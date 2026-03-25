from pathlib import Path

from complaint_generator.local_evidence_import import import_local_evidence
from complaint_generator.workspace import ComplaintWorkspaceService


def test_import_local_evidence_copies_files_and_registers_workspace_documents(tmp_path):
    workspace_root = tmp_path / "sessions"
    evidence_root = tmp_path / "evidence"
    service = ComplaintWorkspaceService(root_dir=workspace_root)

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    text_file = source_dir / "timeline.txt"
    text_file.write_text("Termination email arrived two days after the HR complaint.", encoding="utf-8")
    image_file = source_dir / "screenshot.png"
    image_file.write_bytes(b"\x89PNG\r\nfake-image")

    payload = import_local_evidence(
        paths=[text_file, image_file],
        user_id="case-user",
        claim_element_id="causation",
        workspace_root=workspace_root,
        evidence_root=evidence_root,
        service=service,
    )

    assert payload["status"] == "success"
    assert payload["scanned_file_count"] == 2
    assert payload["imported_count"] == 2
    assert payload["skipped_count"] == 0
    assert sorted(item["filename"] for item in payload["imported"]) == ["screenshot.png", "timeline.txt"]

    timeline_item = next(item for item in payload["imported"] if item["filename"] == "timeline.txt")
    assert "HR complaint" in timeline_item["preview_text"]
    assert Path(timeline_item["copied_path"]).is_file()
    assert Path(timeline_item["artifact_dir"], "metadata.json").is_file()

    session = service.get_session("case-user")["session"]
    documents = session["evidence"]["documents"]
    assert len(documents) == 2
    assert any(record["title"] == "Local import: timeline.txt" for record in documents)
    assert any("metadata.json" in record["attachment_names"] for record in documents)
