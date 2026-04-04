#!/usr/bin/env python3
from __future__ import annotations

import argparse
import email
import email.policy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ipfs_datasets_py.processors.multimedia.email_processor import EmailProcessor

import import_gmail_evidence as gmail_import
from complaint_generator.email_graphrag import build_email_graphrag_artifacts


def _iter_eml_files(root: Path, *, recursive: bool) -> list[Path]:
    pattern = "**/*.eml" if recursive else "*.eml"
    return sorted(path for path in root.glob(pattern) if path.is_file())


def import_local_eml_directory(
    *,
    source_dir: str | Path,
    output_dir: str | Path,
    case_slug: str,
    recursive: bool = False,
    complaint_query: str = "",
    complaint_keywords: list[str] | None = None,
    min_relevance_score: float = 0.0,
) -> dict[str, object]:
    source_root = Path(source_dir).expanduser().resolve()
    output_root = Path(output_dir).expanduser().resolve()
    run_dir = output_root / case_slug
    run_dir.mkdir(parents=True, exist_ok=True)

    processor = EmailProcessor(protocol="eml")
    complaint_keywords = complaint_keywords or []
    parser_args = argparse.Namespace(
        complaint_query=complaint_query,
        complaint_keyword=list(complaint_keywords),
        complaint_keyword_file=[],
    )
    complaint_terms = gmail_import._build_complaint_terms(parser_args)

    records: list[dict[str, object]] = []
    scanned_count = 0
    for index, eml_path in enumerate(_iter_eml_files(source_root, recursive=recursive), start=1):
        scanned_count += 1
        raw_bytes = eml_path.read_bytes()
        email_message = email.message_from_bytes(raw_bytes, policy=email.policy.default)
        parsed = processor._parse_email_message(email_message, include_attachments=True)
        relevance = gmail_import._score_message_relevance(email_message, complaint_terms)
        if complaint_terms and float(relevance["score"] or 0.0) < float(min_relevance_score):
            continue
        bundle_record = gmail_import._save_email_bundle(
            root_dir=run_dir,
            folder_name=str(source_root),
            email_message=email_message,
            raw_bytes=raw_bytes,
            parsed_email=parsed,
            sequence_number=len(records) + 1,
        )
        bundle_record["relevance_score"] = relevance["score"]
        bundle_record["matched_terms"] = relevance["matched_terms"]
        bundle_record["matched_fields"] = relevance["matched_fields"]
        bundle_record["cache_hit"] = False
        bundle_record["raw_sha256"] = gmail_import._raw_email_sha256(raw_bytes)
        bundle_record["raw_cid"] = gmail_import._ipfs_add_bytes(raw_bytes)
        bundle_record["source_eml_path"] = str(eml_path)
        records.append(bundle_record)

    manifest = {
        "status": "success",
        "server": "local_workspace",
        "username": "",
        "auth_mode": "local_eml_import",
        "folders": [str(source_root)],
        "search": "LOCAL_EML_DIRECTORY_IMPORT",
        "complaint_terms": complaint_terms,
        "min_relevance_score": float(min_relevance_score),
        "address_targets": [],
        "from_address_targets": [],
        "recipient_address_targets": [],
        "domain_targets": [],
        "from_domain_targets": [],
        "recipient_domain_targets": [],
        "scanned_message_count": scanned_count,
        "matched_email_count": len(records),
        "output_dir": str(run_dir),
        "cache_index_path": "",
        "emails": records,
    }
    manifest_path = run_dir / "email_import_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"manifest_path": str(manifest_path), "output_dir": str(run_dir), "email_count": len(records)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import a local directory of .eml files into an email evidence manifest.")
    parser.add_argument("source_dir", help="Directory containing .eml files.")
    parser.add_argument("--output-dir", default="evidence/email_imports", help="Output root for imported email bundles.")
    parser.add_argument("--case-slug", required=True, help="Folder name for this import run.")
    parser.add_argument("--recursive", action="store_true", help="Recursively import .eml files under the source directory.")
    parser.add_argument("--complaint-query", default="", help="Free-text query used to derive complaint relevance terms.")
    parser.add_argument("--complaint-keyword", action="append", default=[], help="Additional complaint keyword. Repeat to add more.")
    parser.add_argument("--min-relevance-score", type=float, default=1.0, help="Skip local .eml messages scoring below this threshold when complaint terms are provided.")
    parser.add_argument("--build-graphrag", action="store_true", help="Build GraphRAG and DuckDB artifacts immediately after import.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = import_local_eml_directory(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        case_slug=args.case_slug,
        recursive=args.recursive,
        complaint_query=args.complaint_query,
        complaint_keywords=list(args.complaint_keyword or []),
        min_relevance_score=float(args.min_relevance_score),
    )
    if args.build_graphrag:
        payload["graphrag_summary"] = build_email_graphrag_artifacts(
            manifest_path=payload["manifest_path"],
            include_attachment_text_in_search=True,
        )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
