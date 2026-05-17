from pathlib import Path

from applications.complaint_workspace import ComplaintWorkspaceService


def test_mike_status_contract_state_transitions_and_invariants(tmp_path):
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    user_id = "mike-contract-user"

    initial = service.get_mike_integration_status(user_id)
    assert initial["status_contract_version"] == "complaint-mike-status-v2"
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
    assert after_conflict_sync["invariants"]["pending_sync_matches_handoff_sync_ids"] is True


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
