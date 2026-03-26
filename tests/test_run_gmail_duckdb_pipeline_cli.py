from __future__ import annotations

import argparse
import importlib.util
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
    summary_path = tmp_path / "duckdb" / "gmail_duckdb_pipeline_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    async def fake_run_gmail_duckdb_pipeline(**kwargs):
        summary_path.write_text("{}", encoding="utf-8")
        return {
            "status": "success",
            "pipeline": "gmail_duckdb_pipeline",
            "stop_reason": "checkpoint_window_exhausted",
            "batch_count": 2,
            "total_imported_count": 3,
            "total_searched_message_count": 625,
            "summary_path": str(summary_path),
            "received": kwargs,
        }

    monkeypatch.setattr(module, "run_gmail_duckdb_pipeline", fake_run_gmail_duckdb_pipeline)

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
    assert payload["received"]["years_back"] == 2
    assert payload["received"]["uid_window_size"] == 500
    assert payload["received"]["bm25_search_query"] == "termination grievance"
    assert Path(payload["summary_path"]).exists()
