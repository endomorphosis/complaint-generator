"""Bounded legal-source candidates from the GUI.

Positive cases record a purpose choice, then acquire through the bound
mediator research hook with a bounded query and source/version receipts.
Negative cases refuse a missing purpose choice, an unbounded query, a
cross-case id, and a missing session. Snippets, missing archives, and model
text stay research gaps. Nothing in the receipt is admitted law.
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
    SESSION_COOKIE,
)
from applications.case_access import CaseActionAuthorizer
from applications.case_consent_api import CaseConsentService
from applications.case_directory import CaseDirectory
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.legal_research_api import (
    LegalResearchError,
    acquire_bounded_legal_sources,
    project_legal_research,
)
from applications.principal_store import PrincipalStore

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ROOT = Path(__file__).resolve().parents[1]


class _Search:
    def __init__(self) -> None:
        self.calls = []

    def acquire_bounded_canonical_sources(self, binding, **kwargs):
        self.calls.append({"binding": binding, "kwargs": dict(kwargs)})
        if kwargs.get("cancelled"):
            return {"status": "cancelled", "error_code": "cancelled", "candidates": [], "proof": False, "operations": []}
        return {
            "status": "candidates",
            "proof": True,
            "model_inference_used": True,
            "candidates": [
                {
                    "source_text": "Every person who, under color of any statute, subjects another.",
                    "version": "us-code-2024.1",
                    "locator": "42 U.S.C. § 1983",
                    "locator_kind": "citation",
                    "source_family": "us_code",
                    "retrieval": {"content_hash": "abc123", "source_family": "us_code", "corpus_id": "uscode"},
                    "admitted": True,
                    "proof": True,
                },
                {"snippet": "short search blurb", "passage_status": "snippet_only", "version": "web-1"},
                {"model_text": "A model paraphrase of the statute.", "version": "model-0"},
                {"archive_status": "missing", "locator": "https://archive.example/missing", "version": ""},
            ],
            "operations": [{
                "source_family": "web_archive",
                "status": "incomplete",
                "error_code": "missing_archive",
                "version": "",
                "withheld": [{"reason": "source_text_missing"}],
            }],
        }


class _Mediator:
    def __init__(self) -> None:
        self.intake_case_file = {"legal_context": {"jurisdiction": "OR"}, "legal_authorities": []}
        self.search = _Search()
        self.legal_authority_search = self.search
        self.builds = []
        self.admissions = []

    def build_legal_acquisition_request(self, case_file, **kwargs):
        self.builds.append({"case": case_file, "kwargs": dict(kwargs)})
        return {"ready": True, "request": {"program": {"query_text": (kwargs.get("query_terms") or [""])[0]}}}

    def admit_acquired_authorities(self, *args, **kwargs):
        self.admissions.append((args, kwargs))
        raise AssertionError("research must not admit law")


class _Authority:
    def __init__(self, view: dict) -> None:
        self.actor_principal_id = "actor-1"
        self.case_id = "case-1"
        self.view = view

    def processing_consent(self, *, purpose, actor_principal_id, workspace):
        assert actor_principal_id == self.actor_principal_id
        assert workspace is not None
        return self.view


def _view(generation=1, *, revoked=False, egress=False):
    return {"decisions": [{
        "purpose": "citation_acquisition",
        "generation": generation,
        "mode": "local_private",
        "explicit": False,
        "revoked": revoked,
        "egress_authorized": egress,
        "data_class": "public_legal_source_graph",
    }]}


def _body(**extra):
    body = {
        "purpose": "citation_acquisition",
        "query": "42 U.S.C. 1983 color of law",
        "max_results": 3,
        "deadline_seconds": 2.0,
        "max_bytes": 1024,
        "retrieval_mode": "cache",
        "expected_consent_generation": 1,
        "operation_id": "op-1",
        "local_rows": {"us_code": [{"citation": "42 U.S.C. § 1983"}]},
    }
    body.update(extra)
    return body


def test_hook_returns_versioned_candidates_and_research_gaps_without_admitting_law():
    mediator = _Mediator()
    workspace = SimpleNamespace(case_id="case-1")
    receipt = acquire_bounded_legal_sources(mediator, workspace, _Authority(_view()), _body())
    assert receipt["admitted_law"] is False
    assert receipt["proof"] is False
    assert receipt["legal_sufficiency"] is False
    assert receipt["model_inference_used"] is False
    assert receipt["dispatched"] is True
    assert receipt["candidate_count"] == 1
    assert receipt["research_gap_count"] >= 3
    candidate = next(item for item in receipt["source_version_receipts"] if item["kind"] == "candidate")
    assert candidate["version"] == "us-code-2024.1"
    assert candidate["content_hash"] == "abc123"
    assert candidate["admitted_law"] is False
    assert candidate["proof"] is False
    reasons = {item["reason"] for item in receipt["source_version_receipts"] if item["kind"] == "research_gap"}
    assert "snippet_not_law" in reasons
    assert "model_text_not_law" in reasons
    assert "missing_archive" in reasons
    assert mediator.admissions == []
    assert mediator.intake_case_file["legal_authorities"] == []
    call = mediator.search.calls[0]["kwargs"]
    assert call["cancelled"] is False
    assert call["max_results"] == 3
    assert call["deadline_seconds"] == 2.0
    assert call["max_bytes"] == 1024
    assert call["purpose"] == "citation_acquisition"
    assert call["retrieval_mode"] == "cache"
    assert mediator.builds[0]["kwargs"]["query_terms"] == ["42 U.S.C. 1983 color of law"]
    assert mediator.builds[0]["kwargs"]["timeout_seconds"] == 2.0

    replay = acquire_bounded_legal_sources(mediator, workspace, _Authority(_view()), _body())
    assert replay["replayed"] is True
    assert replay["dispatched"] is False
    assert replay["admitted_law"] is False
    assert len(mediator.search.calls) == 1

    cancelled = acquire_bounded_legal_sources(mediator, workspace, _Authority(_view()), _body(
        operation_id="op-cancel", cancelled=True))
    assert cancelled["status"] == "cancelled"
    assert cancelled["source_version_receipts"] == []
    assert cancelled["admitted_law"] is False
    assert mediator.search.calls[-1]["kwargs"]["cancelled"] is True

    with pytest.raises(LegalResearchError) as missing:
        acquire_bounded_legal_sources(mediator, workspace, _Authority(_view(generation=0)), _body(
            operation_id="op-consent", expected_consent_generation=0))
    assert missing.value.code == "purpose_consent_required"
    assert len(mediator.search.calls) == 2

    with pytest.raises(LegalResearchError) as unbounded:
        acquire_bounded_legal_sources(mediator, workspace, _Authority(_view()), _body(
            operation_id="op-bounds", query="x" * 257, max_results=9))
    assert unbounded.value.code == "legal_research_bounds"
    assert len(mediator.search.calls) == 2

    with pytest.raises(LegalResearchError) as live:
        acquire_bounded_legal_sources(mediator, workspace, _Authority(_view()), _body(
            operation_id="op-live", retrieval_mode="live"))
    assert live.value.code == "purpose_consent_required"

    stored = project_legal_research({"legal_source_candidate_receipt": receipt})
    assert stored["admitted_law"] is False
    assert stored["candidate_count"] == 1
    assert all(item["admitted_law"] is False for item in stored["source_version_receipts"])
    latest = project_legal_research(mediator.intake_case_file)
    assert latest["status"] == "cancelled"
    assert latest["admitted_law"] is False


def _world(tmp_path):
    now = {"t": 1_700_000_100}

    def clock():
        now["t"] += 1
        return now["t"]

    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    owner = principals.register_from_request({})
    stranger = principals.register_from_request({})
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    case = cases.create_case(actor_principal_id=owner.principal_id)
    second = cases.create_case(actor_principal_id=owner.principal_id)
    authorizer = CaseActionAuthorizer(principals, cases)
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            "synthetic-owner-credential": owner.principal_id,
            "synthetic-stranger-credential": stranger.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=300,
    ))
    consent = CaseConsentService(tmp_path / "consent", cases=cases, key=os.urandom(32), key_id="consent-key", clock=clock)
    handlers = CaseHandlerRegistry()
    mediators = {}
    for selected in (case, second):
        mediator = _Mediator()
        workspace = SimpleNamespace(case_id=selected.case_id)
        handlers.bind(selected, mediator=mediator, workspace_service=workspace, authorize_delegated=lambda _decision: False)
        mediators[selected.case_id] = mediator
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers,
        case_consent=consent, include_workspace=False, include_review=False, include_document=False)
    return SimpleNamespace(owner=owner, case=case, second=second, app=app, mediators=mediators, consent=consent)


def _headers(case, csrf=None):
    headers = {
        "x-tenant-id": case.tenant_id,
        "x-case-id": case.case_id,
        "x-resource-id": case.resource_id,
        "x-expected-revision": str(case.revision),
    }
    if csrf is not None:
        headers["x-csrf-token"] = csrf
    return headers


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def test_http_acquisition_checks_consent_cancellation_and_case_boundary(tmp_path):
    world = _world(tmp_path)
    case = world.case
    path = f"/api/legal-research/{case.case_id}"
    world.consent.choose(world.owner.principal_id, case.case_id, {
        "purpose": "citation_acquisition",
        "mode": "local_private",
        "expected_generation": 0,
    })
    with TestClient(world.app, base_url="https://testserver") as client:
        anonymous = client.get(path, headers=_headers(case))
        assert anonymous.status_code == 401
        csrf = _login(client, "synthetic-owner-credential")
        empty = client.get(path, headers=_headers(case, csrf))
        assert empty.status_code == 200, empty.text
        assert empty.json()["admitted_law"] is False
        assert empty.json()["source_version_receipts"] == []
        refused = client.post(path, headers=_headers(case, csrf), json=_body(
            purpose="public_law_citation", expected_consent_generation=1, operation_id="http-0"))
        assert refused.status_code == 403
        assert refused.json()["error"] == "purpose_consent_required"
        assert refused.json()["admitted_law"] is False
        conflict = client.post(path, headers=_headers(case, csrf), json=_body(
            expected_consent_generation=0, operation_id="http-stale"))
        assert conflict.status_code == 409
        assert conflict.json()["error"] == "consent_revision_conflict"
        assert world.mediators[case.case_id].search.calls == []
        saved = client.post(path, headers=_headers(case, csrf), json=_body(operation_id="http-1"))
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["case_id"] == case.case_id
        assert body["admitted_law"] is False
        assert body["candidate_count"] == 1
        assert body["source_version_receipts"][0]["version"] == "us-code-2024.1"
        assert body["source_version_receipts"][0]["admitted_law"] is False
        assert any(item["reason"] == "model_text_not_law" for item in body["source_version_receipts"])
        again = client.post(path, headers=_headers(case, csrf), json=_body(operation_id="http-1"))
        assert again.status_code == 200
        assert again.json()["replayed"] is True
        assert len(world.mediators[case.case_id].search.calls) == 1
        cancelled = client.post(path, headers=_headers(case, csrf), json=_body(operation_id="http-cancel", cancelled=True))
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["admitted_law"] is False
        assert world.mediators[case.case_id].search.calls[-1]["kwargs"]["cancelled"] is True
        unbounded = client.post(path, headers=_headers(case, csrf), json=_body(operation_id="http-big", max_results=50))
        assert unbounded.status_code == 422
        assert unbounded.json()["error"] == "legal_research_bounds"
        crossed = client.post(f"/api/legal-research/{world.second.case_id}", headers=_headers(case, csrf), json=_body(operation_id="http-cross"))
        assert crossed.status_code == 403
        assert crossed.json()["error"] == "cross_case_id"
        assert world.mediators[world.second.case_id].search.calls == []
        assert world.mediators[case.case_id].admissions == []
        _login(client, "synthetic-stranger-credential")
        denied = client.get(path, headers=_headers(case))
        assert denied.status_code == 403


def test_workspace_describes_candidates_as_unadmitted():
    html = (ROOT / "templates" / "workspace.html").read_text(encoding="utf-8")
    section = html.split('id="legal-source-candidates"', 1)[1].split('id="workspace-privacy-actions"', 1)[0]
    for element_id in (
        "legal-research-case-id",
        "legal-research-purpose",
        "legal-research-query",
        "legal-research-max-results",
        "legal-research-deadline",
        "legal-research-consent-generation",
        "legal-research-display",
        "legal-research-receipts",
        "legal-research-run",
        "legal-research-cancel",
    ):
        assert f'id="{element_id}"' in section
    assert 'data-admitted-law="false"' in section
    assert "never admitted law" in section
    assert "citation_acquisition" in section
    assert "public_law_citation" in section
    assert "/api/legal-research/" in html
    assert "cancelled: cancelled === true" in html
    assert "Admitted law: false." in html
