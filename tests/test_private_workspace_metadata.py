"""Public identifiers and default logs must not carry private case metadata.

Synthetic fixtures only. Encryption is not treated as a hide-all-metadata claim.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

USER_NAME = "Jordan Hale"
CASE_NAME = "Hale v. Northwind Clinic"
COMPLAINT = "On March 3 the clinic billed Jordan Hale twice for the same visit."
FILENAME = "hale-visit-invoice.pdf"
NODE_LABEL = "double-billing-of-Jordan-Hale"
QUERY = "elements of unjust enrichment against Northwind Clinic"
TOKEN = "sk-synthetic-metadata-token-priv005"
PAYLOAD = "payload:" + COMPLAINT
KEY_TEXT = "data-key-material-should-not-leak"


def _literals() -> list[str]:
    return [USER_NAME, CASE_NAME, COMPLAINT, FILENAME, NODE_LABEL, QUERY, TOKEN, PAYLOAD, KEY_TEXT]


def _assert_absent(blob: str) -> None:
    for literal in _literals():
        assert literal not in blob


def test_public_cid_metadata_filenames_and_index_omit_private_literals() -> None:
    from integrations.ipfs_datasets.storage import (
        clear_public_index,
        opaque_storage_filename,
        project_public_cid_metadata,
        public_index_snapshot,
        publish_public_index_entry,
    )

    clear_public_index()
    raw = {
        "cid": "bafy-opaque",
        "cid_kind": "opaque",
        "artifact_class": "opaque_private_ref",
        "status": "stored",
        "user_name": USER_NAME,
        "case_name": CASE_NAME,
        "complaint_text": COMPLAINT,
        "filename": FILENAME,
        "node_label": NODE_LABEL,
        "query": QUERY,
        "token": TOKEN,
        "payload": PAYLOAD,
    }
    projected = project_public_cid_metadata(raw, sensitive_literals=_literals())
    filename = opaque_storage_filename("attachment", FILENAME)
    projected["opaque_name"] = filename
    stored = publish_public_index_entry(projected, sensitive_literals=_literals())
    blob = json.dumps({"projected": projected, "stored": stored, "index": public_index_snapshot()})
    _assert_absent(blob)
    assert FILENAME not in filename
    assert stored["artifact_class"] == "opaque_private_ref"
    assert "user_name" not in stored
    assert "query" not in stored


def test_private_diagnostics_keep_operation_identity_and_drop_secrets() -> None:
    from integrations.ipfs_datasets.llm import redact_generation_diagnostic
    from integrations.ipfs_datasets.storage import emit_default_storage_log

    record = {
        "operation_id": "store-private-artifact",
        "status": "degraded",
        "error_category": "backend_unavailable",
        "duration_ms": 18,
        "synthetic_source": "fixture-source-a",
        "payload": PAYLOAD,
        "token": TOKEN,
        "api_key": KEY_TEXT,
        "complaint_text": COMPLAINT,
        "filename": FILENAME,
        "query": QUERY,
        "user_name": USER_NAME,
    }
    diagnostic = redact_generation_diagnostic(record)
    assert diagnostic == {
        "operation_id": "store-private-artifact",
        "status": "degraded",
        "error_category": "backend_unavailable",
        "duration_ms": 18,
        "synthetic_source": "fixture-source-a",
    }
    captured: list[str] = []

    class _Handler(logging.Handler):
        def emit(self, log_record: logging.LogRecord) -> None:
            captured.append(log_record.getMessage())

    logger = logging.getLogger("integrations.ipfs_datasets.storage")
    handler = _Handler()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logged = emit_default_storage_log(record)
    finally:
        logger.removeHandler(handler)
    assert logged == diagnostic
    _assert_absent("\n".join(captured))
    assert "fixture-source-a" in captured[0]
    assert "backend_unavailable" in captured[0]


def test_case_aliases_stay_encrypted_and_do_not_cross_caches() -> None:
    from integrations.ipfs_datasets.llm import (
        case_alias_cache_public_view,
        clear_case_private_caches,
        remember_case_alias,
        resolve_case_alias,
    )

    clear_case_private_caches()
    key_a = os.urandom(32)
    key_b = os.urandom(32)
    remember_case_alias(
        user_id="user-a",
        case_id="case-a",
        alias="party-1",
        canonical=USER_NAME,
        key=key_a,
        key_id="key-a",
    )
    view = case_alias_cache_public_view("user-a", "case-a")
    assert view["encrypted"] is True
    assert USER_NAME not in view["joined_ciphertext"]
    assert CASE_NAME not in view["joined_ciphertext"]
    opened = resolve_case_alias(
        user_id="user-a",
        case_id="case-a",
        alias="party-1",
        key=key_a,
        key_id="key-a",
    )
    assert opened["canonical"] == USER_NAME
    other = resolve_case_alias(
        user_id="user-b",
        case_id="case-a",
        alias="party-1",
        key=key_b,
        key_id="key-b",
    )
    assert other["found"] is False
    other_case = resolve_case_alias(
        user_id="user-a",
        case_id="case-b",
        alias="party-1",
        key=key_a,
        key_id="key-a",
    )
    assert other_case["found"] is False
    with pytest.raises(Exception):
        resolve_case_alias(
            user_id="user-a",
            case_id="case-a",
            alias="party-1",
            key=key_b,
            key_id="key-a",
        )


def test_embeddings_are_private_derived_data(tmp_path: Path) -> None:
    from applications.complaint_workspace import ComplaintWorkspaceService
    from integrations.ipfs_datasets.llm import clear_case_private_caches, open_private_embedding
    from integrations.ipfs_datasets.storage import clear_public_index, public_index_snapshot

    clear_case_private_caches()
    clear_public_index()
    key = os.urandom(32)
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    stored = service.store_case_embedding(
        "user-a",
        "case-a",
        [0.25, 0.5],
        COMPLAINT,
        key=key,
        key_id="embed-key",
        sensitive_literals=_literals(),
    )
    assert stored["classification"] == "private_derived"
    assert stored["public_index"]["classification"] == "private_derived"
    blob = json.dumps(public_index_snapshot())
    _assert_absent(blob)
    assert "0.25" not in blob
    opened = open_private_embedding(
        user_id="user-a",
        case_id="case-a",
        embedding_id=stored["embedding_id"],
        key=key,
        key_id="embed-key",
    )
    assert opened["found"] is True
    assert opened["source_text"] == COMPLAINT
    missing = open_private_embedding(
        user_id="user-b",
        case_id="case-b",
        embedding_id=stored["embedding_id"],
        key=key,
        key_id="embed-key",
    )
    assert missing["found"] is False


def test_workspace_public_reference_and_default_log(tmp_path: Path) -> None:
    from applications.complaint_workspace import ComplaintWorkspaceService
    from integrations.ipfs_datasets.storage import clear_public_index, public_index_snapshot

    clear_public_index()
    service = ComplaintWorkspaceService(root_dir=tmp_path)
    published = service.publish_case_public_reference(
        {
            "cid": "bafy-case-ref",
            "user_name": USER_NAME,
            "case_name": CASE_NAME,
            "complaint_text": COMPLAINT,
            "node_label": NODE_LABEL,
            "query": QUERY,
            "kind": "attachment",
        },
        sensitive_literals=_literals(),
        document_filename=FILENAME,
    )
    logged = service.default_workspace_log(
        {
            "operation_id": "publish-reference",
            "status": "available",
            "error_category": "",
            "duration_ms": 4,
            "synthetic_source": "fixture-source-a",
            "complaint_text": COMPLAINT,
            "token": TOKEN,
            "filename": FILENAME,
        }
    )
    blob = json.dumps({"published": published, "index": public_index_snapshot(), "log": logged})
    _assert_absent(blob)
    assert published["filename"].endswith(".bin")
    assert FILENAME not in published["filename"]
    assert logged["synthetic_source"] == "fixture-source-a"
    assert logged["operation_id"] == "publish-reference"
    exposure = service.metadata_residual_exposure()
    text = exposure["residual_exposure"]
    assert "size" in text
    assert "timing" in text
    assert "access pattern" in text
    assert exposure["padding_policy"]["optional"] is True
    assert exposure["padding_policy"]["hides_all_metadata"] is False
    assert "not a promise" in text


def test_padding_is_optional_and_bounded() -> None:
    from integrations.ipfs_datasets.storage import (
        PADDING_POLICY,
        RESIDUAL_METADATA_EXPOSURE,
        optional_size_padding,
    )

    raw = b"abc"
    skipped = optional_size_padding(raw, enabled=False, block_size=256)
    assert skipped["applied"] is False
    assert skipped["data"] == raw
    assert skipped["policy"]["hides_all_metadata"] is False
    assert skipped["policy"]["residual_exposure"] == RESIDUAL_METADATA_EXPOSURE
    padded = optional_size_padding(raw, enabled=True, block_size=256)
    assert padded["applied"] is True
    assert len(padded["data"]) % 256 == 0
    assert padded["policy"] == PADDING_POLICY
    with pytest.raises(ValueError, match="padding_block_out_of_bounds"):
        optional_size_padding(raw, enabled=True, block_size=16)
    with pytest.raises(ValueError, match="padding_block_out_of_bounds"):
        optional_size_padding(raw, enabled=True, block_size=2 ** 20)


def test_daemon_default_log_redacts_case_material(tmp_path: Path) -> None:
    from complaint_generator.ui_optimizer_daemon import _write_status, redact_daemon_default_log
    import argparse

    log_file = tmp_path / "daemon.log"
    status_file = tmp_path / "status.json"
    pid_file = tmp_path / "daemon.pid"
    args = argparse.Namespace(
        user_id=USER_NAME,
        artifact_root=str(tmp_path),
        workspace_root=str(tmp_path),
        pytest_target="synthetic",
        max_rounds=1,
        iterations=1,
        poll_seconds=1.0,
        retry_seconds=1.0,
        max_cycles=1,
        max_consecutive_errors=1,
        method="actor_critic",
        priority=1,
        provider="",
        model="",
        use_llm_draft=False,
    )
    secret_result = {
        "draft_title": COMPLAINT,
        "markdown_export": {"filename": FILENAME},
        "summary": {"export_review_excerpt": QUERY, "node_label": NODE_LABEL},
        "token": TOKEN,
    }
    payload = _write_status(
        args=args,
        pid_file=pid_file,
        status_file=status_file,
        log_file=log_file,
        state="degraded",
        phase="export",
        cycle_count=1,
        consecutive_errors=1,
        last_result=secret_result,
        error=COMPLAINT,
        error_kind="export_failed",
        error_summary=QUERY,
        phase_started_at=None,
    )
    assert payload["status"] == "degraded"
    log_text = log_file.read_text(encoding="utf-8")
    _assert_absent(log_text)
    assert USER_NAME not in log_text
    diagnostic = redact_daemon_default_log(json.loads(log_text.strip().splitlines()[-1]))
    assert diagnostic["operation_id"] == "export"
    assert diagnostic["status"] == "degraded"
    assert diagnostic["error_category"] == "export_failed"
    assert diagnostic["synthetic_source"] == "ui-optimizer-daemon"
    query_ref_blob = log_text
    assert QUERY not in query_ref_blob
