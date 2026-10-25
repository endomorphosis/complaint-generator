"""Law-derived dependency graph projection.

Positive cases project requirements, burdens, exceptions, and applicability
from admitted authorities, and show factual support, contradiction, and
missing-evidence links beside those rules. Negative cases keep user
narratives, model text, and unadmitted records from rewriting the rules, and
deny an ungranted or cross-case read.
"""
from __future__ import annotations

import json
import os
import subprocess
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
from applications.graph_api import (
    LegalDependencyGraphError,
    project_law_derived_dependency_graph,
)
from applications.principal_store import PrincipalStore
from tests.test_cimp_gui_26 import PASSAGE, _acquire, _review, review_versioned_authority

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ROOT = Path(__file__).resolve().parents[1]
BURDEN = "under color of any statute"
NARRATIVE = "The user narrative rewrites the statute to require personal malice."
MODEL_TEXT = "The model says the element is actually a negligence standard."
SUPPORT_FACT = "A witness states the officer acted under a state schedule."
CONTRADICTION = "A second account states the actor was off duty and not using state authority."


class _Mediator:
    def __init__(self) -> None:
        self.intake_case_file = {"legal_context": {"jurisdiction": "US"}, "legal_authorities": []}
        self.admissions = []
        self.owner_status = "admitted"
        self.dependency_graph = None

    def build_legal_acquisition_request(self, case_file, **kwargs):
        return {"ready": True, "request": {"program": {"query_text": "42 U.S.C. 1983"}}}

    def legal_authority_search(self):
        raise AssertionError("graph projection must not search")

    def admit_acquired_authorities(self, acquisition, claims, intake_case_file, user_id=None):
        self.admissions.append({"explicit_review": acquisition.get("explicit_review"), "user_id": user_id})
        return {"status": self.owner_status, "proof": False}


class _SearchMediator(_Mediator):
    def __init__(self) -> None:
        super().__init__()
        from tests.test_cimp_gui_26 import _Search

        self.search = _Search()
        self.legal_authority_search = self.search


class _Authority:
    actor_principal_id = "actor-1"
    case_id = "case-1"

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


def _admitted_case_file():
    mediator = _SearchMediator()
    _acquire(mediator)
    review_versioned_authority(
        mediator, SimpleNamespace(case_id="case-1"), _Authority(), _review(),
        membership="owner", canonical_owner_principal_id="tenant-1",
    )
    review_versioned_authority(
        mediator, SimpleNamespace(case_id="case-1"), _Authority(), _review(
            operation_id="review-mismatch", jurisdiction="OR"),
        membership="owner", canonical_owner_principal_id="tenant-1",
    )
    case_file = mediator.intake_case_file
    stored = case_file["legal_source_passage_index"]["hash-current"]
    stored["burden"] = BURDEN
    admitted = next(item for item in case_file["legal_authority_admissions"] if item.get("admitted_law") is True)
    admitted["burden"] = "personal malice"
    admitted["requirement"] = NARRATIVE
    case_file["user_narrative"] = NARRATIVE
    case_file["model_output"] = MODEL_TEXT
    mediator.dependency_graph = {
        "nodes": [
            {"id": "fact-support", "node_type": "fact", "description": SUPPORT_FACT, "source_id": "fact-src-support", "origin": "user"},
            {"id": "fact-contradict", "node_type": "fact", "description": CONTRADICTION, "source_id": "fact-src-contradict", "origin": "user"},
            {"id": "model-fact", "node_type": "fact", "description": MODEL_TEXT, "source_id": "fact-src-model", "origin": "model"},
            {
                "id": "rewritten-rule",
                "node_type": "legal_element",
                "description": "User says the statute actually requires malice.",
                "content_hash": "hash-current",
                "origin": "user",
            },
            {
                "id": "invented-rule",
                "node_type": "legal_element",
                "description": "A snippet invented a strict-liability element.",
                "content_hash": "hash-invented",
                "origin": "llm",
            },
        ],
        "edges": [
            {"dependency_type": "supports", "source_id": "fact-support", "target_id": "rewritten-rule"},
            {"dependency_type": "contradicts", "source_id": "fact-contradict", "target_id": "rewritten-rule"},
            {"dependency_type": "supports", "source_id": "model-fact", "target_id": "rewritten-rule"},
            {"dependency_type": "supports", "source_id": "invented-rule", "target_id": "fact-support"},
        ],
    }
    return mediator


