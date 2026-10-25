"""Explicit admission of versioned legal authorities.

Positive cases admit an exact stored passage for the case owner and for an
assigned lawyer, including identity, jurisdiction, effective date,
applicability, exceptions, and treatment state. Negative cases leave a source
mismatch, stale version, missing passage, rejection, and unauthorized reviewer
unresolved while keeping attribution.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import (
    BrowserSessionConfiguration,
    BrowserSessionService,
    PrincipalStoreCredentialAdapter,
)
from applications.case_access import CaseActionAuthorizer
from applications.case_directory import CaseDirectory
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.legal_research_api import (
    acquire_bounded_legal_sources,
    project_authority_admissions,
    review_versioned_authority,
)
from applications.principal_store import PrincipalStore

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ROOT = Path(__file__).resolve().parents[1]
PASSAGE = "Every person who, under color of any statute, subjects another to the deprivation of any rights."
STALE_PASSAGE = "A prior edition of the same section that is no longer current."


def _candidate(**extra):
    row = {
        "source_text": PASSAGE,
        "version": "us-code-2024.1",
        "current_version": "us-code-2024.1",
        "locator": "42 U.S.C. § 1983",
        "authority_identity": "42 U.S.C. § 1983",
        "jurisdiction": "US",
        "effective_date": "1996-10-19",
        "applicability": "applicable",
        "exceptions": ["qualified immunity is not decided here"],
        "treatment_state": "good_law",
        "content_hash": "hash-current",
        "source_family": "us_code",
    }
    row.update(extra)
    return row


class _Search:
    def __init__(self) -> None:
        self.calls = []

    def acquire_bounded_canonical_sources(self, binding, **kwargs):
        self.calls.append(kwargs)
        return {
            "status": "candidates",
            "proof": False,
            "candidates": [
                _candidate(),
                _candidate(source_text=STALE_PASSAGE, version="us-code-1990.1", current_version="us-code-2024.1",
                           content_hash="hash-stale", version_state="stale"),
            ],
        }


class _Mediator:
    def __init__(self) -> None:
        self.intake_case_file = {"legal_context": {"jurisdiction": "US"}, "legal_authorities": []}
        self.search = _Search()
        self.legal_authority_search = self.search
        self.admissions = []
        self.owner_status = "admitted"

    def build_legal_acquisition_request(self, case_file, **kwargs):
        return {"ready": True, "request": {"program": {"query_text": "42 U.S.C. 1983"}}}

    def admit_acquired_authorities(self, acquisition, claims, intake_case_file, user_id=None):
        self.admissions.append({
            "acquisition": acquisition,
            "claims": claims,
            "user_id": user_id,
            "explicit_review": acquisition.get("explicit_review"),
        })
        return {"status": self.owner_status, "proof": False}


class _Authority:
    def __init__(self, generation=1) -> None:
        self.actor_principal_id = "actor-1"
        self.case_id = "case-1"

    def processing_consent(self, *, purpose, actor_principal_id, workspace):
        return {"decisions": [{
            "purpose": purpose,
            "generation": 1,
            "mode": "local_private",
            "explicit": False,
            "revoked": False,
            "egress_authorized": False,
            "data_class": "public_legal_source_graph",
        }]}


def _acquire(mediator):
    return acquire_bounded_legal_sources(mediator, SimpleNamespace(case_id="case-1"), _Authority(), {
        "purpose": "citation_acquisition",
        "query": "42 U.S.C. 1983",
        "max_results": 2,
        "deadline_seconds": 2.0,
        "max_bytes": 2048,
        "retrieval_mode": "cache",
        "expected_consent_generation": 1,
        "operation_id": "acquire-1",
    })


def _review(**extra):
    body = {
        "decision": "admit",
        "source_passage": PASSAGE,
        "content_hash": "hash-current",
        "version": "us-code-2024.1",
        "authority_identity": "42 U.S.C. § 1983",
        "jurisdiction": "US",
        "effective_date": "1996-10-19",
        "applicability": "applicable",
        "exceptions": ["qualified immunity is not decided here"],
        "treatment_state": "good_law",
        "operation_id": "review-1",
    }
    body.update(extra)
    return body


def test_owner_admits_exact_passage_and_failures_stay_unresolved():
    mediator = _Mediator()
    acquired = _acquire(mediator)
    assert acquired["admitted_law"] is False
    assert acquired["source_version_receipts"][0]["source_passage"] == PASSAGE
    assert acquired["source_version_receipts"][0]["admitted_law"] is False
    authority = _Authority()
    admitted = review_versioned_authority(
        mediator, SimpleNamespace(case_id="case-1"), authority, _review(),
        membership="owner", actor_is_encrypted_owner=False, canonical_owner_principal_id="tenant-1",
    )
    assert admitted["status"] == "admitted"
    assert admitted["admitted_law"] is True
    assert admitted["proof"] is False
    assert admitted["legal_sufficiency"] is False
    assert admitted["source_passage"] == PASSAGE
    assert admitted["authority_identity"] == "42 U.S.C. § 1983"
    assert admitted["jurisdiction"] == "US"
    assert admitted["effective_date"] == "1996-10-19"
    assert admitted["applicability"] == "applicable"
    assert admitted["exceptions"] == ["qualified immunity is not decided here"]
    assert admitted["treatment_state"] == "good_law"
    assert admitted["attribution"]["actor_principal_id"] == "actor-1"
    assert admitted["attribution"]["membership"] == "owner"
    assert admitted["attribution"]["canonical_owner_principal_id"] == "tenant-1"
    assert admitted["attribution"]["actor_is_encrypted_owner"] is False
    assert admitted["attribution"]["actor_principal_id"] != admitted["attribution"]["canonical_owner_principal_id"]
    assert mediator.admissions[-1]["explicit_review"] is True
    assert mediator.admissions[-1]["user_id"] == "actor-1"
    assert mediator.intake_case_file["legal_source_candidate_receipt"]["admitted_law"] is False

    replay = review_versioned_authority(
        mediator, SimpleNamespace(case_id="case-1"), authority, _review(),
        membership="owner", canonical_owner_principal_id="tenant-1",
    )
    assert replay["replayed"] is True
    assert len(mediator.admissions) == 1

    mismatched = review_versioned_authority(
        mediator, SimpleNamespace(case_id="case-1"), authority, _review(
            operation_id="review-mismatch", jurisdiction="OR"),
        membership="owner", canonical_owner_principal_id="tenant-1",
    )
    assert mismatched["status"] == "unresolved"
    assert mismatched["reason"] == "source_mismatch"
    assert mismatched["admitted_law"] is False
    assert mismatched["attribution"]["decision"] == "admit"
    assert mismatched["attribution"]["actor_principal_id"] == "actor-1"

    stale = review_versioned_authority(
        mediator, SimpleNamespace(case_id="case-1"), authority, _review(
            operation_id="review-stale", source_passage=STALE_PASSAGE, content_hash="hash-stale",
            version="us-code-1990.1"),
        membership="owner", canonical_owner_principal_id="tenant-1",
    )
    assert stale["status"] == "unresolved"
    assert stale["reason"] == "stale_version"
    assert stale["admitted_law"] is False
    assert stale["attribution"]["recorded"] is True

    missing = review_versioned_authority(
        mediator, SimpleNamespace(case_id="case-1"), authority, _review(
            operation_id="review-missing", source_passage="   ", content_hash="hash-absent"),
        membership="owner", canonical_owner_principal_id="tenant-1",
    )
    assert missing["status"] == "unresolved"
    assert missing["reason"] == "missing_passage"
    assert missing["attribution"]["membership"] == "owner"

    rejected = review_versioned_authority(
        mediator, SimpleNamespace(case_id="case-1"), authority, _review(operation_id="review-reject", decision="reject"),
        membership="assigned-lawyer", canonical_owner_principal_id="tenant-1",
    )
    assert rejected["status"] == "unresolved"
    assert rejected["reason"] == "rejected"
    assert rejected["admitted_law"] is False
    assert rejected["attribution"]["decision"] == "reject"
    assert rejected["attribution"]["membership"] == "assigned-lawyer"

    unauthorized = review_versioned_authority(
        mediator, SimpleNamespace(case_id="case-1"), authority, _review(
            operation_id="review-role", reviewer_principal_id="someone-else"),
        membership="owner", canonical_owner_principal_id="tenant-1",
    )
    assert unauthorized["status"] == "unresolved"
    assert unauthorized["reason"] == "unauthorized_reviewer"
    assert unauthorized["admitted_law"] is False
    assert unauthorized["attribution"]["actor_principal_id"] == "actor-1"
    assert unauthorized["attribution"]["claimed_reviewer_principal_id"] == "someone-else"

    stranger = review_versioned_authority(
        mediator, SimpleNamespace(case_id="case-1"), authority, _review(operation_id="review-stranger"),
        membership="operational-admin", canonical_owner_principal_id="tenant-1",
    )
    assert stranger["reason"] == "unauthorized_reviewer"
    assert stranger["admitted_law"] is False
    assert stranger["attribution"]["membership"] == "operational-admin"
    assert len(mediator.admissions) == 1

    projected = project_authority_admissions(mediator.intake_case_file)
    assert projected["admitted_count"] == 1
    assert projected["unresolved_count"] >= 5
    assert all(item["proof"] is False for item in projected["admissions"])
    assert any(item["reason"] == "source_mismatch" and item["attribution"]["recorded"] is True for item in projected["admissions"])


def _world(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    stranger = principals.register_from_request({})
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    case = cases.create_case(actor_principal_id=owner.principal_id)
    authorizer = CaseActionAuthorizer(principals, cases)
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            "synthetic-owner-credential": owner.principal_id,
            "synthetic-lawyer-credential": lawyer.principal_id,
            "synthetic-stranger-credential": stranger.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=300,
    ))
    handlers = CaseHandlerRegistry()
    mediator = _Mediator()
    workspace = SimpleNamespace(case_id=case.case_id)
    def _delegated_key(decision):
        return decision.membership == "assigned-lawyer" and decision.actor_principal_id == lawyer.principal_id

    handlers.bind(case, mediator=mediator, workspace_service=workspace, authorize_delegated=_delegated_key)
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers,
        include_workspace=False, include_review=False, include_document=False)
    return SimpleNamespace(owner=owner, lawyer=lawyer, case=case, app=app, mediator=mediator, authorizer=authorizer)


def _headers(case, csrf=None, membership=None):
    headers = {
        "x-tenant-id": case.tenant_id,
        "x-case-id": case.case_id,
        "x-resource-id": case.resource_id,
        "x-expected-revision": str(case.revision),
    }
    if csrf is not None:
        headers["x-csrf-token"] = csrf
    if membership is not None:
        headers["x-expected-membership-revision"] = str(membership)
    return headers


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def test_http_owner_and_assigned_lawyer_admit_and_stranger_does_not(tmp_path):
    world = _world(tmp_path)
    case = world.case
    _acquire(world.mediator)
    path = f"/api/legal-research/{case.case_id}/admissions"
    grant = world.authorizer.grant_assigned_lawyer(
        owner_principal_id=world.owner.principal_id,
        lawyer_principal_id=world.lawyer.principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions={"case.read", "case.review"},
        expected_case_revision=case.revision,
    )
    with TestClient(world.app, base_url="https://testserver") as client:
        assert client.get(path, headers=_headers(case)).status_code == 401
        csrf = _login(client, "synthetic-owner-credential")
        saved = client.post(path, headers=_headers(case, csrf), json=_review(operation_id="http-admit"))
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["admitted_law"] is True
        assert body["source_passage"] == PASSAGE
        assert body["attribution"]["membership"] == "owner"
        assert body["attribution"]["actor_principal_id"] == world.owner.principal_id
        assert body["attribution"]["canonical_owner_principal_id"] == case.tenant_id
        assert body["proof"] is False
        listed = client.get(path, headers=_headers(case, csrf))
        assert listed.status_code == 200
        assert listed.json()["admitted_count"] == 1
        mismatch = client.post(path, headers=_headers(case, csrf), json=_review(
            operation_id="http-mismatch", effective_date="2020-01-01"))
        assert mismatch.status_code == 200, mismatch.text
        assert mismatch.json()["status"] == "unresolved"
        assert mismatch.json()["reason"] == "source_mismatch"
        assert mismatch.json()["attribution"]["actor_principal_id"] == world.owner.principal_id
        csrf = _login(client, "synthetic-lawyer-credential")
        lawyer_headers = _headers(case, csrf, grant.revision)
        lawyer = client.post(path, headers=lawyer_headers, json=_review(operation_id="http-lawyer", decision="reject"))
        assert lawyer.status_code == 200, lawyer.text
        assert lawyer.json()["admitted_law"] is False
        assert lawyer.json()["reason"] == "rejected"
        assert lawyer.json()["attribution"]["membership"] == "assigned-lawyer"
        assert lawyer.json()["attribution"]["actor_principal_id"] == world.lawyer.principal_id
        assert lawyer.json()["attribution"]["actor_principal_id"] != lawyer.json()["attribution"]["canonical_owner_principal_id"]
        _login(client, "synthetic-stranger-credential")
        stranger = client.post(path, headers=_headers(case), json=_review(operation_id="http-stranger"))
        assert stranger.status_code == 403
        assert stranger.json()["error"]
    reasons = {item["reason"] for item in world.mediator.intake_case_file["legal_authority_admissions"]}
    assert "source_mismatch" in reasons
    assert "rejected" in reasons
    assert "http-stranger" not in {item["operation_id"] for item in world.mediator.intake_case_file["legal_authority_admissions"]}
    assert sum(1 for item in world.mediator.admissions if item["explicit_review"] is True) == 1


def test_workspace_collects_explicit_authority_review_fields():
    html = (ROOT / "templates" / "workspace.html").read_text(encoding="utf-8")
    section = html.split('id="legal-authority-admission"', 1)[1].split('id="workspace-privacy-actions"', 1)[0]
    for element_id in (
        "legal-admission-case-id",
        "legal-admission-decision",
        "legal-admission-identity",
        "legal-admission-version",
        "legal-admission-jurisdiction",
        "legal-admission-effective-date",
        "legal-admission-applicability",
        "legal-admission-treatment",
        "legal-admission-exceptions",
        "legal-admission-hash",
        "legal-admission-passage",
        "legal-admission-display",
        "legal-admission-attribution",
        "legal-admission-submit",
    ):
        assert f'id="{element_id}"' in section
    assert "unauthorized reviewer" in section
    assert "stale version" in section
    assert "/admissions" in html
    assert "source_passage: fields.source_passage" in html
    assert "membership" in html
