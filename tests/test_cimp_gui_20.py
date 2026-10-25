"""A new process resumes the interview from the encrypted snapshot.

The pending inquiry, case, consent, factual and legal graph revisions,
deferred gaps, and corrections come from that snapshot. Hook receipts and
saved messages are not dispatched again. A browser cache is not a case
record. Denied, revoked, and missing-key resumes stay explicit.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.complaint_workspace import ComplaintWorkspaceService
from applications.complaint_workspace_api import create_complaint_workspace_router

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

USER_ID = "synthetic-gui-20"
PASSPHRASE = "synthetic-gui-20-passphrase"
OTHER_PASSPHRASE = "synthetic-gui-20-other-passphrase"
QUESTION = "Who scheduled the warehouse shift?"
CACHE_QUESTION = "Browser cache question that must not be restored."
FACT_REVISION = "fact-rev-4"
LAW_REVISION = "law-rev-9"
GAP_ID = "inq-deferred-gap"
CORRECTION_ID = "cor-gui-20"
HOOK_REQUEST = "a" * 32


def _service(tmp_path: Path) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(root_dir=tmp_path / "sessions")
    service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    service.ensure_private_case_key(USER_ID, USER_ID)
    return service


def _seed(service: ComplaintWorkspaceService) -> None:
    state = service._load_state(USER_ID)
    state["case_id"] = USER_ID
    state["operation_consent"] = {
        "contract": "operation-consent-v1",
        "case_id": USER_ID,
        "generation": 3,
        "revoked": False,
        "purpose": "extract_facts",
    }
    state["intake_history"] = [{"question_id": "inq-prior", "answer": "I reported the hazard.", "effect_id": "effect-prior"}]
    state["intake_router"] = {"receipts": [{"operation": "extract_facts", "request_id": HOOK_REQUEST, "status": "available", "provider_replayed": False}]}
    state["deferred_gaps"] = [{
        "inquiry_id": GAP_ID,
        "disposition": "deferred",
        "preserved": True,
        "creates_fact": False,
        "target_id": "gap-target",
    }]
    state["factual_corrections"] = [{
        "correction_id": CORRECTION_ID,
        "previous": "January 1",
        "replacement": "January 2",
        "actor_principal_id": USER_ID,
        "prior_retained": True,
    }]
    state["shared_interview"] = {
        "schema_version": "shared-interview-session-v1",
        "session_id": "interview-gui-20",
        "session_revision": 5,
        "pending_inquiry": {
            "inquiry_id": "inq-pending-20",
            "revision": 6,
            "question": QUESTION,
            "objective_id": "witnesses",
            "target_id": "witness-gap",
            "target_revision": "2",
        },
        "knowledge_graph": {"graph_id": "fact-graph-20", "graph_revision": FACT_REVISION, "entities": [{"id": "fact-1", "name": "shift"}]},
        "dependency_graph": {"graph_id": "law-graph-20", "graph_revision": LAW_REVISION, "nodes": [{"id": "req-1", "label": "causation"}]},
        "legal_sufficiency": False,
    }
    service._save_state(state)


def _assert_exact(body: dict) -> None:
    resume = body["encrypted_resume"]
    assert resume["restored"] is True
    assert resume["status"] == "resumed"
    assert resume["hooks_replayed"] is False
    assert resume["messages_replayed"] is False
    assert resume["browser_cache_used"] is False
    assert resume["source"] == "encrypted_interview_snapshot"
    session = body["session"]
    pending = session["shared_interview"]["pending_inquiry"]
    assert pending["inquiry_id"] == "inq-pending-20"
    assert pending["revision"] == 6
    assert pending["question"] == QUESTION
    assert pending["target_id"] == "witness-gap"
    assert session["case_id"] == USER_ID
    assert session["operation_consent"]["generation"] == 3
    assert session["operation_consent"]["revoked"] is False
    assert session["operation_consent"]["purpose"] == "extract_facts"
    assert session["factual_graph_binding"]["revision"] == FACT_REVISION
    assert session["legal_graph_binding"]["revision"] == LAW_REVISION
    assert session["shared_interview"]["knowledge_graph"]["graph_revision"] == FACT_REVISION
    assert session["shared_interview"]["dependency_graph"]["graph_revision"] == LAW_REVISION
    assert session["deferred_gaps"][0]["inquiry_id"] == GAP_ID
    assert session["deferred_gaps"][0]["disposition"] == "deferred"
    assert session["factual_corrections"][0]["correction_id"] == CORRECTION_ID
    assert session["factual_corrections"][0]["replacement"] == "January 2"
    assert session["factual_corrections"][0]["prior_retained"] is True
    assert [item["effect_id"] for item in session["intake_history"]] == ["effect-prior"]
    assert session["intake_router"]["receipts"][0]["request_id"] == HOOK_REQUEST
    assert session["intake_router"]["hooks_replayed"] is False
    assert body["hooks_replayed"] is False
    assert body["messages_replayed"] is False
    assert body["browser_cache_used"] is False
    assert body["legal_sufficiency"] is False
    assert body["stored_as_answer"] is False
    encoded = json.dumps(body)
    assert CACHE_QUESTION not in encoded


def test_new_process_resumes_exact_encrypted_interview_without_replay(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "integrations.ipfs_datasets.llm.generate_text",
        lambda **_kwargs: calls.append("generate") or (_ for _ in ()).throw(AssertionError("provider replay")),
    )
    service = _service(tmp_path)
    _seed(service)
    sealed = service.seal_encrypted_browser_interview(USER_ID)
    assert sealed["hooks_replayed"] is False
    assert sealed["messages_replayed"] is False
    state = service._load_state(USER_ID)
    state["shared_interview"]["pending_inquiry"]["question"] = "session cache question"
    state["operation_consent"]["generation"] = 99
    state["factual_graph_binding"] = {"revision": "fact-rev-stale", "status": "bound"}
    state["legal_graph_binding"] = {"revision": "law-rev-stale", "status": "bound"}
    state["deferred_gaps"] = [{"inquiry_id": "inq-session-cache", "disposition": "deferred"}]
    state["factual_corrections"] = [{"correction_id": "cor-session-cache", "replacement": "session"}]
    state["intake_history"] = [{"question_id": "extra", "answer": "replay me", "effect_id": "effect-replay"}]
    state["intake_router"] = {"receipts": [{"operation": "extract_facts", "request_id": "b" * 32, "status": "available"}]}
    service._save_state(state)
    fresh = ComplaintWorkspaceService(root_dir=service._session_dir)
    fresh.unlock_private_keys(passphrase=PASSPHRASE)
    resumed = fresh.resume_encrypted_browser_interview(USER_ID, browser_cache={"question": CACHE_QUESTION, "case_text": CACHE_QUESTION})
    _assert_exact(resumed)
    assert calls == []
    assert fresh._interview_mediators == {}
    again = fresh.run_intake_chat_turn(USER_ID, message=json.dumps({"question": CACHE_QUESTION}), interview_action="encrypted_resume")
    _assert_exact(again)
    assert calls == []


def test_http_resume_uses_encrypted_snapshot_not_request_body(tmp_path):
    service = _service(tmp_path)
    _seed(service)
    service.seal_encrypted_browser_interview(USER_ID)
    app = FastAPI()
    app.include_router(create_complaint_workspace_router(service, trusted_local=True))
    client = TestClient(app)
    response = client.post(
        "/api/complaint-workspace/intake-chat",
        json={"user_id": USER_ID, "message": CACHE_QUESTION, "interview_action": "encrypted_resume"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    _assert_exact(body)
    assert body["adaptive_inquiry"]["prompt"] == QUESTION
    assert body["adaptive_inquiry"]["inquiry_id"] == "inq-pending-20"


def test_denied_revoked_and_missing_key_resume_are_explicit(tmp_path):
    service = _service(tmp_path)
    _seed(service)
    service.seal_encrypted_browser_interview(USER_ID)
    service._authorizer = lambda _requirement, _context: False
    denied = service.resume_encrypted_browser_interview(USER_ID, browser_cache=CACHE_QUESTION)
    assert denied["status"] == "denied"
    assert denied["encrypted_resume"]["code"] == "authorization_denied"
    assert denied["encrypted_resume"]["restored"] is False
    assert denied["encrypted_resume"]["explicit"] is True
    assert denied["browser_cache_used"] is False
    assert CACHE_QUESTION not in json.dumps(denied)
    assert "shared_interview" not in denied["session"]

    locked = _service(tmp_path / "locked")
    _seed(locked)
    locked.seal_encrypted_browser_interview(USER_ID)
    locked.lock_private_keys()
    locked_result = locked.resume_encrypted_browser_interview(USER_ID, browser_cache=CACHE_QUESTION)
    assert locked_result["status"] == "denied"
    assert locked_result["encrypted_resume"]["code"] == "unlock_needed"
    assert locked_result["encrypted_resume"]["restored"] is False
    assert CACHE_QUESTION not in json.dumps(locked_result)

    missing = ComplaintWorkspaceService(root_dir=tmp_path / "no-keys")
    missing_result = missing.resume_encrypted_browser_interview(USER_ID, browser_cache=CACHE_QUESTION)
    assert missing_result["status"] == "missing_key"
    assert missing_result["encrypted_resume"]["code"] == "missing_key"
    assert missing_result["encrypted_resume"]["restored"] is False
    assert CACHE_QUESTION not in json.dumps(missing_result)

    source = _service(tmp_path / "source")
    _seed(source)
    source.seal_encrypted_browser_interview(USER_ID)
    other = ComplaintWorkspaceService(root_dir=tmp_path / "revoked")
    other.initialize_private_keys(protection="passphrase", passphrase=OTHER_PASSPHRASE)
    other.ensure_private_case_key(USER_ID, USER_ID)
    src_dir = source.interview_snapshot_directory(USER_ID)
    dest_dir = other.interview_snapshot_directory(USER_ID)
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_dir, dest_dir)
    revoked = other.resume_encrypted_browser_interview(USER_ID, browser_cache=CACHE_QUESTION)
    assert revoked["status"] == "revoked"
    assert revoked["encrypted_resume"]["code"] == "key_revoked"
    assert revoked["encrypted_resume"]["restored"] is False
    assert revoked["hooks_replayed"] is False
    assert QUESTION not in json.dumps(revoked)
    assert CACHE_QUESTION not in json.dumps(revoked)
    opened = other._load_state(USER_ID)
    assert QUESTION not in json.dumps(opened.get("shared_interview") or {})


def test_browser_resume_ignores_page_cache(tmp_path, monkeypatch):
    from tests.test_cimp_gui_15 import USER_ID as BROWSER_USER
    from tests.test_cimp_gui_15 import _page

    with _page(tmp_path, monkeypatch) as (world, page):
        service = world.service
        state = service._load_state(BROWSER_USER)
        state["case_id"] = BROWSER_USER
        state["operation_consent"] = {"contract": "operation-consent-v1", "case_id": BROWSER_USER, "generation": 4, "revoked": False, "purpose": "extract_facts"}
        state["deferred_gaps"] = [{"inquiry_id": GAP_ID, "disposition": "deferred", "preserved": True, "creates_fact": False, "target_id": "gap-target"}]
        state["factual_corrections"] = [{"correction_id": CORRECTION_ID, "previous": "January 1", "replacement": "January 2", "prior_retained": True}]
        state["intake_history"] = [{"question_id": "inq-prior", "answer": "I reported the hazard.", "effect_id": "effect-prior"}]
        state["shared_interview"] = {
            "schema_version": "shared-interview-session-v1",
            "session_id": "interview-gui-20-browser",
            "session_revision": 5,
            "pending_inquiry": {
                "inquiry_id": "inq-pending-20",
                "revision": 6,
                "question": QUESTION,
                "objective_id": "witnesses",
                "target_id": "witness-gap",
                "target_revision": "2",
            },
            "knowledge_graph": {"graph_id": "fact-graph-20", "graph_revision": FACT_REVISION, "entities": [{"id": "fact-1"}]},
            "dependency_graph": {"graph_id": "law-graph-20", "graph_revision": LAW_REVISION, "nodes": [{"id": "req-1"}]},
            "legal_sufficiency": False,
        }
        service._save_state(state)
        service.seal_encrypted_browser_interview(BROWSER_USER)
        drifted = service._load_state(BROWSER_USER)
        drifted["shared_interview"]["pending_inquiry"]["question"] = "session cache question"
        drifted["operation_consent"]["generation"] = 1
        service._save_state(drifted)
        page.evaluate(
            """marker => {
                localStorage.setItem('complaint-workspace-case', marker);
                sessionStorage.setItem('complaint-workspace-inquiry', marker);
            }""",
            CACHE_QUESTION,
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_function("['ready', 'partial', 'denied', 'error'].includes(document.body.dataset.workspaceHydrated)")
        assert page.locator("#encrypted-interview-resume").get_attribute("data-task") == "CIMP-GUI-20"
        assert CACHE_QUESTION not in page.text_content("#adaptive-pending-prompt")
        page.click("#encrypted-interview-resume-button")
        page.wait_for_function("document.getElementById('encrypted-interview-resume').dataset.restored === 'true'")
        assert page.get_attribute("#encrypted-interview-resume", "data-browser-cache-used") == "false"
        assert page.get_attribute("#encrypted-interview-resume", "data-hooks-replayed") == "false"
        assert page.get_attribute("#encrypted-interview-resume", "data-messages-replayed") == "false"
        assert page.text_content("#encrypted-interview-resume-inquiry") == QUESTION
        assert "factual fact-rev-4 legal law-rev-9" in page.text_content("#encrypted-interview-resume-graphs")
        assert GAP_ID in page.text_content("#encrypted-interview-resume-gaps")
        assert CORRECTION_ID in page.text_content("#encrypted-interview-resume-corrections")
        assert "consent generation 4" in page.text_content("#encrypted-interview-resume-consent")
        assert page.text_content("#adaptive-pending-prompt") == QUESTION
        stored = page.evaluate("JSON.stringify({...localStorage, ...sessionStorage})")
        assert CACHE_QUESTION in stored
        assert page.text_content("#encrypted-interview-resume-inquiry") != CACHE_QUESTION
