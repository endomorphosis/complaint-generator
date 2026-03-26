from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Sequence

from .email_graphrag import build_email_duckdb_artifacts, search_email_graphrag_duckdb
from .email_import import import_gmail_evidence


def _default_duckdb_output_dir(manifest_path: str | Path, explicit_output_dir: str | None) -> Path:
    if explicit_output_dir:
        return Path(explicit_output_dir).expanduser().resolve()
    return Path(manifest_path).expanduser().resolve().parent / "duckdb"


async def run_gmail_duckdb_pipeline(
    *,
    user_id: str,
    addresses: Sequence[str],
    claim_element_id: str = "causation",
    folder: str = "INBOX",
    folders: Sequence[str] = (),
    years_back: Optional[int] = 2,
    date_after: Optional[str] = None,
    date_before: Optional[str] = None,
    complaint_query: Optional[str] = None,
    complaint_keywords: Sequence[str] = (),
    min_relevance_score: float = 0.0,
    workspace_root: str | Path = ".complaint_workspace/sessions",
    evidence_root: str | Path | None = None,
    gmail_user: Optional[str] = None,
    gmail_app_password: Optional[str] = None,
    use_gmail_oauth: bool = False,
    gmail_oauth_client_secrets: Optional[str] = None,
    gmail_oauth_token_cache: Optional[str] = None,
    gmail_oauth_open_browser: bool = True,
    checkpoint_name: str = "gmail-duckdb-pipeline",
    uid_window_size: int = 500,
    max_batches: int = 20,
    duckdb_output_dir: Optional[str] = None,
    append_to_existing_corpus: bool = False,
    bm25_search_query: Optional[str] = None,
    bm25_search_limit: int = 20,
) -> dict[str, Any]:
    batch_summaries: list[dict[str, object]] = []
    total_imported_count = 0
    total_searched_message_count = 0
    total_raw_email_bytes = 0
    latest_import_payload: dict[str, object] | None = None
    latest_duckdb_summary: dict[str, object] | None = None
    stop_reason = "max_batches_reached"

    for batch_number in range(1, max(1, int(max_batches)) + 1):
        import_payload = await import_gmail_evidence(
            addresses=addresses,
            user_id=user_id,
            claim_element_id=claim_element_id,
            workspace_root=Path(workspace_root),
            evidence_root=Path(evidence_root) if evidence_root else None,
            folder=folder,
            folders=folders,
            date_after=date_after,
            date_before=date_before,
            years_back=years_back,
            complaint_query=complaint_query,
            complaint_keywords=complaint_keywords,
            min_relevance_score=min_relevance_score,
            use_gmail_oauth=use_gmail_oauth,
            gmail_oauth_client_secrets=gmail_oauth_client_secrets,
            gmail_oauth_token_cache=gmail_oauth_token_cache,
            gmail_oauth_open_browser=gmail_oauth_open_browser,
            use_uid_checkpoint=True,
            checkpoint_name=checkpoint_name,
            uid_window_size=uid_window_size,
            gmail_user=gmail_user,
            gmail_app_password=gmail_app_password,
        )

        latest_import_payload = dict(import_payload)
        total_imported_count += int(import_payload.get("imported_count") or 0)
        total_searched_message_count += int(import_payload.get("searched_message_count") or 0)
        total_raw_email_bytes += int(import_payload.get("raw_email_total_bytes") or 0)

        manifest_path = str(import_payload.get("manifest_path") or "")
        batch_entry: dict[str, object] = {
            "batch_number": batch_number,
            "imported_count": int(import_payload.get("imported_count") or 0),
            "searched_message_count": int(import_payload.get("searched_message_count") or 0),
            "raw_email_total_bytes": int(import_payload.get("raw_email_total_bytes") or 0),
            "manifest_path": manifest_path,
            "checkpoint_path": import_payload.get("checkpoint_path"),
        }

        if manifest_path and int(import_payload.get("imported_count") or 0) > 0:
            resolved_output_dir = _default_duckdb_output_dir(manifest_path, duckdb_output_dir)
            latest_duckdb_summary = build_email_duckdb_artifacts(
                manifest_path=manifest_path,
                output_dir=resolved_output_dir,
                append=bool(append_to_existing_corpus or batch_number > 1),
            )
            batch_entry["duckdb_index"] = latest_duckdb_summary

        batch_summaries.append(batch_entry)

        searched_count = int(import_payload.get("searched_message_count") or 0)
        if searched_count <= 0:
            stop_reason = "no_new_messages"
            break
        if uid_window_size and searched_count < int(uid_window_size):
            stop_reason = "checkpoint_window_exhausted"
            break

    bm25_search_payload: dict[str, object] | None = None
    if bm25_search_query and latest_duckdb_summary and latest_duckdb_summary.get("duckdb_path"):
        bm25_search_payload = search_email_graphrag_duckdb(
            index_path=latest_duckdb_summary["duckdb_path"],
            query=bm25_search_query,
            limit=int(bm25_search_limit or 20),
            ranking="bm25",
        )

    summary = {
        "status": "success",
        "pipeline": "gmail_duckdb_pipeline",
        "user_id": user_id,
        "claim_element_id": claim_element_id,
        "years_back": years_back,
        "date_after": (latest_import_payload or {}).get("date_after"),
        "date_before": (latest_import_payload or {}).get("date_before"),
        "checkpoint_name": checkpoint_name,
        "uid_window_size": int(uid_window_size or 0),
        "max_batches": int(max_batches),
        "stop_reason": stop_reason,
        "batch_count": len(batch_summaries),
        "total_imported_count": total_imported_count,
        "total_searched_message_count": total_searched_message_count,
        "total_raw_email_bytes": total_raw_email_bytes,
        "batches": batch_summaries,
        "latest_import": latest_import_payload,
        "duckdb_index": latest_duckdb_summary,
        "bm25_search": bm25_search_payload,
    }

    if latest_duckdb_summary and latest_duckdb_summary.get("index_dir"):
        summary_path = Path(str(latest_duckdb_summary["index_dir"])) / "gmail_duckdb_pipeline_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        summary["summary_path"] = str(summary_path)

    return summary


def search_email_duckdb_corpus(
    *,
    index_path: str | Path,
    query: str,
    limit: int = 20,
    ranking: str = "bm25",
    bm25_k1: float = 1.2,
    bm25_b: float = 0.75,
) -> dict[str, Any]:
    return search_email_graphrag_duckdb(
        index_path=index_path,
        query=query,
        limit=limit,
        ranking=ranking,
        bm25_k1=bm25_k1,
        bm25_b=bm25_b,
    )


__all__ = ["run_gmail_duckdb_pipeline", "search_email_duckdb_corpus"]
