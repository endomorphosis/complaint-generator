from __future__ import annotations

import mailbox
import json
import mimetypes
import re
import zipfile
from email import policy
from email.generator import BytesGenerator
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Optional, Sequence

if TYPE_CHECKING:
    from applications.complaint_workspace import ComplaintWorkspaceService


_CLAIM_ELEMENT_HINTS: dict[str, tuple[str, ...]] = {
    "protected_activity": (
        "hr complaint",
        "reported discrimination",
        "reported harassment",
        "grievance",
        "complaint email",
        "accommodation request",
        "protected activity",
    ),
    "employer_knowledge": (
        "manager knew",
        "hr acknowledged",
        "supervisor notified",
        "received your complaint",
        "reply from hr",
        "knowledge",
    ),
    "adverse_action": (
        "termination",
        "fired",
        "demotion",
        "discipline",
        "suspension",
        "denial notice",
        "eviction",
        "adverse action",
    ),
    "causation": (
        "two days later",
        "shortly after",
        "immediately after",
        "after the hr complaint",
        "retaliation",
        "because you reported",
        "timing",
        "causal",
    ),
    "harm": (
        "lost wages",
        "emotional distress",
        "medical",
        "damages",
        "harm",
        "benefits",
        "rent",
    ),
}


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


def _suggest_claim_element_id(*parts: str) -> tuple[str, dict[str, int]]:
    haystack = " ".join(str(part or "") for part in parts).strip().lower()
    scores = {claim_element_id: 0 for claim_element_id in _CLAIM_ELEMENT_HINTS}
    if haystack:
        for claim_element_id, hints in _CLAIM_ELEMENT_HINTS.items():
            for hint in hints:
                if hint in haystack:
                    scores[claim_element_id] += 1
    best_claim_element_id = max(scores.items(), key=lambda item: (item[1], item[0]))[0]
    if scores[best_claim_element_id] <= 0:
        return "causation", scores
    return best_claim_element_id, scores


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _save_workspace_artifact(
    *,
    service: "ComplaintWorkspaceService",
    user_id: str,
    kind: str,
    claim_element_id: str,
    title: str,
    summary_lines: Sequence[str],
    source: str,
    attachment_names: Sequence[str],
) -> dict[str, Any]:
    return service.save_evidence(
        user_id,
        kind=kind,
        claim_element_id=claim_element_id,
        title=title,
        content="\n".join(str(line) for line in summary_lines if str(line).strip()).strip(),
        source=source,
        attachment_names=list(attachment_names),
    )


