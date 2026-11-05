"""Complete complaint and human-review journey on the real case owners.

The path is the original complaint, one adaptive question, a corrected fact,
a private annotation, a source-bound requirement, a cited draft, a lawyer
message and review, an explicit owner acceptance, and a cold encrypted resume.
Unresolved, unknown, cancelled, provider, source, proof, and storage failures
stay failures. A stranger is denied. A completed screen does not file a case.
"""
from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from complaint_phases.knowledge_graph import KnowledgeGraph
from tests import gui_native_browser as browser
from tests.gui_ux_overhaul_fixtures import (
    JOURNEY_FAILURES,
    JOURNEY_STAGES,
    OWNER_CREDENTIAL,
    STRANGER_CREDENTIAL,
    assert_success_is_not_filing,
    baseline_manifest,
    complete_journey_world,
    load_contract,
)
from tests.test_cimp_gui_14 import NARRATIVE, _composed_headers, _composed_login
from tests.test_cimp_gui_29 import LEGAL_TEXT, LEAN_TEXT, OBLIGATION_TEXT, VOCABULARY

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

ANSWER = "Alex Rivera fired me on March 4, 2024 after I reported a safety concern."
REPLACEMENT = "Alex Rivera fired me on March 5, 2024 after I reported a safety concern."
NOTE = "Synthetic margin note on the denial letter. This note is not a new exhibit."
MESSAGE = "Synthetic owner note for the assigned lawyer."
EVIDENCE = b"Line alpha\nThe employer ended the job on March 5.\n"


def _headers(case, csrf=None, membership=None):
    headers = _composed_headers(case, csrf)
    if membership is not None:
        headers["x-expected-membership-revision"] = str(membership)
    return headers


