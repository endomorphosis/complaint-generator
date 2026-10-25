"""Versioned legal graph refresh.

Positive cases bump the dependency generation after a source, context, or
factual correction and invalidate the prior links, questions, and proof
obligations. A late result is stored only when the actor grant, case revision,
consent, legal source hashes, and dependency generation still match. Negative
cases keep stale or revoked results from restoring those records.
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
from applications.case_access import CaseActionAuthorizer
from applications.case_consent_api import CaseConsentService
from applications.case_directory import CaseDirectory
from applications.case_routes import CaseHandlerRegistry, compose_case_routes
from applications.graph_api import (
    LegalDependencyGraphError,
    accept_versioned_law_late_result,
    refresh_versioned_law_graph,
)
from applications.principal_store import PrincipalStore
from mediator.workflow_service import WorkflowActionService
from tests.test_cimp_gui_27 import _admitted_case_file

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


def _service():
    mediator = _admitted_case_file()
    service = WorkflowActionService(mediator)
    mediator.workflow_actions = service
    return mediator, service


def _live(**overrides):
    binding = {
        "case_id": "case-1",
        "actor_principal_id": "actor-1",
        "case_revision": 3,
        "grant_revision": 1,
        "granted_actions": ["case.update"],
        "consent_generation": 2,
        "consent_revoked": False,
    }
    binding.update(overrides)
    return binding


def _refresh_body(**overrides):
    body = {
        "operation_id": "refresh-1",
        "correction_kind": "factual",
        "case_id": "case-1",
        "expected_case_revision": 3,
        "expected_consent_generation": 2,
        "expected_grant_revision": 1,
        "expected_dependency_generation": 0,
        "legal_source_hashes": ["hash-current"],
        "links": [{"id": "link-old", "text": "supports the prior fact", "content_hash": "hash-current"}],
        "questions": [{"id": "question-old", "text": "which fact still applies?", "content_hash": "hash-current"}],
        "proof_obligations": [{"id": "proof-old", "text": "prove the prior fact", "content_hash": "hash-current"}],
        "successors": {
            "links": [{"id": "link-new", "text": "supports the corrected fact", "content_hash": "hash-current"}],
            "questions": [{"id": "question-new", "text": "what is the corrected fact?", "content_hash": "hash-current"}],
            "proof_obligations": [{"id": "proof-new", "text": "prove the corrected fact", "content_hash": "hash-current"}],
        },
    }
    body.update(overrides)
    return body


def _replace_source(mediator, content_hash="hash-next"):
    case_file = mediator.intake_case_file
    index = case_file["legal_source_passage_index"]
    stored = dict(index.pop("hash-current"))
    stored["content_hash"] = content_hash
    stored["source_passage"] = stored["source_passage"] + " [corrected source]"
    index[content_hash] = stored
    for item in case_file["legal_authority_admissions"]:
        if item.get("admitted_law") is True and item.get("content_hash") == "hash-current":
            item["content_hash"] = content_hash
            item["source_passage"] = stored["source_passage"]
    return content_hash


def test_refresh_versions_generation_and_invalidates_prior_dependencies():
    mediator, _service_obj = _service()
    first = refresh_versioned_law_graph(mediator, live=_live(), body=_refresh_body())
    assert first["task_id"] == "CIMP-GUI-28"
    assert first["applied"] is True
    assert first["proof"] is False
    assert first["legal_sufficiency"] is False
    assert first["dependency_generation"] == 1
    assert first["operation_version"] == 1
    assert first["invalidated"] == {"links": 1, "questions": 1, "proof_obligations": 1}
    assert {item["id"]: item["status"] for item in first["links"]} == {"link-old": "invalidated", "link-new": "current"}
    assert first["questions"][0]["invalidated_reason"] == "stale_after_factual_correction"
    assert first["proof_obligations"][0]["status"] == "invalidated"
    assert all(item["proof"] is False for item in first["links"] + first["questions"] + first["proof_obligations"])

    replay = refresh_versioned_law_graph(mediator, live=_live(), body=_refresh_body())
    assert replay["replayed"] is True
    assert replay["applied"] is False
    assert replay["dependency_generation"] == 1
    assert replay["operation_version"] == 1

    _replace_source(mediator)
    second = refresh_versioned_law_graph(mediator, live=_live(case_revision=4), body=_refresh_body(
        operation_id="refresh-source",
        correction_kind="source",
        expected_case_revision=4,
        expected_dependency_generation=1,
        legal_source_hashes=["hash-next"],
        links=None,
        questions=None,
        proof_obligations=None,
        successors={
            "links": [{"id": "link-source", "text": "supports the corrected source", "content_hash": "hash-next"}],
            "questions": [{"id": "question-source", "text": "does the corrected source still apply?", "content_hash": "hash-next"}],
            "proof_obligations": [{"id": "proof-source", "text": "obligations follow the corrected source", "content_hash": "hash-next"}],
        },
    ))
    assert second["dependency_generation"] == 2
    assert second["operation_version"] == 2
    assert second["legal_source_hashes"] == ["hash-next"]
    statuses = {item["id"]: item["status"] for item in second["links"]}
    assert statuses["link-old"] == "invalidated"
    assert statuses["link-new"] == "invalidated"
    assert statuses["link-source"] == "current"
    assert second["questions"][1]["status"] == "invalidated"
    assert {item["status"] for item in second["proof_obligations"] if item["id"] != "proof-source"} == {"invalidated"}

    context = refresh_versioned_law_graph(mediator, live=_live(case_revision=4, consent_generation=3), body=_refresh_body(
        operation_id="refresh-context",
        correction_kind="context",
        expected_case_revision=4,
        expected_consent_generation=3,
        expected_dependency_generation=2,
        legal_source_hashes=["hash-next"],
        links=None,
        questions=None,
        proof_obligations=None,
        successors={"links": [{"id": "link-context", "text": "context correction", "content_hash": "hash-next"}]},
    ))
    assert context["correction_kind"] == "context"
    assert context["dependency_generation"] == 3
    assert {item["id"]: item["status"] for item in context["links"]}["link-source"] == "invalidated"
    assert {item["id"]: item["status"] for item in context["links"]}["link-context"] == "current"


def test_late_result_matches_current_binding_and_stale_results_do_not_apply():
    mediator, service = _service()
    refresh_versioned_law_graph(mediator, live=_live(), body=_refresh_body())
    late = accept_versioned_law_late_result(mediator, live=_live(), body={
        "operation_id": "late-current",
        "case_id": "case-1",
        "actor_principal_id": "actor-1",
        "case_revision": 3,
        "consent_generation": 2,
        "grant_revision": 1,
        "dependency_generation": 1,
        "legal_source_hashes": ["hash-current"],
        "links": [{"id": "link-late", "text": "late support", "content_hash": "hash-current"}],
        "questions": [{"id": "question-late", "text": "late question", "content_hash": "hash-current"}],
        "proof_obligations": [{"id": "proof-late", "text": "late obligation", "content_hash": "hash-current"}],
    })
    assert late["applied"] is True
    assert late["proof"] is False
    assert late["dependency_generation"] == 1
    assert {item["id"]: item["status"] for item in late["links"]}["link-old"] == "invalidated"
    assert {item["id"]: item["status"] for item in late["links"]}["link-late"] == "current"

    again = accept_versioned_law_late_result(mediator, live=_live(), body={
        "operation_id": "late-current",
        "dependency_generation": 1,
        "links": [{"id": "link-other", "text": "should not store", "content_hash": "hash-current"}],
    })
    assert again["replayed"] is True
    assert again["applied"] is False
    assert "link-other" not in {item["id"] for item in again["links"]}

    stale_cases = [
        (_live(case_revision=9), {"dependency_generation": 1}, "stale_case_revision"),
        (_live(consent_generation=8), {"dependency_generation": 1}, "stale_consent"),
        (_live(grant_revision=7), {"dependency_generation": 1}, "stale_actor_grant"),
        (_live(actor_principal_id="actor-2"), {"dependency_generation": 1}, "stale_actor_grant"),
        (_live(consent_revoked=True), {"dependency_generation": 1}, "consent_revoked"),
        (_live(granted_actions=["case.read"]), {"dependency_generation": 1}, "actor_not_permitted"),
        (_live(), {"dependency_generation": 0}, "stale_dependency_generation"),
        (_live(), {"dependency_generation": 1, "case_id": "case-other"}, "cross_case_id"),
    ]
    before = [dict(item) for item in service._refresh_case_file()["legal_graph_refresh"]["records"]["links"]]
    for live, claim, code in stale_cases:
        body = {"operation_id": "late-" + code, **claim}
        with pytest.raises(LegalDependencyGraphError) as caught:
            accept_versioned_law_late_result(mediator, live=live, body=body)
        assert caught.value.code == code
    after = service._refresh_case_file()["legal_graph_refresh"]["records"]["links"]
    assert after == before
    assert {item["id"]: item["status"] for item in after}["link-old"] == "invalidated"

    _replace_source(mediator)
    with pytest.raises(LegalDependencyGraphError) as stale_hash:
        accept_versioned_law_late_result(mediator, live=_live(), body={
            "operation_id": "late-hash",
            "dependency_generation": 1,
            "legal_source_hashes": ["hash-current"],
        })
    assert stale_hash.value.code == "stale_legal_source_hash"
    assert service._refresh_case_file()["legal_graph_refresh"]["legal_source_hashes"] == ["hash-current"]


def test_refresh_refuses_stale_expectations_without_writing():
    mediator, service = _service()
    refresh_versioned_law_graph(mediator, live=_live(), body=_refresh_body())
    generation = service._refresh_case_file()["legal_graph_refresh"]["dependency_generation"]
    refusals = [
        _refresh_body(operation_id="bad-case", expected_case_revision=1),
        _refresh_body(operation_id="bad-consent", expected_consent_generation=1),
        _refresh_body(operation_id="bad-grant", expected_grant_revision=0),
        _refresh_body(operation_id="bad-generation", expected_dependency_generation=0),
        _refresh_body(operation_id="bad-kind", correction_kind="narrative", expected_dependency_generation=1),
        _refresh_body(operation_id="bad-source", correction_kind="source", expected_dependency_generation=1),
        _refresh_body(operation_id="bad-hash", legal_source_hashes=["hash-forged"], expected_dependency_generation=1),
    ]
    codes = []
    for body in refusals:
        with pytest.raises(LegalDependencyGraphError) as caught:
            refresh_versioned_law_graph(mediator, live=_live(), body=body)
        codes.append(caught.value.code)
    assert codes == [
        "stale_case_revision",
        "stale_consent",
        "stale_actor_grant",
        "stale_dependency_generation",
        "correction_kind_required",
        "source_unchanged",
        "stale_legal_source_hash",
    ]
    assert service._refresh_case_file()["legal_graph_refresh"]["dependency_generation"] == generation
    with pytest.raises(LegalDependencyGraphError) as missing:
        refresh_versioned_law_graph(SimpleNamespace(intake_case_file={}), live=_live(), body=_refresh_body())
    assert missing.value.code == "legal_dependency_unavailable"


def _world(tmp_path):
    now = {"t": 1_700_000_100}

    def clock():
        now["t"] += 1
        return now["t"]

    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    stranger = principals.register_from_request({})
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    case = cases.create_case(actor_principal_id=owner.principal_id)
    second = cases.create_case(actor_principal_id=owner.principal_id)
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
    consent = CaseConsentService(tmp_path / "consent", cases=cases, key=os.urandom(32), key_id="consent-key", clock=clock)
    mediator = _admitted_case_file()
    mediator.workflow_actions = WorkflowActionService(mediator)
    handlers = CaseHandlerRegistry()
    handlers.bind(case, mediator=mediator, workspace_service=SimpleNamespace(case_id=case.case_id),
        authorize_delegated=lambda decision: decision.membership == "assigned-lawyer")
    handlers.bind(second, mediator=_admitted_case_file(), workspace_service=SimpleNamespace(case_id=second.case_id),
        authorize_delegated=lambda _decision: False)
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers,
        case_consent=consent, include_workspace=False, include_review=False, include_document=False)
    return SimpleNamespace(owner=owner, lawyer=lawyer, stranger=stranger, case=case, second=second,
        app=app, mediator=mediator, authorizer=authorizer, consent=consent)


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


def _http_body(case, **overrides):
    body = _refresh_body(
        case_id=case.case_id,
        expected_case_revision=case.revision,
        expected_consent_generation=1,
        expected_grant_revision=0,
        expected_dependency_generation=0,
    )
    body.update(overrides)
    return body


def test_http_refresh_and_late_result_follow_live_authority(tmp_path):
    world = _world(tmp_path)
    case = world.case
    path = f"/api/graphs/{case.case_id}/legal-dependency/refresh"
    late_path = f"/api/graphs/{case.case_id}/legal-dependency/late-result"
    world.consent.choose(world.owner.principal_id, case.case_id, {
        "purpose": "public_law_citation",
        "mode": "local_private",
        "expected_generation": 0,
    })
    grant = world.authorizer.grant_assigned_lawyer(
        owner_principal_id=world.owner.principal_id,
        lawyer_principal_id=world.lawyer.principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions={"case.read"},
        expected_case_revision=case.revision,
    )
    with TestClient(world.app, base_url="https://testserver") as client:
        assert client.post(path, headers=_headers(case), json=_http_body(case)).status_code == 401
        csrf = _login(client, "synthetic-owner-credential")
        stale = client.post(path, headers=_headers(case, csrf), json=_http_body(case, expected_consent_generation=0))
        assert stale.status_code == 409
        assert stale.json()["error"] == "stale_consent"
        assert stale.json()["proof"] is False
        saved = client.post(path, headers=_headers(case, csrf), json=_http_body(case))
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["dependency_generation"] == 1
        assert body["links"][0]["status"] == "invalidated"
        assert body["questions"][0]["status"] == "invalidated"
        assert body["proof_obligations"][0]["status"] == "invalidated"
        assert body["proof"] is False
        replay = client.post(path, headers=_headers(case, csrf), json=_http_body(case))
        assert replay.status_code == 200
        assert replay.json()["replayed"] is True
        assert replay.json()["dependency_generation"] == 1
        crossed = client.post(
            f"/api/graphs/{world.second.case_id}/legal-dependency/refresh",
            headers=_headers(case, csrf),
            json=_http_body(case, operation_id="cross", case_id=world.second.case_id),
        )
        assert crossed.status_code == 403
        late = client.post(late_path, headers=_headers(case, csrf), json={
            "operation_id": "late-http",
            "case_id": case.case_id,
            "dependency_generation": 1,
            "actor_principal_id": world.owner.principal_id,
            "case_revision": case.revision,
            "consent_generation": 1,
            "grant_revision": 0,
            "legal_source_hashes": ["hash-current"],
            "links": [{"id": "link-http", "text": "late http support", "content_hash": "hash-current"}],
        })
        assert late.status_code == 200, late.text
        assert late.json()["applied"] is True
        assert late.json()["dependency_generation"] == 1
        stale_late = client.post(late_path, headers=_headers(case, csrf), json={
            "operation_id": "late-stale",
            "case_id": case.case_id,
            "dependency_generation": 0,
            "links": [{"id": "link-stale", "text": "restore old link", "content_hash": "hash-current"}],
        })
        assert stale_late.status_code == 409
        assert stale_late.json()["error"] == "stale_dependency_generation"
        assert stale_late.json()["applied"] is False
        csrf = _login(client, "synthetic-lawyer-credential")
        lawyer = client.post(path, headers=_headers(case, csrf, grant.revision), json=_http_body(case, operation_id="lawyer"))
        assert lawyer.status_code == 403
        csrf = _login(client, "synthetic-stranger-credential")
        stranger = client.post(path, headers=_headers(case, csrf), json=_http_body(case, operation_id="stranger"))
        assert stranger.status_code == 403
        assert "hash-current" not in stranger.text or stranger.json().get("applied") is not True
    ledger = world.mediator.intake_case_file["legal_graph_refresh"]
    assert ledger["dependency_generation"] == 1
    assert {item["id"]: item["status"] for item in ledger["records"]["links"]}["link-old"] == "invalidated"
    assert "link-stale" not in {item["id"] for item in ledger["records"]["links"]}
    assert "link-http" in {item["id"] for item in ledger["records"]["links"]}