def test_projection_keeps_admitted_rules_apart_from_narratives():
    mediator = _admitted_case_file()
    payload = project_law_derived_dependency_graph(
        mediator.intake_case_file, dependency_graph=mediator.dependency_graph, case_id="case-1",
    )
    assert payload["task_id"] == "CIMP-GUI-27"
    assert payload["proof"] is False
    assert payload["legal_sufficiency"] is False
    assert payload["rules_rewritten_by_user_or_model"] is False
    assert payload["user_facts_are_not_law"] is True
    assert payload["admitted_count"] == 1
    rule = payload["requirements"][0]
    assert rule["requirement"] == PASSAGE
    assert rule["burden"] == BURDEN
    assert rule["burden_status"] == "admitted_passage"
    assert rule["exceptions"] == ["qualified immunity is not decided here"]
    assert rule["applicability"] == "applicable"
    assert rule["jurisdiction"] == "US"
    assert rule["effective_date"] == "1996-10-19"
    assert rule["authority_identity"] == "42 U.S.C. § 1983"
    assert rule["source"] == "admitted_authority"
    assert rule["admitted_law"] is True
    assert NARRATIVE not in rule["requirement"]
    assert MODEL_TEXT not in rule["requirement"]
    assert rule["burden"] != "personal malice"
    kinds = {(item["link_kind"], item["fact_source_id"], item["fact_text"]) for item in payload["factual_links"]}
    assert ("supports", "fact-src-support", SUPPORT_FACT) in kinds
    assert ("contradicts", "fact-src-contradict", CONTRADICTION) in kinds
    assert ("supports", "fact-src-model", MODEL_TEXT) in kinds
    assert all(item["rewrites_legal_rule"] is False for item in payload["factual_links"])
    assert all(item["link_kind"] != "missing_evidence" or item["reason"] != "no_supporting_fact" for item in payload["factual_links"])
    reasons = {item["reason"] for item in payload["rejected_narratives"]}
    assert "user_or_model_text_not_law" in reasons
    assert "graph_text_does_not_rewrite_admitted_rule" in reasons
    assert "unadmitted_dependency" in reasons
    assert "source_mismatch" in reasons
    joined_rules = " ".join(item["requirement"] + item["burden"] + item["applicability"] for item in payload["requirements"])
    assert "strict-liability" not in joined_rules
    assert "personal malice" not in joined_rules
    assert MODEL_TEXT not in joined_rules

    bare = {"legal_authority_admissions": [], "user_narrative": NARRATIVE}
    empty = project_law_derived_dependency_graph(bare, case_id="case-1")
    assert empty["requirements"] == []
    assert empty["research_gap"] == "no_admitted_authority"
    assert empty["factual_links"] == []
    assert empty["rejected_narratives"][0]["text"] == NARRATIVE
    with pytest.raises(LegalDependencyGraphError) as missing:
        project_law_derived_dependency_graph(None)
    assert missing.value.code == "legal_dependency_unavailable"


def _world(tmp_path):
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
    mediator = _admitted_case_file()
    handlers = CaseHandlerRegistry()
    handlers.bind(case, mediator=mediator, workspace_service=SimpleNamespace(case_id=case.case_id),
        authorize_delegated=lambda decision: decision.membership == "assigned-lawyer")
    handlers.bind(second, mediator=_Mediator(), workspace_service=SimpleNamespace(case_id=second.case_id),
        authorize_delegated=lambda _decision: False)
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers,
        include_workspace=False, include_review=False, include_document=False)
    return SimpleNamespace(owner=owner, lawyer=lawyer, stranger=stranger, case=case, second=second,
        app=app, mediator=mediator, authorizer=authorizer)


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


