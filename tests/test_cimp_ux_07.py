"""Chat, split context, and full workspace are views of one encrypted session.

Switching the view keeps the server session, the pending inquiry id and
revision, the selected evidence item, and the draft text. The switch reads
the existing workspace session through the SDK and does not start another
interview or store the complaint in browser storage.
"""
from __future__ import annotations

from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

NARRATIVE = "On March 1 the office denied the request for the two-bedroom voucher."
EVIDENCE_TITLE = "March voucher denial email"
DRAFT_TITLE = "Voucher denial complaint"
DRAFT_BODY = "The office denied the two-bedroom voucher on March 1."
UNSAVED = " The draft still includes this unsaved sentence."


def _open(tmp_path, monkeypatch, *, world=None):
    world = world or owner_lawyer_journey_world(tmp_path / "world")
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux07-profile"
    profile.mkdir(mode=0o700)
    observed = set()

    def verify_startup_cleanup():
        observed.update(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"] and cleanup["remaining_pids"] == [], "failed startup left owned browser processes"

    with ExitStack() as startup:
        startup.callback(verify_startup_cleanup)
        playwright = browser._load_sync_playwright()().start()
        startup.callback(playwright.stop)
        observed.update(browser._with_descendants(browser._matching_pids((node.argv[1],))))
        context = browser._launch_context(playwright, chromium.path, profile, bridge)
        startup.callback(context.close)
        observed.update(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
        browser._assert_process_custody(node, chromium, profile)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(20000)
        page.set_viewport_size({"width": 1440, "height": 1000})
        startup.pop_all()
    return world, page, playwright, context, node, profile, observed


def _close(playwright, context, node, profile, observed):
    context.close()
    playwright.stop()
    observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
    cleanup = browser._wait_for_cleanup(observed)
    assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
    assert cleanup["remaining_pids"] == []


def _seed(world):
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        headers = _composed_headers(world.case, csrf)
        started = client.post(
            "/api/complaint-workspace/intake-chat",
            headers=headers,
            json={"message": NARRATIVE, "interview_action": "start"},
        )
        assert started.status_code == 200, started.text
        pending = started.json()["session"]["shared_interview"]["pending_inquiry"]
        evidence = client.post(
            "/api/complaint-workspace/evidence",
            headers=headers,
            json={
                "kind": "document",
                "claim_element_id": "adverse_action",
                "title": EVIDENCE_TITLE,
                "content": "The written denial arrived by email on March 1.",
                "source": "inbox",
            },
        )
        assert evidence.status_code == 200, evidence.text
        saved = evidence.json()["saved"]
        draft = client.post(
            "/api/complaint-workspace/update-draft",
            headers=headers,
            json={"title": DRAFT_TITLE, "body": DRAFT_BODY, "requested_relief": ["Restore the voucher review"]},
        )
        assert draft.status_code == 200, draft.text
        session = client.get("/api/complaint-workspace/session", headers=headers, params={"case_id": world.case.case_id})
        assert session.status_code == 200, session.text
        body = session.json()
        shared = body["session"]["shared_interview"]
        assert shared["pending_inquiry"]["inquiry_id"] == pending["inquiry_id"]
        assert shared["pending_inquiry"]["revision"] == pending["revision"]
        assert body["session"]["draft"]["body"] == DRAFT_BODY
        return pending["inquiry_id"], pending["revision"], saved["id"]


def _sign_in(page):
    page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
    page.fill("#case-credential", "synthetic-owner-credential")
    with page.expect_response(lambda response: response.request.method == "POST"
            and response.url.endswith("/api/complaint-workspace/auth/login")):
        page.click("#case-login button[type=submit]")
    page.click("#case-list button")
    page.wait_for_function("""() => document.getElementById('complaint-case-shell-actor').dataset.relationship === 'owner'""")


def _workspace(page, inquiry_id):
    page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
    page.wait_for_function("""(inquiryId) => {
        const pending = document.getElementById('adaptive-pending');
        const draft = document.getElementById('draft-body');
        const shell = document.getElementById('complaint-case-shell');
        return pending && pending.dataset.inquiryId === inquiryId && draft && draft.value
            && shell && shell.getAttribute('aria-busy') === 'false' && shell.dataset.sessionKey;
    }""", arg=inquiry_id)


def _view(page):
    return page.evaluate("""() => {
        const pending = document.getElementById('adaptive-pending');
        const list = document.getElementById('evidence-list');
        return {
            mode: document.documentElement.dataset.workspacePresentation,
            sessionKey: document.getElementById('complaint-case-shell').dataset.sessionKey,
            inquiryId: pending.dataset.inquiryId,
            revision: pending.dataset.revision,
            evidenceId: list.dataset.selectedId || '',
            draft: document.getElementById('draft-body').value,
            title: document.getElementById('draft-title').value,
        };
    }""")


def test_modes_keep_the_same_session_inquiry_evidence_and_draft(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    inquiry_id, revision, evidence_id = _seed(world)
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    posted = []
    page.on("request", lambda request: posted.append((request.method, request.url)) if request.method == "POST" else None)
    try:
        _sign_in(page)
        _workspace(page, inquiry_id)
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        page.evaluate("""({evidenceId, draft}) => {
            const evidenceTab = document.querySelector('.tab-button[data-tab-target="evidence"]');
            if (evidenceTab) evidenceTab.click();
            const item = document.querySelector('#evidence-list button[data-evidence-id="' + evidenceId + '"]');
            if (!item) throw new Error('evidence item missing');
            item.click();
            const body = document.getElementById('draft-body');
            body.value = draft;
            body.dispatchEvent(new Event('input', {bubbles: true}));
        }""", {"evidenceId": evidence_id, "draft": DRAFT_BODY + UNSAVED})
        before_keys = page.evaluate("() => Object.keys(localStorage).sort()")
        before = _view(page)
        assert before["mode"] == "full-workspace"
        assert before["revision"] == str(revision)
        assert before["evidenceId"] == evidence_id
        assert before["draft"] == DRAFT_BODY + UNSAVED
        for mode, context_visible, intake_visible in (
            ("chat-only", False, True),
            ("chat-plus-context", True, True),
            ("full-workspace", False, True),
        ):
            switched = page.evaluate("""async (mode) => window.complaintCaseShell.setPresentationMode(mode)""", mode)
            assert switched is True
            current = _view(page)
            assert current["mode"] == mode
            assert current["sessionKey"] == before["sessionKey"]
            assert current["inquiryId"] == inquiry_id
            assert current["revision"] == str(revision)
            assert current["evidenceId"] == evidence_id
            assert current["draft"] == DRAFT_BODY + UNSAVED
            assert current["title"] == DRAFT_TITLE
            assert page.locator("#complaint-presentation-context").is_visible() is context_visible
            assert page.locator("[data-tab-panel='intake']").is_visible() is intake_visible
            if mode != "full-workspace":
                assert page.locator("[data-tab-panel='draft']").is_hidden()
                assert page.locator("[data-tab-panel='evidence']").is_hidden()
            if mode == "chat-plus-context":
                context_text = page.locator("#complaint-presentation-context").inner_text()
                assert inquiry_id in context_text
                assert str(revision) in context_text
                assert EVIDENCE_TITLE in context_text
                assert DRAFT_BODY + UNSAVED in context_text
        continuity = page.evaluate("""async () => {
            const read = await window.workspaceClient.readCanonicalSession(window.complaintCaseShell.binding());
            return read.continuity;
        }""")
        assert continuity["transport"] == "complaint-workspace-session"
        assert continuity["inquiry_id"] == inquiry_id
        assert continuity["inquiry_revision"] == revision
        assert evidence_id in continuity["evidence_ids"]
        assert continuity["draft_body"] == DRAFT_BODY
        assert continuity["draft_title"] == DRAFT_TITLE
        stored = page.evaluate("() => Object.entries(localStorage).map(([key, value]) => key + '=' + value).join('\\n')")
        assert DRAFT_BODY not in stored
        assert inquiry_id not in stored
        assert "complaint-entry-question" not in stored
        after_keys = page.evaluate("() => Object.keys(localStorage).sort()")
        assert after_keys == before_keys
        assert not any(url.endswith("/api/complaint-workspace/intake-chat") for _method, url in posted)
        focused = page.evaluate("""async () => {
            document.getElementById('adaptive-answer').focus();
            await window.complaintCaseShell.setPresentationMode('chat-only');
            return document.activeElement.id;
        }""")
        assert focused == "adaptive-answer"
    finally:
        _close(playwright, context, node, profile, observed)


def test_unknown_mode_and_locked_case_do_not_invent_a_session(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    inquiry_id, _revision, _evidence_id = _seed(world)
    world.service.lock_private_keys()
    world.owner_keys.lock()
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    try:
        _sign_in(page)
        page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        page.wait_for_function("""() => document.getElementById('complaint-entry').dataset.entry === 'missing-key'
            && document.getElementById('complaint-case-shell').getAttribute('aria-busy') === 'false'""")
        refused = page.evaluate("""async () => window.complaintCaseShell.setPresentationMode('client-interview')""")
        assert refused is False
        assert page.locator("#complaint-presentation-status").inner_text() == "That workspace view is not available."
        assert page.evaluate("() => document.documentElement.dataset.workspacePresentation") == "full-workspace"
        switched = page.evaluate("""async () => window.complaintCaseShell.setPresentationMode('chat-plus-context')""")
        assert switched is True
        assert page.locator("#complaint-presentation-context").is_visible()
        context_text = page.locator("#complaint-presentation-context").inner_text()
        assert inquiry_id not in context_text
        assert DRAFT_BODY not in context_text
        assert NARRATIVE not in context_text
        assert page.locator("#complaint-entry-question").inner_text() == ""
        stored = page.evaluate("() => Object.entries(localStorage).map(([key, value]) => key + '=' + value).join('\\n')")
        assert inquiry_id not in stored
        assert DRAFT_BODY not in stored
        assert page.evaluate("() => typeof window.localComplaintStore") == "undefined"
    finally:
        _close(playwright, context, node, profile, observed)
