from __future__ import annotations

import anyio
import email
import email.policy
import imaplib
import json
import re
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Optional, Sequence

from ipfs_datasets_py.processors.multimedia.email_processor import create_email_processor
from .evidence_relevance import build_complaint_terms, score_email_relevance
from .email_oauth import build_xoauth2_bytes, resolve_gmail_oauth_access_token

if TYPE_CHECKING:
    from applications.complaint_workspace import ComplaintWorkspaceService


def _slugify_fragment(value: str, *, fallback: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-")
    return text[:80] or fallback


def _normalize_addresses(addresses: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in addresses:
        value = str(item or "").strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _normalize_items(values: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        value = str(item or "").strip()
        lookup = value.lower()
        if not value or lookup in seen:
            continue
        seen.add(lookup)
        normalized.append(value)
    return normalized


def _extract_header_addresses(message: email.message.EmailMessage) -> set[str]:
    header_values = [
        str(message.get("From", "") or ""),
        str(message.get("To", "") or ""),
        str(message.get("Cc", "") or ""),
        str(message.get("Bcc", "") or ""),
        str(message.get("Reply-To", "") or ""),
    ]
    addresses: set[str] = set()
    for value in header_values:
        for _, addr in getaddresses([value]):
            normalized = str(addr or "").strip().lower()
            if normalized:
                addresses.add(normalized)
    return addresses


def _extract_header_addresses_from_raw(raw_message: bytes) -> set[str]:
    try:
        parsed = BytesParser(policy=policy.default).parsebytes(raw_message)
    except Exception:
        return set()
    addresses: set[str] = set()
    for header_name in ("from", "to", "cc", "bcc", "reply-to", "sender"):
        header = parsed.get(header_name)
        header_addresses = getattr(header, "addresses", ()) or ()
        for entry in header_addresses:
            username = str(getattr(entry, "username", "") or "").strip()
            domain = str(getattr(entry, "domain", "") or "").strip()
            if username and domain:
                addresses.add(f"{username}@{domain}".lower())
    return addresses


def _message_matches_addresses(message: email.message.EmailMessage, addresses: Sequence[str]) -> bool:
    if not addresses:
        return True
    header_addresses = _extract_header_addresses(message)
    return any(address in header_addresses for address in addresses)


def _extract_body_text(message: email.message.EmailMessage) -> str:
    body_parts: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if (part.get_content_disposition() or "").lower() == "attachment":
                continue
            if part.get_content_type() != "text/plain":
                continue
            try:
                body_parts.append(part.get_content())
            except (UnicodeDecodeError, LookupError, AttributeError):
                payload = part.get_payload(decode=True) or b""
                body_parts.append(payload.decode("utf-8", errors="ignore"))
    else:
        try:
            body_parts.append(message.get_content())
        except (UnicodeDecodeError, LookupError, AttributeError):
            payload = message.get_payload(decode=True) or b""
            body_parts.append(payload.decode("utf-8", errors="ignore"))
    return "\n".join(part.strip() for part in body_parts if str(part or "").strip()).strip()


def _extract_attachment_payloads(message: email.message.EmailMessage) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        disposition = (part.get_content_disposition() or "").lower()
        if not filename and disposition != "attachment":
            continue
        payload = part.get_payload(decode=True) or b""
        attachments.append(
            {
                "filename": _slugify_fragment(str(filename or "attachment.bin"), fallback="attachment.bin"),
                "content_type": str(part.get_content_type() or "application/octet-stream"),
                "size": len(payload),
                "data": payload,
            }
        )
    return attachments


def _default_evidence_root(workspace_root: Path) -> Path:
    if workspace_root.name == "sessions":
        return workspace_root.parent / "evidence"
    return workspace_root / "evidence"


def _checkpoint_path(artifact_root: Path, checkpoint_name: Optional[str]) -> Path:
    name = _slugify_fragment(str(checkpoint_name or "default"), fallback="default")
    return artifact_root / "_state" / f"{name}_checkpoint.json"


def _load_checkpoint(artifact_root: Path, checkpoint_name: Optional[str]) -> dict[str, Any]:
    path = _checkpoint_path(artifact_root, checkpoint_name)
    if not path.exists():
        return {"version": 1, "folders": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "folders": {}}
    payload.setdefault("version", 1)
    payload.setdefault("folders", {})
    return payload


def _save_checkpoint(artifact_root: Path, checkpoint_name: Optional[str], payload: dict[str, Any]) -> Path:
    path = _checkpoint_path(artifact_root, checkpoint_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _coerce_message_uid(value: bytes | str | int | None) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    text = str(value or "").strip()
    try:
        return int(text)
    except Exception:
        return 0


def _build_email_import_manifest(
    *,
    artifact_root: Path,
    gmail_user: Optional[str],
    folder: str,
    folders: Sequence[str],
    user_id: str,
    claim_element_id: str,
    workspace_root: Path,
    evidence_root: Path,
    matched_addresses: Sequence[str],
    complaint_terms: Sequence[str],
    min_relevance_score: float,
    searched_message_count: int,
    skipped_count: int,
    relevance_filtered_count: int,
    imported: Sequence[dict[str, Any]],
    limit: Optional[int],
    date_after: Optional[str],
    date_before: Optional[str],
    use_uid_checkpoint: bool = False,
    uid_window_size: Optional[int] = None,
    checkpoint_path: Optional[Path] = None,
    checkpoint_payload: Optional[dict[str, Any]] = None,
) -> Path:
    manifest_payload = {
        "status": "success",
        "gmail_user": gmail_user or "",
        "folder": folder,
        "folders": list(folders),
        "user_id": user_id,
        "claim_element_id": claim_element_id,
        "workspace_root": str(workspace_root),
        "evidence_root": str(evidence_root),
        "output_dir": str(artifact_root),
        "matched_addresses": list(matched_addresses),
        "complaint_terms": list(complaint_terms),
        "min_relevance_score": float(min_relevance_score),
        "limit": int(limit) if limit is not None else None,
        "date_after": date_after,
        "date_before": date_before,
        "use_uid_checkpoint": bool(use_uid_checkpoint),
        "uid_window_size": int(uid_window_size) if uid_window_size is not None else None,
        "searched_message_count": int(searched_message_count),
        "matched_email_count": len(imported),
        "imported_count": len(imported),
        "skipped_count": int(skipped_count),
        "relevance_filtered_count": int(relevance_filtered_count),
        "raw_email_total_bytes": sum(int(item.get("raw_size_bytes") or 0) for item in imported),
        "attachment_total": sum(len(item.get("attachment_paths") or []) for item in imported),
        "checkpoint_path": str(checkpoint_path) if checkpoint_path is not None else None,
        "checkpoint": checkpoint_payload or None,
        "emails": list(imported),
        "mediator_evidence_records": [
            {
                "title": f"Email import: {item.get('subject') or 'Untitled email'}",
                "kind": "document",
                "source": f"gmail_imap_import:{item.get('folder') or folder}",
                "content": (
                    f"Subject: {item.get('subject') or ''}\n"
                    f"From: {item.get('from') or ''}\n"
                    f"To: {item.get('to') or ''}\n"
                    f"Date: {item.get('date') or ''}\n"
                    f"Saved email: {item.get('eml_path') or ''}"
                ).strip(),
                "attachment_names": [Path(path).name for path in list(item.get("attachment_paths") or [])],
                "metadata": {
                    "folder": item.get("folder"),
                    "message_id": item.get("message_id"),
                    "message_id_header": item.get("message_id_header"),
                    "artifact_dir": item.get("artifact_dir"),
                    "eml_path": item.get("eml_path"),
                    "metadata_path": item.get("metadata_path"),
                    "participants": list(item.get("participants") or []),
                    "relevance_score": float(item.get("relevance_score") or 0.0),
                },
            }
            for item in imported
        ],
    }
    manifest_path = artifact_root / "email_import_manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_path


async def _search_message_ids(
    connection: Any,
    *,
    folder: str,
    date_after: Optional[str],
    date_before: Optional[str],
    limit: Optional[int] = None,
) -> list[bytes]:
    def _run() -> list[bytes]:
        status, _ = connection.select(folder, readonly=True)
        if status != "OK":
            raise RuntimeError(f"failed to open IMAP folder {folder!r}: {status}")
        if limit is not None and limit > 0 and not date_after and not date_before:
            status, count_data = connection.select(folder, readonly=True)
            if status != "OK":
                raise RuntimeError(f"failed to open IMAP folder {folder!r}: {status}")
            total_messages = int((count_data or [b"0"])[0] or b"0")
            start = max(1, total_messages - int(limit) + 1)
            return [str(index).encode("ascii") for index in range(start, total_messages + 1)]
        criteria: list[str] = []
        if date_after:
            after_value = datetime.fromisoformat(str(date_after)).strftime("%d-%b-%Y")
            criteria.extend(["SINCE", after_value])
        if date_before:
            before_value = datetime.fromisoformat(str(date_before)).strftime("%d-%b-%Y")
            criteria.extend(["BEFORE", before_value])
        if not criteria:
            criteria = ["ALL"]
        status, data = connection.search(None, *criteria)
        if status != "OK":
            raise RuntimeError(f"failed to search IMAP folder {folder!r}: {status}")
        raw_ids = data[0] if data else b""
        return [item for item in raw_ids.split() if item]

    return await anyio.to_thread.run_sync(_run)


async def _fetch_recent_message_ids(connection: Any, *, folder: str, limit: int) -> list[bytes]:
    def _run() -> list[bytes]:
        status, count_data = connection.select(folder, readonly=True)
        if status != "OK":
            raise RuntimeError(f"failed to open IMAP folder {folder!r}: {status}")
        total_messages = int((count_data or [b"0"])[0] or b"0")
        start = max(1, total_messages - max(0, int(limit)) + 1)
        return [str(index).encode("ascii") for index in range(start, total_messages + 1)]

    return await anyio.to_thread.run_sync(_run)


async def _search_message_uids(
    connection: Any,
    *,
    folder: str,
    date_after: Optional[str],
    date_before: Optional[str],
    after_uid: Optional[int] = None,
) -> list[bytes]:
    def _run() -> list[bytes]:
        status, _ = connection.select(folder, readonly=True)
        if status != "OK":
            raise RuntimeError(f"failed to open IMAP folder {folder!r}: {status}")
        criteria: list[str] = []
        if after_uid and int(after_uid) > 0:
            criteria.extend(["UID", f"{int(after_uid) + 1}:*"])
        if date_after:
            after_value = datetime.fromisoformat(str(date_after)).strftime("%d-%b-%Y")
            criteria.extend(["SINCE", after_value])
        if date_before:
            before_value = datetime.fromisoformat(str(date_before)).strftime("%d-%b-%Y")
            criteria.extend(["BEFORE", before_value])
        if not criteria:
            criteria = ["ALL"]
        status, data = connection.uid("search", None, *criteria)
        if status != "OK":
            raise RuntimeError(f"failed to UID search IMAP folder {folder!r}: {status}")
        raw_ids = data[0] if data else b""
        return [item for item in raw_ids.split() if item]

    return await anyio.to_thread.run_sync(_run)


async def _fetch_raw_message(connection: Any, message_id: bytes) -> bytes:
    def _run() -> bytes:
        status, data = connection.fetch(message_id, "(RFC822)")
        if status != "OK":
            raise RuntimeError(f"failed to fetch IMAP message {message_id!r}: {status}")
        for item in data or []:
            if isinstance(item, tuple) and len(item) >= 2:
                return bytes(item[1] or b"")
        raise RuntimeError(f"missing RFC822 payload for IMAP message {message_id!r}")

    return await anyio.to_thread.run_sync(_run)


async def _fetch_raw_message_by_uid(connection: Any, uid: bytes) -> bytes:
    def _run() -> bytes:
        status, data = connection.uid("fetch", uid, "(RFC822)")
        if status != "OK":
            raise RuntimeError(f"failed to fetch IMAP UID {uid!r}: {status}")
        for item in data or []:
            if isinstance(item, tuple) and len(item) >= 2:
                return bytes(item[1] or b"")
        raise RuntimeError(f"missing RFC822 payload for IMAP UID {uid!r}")

    return await anyio.to_thread.run_sync(_run)


async def _connect_processor_with_xoauth2(processor: Any, *, gmail_user: str, access_token: str) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        connection = imaplib.IMAP4_SSL(processor.server, processor.port, timeout=processor.timeout)
        xoauth2 = build_xoauth2_bytes(gmail_user, access_token)
        connection.authenticate("XOAUTH2", lambda _challenge: xoauth2)
        processor.connection = connection
        processor.connected = True
        return {
            "status": "success",
            "protocol": "imap",
            "server": processor.server,
            "port": processor.port,
            "username": gmail_user,
            "connected": True,
            "auth_mode": "gmail_oauth",
        }

    return await anyio.to_thread.run_sync(_run)


async def import_gmail_evidence(
    *,
    addresses: Sequence[str],
    user_id: str,
    claim_element_id: str,
    workspace_root: str | Path = ".complaint_workspace/sessions",
    evidence_root: str | Path | None = None,
    folder: str = "INBOX",
    folders: Sequence[str] = (),
    limit: Optional[int] = None,
    date_after: Optional[str] = None,
    date_before: Optional[str] = None,
    gmail_user: Optional[str] = None,
    gmail_app_password: Optional[str] = None,
    use_gmail_oauth: bool = False,
    gmail_oauth_client_secrets: Optional[str] = None,
    gmail_oauth_token_cache: Optional[str] = None,
    gmail_oauth_open_browser: bool = True,
    complaint_query: Optional[str] = None,
    complaint_keywords: Sequence[str] = (),
    complaint_keyword_files: Sequence[str] = (),
    min_relevance_score: float = 0.0,
    use_uid_checkpoint: bool = False,
    checkpoint_name: Optional[str] = None,
    uid_window_size: Optional[int] = None,
    service: "ComplaintWorkspaceService" | None = None,
) -> dict[str, Any]:
    normalized_addresses = _normalize_addresses(addresses)
    if not normalized_addresses:
        raise ValueError("At least one target email address is required")
    complaint_terms = build_complaint_terms(
        complaint_query=complaint_query,
        complaint_keywords=complaint_keywords,
        complaint_keyword_files=complaint_keyword_files,
    )

    workspace_root_path = Path(workspace_root)
    evidence_root_path = Path(evidence_root) if evidence_root is not None else _default_evidence_root(workspace_root_path)
    normalized_folders = _normalize_items(folders) if folders else []
    if not normalized_folders:
        normalized_folders = [str(folder or "INBOX").strip() or "INBOX"]
    if service is None:
        from applications.complaint_workspace import ComplaintWorkspaceService

        service = ComplaintWorkspaceService(root_dir=workspace_root_path)

    processor = create_email_processor(
        protocol="imap",
        server="imap.gmail.com",
        username=gmail_user,
        password=gmail_app_password,
        use_ssl=True,
    )

    artifact_root = evidence_root_path / _slugify_fragment(user_id, fallback="anonymous-user") / "gmail-import"
    artifact_root.mkdir(parents=True, exist_ok=True)
    checkpoint_payload = _load_checkpoint(artifact_root, checkpoint_name) if use_uid_checkpoint else None
    checkpoint_file_path = _checkpoint_path(artifact_root, checkpoint_name) if use_uid_checkpoint else None

    oauth_token_payload: dict[str, Any] | None = None
    if use_gmail_oauth:
        if not gmail_user:
            raise ValueError("gmail_user is required when use_gmail_oauth=True")
        if not gmail_oauth_client_secrets:
            raise ValueError("gmail_oauth_client_secrets is required when use_gmail_oauth=True")
        access_token, oauth_token_payload = resolve_gmail_oauth_access_token(
            gmail_user=gmail_user,
            client_secrets_path=gmail_oauth_client_secrets,
            token_cache_path=gmail_oauth_token_cache,
            open_browser=gmail_oauth_open_browser,
        )
        await _connect_processor_with_xoauth2(processor, gmail_user=gmail_user, access_token=access_token)
    else:
        await processor.connect()
    try:
        imported: list[dict[str, Any]] = []
        skipped_count = 0
        relevance_filtered_count = 0
        searched_message_count = 0
        seen_message_headers: set[str] = set()
        global_index = 0
        for folder_name in normalized_folders:
            folder_last_processed_uid = 0
            try:
                if use_uid_checkpoint:
                    folder_state = (checkpoint_payload or {}).setdefault("folders", {}).setdefault(folder_name, {})
                    folder_last_processed_uid = int(folder_state.get("last_processed_uid") or 0)
                    message_ids = await _search_message_uids(
                        processor.connection,
                        folder=folder_name,
                        date_after=date_after,
                        date_before=date_before,
                        after_uid=folder_last_processed_uid,
                    )
                    cap = uid_window_size if uid_window_size is not None else limit
                    if cap is not None and int(cap) > 0:
                        message_ids = message_ids[: int(cap)]
                else:
                    message_ids = await _search_message_ids(
                        processor.connection,
                        folder=folder_name,
                        date_after=date_after,
                        date_before=date_before,
                        limit=limit,
                    )
                    if limit is not None and limit > 0 and (date_after or date_before):
                        message_ids = message_ids[-int(limit) :]
            except imaplib.IMAP4.error as exc:
                if not (limit is not None and limit > 0 and "got more than 1000000 bytes" in str(exc)):
                    raise
                message_ids = await _fetch_recent_message_ids(processor.connection, folder=folder_name, limit=int(limit))

            searched_message_count += len(message_ids)
            iterable_message_ids = message_ids if use_uid_checkpoint else list(reversed(message_ids))
            for message_id in iterable_message_ids:
                if use_uid_checkpoint:
                    folder_last_processed_uid = max(folder_last_processed_uid, _coerce_message_uid(message_id))
                    raw_message = await _fetch_raw_message_by_uid(processor.connection, message_id)
                else:
                    raw_message = await _fetch_raw_message(processor.connection, message_id)
                parsed_message = email.message_from_bytes(raw_message, policy=email.policy.default)
                message_header_id = str(parsed_message.get("Message-ID") or "").strip().lower()
                if message_header_id and message_header_id in seen_message_headers:
                    continue
                if message_header_id:
                    seen_message_headers.add(message_header_id)
                header_addresses = _extract_header_addresses(parsed_message) | _extract_header_addresses_from_raw(raw_message)
                if normalized_addresses and not any(address in header_addresses for address in normalized_addresses):
                    skipped_count += 1
                    continue

                subject = str(parsed_message.get("Subject") or "").strip() or "Untitled email"
                sender = str(parsed_message.get("From") or "").strip()
                recipient = str(parsed_message.get("To") or "").strip()
                email_date = str(parsed_message.get("Date") or "").strip()
                body_text = _extract_body_text(parsed_message)
                attachments = _extract_attachment_payloads(parsed_message)
                participants = sorted(header_addresses)
                relevance = score_email_relevance(
                    complaint_terms=complaint_terms,
                    subject=subject,
                    sender=sender,
                    recipient=recipient,
                    cc=str(parsed_message.get("Cc") or "").strip(),
                    reply_to=str(parsed_message.get("Reply-To") or "").strip(),
                    body_text=body_text,
                    attachment_names=[str(item.get("filename") or "") for item in attachments],
                )
                if complaint_terms and float(relevance["score"]) < float(min_relevance_score):
                    relevance_filtered_count += 1
                    continue

                global_index += 1
                date_fragment = "undated"
                try:
                    if email_date:
                        date_fragment = parsedate_to_datetime(email_date).strftime("%Y%m%d")
                except Exception:
                    pass
                message_dir = artifact_root / f"{global_index:04d}_{date_fragment}_{_slugify_fragment(subject, fallback='email')}"
                message_dir.mkdir(parents=True, exist_ok=True)

                eml_path = message_dir / "message.eml"
                eml_path.write_bytes(raw_message)

                saved_attachments: list[dict[str, Any]] = []
                attachment_names: list[str] = [eml_path.name]
                attachments_dir = message_dir / "attachments"
                for attachment in attachments:
                    attachments_dir.mkdir(parents=True, exist_ok=True)
                    attachment_path = attachments_dir / attachment["filename"]
                    attachment_path.write_bytes(bytes(attachment["data"]))
                    saved_attachments.append(
                        {
                            "filename": attachment["filename"],
                            "path": str(attachment_path),
                            "content_type": attachment["content_type"],
                            "size": int(attachment["size"] or 0),
                        }
                    )
                    attachment_names.append(attachment["filename"])

                metadata_payload = {
                    "subject": subject,
                    "from": sender,
                    "to": recipient,
                    "cc": str(parsed_message.get("Cc") or "").strip(),
                    "date": email_date,
                    "folder": folder_name,
                    "message_id_header": str(parsed_message.get("Message-ID") or "").strip(),
                    "matched_addresses": normalized_addresses,
                    "relevance_score": float(relevance["score"]),
                    "matched_terms": list(relevance["matched_terms"]),
                    "matched_fields": list(relevance["matched_fields"]),
                    "attachment_count": len(saved_attachments),
                    "attachments": saved_attachments,
                    "participants": participants,
                    "body_preview": body_text[:4000],
                    "raw_size_bytes": len(raw_message),
                    "artifact_dir": str(message_dir),
                    "eml_path": str(eml_path),
                }
                metadata_path = message_dir / "message.json"
                metadata_path.write_text(
                    json.dumps(metadata_payload, indent=2, sort_keys=True, ensure_ascii=False),
                    encoding="utf-8",
                )
                attachment_names.append(metadata_path.name)

                summary_lines = [
                    f"Subject: {subject}",
                    f"Folder: {folder_name}",
                    f"From: {sender}",
                    f"To: {recipient}",
                    f"Date: {email_date}",
                    f"Matched addresses: {', '.join(normalized_addresses)}",
                    f"Artifact directory: {message_dir}",
                ]
                if body_text:
                    summary_lines.extend(["", body_text[:4000]])

                workspace_record = service.save_evidence(
                    user_id,
                    kind="document",
                    claim_element_id=claim_element_id,
                    title=f"Email import: {subject}",
                    content="\n".join(summary_lines).strip(),
                    source=f"gmail_imap_import:{folder_name}",
                    attachment_names=attachment_names,
                )

                imported.append(
                    {
                        "message_id": message_id.decode("utf-8", errors="ignore"),
                        "imap_uid": _coerce_message_uid(message_id) if use_uid_checkpoint else None,
                        "message_id_header": str(parsed_message.get("Message-ID") or "").strip(),
                        "folder": folder_name,
                        "subject": subject,
                        "from": sender,
                        "to": recipient,
                        "date": email_date,
                        "relevance_score": float(relevance["score"]),
                        "matched_terms": list(relevance["matched_terms"]),
                        "matched_fields": list(relevance["matched_fields"]),
                        "participants": participants,
                        "raw_size_bytes": len(raw_message),
                        "artifact_dir": str(message_dir),
                        "bundle_dir": str(message_dir),
                        "eml_path": str(eml_path),
                        "email_path": str(eml_path),
                        "metadata_path": str(metadata_path),
                        "parsed_path": str(metadata_path),
                        "attachment_paths": [item["path"] for item in saved_attachments],
                        "workspace_evidence_id": ((workspace_record.get("saved") or {}).get("id")),
                    }
                )

            if use_uid_checkpoint and checkpoint_payload is not None:
                folder_state = checkpoint_payload.setdefault("folders", {}).setdefault(folder_name, {})
                folder_state["last_processed_uid"] = int(folder_last_processed_uid or 0)
                folder_state["last_run_searched_message_count"] = len(message_ids)
                folder_state["updated_at"] = datetime.now(UTC).isoformat()

        if use_uid_checkpoint and checkpoint_payload is not None:
            checkpoint_file_path = _save_checkpoint(artifact_root, checkpoint_name, checkpoint_payload)

        manifest_path = _build_email_import_manifest(
            artifact_root=artifact_root,
            gmail_user=gmail_user,
            folder=folder,
            folders=normalized_folders,
            user_id=user_id,
            claim_element_id=claim_element_id,
            workspace_root=workspace_root_path,
            evidence_root=evidence_root_path,
            matched_addresses=normalized_addresses,
            complaint_terms=complaint_terms,
            min_relevance_score=float(min_relevance_score),
            searched_message_count=searched_message_count,
            skipped_count=skipped_count,
            relevance_filtered_count=relevance_filtered_count,
            imported=imported,
            limit=limit,
            date_after=date_after,
            date_before=date_before,
            use_uid_checkpoint=use_uid_checkpoint,
            uid_window_size=uid_window_size,
            checkpoint_path=checkpoint_file_path,
            checkpoint_payload=checkpoint_payload,
        )
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if use_gmail_oauth:
            manifest_payload["gmail_oauth"] = {
                "client_secrets_path": str(Path(gmail_oauth_client_secrets).expanduser().resolve()) if gmail_oauth_client_secrets else "",
                "token_cache_path": str(Path(gmail_oauth_token_cache).expanduser().resolve()) if gmail_oauth_token_cache else "",
                "open_browser": bool(gmail_oauth_open_browser),
                "expires_at": (oauth_token_payload or {}).get("expires_at"),
                "has_refresh_token": bool((oauth_token_payload or {}).get("refresh_token")),
            }
            manifest_path.write_text(json.dumps(manifest_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "status": "success",
            "gmail_user": gmail_user or "",
            "folder": folder,
            "folders": normalized_folders,
            "claim_element_id": claim_element_id,
            "user_id": user_id,
            "workspace_root": str(workspace_root_path),
            "evidence_root": str(evidence_root_path),
            "matched_addresses": normalized_addresses,
            "complaint_terms": complaint_terms,
            "min_relevance_score": float(min_relevance_score),
            "auth_mode": "gmail_oauth" if use_gmail_oauth else "gmail_app_password",
            "use_uid_checkpoint": bool(use_uid_checkpoint),
            "uid_window_size": int(uid_window_size) if uid_window_size is not None else None,
            "searched_message_count": searched_message_count,
            "imported_count": len(imported),
            "skipped_count": skipped_count,
            "relevance_filtered_count": relevance_filtered_count,
            "raw_email_total_bytes": sum(int(item.get("raw_size_bytes") or 0) for item in imported),
            "manifest_path": str(manifest_path),
            "checkpoint_path": str(checkpoint_file_path) if checkpoint_file_path is not None else None,
            "checkpoint": checkpoint_payload,
            "gmail_oauth": (
                {
                    "client_secrets_path": str(Path(gmail_oauth_client_secrets).expanduser().resolve()) if gmail_oauth_client_secrets else "",
                    "token_cache_path": str(Path(gmail_oauth_token_cache).expanduser().resolve()) if gmail_oauth_token_cache else "",
                    "open_browser": bool(gmail_oauth_open_browser),
                    "expires_at": (oauth_token_payload or {}).get("expires_at"),
                    "has_refresh_token": bool((oauth_token_payload or {}).get("refresh_token")),
                }
                if use_gmail_oauth
                else None
            ),
            "imported": imported,
        }
    finally:
        await processor.disconnect()


__all__ = ["import_gmail_evidence"]