def _import_regular_file(
    *,
    original_resolved: Path,
    artifact_root: Path,
    index: int,
    service: "ComplaintWorkspaceService",
    user_id: str,
    claim_element_id: str,
    kind: str,
) -> dict[str, Any]:
    file_fragment = _slugify_fragment(original_resolved.name, fallback=f"artifact-{index}")
    artifact_dir = artifact_root / f"{index:04d}_{file_fragment}"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    copied_path = artifact_dir / original_resolved.name
    copied_path.write_bytes(original_resolved.read_bytes())

    media_type = mimetypes.guess_type(str(original_resolved))[0] or "application/octet-stream"
    preview_text = _extract_text_preview(original_resolved)

    suggested_claim_element_id, suggestion_scores = _suggest_claim_element_id(original_resolved.name, str(original_resolved), preview_text)
    effective_claim_element_id = suggested_claim_element_id if claim_element_id in {"auto", "suggested"} else claim_element_id

    metadata_payload = {
        "original_path": str(original_resolved),
        "copied_path": str(copied_path),
        "filename": original_resolved.name,
        "suffix": original_resolved.suffix.lower(),
        "media_type": media_type,
        "size": int(original_resolved.stat().st_size),
        "preview_text": preview_text,
        "artifact_dir": str(artifact_dir),
        "import_strategy": "file_copy",
        "import_origin_label": "file",
        "requested_claim_element_id": claim_element_id,
        "effective_claim_element_id": effective_claim_element_id,
        "suggested_claim_element_id": suggested_claim_element_id,
        "suggested_claim_element_scores": suggestion_scores,
    }
    metadata_path = artifact_dir / "metadata.json"
    _write_json(metadata_path, metadata_payload)

    summary_lines = [
        f"File: {original_resolved.name}",
        f"Original path: {original_resolved}",
        f"Media type: {media_type}",
        f"Size: {int(original_resolved.stat().st_size)} bytes",
        f"Suggested claim element: {suggested_claim_element_id}",
        f"Saved claim element: {effective_claim_element_id}",
        f"Artifact directory: {artifact_dir}",
    ]
    if preview_text:
        summary_lines.extend(["", preview_text])

    workspace_record = _save_workspace_artifact(
        service=service,
        user_id=user_id,
        kind=kind,
        claim_element_id=effective_claim_element_id,
        title=f"Local import: {original_resolved.name}",
        summary_lines=summary_lines,
        source=f"local_artifact_import:{original_resolved}",
        attachment_names=[copied_path.name, metadata_path.name],
    )

    return {
        "original_path": str(original_resolved),
        "artifact_dir": str(artifact_dir),
        "copied_path": str(copied_path),
        "filename": original_resolved.name,
        "media_type": media_type,
        "preview_text": preview_text,
        "import_origin_label": "file",
        "suggested_claim_element_id": suggested_claim_element_id,
        "effective_claim_element_id": effective_claim_element_id,
        "workspace_evidence_id": ((workspace_record.get("saved") or {}).get("id")),
    }


def _import_zip_archive(
    *,
    archive_path: Path,
    artifact_root: Path,
    index: int,
    service: "ComplaintWorkspaceService",
    user_id: str,
    claim_element_id: str,
    kind: str,
) -> list[dict[str, Any]]:
    imported: list[dict[str, Any]] = []
    archive_fragment = _slugify_fragment(archive_path.name, fallback=f"archive-{index}")
    base_dir = artifact_root / f"{index:04d}_{archive_fragment}"
    base_dir.mkdir(parents=True, exist_ok=True)
    archive_copy_path = base_dir / archive_path.name
    archive_copy_path.write_bytes(archive_path.read_bytes())

    extracted_root = base_dir / "extracted"
    with zipfile.ZipFile(archive_path) as archive:
        member_names = [name for name in archive.namelist() if not name.endswith("/")]
        for member_index, member_name in enumerate(member_names, start=1):
            member_fragment = _slugify_fragment(Path(member_name).name or member_name, fallback=f"member-{member_index}")
            member_dir = base_dir / f"member-{member_index:04d}_{member_fragment}"
            member_dir.mkdir(parents=True, exist_ok=True)
            extracted_path = extracted_root / member_name
            extracted_path.parent.mkdir(parents=True, exist_ok=True)
            extracted_path.write_bytes(archive.read(member_name))

            media_type = mimetypes.guess_type(member_name)[0] or "application/octet-stream"
            preview_text = _extract_text_preview(extracted_path)
            suggested_claim_element_id, suggestion_scores = _suggest_claim_element_id(archive_path.name, member_name, preview_text)
            effective_claim_element_id = suggested_claim_element_id if claim_element_id in {"auto", "suggested"} else claim_element_id
            metadata_payload = {
                "archive_path": str(archive_path),
                "archive_copy_path": str(archive_copy_path),
                "member_name": member_name,
                "extracted_path": str(extracted_path),
                "media_type": media_type,
                "size": int(extracted_path.stat().st_size),
                "preview_text": preview_text,
                "artifact_dir": str(member_dir),
                "import_strategy": "zip_member_extraction",
                "import_origin_label": "zip_member",
                "requested_claim_element_id": claim_element_id,
                "effective_claim_element_id": effective_claim_element_id,
                "suggested_claim_element_id": suggested_claim_element_id,
                "suggested_claim_element_scores": suggestion_scores,
            }
            metadata_path = member_dir / "metadata.json"
            _write_json(metadata_path, metadata_payload)

            workspace_record = _save_workspace_artifact(
                service=service,
                user_id=user_id,
                kind=kind,
                claim_element_id=effective_claim_element_id,
                title=f"Archive import: {archive_path.name} :: {member_name}",
                summary_lines=[
                    f"Archive: {archive_path}",
                    f"Archive copy: {archive_copy_path}",
                    f"Member: {member_name}",
                    f"Media type: {media_type}",
                    f"Suggested claim element: {suggested_claim_element_id}",
                    f"Saved claim element: {effective_claim_element_id}",
                    f"Artifact directory: {member_dir}",
                    "",
                    preview_text,
                ],
                source=f"local_archive_import:{archive_path}!{member_name}",
                attachment_names=[archive_copy_path.name, extracted_path.name, metadata_path.name],
            )
            imported.append(
                {
                    "original_path": str(archive_path),
                    "archive_path": str(archive_path),
                    "archive_member": member_name,
                    "artifact_dir": str(member_dir),
                    "copied_path": str(extracted_path),
                    "filename": Path(member_name).name,
                    "media_type": media_type,
                    "preview_text": preview_text,
                    "import_origin_label": "zip_member",
                    "suggested_claim_element_id": suggested_claim_element_id,
                    "effective_claim_element_id": effective_claim_element_id,
                    "workspace_evidence_id": ((workspace_record.get("saved") or {}).get("id")),
                }
            )
    return imported


