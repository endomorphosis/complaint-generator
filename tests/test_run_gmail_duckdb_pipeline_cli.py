from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import anyio


def _load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_gmail_duckdb_pipeline.py"
    spec = importlib.util.spec_from_file_location("run_gmail_duckdb_pipeline_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_parser_exposes_pipeline_and_bm25_flags():
    module = _load_script_module()

    help_text = module.build_parser().format_help()

    assert "--years-back" in help_text
    assert "--uid-window-size" in help_text
    assert "--max-batches" in help_text
    assert "--duckdb-output-dir" in help_text
    assert "--append-to-existing-corpus" in help_text
    assert "--bm25-search-query" in help_text
    assert "--bm25-search-limit" in help_text


def test_run_pipeline_batches_imports_and_appends_duckdb(tmp_path, monkeypatch):
    module = _load_script_module()
    manifest_one = tmp_path / "batch-one-manifest.json"
    manifest_two = tmp_path / "batch-two-manifest.json"
    manifest_three = tmp_path / "batch-three-manifest.json"
    for manifest in (manifest_one, manifest_two, manifest_three):
        manifest.write_text(json.dumps({"emails": []}), encoding="utf-8")

    import_payloads = iter(
        [
            {
                "status": "success",
                "date_after": "2024-03-26",
                "date_before": None,
                "searched_message_count": 500,
                "imported_count": 2,
                "raw_email_total_bytes": 1000,
                "manifest_path": str(manifest_one),
                "checkpoint_path": str(tmp_path / "checkpoint.json"),
            },
            {
                "status": "success",
                "date_after": "2024-03-26",
                "date_before": None,
                "searched_message_count": 125,
                "imported_count": 1,
                "raw_email_total_bytes": 400,
                "manifest_path": str(manifest_two),
                "checkpoint_path": str(tmp_path / "checkpoint.json"),
            },
            {
                "status": "success",
                "date_after": "2024-03-26",
                "date_before": None,
                "searched_message_count": 0,
                "imported_count": 0,
                "raw_email_total_bytes": 0,
                "manifest_path": str(manifest_three),
                "checkpoint_path": str(tmp_path / "checkpoint.json"),
            },
        ]
    )
    import_calls = []
    duckdb_calls = []
    search_calls = []

    async def fake_import_gmail_evidence(**kwargs):
        import_calls.append(dict(kwargs))
        return next(import_payloads)

    def fake_build_email_duckdb_artifacts(*, manifest_path, output_dir=None, include_attachment_text=False, append=False):
        duckdb_calls.append(
            {
                "manifest_path": manifest_path,
                "output_dir": output_dir,
                "append": append,
                "include_attachment_text": include_attachment_text,
            }
        )
        return {
            "status": "created",
            "duckdb_path": str(tmp_path / "duckdb" / "email_corpus.duckdb"),
            "index_dir": str(tmp_path / "duckdb"),
            "bm25_terms_parquet_path": str(tmp_path / "duckdb" / "email_bm25_terms.parquet"),
        }

    def fake_search_email_graphrag_duckdb(*, index_path, query, limit, ranking="bm25", bm25_k1=1.2, bm25_b=0.75):
        search_calls.append(
            {
                "index_path": index_path,
                "query": query,
                "limit": limit,
                "ranking": ranking,
                "bm25_k1": bm25_k1,
                "bm25_b": bm25_b,
            }
        )
        return {
            "status": "success",
            "query": query,
            "ranking": ranking,
            "result_count": 2,
            "results": [],
        }

    monkeypatch.setattr(module, "import_gmail_evidence", fake_import_gmail_evidence)
    monkeypatch.setattr(module, "build_email_duckdb_artifacts", fake_build_email_duckdb_artifacts)
    monkeypatch.setattr(module, "search_email_graphrag_duckdb", fake_search_email_graphrag_duckdb)

    args = argparse.Namespace(
        user_id="case-user",
        addresses=["hr@example.com", "manager@example.com"],
        claim_element_id="causation",
        folder="INBOX",
        scan_folder=["[Gmail]/All Mail"],
        years_back=2,
        date_after=None,
        date_before=None,
        complaint_query="termination retaliation",
        complaint_keyword=["termination", "retaliation"],
        min_relevance_score=1.5,
        workspace_root=str(tmp_path / "sessions"),
        evidence_root=str(tmp_path / "evidence"),
        gmail_user="user@gmail.com",
        gmail_app_password="app-password",
        use_gmail_oauth=False,
        gmail_oauth_client_secrets=None,
        gmail_oauth_token_cache=None,
        no_gmail_oauth_browser=False,
        prompt_for_credentials=False,
        use_keyring=False,
        save_to_keyring=False,
        use_ipfs_secrets_vault=False,
        save_to_ipfs_secrets_vault=False,
        checkpoint_name="gmail-duckdb-pipeline",
        uid_window_size=500,
        max_batches=5,
        duckdb_output_dir=str(tmp_path / "duckdb"),
        append_to_existing_corpus=False,
        bm25_search_query="termination grievance",
        bm25_search_limit=25,
        json=True,
    )

    payload = anyio.run(module._run, args)

    assert payload["status"] == "success"
    assert payload["stop_reason"] == "checkpoint_window_exhausted"
    assert payload["batch_count"] == 2
    assert payload["total_imported_count"] == 3
    assert payload["total_searched_message_count"] == 625
    assert len(import_calls) == 2
    assert import_calls[0]["use_uid_checkpoint"] is True
    assert import_calls[0]["years_back"] == 2
    assert len(duckdb_calls) == 2
    assert duckdb_calls[0]["append"] is False
    assert duckdb_calls[1]["append"] is True
    assert search_calls[0]["ranking"] == "bm25"
    assert search_calls[0]["limit"] == 25
    assert Path(payload["summary_path"]).exists()
