"""Authorized case creation and selection through the composed HTTP catalog.

Synthetic principals only. Newly created cases stay owner-only; a lawyer grant
from the action authorizer does not open sealed revisions without a key grant.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import (
    SESSION_COOKIE,
    BrowserSessionConfiguration,
    BrowserSessionService,
    PrincipalStoreCredentialAdapter,
)
from applications.case_access import ASSIGNED_LAWYER_ACTIONS, CaseActionAuthorizer
from applications.case_api import CATALOG_LIMITATIONS, CaseCatalog
from applications.case_directory import MEMBERSHIP_OWNER_ONLY, CaseDirectory
from applications.case_routes import compose_case_routes
from applications.principal_store import PrincipalStore

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
OWNER_CREDENTIAL = "synthetic-password"
STRANGER_CREDENTIAL = "synthetic-access-token"
LAWYER_CREDENTIAL = "synthetic-auth-token"


def _world(tmp_path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=case_key, key_id="case-key")
    owner = principals.register_from_request({})
    stranger = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            OWNER_CREDENTIAL: owner.principal_id,
            STRANGER_CREDENTIAL: stranger.principal_id,
            LAWYER_CREDENTIAL: lawyer.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=60,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    catalog = CaseCatalog(cases, authorizer, key=case_key, key_id="case-key")
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_catalog=catalog,
                        include_workspace=False, include_review=False, include_document=False)
    return SimpleNamespace(owner=owner, stranger=stranger, lawyer=lawyer, cases=cases,
                           authorizer=authorizer, catalog=catalog, app=app)


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200
    assert client.cookies.get(SESSION_COOKIE)
    return response.json()["csrf_token"]


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def test_owner_creates_lists_and_reads_only_owner_cases(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        anonymous = client.get("/api/cases")
        assert anonymous.status_code == 401
        token = _login(client, OWNER_CREDENTIAL)
        rejected = client.post("/api/cases", headers=_csrf(token), json={"collaborators": [world.lawyer.principal_id]})
        assert rejected.status_code == 403
        assert rejected.json()["error"] == "collaboration_not_available"
        assert world.cases.list_cases(actor_principal_id=world.owner.principal_id) == ()
        minted = client.post("/api/cases", headers=_csrf(token), json={"label": "synthetic-one", "user_id": world.owner.principal_id, "case_id": world.owner.principal_id})
        assert minted.status_code == 201
        body = minted.json()
        assert body["membership"] == MEMBERSHIP_OWNER_ONLY
        assert body["case_id"] != world.owner.principal_id
        assert body["tenant_id"] != world.owner.principal_id
        assert body["actor_is_encrypted_owner"] is False
        assert body["canonical_owner_principal_id"] == body["tenant_id"]
        assert body["unresolved_gaps"] == []
        assert body["directory_revision"] == 1
        assert "key_grants_are_not_issued_here" in body["limitations"]
        listed = client.get("/api/cases")
        assert listed.status_code == 200
        assert [item["case_id"] for item in listed.json()["cases"]] == [body["case_id"]]
        read = client.get(f"/api/cases/{body['case_id']}")
        assert read.status_code == 200
        assert read.json()["envelope_sha256"] == body["envelope_sha256"]
        assert read.json()["label"] == "synthetic-one"


def test_unknown_and_foreign_identifiers_do_not_enumerate_other_users(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        created = owner_client.post("/api/cases", headers=_csrf(owner_token), json={"label": "owned"})
        assert created.status_code == 201
        case = created.json()
    with TestClient(world.app, base_url="https://testserver") as client:
        token = _login(client, STRANGER_CREDENTIAL)
        own = client.post("/api/cases", headers=_csrf(token), json={"label": "other"})
        assert own.status_code == 201
        listed = client.get("/api/cases")
        assert listed.status_code == 200
        assert case["case_id"] not in listed.text
        assert world.owner.principal_id not in listed.text
        assert case["tenant_id"] not in listed.text
        unknown = client.get("/api/cases/does-not-exist")
        foreign = client.get(f"/api/cases/{case['case_id']}")
        assert unknown.status_code == foreign.status_code == 404
        assert unknown.json() == foreign.json() == {"error": "missing_case"}
        assert world.owner.principal_id not in foreign.text
        assert case["tenant_id"] not in foreign.text
        probed = client.get(f"/api/cases/{case['case_id']}", params={
            "tenant_id": case["tenant_id"], "resource_id": case["resource_id"], "expected_revision": case["directory_revision"],
        })
        invented = client.get("/api/cases/does-not-exist", params={
            "tenant_id": "not-a-tenant", "resource_id": "not-a-resource", "expected_revision": 1,
        })
        assert probed.status_code == invented.status_code
        assert probed.json() == invented.json()
        assert world.owner.principal_id not in probed.text
        swapped = client.get("/api/cases", params={"user_id": world.owner.principal_id})
        assert swapped.status_code == 403
        assert case["case_id"] not in swapped.text
        selected = client.post(f"/api/cases/{case['case_id']}/select", headers=_csrf(token), json={})
        assert selected.status_code == 404
        assert selected.json() == {"error": "missing_case"}


def test_switching_cases_clears_transient_state_and_keeps_independent_revisions(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        token = _login(client, OWNER_CREDENTIAL)
        first = client.post("/api/cases", headers=_csrf(token), json={"label": "alpha"}).json()
        second = client.post("/api/cases", headers=_csrf(token), json={"label": "beta"}).json()
        assert first["tenant_id"] == second["tenant_id"]
        assert first["case_id"] != second["case_id"]
        assert first["envelope_sha256"] != second["envelope_sha256"]
        selected = client.post(f"/api/cases/{first['case_id']}/select", headers=_csrf(token), json={})
        assert selected.status_code == 200
        assert selected.json()["transient_cleared"] is True
        draft = client.post(f"/api/cases/{first['case_id']}/transient", headers=_csrf(token), json={"draft": "unsaved-note"})
        assert draft.status_code == 200
        assert draft.json()["transient"]["draft"] == "unsaved-note"
        gaps = client.post(f"/api/cases/{first['case_id']}/gaps", headers=_csrf(token), json={
            "unresolved_gaps": ["gap-alpha"], "expected_content_revision": 1,
        })
        assert gaps.status_code == 200
        alpha_sha = gaps.json()["envelope_sha256"]
        alpha_bytes = world.catalog.sealed_envelope(world.owner.principal_id, first["case_id"])
        stale = client.post(f"/api/cases/{first['case_id']}/gaps", headers=_csrf(token), json={
            "unresolved_gaps": ["replaced"], "expected_content_revision": 1,
        })
        assert stale.status_code == 409
        assert world.catalog.sealed_envelope(world.owner.principal_id, first["case_id"]) == alpha_bytes
        switched = client.post(f"/api/cases/{second['case_id']}/select", headers=_csrf(token), json={})
        assert switched.status_code == 200
        assert switched.json()["transient_cleared"] is True
        assert switched.json()["transient"]["draft"] == ""
        assert switched.json()["unresolved_gaps"] == []
        assert switched.json()["directory_revision"] == 1
        beta_gaps = client.post(f"/api/cases/{second['case_id']}/gaps", headers=_csrf(token), json={
            "unresolved_gaps": ["gap-beta"], "expected_content_revision": 1,
        })
        assert beta_gaps.status_code == 200
        assert world.catalog.sealed_envelope(world.owner.principal_id, first["case_id"]) == alpha_bytes
        again = client.get(f"/api/cases/{first['case_id']}")
        assert again.json()["unresolved_gaps"] == ["gap-alpha"]
        assert again.json()["envelope_sha256"] == alpha_sha
        assert again.json()["encrypted_content_revision"] == 2
        beta = client.get(f"/api/cases/{second['case_id']}")
        assert beta.json()["unresolved_gaps"] == ["gap-beta"]
        assert beta.json()["envelope_sha256"] != alpha_sha
        session = client.get("/api/cases/session")
        assert session.json()["selected_case_id"] == second["case_id"]
        assert session.json()["transient"]["draft"] == ""
        assert {item["case_id"] for item in session.json()["cases"]} == {first["case_id"], second["case_id"]}


def test_explicit_membership_does_not_bypass_missing_key_grants(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as owner_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        created = owner_client.post("/api/cases", headers=_csrf(owner_token), json={}).json()
        owner_client.post(f"/api/cases/{created['case_id']}/select", headers=_csrf(owner_token), json={})
        owner_client.post(f"/api/cases/{created['case_id']}/gaps", headers=_csrf(owner_token), json={
            "unresolved_gaps": ["sealed-gap"], "expected_content_revision": 1,
        })
    grant = world.authorizer.grant_assigned_lawyer(
        owner_principal_id=world.owner.principal_id,
        lawyer_principal_id=world.lawyer.principal_id,
        case_id=created["case_id"],
        resource_id=created["resource_id"],
        tenant_id=created["tenant_id"],
        actions=set(ASSIGNED_LAWYER_ACTIONS),
        expected_case_revision=created["directory_revision"],
    )
    with TestClient(world.app, base_url="https://testserver") as client:
        token = _login(client, LAWYER_CREDENTIAL)
        listed = client.get("/api/cases")
        assert listed.status_code == 200
        assert listed.json()["cases"] == []
        assert "sealed-gap" not in listed.text
        denied = client.get(f"/api/cases/{created['case_id']}")
        unknown = client.get("/api/cases/unknown-case")
        assert denied.status_code == unknown.status_code
        assert denied.json() == unknown.json()
        opened = client.get(f"/api/cases/{created['case_id']}", params={
            "tenant_id": created["tenant_id"],
            "resource_id": created["resource_id"],
            "expected_revision": created["directory_revision"],
            "expected_membership_revision": grant.revision,
        })
        assert opened.status_code == 200
        body = opened.json()
        assert body["membership"] == "assigned-lawyer"
        assert body["plaintext_available"] is False
        assert body["key_grant"] == "required"
        assert "unresolved_gaps" not in body
        assert "sealed-gap" not in opened.text
        assert "envelope_sha256" not in body
        written = client.post(f"/api/cases/{created['case_id']}/gaps", headers=_csrf(token), json={
            "unresolved_gaps": ["lawyer-gap"], "expected_content_revision": 2,
            "tenant_id": created["tenant_id"], "resource_id": created["resource_id"],
            "expected_revision": created["directory_revision"],
            "expected_membership_revision": grant.revision,
        })
        assert written.status_code == 404
        assert written.json()["error"] == "missing_case"
    owner_view = world.catalog.read(world.owner.principal_id, created["case_id"])
    assert owner_view["unresolved_gaps"] == ["sealed-gap"]
    with pytest.raises(Exception):
        world.catalog.sealed_envelope(world.lawyer.principal_id, created["case_id"])


def test_cases_page_clears_transient_ui_and_states_owner_only_limits(tmp_path):
    world = _world(tmp_path)
    with TestClient(world.app, base_url="https://testserver") as client:
        response = client.get("/cases")
    assert response.status_code == 200
    page = response.text
    assert "clearTransientState" in page
    assert "owner-only" in page
    assert "key grants" in page
    assert "other participants" in page
    assert "invite" not in page
    assert "WebSocket" not in page
    assert world.owner.principal_id not in page
    assert set(CATALOG_LIMITATIONS)
