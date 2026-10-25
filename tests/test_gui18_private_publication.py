"""Actual issued-cookie correction and encrypted publication boundaries."""
from pathlib import Path
from threading import Event, Thread
import json
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.complaint_workspace import ComplaintWorkspaceService
from tests.test_cimp_gui_14 import PASSPHRASE, _composed_case_world, _composed_headers, _composed_login

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
ANSWER = "Alex Rivera fired me on March 4, 2024 after I reported a safety concern."
CORRECTION = "Alex Rivera fired me on March 5, 2024 after I reported a safety concern."


def _prepare(client, world):
    csrf = _composed_login(client)
    headers = _composed_headers(world.case, csrf)
    started = client.post("/api/complaint-workspace/intake-chat", headers=headers, json={
        "message": "On March 4, 2024 supervisor Alex Rivera fired me after I reported safety concerns.",
        "question_id": "original_complaint", "interview_action": "start"})
    assert started.status_code == 200, started.text
    inquiry = started.json()["interview"]["inquiry"]
    answered = client.post("/api/complaint-workspace/intake-chat", headers=headers, json={
        "message": ANSWER, "question_id": inquiry["inquiry_id"],
        "expected_question_revision": inquiry["revision"], "interview_action": "answer"})
    assert answered.status_code == 200, answered.text
    offer = answered.json()["adaptive_inquiry"]["factual_correction"]
    assert offer["target_stable_id"], "The actual owner's accepted answer needs a correction target."
    assert offer["actor_principal_id"] == world.owner.principal_id
    assert offer["canonical_owner_principal_id"] == world.case.tenant_id
    assert world.owner.principal_id != world.case.tenant_id
    return csrf, offer


def _correct(client, world, csrf, offer):
    return client.post("/api/complaint-workspace/intake-chat", headers=_composed_headers(world.case, csrf), json={
        "message": json.dumps({"schema": "gui-factual-correction-v1", "replacement": CORRECTION,
            "expected_graph_revision": offer["expected_graph_revision"],
            "expected_session_revision": offer["expected_session_revision"],
            "target_stable_id": offer["target_stable_id"]}), "interview_action": "correct"})


def test_actual_owner_correction_survives_fresh_encrypted_workspace(tmp_path):
    world = _composed_case_world(tmp_path)
    service = world.services[world.case.case_id]
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf, offer = _prepare(client, world)
        response = _correct(client, world, csrf, offer)
        assert response.status_code == 200, response.text
        receipt = response.json()["factual_correction"]
        assert receipt["status"] == "applied", receipt
        assert receipt["actor_principal_id"] == world.owner.principal_id
        assert receipt["canonical_owner_principal_id"] == world.case.tenant_id
        assert receipt["actor_matches_canonical_owner"] is False
    cold = ComplaintWorkspaceService(root_dir=service._session_dir)
    cold.unlock_private_keys(passphrase=PASSPHRASE)
    registry = CaseHandlerRegistry()
    registry.bind(world.case, mediator=cold, workspace_service=cold)
    app = FastAPI()
    compose_case_routes(app, authorizer=world.authorizer, browser_sessions=world.sessions,
        case_handlers=registry, include_review=False, include_document=False)
    with TestClient(app, base_url="https://testserver") as client:
        _composed_login(client)
        response = client.get("/api/complaint-workspace/session", headers=_composed_headers(world.case))
        assert response.status_code == 200, response.text
        history = response.json()["session"]["intake_history"]
        answers = [row.get("answer") for row in history]
        assert ANSWER in answers and CORRECTION in answers


@pytest.mark.parametrize("stage", ["crypto", "head_temp_fsync"])
@pytest.mark.parametrize("boundary", ["logout", "key_lock"])
def test_revoked_actual_correction_never_publishes_or_recovers(tmp_path, monkeypatch, stage, boundary):
    from integrations import private_storage
    world = _composed_case_world(tmp_path)
    service = world.services[world.case.case_id]
    entered, release = Event(), Event()
    original_seal, original_fsync = private_storage._seal_role, private_storage._fsync_file
    with TestClient(world.app, base_url="https://testserver") as client, TestClient(world.app, base_url="https://testserver") as other:
        csrf, offer = _prepare(client, world)
        other.cookies.update(client.cookies)
        repository = service.joined_revision_repository(world.case.tenant_id, world.case.case_id)
        before = (repository / "head.cgpe").read_bytes()

        def pause():
            entered.set()
            assert release.wait(20), "Actual encrypted correction boundary did not release."

        def seal_then_wait(payload, **values):
            result = original_seal(payload, **values)
            if stage == "crypto" and values.get("kind") == "revision-manifest":
                pause()
            return result

        def fsync_then_wait(descriptor, operation):
            original_fsync(descriptor, operation)
            path = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
            if stage == "head_temp_fsync" and path.parent == repository and path.read_bytes().startswith(private_storage._HEAD_RECORD_MAGIC):
                pause()

        monkeypatch.setattr(private_storage, "_seal_role", seal_then_wait)
        monkeypatch.setattr(private_storage, "_fsync_file", fsync_then_wait)
        responses, errors = [], []
        def update():
            try:
                responses.append(_correct(client, world, csrf, offer))
            except BaseException as exc:
                errors.append(exc)
        worker = Thread(target=update, daemon=True)
        worker.start()
        try:
            assert entered.wait(20), "The actual correction did not reach encrypted publication."
            assert (repository / "head.cgpe").read_bytes() == before
            if boundary == "logout":
                assert other.post("/api/complaint-workspace/auth/logout", headers={"x-csrf-token": csrf}).status_code == 200
            else:
                service.lock_private_keys()
            assert worker.is_alive(), "The boundary must occur while the real writer is still paused."
        finally:
            release.set()
            worker.join(20)
        assert not worker.is_alive()
        assert (repository / "head.cgpe").read_bytes() == before, "Revoked correction advanced the authoritative encrypted head."
        if errors:
            raise errors[0]
        assert len(responses) == 1
        if boundary == "key_lock":
            service.unlock_private_keys(passphrase=PASSPHRASE)
        service.recover_joined_intake_revision(world.case.tenant_id, case_id=world.case.case_id)
        service.recover_joined_intake_revision(world.case.tenant_id, case_id=world.case.case_id)
        assert (repository / "head.cgpe").read_bytes() == before
