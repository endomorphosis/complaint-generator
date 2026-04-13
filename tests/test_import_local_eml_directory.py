from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "import_local_eml_directory.py"
    spec = importlib.util.spec_from_file_location("import_local_eml_directory_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_import_local_eml_directory_materializes_manifest_and_attachments(tmp_path: Path) -> None:
    module = _load_script_module()
    source_dir = tmp_path / "emails"
    source_dir.mkdir()
    sample_eml = (
        b"From: \"Tilton, Kati\" <KTilton@clackamas.us>\r\n"
        b"To: benjamin barber <starworks5@gmail.com>\r\n"
        b"Subject: RE: HCV Orientation\r\n"
        b"Date: Thu, 26 Mar 2026 09:36:46 -0700\r\n"
        b"Message-ID: <msg-1@example.com>\r\n"
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: multipart/mixed; boundary=\"sep\"\r\n"
        b"\r\n"
        b"--sep\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Please see the attached denial for the living room accommodation.\r\n"
        b"--sep\r\n"
        b"Content-Type: text/plain; name=\"note.txt\"\r\n"
        b"Content-Disposition: attachment; filename=\"note.txt\"\r\n"
        b"\r\n"
        b"Attachment text.\r\n"
        b"--sep--\r\n"
    )
    (source_dir / "message.eml").write_bytes(sample_eml)

    payload = module.import_local_eml_directory(
        source_dir=source_dir,
        output_dir=tmp_path / "output",
        case_slug="local-confirmed",
        complaint_query="hcv orientation living room accommodation",
        complaint_keywords=["voucher"],
    )

    manifest_path = Path(payload["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["email_count"] == 1
    assert manifest["matched_email_count"] == 1
    assert manifest["complaint_terms"][:3] == ["hcv", "orientation", "living"]
    record = manifest["emails"][0]
    assert Path(record["email_path"]).is_file()
    assert Path(record["parsed_path"]).is_file()
    assert len(record["attachment_paths"]) == 1
    assert Path(record["attachment_paths"][0]).is_file()
    assert record["message_id_header"] == "<msg-1@example.com>"
    assert record["relevance_score"] > 0


def test_import_local_eml_directory_filters_irrelevant_messages(tmp_path: Path) -> None:
    module = _load_script_module()
    source_dir = tmp_path / "emails"
    source_dir.mkdir()
    relevant_eml = (
        b"From: \"Tilton, Kati\" <KTilton@clackamas.us>\r\n"
        b"To: benjamin barber <starworks5@gmail.com>\r\n"
        b"Subject: RE: HCV Orientation\r\n"
        b"Date: Thu, 26 Mar 2026 09:36:46 -0700\r\n"
        b"Message-ID: <relevant@example.com>\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"The living room accommodation was denied after orientation.\r\n"
    )
    irrelevant_eml = (
        b"From: github@example.com\r\n"
        b"To: dev@example.com\r\n"
        b"Subject: CI run cancelled\r\n"
        b"Date: Thu, 26 Mar 2026 09:36:46 -0700\r\n"
        b"Message-ID: <irrelevant@example.com>\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Workflow status update for repository maintenance.\r\n"
    )
    (source_dir / "relevant.eml").write_bytes(relevant_eml)
    (source_dir / "irrelevant.eml").write_bytes(irrelevant_eml)

    payload = module.import_local_eml_directory(
        source_dir=source_dir,
        output_dir=tmp_path / "output",
        case_slug="filtered-confirmed",
        complaint_query="hcv orientation living room accommodation",
        complaint_keywords=["voucher"],
        min_relevance_score=1.0,
    )

    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))

    assert manifest["scanned_message_count"] == 2
    assert manifest["matched_email_count"] == 1
    assert manifest["emails"][0]["message_id_header"] == "<relevant@example.com>"
