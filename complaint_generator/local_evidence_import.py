from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Optional, Sequence

if TYPE_CHECKING:
    from applications.complaint_workspace import ComplaintWorkspaceService


def _slugify_fragment(value: str, *, fallback: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-")
    return text[:80] or fallback


def _normalize_paths(paths: Iterable[str | Path]) -> list[Path]:
    normalized: list[Path] = []
    seen: set[str] = set()
    for item in paths:
        candidate = Path(item).expanduser()
        lookup = str(candidate)
        if not lookup or lookup in seen:
            continue
        seen.add(lookup)
        normalized.append(candidate)
    return normalized


def _default_evidence_root(workspace_root: Path) -> Path:
    if workspace_root.name == "sessions":
        return workspace_root.parent / "evidence"
    return workspace_root / "evidence"


def _iter_files(paths: Sequence[Path]) -> list[Path]:
    files: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        if path.is_file():
            lookup = str(path.resolve())
            if lookup not in seen:
                files.append(path)
                seen.add(lookup)
            continue
        if path.is_dir():
            for child in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
                lookup = str(child.resolve())
                if lookup in seen:
                    continue
                files.append(child)
                seen.add(lookup)
    return files


def _extract_text_preview(path: Path, max_chars: int = 4000) -> str:
    suffix = path.suffix.lower()
    text_like_suffixes = {".txt", ".md", ".json", ".csv", ".eml", ".html", ".htm", ".xml", ".rtf", ".log"}
    if suffix not in text_like_suffixes:
        return ""
    try:
        raw = path.read_bytes()
    except Exception:
        return ""
    if suffix == ".rtf":
        try:
            text = raw.decode("utf-8", errors="ignore")
            text = re.sub(r"\\[a-z]+-?\d* ?", "", text)
            text = text.replace("{", "").replace("}", "")
        except Exception:
            return ""
    else:
        text = raw.decode("utf-8", errors="ignore")
    return text.strip()[:max_chars]


def import_local_evidence(
    *,
    paths: Sequence[str | Path],
    user_id: str,
    claim_element_id: str,
    kind: str = "document",
    workspace_root: str | Path = ".complaint_workspace/sessions",
    evidence_root: str | Path | None = None,
    service: "ComplaintWorkspaceService" | None = None,
) -> dict[str, Any]:
    normalized_paths = _normalize_paths(paths)
    if not normalized_paths:
        raise ValueError("At least one local file or directory path is required")

    workspace_root_path = Path(workspace_root)
    evidence_root_path = Path(evidence_root) if evidence_root is not None else _default_evidence_root(workspace_root_path)
    if service is None:
        from applications.complaint_workspace import ComplaintWorkspaceService

        service = ComplaintWorkspaceService(root_dir=workspace_root_path)

    artifact_root = evidence_root_path / _slugify_fragment(user_id, fallback="anonymous-user") / "local-import"
    artifact_root.mkdir(parents=True, exist_ok=True)

    resolved_files = _iter_files(normalized_paths)
    imported: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for index, original_path in enumerate(resolved_files, start=1):
        try:
            original_resolved = original_path.resolve()
        except Exception:
            skipped.append({"path": str(original_path), "reason": "path could not be resolved"})
            continue
        if not original_resolved.exists() or not original_resolved.is_file():
            skipped.append({"path": str(original_path), "reason": "file not found"})
            continue

        file_fragment = _slugify_fragment(original_resolved.name, fallback=f"artifact-{index}")
        artifact_dir = artifact_root / f"{index:04d}_{file_fragment}"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        copied_path = artifact_dir / original_resolved.name
        copied_path.write_bytes(original_resolved.read_bytes())

        media_type = mimetypes.guess_type(str(original_resolved))[0] or "application/octet-stream"
        preview_text = _extract_text_preview(original_resolved)

        metadata_payload = {
            "original_path": str(original_resolved),
            "copied_path": str(copied_path),
            "filename": original_resolved.name,
            "suffix": original_resolved.suffix.lower(),
            "media_type": media_type,
            "size": int(original_resolved.stat().st_size),
            "preview_text": preview_text,
            "artifact_dir": str(artifact_dir),
        }
        metadata_path = artifact_dir / "metadata.json"
        metadata_path.write_text(json.dumps(metadata_payload, indent=2, sort_keys=True), encoding="utf-8")

        summary_lines = [
            f"File: {original_resolved.name}",
            f"Original path: {original_resolved}",
            f"Media type: {media_type}",
            f"Size: {int(original_resolved.stat().st_size)} bytes",
            f"Artifact directory: {artifact_dir}",
        ]
        if preview_text:
            summary_lines.extend(["", preview_text])

        workspace_record = service.save_evidence(
            user_id,
            kind=kind,
            claim_element_id=claim_element_id,
            title=f"Local import: {original_resolved.name}",
            content="\n".join(summary_lines).strip(),
            source=f"local_artifact_import:{original_resolved}",
            attachment_names=[copied_path.name, metadata_path.name],
        )

        imported.append(
            {
                "original_path": str(original_resolved),
                "artifact_dir": str(artifact_dir),
                "copied_path": str(copied_path),
                "filename": original_resolved.name,
                "media_type": media_type,
                "preview_text": preview_text,
                "workspace_evidence_id": ((workspace_record.get("saved") or {}).get("id")),
            }
        )

    return {
        "status": "success",
        "user_id": user_id,
        "claim_element_id": claim_element_id,
        "kind": kind,
        "workspace_root": str(workspace_root_path),
        "evidence_root": str(evidence_root_path),
        "requested_paths": [str(path) for path in normalized_paths],
        "scanned_file_count": len(resolved_files),
        "imported_count": len(imported),
        "skipped_count": len(skipped),
        "imported": imported,
        "skipped": skipped,
    }


__all__ = ["import_local_evidence"]
