"""Accepted answers and corrections update the canonical graphs once.

A reply carries the server question id and the revision the person was shown.
A stale or conflicting reply stays readable JSON, leaves the pending inquiry
and encrypted head alone, and cannot repaint another case or admitted law.
"""
from __future__ import annotations

import json
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

NARRATIVE = "On April 2 the office denied the request for the accessible unit."
ANSWER = "The denial was given in person by the office manager on April 2."
CORRECTION = "The denial was given in writing by the office manager on April 2."


def _legal_digest(graph):
    return json.dumps(graph or {}, sort_keys=True, default=str, separators=(",", ":"))


def _open(tmp_path, monkeypatch, *, world):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux10-profile"
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
    return page, playwright, context, node, profile, observed


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
            json={"message": NARRATIVE, "interview_action": "start", "question_id": "original_complaint"},
        )
        assert started.status_code == 200, started.text
        body = started.json()
        session = body["session"]
        pending = session["shared_interview"]["pending_inquiry"]
        return {
            "inquiry_id": pending["inquiry_id"],
            "revision": pending["revision"],
            "question": pending["question"],
            "legal": _legal_digest(session["shared_interview"].get("dependency_graph")),
            "graph": _legal_digest(session["shared_interview"].get("knowledge_graph")),
            "head": body["encrypted_head"]["private_revision"],
            "case_id": session.get("case_id") or world.case.case_id,
        }


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
        const card = document.getElementById('inquiry-card');
        return card && card.dataset.pending === 'true' && card.dataset.inquiryId === inquiryId
            && document.getElementById('adaptive-submit-answer');
    }""", arg=inquiry_id)
    page.locator('#complaint-case-shell-nav [data-case-task="mediator"]').click()
    page.locator('[data-case-panel="mediator"] #adaptive-answer').wait_for(state="visible")


def _server_graphs(page):
    return page.evaluate("""async () => {
        const binding = window.complaintCaseShell.binding();
        const response = await fetch('/api/complaint-workspace/session?case_id=' + encodeURIComponent(binding.case_id), {
            credentials: 'same-origin',
            headers: {
                'x-case-id': binding.case_id,
                'x-tenant-id': binding.tenant_id,
                'x-resource-id': binding.resource_id,
                'x-expected-revision': String(binding.directory_revision),
            },
        });
        const body = await response.json();
        const session = body.session || {};
        const interview = session.shared_interview || {};
        const pending = interview.pending_inquiry || {};
        const projection = body.affected_support_projection || session.affected_support_projection || [];
        return {
            status: response.status,
            caseId: session.case_id || '',
            inquiryId: pending.inquiry_id || '',
            revision: pending.revision,
            question: pending.question || '',
            head: (body.encrypted_head || {}).private_revision || String(session.private_revision || ''),
            supportCount: projection.length,
            effects: projection.map((item) => item.effect_id),
            changesLaw: projection.some((item) => item.changes_law === true),
            legal: JSON.stringify(interview.dependency_graph || {}),
            factual: JSON.stringify(interview.knowledge_graph || {}),
            offer: ((body.adaptive_inquiry || {}).factual_correction) || {},
        };
    }""")


def test_answer_and_correction_update_graphs_once_and_stale_replies_do_not(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    seeded = _seed(world)
    page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch, world=world)
    posted = []

    def remember(request):
        if request.method == "POST" and request.url.endswith("/api/complaint-workspace/mcp/rpc"):
            posted.append(request.post_data or "")

    try:
        _sign_in(page)
        _workspace(page, seeded["inquiry_id"])
        page.on("request", remember)
        page.fill("#adaptive-answer", ANSWER)
        page.click("#adaptive-submit-answer")
        page.wait_for_function("""() => {
            const node = document.getElementById('inquiry-graph-change');
            return node && node.dataset.applied === 'true' && node.dataset.changesLaw === 'false';
        }""")
        shown = page.evaluate("""() => {
            const card = document.getElementById('inquiry-card');
            const change = document.getElementById('inquiry-graph-change');
            return {
                inquiryId: card.dataset.inquiryId,
                revision: card.dataset.revision,
                changeText: document.getElementById('inquiry-graph-change-text').textContent,
                count: change.dataset.count,
                caseId: change.dataset.caseId,
            };
        }""")
        assert posted, "the answer was not submitted"
        body = json.loads(posted[-1])
        arguments = body["params"]["arguments"]
        assert arguments["question_id"] == seeded["inquiry_id"]
        assert arguments["expected_question_revision"] == seeded["revision"]
        assert arguments["interview_action"] == "answer"
        assert arguments["message"] == ANSWER
        after = _server_graphs(page)
        assert after["status"] == 200
        assert after["supportCount"] == 1
        assert after["effects"] == [f"answer:{seeded['inquiry_id']}:{seeded['revision']}"]
        assert after["changesLaw"] is False
        assert json.loads(after["legal"]) == json.loads(seeded["legal"])
        assert json.loads(after["factual"]) != json.loads(seeded["graph"])
        assert after["inquiryId"] == shown["inquiryId"]
        assert after["inquiryId"] != seeded["inquiry_id"] or after["revision"] != seeded["revision"]
        assert "factual graph was updated once" in shown["changeText"]
        head_after_answer = after["head"]
        pending_after_answer = after["inquiryId"]
        stale = page.evaluate("""async (prior) => {
            const client = window.workspaceClient;
            const userId = (client.caseContext && client.caseContext.tenant_id) || '';
            const result = await client.submitCanonicalGraphAnswer(userId, prior.answer + ' stale', {
                question_id: prior.inquiryId,
                expected_question_revision: prior.revision,
            });
            const card = document.getElementById('inquiry-card');
            return {
                accepted: result.accepted,
                conflict: result.conflict,
                readable: result.payload && typeof result.payload === 'object',
                payloadConflict: result.payload && result.payload.conflict,
                cardInquiry: card.dataset.inquiryId,
                cardRevision: card.dataset.revision,
                keptHead: (result.payload && result.payload.encrypted_head && result.payload.encrypted_head.private_revision) || '',
                keptInquiry: ((result.payload && result.payload.session && result.payload.session.shared_interview && result.payload.session.shared_interview.pending_inquiry) || {}).inquiry_id || '',
            };
        }""", {"answer": ANSWER, "inquiryId": seeded["inquiry_id"], "revision": seeded["revision"]})
        assert stale["accepted"] is False
        assert stale["readable"] is True
        assert stale["conflict"] == "stale_question"
        assert stale["payloadConflict"] == "stale_question"
        assert stale["cardInquiry"] == pending_after_answer
        assert stale["keptInquiry"] == pending_after_answer
        assert stale["keptHead"] == head_after_answer
        still = _server_graphs(page)
        assert still["supportCount"] == 1
        assert still["head"] == head_after_answer
        assert still["inquiryId"] == pending_after_answer
        assert still["legal"] == after["legal"]
        foreign = page.evaluate("""() => {
            const card = document.getElementById('inquiry-card');
            const before = card.dataset.inquiryId;
            window.complaintConversation.project({
                conflict: null,
                session: {
                    case_id: 'case-newer-than-the-open-case',
                    shared_interview: {pending_inquiry: {inquiry_id: 'inq-foreign', revision: 9, question: 'A different case question'}},
                },
                encrypted_head: {case_id: 'case-newer-than-the-open-case', private_revision: '0'},
            });
            return {before: before, after: card.dataset.inquiryId, question: document.getElementById('inquiry-card-question').textContent};
        }""")
        assert foreign["after"] == foreign["before"]
        assert "different case" not in foreign["question"]
        page.fill("#factual-correction-replacement", CORRECTION)
        page.click("#factual-correction-submit")
        page.wait_for_function("""() => {
            const node = document.getElementById('inquiry-graph-change');
            return node && (node.dataset.applied === 'true' || node.dataset.conflict);
        }""")
        corrected = _server_graphs(page)
        change = page.evaluate("""() => document.getElementById('inquiry-graph-change').dataset.conflict""")
        assert corrected["changesLaw"] is False
        assert json.loads(corrected["legal"]) == json.loads(after["legal"])
        if change:
            assert corrected["supportCount"] == 1
            assert corrected["head"] == head_after_answer
            assert corrected["inquiryId"] == pending_after_answer
        else:
            assert corrected["supportCount"] == 2
            assert corrected["effects"][0] == after["effects"][0]
            assert corrected["effects"][1].startswith("correction:")
            replay = page.evaluate("""async (fields) => {
                const client = window.workspaceClient;
                const userId = (client.caseContext && client.caseContext.tenant_id) || '';
                const result = await client.submitCanonicalGraphCorrection(userId, fields.replacement, fields);
                return {accepted: result.accepted, conflict: result.conflict, readable: typeof result.payload === 'object'};
            }""", {
                "replacement": CORRECTION,
                "expected_graph_revision": after["offer"].get("expected_graph_revision"),
                "expected_session_revision": after["offer"].get("expected_session_revision"),
                "target_stable_id": after["offer"].get("target_stable_id") or "",
                "actor_principal_id": after["offer"].get("actor_principal_id") or "",
                "question_id": after["offer"].get("target_stable_id") or "",
            })
            assert replay["readable"] is True
            replayed = _server_graphs(page)
            assert replayed["supportCount"] == 2
            assert replayed["legal"] == corrected["legal"]
            assert replayed["head"] == corrected["head"]
    finally:
        _close(playwright, context, node, profile, observed)
