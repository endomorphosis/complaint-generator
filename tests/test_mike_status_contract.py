from pathlib import Path

from complaint_generator.workspace import (
    build_mike_handoff as package_build_mike_handoff,
    sync_mike_final_draft as package_sync_mike_final_draft,
)
from applications.complaint_workspace import ComplaintWorkspaceService


def test_mike_status_contract_state_transitions_and_invariants(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "mike-contract-user"

    initial = service.get_mike_integration_status(user_id)
    assert initial["status_contract_version"] == "complaint-mike-status-v3"
    assert initial["workflow_state"]["key"] == "not_handed_off"
    assert initial["pending_sync"] is False
    assert isinstance(initial["citation_link_conflict_count"], int)
    assert isinstance(initial["citation_link_unknown_element_count"], int)
    assert initial["invariants"]["conflict_counters_non_null_numeric"] is True
    assert initial["invariants"]["recommended_action_present"] is True

    handoff = service.build_mike_handoff(user_id)
    after_handoff = service.get_mike_integration_status(user_id)
    assert handoff["handoff_id"] == after_handoff["latest_handoff_id"]
    assert after_handoff["workflow_state"]["key"] == "handoff_pending_sync"
    assert after_handoff["pending_sync"] is True
    assert after_handoff["latest_sync_handoff_id"] is None

    service.sync_mike_final_draft(
        user_id,
        body="Synced clean body",
        handoff_id=handoff["handoff_id"],
        citation_links=[{"citation_id": "cite-clean", "claim_element_id": "causation"}],
    )
    after_clean_sync = service.get_mike_integration_status(user_id)
    assert after_clean_sync["workflow_state"]["key"] == "synced_clean"
    assert after_clean_sync["pending_sync"] is False
    assert after_clean_sync["has_citation_link_conflicts"] is False
    assert "grounding_component" in after_clean_sync
    assert "proof_component" in after_clean_sync

    service.sync_mike_final_draft(
        user_id,
        body="Synced conflicting body",
        handoff_id=handoff["handoff_id"],
        citation_links=[
            {"citation_id": "cite-conflict", "claim_element_id": "causation"},
            {"citation_id": "cite-conflict", "claim_element_id": "harm"},
            {"citation_id": "cite-unknown", "claim_element_id": "unknown"},
        ],
    )
    after_conflict_sync = service.get_mike_integration_status(user_id)
    assert after_conflict_sync["workflow_state"]["key"] == "synced_with_conflicts"
    assert after_conflict_sync["has_citation_link_conflicts"] is True
    assert after_conflict_sync["conflict_component"]["conflict_count"] == 1
    assert after_conflict_sync["conflict_component"]["unknown_element_count"] == 1
    assert after_conflict_sync["invariants"]["pending_sync_implies_handoff"] is True
    assert after_conflict_sync["invariants"]["synced_handoff_never_pending"] is True
    assert "router_policy" in after_conflict_sync


def test_mike_ui_state_contract_keys_are_shared_across_surfaces():
    repo_root = Path(__file__).resolve().parent.parent
    workspace_content = (repo_root / "templates" / "workspace.html").read_text()
    document_content = (repo_root / "templates" / "document.html").read_text()
    dashboard_content = (repo_root / "applications" / "dashboard_ui.py").read_text()

    expected_keys = [
        "not_handed_off",
        "handoff_pending_sync",
        "synced_clean",
        "synced_with_conflicts",
    ]

    for key in expected_keys:
        assert key in workspace_content
        assert key in document_content
        assert key in dashboard_content


def test_mike_status_guardrail_copy_mentions_stale_or_missing_contract_across_surfaces():
    repo_root = Path(__file__).resolve().parent.parent
    workspace_content = (repo_root / "templates" / "workspace.html").read_text()
    document_content = (repo_root / "templates" / "document.html").read_text()
    dashboard_content = (repo_root / "applications" / "dashboard_ui.py").read_text()

    assert "status_contract_version" in workspace_content
    assert "status_contract_version" in document_content
    assert "status_contract_version" in dashboard_content
    assert "stale — refresh before export" in workspace_content
    assert "stale — refresh before export" in document_content
    assert "stale or missing contract metadata" in dashboard_content


def test_mike_sync_uses_latest_handoff_when_handoff_id_is_omitted(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "mike-handoff-fallback-user"
    handoff = service.build_mike_handoff(user_id)

    service.sync_mike_final_draft(
        user_id,
        body="Synced body without explicit handoff id",
    )

    status = service.get_mike_integration_status(user_id)
    assert status["latest_handoff_id"] == handoff["handoff_id"]
    assert status["latest_sync_handoff_id"] == handoff["handoff_id"]
    assert status["pending_sync"] is False


def test_mike_sync_preserves_intentional_body_whitespace(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "mike-whitespace-user"
    service.build_mike_handoff(user_id)
    original_body = "\n  Final draft body with intentional spacing  \n"

    service.sync_mike_final_draft(user_id, body=original_body)

    session = service.get_session(user_id)
    assert session["session"]["draft"]["body"] == original_body


def test_local_edits_after_mike_sync_mark_status_as_not_current(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "mike-local-edit-user"
    handoff = service.build_mike_handoff(user_id)
    service.sync_mike_final_draft(user_id, body="Synced Mike body", handoff_id=handoff["handoff_id"])

    synced_status = service.get_mike_integration_status(user_id)
    assert synced_status["workflow_state"]["key"] == "synced_clean"

    service.update_draft(user_id, body="Locally edited body after sync")

    diverged_status = service.get_mike_integration_status(user_id)
    assert diverged_status["has_mike_synced_draft"] is False
    assert diverged_status["workflow_state"]["key"] == "handoff_pending_sync"


def test_package_sync_wrapper_passes_structured_deltas_and_editor_metadata(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "mike-package-wrapper-user"
    package_build_mike_handoff(user_id, service=service)

    package_sync_mike_final_draft(
        user_id,
        body="Package wrapper synced body",
        structured_deltas=[{"op": "replace", "target": "paragraph-1", "before": "old", "after": "new"}],
        editor_metadata={"editor_user_id": "wrapper-editor", "channel": "package-api"},
        service=service,
    )

    session = service.get_session(user_id)
    sync_metadata = session["session"]["draft"]["sync_metadata"]
    assert sync_metadata["structured_deltas"][0]["target"] == "paragraph-1"
    assert sync_metadata["editor_metadata"]["editor_user_id"] == "wrapper-editor"


def test_mike_handoff_exposes_router_grounding_logic_and_submodule_contracts(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    service.submit_intake_answers(
        "handoff-contract-user",
        {
            "party_name": "Taylor Smith",
            "opposing_party": "Acme Logistics",
            "protected_activity": "Reported safety violations",
            "adverse_action": "Termination",
            "timeline": "Reported on April 2; terminated on April 5",
            "harm": "Lost wages",
        },
    )

    payload = service.build_mike_handoff("handoff-contract-user", grounding_mode="legal_corpus_only")
    handoff_payload = payload["handoff_payload"]

    assert payload["contract_versions"]["handoff"] == "complaint-mike-handoff-v3"
    assert handoff_payload["router_policy"]["provider_policy_source"] == "complaint_generator"
    assert handoff_payload["grounding_mode"] == "legal_corpus_only"
    assert handoff_payload["corpus_boundaries"]["strict_legal_containment"] is True
    assert "logic_handoff" in handoff_payload
    assert "submodule_inventory" in handoff_payload
    assert "compatibility_target_matrix" in handoff_payload
    assert len(str(handoff_payload["submodule_inventory"]["mike"]["commit"])) == 40
    assert len(str(handoff_payload["submodule_inventory"]["ipfs_datasets_py"]["commit"])) == 40
    assert len(str(handoff_payload["compatibility_target_matrix"]["submodule_shas"]["mike_commit"])) == 40
    assert len(str(handoff_payload["compatibility_target_matrix"]["submodule_shas"]["ipfs_datasets_py_commit"])) == 40
    assert "grounding_mode" in payload["sync_contract"]["optional_fields"]
    assert "assertion_annotations" in payload["sync_contract"]["optional_fields"]
    assert "authority_links" in payload["sync_contract"]["optional_fields"]


def test_mike_sync_persists_grounding_logic_and_release_gate_blockers(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "mike-grounding-user"
    service.submit_intake_answers(
        user_id,
        {
            "party_name": "Taylor Smith",
            "opposing_party": "Acme Logistics",
            "protected_activity": "Reported safety violations to HR",
            "adverse_action": "Was terminated three days later",
            "timeline": "Reported on April 2; terminated on April 5",
            "harm": "Lost wages and benefits",
        },
    )
    handoff = service.build_mike_handoff(user_id)

    sync_payload = service.sync_mike_final_draft(
        user_id,
        body="Defendant unlawfully retaliated against Plaintiff. Plaintiff seeks damages and fees.",
        handoff_id=handoff["handoff_id"],
        grounding_mode="legal_corpus_only",
        assertion_annotations=[
            {
                "assertion_id": "a-1",
                "text": "Defendant unlawfully retaliated against Plaintiff.",
                "assertion_type": "legal_conclusion",
                "grounded": False,
            },
            {
                "assertion_id": "a-2",
                "text": "Plaintiff seeks damages and fees.",
                "assertion_type": "requested_relief",
                "grounded": True,
                "authority_ids": ["relief-1"],
            },
        ],
        authority_links=[
            {
                "authority_id": "relief-1",
                "authority_type": "statute",
                "citation": "42 U.S.C. § 1988",
                "source": "federal_statutes",
                "assertion_ids": ["a-2"],
            }
        ],
        sync_provenance={"editor_version": "mike-test", "skill_asset_ids": ["complaint-grounding"]},
    )

    assert sync_payload["legal_corpus_review"]["has_blockers"] is True
    assert sync_payload["logic_review"]["has_blockers"] is True
    assert sync_payload["draft"]["sync_metadata"]["sync_provenance"]["editor_version"] == "mike-test"

    gate = service.get_client_release_gate(user_id)
    assert gate["complaint_output_release_gate"]["verdict"] == "blocked"
    assert "Legal-corpus-only mode" in gate["complaint_output_release_gate"]["reason"]
    assert "Formal proof coverage, contradiction, or chronology checks are still failing" in gate["complaint_output_release_gate"]["reason"]


def test_formal_diagnostics_include_mike_grounding_and_logic_snapshot(tmp_path, monkeypatch):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "mike-formal-diagnostics-user"
    handoff = service.build_mike_handoff(user_id)
    service.sync_mike_final_draft(
        user_id,
        body="Plaintiff reported discrimination on March 1. Defendant terminated Plaintiff on March 3.",
        handoff_id=handoff["handoff_id"],
    )

    monkeypatch.setattr(
        service,
        "analyze_complaint_output",
        lambda user_id: {
            "user_id": user_id,
            "ui_feedback": {
                "claim_type_alignment_score": 75,
                "filing_shape_score": 80,
                "release_gate": {"verdict": "warning"},
                "formal_diagnostics": {"release_gate_verdict": "warning"},
                "router_review": {"backend": {"provider": "template"}},
            },
            "packet_summary": {
                "has_draft": True,
                "draft_strategy": "template",
                "formal_defect_count": 0,
                "high_severity_issue_count": 0,
                "complaint_output_router_backend": {"provider": "template"},
            },
        },
    )
    monkeypatch.setattr(
        service,
        "build_export_artifact",
        lambda user_id, output_format="markdown": {
            "filename": "complaint.md",
            "media_type": "text/markdown",
            "body": b"COMPLAINT\n\n1. Plaintiff reported discrimination.\n2. Defendant terminated Plaintiff.\n",
        },
    )

    payload = service.get_formal_diagnostics(user_id)
    assert "mike_grounding" in payload
    assert "mike_logic" in payload
    assert "mike_sync_diagnostics" in payload


def test_mike_assertion_classifier_covers_relief_temporal_legal_and_factual_cases():
    assert ComplaintWorkspaceService._classify_mike_assertion_type("Plaintiff seeks injunctive relief and damages.") == "requested_relief"
    assert ComplaintWorkspaceService._classify_mike_assertion_type("On March 3, Defendant terminated Plaintiff after the complaint.") == "temporal_assertion"
    assert ComplaintWorkspaceService._classify_mike_assertion_type("Defendant unlawfully retaliated against Plaintiff.") == "legal_conclusion"
    assert ComplaintWorkspaceService._classify_mike_assertion_type("Plaintiff reported safety concerns to HR in writing.") == "factual_statement"
    assert ComplaintWorkspaceService._classify_mike_assertion_type("") == "unsupported_rhetoric"
    assert ComplaintWorkspaceService._classify_mike_assertion_type("Too vague.") == "unsupported_rhetoric"
