"""Accepted answers and corrections update the canonical graphs once.

A reply carries the server question id and the revision the person was shown.
A stale or conflicting reply stays readable JSON, leaves the pending inquiry
and encrypted head alone, and cannot repaint another case or admitted law.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from tests import gui_native_browser as browser
from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
from tests.test_cimp_gui_14 import _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

NARRATIVE = ("My employer discriminated against me and denied my request for an accessible workplace on April 2, 2024. "
             "Under Oregon law. Applicable law date: 2024-06-01.")
LAW_TEXT = "An employer shall provide written notice to an employee before denying an accommodation."
LAW_CITATION = "Synthetic UX10 fixture notice rule"
LAW_VERSION = "synthetic-2024-edition"
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


def _provision_local_source(world):
    # Authored operator fixture bytes go through real encrypted authority storage
    # and the production source/temporal admission path. No verification flags,
    # acquisition result, governing-law decision, or model response is supplied.
    mediator = world.service._mediator_for_shared_interview(world.case.tenant_id, world.case.case_id)
    source = {
        "type": "statute", "source": "authored-local-test-corpus", "title": "Synthetic notice rule",
        "citation": LAW_CITATION, "content": LAW_TEXT, "jurisdiction": "OR",
        "metadata": {
            "source_text": LAW_TEXT, "source_hash": hashlib.sha256(LAW_TEXT.encode()).hexdigest(),
            "authority_id": "synthetic-ux10-notice", "authority_version": LAW_VERSION,
            "effective_date": "2024-01-01", "as_of_date": "2024-06-01",
            "provenance": {"source_id": "synthetic-ux10-notice"},
        },
    }
    stored = mediator.legal_authority_storage.add_authority(source, world.case.tenant_id,
        claim_type="employment_discrimination")
    assert stored > 0


def _assert_source_bound_law(graph):
    nodes = graph.get("nodes") or {}
    matching = [node for node in nodes.values()
        if node.get("node_type") == "legal_element"
        and (node.get("attributes") or {}).get("dependency_class") == "legally_sourced_requirement"
        and (node.get("attributes") or {}).get("citation") == LAW_CITATION]
    assert matching, "the actual source admission did not produce a legal requirement"
    for node in matching:
        attrs = node["attributes"]
        assert attrs["source_available"] is True
        assert attrs["source_bound"] is True
        assert attrs["source_hash"] == hashlib.sha256(LAW_TEXT.encode()).hexdigest()
        assert attrs["authority_version"] == LAW_VERSION
        assert attrs["temporal_applicability"]["applicable"] is True
        assert attrs["law_derived"] is False
        span = attrs["source_span"]
        assert LAW_TEXT.encode()[span["start"]:span["end"]].decode() == attrs["rule_text"]


def _assert_factual_statement(graph, statement, *, status):
    states = ((graph.get("metadata") or {}).get("factual_ledger") or {}).get("assertion_states") or {}
    matching = [row for row in states.values()
        if (row.get("envelope") or {}).get("source_text") == statement and row.get("status") == status]
    assert matching, f"the persisted factual graph lacks the {status} statement"
    for row in matching:
        envelope = row["envelope"]
        assert envelope["is_asserted_user_fact"] is True
        entity = graph["entities"][row["entity_id"]]
        assert entity["provenance"]["user_assertion"]["source_text"] == statement
    return matching


def _rpc_arguments(request, action):
    if request.method != "POST" or not request.url.endswith("/api/complaint-workspace/mcp/rpc"):
        return None
    body = json.loads(request.post_data or "{}")
    params = body.get("params") or {}
    arguments = params.get("arguments") or {}
    if (body.get("method") == "tools/call" and params.get("name") == "complaint.run_intake_chat_turn"
            and arguments.get("interview_action") == action):
        return arguments
    return None


def _rpc_payload(response):
    body = response.json()
    result = body["result"]
    return result.get("structuredContent", result)


def _seed(world):
    _provision_local_source(world)
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
        _assert_source_bound_law(session["shared_interview"]["dependency_graph"])
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
        arguments = _rpc_arguments(request, "answer")
        if arguments is not None:
            posted.append(arguments)

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
        assert len(posted) == 1, "one answer click must issue one answer RPC"
        arguments = posted[0]
        assert arguments["question_id"] == seeded["inquiry_id"]
        assert arguments["expected_question_revision"] == seeded["revision"]
        assert arguments["interview_action"] == "answer"
        assert arguments["message"] == ANSWER
        after = _server_graphs(page)
        assert after["status"] == 200
        assert after["supportCount"] == 1
        assert after["effects"] == [f"answer:{seeded['inquiry_id']}:{seeded['revision']}"]
        assert after["changesLaw"] is False
        _assert_source_bound_law(json.loads(after["legal"]))
        assert json.loads(after["legal"]) == json.loads(seeded["legal"])
        assert json.loads(after["factual"]) != json.loads(seeded["graph"])
        _assert_factual_statement(json.loads(after["factual"]), ANSWER, status="active")
        assert after["offer"]["schema"] == "gui-factual-correction-v1"
        assert after["offer"]["requires_expected_revision"] is True
        assert after["offer"]["prior_answer"] == ANSWER
        assert after["offer"]["target_stable_id"]
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
        assert still["factual"] == after["factual"]
        _assert_source_bound_law(json.loads(still["legal"]))
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
        unchanged = _server_graphs(page)
        assert unchanged["head"] == head_after_answer
        assert unchanged["factual"] == after["factual"]
        assert unchanged["legal"] == after["legal"]
        page.fill("#factual-correction-replacement", CORRECTION)
        with page.expect_response(lambda response: _rpc_arguments(response.request, "correct") is not None) as actual:
            page.click("#factual-correction-submit")
        response = actual.value
        assert response.status == 200
        payload = _rpc_payload(response)
        receipt = payload["factual_correction"]
        assert receipt["status"] == "applied", receipt
        assert receipt["correction"]["lineage"]["previous_envelope_retained"] is True
        assert receipt["correction"]["lineage"]["previous_status"] == "superseded"
        page.wait_for_function("""() => {
            const node = document.getElementById('inquiry-graph-change');
            return node && node.dataset.applied === 'true' && node.dataset.count === '2'
                && !node.dataset.conflict && node.dataset.effectId.startsWith('correction:');
        }""")
        corrected = _server_graphs(page)
        assert corrected["status"] == 200
        assert corrected["changesLaw"] is False
        _assert_source_bound_law(json.loads(corrected["legal"]))
        assert json.loads(corrected["legal"]) == json.loads(after["legal"])
        assert corrected["supportCount"] == 2
        assert corrected["effects"][0] == after["effects"][0]
        assert corrected["effects"][1].startswith("correction:")
        assert len(set(corrected["effects"])) == 2
        assert corrected["head"] != head_after_answer
        assert corrected["factual"] != after["factual"]
        corrected_graph = json.loads(corrected["factual"])
        _assert_factual_statement(corrected_graph, ANSWER, status="superseded")
        _assert_factual_statement(corrected_graph, CORRECTION, status="active")
        replay = page.evaluate("""async (fields) => {
            const client = window.workspaceClient;
            const userId = (client.caseContext && client.caseContext.tenant_id) || '';
            const result = await client.submitCanonicalGraphCorrection(userId, fields.replacement, fields);
            return {accepted: result.accepted, conflict: result.conflict, readable: typeof result.payload === 'object'};
        }""", {
            "replacement": CORRECTION,
            "expected_graph_revision": after["offer"]["expected_graph_revision"],
            "expected_session_revision": after["offer"]["expected_session_revision"],
            "target_stable_id": after["offer"]["target_stable_id"],
            "actor_principal_id": after["offer"]["actor_principal_id"],
            "question_id": after["offer"]["target_stable_id"],
        })
        assert replay["accepted"] is False
        assert replay["conflict"] == "stale_target"
        assert replay["readable"] is True
        replayed = _server_graphs(page)
        assert replayed["status"] == 200
        assert replayed["supportCount"] == 2
        assert replayed["effects"] == corrected["effects"]
        assert replayed["legal"] == corrected["legal"]
        assert replayed["head"] == corrected["head"]
        assert replayed["factual"] == corrected["factual"]
    finally:
        _close(playwright, context, node, profile, observed)
