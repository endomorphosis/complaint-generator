"""Show source-bound proof traces and unavailable states in the workspace.

Positive cases record executed, degraded, and not-executed rows with engine
versions and counterexamples, then render them through the real workspace DOM.
Missing prover, timeout, and source drift stay visible. None of those become a
green checkmark or legal sufficiency.
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
from applications.case_directory import CaseDirectory
from applications.case_routes import PROTECTED_PREFIXES, CaseHandlerRegistry, compose_case_routes
from applications.legal_analysis_api import (
    PROOF_TRACE_ROUTE,
    LegalAnalysisError,
    project_proof_traces,
    record_case_proof_traces,
)
from applications.principal_store import PrincipalStore

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

SOURCE = "synthetic-source-identity-31"


def _row(**overrides):
    payload = {
        "obligation_id": "obligation-executed",
        "statement": "The synthetic source requires approval before retention.",
        "source_span": "source:0-48",
        "source_identity": SOURCE,
        "proof_status": "executed",
        "engine_name": "synthetic-lean",
        "engine_version": "0.0-test",
        "legal_sufficiency": True,
        "green_checkmark": True,
    }
    payload.update(overrides)
    return payload


def _body(obligations, **overrides):
    payload = {
        "request_id": "cimp-gui-31-synthetic",
        "source_identity": SOURCE,
        "expected_source_identity": SOURCE,
        "legal_sufficiency": True,
        "obligations": obligations,
    }
    payload.update(overrides)
    return payload


def _assert_not_sufficient(payload):
    assert payload["legal_sufficiency"] is False
    assert payload["proof"] is False
    assert payload["executed_proof"] is False
    assert payload["governing_legal_authority"] is False
    assert payload["admitted_law"] is False
    for row in payload["obligations"]:
        assert row["legal_sufficiency"] is False
        assert row["executed_proof"] is False
        assert row["source_bound"] is True


def test_recorded_trace_keeps_executed_degraded_and_not_executed_distinct():
    mediator = SimpleNamespace(intake_case_file={
        "canonical_legal_ir_attachment": {
            "source_identity": SOURCE,
            "typed_obligations": [{
                "obligation_id": "obligation-from-ir",
                "statement": "Canonical source obligation remains unbound to a prover.",
                "source_span": "source:80-120",
            }],
        },
    })
    payload = record_case_proof_traces(mediator, _body([
        _row(),
        _row(obligation_id="obligation-degraded", proof_status="degraded", engine_name="synthetic-z3", engine_version="4.13-test", counterexample="model: approval bit is false"),
        _row(obligation_id="obligation-open", proof_status="not_executed", engine_name="", engine_version=""),
    ]))
    assert payload["task_id"] == "CIMP-GUI-31"
    assert payload["status"] == "visible"
    assert payload["supplied_legal_sufficiency_ignored"] is True
    _assert_not_sufficient(payload)
    by_id = {row["obligation_id"]: row for row in payload["obligations"]}
    assert by_id["obligation-executed"]["proof_status"] == "executed"
    assert by_id["obligation-executed"]["green_checkmark"] is True
    assert by_id["obligation-degraded"]["proof_status"] == "degraded"
    assert by_id["obligation-degraded"]["green_checkmark"] is False
    assert by_id["obligation-degraded"]["counterexample"] == "model: approval bit is false"
    assert by_id["obligation-open"]["proof_status"] == "not_executed"
    assert by_id["obligation-open"]["green_checkmark"] is False
    assert by_id["obligation-from-ir"]["proof_status"] == "not_executed"
    assert by_id["obligation-from-ir"]["green_checkmark"] is False
    assert payload["engine_versions"] == [
        {"name": "synthetic-lean", "version": "0.0-test"},
        {"name": "synthetic-z3", "version": "4.13-test"},
    ]
    assert payload["counterexamples"][0]["green_checkmark"] is False
    projected = project_proof_traces(mediator.intake_case_file)
    assert projected["obligations"][0]["proof_status"] == "executed"
    assert projected["legal_sufficiency"] is False
    empty = project_proof_traces({})
    assert empty["status"] == "empty"
    assert empty["legal_sufficiency"] is False
    assert "not a successful proof" in empty["limitations"][0]


def test_missing_prover_timeout_and_source_drift_stay_visible():
    mediator = SimpleNamespace(intake_case_file={})
    payload = record_case_proof_traces(mediator, _body([
        _row(obligation_id="obligation-missing", proof_status="executed", engine_name="", engine_version="", prover_missing=True),
        _row(obligation_id="obligation-timeout", proof_status="executed", timed_out=True),
        _row(obligation_id="obligation-drift", proof_status="executed", source_identity="other-source"),
        _row(obligation_id="obligation-counterexample", proof_status="executed", counterexample="trace: goal unsat under the bound"),
    ]))
    by_id = {row["obligation_id"]: row for row in payload["obligations"]}
    assert by_id["obligation-missing"]["proof_status"] == "missing_prover"
    assert by_id["obligation-timeout"]["proof_status"] == "timeout"
    assert by_id["obligation-drift"]["proof_status"] == "source_drift"
    assert by_id["obligation-counterexample"]["proof_status"] == "executed"
    for row in by_id.values():
        if row["obligation_id"] != "obligation-counterexample":
            assert row["green_checkmark"] is False
    assert by_id["obligation-counterexample"]["green_checkmark"] is False
    assert payload["source_drift"] is True
    _assert_not_sufficient(payload)
    drifted = record_case_proof_traces(SimpleNamespace(intake_case_file={}), _body(
        [_row(obligation_id="obligation-envelope")],
        expected_source_identity="expected-other-source",
    ))
    assert drifted["obligations"][0]["proof_status"] == "source_drift"
    assert drifted["obligations"][0]["green_checkmark"] is False
    assert drifted["legal_sufficiency"] is False
    with pytest.raises(LegalAnalysisError) as missing:
        record_case_proof_traces(SimpleNamespace(), _body([_row()]))
    assert missing.value.code == "legal_analysis_unavailable"


class _Mediator:
    def __init__(self) -> None:
        self.intake_case_file = {}


def _world(tmp_path):
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
    mediator = _Mediator()
    handlers = CaseHandlerRegistry()
    handlers.bind(case, mediator=mediator, workspace_service=SimpleNamespace(case_id=case.case_id),
        authorize_delegated=lambda _decision: False)
    handlers.bind(second, mediator=_Mediator(), workspace_service=SimpleNamespace(case_id=second.case_id),
        authorize_delegated=lambda _decision: False)
    app = FastAPI()
    compose_case_routes(app, authorizer=authorizer, browser_sessions=sessions, case_handlers=handlers,
        include_workspace=False, include_review=False, include_document=False)
    return SimpleNamespace(owner=owner, case=case, second=second, app=app, mediator=mediator)


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


def test_proof_trace_route_stays_on_the_protected_legal_analysis_prefix():
    assert any(PROOF_TRACE_ROUTE.startswith(prefix + "/") for prefix in PROTECTED_PREFIXES)


def test_http_projects_unavailable_states_without_authority(tmp_path):
    world = _world(tmp_path)
    path = f"/api/legal-analysis/{world.case.case_id}/proof-traces"
    body = _body([
        _row(),
        _row(obligation_id="obligation-missing", proof_status="missing_prover", engine_name="", engine_version=""),
        _row(obligation_id="obligation-timeout", proof_status="timeout"),
        _row(obligation_id="obligation-drift", proof_status="source_drift", source_identity="drifted-source"),
    ])
    with TestClient(world.app, base_url="https://testserver") as client:
        assert client.get(path, headers=_headers(world.case)).status_code == 401
        login = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-owner-credential"})
        assert login.status_code == 200, login.text
        csrf = login.json()["csrf_token"]
        empty = client.get(path, headers=_headers(world.case, csrf))
        assert empty.status_code == 200, empty.text
        assert empty.json()["status"] == "empty"
        assert empty.json()["legal_sufficiency"] is False
        recorded = client.post(path, headers=_headers(world.case, csrf), json=body)
        assert recorded.status_code == 200, recorded.text
        payload = recorded.json()
        assert payload["case_id"] == world.case.case_id
        assert payload["legal_sufficiency"] is False
        statuses = {row["obligation_id"]: row for row in payload["obligations"]}
        assert statuses["obligation-executed"]["green_checkmark"] is True
        assert statuses["obligation-missing"]["proof_status"] == "missing_prover"
        assert statuses["obligation-timeout"]["proof_status"] == "timeout"
        assert statuses["obligation-drift"]["proof_status"] == "source_drift"
        assert statuses["obligation-missing"]["green_checkmark"] is False
        assert statuses["obligation-timeout"]["green_checkmark"] is False
        assert statuses["obligation-drift"]["green_checkmark"] is False
        stored = client.get(path, headers=_headers(world.case, csrf))
        assert stored.json()["source_drift"] is True
        assert stored.json()["engine_versions"][0]["version"] == "0.0-test"
        crossed = client.post(path, headers=_headers(world.case, csrf), params={"case_id": world.second.case_id}, json=body)
        assert crossed.status_code == 403
        assert crossed.json()["error"] == "cross_case_id"
        assert crossed.json()["executed_proof"] is False
        assert crossed.json()["proof"] is False
        stranger = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-stranger-credential"})
        denied = client.get(path, headers=_headers(world.case, stranger.json()["csrf_token"]))
        assert denied.status_code == 403



def test_workspace_script_renders_traces_and_keeps_unavailable_states_visible(tmp_path):
    import json
    import subprocess
    from pathlib import Path

    from applications.site_ui import attach_core_site_ui_routes

    html = Path("templates/workspace.html").read_text(encoding="utf-8")
    section = html.split('id="proof-trace-panel"', 1)[1].split('id="legal-effective-context"', 1)[0]
    for element_id in (
        "proof-trace-case-id",
        "proof-trace-summary",
        "proof-trace-list",
        "proof-trace-counterexamples",
        "proof-trace-engines",
        "proof-trace-refresh",
    ):
        assert f'id="{element_id}"' in section
    assert "not legal sufficiency" in section
    assert 'data-legal-sufficiency="false"' in section
    start = html.index("let proofTraceRequestEpoch = 0;")
    end = html.index("document.getElementById('proof-trace-refresh')", start)
    script = html[start:end]
    world = _world(tmp_path)
    attach_core_site_ui_routes(world.app)
    with TestClient(world.app, base_url="https://testserver") as client:
        page = client.get("/workspace")
        assert page.status_code == 200
        assert 'id="proof-trace-panel"' in page.text
        assert "missing prover, a timeout, and source drift" in page.text
    payload = record_case_proof_traces(SimpleNamespace(intake_case_file={
        "canonical_legal_ir_attachment": {"source_identity": SOURCE, "typed_obligations": [{
            "obligation_id": "obligation-from-ir",
            "statement": "Canonical source obligation remains unbound to a prover.",
            "source_span": "source:80-120",
        }]},
    }), _body([
        _row(statement="Approval is required.", source_span="source:0-12"),
        _row(obligation_id="obligation-missing", statement="No prover is installed.", source_span="source:13-24", proof_status="missing_prover", engine_name="", engine_version=""),
        _row(obligation_id="obligation-timeout", statement="The prover exceeded its budget.", source_span="source:25-36", proof_status="timeout"),
        _row(obligation_id="obligation-drift", statement="The source no longer matches.", source_span="source:37-48", source_identity="drifted-source"),
        _row(obligation_id="obligation-degraded", statement="A degraded engine answered.", source_span="source:49-60", proof_status="degraded", engine_name="synthetic-z3", engine_version="4.13-test", counterexample="model: approval bit is false"),
    ]))
    payload["case_id"] = "case-1"
    program = r"""
