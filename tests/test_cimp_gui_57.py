"""Offline and unavailable GUI outcomes stay explicit.

Absent models, law, provers, and storage, plus rate limits, network denial,
missing keys, corrupt snapshots, and revoked grants are required cases.
Pending research and factual gaps stay visible. Durability and proof stay
unverified unless the owning check actually succeeded. An unavailable
capability is not a successful end-to-end route.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from applications.case_storage_api import CaseStorageError
from integrations.private_storage import (
    PrivateArtifactBinding,
    seal_private_artifact,
    verify_ciphertext_durability,
)
from applications.legal_analysis_api import project_proof_traces, record_case_proof_traces
from applications.legal_research_api import LegalResearchError, acquire_bounded_legal_sources
from applications.case_review import project_workflow_stage
from mediator.hook_runtime import admit_gui_bounded_inference, dispatch_gui_bounded_inference
from tests.gui_collaboration_fixtures import (
    CASE,
    GRAPH,
    OWNER,
    authenticated_storage_app,
    inference_bundle,
    proof_body,
    proof_mediator,
    research_authority,
    research_body,
    research_mediator,
    reset_inference_bindings,
    storage_body,
    storage_world,
    workflow_case,
)
from tests.gui_native_browser import probe_inherited_network_denial

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _dispatch(bundle, *, transport=None, session_id: str):
    return dispatch_gui_bounded_inference(
        policy_record=bundle["policy_record"],
        grant=bundle["grant"],
        purpose_id="extract_facts",
        inputs=bundle["inputs"],
        source_bindings=bundle["bindings"],
        legal_context=bundle["legal_context"],
        owner_id=OWNER,
        case_id=CASE,
        session_id=session_id,
        session_revision=1,
        graph_revision=GRAPH,
        deadline=bundle["deadline"],
        now=bundle["now"],
        privacy_context=bundle["privacy_context"],
        model_transport=transport,
        allow_local_fallback=False,
        allow_cross_provider_fallback=False,
        operation="refresh_grounding",
    )


def _assert_not_route(result: dict) -> None:
    assert result["accepted"] is False
    assert result["requirements_satisfied"] is False
    assert result["requirements_satisfied_by_model"] is False
    assert result["live_model_identity_verified"] is False
    assert result.get("status") != "available"


def test_absent_model_rate_limit_network_denial_and_revoked_grant_are_not_routes():
    reset_inference_bindings()
    absent = _dispatch(inference_bundle(session_id="session-absent"), transport=None, session_id="session-absent")
    _assert_not_route(absent)
    assert absent["status"] == "unavailable"
    assert absent["code"] == "unavailable"
    assert absent["router_calls"]

    limited = _dispatch(
        inference_bundle(session_id="session-rate"),
        transport=lambda _call: {"status": "rate_limited"},
        session_id="session-rate",
    )
    _assert_not_route(limited)
    assert limited["code"] == "rate_limited"
    assert limited["status"] == "unavailable"

    denied = _dispatch(
        inference_bundle(session_id="session-net"),
        transport=lambda _call: {"status": "network_denied"},
        session_id="session-net",
    )
    _assert_not_route(denied)
    assert denied["code"] == "network_denied"
    fence = probe_inherited_network_denial()
    assert isinstance(fence, dict)
    assert fence.get("af_unix_only") is True or denied["accepted"] is False

    revoked_bundle = inference_bundle(revoked=True, session_id="session-revoked")
    revoked = _dispatch(revoked_bundle, transport=lambda _call: {"status": "available", "output": {"facts": []}}, session_id="session-revoked")
    _assert_not_route(revoked)
    assert revoked["code"] == "grant_revoked"
    assert revoked["router_calls"] == []


def test_held_model_text_is_not_an_end_to_end_success_and_revocation_drops_it():
    reset_inference_bindings()
    bundle = inference_bundle(session_id="session-hold")

    def transport(_call):
        return {"status": "available", "output": {"facts": [{"field": "act", "value": "synthetic act", "target_ref": "entity-57"}]}}

    held = _dispatch(bundle, transport=transport, session_id="session-hold")
    assert held["status"] == "held"
    assert held["code"] == "awaiting_late_admission"
    assert held["accepted"] is False
    assert held["output"] is None
    assert held["requirements_satisfied"] is False
    assert "provider_output_is_not_verified_legal_support" in held["limitations"]

    admitted = admit_gui_bounded_inference(
        invocation_id=held["invocation_id"],
        policy_record=bundle["policy_record"],
        grant=bundle["grant"],
        source_bindings=bundle["bindings"],
        owner_id=OWNER,
        case_id=CASE,
        graph_revision=GRAPH,
        session_revision=1,
    )
    assert admitted["accepted"] is True
    assert admitted["requirements_satisfied"] is False
    assert admitted["unverified_legal_support"] is True
    assert admitted["live_model_identity_verified"] is False
    assert admitted["output"]["facts"][0]["field"] == "act"

    again = inference_bundle(session_id="session-hold-revoke")
    second = _dispatch(again, transport=transport, session_id="session-hold-revoke")
    assert second["status"] == "held"
    revoked_grant = dict(again["grant"])
    revoked_grant["revoked"] = True
    dropped = admit_gui_bounded_inference(
        invocation_id=second["invocation_id"],
        policy_record=again["policy_record"],
        grant=revoked_grant,
        source_bindings=again["bindings"],
        owner_id=OWNER,
        case_id=CASE,
        graph_revision=GRAPH,
        session_revision=1,
    )
    assert dropped["accepted"] is False
    assert dropped["code"] == "grant_revoked"
    assert dropped["output"] is None
    assert dropped["requirements_satisfied"] is False


def test_absent_law_keeps_research_gaps_and_absent_hook_is_unavailable():
    missing = acquire_bounded_legal_sources(
        research_mediator(absent_law=True),
        object(),
        research_authority(),
        research_body(),
    )
    assert missing["admitted_law"] is False
    assert missing["proof"] is False
    assert missing["legal_sufficiency"] is False
    assert missing["status"] == "unavailable"
    assert missing["research_gap_count"] >= 1
    assert missing["context_required"]["selection_status"] == "pending"
    assert "law_corpus_absent" in missing["context_required"]["reason_codes"]
    reasons = {item["reason"] for item in missing["source_version_receipts"] if item["kind"] == "research_gap"}
    assert "missing_archive" in reasons
    assert "model_text_not_law" in reasons or "model_text" in reasons
    assert all(item["admitted_law"] is False and item["proof"] is False for item in missing["source_version_receipts"])

    with pytest.raises(LegalResearchError) as absent:
        acquire_bounded_legal_sources(research_mediator(absent_hook=True), object(), research_authority(), research_body())
    assert absent.value.code == "research_hook_unavailable"

    with pytest.raises(LegalResearchError) as revoked:
        acquire_bounded_legal_sources(
            research_mediator(absent_law=True),
            object(),
            research_authority(revoked=True),
            {**research_body(), "retrieval_mode": "live", "operation_id": "op-57-live"},
        )
    assert revoked.value.code == "purpose_consent_required"


def test_absent_prover_and_corrupt_snapshot_keep_factual_and_proof_gaps():
    mediator = proof_mediator()
    recorded = record_case_proof_traces(mediator, proof_body(status="missing_prover"))
    assert recorded["executed_proof"] is False
    assert recorded["proof"] is False
    assert recorded["legal_sufficiency"] is False
    assert recorded["admitted_law"] is False
    assert recorded["governing_legal_authority"] is False
    assert recorded["proof_status_counts"]["missing_prover"] == 1
    assert recorded["obligations"][0]["green_checkmark"] is False
    assert recorded["obligations"][0]["engine_name"] == ""
    assert recorded["supplied_legal_sufficiency_ignored"] is True
    projected = project_proof_traces(mediator.intake_case_file)
    assert projected["executed_proof"] is False

    claimed = record_case_proof_traces(proof_mediator(), proof_body(status="executed"))
    assert claimed["obligations"][0]["proof_status"] == "not_executed"
    assert claimed["obligations"][0]["reported_proof_status"] == "executed"
    assert claimed["executed_proof"] is False
    assert claimed["engine_versions"] == []

    pending = project_workflow_stage(workflow_case())
    assert pending["stage"] == "legal_unresolved"
    assert pending["domains"]["factual"]["settled"] is True
    assert pending["domains"]["legal"]["reason"] == "legal_not_admitted"
    assert pending["domains"]["proof"]["reason"] == "not_executed"
    assert pending["legal_sufficiency"] is False
    assert pending["readiness"]["ready_for_versioned_export"] is False

    corrupt = project_workflow_stage(workflow_case(corrupt_snapshot=True))
    assert corrupt["stage"] == "factual_unresolved"
    assert corrupt["domains"]["factual"]["reason"] == "factual_not_current"
    assert corrupt["domains"]["legal"]["governing_law"] is False
    assert corrupt["domains"]["legal"]["governing_law_claim_ignored"] is True
    assert corrupt["domains"]["proof"]["settled"] is False
    assert corrupt["exportable_drafts"] == []
    assert "ready" in corrupt["readiness"]["ignored_checkbox_keys"]


def test_missing_keys_corrupt_storage_and_absent_backend_stay_undurable(tmp_path):
    from tests.gui_collaboration_fixtures import Kit

    missing = storage_world(tmp_path / "missing-key", with_key=False)
    with pytest.raises(CaseStorageError) as missing_error:
        missing["service"].commit(missing["owner"].principal_id, storage_body(missing, idempotency_key="missing-key"))
    assert missing_error.value.code == "key_unavailable"
    assert missing_error.value.receipt["durable"] is False
    assert missing_error.value.receipt["storage_readiness"] == "unresolved"
    assert missing_error.value.receipt["actor_is_encrypted_owner"] is False

    offline = storage_world(tmp_path / "offline", Kit(offline=True))
    with pytest.raises(CaseStorageError) as offline_error:
        offline["service"].commit(offline["owner"].principal_id, storage_body(offline, idempotency_key="offline"))
    assert offline_error.value.code == "kit_manifest_failed"
    assert offline_error.value.receipt["storage_readiness"] == "unavailable"
    assert offline_error.value.receipt["durable"] is False
    assert offline_error.value.receipt["unresolved"] is True
    assert offline_error.value.receipt["replica_status"] == "unresolved"

    sealed = storage_world(tmp_path / "sealed", Kit())
    case = sealed["case"]
    session = sealed["service"]._sessions[sealed["owner"].principal_id]
    key_id = session.ensure_data_key(case.tenant_id, case.case_id)
    envelope = seal_private_artifact(
        b"synthetic-ciphertext-57",
        binding=PrivateArtifactBinding(
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            artifact_kind="case-ciphertext",
            revision="r57",
            principal_id=case.tenant_id,
        ),
        key=session.lookup_data_key(case.tenant_id, case.case_id, key_id),
        key_id=key_id,
    )
    corrupt = verify_ciphertext_durability(Kit(corrupt=True), envelope)
    assert corrupt["durable"] is False
    assert corrupt["readback_matched"] is False
    assert corrupt["code"] == "readback_mismatch"
    assert corrupt["pin_is_durable"] is False
    assert "verified_replica" not in corrupt["state_names"]
    matched = verify_ciphertext_durability(Kit(), envelope)
    assert matched["durable"] is True
    assert matched["readback_matched"] is True
    assert matched["local_commit_is_durable"] is False
    assert matched["queued_replication_is_durable"] is False

    healthy = storage_world(tmp_path / "healthy", Kit())
    app = authenticated_storage_app(healthy, mount_storage=False)
    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/api/complaint-workspace/auth/login", json={"credential": "synthetic-owner-57"})
        assert login.status_code == 200, login.text
        failed = client.post(
            "/api/cases/storage/durability",
            headers={"x-csrf-token": login.json()["csrf_token"]},
            json=storage_body(healthy, idempotency_key="absent-backend"),
        )
    assert failed.status_code >= 400
    body = failed.json()
    assert body["error"] == "storage_unavailable"
    assert body["durable"] is False
    assert body["storage_readiness"] == "unavailable"
    assert body["unresolved"] is True
    assert b"synthetic-ciphertext-57".decode() not in failed.text
    assert "synthetic-passphrase-57" not in failed.text
