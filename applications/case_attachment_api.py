"""HTTP owner for encrypted shared attachments and derived artifacts.

The browser session supplies the actor. Bodies cannot mint a role, a key, or
a grant. Filenames, previews, and derived indexes are returned only from a
download that has just rechecked the actor grant. Listing stays opaque.

Admission is JSON base64 inside the existing case body limit. This route does
not accept multipart uploads and does not claim a streaming transport.
"""

from __future__ import annotations

import base64
from typing import Any, Mapping

from starlette.requests import Request

from integrations.private_collaboration import (
    BROWSER_KEY_FIELDS,
    SharedAttachmentError,
    SharedAttachmentStore,
    UserOwnedKeySession,
    attachment_http_status,
)

TASK_ID = "CIMP-GUI-37"


class CaseAttachmentService:
    """Route-facing facade. Key sessions are injected by the operator."""

    def __init__(self, store: SharedAttachmentStore, sessions: Mapping[str, UserOwnedKeySession]) -> None:
        if not isinstance(store, SharedAttachmentStore) or not isinstance(sessions, Mapping):
            raise SharedAttachmentError("authority_owners")
        self._store = store
        self._sessions = dict(sessions)
        for principal_id, session in self._sessions.items():
            if not isinstance(principal_id, str) or not isinstance(session, UserOwnedKeySession):
                raise SharedAttachmentError("key_owner_required")

    @property
    def store(self) -> SharedAttachmentStore:
        return self._store

    def store_attachment(self, actor_principal_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        material = self._body(body)
        content = self._content(material)
        session = self._session(actor_principal_id)
        delegated = isinstance(material.get("key_grant_id"), str)
        if not delegated:
            return self._store.store(
                actor_principal_id=actor_principal_id,
                tenant_id=str(material.get("tenant_id") or ""),
                case_id=str(material.get("case_id") or ""),
                resource_id=str(material.get("resource_id") or ""),
                artifact_revision=str(material.get("artifact_revision") or ""),
                filename=str(material.get("filename") or ""),
                media_type=str(material.get("media_type") or ""),
                content=content,
                idempotency_key=str(material.get("idempotency_key") or ""),
                owner_session=session,
            )
        version = material.get("membership_version")
        return self._store.store(
            actor_principal_id=actor_principal_id,
            tenant_id=str(material.get("tenant_id") or ""),
            case_id=str(material.get("case_id") or ""),
            resource_id=str(material.get("resource_id") or ""),
            artifact_revision=str(material.get("artifact_revision") or ""),
            filename=str(material.get("filename") or ""),
            media_type=str(material.get("media_type") or ""),
            content=content,
            idempotency_key=str(material.get("idempotency_key") or ""),
            recipient_session=session,
            membership_grant_id=material.get("membership_grant_id") if isinstance(material.get("membership_grant_id"), str) else None,
            membership_version=version if type(version) is int else None,
            key_grant_id=material.get("key_grant_id") if isinstance(material.get("key_grant_id"), str) else None,
        )

    def list_attachments(self, actor_principal_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        material = self._body(body)
        version = material.get("membership_version")
        return self._store.list_public(
            actor_principal_id=actor_principal_id,
            tenant_id=str(material.get("tenant_id") or ""),
            case_id=str(material.get("case_id") or ""),
            resource_id=str(material.get("resource_id") or ""),
            membership_grant_id=material.get("membership_grant_id") if isinstance(material.get("membership_grant_id"), str) else None,
            membership_version=version if type(version) is int else None,
        )

    def download_attachment(self, actor_principal_id: str, attachment_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        material = self._body(body)
        session = self._session(actor_principal_id)
        version = material.get("membership_version")
        role = material.get("artifact_role") if isinstance(material.get("artifact_role"), str) else "content"
        if not isinstance(material.get("key_grant_id"), str):
            return self._store.download(
                actor_principal_id=actor_principal_id,
                tenant_id=str(material.get("tenant_id") or ""),
                case_id=str(material.get("case_id") or ""),
                resource_id=str(material.get("resource_id") or ""),
                attachment_id=attachment_id,
                owner_session=session,
                role=role,
            )
        return self._store.download(
            actor_principal_id=actor_principal_id,
            tenant_id=str(material.get("tenant_id") or ""),
            case_id=str(material.get("case_id") or ""),
            resource_id=str(material.get("resource_id") or ""),
            attachment_id=attachment_id,
            recipient_session=session,
            membership_grant_id=material.get("membership_grant_id") if isinstance(material.get("membership_grant_id"), str) else None,
            membership_version=version if type(version) is int else None,
            key_grant_id=material.get("key_grant_id") if isinstance(material.get("key_grant_id"), str) else None,
            role=role,
        )

    def _session(self, actor_principal_id: str) -> UserOwnedKeySession:
        session = self._sessions.get(actor_principal_id)
        if not isinstance(session, UserOwnedKeySession):
            raise SharedAttachmentError("key_owner_required")
        return session

    def _body(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(body, Mapping):
            raise SharedAttachmentError("request_body")
        if any(name in body for name in BROWSER_KEY_FIELDS):
            raise SharedAttachmentError("browser_key_rejected")
        return body

    def _content(self, body: Mapping[str, Any]) -> bytes:
        encoded = body.get("content_base64")
        if not isinstance(encoded, str) or encoded.strip() == "":
            raise SharedAttachmentError("content_rejected")
        try:
            return base64.b64decode(encoded.encode("ascii"), validate=True)
        except (UnicodeEncodeError, ValueError) as exc:
            raise SharedAttachmentError("content_rejected") from exc


def mount_case_attachments(app: Any) -> None:
    """Mount attachment routes on the authenticated case catalog boundary."""

    from fastapi.responses import JSONResponse

    def _service(request: Any) -> CaseAttachmentService:
        service = getattr(request.app.state, "case_attachments", None)
        if not isinstance(service, CaseAttachmentService):
            raise SharedAttachmentError("attachment_unavailable")
        return service

    def _actor(request: Any) -> str:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        if not isinstance(actor, str) or actor == "":
            raise SharedAttachmentError("unauthenticated")
        return actor

    def _material(request: Any) -> Mapping[str, Any]:
        material = getattr(request.state, "case_catalog_material", None)
        return material if isinstance(material, dict) else {}

    def _fail(exc: SharedAttachmentError) -> JSONResponse:
        return JSONResponse({"error": exc.code}, status_code=attachment_http_status(exc.code))

    @app.post("/api/cases/attachments")
    async def attachment_store(request: Request):
        try:
            created = _service(request).store_attachment(_actor(request), _material(request))
        except SharedAttachmentError as exc:
            return _fail(exc)
        return JSONResponse(created, status_code=201)

    @app.get("/api/cases/attachments")
    async def attachment_list(request: Request):
        try:
            return JSONResponse(_service(request).list_attachments(_actor(request), _material(request)))
        except SharedAttachmentError as exc:
            return _fail(exc)

    @app.post("/api/cases/attachments/{attachment_id}/download")
    async def attachment_download(attachment_id: str, request: Request):
        try:
            return JSONResponse(_service(request).download_attachment(_actor(request), attachment_id, _material(request)))
        except SharedAttachmentError as exc:
            return _fail(exc)
