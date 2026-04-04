#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from complaint_generator.email_graphrag import build_email_graphrag_artifacts


def _merge_terms(manifests: list[dict[str, Any]]) -> list[str]:
    counts: Counter[str] = Counter()
    for manifest in manifests:
        for term in list(manifest.get("complaint_terms") or []):
            cleaned = str(term or "").strip().lower()
            if cleaned:
                counts[cleaned] += 1
    return [term for term, _count in counts.most_common()]


def _record_identity(record: dict[str, Any]) -> str:
    for key in ("message_id_header", "message_key", "raw_sha256", "email_path", "source_eml_path"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    return json.dumps(
        {
            "subject": record.get("subject"),
            "date": record.get("date"),
            "from": record.get("from"),
            "to": record.get("to"),
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def merge_email_manifests(
    *,
    manifest_paths: list[str | Path],
    output_dir: str | Path,
    case_slug: str,
) -> dict[str, Any]:
    manifest_files = [Path(path).expanduser().resolve() for path in manifest_paths]
    manifests = [json.loads(path.read_text(encoding="utf-8")) for path in manifest_files]

    seen: set[str] = set()
    merged_records: list[dict[str, Any]] = []
    source_records = 0
    duplicate_count = 0
    for manifest_file, manifest in zip(manifest_files, manifests):
        for record in list(manifest.get("emails") or []):
            source_records += 1
            identity = _record_identity(record)
            if identity in seen:
                duplicate_count += 1
                continue
            seen.add(identity)
            merged_record = dict(record)
            merged_record["source_manifest_path"] = str(manifest_file)
            merged_records.append(merged_record)

    merged_records.sort(
        key=lambda record: (
            str(record.get("date") or ""),
            str(record.get("subject") or ""),
            str(record.get("message_id_header") or record.get("raw_sha256") or ""),
        )
    )

    output_root = Path(output_dir).expanduser().resolve()
    run_dir = output_root / case_slug
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "status": "success",
        "server": "local_workspace",
        "username": "",
        "auth_mode": "merged_email_manifests",
        "folders": [str(path.parent) for path in manifest_files],
        "search": "MERGED_EMAIL_MANIFESTS",
        "complaint_terms": _merge_terms(manifests),
        "min_relevance_score": max(float(manifest.get("min_relevance_score") or 0.0) for manifest in manifests) if manifests else 0.0,
        "address_targets": [],
        "from_address_targets": [],
        "recipient_address_targets": [],
        "domain_targets": [],
        "from_domain_targets": [],
        "recipient_domain_targets": [],
        "scanned_message_count": source_records,
        "matched_email_count": len(merged_records),
        "output_dir": str(run_dir),
        "cache_index_path": "",
        "source_manifest_paths": [str(path) for path in manifest_files],
        "duplicate_email_count": duplicate_count,
        "emails": merged_records,
    }
    manifest_path = run_dir / "email_import_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "manifest_path": str(manifest_path),
        "output_dir": str(run_dir),
        "email_count": len(merged_records),
        "duplicate_email_count": duplicate_count,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge existing email import manifests into one deduplicated manifest.")
    parser.add_argument("manifest_paths", nargs="+", help="Input email_import_manifest.json files.")
    parser.add_argument("--output-dir", default="evidence/email_imports", help="Output root for the merged manifest.")
    parser.add_argument("--case-slug", required=True, help="Folder name for this merged run.")
    parser.add_argument("--build-graphrag", action="store_true", help="Build GraphRAG and DuckDB artifacts after merge.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = merge_email_manifests(
        manifest_paths=list(args.manifest_paths),
        output_dir=args.output_dir,
        case_slug=args.case_slug,
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