def _message_bytes(message: mailbox.mboxMessage) -> bytes:
    buffer = BytesIO()
    generator = BytesGenerator(buffer, policy=policy.default)
    generator.flatten(message)
    return buffer.getvalue()


def _import_mbox_archive(
    *,
    archive_path: Path,
    artifact_root: Path,
    index: int,
    service: "ComplaintWorkspaceService",
    user_id: str,
    claim_element_id: str,
    kind: str,
) -> list[dict[str, Any]]:
    imported: list[dict[str, Any]] = []
    archive_fragment = _slugify_fragment(archive_path.name, fallback=f"mbox-{index}")
    base_dir = artifact_root / f"{index:04d}_{archive_fragment}"
    base_dir.mkdir(parents=True, exist_ok=True)
    archive_copy_path = base_dir / archive_path.name
    archive_copy_path.write_bytes(archive_path.read_bytes())

    message_box = mailbox.mbox(str(archive_path))
    for message_index, message in enumerate(message_box, start=1):
        subject = str(message.get("subject") or "Untitled email").strip()
        sender = str(message.get("from") or "").strip()
        recipient = str(message.get("to") or "").strip()
        body_text = message.get_payload()
        if isinstance(body_text, list):
            body_text = "\n".join(str(part.get_payload(decode=False) or "") for part in body_text)
        body_text = str(body_text or "").strip()[:4000]

        message_fragment = _slugify_fragment(subject, fallback=f"message-{message_index}")
        message_dir = base_dir / f"message-{message_index:04d}_{message_fragment}"
        message_dir.mkdir(parents=True, exist_ok=True)
        eml_path = message_dir / "message.eml"
        eml_path.write_bytes(_message_bytes(message))

        suggested_claim_element_id, suggestion_scores = _suggest_claim_element_id(archive_path.name, subject, sender, recipient, body_text)
        effective_claim_element_id = suggested_claim_element_id if claim_element_id in {"auto", "suggested"} else claim_element_id
        metadata_payload = {
            "archive_path": str(archive_path),
            "archive_copy_path": str(archive_copy_path),
            "subject": subject,
            "from": sender,
            "to": recipient,
            "artifact_dir": str(message_dir),
            "eml_path": str(eml_path),
            "preview_text": body_text,
            "import_strategy": "mbox_message_extraction",
            "import_origin_label": "mbox_message",
            "requested_claim_element_id": claim_element_id,
            "effective_claim_element_id": effective_claim_element_id,
            "suggested_claim_element_id": suggested_claim_element_id,
            "suggested_claim_element_scores": suggestion_scores,
        }
        metadata_path = message_dir / "metadata.json"
        _write_json(metadata_path, metadata_payload)

        workspace_record = _save_workspace_artifact(
            service=service,
            user_id=user_id,
            kind=kind,
            claim_element_id=effective_claim_element_id,
            title=f"Mailbox import: {subject}",
            summary_lines=[
                f"Mailbox: {archive_path}",
                f"Archive copy: {archive_copy_path}",
                f"From: {sender}",
                f"To: {recipient}",
                f"Suggested claim element: {suggested_claim_element_id}",
                f"Saved claim element: {effective_claim_element_id}",
                f"Artifact directory: {message_dir}",
                "",
                body_text,
            ],
            source=f"local_mbox_import:{archive_path}",
            attachment_names=[archive_copy_path.name, eml_path.name, metadata_path.name],
        )
        imported.append(
            {
                "original_path": str(archive_path),
                "archive_path": str(archive_path),
                "artifact_dir": str(message_dir),
                "copied_path": str(eml_path),
                "filename": eml_path.name,
                "media_type": "message/rfc822",
                "preview_text": body_text,
                "import_origin_label": "mbox_message",
                "suggested_claim_element_id": suggested_claim_element_id,
                "effective_claim_element_id": effective_claim_element_id,
                "workspace_evidence_id": ((workspace_record.get("saved") or {}).get("id")),
            }
        )
    return imported