const payload = JSON.parse(process.argv[1]);
const forged = JSON.parse(process.argv[2]);
const elements = {};
function make(id) {
  return {id, textContent:'', className:'', dataset:{}, value:'', children:[],
    replaceChildren() { this.children = []; },
    appendChild(child) { this.children.push(child); return child; },
    addEventListener() {}};
}
['proof-trace-summary','proof-trace-list','proof-trace-counterexamples','proof-trace-engines','proof-trace-case-id','proof-trace-refresh'].forEach(id => { elements[id] = make(id); });
elements['proof-trace-case-id'].value = 'case-1';
const document = {getElementById(id) { return elements[id]; }, createElement() { return make('created'); }};
let workspacePrivacyInactive = false;
let workspacePrivacyEpoch = 1;
const client = {_privacyEpoch: 1, activePrincipalId: 'principal', caseContext: {case_id: 'case-1'}};
""" + script + r"""
const capture = {caseId:'case-1', requestEpoch: proofTraceRequestEpoch, privacyEpoch: workspacePrivacyEpoch,
  clientEpoch: client._privacyEpoch, actor: client.activePrincipalId, caseContext: JSON.stringify(client.caseContext)};
renderProofTraces(forged, capture);
const forgedRows = elements['proof-trace-list'].children.length;
renderProofTraces(payload, capture);
const rows = elements['proof-trace-list'].children.map(row => ({
  id: row.dataset.obligationId, status: row.dataset.proofStatus, green: row.dataset.greenCheckmark,
  sufficiency: row.dataset.legalSufficiency, text: row.textContent}));
