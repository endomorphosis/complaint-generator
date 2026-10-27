"""First-run, sign-in, unlock, and cold-resume entry.

A new person can see how to name a complaint. An existing owner selects the
real case and, once the private key is available, resumes the server's pending
question. A denied sign-in, a missing key, and an unavailable catalog stay
explicit. The browser does not invent a case, show a ready badge, rebuild the
question from storage, or hide a consent grant.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import PASSPHRASE, _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

NARRATIVE = "On March 1 the office denied the request for the two-bedroom voucher."
CACHE_QUESTION = "browser-cache-question-ux06-must-not-appear"


def _open(tmp_path, monkeypatch):
    world = owner_lawyer_journey_world(tmp_path / "world")
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux06-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    browser._assert_process_custody(node, chromium, profile)
    observed = set(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(20000)
    page.set_viewport_size({"width": 1440, "height": 1000})
    return world, page, playwright, context, node, profile, observed


def _close(playwright, context, node, profile, observed):
    context.close()
    playwright.stop()
    observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
    cleanup = browser._wait_for_cleanup(observed)
    assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
    assert cleanup["remaining_pids"] == []


def _sign_in(page, credential):
    page.fill("#case-credential", credential)
    with page.expect_response(lambda response: response.request.method == "POST"
            and response.url.endswith("/api/complaint-workspace/auth/login")) as login:
        page.click("#case-login button[type=submit]")
    return login.value


def _shell_ready(page):
    page.wait_for_function("""() => window.complaintCaseShell
        && document.getElementById('complaint-entry')
        && document.getElementById('complaint-case-shell').getAttribute('aria-busy') === 'false'""")


def _pending_question(world):
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _composed_login(client)
        started = client.post(
            "/api/complaint-workspace/intake-chat",
            headers=_composed_headers(world.case, csrf),
            json={"message": NARRATIVE, "interview_action": "start"},
        )
        assert started.status_code == 200, started.text
        pending = started.json()["session"]["shared_interview"]["pending_inquiry"]
        question = pending.get("question") or pending.get("prompt")
        assert question and question != CACHE_QUESTION
        assert NARRATIVE not in question
        return pending["inquiry_id"], question


def _lock(world):
    world.service.lock_private_keys()
    world.owner_keys.lock()


def _unlock(world):
    assert world.service.unlock_private_keys(passphrase=PASSPHRASE)["unlocked"] is True
    world.owner_keys.unlock_passphrase(PASSPHRASE)


def test_new_user_can_identify_and_begin_a_complaint(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    try:
        opened = page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        assert opened.status == 200
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        _shell_ready(page)
        assert page.locator("#workspace-begin-complaint").inner_text() == "Begin a complaint"
        assert page.locator("#complaint-entry").get_attribute("data-entry") == "first-run"
        assert page.locator("#complaint-entry").get_attribute("data-ready-badge") == "false"
        assert page.locator("#complaint-entry-consent-remote").is_checked() is False
        page.click("#workspace-begin-complaint")
        page.wait_for_url("**/cases#create-case")
        assert page.locator("#case-label").is_visible()
        _shell_ready(page)
        denied = _sign_in(page, "not-a-real-credential")
        assert denied.status == 401
        assert page.locator("#case-error").inner_text() == "authentication_failed"
        assert page.locator("#complaint-entry").get_attribute("data-entry") == "denied"
        assert page.locator("#complaint-entry").get_attribute("data-ready-badge") == "false"
        assert "No replacement case" in page.locator("#complaint-entry-boundary").inner_text()
        assert page.locator("#case-list").get_attribute("data-state") == "error"
        issued = _sign_in(page, "synthetic-stranger-credential")
        assert issued.status == 200
        _shell_ready(page)
        page.wait_for_function("() => document.getElementById('complaint-entry').dataset.entry === 'first-run'")
        page.click("#complaint-entry-begin")
        assert page.evaluate("() => document.activeElement.id") == "case-label"
        page.fill("#case-label", "First complaint from the new account")
        page.click("#create-case button[type=submit]")
        page.wait_for_function("""() => Array.from(document.querySelectorAll('#case-list button'))
            .some(button => button.textContent.includes('First complaint from the new account'))""")
        labels = page.locator("#case-list button").all_inner_texts()
        assert labels == ["First complaint from the new account"]
        assert page.locator("#case-list").get_attribute("data-ready-badge") == "false"
        assert world.case.case_id not in " ".join(labels)
    finally:
        _close(playwright, context, node, profile, observed)


def test_owner_selects_unlocks_and_resumes_the_pending_question(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    try:
        inquiry_id, question = _pending_question(world)
        _lock(world)
        opened = page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        assert opened.status == 200
        page.evaluate("""(cached) => {
            localStorage.setItem('complaint-entry-question', cached);
            sessionStorage.setItem('complaint-entry-question', cached);
        }""", CACHE_QUESTION)
        _sign_in(page, "synthetic-owner-credential")
        page.click("#case-list button")
        _shell_ready(page)
        page.wait_for_function("""(caseId) => document.getElementById('complaint-entry').dataset.entry === 'missing-key'
            && document.getElementById('complaint-entry').dataset.caseId === caseId""", arg=world.case.case_id)
        entry_text = page.locator("#complaint-entry").inner_text()
        assert question not in entry_text
        assert CACHE_QUESTION not in entry_text
        assert page.locator("#complaint-case-shell").get_attribute("data-ready-badge") == "false"
        assert page.locator("#complaint-case-shell").get_attribute("data-state") == "missing-key"
        assert page.locator("#case-context").get_attribute("data-state") == "locked"
        before = [item["case_id"] for item in page.evaluate("""async () => {
            const response = await fetch('/api/cases', {credentials: 'same-origin', headers: {accept: 'application/json'}});
            const body = await response.json();
            return body.cases || [];
        }""")]
        posted = []
        page.on("request", lambda request: posted.append((request.method, request.url, request.post_data or "")))
        page.fill("#complaint-entry-passphrase", PASSPHRASE)
        page.click("#complaint-entry-unlock button[type=submit]")
        page.wait_for_function("""() => {
            const result = document.getElementById('complaint-entry-unlock-result').textContent;
            return result.includes('still missing') && result.includes('unavailable');
        }""")
        assert all(PASSPHRASE not in body for _method, _url, body in posted)
        assert CACHE_QUESTION not in page.evaluate("() => JSON.stringify({...localStorage, ...sessionStorage})")
        still = [item["case_id"] for item in page.evaluate("""async () => {
            const response = await fetch('/api/cases', {credentials: 'same-origin', headers: {accept: 'application/json'}});
            const body = await response.json();
            return body.cases || [];
        }""")]
        assert still == before
        assert page.locator("#complaint-entry").get_attribute("data-entry") == "missing-key"
        _unlock(world)
        page.click("#complaint-entry-unlock button[type=submit]")
        page.wait_for_function("""(inquiryId) => {
            const entry = document.getElementById('complaint-entry');
            const question = document.getElementById('complaint-entry-question');
            return entry.dataset.entry === 'resume' && question.dataset.inquiryId === inquiryId && !question.hidden;
        }""", arg=str(inquiry_id))
        assert page.locator("#complaint-entry-question").inner_text() == question
        assert CACHE_QUESTION not in page.locator("#complaint-case-shell").inner_text()
        assert page.locator("#complaint-entry-consent-remote").is_checked() is False
        assert page.locator("#complaint-entry").get_attribute("data-consent") == "visible-not-granted"
        consent_posts = [item for item in posted if "processing-consent" in item[1] and item[0] == "POST"]
        assert consent_posts == []
        page.locator("[data-case-panel='mediator']").wait_for(state="visible")
        assert question in page.locator("[data-case-panel='mediator']").inner_text()
    finally:
        _close(playwright, context, node, profile, observed)


def test_unavailable_catalog_is_explicit_and_opens_no_replacement_case(tmp_path, monkeypatch):
    world, page, playwright, context, node, profile, observed = _open(tmp_path, monkeypatch)
    try:
        opened = page.goto(browser.SAME_ORIGIN + "/cases", wait_until="domcontentloaded")
        assert opened.status == 200
        _sign_in(page, "synthetic-owner-credential")
        page.click("#case-list button")
        _shell_ready(page)
        page.wait_for_function("() => document.getElementById('complaint-case-shell-case').dataset.bound === 'case'")
        case_id = page.locator("#complaint-case-shell-case").get_attribute("data-case-id")
        assert case_id == world.case.case_id
        page.evaluate("""() => {
            const original = window.fetch.bind(window);
            window.fetch = function (input, options) {
                const raw = typeof input === 'string' ? input : input.url;
                const path = new URL(raw, location.origin).pathname;
                if (path === '/api/cases/session') {
                    return Promise.resolve(new Response(JSON.stringify({error: 'catalog_unavailable'}),
                        {status: 503, headers: {'content-type': 'application/json'}}));
                }
                return original(input, options);
            };
        }""")
        page.evaluate("() => window.complaintCaseShell.refresh()")
        page.wait_for_function("() => document.getElementById('complaint-entry').dataset.entry === 'unavailable'")
        assert page.locator("#complaint-case-shell").get_attribute("data-ready-badge") == "false"
        assert page.locator("#complaint-case-shell").get_attribute("data-state") != "ready"
        assert page.locator("#complaint-entry-question").is_hidden()
        assert "unavailable" in page.locator("#complaint-entry-title").inner_text().lower()
        assert page.locator("#complaint-case-shell-case").get_attribute("data-bound") == "empty"
        listed = page.locator("#case-list button").all_inner_texts()
        assert any("owner-lawyer-journey" in label for label in listed)
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
    finally:
        _close(playwright, context, node, profile, observed)