def _import_pst_container(
    *,
    archive_path: Path,
    artifact_root: Path,
    index: int,
    service: "ComplaintWorkspaceService",
    user_id: str,
    claim_element_id: str,
    kind: str,
) -> dict[str, Any]:
    container_import = _import_regular_file(
        original_resolved=archive_path,
        artifact_root=artifact_root,
        index=index,
        service=service,
        user_id=user_id,
        claim_element_id=claim_element_id,
        kind=kind,
    )
    metadata_path = Path(container_import["artifact_dir"]) / "metadata.json"
    metadata_payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata_payload["archive_kind"] = "pst"
    metadata_payload["extraction_status"] = "pst_parser_not_bundled"
    metadata_payload["import_origin_label"] = "pst_container"
    _write_json(metadata_path, metadata_payload)
    container_import["import_origin_label"] = "pst_container"
    return container_import


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

        suffix = original_resolved.suffix.lower()
        if suffix == ".zip":
            imported.extend(
                _import_zip_archive(
                    archive_path=original_resolved,
                    artifact_root=artifact_root,
                    index=index,
                    service=service,
                    user_id=user_id,
                    claim_element_id=claim_element_id,
                    kind=kind,
                )
            )
            continue
        if suffix in {".mbox", ".mbx"}:
            imported.extend(
                _import_mbox_archive(
                    archive_path=original_resolved,
                    artifact_root=artifact_root,
                    index=index,
                    service=service,
                    user_id=user_id,
                    claim_element_id=claim_element_id,
                    kind=kind,
                )
            )
            continue
        if suffix == ".pst":
            imported.append(
                _import_pst_container(
                    archive_path=original_resolved,
                    artifact_root=artifact_root,
                    index=index,
                    service=service,
                    user_id=user_id,
                    claim_element_id=claim_element_id,
                    kind=kind,
                )
            )
            continue

        imported.append(
            _import_regular_file(
                original_resolved=original_resolved,
                artifact_root=artifact_root,
                index=index,
                service=service,
                user_id=user_id,
                claim_element_id=claim_element_id,
                kind=kind,
            )
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