const summary = {text: elements['proof-trace-summary'].textContent, sufficiency: elements['proof-trace-summary'].dataset.legalSufficiency,
  verification: elements['proof-trace-summary'].dataset.verification, drift: elements['proof-trace-summary'].dataset.sourceDrift};
const counters = elements['proof-trace-counterexamples'].children.map(node => ({text: node.textContent, green: node.dataset.greenCheckmark}));
const engines = elements['proof-trace-engines'].textContent;
clearProofTraceView();
const cleared = {rows: elements['proof-trace-list'].children.length, verification: elements['proof-trace-summary'].dataset.verification,
  text: elements['proof-trace-summary'].textContent};
process.stdout.write(JSON.stringify({forgedRows, rows, summary, counters, engines, cleared}));
"""
    forged = dict(payload)
    forged["legal_sufficiency"] = True
    completed = subprocess.run(["node", "-e", program, json.dumps(payload), json.dumps(forged)], check=True, capture_output=True, text=True)
    rendered = json.loads(completed.stdout)
    assert rendered["forgedRows"] == 0
    by_id = {row["id"]: row for row in rendered["rows"]}
    assert by_id["obligation-executed"]["status"] == "executed"
    assert by_id["obligation-executed"]["green"] == "true"
    assert by_id["obligation-executed"]["sufficiency"] == "false"
    assert "synthetic-lean 0.0-test" in by_id["obligation-executed"]["text"]
    for obligation_id, status in (
        ("obligation-missing", "missing_prover"),
        ("obligation-timeout", "timeout"),
        ("obligation-drift", "source_drift"),
        ("obligation-degraded", "degraded"),
        ("obligation-from-ir", "not_executed"),
    ):
        assert by_id[obligation_id]["status"] == status
        assert by_id[obligation_id]["green"] == "false"
        assert by_id[obligation_id]["sufficiency"] == "false"
        assert "✓" not in by_id[obligation_id]["text"]
        assert "✔" not in by_id[obligation_id]["text"]
    assert rendered["summary"]["sufficiency"] == "false"
    assert "not legal sufficiency" in rendered["summary"]["text"]
    assert "missing_prover" in rendered["summary"]["text"]
    assert "timeout" in rendered["summary"]["text"]
    assert "source_drift" in rendered["summary"]["text"]
    assert rendered["summary"]["drift"] == "true"
    assert rendered["counters"][0]["green"] == "false"
    assert "model: approval bit is false" in rendered["counters"][0]["text"]
    assert "synthetic-z3 4.13-test" in rendered["engines"]
    assert rendered["cleared"]["rows"] == 0
    assert rendered["cleared"]["verification"] == "unknown"
    assert "not a successful proof" in rendered["cleared"]["text"]
