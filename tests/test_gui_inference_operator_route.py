"""Trusted route selection and real concurrent ASGI consent boundaries."""
from __future__ import annotations

import os
import threading
import time

import pytest
from fastapi.testclient import TestClient

from applications.gui_inference_route import NATIVE_OBSERVED_GROK47, resolve_gui_inference_route
from applications.server import SERVER
from applications.case_consent_api import CaseConsentService
from applications.launcher import create_uvicorn_app_for_type, launch_application
from applications.review_api import create_review_api_app
from applications.review_ui import create_review_dashboard_app, create_review_surface_app
from mediator.hook_runtime import native_gui_inference_transport
from tests.test_cimp_gui_14 import _composed_case_world, _composed_headers, _composed_login
from tests.test_cimp_gui_34 import NARRATIVE, FRAGMENT, choose, _install_gui_observed_boundary

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def test_finite_operator_selector_has_no_environment_or_callback_claim_fallback(monkeypatch):
    monkeypatch.setenv("GUI_INFERENCE_ROUTE", NATIVE_OBSERVED_GROK47)
    monkeypatch.setenv("GROK_AUTHORIZED", "1")
    assert resolve_gui_inference_route() is None
    assert resolve_gui_inference_route(NATIVE_OBSERVED_GROK47) is native_gui_inference_transport
    def synthetic(_call):
        return {"live_model_identity_verified": True, "observed_provider": "grok_cli"}
    assert resolve_gui_inference_route(synthetic_transport=synthetic) is synthetic
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_gui_inference_route(NATIVE_OBSERVED_GROK47, synthetic_transport=synthetic)
    with pytest.raises(ValueError, match="requires_explicit"):
        resolve_gui_inference_route(synthetic_transport=native_gui_inference_transport)


@pytest.mark.parametrize("route", [True, "grok_cli", "os.system", " native_observed_grok47", {}, []])
def test_unknown_or_untyped_operator_routes_refuse(route):
    with pytest.raises(ValueError, match="unknown_gui_inference_route"):
        resolve_gui_inference_route(route)


@pytest.mark.parametrize("factory", [
    lambda: SERVER(None, gui_inference_route=NATIVE_OBSERVED_GROK47).app,
    lambda: create_review_api_app(None, gui_inference_route=NATIVE_OBSERVED_GROK47),
    lambda: create_review_surface_app(None, gui_inference_route=NATIVE_OBSERVED_GROK47),
    lambda: create_review_dashboard_app(gui_inference_route=NATIVE_OBSERVED_GROK47),
])
def test_operator_selection_without_case_owners_does_not_authorize_requests(factory):
    app = factory()
    assert app.state.gui_inference_route == NATIVE_OBSERVED_GROK47
    assert app.state.gui_inference_transport is native_gui_inference_transport
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/api/complaint-workspace/inference/dispatch",
            json={"purpose": "extract_facts", "inputs": {"source_text": "private", "target_ref": "caller"}})
        assert response.status_code in {401, 503}


@pytest.mark.parametrize("kind", ["review-api", "review-dashboard", "review-surface"])
def test_actual_launcher_application_config_forwards_finite_route(kind, monkeypatch):
    observed = {}
    def capture(app, configuration):
        observed.update(app=app, configuration=configuration)
    monkeypatch.setattr("applications.launcher._run_uvicorn_app", capture)
    config = {"gui_inference_route": NATIVE_OBSERVED_GROK47, "host": "127.0.0.1", "port": 12345}
    launch_application(kind, object(), config)
    assert observed["app"].state.gui_inference_transport is native_gui_inference_transport
    assert observed["configuration"] is config


def test_server_launcher_forwards_config_without_starting_listener(monkeypatch):
    seen = {}
    def capture(self, **options):
        seen.update(app=self.app, options=options)
    monkeypatch.setattr(SERVER, "run", capture)
    launch_application("server", object(), {"gui_inference_route": NATIVE_OBSERVED_GROK47, "port": 12345})
    assert seen["app"].state.gui_inference_transport is native_gui_inference_transport
    assert seen["options"]["port"] == 12345