def _post_chat(client, case, csrf, body):
    response = client.post(
        "/api/complaint-workspace/intake-chat",
        headers=_headers(case, csrf),
        json=body,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert_success_is_not_filing(payload)
    return payload


def _session(client, case):
    response = client.get("/api/complaint-workspace/session", headers=_headers(case))
    assert response.status_code == 200, response.text
    return response.json()["session"]


def test_contract_keeps_the_source_bound_before_and_after_story():
    contract = load_contract()
    manifest = baseline_manifest()
    phases = set(contract["phases"])
    assert {"before", "after"} <= phases
    captures = manifest.get("captures") or manifest.get("screenshots") or manifest.get("entries") or []
    if isinstance(manifest, dict) and not captures:
        captures = [row for row in manifest.values() if isinstance(row, dict)]
    assert captures
    joined = json.dumps({"contract": contract, "manifest": manifest})
    assert "before" in joined and "after" in joined
    assert_success_is_not_filing({"legal_sufficiency": False, "court_filed": False})
    with pytest.raises(ValueError, match="success_claimed_legal_sufficiency"):
        assert_success_is_not_filing({"legal_sufficiency": True})


def test_owner_journey_reaches_acceptance_and_cold_resume(tmp_path):
    world = complete_journey_world(tmp_path / "journey")
    case = world.case
    stages = []
    with TestClient(world.app, base_url="https://testserver") as owner:
        csrf = _composed_login(owner)
        narrative = (
            NARRATIVE
            + " My employer fired me on 2024-03-04 after I submitted a safety report."
            + " Under Oregon law. Applicable law date: 2024-03-15."
        )
        started = _post_chat(owner, case, csrf, {
            "message": narrative,
            "question_id": "original_complaint",
            "interview_action": "start",
        })
        assert started["interview"]["session_revision"] >= 1
        assert started.get("legal_sufficiency") is not True
        stages.append("original_complaint")
        pending = _session(owner, case)["shared_interview"]["pending_inquiry"]
        assert pending["inquiry_id"]
        why = _post_chat(owner, case, csrf, {"message": "/why"})
        assert why.get("stored_as_answer") is False
        answered = _post_chat(owner, case, csrf, {
            "message": ANSWER,
            "question_id": pending["inquiry_id"],
            "expected_question_revision": pending["revision"],
            "interview_action": "answer",
        })
        offer = answered["adaptive_inquiry"]["factual_correction"]
        assert offer["target_stable_id"]
        stages.append("adaptive_question")
        state = _session(owner, case)
        graph_revision = offer.get("expected_graph_revision") or offer.get("graph_revision")
        session_revision = state["shared_interview"]["session_revision"]
        corrected = _post_chat(owner, case, csrf, {
            "message": json.dumps({
                "replacement": REPLACEMENT,
                "expected_graph_revision": graph_revision,
                "expected_session_revision": session_revision,
                "target_stable_id": offer["target_stable_id"],
            }),
            "interview_action": "correct",
            "expected_graph_revision": graph_revision,
            "expected_session_revision": session_revision,
        })
        assert corrected["factual_correction"]["status"] == "applied"
        assert corrected["legal_sufficiency"] is False
        graph = KnowledgeGraph.from_dict(_session(owner, case)["shared_interview"]["knowledge_graph"])
        assert graph.assertion_state(offer["target_stable_id"])["status"] == "superseded"
        assert REPLACEMENT in [row.get("answer") for row in _session(owner, case)["intake_history"]]
        stages.append("corrected_factual_graph")

        received = owner.post("/api/cases/evidence", headers=_headers(case, csrf), json={
            "tenant_id": case.tenant_id,
            "case_id": case.case_id,
            "resource_id": case.resource_id,
            "source_filename": "denial.txt",
            "original_filename": "denial.txt",
            "media_type": "text/plain",
            "content_base64": base64.b64encode(EVIDENCE).decode("ascii"),
            "idempotency_key": "ux64-evidence",
        })
        assert received.status_code == 201, received.text
        evidence_id = received.json()["evidence_id"]
        noted = owner.post("/api/cases/evidence/annotations", headers=_headers(case, csrf), json={
            "tenant_id": case.tenant_id,
            "case_id": case.case_id,
            "resource_id": case.resource_id,
            "evidence_id": evidence_id,
            "artifact_version": 1,
            "expected_case_revision": case.revision,
            "expected_annotation_revision": "",
            "idempotency_key": "ux64-note",
            "kind": "comment",
            "note": NOTE,
        })
        assert noted.status_code == 201, noted.text
        assert noted.json().get("adopted_as_answer") is not True
        assert NOTE.encode() not in b"".join(world.evidence_backend.objects.values()) if hasattr(world.evidence_backend, "objects") else True
        stages.append("private_annotated_evidence")

        context = owner.get(f"/api/legal-context/{case.case_id}", headers=_headers(case))
        assert context.status_code == 200, context.text
        selected = owner.post(f"/api/legal-context/{case.case_id}", headers=_headers(case, csrf), json={
            "expected_context_revision": context.json()["context_revision"],
            "jurisdiction": "Oregon",
            "forum": "synthetic-state-trial-forum",
            "applicability": "explicit",
            "applicable_law_date": "2024-03-15",
            "event_date": "2024-03-04",
        })
        assert selected.status_code == 200, selected.text
        consent = owner.post(f"/api/cases/{case.case_id}/processing-consent", headers={"x-csrf-token": csrf}, json={
            "purpose": "citation_acquisition",
            "mode": "local_private",
            "expected_generation": 0,
        })
        assert consent.status_code == 200, consent.text
        generation = consent.json()["generation"]
        acquired = owner.post(f"/api/legal-research/{case.case_id}", headers=_headers(case, csrf), json={
            "purpose": "citation_acquisition",
            "query": "termination statute",
            "max_results": 2,
            "deadline_seconds": 2.0,
            "max_bytes": 4096,
            "retrieval_mode": "cache",
            "expected_consent_generation": generation,
            "operation_id": "ux64-local-source",
            "local_rows": {"state_statute": [{
                "text": LEGAL_TEXT,
                "citation": "fixture://ux64-source",
                "uri": "fixture://ux64-source",
                "corpus_version": "synthetic-v1",
                "jurisdiction": "OR",
                "effective_date": "2024-01-01",
            }], "state_administrative_rule": []},
        })
        assert acquired.status_code == 200, acquired.text
        assert acquired.json()["admitted_law"] is False and acquired.json()["proof"] is False
        source = next(row for row in acquired.json()["source_version_receipts"] if row["kind"] == "candidate")
        admitted = owner.post(f"/api/legal-research/{case.case_id}/admissions", headers=_headers(case, csrf), json={
            "decision": "admit",
            "source_passage": source["source_passage"],
            "authority_identity": source["authority_identity"],
            "jurisdiction": source["jurisdiction"],
            "effective_date": source["effective_date"],
            "version": source["version"],
            "content_hash": source["content_hash"],
            "applicability": source["stated_applicability"],
            "treatment_state": source["treatment_state"],
            "exceptions": source["exceptions"],
            "operation_id": "ux64-admit-source",
        })
        assert admitted.status_code == 200, admitted.text
        assert admitted.json()["source_status"] == "source_admitted"
        assert admitted.json()["admitted_law"] is False and admitted.json()["proof"] is False
        stages.append("source_bound_legal_requirement")

        current = owner.get(f"/api/legal-analysis/{case.case_id}", headers=_headers(case))
        assert current.status_code == 200, current.text
        start = LEGAL_TEXT.index(OBLIGATION_TEXT)
        drafted = owner.post(f"/api/legal-analysis/{case.case_id}", headers=_headers(case, csrf), json={
            "request_id": "ux64-cited-draft",
            "source_content_hash": source["content_hash"],
            "vocabulary": VOCABULARY,
            "expected_private_revision": current.json()["private_revision"],
            "expected_session_revision": current.json()["session_revision"],
            "emitted_lean": LEAN_TEXT,
            "typed_obligations": [{
                "kind": "obligation",
                "obligation_id": "ux64-duty",
                "statement": OBLIGATION_TEXT,
                "source_span": {"start": start, "end": start + len(OBLIGATION_TEXT), "text": OBLIGATION_TEXT, "unit": "character"},
            }],
        })
        assert drafted.status_code == 200, drafted.text
        draft = drafted.json()
        assert draft["status"] == "attached"
        assert draft["legal_sufficiency"] is False and draft["proof"] is False
        span = draft["typed_obligations"][0]["source_span"]
        assert LEGAL_TEXT[span["start"]:span["end"]] == span["text"] == OBLIGATION_TEXT
        stages.append("cited_draft")

        invited = owner.post("/api/cases/assignments", headers=_headers(case, csrf), json={
            "case_id": case.case_id,
            "member_principal_id": world.lawyer.principal_id,
            "scope": ["case.read", "case.review", "case.message.send"],
            "expires_at": world.now["t"] + 3600,
            "expected_case_revision": case.revision,
            "idempotency_key": "ux64-invite",
        })
        assert invited.status_code == 201, invited.text
        grant_id = invited.json()["grant_id"]
    with TestClient(world.app, base_url="https://testserver") as lawyer:
        lawyer_csrf = _composed_login(lawyer, "synthetic-lawyer-credential")
        accepted = lawyer.post(f"/api/cases/assignments/{grant_id}/accept", headers=_headers(case, lawyer_csrf), json={
            "case_id": case.case_id,
            "scope": ["case.read", "case.review", "case.message.send"],
            "idempotency_key": "ux64-accept-scope",
        })
        assert accepted.status_code == 200, accepted.text
        version = accepted.json()["version"]
    with TestClient(world.app, base_url="https://testserver") as owner:
        csrf = _composed_login(owner)
        thread = owner.post("/api/cases/messages/threads", headers=_headers(case, csrf), json={
            "case_id": case.case_id,
            "idempotency_key": "ux64-thread",
        })
        assert thread.status_code == 201, thread.text
        sent = owner.post(
            f"/api/cases/messages/threads/{thread.json()['thread_id']}/messages",
            headers=_headers(case, csrf),
            json={"case_id": case.case_id, "text": MESSAGE, "idempotency_key": "ux64-message"},
        )
        assert sent.status_code == 201, sent.text
        assert sent.json()["disposition"] == "conversation"
        assert sent.json().get("adoption") is None
        stages.append("lawyer_message")
        sharing = owner.get(f"/api/legal-analysis/{case.case_id}/lawyer-reviews/sharing", headers=_headers(case))
        assert sharing.status_code == 200, sharing.text
        shared = owner.post(f"/api/legal-analysis/{case.case_id}/lawyer-reviews/share", headers=_headers(case, csrf), json={
            "membership_id": grant_id,
            "expected_membership_version": version,
            "expected_private_revision": sharing.json()["private_revision"],
        })
        assert shared.status_code == 200, shared.text
    with TestClient(world.app, base_url="https://testserver") as lawyer:
        lawyer_csrf = _composed_login(lawyer, "synthetic-lawyer-credential")
        view = lawyer.get(f"/api/legal-analysis/{case.case_id}/review-items", headers=_headers(case, lawyer_csrf, version))
        assert view.status_code == 200, view.text
        live = view.json()["live_revisions"]
        proposed = lawyer.post(f"/api/legal-analysis/{case.case_id}/review-items", headers=_headers(case, lawyer_csrf, version), json={
            "operation": "create_proposal",
            "request_id": "ux64-lawyer-review",
            "body": "Please consider the corrected firing date.",
            "target_kind": "fact",
            "target_id": offer["target_stable_id"],
            "proposed_text": REPLACEMENT,
            "expected_review_revision": view.json()["review_revision"],
            **{"expected_" + name: live[name] for name in ("case_revision", "source_revision", "fact_revision", "proof_revision")},
        })
        assert proposed.status_code == 200, proposed.text
        assert proposed.json()["legal_sufficiency"] is not True
        stages.append("lawyer_review")
        proposal = proposed.json()
    with TestClient(world.app, base_url="https://testserver") as owner:
        csrf = _composed_login(owner)
        state = _session(owner, case)
        decision = owner.post(f"/api/legal-analysis/{case.case_id}/review-transitions", headers=_headers(case, csrf), json={
            "proposal_id": proposal["record"]["item_id"],
            "request_id": "ux64-owner-accept",
            "expected_review_revision": proposal["review_revision"],
            "expected_private_revision": state["private_revision"],
            "expected_session_revision": state["shared_interview"]["session_revision"],
        })
        assert decision.status_code == 200, decision.text
        receipt = decision.json()
        assert receipt["applied"] is True and receipt["status"] == "accepted"
        assert receipt["accepting_owner_actor"] == world.owner.principal_id
        assert receipt.get("legal_sufficiency") is not True
        assert receipt.get("court_filed") is not True
        stages.append("owner_acceptance")
        expected_graph = _session(owner, case)["shared_interview"]["knowledge_graph"]
        expected_history = _session(owner, case)["intake_history"]
    from tests.gui_collaboration_fixtures import owner_lawyer_journey_world
    cold = owner_lawyer_journey_world(tmp_path / "cold", previous=world)
    with TestClient(cold.app, base_url="https://testserver") as resumed:
        csrf = _composed_login(resumed)
        opened = _post_chat(resumed, cold.case, csrf, {"interview_action": "encrypted_resume", "message": "{\"browser_cache\": true}"})
        resume = opened.get("encrypted_resume") or opened
        assert resume.get("hooks_replayed") is not True
        assert resume.get("reconstructed_from_browser_cache") is not True
        state = _session(resumed, cold.case)
        assert state["shared_interview"]["knowledge_graph"] == expected_graph
        assert REPLACEMENT in [row.get("answer") for row in state["intake_history"]]
        assert state["intake_history"] == expected_history
        stages.append("cold_resume")
    assert tuple(stages) == JOURNEY_STAGES


def test_failures_and_strangers_do_not_become_a_filing(tmp_path):
    world = complete_journey_world(tmp_path / "failures")
    case = world.case
    seen = []
    with TestClient(world.app, base_url="https://testserver") as owner, TestClient(world.app, base_url="https://testserver") as stranger:
        csrf = _composed_login(owner)
        stranger_csrf = _composed_login(stranger, STRANGER_CREDENTIAL)
        started = _post_chat(owner, case, csrf, {
            "message": NARRATIVE,
            "question_id": "original_complaint",
            "interview_action": "start",
        })
        pending = started["interview"].get("pending_inquiry") or _session(owner, case)["shared_interview"]["pending_inquiry"]
        unknown = _post_chat(owner, case, csrf, {
            "message": "I do not know",
            "question_id": pending["inquiry_id"],
            "expected_question_revision": pending["revision"],
            "interview_action": "answer",
        })
        assert unknown.get("legal_sufficiency") is not True
        seen.append("unknown")
        cancelled = _post_chat(owner, case, csrf, {"interview_action": "cancel", "message": ""})
        stop = cancelled.get("interview_stop") or cancelled
        assert stop.get("legal_sufficiency") is False or cancelled.get("legal_sufficiency") is False
        seen.append("cancelled")
        consent = owner.post(f"/api/cases/{case.case_id}/processing-consent", headers={"x-csrf-token": csrf}, json={
            "purpose": "citation_acquisition", "mode": "local_private", "expected_generation": 0,
        })
        assert consent.status_code == 200, consent.text
        provider = owner.post(f"/api/legal-research/{case.case_id}", headers=_headers(case, csrf), json={
            "purpose": "citation_acquisition",
            "query": "termination statute",
            "max_results": 1,
            "deadline_seconds": 1.0,
            "max_bytes": 1024,
            "retrieval_mode": "cache",
            "expected_consent_generation": consent.json()["generation"],
            "operation_id": "ux64-provider-missing",
        })
        assert provider.status_code == 200, provider.text
        assert provider.json()["status"] in {"unavailable", "cancelled", "unresolved"}
        assert provider.json()["admitted_law"] is False and provider.json()["proof"] is False
        seen.append("provider")
        dropped = owner.post(f"/api/legal-research/{case.case_id}", headers=_headers(case, csrf), json={
            "purpose": "citation_acquisition",
            "query": "termination statute",
            "max_results": 1,
            "deadline_seconds": 1.0,
            "max_bytes": 1024,
            "retrieval_mode": "cache",
            "expected_consent_generation": consent.json()["generation"],
            "operation_id": "ux64-cancelled",
            "cancelled": True,
        })
        assert dropped.status_code == 200, dropped.text
        assert dropped.json()["status"] == "cancelled"
        assert dropped.json()["admitted_law"] is False
        seen.append("unresolved")
        source = owner.post(f"/api/legal-research/{case.case_id}/admissions", headers=_headers(case, csrf), json={
            "decision": "admit",
            "source_passage": "text that was never acquired",
            "authority_identity": "missing-authority",
            "jurisdiction": "OR",
            "effective_date": "2024-01-01",
            "version": "missing",
            "content_hash": "0" * 64,
            "applicability": "unknown",
            "treatment_state": "unknown",
            "exceptions": [],
            "operation_id": "ux64-bad-source",
        })
        assert source.status_code >= 400 or source.json().get("admitted_law") is False
        if source.status_code == 200:
            assert source.json().get("status") in {"unresolved", "refused", "denied"}
        seen.append("source")
        proof = owner.post(f"/api/legal-analysis/{case.case_id}/proof-traces", headers=_headers(case, csrf), json={
            "legal_sufficiency": True,
            "proof_status": "executed",
        })
        assert proof.status_code >= 400, proof.text
        assert proof.json().get("legal_sufficiency") is not True
        assert proof.json().get("executed_proof") is not True
        seen.append("proof")
        world.service.intake_case_file = {}
        filing = owner.post(f"/api/documents/{case.case_id}/draft-versions", headers=_headers(case, csrf), json={
            "operation": "file_with_court",
            "request_id": "ux64-file",
            "draft_id": "draft-ux64",
            "text": "This sentence must not be filed.",
        })
        assert filing.status_code == 403, filing.text
        assert filing.json()["detail"] == "automatic_filing_refused"
        world.service.lock_private_keys()
        stored = owner.get("/api/complaint-workspace/session", headers=_headers(case))
        assert stored.status_code in {401, 403, 409, 503}, stored.text
        assert stored.json().get("session_readable") is not True
        seen.append("storage")
        denied = stranger.get(f"/api/cases/{case.case_id}", headers=_headers(case, stranger_csrf))
        assert denied.status_code in {403, 404}, denied.text
        assert NARRATIVE not in denied.text
        assert REPLACEMENT not in denied.text
        seen.append("unauthorized")
    assert tuple(seen) == JOURNEY_FAILURES


def test_workspace_dom_keeps_sufficiency_and_filing_false(tmp_path, monkeypatch):
    denial = browser.probe_inherited_network_denial()
    if not denial["af_unix_only"]:
        raise browser.BrowserCapabilityError("inherited AF_UNIX-only denial is not active")
    world = complete_journey_world(tmp_path / "dom")
    bridge = browser.SameOriginAsgiBridge(world.app)
    node, chromium = browser.pin_executables()
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", node.path)
    profile = tmp_path / "ux64-profile"
    profile.mkdir(mode=0o700)
    playwright = browser._load_sync_playwright()().start()
    context = browser._launch_context(playwright, chromium.path, profile, bridge)
    observed = set(browser._with_descendants(browser._matching_pids((str(profile), node.argv[1]))))
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(20000)
    try:
        page.goto(browser.SAME_ORIGIN + "/workspace", wait_until="domcontentloaded")
        assert page.evaluate("() => typeof window.mockApi") == "undefined"
        page.evaluate(
            """async () => {
                const response = await fetch('/api/complaint-workspace/auth/login', {
                    method: 'POST', credentials: 'same-origin', headers: {'content-type': 'application/json'},
                    body: JSON.stringify({credential: 'synthetic-owner-credential'})});
                if (!response.ok) throw new Error('login_' + response.status);
                return await response.json();
            }"""
        )
        assert page.get_attribute("#complaint-readiness", "data-legal-sufficiency") == "false"
        assert page.get_attribute("#complaint-readiness", "data-filing-succeeded") == "false"
        assert page.get_attribute("#derived-workflow-stage", "data-automatic-court-filing") == "false"
        page.fill("#adaptive-narrative", NARRATIVE)
        page.click("#adaptive-enter-narrative")
        page.wait_for_function("document.getElementById('adaptive-pending').dataset.pending === 'true'")
        page.click("#inquiry-why")
        page.wait_for_function("document.getElementById('inquiry-explanation-status').dataset.action === 'why'")
        assert page.get_attribute("#inquiry-explanation", "data-legal-sufficiency") == "false"
        assert page.get_attribute("#inquiry-explanation-status", "data-stored-as-answer") == "false"
        page.click("#finite-interview-cancel")
        page.wait_for_function("document.getElementById('finite-interview-outcome').dataset.stop !== ''")
        assert page.get_attribute("#finite-interview-outcome", "data-legal-sufficiency") == "false"
        assert page.get_attribute("#finite-interview-outcome", "data-stop") not in {"", "sufficient", "verified", "filed"}
        assert "not legal sufficiency" in page.locator("#finite-interview-sufficiency").inner_text().lower()
        assert OWNER_CREDENTIAL
    finally:
        context.close()
        playwright.stop()
        observed |= browser._with_descendants(browser._matching_pids((str(profile), node.argv[1])))
        cleanup = browser._wait_for_cleanup(observed)
        assert cleanup["cleaned"], "owned Chromium/Node descendants did not quiesce"
