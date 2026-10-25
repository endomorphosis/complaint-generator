"""Case processing consent is explicit, persisted, and revocable.

Local private is the default. Grok egress exists only after the owner
authorizes one case and one purpose. Lawyer membership, an admin role,
development Grok authorization, and message receipt do not create that consent.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from applications.browser_sessions import (
    SESSION_COOKIE,
    BrowserSessionConfiguration,
    BrowserSessionService,
    PrincipalStoreCredentialAdapter,
)
from applications.case_access import CaseActionAuthorizer
from applications.case_api import CaseCatalog
from applications.case_consent_api import CaseConsentService
from applications.case_directory import CaseDirectory
from applications.case_routes import compose_case_routes
from applications.principal_store import PrincipalStore

OWNER_CREDENTIAL = "synthetic-password"
LAWYER_CREDENTIAL = "synthetic-auth-token"
ADMIN_CREDENTIAL = "synthetic-access-token"
ROOT = Path(__file__).resolve().parents[1]


def _world(tmp_path):
    now = {"t": 1_700_000_100}

    def clock():
        now["t"] += 1
        return now["t"]

    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    case_key = os.urandom(32)
    cases = CaseDirectory(tmp_path / "cases", key=case_key, key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    admin = principals.install_server_role(role="operational_admin")
    sessions = BrowserSessionService(BrowserSessionConfiguration(
        adapter=PrincipalStoreCredentialAdapter(principals, {
            OWNER_CREDENTIAL: owner.principal_id,
            LAWYER_CREDENTIAL: lawyer.principal_id,
            ADMIN_CREDENTIAL: admin.principal_id,
        }),
        signing_key=os.urandom(32),
        ttl_seconds=120,
    ))
    authorizer = CaseActionAuthorizer(principals, cases)
    catalog = CaseCatalog(cases, authorizer, key=case_key, key_id="case-key")
    consent = CaseConsentService(
        tmp_path / "consent", cases=cases, key=os.urandom(32), key_id="consent-key", clock=clock,
    )
    app = FastAPI()
    compose_case_routes(
        app, authorizer=authorizer, browser_sessions=sessions, case_catalog=catalog,
        case_consent=consent, include_workspace=False, include_review=False, include_document=False,
    )
    return app, owner, lawyer, admin, consent


def _login(client, credential):
    response = client.post("/api/complaint-workspace/auth/login", json={"credential": credential})
    assert response.status_code == 200, response.text
    assert client.cookies.get(SESSION_COOKIE)
    return response.json()["csrf_token"]


def _csrf(token):
    return {"x-csrf-token": token, "content-type": "application/json"}


def _create_case(client, token, label="owned"):
    created = client.post("/api/cases", headers=_csrf(token), json={"label": label})
    assert created.status_code == 201, created.text
    return created.json()


def _decision(payload, purpose):
    return next(item for item in payload["decisions"] if item["purpose"] == purpose)


def test_owner_persists_displays_and_revokes_purpose_consent(tmp_path):
    app, _owner, _lawyer, _admin, consent = _world(tmp_path)
    page = (ROOT / "templates" / "workspace.html").read_text(encoding="utf-8")
    assert 'id="case-processing-consent"' in page
    assert "Local private: this purpose never calls a remote provider." in page
    assert "Explicitly authorized Grok processing: grok_cli / grok-4.7 for this case and purpose." in page
    assert "Revoked: Grok processing for this purpose is not authorized." in page
    assert "development Grok authorization" in page
    assert "/processing-consent" in page

    with TestClient(app, base_url="https://testserver") as client:
        token = _login(client, OWNER_CREDENTIAL)
        case = _create_case(client, token)
        other = _create_case(client, token, label="other")
        initial = client.get(f"/api/cases/{case['case_id']}/processing-consent")
        assert initial.status_code == 200, initial.text
        body = initial.json()
        assert body["egress_authorized"] is False
        assert body["implications"] == {
            "lawyer_membership": False,
            "admin_role": False,
            "development_grok_authorization": False,
            "message_receipt": False,
        }
        assert _decision(body, "extract_facts")["display"].startswith("Local private")
        assert _decision(body, "propose_questions")["egress_authorized"] is False

        refused = client.post(
            f"/api/cases/{case['case_id']}/processing-consent",
            headers=_csrf(token),
            json={"purpose": "extract_facts", "mode": "grok_cloud", "expected_generation": 0},
        )
        assert refused.status_code == 403
        assert refused.json()["error"] == "explicit_case_purpose_required"

        authorized = client.post(
            f"/api/cases/{case['case_id']}/processing-consent",
            headers=_csrf(token),
            json={
                "purpose": "extract_facts",
                "mode": "grok_cloud",
                "explicit_case_purpose": True,
                "expected_generation": 0,
            },
        )
        assert authorized.status_code == 200, authorized.text
        saved = authorized.json()
        assert saved["generation"] == 1
        assert saved["egress_authorized"] is True
        chosen = _decision(saved, "extract_facts")
        assert chosen["egress_authorized"] is True
        assert chosen["provider"] == "grok_cli"
        assert chosen["model"] == "grok-4.7"
        assert chosen["display"].startswith("Explicitly authorized Grok")
        assert _decision(saved, "propose_questions")["egress_authorized"] is False
        assert saved["operation_consent"]["grants"] == [{
            "purpose": "extract_facts",
            "provider_kind": "grok_inference",
            "provider": "grok_cli",
            "model": "grok-4.7",
            "data_class": "raw_intake",
            "explicit": True,
            "tools": False,
        }]

        reloaded = consent.read(saved["owner_principal_id"], case["case_id"])
        assert _decision(reloaded, "extract_facts")["egress_authorized"] is True
        isolated = client.get(f"/api/cases/{other['case_id']}/processing-consent")
        assert isolated.status_code == 200
        assert isolated.json()["egress_authorized"] is False

        stale = client.post(
            f"/api/cases/{case['case_id']}/processing-consent/revoke",
            headers=_csrf(token),
            json={"purpose": "extract_facts", "expected_generation": 0},
        )
        assert stale.status_code == 409
        assert stale.json()["error"] == "revision_conflict"

        revoked = client.post(
            f"/api/cases/{case['case_id']}/processing-consent/revoke",
            headers=_csrf(token),
            json={"purpose": "extract_facts", "expected_generation": 1},
        )
        assert revoked.status_code == 200, revoked.text
        after = revoked.json()
        assert after["generation"] == 2
        assert after["egress_authorized"] is False
        assert after["operation_consent"]["revoked"] is True
        shown = _decision(after, "extract_facts")
        assert shown["revoked"] is True
        assert shown["display"].startswith("Revoked")
        assert consent.read(after["owner_principal_id"], case["case_id"])["egress_authorized"] is False


def test_membership_admin_development_and_messages_do_not_imply_egress(tmp_path):
    app, owner, lawyer, admin, consent = _world(tmp_path)
    with TestClient(app, base_url="https://testserver") as owner_client, TestClient(app, base_url="https://testserver") as lawyer_client, TestClient(app, base_url="https://testserver") as admin_client:
        owner_token = _login(owner_client, OWNER_CREDENTIAL)
        lawyer_token = _login(lawyer_client, LAWYER_CREDENTIAL)
        admin_token = _login(admin_client, ADMIN_CREDENTIAL)
        case = _create_case(owner_client, owner_token)
        path = f"/api/cases/{case['case_id']}/processing-consent"

        anonymous = TestClient(app, base_url="https://testserver")
        assert anonymous.get(path).status_code == 401

        for client, token in ((lawyer_client, lawyer_token), (admin_client, admin_token)):
            denied = client.get(path)
            assert denied.status_code == 404, denied.text
            assert denied.json()["error"] == "missing_case"
            posted = client.post(path, headers=_csrf(token), json={
                "purpose": "extract_facts",
                "mode": "grok_cloud",
                "explicit_case_purpose": True,
                "expected_generation": 0,
            })
            assert posted.status_code == 404
            assert posted.json()["error"] == "missing_case"

        for implied in (
            {"lawyer_membership": True},
            {"admin_role": True},
            {"development_grok_authorization": True},
            {"message_receipt": True},
        ):
            rejected = owner_client.post(path, headers=_csrf(owner_token), json={
                "purpose": "extract_facts",
                "mode": "grok_cloud",
                "explicit_case_purpose": True,
                "expected_generation": 0,
                **implied,
            })
            assert rejected.status_code == 403, rejected.text
            assert rejected.json()["error"] == "consent_not_implied"

        current = owner_client.get(path)
        assert current.status_code == 200
        assert current.json()["egress_authorized"] is False
        assert consent.read(owner.principal_id, case["case_id"])["egress_authorized"] is False
        assert lawyer.principal_id != owner.principal_id
        assert admin.principal_id != owner.principal_id