def test_http_projects_for_owner_and_lawyer_and_refuses_rewrite(tmp_path):
    world = _world(tmp_path)
    case = world.case
    path = f"/api/graphs/{case.case_id}/legal-dependency"
    grant = world.authorizer.grant_assigned_lawyer(
        owner_principal_id=world.owner.principal_id,
        lawyer_principal_id=world.lawyer.principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions={"case.read"},
        expected_case_revision=case.revision,
    )
    before = list(world.mediator.intake_case_file["legal_authority_admissions"])
    with TestClient(world.app, base_url="https://testserver") as client:
        assert client.get(path, headers=_headers(case)).status_code == 401
        csrf = _login(client, "synthetic-owner-credential")
        allowed = client.get(path, headers=_headers(case, csrf))
        assert allowed.status_code == 200, allowed.text
        body = allowed.json()
        assert body["requirements"][0]["requirement"] == PASSAGE
        assert body["requirements"][0]["burden"] == BURDEN
        assert body["requirements"][0]["applicability"] == "applicable"
        assert body["rules_rewritten_by_user_or_model"] is False
        crossed = client.get(path, headers=_headers(case, csrf), params={"case_id": world.second.case_id})
        assert crossed.status_code == 403
        assert crossed.json()["error"] == "cross_case_id"
        other = client.get(f"/api/graphs/{world.second.case_id}/legal-dependency", headers=_headers(case, csrf))
        assert other.status_code == 403
        rewrite = client.post(path, headers=_headers(case, csrf), json={
            "requirement": NARRATIVE,
            "user_narrative": NARRATIVE,
            "model_output": MODEL_TEXT,
        })
        assert rewrite.status_code == 400
        assert rewrite.json()["error"] == "narrative_not_law"
        assert rewrite.json()["rules_rewritten_by_user_or_model"] is False
        csrf = _login(client, "synthetic-lawyer-credential")
        lawyer = client.get(path, headers=_headers(case, csrf, grant.revision))
        assert lawyer.status_code == 200, lawyer.text
        assert lawyer.json()["requirements"][0]["exceptions"] == ["qualified immunity is not decided here"]
        csrf = _login(client, "synthetic-stranger-credential")
        stranger = client.get(path, headers=_headers(case, csrf))
        assert stranger.status_code == 403
        assert stranger.json()["error"]
        assert PASSAGE not in stranger.text
    assert world.mediator.intake_case_file["legal_authority_admissions"] == before
    assert world.mediator.intake_case_file["user_narrative"] == NARRATIVE


def test_view_renders_rules_and_facts_in_separate_sections():
    mediator = _admitted_case_file()
    payload = project_law_derived_dependency_graph(
        mediator.intake_case_file, dependency_graph=mediator.dependency_graph, case_id="case-1",
    )
    script = r"""
const view = require(process.argv[1]);
const payload = JSON.parse(process.argv[2]);
const html = view.renderLawDerivedDependencyGraph({ innerHTML: "" }, payload);
const legal = html.split('data-role="factual-links"')[0];
const facts = html.split('data-role="factual-links"')[1].split('data-role="rejected-narratives"')[0];
if (!legal.includes('data-role="legal-rule"')) process.exit(2);
if (!legal.includes(payload.requirements[0].requirement)) process.exit(3);
if (!legal.includes(payload.requirements[0].burden)) process.exit(4);
if (!legal.includes(payload.requirements[0].applicability)) process.exit(5);
if (legal.includes(payload.factual_links.find((item) => item.link_kind === "supports").fact_text)) process.exit(6);
if (!facts.includes('data-link-kind="supports"')) process.exit(7);
if (!facts.includes('data-link-kind="contradicts"')) process.exit(8);
if (!facts.includes('data-rewrites-legal-rule="false"')) process.exit(9);
if (html.includes("WebSocket") || html.includes("EventSource")) process.exit(10);
process.stdout.write("ok");
"""
    completed = subprocess.run(
        ["node", "-e", script, str(ROOT / "static" / "complaint_graph_view.js"), json.dumps(payload)],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert completed.stdout == "ok"
