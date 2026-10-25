"""GUI inference stays on the pinned Grok hook route.

The transport is synthetic and observed. A matching router, provider, and
model name does not qualify a live model. Late admission re-reads consent,
the resource grant, and source revisions.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from applications.complaint_workspace import ComplaintWorkspaceService
from integrations.ipfs_datasets.llm import clear_remote_invocation_bindings, pinned_hook_inference_route
from mediator.hook_runtime import clear_gui_inference_holds


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
_DEADLINE = datetime(2026, 12, 1, tzinfo=timezone.utc)
_USER = "synthetic-gui-owner"
_SOURCE = "a" * 64
_NARRATIVE = "SYNTHETIC_COMPLAINT_NARRATIVE_NOT_FOR_EGRESS"


def setup_function() -> None:
    clear_remote_invocation_bindings()
    clear_gui_inference_holds()


def _legal() -> dict:
    return {
        "status": "explicit",
        "jurisdiction": "synthetic",
        "jurisdiction_explicit": True,
        "context_revision": 1,
        "applicable_law_date": {"role": "applicable_law_date", "raw_text": "", "start_date": "", "end_date": "", "is_uncertain": True},
        "event_date": {"role": "event_date", "raw_text": "2024-01-02", "start_date": "2024-01-02", "end_date": "2024-01-02", "is_uncertain": False},
        "filing_reference_date": {"role": "filing_reference_date", "raw_text": "", "start_date": "", "end_date": "", "is_uncertain": True},
        "corpus_retrieval_date": {"role": "corpus_retrieval_date", "raw_text": "", "start_date": "", "end_date": "", "is_uncertain": True},
    }


def _bindings() -> list[dict]:
    return [{"source_id": "src-gui-1", "content_hash": _SOURCE, "excerpt": "do-not-retain"}]


def _inputs() -> dict:
    return {"source_text": "notice of the act", "target_ref": "target.gui-1"}


def _grant() -> dict:
    return {"grant_id": "grant-gui-1", "generation": 2, "revoked": False}


def _service(tmp_path) -> ComplaintWorkspaceService:
    service = ComplaintWorkspaceService(tmp_path / "workspace")
    created = service.initialize_private_keys(protection="passphrase", passphrase="synthetic-gui-passphrase")
    assert created.get("unlocked") is True or created.get("status") in {"available", "ready"}
    service.ensure_private_case_key(_USER, _USER)
    return service


def _authorize(service: ComplaintWorkspaceService, **overrides) -> dict:
    payload = {
        "grant": _grant(),
        "source_bindings": _bindings(),
        "graph_revision": "gr-gui-1",
        "session_revision": 3,
        "session_id": "session-gui-1",
    }
    payload.update(overrides)
    return service.record_gui_inference_authority(_USER, **payload)


def _transport(body: dict):
    seen: list[dict] = []

    def transport(call: dict) -> dict:
        seen.append(call)
        return {
            "status": "available",
            "output": body,
            "observed_router": "synthetic-transport",
            "observed_provider": "grok_cli",
            "observed_model": "grok-4.7",
            "observed_build": "grok-4.7-build",
            "evidence_class": "native_final_end_model_usage",
            "live_model_identity_verified": True,
        }

    return seen, transport


def _facts() -> dict:
    return {"facts": [{"field": "act", "value": "notice", "target_ref": "target.gui-1"}]}


def _dispatch(service, transport, **overrides):
    payload = {
        "purpose": "extract_facts",
        "inputs": _inputs(),
        "legal_context": _legal(),
        "deadline": _DEADLINE,
        "now": _NOW,
        "model_transport": transport,
        "complaint_text": _NARRATIVE,
    }
    payload.update(overrides)
    return service.dispatch_bounded_gui_inference(_USER, **payload)


def test_positive_route_shape_and_late_admission(tmp_path):
    service = _service(tmp_path)
    service.set_privacy_policy(_USER, "grok")
    recorded = _authorize(service)
    assert recorded["recorded"] is True
    assert recorded["source_references"] == [{"source_id": "src-gui-1", "content_hash": _SOURCE}]
    assert recorded["code"] == "recorded"
    assert "do-not-retain" not in str(recorded["source_references"])
    seen, transport = _transport(_facts())
    dispatched = _dispatch(service, transport)
    route = pinned_hook_inference_route()
    assert dispatched["status"] == "held"
    assert dispatched["output"] is None
    assert dispatched["accepted"] is False
    assert dispatched["model_dispatched"] is True
    assert dispatched["live_model_identity_verified"] is False
    assert dispatched["identity"]["live_model_identity_verified"] is False
    assert dispatched["identity"]["transport_kind"] == "synthetic"
    assert dispatched["requirements_satisfied"] is False
    assert dispatched["development_grok_authorization_ignored"] is True
    assert len(seen) == 1
    call = seen[0]
    assert call["router"] == route["router"] == route["inference_owner"]
    assert call["provider"] == "grok_cli"
    assert call["model"] == "grok-4.7"
    assert call["allow_local_fallback"] is False
    assert call["allow_cross_provider_fallback"] is False
    assert call["tools_allowed"] is False
    assert call["may_mark_requirements_satisfied"] is False
    assert set(call["inputs"]) == {"source_text", "target_ref"}
    assert call["source_references"] == [{"source_id": "src-gui-1", "content_hash": _SOURCE}]
    assert _NARRATIVE not in str(call)
    admitted = service.admit_bounded_gui_inference(_USER, invocation_id=dispatched["invocation_id"])
    assert admitted["accepted"] is True
    assert admitted["output"] == _facts()
    assert admitted["live_model_identity_verified"] is False
    assert admitted["consent_revalidated"] is True
    assert admitted["grant_revalidated"] is True
    assert admitted["source_revision_revalidated"] is True
    assert admitted["requirements_satisfied"] is False
    again = service.admit_bounded_gui_inference(_USER, invocation_id=dispatched["invocation_id"])
    assert again["accepted"] is False
    assert again["code"] == "invocation_missing"


def test_local_private_fallback_and_extra_inputs_do_not_dispatch(tmp_path):
    service = _service(tmp_path)
    _authorize(service)
    seen, transport = _transport(_facts())
    local = _dispatch(service, transport)
    assert seen == []
    assert local["model_dispatched"] is False
    assert local["code"] == "local_private"
    assert local["live_model_identity_verified"] is False

    service.set_privacy_policy(_USER, "grok")
    seen, transport = _transport(_facts())
    fallback = _dispatch(service, transport, allow_local_fallback=True)
    assert seen == []
    assert fallback["code"] == "unpinned_route"
    assert fallback["model_dispatched"] is False

    seen, transport = _transport(_facts())
    wrong_model = _dispatch(service, transport, requested_model="grok-3")
    assert seen == []
    assert wrong_model["code"] == "unpinned_route"

    seen, transport = _transport(_facts())
    extra = _dispatch(service, transport, inputs={**_inputs(), "unrelated_note": "extra-field"})
    assert seen == []
    assert extra["code"] == "input_bounds"
    assert extra["model_dispatched"] is False

    seen, transport = _transport(_facts())
    leaked = _dispatch(service, transport, inputs={"source_text": _NARRATIVE, "target_ref": "target.gui-1"})
    assert seen == []
    assert leaked["code"] == "query_not_minimized"

    revoked = _authorize(service, grant={"grant_id": "grant-gui-1", "generation": 2, "revoked": True})
    assert revoked["recorded"] is True
    seen, transport = _transport(_facts())
    refused = _dispatch(service, transport)
    assert seen == []
    assert refused["code"] == "grant_revoked"


def test_late_admission_rechecks_consent_grant_and_source_revision(tmp_path):
    service = _service(tmp_path)
    service.set_privacy_policy(_USER, "grok")
    _authorize(service)
    seen, transport = _transport(_facts())
    dispatched = _dispatch(service, transport)
    assert dispatched["status"] == "held"
    assert len(seen) == 1
    service.set_privacy_policy(_USER, "local")
    revoked = service.admit_bounded_gui_inference(_USER, invocation_id=dispatched["invocation_id"])
    assert revoked["accepted"] is False
    assert revoked["code"] == "consent_revoked"
    assert revoked["output"] is None
    assert revoked["consent_revalidated"] is True
    assert revoked["live_model_identity_verified"] is False

    service.set_privacy_policy(_USER, "grok")
    _authorize(service)
    seen, transport = _transport(_facts())
    dispatched = _dispatch(service, transport)
    _authorize(service, source_bindings=[{"source_id": "src-gui-1", "content_hash": "b" * 64}])
    stale_source = service.admit_bounded_gui_inference(_USER, invocation_id=dispatched["invocation_id"])
    assert stale_source["accepted"] is False
    assert stale_source["code"] == "stale_source_revision"
    assert stale_source["source_revision_revalidated"] is True

    _authorize(service)
    seen, transport = _transport(_facts())
    dispatched = _dispatch(service, transport)
    _authorize(service, grant={"grant_id": "grant-gui-1", "generation": 3, "revoked": False})
    stale_grant = service.admit_bounded_gui_inference(_USER, invocation_id=dispatched["invocation_id"])
    assert stale_grant["accepted"] is False
    assert stale_grant["code"] == "stale_grant"
    assert stale_grant["grant_revalidated"] is True

    _authorize(service)
    seen, transport = _transport(_facts())
    dispatched = _dispatch(service, transport)
    _authorize(service, graph_revision="gr-gui-2")
    stale_graph = service.admit_bounded_gui_inference(_USER, invocation_id=dispatched["invocation_id"])
    assert stale_graph["accepted"] is False
    assert stale_graph["code"] == "stale_revision"
    assert stale_graph["output"] is None
