"""Review items stay typed until an authorized acceptance changes case state.

Tasks, comments, and proposals do not rewrite facts, answers, legal admissions,
or draft revisions. Acceptance compares the review revision and the target
revision, keeps dissent and prior text, and invalidates support bound to the
replaced revision.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import (
    BrowserSessionConfiguration,
    BrowserSessionService,
    PrincipalStoreCredentialAdapter,
)
from applications.case_access import ASSIGNED_LAWYER_ACTIONS, CaseActionAuthorizer
from applications.case_directory import CaseDirectory
from applications.case_review import REVIEW_ITEMS_ROUTE, REVIEW_TRANSITIONS_ROUTE
from applications.case_routes import PROTECTED_PREFIXES, CaseHandlerRegistry, compose_case_routes
from applications.principal_store import PrincipalStore
from mediator.workflow_service import WorkflowActionService

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


def _world(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    other = principals.install_server_role(role="lawyer")
    reader = principals.install_server_role(role="lawyer")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    case = cases.create_case(actor_principal_id=owner.principal_id)
    authorizer = CaseActionAuthorizer(principals, cases)
    grant = authorizer.grant_assigned_lawyer(
        owner_principal_id=owner.principal_id,
        lawyer_principal_id=lawyer.principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions=frozenset({"case.read", "case.review"}),
        expected_case_revision=case.revision,
    )
    other_grant = authorizer.grant_assigned_lawyer(
        owner_principal_id=owner.principal_id,
        lawyer_principal_id=other.principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions=frozenset({"case.read", "case.review"}),
        expected_case_revision=case.revision,
    )
    read_grant = authorizer.grant_assigned_lawyer(
        owner_principal_id=owner.principal_id,
        lawyer_principal_id=reader.principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions=frozenset({"case.read"}),
        expected_case_revision=case.revision,
    )
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            "synthetic-lawyer-credential": lawyer.principal_id,
            "synthetic-other-credential": other.principal_id,
            "synthetic-reader-credential": reader.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=300,
    ))
    mediator = SimpleNamespace(intake_case_file={})
    handlers = CaseHandlerRegistry()
    handlers.bind(case, mediator=mediator, workspace_service=SimpleNamespace(case_id=case.case_id),
        authorize_delegated=lambda decision: decision.membership == "assigned-lawyer")
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers,
        include_workspace=False, include_review=False, include_document=False)
    return SimpleNamespace(case=case, grant=grant, other_grant=other_grant, read_grant=read_grant,
        app=app, mediator=mediator, lawyer=lawyer, other=other)


def _headers(case, csrf, membership_revision):
    return {
        "x-tenant-id": case.tenant_id,
        "x-case-id": case.case_id,
        "x-resource-id": case.resource_id,
        "x-expected-revision": str(case.revision),
        "x-expected-membership-revision": str(membership_revision),
        "x-csrf-token": csrf,
    }


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _paths(case_id):
    return (
        f"/api/legal-analysis/{case_id}/review-items",
        f"/api/legal-analysis/{case_id}/review-transitions",
    )


def test_review_routes_require_case_review_on_the_legal_analysis_prefix():
    assert any(REVIEW_ITEMS_ROUTE.startswith(prefix + "/") for prefix in PROTECTED_PREFIXES)
    assert any(REVIEW_TRANSITIONS_ROUTE.startswith(prefix + "/") for prefix in PROTECTED_PREFIXES)
    assert "case.review" in ASSIGNED_LAWYER_ACTIONS
    assert "case.update" not in ASSIGNED_LAWYER_ACTIONS


def test_only_authorized_acceptance_updates_case_state_and_invalidates_support(tmp_path):
    world = _world(tmp_path)
    items_path, transitions_path = _paths(world.case.case_id)
    with TestClient(world.app, base_url="https://testserver") as client, TestClient(world.app, base_url="https://testserver") as reader:
        assert client.get(items_path).status_code == 401
        csrf = _login(client, "synthetic-lawyer-credential")
        headers = _headers(world.case, csrf, world.grant.revision)
        reader_csrf = _login(reader, "synthetic-reader-credential")
        reader_headers = _headers(world.case, reader_csrf, world.read_grant.revision)
        task = client.post(items_path, headers=headers, json={
            "operation": "create_task",
            "request_id": "task-1",
            "title": "Check the date",
            "body": "This task must not become a fact.",
            "target_kind": "fact",
            "target_id": "fact-date",
            "proposed_text": "The date was March.",
        })
        assert task.status_code == 200, task.text
        assert task.json()["record"]["item_type"] == "review_task"
        assert task.json()["facts"] == {}
        comment = client.post(items_path, headers=headers, json={
            "operation": "create_comment",
            "request_id": "comment-1",
            "body": "I disagree with the wording.",
            "target_kind": "answer",
            "target_id": "answer-date",
            "proposed_text": "March 3.",
            "replacement": "March 3.",
        })
        assert comment.status_code == 200, comment.text
        assert comment.json()["record"]["item_type"] == "review_comment"
        assert comment.json()["record"]["updates_case_state"] is False
        assert comment.json()["answers"] == {}
        proposal = client.post(items_path, headers=headers, json={
            "operation": "create_proposal",
            "request_id": "proposal-1",
            "body": "Adopt the March date.",
            "target_kind": "fact",
            "target_id": "fact-date",
            "proposed_text": "The filing date was 3 March.",
        })
        assert proposal.status_code == 200, proposal.text
        proposal_id = proposal.json()["record"]["item_id"]
        assert proposal.json()["facts"] == {}
        dissent = client.post(items_path, headers=headers, json={
            "operation": "dissent",
            "request_id": "dissent-1",
            "proposal_id": proposal_id,
            "body": "The date is still unverified.",
        })
        assert dissent.status_code == 200, dissent.text
        dissent_id = dissent.json()["record"]["item_id"]
        denied = reader.post(transitions_path, headers=reader_headers, json={
            "operation": "accept",
            "request_id": "reader-accept",
            "proposal_id": proposal_id,
            "target_kind": "fact",
            "target_id": "fact-date",
            "replacement": "The filing date was 3 March.",
            "expected_review_revision": 0,
            "expected_target_revision": 0,
        })
        assert denied.status_code == 403
        assert reader.get(items_path, headers=reader_headers).json()["facts"] == {}
        task_accept = client.post(transitions_path, headers=headers, json={
            "operation": "accept",
            "request_id": "accept-task",
            "proposal_id": task.json()["record"]["item_id"],
            "target_kind": "fact",
            "target_id": "fact-date",
            "replacement": "This task must not become a fact.",
            "expected_review_revision": 0,
            "expected_target_revision": 0,
        })
        assert task_accept.status_code == 403
        assert task_accept.json()["error"] == "not_an_accepted_transition"
        accepted = client.post(transitions_path, headers=headers, json={
            "operation": "accept",
            "request_id": "accept-1",
            "proposal_id": proposal_id,
            "target_kind": "fact",
            "target_id": "fact-date",
            "replacement": "The filing date was 3 March.",
            "expected_review_revision": 0,
            "expected_target_revision": 0,
        })
        assert accepted.status_code == 200, accepted.text
        body = accepted.json()
        assert body["record"]["updates_case_state"] is True
        assert body["record"]["preserved_dissent_ids"] == [dissent_id]
        assert body["facts"]["fact-date"]["text"] == "The filing date was 3 March."
        assert body["facts"]["fact-date"]["revision"] == 1
        assert body["answers"] == {}
        assert body["legal_admissions"] == {}
        assert body["draft_revisions"] == {}
        assert any(item["item_id"] == dissent_id for item in body["dissent"])
        bound = client.post(items_path, headers=headers, json={
            "operation": "bind_support",
            "request_id": "support-1",
            "support_id": "support-date",
            "depends_on_kind": "fact",
            "depends_on_id": "fact-date",
            "depends_on_revision": 1,
        })
        assert bound.status_code == 200, bound.text
        assert bound.json()["facts"]["fact-date"]["revision"] == 1
        assert bound.json()["downstream_support"][0]["status"] == "current"
        other_proposal = client.post(items_path, headers=headers, json={
            "operation": "create_proposal",
            "request_id": "proposal-answer",
            "body": "Record the answer separately.",
            "target_kind": "answer",
            "target_id": "answer-date",
            "proposed_text": "3 March 2024.",
        })
        assert other_proposal.status_code == 200, other_proposal.text
        other_id = other_proposal.json()["record"]["item_id"]
        review_revision = other_proposal.json()["review_revision"]
        other_accepted = client.post(transitions_path, headers=headers, json={
            "operation": "accept",
            "request_id": "accept-answer",
            "proposal_id": other_id,
            "target_kind": "answer",
            "target_id": "answer-date",
            "replacement": "3 March 2024.",
            "expected_review_revision": review_revision,
            "expected_target_revision": 0,
        })
        assert other_accepted.status_code == 200, other_accepted.text
        assert other_accepted.json()["answers"]["answer-date"]["text"] == "3 March 2024."
        assert other_accepted.json()["downstream_support"][0]["status"] == "current"
        replacement = client.post(items_path, headers=headers, json={
            "operation": "create_proposal",
            "request_id": "proposal-2",
            "body": "Correct the fact.",
            "target_kind": "fact",
            "target_id": "fact-date",
            "proposed_text": "The filing date was 4 March.",
        })
        assert replacement.status_code == 200, replacement.text
        second_id = replacement.json()["record"]["item_id"]
        live_revision = replacement.json()["review_revision"]
        stale = client.post(transitions_path, headers=headers, json={
            "operation": "accept",
            "request_id": "accept-stale",
            "proposal_id": second_id,
            "target_kind": "fact",
            "target_id": "fact-date",
            "replacement": "The filing date was 4 March.",
            "expected_review_revision": live_revision,
            "expected_target_revision": 0,
        })
        assert stale.status_code == 409
        assert stale.json()["error"] == "stale_target_revision"
        updated = client.post(transitions_path, headers=headers, json={
            "operation": "accept",
            "request_id": "accept-2",
            "proposal_id": second_id,
            "target_kind": "fact",
            "target_id": "fact-date",
            "replacement": "The filing date was 4 March.",
            "expected_review_revision": live_revision,
            "expected_target_revision": 1,
        })
        assert updated.status_code == 200, updated.text
        fact = updated.json()["facts"]["fact-date"]
        assert fact["text"] == "The filing date was 4 March."
        assert fact["revision"] == 2
        assert fact["history"][0]["text"] == "The filing date was 3 March."
        assert fact["history"][0]["revision"] == 1
        support = updated.json()["downstream_support"][0]
        assert support["status"] == "invalidated"
        assert support["stale"] is True
        assert support["support_id"] == "support-date"
        assert any(item["item_id"] == dissent_id for item in updated.json()["dissent"])
        assert updated.json()["answers"]["answer-date"]["text"] == "3 March 2024."
        replay = client.post(transitions_path, headers=headers, json={
            "operation": "accept",
            "request_id": "accept-2",
            "proposal_id": second_id,
            "target_kind": "fact",
            "target_id": "fact-date",
            "replacement": "The filing date was 4 March.",
            "expected_review_revision": live_revision,
            "expected_target_revision": 1,
        })
        assert replay.status_code == 200, replay.text
        assert replay.json()["replayed"] is True
        assert replay.json()["facts"]["fact-date"]["revision"] == 2
        assert updated.json()["governing_legal_authority"] is False
        assert updated.json()["legal_sufficiency"] is False
        assert updated.json()["limitations"]


def test_concurrent_acceptance_keeps_one_revision_and_dissent(tmp_path):
    world = _world(tmp_path)
    items_path, transitions_path = _paths(world.case.case_id)
    with TestClient(world.app, base_url="https://testserver") as client, TestClient(world.app, base_url="https://testserver") as other:
        csrf = _login(client, "synthetic-lawyer-credential")
        headers = _headers(world.case, csrf, world.grant.revision)
        other_csrf = _login(other, "synthetic-other-credential")
        other_headers = _headers(world.case, other_csrf, world.other_grant.revision)
        first = client.post(items_path, headers=headers, json={
            "operation": "create_proposal",
            "request_id": "race-proposal-a",
            "body": "First wording.",
            "target_kind": "legal_admission",
            "target_id": "admission-1",
            "proposed_text": "The notice was sent.",
        })
        second = other.post(items_path, headers=other_headers, json={
            "operation": "create_proposal",
            "request_id": "race-proposal-b",
            "body": "Second wording.",
            "target_kind": "legal_admission",
            "target_id": "admission-1",
            "proposed_text": "The notice was not sent.",
        })
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        dissent = other.post(items_path, headers=other_headers, json={
            "operation": "dissent",
            "request_id": "race-dissent",
            "proposal_id": first.json()["record"]["item_id"],
            "body": "Do not admit notice yet.",
        })
        assert dissent.status_code == 200, dissent.text
        payload = {
            "operation": "accept",
            "target_kind": "legal_admission",
            "target_id": "admission-1",
            "expected_review_revision": 0,
            "expected_target_revision": 0,
        }
        winner = client.post(transitions_path, headers=headers, json={
            **payload,
            "request_id": "race-accept-a",
            "proposal_id": first.json()["record"]["item_id"],
            "replacement": "The notice was sent.",
        })
        loser = other.post(transitions_path, headers=other_headers, json={
            **payload,
            "request_id": "race-accept-b",
            "proposal_id": second.json()["record"]["item_id"],
            "replacement": "The notice was not sent.",
        })
        assert winner.status_code == 200, winner.text
        assert loser.status_code == 409
        assert loser.json()["error"] == "stale_review_revision"
        visible = client.get(items_path, headers=headers)
        assert visible.status_code == 200
        admission = visible.json()["legal_admissions"]["admission-1"]
        assert admission["text"] == "The notice was sent."
        assert admission["revision"] == 1
        assert visible.json()["facts"] == {}
        assert visible.json()["draft_revisions"] == {}
        assert any(item["item_id"] == dissent.json()["record"]["item_id"] for item in visible.json()["dissent"])
        assert len(visible.json()["acceptance_history"]) == 1


def test_direct_transition_refuses_comments_and_replay_mismatch(tmp_path):
    mediator = SimpleNamespace(intake_case_file={})
    service = WorkflowActionService(mediator)
    common = dict(
        case_id="case-synthetic",
        actor_principal_id="lawyer-1",
        canonical_owner_principal_id="tenant-1",
        authorized=True,
        item_id="proposal-1",
        target_kind="draft_revision",
        target_id="draft-1",
        replacement="Paragraph one.",
        expected_review_revision=0,
        expected_target_revision=0,
        request_id="direct-1",
    )
    refused = service.apply_authorized_review_transition(**{**common, "item_type": "review_comment"})
    assert refused["status"] == "refused"
    assert refused["error"]["code"] == "not_an_accepted_transition"
    assert refused["applied"] is False
    assert mediator.intake_case_file.get("review_case_state") is None
    unauthorized = service.apply_authorized_review_transition(**{**common, "item_type": "review_proposal", "authorized": False})
    assert unauthorized["error"]["code"] == "actor_not_permitted"
    assert mediator.intake_case_file.get("review_case_state") is None
    applied = service.apply_authorized_review_transition(**{**common, "item_type": "review_proposal"})
    assert applied["status"] == "applied"
    assert applied["draft_revisions"]["draft-1"]["revision"] == 1
    mismatch = service.apply_authorized_review_transition(**{
        **common,
        "item_type": "review_proposal",
        "replacement": "Paragraph two.",
        "expected_review_revision": 1,
        "expected_target_revision": 1,
    })
    assert mismatch["error"]["code"] == "replay_mismatch"
    assert mediator.intake_case_file["review_case_state"]["draft_revisions"]["draft-1"]["text"] == "Paragraph one."
    replay = service.apply_authorized_review_transition(**{**common, "item_type": "review_proposal"})
    assert replay["replayed"] is True
    assert replay["draft_revisions"]["draft-1"]["revision"] == 1
