from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "master_case_email.py"
    spec = importlib.util.spec_from_file_location("master_case_email_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_parser_exposes_master_rebuild_and_search_flags() -> None:
    module = _load_script_module()

    help_text = module.build_parser().format_help()

    assert "--rebuild" in help_text
    assert "--search-query" in help_text
    assert "--agentic-query" in help_text
    assert "--seed-term" in help_text
    assert "--required-participant-domain" in help_text


def test_main_uses_canonical_master_paths(monkeypatch, capsys) -> None:
    module = _load_script_module()

    def fake_build_email_graphrag_artifacts(*, manifest_path, include_attachment_text_in_search):
        assert Path(manifest_path) == module.MASTER_MANIFEST_PATH
        assert include_attachment_text_in_search is True
        return {"status": "rebuilt"}

    def fake_search_email_graphrag_duckdb(*, index_path, query, limit):
        assert Path(index_path) == module.MASTER_DUCKDB_PATH
        assert query == "living room"
        assert limit == 5
        return {"status": "success", "query": query, "result_count": 1}

    def fake_search_email_corpus_agentic(
        *,
        index_path,
        complaint_query,
        complaint_keywords,
        seed_terms,
        seed_participants,
        required_participant_domains,
        result_limit,
        chain_limit,
        emit_graphrag,
    ):
        assert Path(index_path) == module.MASTER_DUCKDB_PATH
        assert complaint_query == "mobility accommodation"
        assert complaint_keywords == ["voucher"]
        assert seed_terms == ["ashley ferron"]
        assert seed_participants == ["aferron@clackamas.us"]
        assert required_participant_domains == ["clackamas.us"]
        assert result_limit == 10
        assert chain_limit == 4
        assert emit_graphrag is True
        return {"status": "success", "result_count": 2}

    monkeypatch.setattr(module, "build_email_graphrag_artifacts", fake_build_email_graphrag_artifacts)
    monkeypatch.setattr(module, "search_email_graphrag_duckdb", fake_search_email_graphrag_duckdb)
    monkeypatch.setattr(module, "search_email_corpus_agentic", fake_search_email_corpus_agentic)

    exit_code = module.main(
        [
            "--rebuild",
            "--search-query",
            "living room",
            "--search-limit",
            "5",
            "--agentic-query",
            "mobility accommodation",
            "--complaint-keyword",
            "voucher",
            "--seed-term",
            "ashley ferron",
            "--seed-participant",
            "aferron@clackamas.us",
            "--required-participant-domain",
            "clackamas.us",
            "--result-limit",
            "10",
            "--chain-limit",
            "4",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["master_manifest_path"] == str(module.MASTER_MANIFEST_PATH)
    assert payload["master_duckdb_path"] == str(module.MASTER_DUCKDB_PATH)
    assert payload["graphrag_summary"] == {"status": "rebuilt"}
    assert payload["duckdb_search"]["result_count"] == 1
    assert payload["agentic_search"]["result_count"] == 2
