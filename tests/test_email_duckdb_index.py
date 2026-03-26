from __future__ import annotations

import json
import importlib
import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")

repo_root = Path(__file__).resolve().parents[2] / "ipfs_datasets_py"
sys.path.insert(0, str(repo_root))
for module_name in list(sys.modules):
    if module_name == "ipfs_datasets_py" or module_name.startswith("ipfs_datasets_py."):
        sys.modules.pop(module_name, None)
module = importlib.import_module("ipfs_datasets_py.processors.multimedia.email_duckdb_index")

build_email_duckdb_index = module.build_email_duckdb_index
search_email_duckdb_index = module.search_email_duckdb_index


def test_build_and_search_email_duckdb_index(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "message.eml").write_bytes(
        (
            b"From: hr@example.com\r\n"
            b"To: employee@example.com\r\n"
            b"Subject: Termination meeting\r\n"
            b"Message-ID: <msg-1@example.test>\r\n"
            b"\r\n"
            b"The retaliation timeline and termination hearing are attached.\r\n"
        )
    )
    attachment = bundle_dir / "timeline.txt"
    attachment.write_text("Retaliation timeline with protected activity details.", encoding="utf-8")
    manifest_path = tmp_path / "email_import_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "emails": [
                    {
                        "subject": "Termination meeting",
                        "from": "hr@example.com",
                        "to": "employee@example.com",
                        "cc": "",
                        "date": "2026-03-25T12:00:00+00:00",
                        "message_id_header": "<msg-1@example.test>",
                        "bundle_dir": str(bundle_dir),
                        "eml_path": str(bundle_dir / "message.eml"),
                        "attachment_paths": [str(attachment)],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    summary = build_email_duckdb_index(manifest_path=manifest_path, output_dir=tmp_path / "duckdb")

    assert summary["status"] == "created"
    assert Path(summary["duckdb_path"]).exists()
    assert Path(summary["messages_parquet_path"]).exists()
    assert Path(summary["terms_parquet_path"]).exists()
    assert Path(summary["bm25_terms_parquet_path"]).exists()
    assert summary["bm25_distinct_term_count"] >= 1

    search_payload = search_email_duckdb_index(
        index_path=summary["duckdb_path"],
        query="retaliation hearing hr@example.com",
        limit=5,
        ranking="bm25",
    )

    assert search_payload["status"] == "success"
    assert search_payload["ranking"] == "bm25"
    assert search_payload["result_count"] == 1
    assert search_payload["results"][0]["subject"] == "Termination meeting"
    assert "retaliation timeline" in search_payload["results"][0]["snippet"].lower()


def test_build_email_duckdb_index_can_append_manifests(tmp_path: Path) -> None:
    bundle_one = tmp_path / "bundle-one"
    bundle_one.mkdir()
    (bundle_one / "message.eml").write_bytes(
        (
            b"From: hr@example.com\r\n"
            b"To: employee@example.com\r\n"
            b"Subject: First notice\r\n"
            b"Message-ID: <msg-1@example.test>\r\n"
            b"\r\n"
            b"First body.\r\n"
        )
    )
    manifest_one = tmp_path / "manifest-one.json"
    manifest_one.write_text(
        json.dumps(
            {
                "emails": [
                    {
                        "subject": "First notice",
                        "from": "hr@example.com",
                        "to": "employee@example.com",
                        "message_id_header": "<msg-1@example.test>",
                        "bundle_dir": str(bundle_one),
                        "eml_path": str(bundle_one / "message.eml"),
                        "attachment_paths": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    bundle_two = tmp_path / "bundle-two"
    bundle_two.mkdir()
    (bundle_two / "message.eml").write_bytes(
        (
            b"From: counsel@example.com\r\n"
            b"To: employee@example.com\r\n"
            b"Subject: Second notice\r\n"
            b"Message-ID: <msg-2@example.test>\r\n"
            b"\r\n"
            b"Second body.\r\n"
        )
    )
    manifest_two = tmp_path / "manifest-two.json"
    manifest_two.write_text(
        json.dumps(
            {
                "emails": [
                    {
                        "subject": "Second notice",
                        "from": "counsel@example.com",
                        "to": "employee@example.com",
                        "message_id_header": "<msg-2@example.test>",
                        "bundle_dir": str(bundle_two),
                        "eml_path": str(bundle_two / "message.eml"),
                        "attachment_paths": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    summary_one = build_email_duckdb_index(manifest_path=manifest_one, output_dir=tmp_path / "duckdb")
    summary_two = build_email_duckdb_index(
        manifest_path=manifest_two,
        output_dir=tmp_path / "duckdb",
        append=True,
    )

    search_payload = search_email_duckdb_index(
        index_path=summary_two["duckdb_path"],
        query="notice",
        limit=10,
        ranking="bm25",
    )

    assert summary_one["append_mode"] is False
    assert summary_two["append_mode"] is True
    assert search_payload["result_count"] == 2


def test_search_email_duckdb_index_falls_back_to_weighted_when_bm25_tables_are_empty(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "message.eml").write_bytes(
        (
            b"From: hr@example.com\r\n"
            b"To: employee@example.com\r\n"
            b"Subject: Care card cancellation\r\n"
            b"Message-ID: <msg-fallback@example.test>\r\n"
            b"\r\n"
            b"Care card cancellation details.\r\n"
        )
    )
    manifest_path = tmp_path / "email_import_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "emails": [
                    {
                        "subject": "Care card cancellation",
                        "from": "hr@example.com",
                        "to": "employee@example.com",
                        "message_id_header": "<msg-fallback@example.test>",
                        "bundle_dir": str(bundle_dir),
                        "eml_path": str(bundle_dir / "message.eml"),
                        "attachment_paths": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    summary = build_email_duckdb_index(manifest_path=manifest_path, output_dir=tmp_path / "duckdb")
    con = duckdb.connect(summary["duckdb_path"])
    con.execute("DELETE FROM email_bm25_documents")
    con.execute("DELETE FROM email_bm25_terms")
    con.close()

    search_payload = search_email_duckdb_index(
        index_path=summary["duckdb_path"],
        query="care card cancellation",
        limit=5,
        ranking="bm25",
    )

    assert search_payload["status"] == "success"
    assert search_payload["ranking"] == "weighted"
    assert search_payload["result_count"] == 1
    assert search_payload["results"][0]["subject"] == "Care card cancellation"
