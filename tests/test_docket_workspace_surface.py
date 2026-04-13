from __future__ import annotations

from applications import complaint_cli
from applications.complaint_workspace import ComplaintWorkspaceService
import ipfs_datasets_py.processors.legal_data as legal_data


def _sample_dataset() -> dict:
    return {
        "dataset_id": "dataset-1",
        "docket_id": "1:24-cv-1001",
        "case_name": "Doe v. Acme",
        "court": "D. Example",
        "documents": [
            {
                "id": "doc-1",
                "title": "Complaint",
                "text": "Fair housing complaint",
                "date_filed": "2026-01-01",
                "document_number": "1",
                "metadata": {"kind": "pleading"},
            }
        ],
        "knowledge_graph": {
            "entities": [
                {"id": "issue-1", "type": "legal_issue", "label": "Retaliation"},
                {"id": "issue-2", "type": "claim", "label": "Discrimination"},
                {"id": "doc-entity-1", "type": "document", "label": "Complaint"},
            ],
            "relationships": [
                {"id": "rel-1", "type": "supports", "source": "issue-1", "target": "issue-2"},
                {"id": "rel-2", "type": "describes", "source": "doc-entity-1", "target": "issue-1"},
            ],
        },
        "metadata": {"source": "unit-test"},
    }


def test_docket_tools_are_listed_in_mcp_surface() -> None:
    tools = ComplaintWorkspaceService().list_mcp_tools()["tools"]
    names = {tool["name"] for tool in tools}
    assert "complaint.view_docket_dataset" in names
    assert "complaint.search_docket_dataset" in names
    assert "complaint.get_docket_dataset_metadata" in names
    assert "complaint.get_docket_dataset_graph" in names


def test_workspace_can_project_metadata_and_issue_links(monkeypatch) -> None:
    service = ComplaintWorkspaceService()
    dataset = _sample_dataset()

    monkeypatch.setattr(service, "_load_docket_dataset_payload", lambda *args, **kwargs: dataset)
    monkeypatch.setattr(
        legal_data,
        "summarize_docket_dataset",
        lambda payload: {
            "dataset_id": payload["dataset_id"],
            "document_count": len(payload["documents"]),
            "knowledge_graph_entity_count": len(payload["knowledge_graph"]["entities"]),
            "knowledge_graph_relationship_count": len(payload["knowledge_graph"]["relationships"]),
        },
    )

    metadata = service.get_docket_dataset_metadata("/tmp/docket.json", input_type="json")
    graph = service.get_docket_dataset_graph("/tmp/docket.json", input_type="json")

    assert metadata["dataset_id"] == "dataset-1"
    assert metadata["metadata"]["source"] == "unit-test"
    assert graph["knowledge_graph"]["issue_entity_count"] == 2
    assert graph["knowledge_graph"]["issue_link_count"] == 2
    assert graph["knowledge_graph"]["issue_links"][0]["source_entity"]["id"] == "issue-1"


def test_workspace_dispatches_docket_search_tool(monkeypatch) -> None:
    service = ComplaintWorkspaceService()
    expected = {
        "query": "retaliation",
        "search_backend": "bm25",
        "search_results": {"result_count": 1, "results": [{"id": "doc-1"}]},
    }
    monkeypatch.setattr(service, "search_docket_dataset", lambda *args, **kwargs: expected)

    result = service.call_mcp_tool(
        "complaint.search_docket_dataset",
        {
            "input_path": "/tmp/docket.json",
            "input_type": "json",
            "query": "retaliation",
            "search_backend": "bm25",
        },
    )

    assert result == expected


def test_cli_docket_graph_command_uses_workspace_service(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        complaint_cli.service,
        "get_docket_dataset_graph",
        lambda input_path, input_type="packaged": {
            "input_path": input_path,
            "input_type": input_type,
            "knowledge_graph": {"issue_link_count": 3},
        },
    )

    complaint_cli.docket_graph("/tmp/bundle_manifest.json", input_type="packaged")
    rendered = capsys.readouterr().out

    assert '"issue_link_count": 3' in rendered
