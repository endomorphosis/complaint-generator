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
    assert after_conflict_sync["invariants"]["pending_sync_implies_handoff"] is True
    assert after_conflict_sync["invariants"]["synced_handoff_never_pending"] is True


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