@pytest.fixture
def native_world(tmp_path):
    w = _composed_case_world(tmp_path)
    w.seen = []
    w.consent = CaseConsentService(tmp_path / "consent", cases=w.cases, key=os.urandom(32),
        key_id="consent-key", clock=lambda: 1700000100)
    w.app = SERVER(None, authorizer=w.authorizer, browser_sessions=w.sessions,
        case_handlers=w.handlers, case_consent=w.consent,
        gui_inference_route=NATIVE_OBSERVED_GROK47).app
    assert w.app.state.gui_inference_transport is native_gui_inference_transport
    with TestClient(w.app, base_url="https://testserver") as client:
        w.client = client
        w.csrf = _composed_login(client)
        w.headers = _composed_headers(w.case, w.csrf)
        started = client.post("/api/complaint-workspace/intake-chat", headers=w.headers,
            json={"message": NARRATIVE, "interview_action": "start"})
        assert started.status_code == 200, started.text
        w.target = started.json()["graph_targets"]["target_id"]
        yield w


@pytest.mark.parametrize("frontdoor", ["http", "mcp", "rpc"])
@pytest.mark.parametrize("boundary", ["revoke", "logout"])
def test_real_http_boundary_completes_while_native_observed_dispatch_is_pending(native_world, monkeypatch, frontdoor, boundary):
    w = native_world
    started, release = threading.Event(), threading.Event()
    def wait_for_boundary():
        started.set()
        if not release.wait(8):
            raise TimeoutError("synthetic observed boundary release deadline")
    observed = _install_gui_observed_boundary(w, monkeypatch, action=wait_for_boundary)
    choose(w)
    outcome = {}
    request = {"purpose": "extract_facts", "inputs": {"source_text": FRAGMENT, "target_ref": w.target},
               "timeout_seconds": 5.0}
    def dispatch():
        try:
            if frontdoor == "http":
                response = w.client.post("/api/complaint-workspace/inference/dispatch", headers=w.headers, json=request)
            elif frontdoor == "mcp":
                response = w.client.post("/api/complaint-workspace/mcp/call", headers=w.headers,
                    json={"tool_name": "complaint.dispatch_bounded_gui_inference", "arguments": request})
            else:
                response = w.client.post("/api/complaint-workspace/mcp/rpc", headers=w.headers,
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                        "name": "complaint.dispatch_bounded_gui_inference", "arguments": request}})
            outcome.update(status=response.status_code, body=response.json())
        except BaseException as exc:
            outcome["error"] = type(exc).__name__
    worker = threading.Thread(target=dispatch, daemon=True)
    worker.start()
    try:
        assert started.wait(5), outcome
        before = time.monotonic()
        if boundary == "revoke":
            revoked = choose(w, grok=False)
            decision = next(item for item in revoked["decisions"] if item["purpose"] == "extract_facts")
            assert decision["egress_authorized"] is False
        else:
            logout = w.client.post("/api/complaint-workspace/auth/logout", headers={"x-csrf-token": w.csrf})
            assert logout.status_code == 200
        assert time.monotonic() - before < 2.0
        assert worker.is_alive(), "provider wait must remain pending until the real boundary completes"
    finally:
        release.set()
        worker.join(10)
    assert not worker.is_alive() and "error" not in outcome
    assert outcome["status"] == 200
    body = outcome["body"]
    if frontdoor == "rpc":
        body = body["result"]["structuredContent"]
    assert body["accepted"] is False and body["output"] is None, body
    assert body["provider_invoked"] is True and body["model_dispatched"] is True
    assert body["live_model_identity_verified"] is False
    assert len(observed) == 1 and not w.seen
    assert not getattr(w.services[w.case.case_id], "_gui_server_holds", {})
