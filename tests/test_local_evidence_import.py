import json
import mailbox
from email.message import EmailMessage
from pathlib import Path
import zipfile

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
    assert timeline_item["suggested_claim_element_id"] == "protected_activity"
    assert timeline_item["effective_claim_element_id"] == "causation"
    assert timeline_item["import_origin_label"] == "file"
    assert Path(timeline_item["copied_path"]).is_file()
    metadata_path = Path(timeline_item["artifact_dir"], "metadata.json")
    assert metadata_path.is_file()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["suggested_claim_element_id"] == "protected_activity"
    assert metadata["import_origin_label"] == "file"

    session = service.get_session("case-user")["session"]
    documents = session["evidence"]["documents"]
    assert len(documents) == 2
    assert any(record["title"] == "Local import: timeline.txt" for record in documents)
    assert any("metadata.json" in record["attachment_names"] for record in documents)


def test_import_local_evidence_expands_zip_archives(tmp_path):
    workspace_root = tmp_path / "sessions"
    evidence_root = tmp_path / "evidence"
    service = ComplaintWorkspaceService(root_dir=workspace_root)

    archive_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("emails/timeline.txt", "Termination followed the HR complaint.")
        archive.writestr("screenshots/notice.png", b"\x89PNG\r\nfake-image")

    payload = import_local_evidence(
        paths=[archive_path],
        user_id="case-user",
        claim_element_id="causation",
        workspace_root=workspace_root,
        evidence_root=evidence_root,
        service=service,
    )

    assert payload["imported_count"] == 2
    assert sorted(item["archive_member"] for item in payload["imported"]) == ["emails/timeline.txt", "screenshots/notice.png"]
    timeline_member = next(item for item in payload["imported"] if item["archive_member"] == "emails/timeline.txt")
    assert timeline_member["import_origin_label"] == "zip_member"
    assert timeline_member["suggested_claim_element_id"] == "protected_activity"
    session = service.get_session("case-user")["session"]
    assert any(record["title"] == "Archive import: bundle.zip :: emails/timeline.txt" for record in session["evidence"]["documents"])


def test_import_local_evidence_expands_mbox_archives(tmp_path):
    workspace_root = tmp_path / "sessions"
    evidence_root = tmp_path / "evidence"
    service = ComplaintWorkspaceService(root_dir=workspace_root)

    archive_path = tmp_path / "mailbox.mbox"
    box = mailbox.mbox(str(archive_path))
    message = EmailMessage()
    message["Subject"] = "Termination email"
    message["From"] = "hr@example.com"
    message["To"] = "employee@example.com"
    message.set_content("Termination followed the HR complaint by two days.")
    box.add(message)
    box.flush()
    box.close()

    payload = import_local_evidence(
        paths=[archive_path],
        user_id="case-user",
        claim_element_id="causation",
        workspace_root=workspace_root,
        evidence_root=evidence_root,
        service=service,
    )

    assert payload["imported_count"] == 1
    assert payload["imported"][0]["media_type"] == "message/rfc822"
    assert payload["imported"][0]["import_origin_label"] == "mbox_message"
    session = service.get_session("case-user")["session"]
    assert any(record["title"] == "Mailbox import: Termination email" for record in session["evidence"]["documents"])


def test_import_local_evidence_can_auto_assign_claim_element_from_content(tmp_path):
    workspace_root = tmp_path / "sessions"
    evidence_root = tmp_path / "evidence"
    service = ComplaintWorkspaceService(root_dir=workspace_root)

    source_file = tmp_path / "hr-complaint.txt"
    source_file.write_text("I submitted an HR complaint and grievance email to management.", encoding="utf-8")

    payload = import_local_evidence(
        paths=[source_file],
        user_id="case-user",
        claim_element_id="auto",
        workspace_root=workspace_root,
        evidence_root=evidence_root,
        service=service,
    )

    assert payload["imported_count"] == 1
    imported = payload["imported"][0]
    assert imported["suggested_claim_element_id"] == "protected_activity"
    assert imported["effective_claim_element_id"] == "protected_activity"

    session = service.get_session("case-user")["session"]
    documents = session["evidence"]["documents"]
    assert documents[0]["claim_element_id"] == "protected_activity"
