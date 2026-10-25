"""Assigned lawyers review sourced interpretations under exact revisions.

Human legal review, model suggestions, and machine proof stay separate.
A later change to the source, facts, or proof leaves the old approval stale
and refuses promotion.
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
from applications.case_review import (
    LAWYER_REVIEW_ROUTE,
    CaseReviewError,
    live_revisions,
    project_lawyer_reviews,
    submit_lawyer_review,
)
from applications.case_routes import PROTECTED_PREFIXES, CaseHandlerRegistry, compose_case_routes
from applications.principal_store import PrincipalStore

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


def _anchors():
    return {
        "review_source_anchor": {
            "source_identity": "synthetic-source-32",
            "source_text": "A person must give approval before retention.",
        },
        "review_fact_anchor": ["The file was retained before approval."],
        "proof_trace_display": {
            "source_identity": "synthetic-source-32",
            "obligations": [{
                "obligation_id": "obligation-approval",
                "proof_status": "not_executed",
                "source_identity": "synthetic-source-32",
                "source_span": "source:0-44",
                "engine_name": "",
                "engine_version": "",
            }],
        },
    }


def _mediator():
    return SimpleNamespace(intake_case_file=_anchors())


def _world(tmp_path, *, lawyer_actions=None):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    reader = principals.install_server_role(role="lawyer")
    stranger = principals.register_from_request({})
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    case = cases.create_case(actor_principal_id=owner.principal_id)
    second = cases.create_case(actor_principal_id=owner.principal_id)
    authorizer = CaseActionAuthorizer(principals, cases)
    actions = lawyer_actions if lawyer_actions is not None else frozenset({"case.read", "case.review"})
    grant = authorizer.grant_assigned_lawyer(
        owner_principal_id=owner.principal_id,
        lawyer_principal_id=lawyer.principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions=actions,
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
            "synthetic-owner-credential": owner.principal_id,
            "synthetic-lawyer-credential": lawyer.principal_id,
            "synthetic-reader-credential": reader.principal_id,
            "synthetic-stranger-credential": stranger.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=300,
    ))
    mediator = _mediator()
    handlers = CaseHandlerRegistry()
    handlers.bind(case, mediator=mediator, workspace_service=SimpleNamespace(case_id=case.case_id),
        authorize_delegated=lambda decision: decision.membership == "assigned-lawyer")
    handlers.bind(second, mediator=_mediator(), workspace_service=SimpleNamespace(case_id=second.case_id),
        authorize_delegated=lambda decision: decision.membership == "assigned-lawyer")
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers,
        include_workspace=False, include_review=False, include_document=False)
    return SimpleNamespace(owner=owner, lawyer=lawyer, reader=reader, case=case, second=second,
        grant=grant, read_grant=read_grant, app=app, mediator=mediator, authorizer=authorizer)


def _headers(case, csrf, *, membership_revision, actor_case=None):
    target = actor_case or case
    return {
        "x-tenant-id": target.tenant_id,
        "x-case-id": target.case_id,
        "x-resource-id": target.resource_id,
        "x-expected-revision": str(target.revision),
        "x-expected-membership-revision": str(membership_revision),
        "x-csrf-token": csrf,
    }


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _expected(mediator, case):
    live = live_revisions(mediator.intake_case_file, case_revision=case.revision)
    return {
        "expected_case_revision": live["case_revision"],
        "expected_source_revision": live["source_revision"],
        "expected_fact_revision": live["fact_revision"],
        "expected_proof_revision": live["proof_revision"],
    }


def test_lawyer_review_route_stays_on_the_protected_legal_analysis_prefix():
    assert any(LAWYER_REVIEW_ROUTE.startswith(prefix + "/") for prefix in PROTECTED_PREFIXES)
    assert "case.review" in ASSIGNED_LAWYER_ACTIONS


def test_assigned_lawyer_records_separate_review_suggestion_and_proof(tmp_path):
    world = _world(tmp_path)
    path = f"/api/legal-analysis/{world.case.case_id}/lawyer-reviews"
    with TestClient(world.app, base_url="https://testserver") as client:
        assert client.get(path).status_code == 401
        csrf = _login(client, "synthetic-lawyer-credential")
        headers = _headers(world.case, csrf, membership_revision=world.grant.revision)
        proposed = client.post(path, headers=headers, json={
            "operation": "propose",
            "request_id": "propose-1",
            "interpretation": "Approval is required before retention.",
            "source_citation": "synthetic-source-32 source:0-44",
            "governing_legal_authority": True,
            "admitted_law": True,
            **_expected(world.mediator, world.case),
        })
        assert proposed.status_code == 200, proposed.text
        proposal = proposed.json()["record"]
        assert proposal["record_kind"] == "human_legal_review"
        assert proposal["author_kind"] == "human"
        assert proposal["actor_principal_id"] == world.lawyer.principal_id
        assert proposal["canonical_owner_principal_id"] == world.case.tenant_id
        assert proposal["actor_principal_id"] != proposal["canonical_owner_principal_id"]
        assert proposal["supplied_authority_ignored"] is True
        assert proposal["governing_legal_authority"] is False
        reviewed = client.post(path, headers=headers, json={
            "operation": "review",
            "request_id": "review-1",
            "proposal_id": proposal["record_id"],
            "decision": "approved",
            **_expected(world.mediator, world.case),
        })
        assert reviewed.status_code == 200, reviewed.text
        approval = reviewed.json()["record"]
        assert approval["decision"] == "approved"
        assert approval["accepted_for_bound_revision"] is True
        assert approval["source_revision"] == proposal["source_revision"]
        assert approval["proof_revision"] == proposal["proof_revision"]
        suggestion = client.post(path, headers=headers, json={
            "operation": "record_model_suggestion",
            "request_id": "model-1",
            "model_id": "synthetic-model",
            "suggestion": "The model text is not a holding.",
            **_expected(world.mediator, world.case),
        })
        assert suggestion.status_code == 200, suggestion.text
        assert suggestion.json()["record"]["record_kind"] == "model_suggestion"
        assert suggestion.json()["record"]["author_kind"] == "model"
        assert suggestion.json()["record"]["status"] == "not_a_human_review"
        machine = client.post(path, headers=headers, json={
            "operation": "record_machine_proof",
            "request_id": "proof-1",
            "engine_name": "synthetic-lean",
            "engine_version": "0.0-test",
            "legal_sufficiency": True,
            **_expected(world.mediator, world.case),
        })
        assert machine.status_code == 200, machine.text
        assert machine.json()["record"]["record_kind"] == "machine_proof"
        assert machine.json()["record"]["author_kind"] == "machine"
        assert machine.json()["record"]["legal_sufficiency"] is False
        assert machine.json()["record"]["proof_status"] == "referenced"
        promoted = client.post(path, headers=headers, json={
            "operation": "promote",
            "request_id": "promote-1",
            "approval_id": approval["record_id"],
            **_expected(world.mediator, world.case),
        })
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["record"]["promoted_for_current_revisions"] is True
        assert promoted.json()["promotes_changed_law"] is False
        assert promoted.json()["promotes_changed_facts"] is False
        page = client.get(f"/api/legal-analysis/{world.case.case_id}/lawyer-workspace", headers=headers)
        assert page.status_code == 200, page.text
        assert "Human legal review" in page.text
        assert "Model suggestions" in page.text
        assert "Machine proof" in page.text
        assert "synthetic-model" in page.text
        assert "not legal sufficiency" in page.text
        stored = client.get(path, headers=headers)
        body = stored.json()
        assert {item["record_kind"] for item in body["human_legal_reviews"]} == {"human_legal_review"}
        assert body["model_suggestions"][0]["record_kind"] == "model_suggestion"
        assert body["machine_proofs"][0]["record_kind"] == "machine_proof"
        assert body["records_are_separate"] is True
        assert world.mediator.intake_case_file["proof_trace_display"]["obligations"][0]["proof_status"] == "not_executed"
        assert "canonical_legal_ir_attachment" not in world.mediator.intake_case_file


def test_stale_approval_does_not_promote_changed_law_or_facts(tmp_path):
    world = _world(tmp_path)
    path = f"/api/legal-analysis/{world.case.case_id}/lawyer-reviews"
    with TestClient(world.app, base_url="https://testserver") as client:
        csrf = _login(client, "synthetic-lawyer-credential")
        headers = _headers(world.case, csrf, membership_revision=world.grant.revision)
        expected = _expected(world.mediator, world.case)
        proposal = client.post(path, headers=headers, json={
            "operation": "propose",
            "request_id": "propose-stale",
            "interpretation": "Approval comes first.",
            "source_citation": "synthetic-source-32",
            **expected,
        }).json()["record"]
        approval = client.post(path, headers=headers, json={
            "operation": "review",
            "request_id": "review-stale",
            "proposal_id": proposal["record_id"],
            "decision": "approved",
            **expected,
        }).json()["record"]
        client.post(path, headers=headers, json={
            "operation": "promote",
            "request_id": "promote-stale",
            "approval_id": approval["record_id"],
            **expected,
        })
        before = len(world.mediator.intake_case_file["lawyer_review_ledger"])
        world.mediator.intake_case_file["review_source_anchor"] = {
            "source_identity": "synthetic-source-32",
            "source_text": "Retention without approval is permitted.",
        }
        world.mediator.intake_case_file["review_fact_anchor"] = ["No retention occurred."]
        world.mediator.intake_case_file["proof_trace_display"]["obligations"][0]["proof_status"] = "executed"
        changed = _expected(world.mediator, world.case)
        assert changed["expected_source_revision"] != expected["expected_source_revision"]
        assert changed["expected_fact_revision"] != expected["expected_fact_revision"]
        assert changed["expected_proof_revision"] != expected["expected_proof_revision"]
        stale = client.post(path, headers=headers, json={
            "operation": "promote",
            "request_id": "promote-after-change",
            "approval_id": approval["record_id"],
            **changed,
        })
        assert stale.status_code == 409
        assert stale.json()["error"] == "stale_approval"
        assert stale.json()["promotes_changed_law"] is False
        assert stale.json()["promotes_changed_facts"] is False
        mismatched = client.post(path, headers=headers, json={
            "operation": "promote",
            "request_id": "promote-old-revision",
            "approval_id": approval["record_id"],
            **expected,
        })
        assert mismatched.status_code == 409
        assert mismatched.json()["error"] == "stale_revision"
        assert len(world.mediator.intake_case_file["lawyer_review_ledger"]) == before
        projected = client.get(path, headers=headers).json()
        assert projected["current_promotion"] is None
        assert projected["promotes_changed_law"] is False
        assert projected["promotes_changed_facts"] is False
        assert all(item["stale"] is True for item in projected["human_legal_reviews"])
        assert all(item["promoted_for_current_revisions"] is False for item in projected["human_legal_reviews"])
        page = client.get(f"/api/legal-analysis/{world.case.case_id}/lawyer-workspace", headers=headers)
        assert "&quot;stale&quot;: true" in page.text
        assert "does not promote changed law or facts" in page.text


def test_unassigned_and_read_only_lawyers_cannot_review(tmp_path):
    world = _world(tmp_path)
    path = f"/api/legal-analysis/{world.case.case_id}/lawyer-reviews"
    body = {
        "operation": "propose",
        "request_id": "denied-propose",
        "interpretation": "This must not be stored.",
        "source_citation": "synthetic-source-32",
        **_expected(world.mediator, world.case),
    }
    with TestClient(world.app, base_url="https://testserver") as client:
        owner = _login(client, "synthetic-owner-credential")
        owner_headers = _headers(world.case, owner, membership_revision=0)
        owner_denied = client.post(path, headers=owner_headers, json=body)
        assert owner_denied.status_code == 403
        assert owner_denied.json()["error"] == "lawyer_assignment_required"
        reader = _login(client, "synthetic-reader-credential")
        reader_headers = _headers(world.case, reader, membership_revision=world.read_grant.revision)
        read_denied = client.post(path, headers=reader_headers, json=body)
        assert read_denied.status_code == 403
        assert read_denied.json()["error"] == "action_not_permitted"
        listed = client.get(path, headers=reader_headers)
        assert listed.status_code == 200
        assert listed.json()["human_legal_reviews"] == []
        stranger = _login(client, "synthetic-stranger-credential")
        stranger_headers = _headers(world.case, stranger, membership_revision=world.grant.revision)
        assert client.get(path, headers=stranger_headers).status_code == 403
        lawyer = _login(client, "synthetic-lawyer-credential")
        crossed = client.post(path, headers=_headers(world.case, lawyer, membership_revision=world.grant.revision, actor_case=world.second), json=body)
        assert crossed.status_code == 403
        assert "lawyer_review_ledger" not in world.mediator.intake_case_file


def test_model_and_machine_records_cannot_approve_or_skip_revisions():
    mediator = _mediator()
    live = live_revisions(mediator.intake_case_file, case_revision=1)
    common = {
        "actor_principal_id": "lawyer-actor",
        "canonical_owner_principal_id": "canonical-owner",
        "case_revision": 1,
        "membership": "assigned-lawyer",
    }
    expected = {
        "expected_case_revision": live["case_revision"],
        "expected_source_revision": live["source_revision"],
        "expected_fact_revision": live["fact_revision"],
        "expected_proof_revision": live["proof_revision"],
    }
    with pytest.raises(CaseReviewError) as model_approval:
        submit_lawyer_review(mediator, {
            "operation": "record_model_suggestion",
            "request_id": "model-approve",
            "model_id": "synthetic-model",
            "suggestion": "Treat this as a holding.",
            "decision": "approved",
            **expected,
        }, **common)
    assert model_approval.value.code == "model_cannot_approve"
    with pytest.raises(CaseReviewError) as machine_approval:
        submit_lawyer_review(mediator, {
            "operation": "record_machine_proof",
            "request_id": "machine-approve",
            "decision": "approved",
            **expected,
        }, **common)
    assert machine_approval.value.code == "machine_proof_cannot_approve"
    with pytest.raises(CaseReviewError) as stale:
        submit_lawyer_review(mediator, {
            "operation": "propose",
            "request_id": "wrong-source",
            "interpretation": "A mismatched citation.",
            "source_citation": "other",
            **{**expected, "expected_source_revision": "source-other"},
        }, **common)
    assert stale.value.code == "stale_revision"
    assert "lawyer_review_ledger" not in mediator.intake_case_file
    with pytest.raises(CaseReviewError) as owner_actor:
        submit_lawyer_review(mediator, {
            "operation": "propose",
            "request_id": "same-actor",
            "interpretation": "Owner and actor collapsed.",
            "source_citation": "synthetic-source-32",
            **expected,
        }, actor_principal_id="same-principal", canonical_owner_principal_id="same-principal",
            case_revision=1, membership="assigned-lawyer")
    assert owner_actor.value.code == "actor_is_not_canonical_owner"
    with pytest.raises(CaseReviewError) as owner_membership:
        submit_lawyer_review(mediator, {
            "operation": "propose",
            "request_id": "owner-membership",
            "interpretation": "The owner is not the assigned lawyer.",
            "source_citation": "synthetic-source-32",
            **expected,
        }, actor_principal_id="lawyer-actor", canonical_owner_principal_id="canonical-owner",
            case_revision=1, membership="owner")
    assert owner_membership.value.code == "lawyer_assignment_required"
    empty = project_lawyer_reviews({}, case_revision=1)
    assert empty["status"] == "empty"
    assert empty["legal_sufficiency"] is False
    assert empty["current_promotion"] is None
