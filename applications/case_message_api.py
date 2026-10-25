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

from applications.case_messages import (
    CaseMessageError,
    CaseMessageStore,
    message_http_status,
)

TASK_ID = "CIMP-GUI-42"


class CaseMessageService:
    """Route-facing facade over the encrypted thread store."""

    def __init__(self, store: CaseMessageStore) -> None:
        if not isinstance(store, CaseMessageStore):
            raise CaseMessageError("authority_owners")
        self._store = store

    @property
    def store(self) -> CaseMessageStore:
        return self._store

    def create_thread(self, actor_principal_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._store.create_thread(actor_principal_id, body)

    def list_threads(self, actor_principal_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._store.list_threads(actor_principal_id, body)

    def send(self, actor_principal_id: str, thread_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._store.send(actor_principal_id, thread_id, body)

    def revise(self, actor_principal_id: str, thread_id: str, message_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._store.revise(actor_principal_id, thread_id, message_id, body)

    def page(self, actor_principal_id: str, thread_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._store.page(actor_principal_id, thread_id, body)

    def adopt(self, actor_principal_id: str, thread_id: str, message_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._store.adopt(actor_principal_id, thread_id, message_id, body)


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
        return JSONResponse({"error": exc.code}, status_code=message_http_status(exc.code))

    @app.post("/api/cases/messages/threads")
    async def message_thread_create(request: Request):
        try:
            created = _service(request).create_thread(_actor(request), _material(request))
        except CaseMessageError as exc:
            return _fail(exc)
        return JSONResponse(created, status_code=201)

    @app.get("/api/cases/messages/threads")
    async def message_thread_list(request: Request):
        try:
            return JSONResponse(_service(request).list_threads(_actor(request), _material(request)))
        except CaseMessageError as exc:
            return _fail(exc)

    @app.post("/api/cases/messages/threads/{thread_id}/messages")
    async def message_send(thread_id: str, request: Request):
        try:
            created = _service(request).send(_actor(request), thread_id, _material(request))
        except CaseMessageError as exc:
            return _fail(exc)
        return JSONResponse(created, status_code=201)

    @app.post("/api/cases/messages/threads/{thread_id}/messages/{message_id}/revise")
    async def message_revise(thread_id: str, message_id: str, request: Request):
        try:
            return JSONResponse(_service(request).revise(_actor(request), thread_id, message_id, _material(request)))
        except CaseMessageError as exc:
            return _fail(exc)

    @app.get("/api/cases/messages/threads/{thread_id}/messages")
    async def message_page(thread_id: str, request: Request):
        try:
            return JSONResponse(_service(request).page(_actor(request), thread_id, _material(request)))
        except CaseMessageError as exc:
            return _fail(exc)

    @app.post("/api/cases/messages/threads/{thread_id}/messages/{message_id}/adopt")
    async def message_adopt(thread_id: str, message_id: str, request: Request):
        try:
            return JSONResponse(_service(request).adopt(_actor(request), thread_id, message_id, _material(request)))
        except CaseMessageError as exc:
            return _fail(exc)
