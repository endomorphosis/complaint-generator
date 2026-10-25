"""HTTP owner for authorized encrypted case conversations.

Routes sit on the case catalog boundary. The session actor is taken from the
verified browser principal. Request bodies cannot mint a role, a grant, or a
disposition. Message text remains conversation until ``adopt``.

This module does not deliver external messages and does not claim WebSocket
or SSE. Adoption does not call a model or write an evidence artifact.
"""

from __future__ import annotations

from typing import Any, Mapping

from starlette.requests import Request
from starlette.concurrency import run_in_threadpool
from applications.browser_sessions import BrowserSessionError, BrowserSessionService, SESSION_COOKIE

from applications.case_messages import (
    CaseMessageError,
    CaseMessageStore,
    message_http_status,
)

TASK_ID = "CIMP-GUI-42"
_NO_STORE = {"Cache-Control": "no-store, max-age=0, private", "Pragma": "no-cache", "Expires": "0"}


class CaseMessageService:
    """Route-facing facade over the encrypted thread store."""

    def __init__(self, store: CaseMessageStore) -> None:
        if not isinstance(store, CaseMessageStore):
            raise CaseMessageError("authority_owners")
        self._store = store
        self._attachments: Any = None

    def bind_attachments(self, attachments: Any) -> None:
        """Share files through the attachment owner. This service does not seal bytes itself."""

        from applications.case_attachment_api import CaseAttachmentService

        if not isinstance(attachments, CaseAttachmentService):
            raise CaseMessageError("authority_owners")
        self._attachments = attachments

    def share_attachment(self, actor_principal_id: str, thread_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        return self._attachment_call("store_attachment", actor_principal_id, thread_id, body, verify_access=verify_access)

    def list_attachments(self, actor_principal_id: str, thread_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._attachment_call("list_attachments", actor_principal_id, thread_id, body)

    def read_attachment(self, actor_principal_id: str, thread_id: str, attachment_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        return self._attachment_call("download_attachment", actor_principal_id, thread_id, body, attachment_id=attachment_id, verify_access=verify_access)

    def preview_attachment(self, actor_principal_id: str, thread_id: str, attachment_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        return self._attachment_call("preview_attachment", actor_principal_id, thread_id, body, attachment_id=attachment_id, verify_access=verify_access)

    def attachment_notices(self, actor_principal_id: str, thread_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._attachment_call("list_notices", actor_principal_id, thread_id, body)

    def _attachment_call(self, method: str, actor_principal_id: str, thread_id: str, body: Mapping[str, Any], *, attachment_id: str | None = None, verify_access=None) -> dict[str, Any]:
        from applications.case_attachment_api import CaseAttachmentService, SharedAttachmentError

        service = self._attachments
        if not isinstance(service, CaseAttachmentService):
            raise CaseMessageError("attachment_unavailable")
        if not isinstance(body, Mapping):
            raise CaseMessageError("request_body")
        material = dict(body)
        supplied = material.get("thread_id", thread_id)
        if supplied != thread_id:
            raise CaseMessageError("thread_mismatch")
        material["thread_id"] = thread_id
        try:
            target = getattr(service, method)
            if attachment_id is None:
                if verify_access is None or method == "list_attachments" or method == "list_notices":
                    if method in {"list_attachments", "list_notices"}:
                        return target(actor_principal_id, material)
                    return target(actor_principal_id, material, verify_access=verify_access)
                return target(actor_principal_id, material, verify_access=verify_access)
            return target(actor_principal_id, attachment_id, material, verify_access=verify_access)
        except SharedAttachmentError as exc:
            raise CaseMessageError(exc.code) from exc

    @property
    def store(self) -> CaseMessageStore:
        return self._store

    def _current_call(self, method, actor, *args, verify_access=None):
        if verify_access is None:
            return getattr(self._store, method)(actor, *args)
        body = args[-1]
        key = (self._store._key_id, self._store._key)
        def verify():
            verify_access()
            self._store._active(actor)
            if (self._store._key_id, self._store._key) != key:
                raise CaseMessageError("message_unavailable")
            payload = self._store._body(body)
            if method in {"page", "list_threads"}:
                admission = self._store._admit_read(actor, str(payload.get("case_id") or ""), payload)
            else:
                admission = self._store._admit(actor, str(payload.get("case_id") or ""),
                    "case.review" if method == "adopt" else "case.message.send", payload)
            if method not in {"create_thread", "list_threads"}:
                self._store._require_thread(args[0], admission["case_id"])
        with self._store.publication_scope(verify):
            return getattr(self._store, method)(actor, *args)

    def create_thread(self, actor_principal_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        return self._current_call("create_thread", actor_principal_id, body, verify_access=verify_access)

    def list_threads(self, actor_principal_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        return self._current_call("list_threads", actor_principal_id, body, verify_access=verify_access)

    def send(self, actor_principal_id: str, thread_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        return self._current_call("send", actor_principal_id, thread_id, body, verify_access=verify_access)

    def revise(self, actor_principal_id: str, thread_id: str, message_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        return self._current_call("revise", actor_principal_id, thread_id, message_id, body, verify_access=verify_access)

    def page(self, actor_principal_id: str, thread_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        return self._current_call("page", actor_principal_id, thread_id, body, verify_access=verify_access)

    def adopt(self, actor_principal_id: str, thread_id: str, message_id: str, body: Mapping[str, Any], *, verify_access=None) -> dict[str, Any]:
        return self._current_call("adopt", actor_principal_id, thread_id, message_id, body, verify_access=verify_access)


def mount_case_messages(app: Any) -> None:
    """Mount conversation routes. Catalog authentication runs before these handlers."""

    from fastapi.responses import JSONResponse

    def _service(request: Any) -> CaseMessageService:
        service = getattr(request.app.state, "case_messages", None)
        if not isinstance(service, CaseMessageService):
            raise CaseMessageError("message_unavailable")
        return service

    def _actor(request: Any) -> str:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        if not isinstance(actor, str) or actor == "":
            raise CaseMessageError("unauthenticated")
        return actor

    def _material(request: Any) -> Mapping[str, Any]:
        material = getattr(request.state, "case_catalog_material", None)
        return material if isinstance(material, dict) else {}

    def _fail(exc: CaseMessageError) -> JSONResponse:
        return JSONResponse({"error": exc.code}, status_code=message_http_status(exc.code), headers=_NO_STORE)

    async def _dispatch(request, method, *identities, status=200):
        try:
            service = _service(request)
            sessions = getattr(request.app.state, "browser_sessions", None)
            bound = getattr(request.state, "browser_principal", None)
            token = request.cookies.get(SESSION_COOKIE)
            if not isinstance(sessions, BrowserSessionService) or bound is None:
                raise CaseMessageError("unauthenticated")
            def verify():
                try:
                    current = sessions.authenticate_token(token)
                except BrowserSessionError:
                    raise CaseMessageError("unauthenticated") from None
                if (current.principal_id, current.tenant_id, current.generation) != (
                        bound.principal_id, bound.tenant_id, bound.generation):
                    raise CaseMessageError("unauthenticated")
                if (_service(request) is not service
                        or getattr(request.app.state, "browser_sessions", None) is not sessions):
                    raise CaseMessageError("message_unavailable")
            verify()
            result = await run_in_threadpool(getattr(service, method), _actor(request),
                *identities, _material(request), verify_access=verify)
            verify()
            return JSONResponse(result, status_code=status, headers=_NO_STORE)
        except CaseMessageError as exc:
            return _fail(exc)

    @app.post("/api/cases/messages/threads")
    async def message_thread_create(request: Request):
        return await _dispatch(request, "create_thread", status=201)

    @app.get("/api/cases/messages/threads")
    async def message_thread_list(request: Request):
        return await _dispatch(request, "list_threads")

    @app.post("/api/cases/messages/threads/{thread_id}/messages")
    async def message_send(thread_id: str, request: Request):
        return await _dispatch(request, "send", thread_id, status=201)

    @app.post("/api/cases/messages/threads/{thread_id}/messages/{message_id}/revise")
    async def message_revise(thread_id: str, message_id: str, request: Request):
        return await _dispatch(request, "revise", thread_id, message_id)

    @app.get("/api/cases/messages/threads/{thread_id}/messages")
    async def message_page(thread_id: str, request: Request):
        return await _dispatch(request, "page", thread_id)

    @app.post("/api/cases/messages/threads/{thread_id}/messages/{message_id}/adopt")
    async def message_adopt(thread_id: str, message_id: str, request: Request):
        return await _dispatch(request, "adopt", thread_id, message_id)
