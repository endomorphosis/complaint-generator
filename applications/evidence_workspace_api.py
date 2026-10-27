"""HTTP handlers for the case-scoped evidence catalog.

The browser session supplies the actor. A body cannot mint a role, a key, or
a legal conclusion. Missing keys and missing extraction capability stay
unavailable. A ciphertext receipt is not authenticity, relevance, admissibility,
or claim support.
"""

from __future__ import annotations

from typing import Any, Mapping

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from applications.browser_sessions import SESSION_COOKIE, BrowserSessionError, BrowserSessionService

from integrations.evidence_workspace import (
    INGESTION_STATUSES,
    TASK_ID,
    EvidenceWorkspace,
    EvidenceWorkspaceError,
    legal_qualities,
)

_NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0, private",
    "Pragma": "no-cache",
    "Expires": "0",
}


def evidence_http_status(code: str) -> int:
    if code in {"unauthenticated"}:
        return 401
    if code in {"not_owner", "tenant_mismatch", "selector_rejected", "legal_quality_rejected", "missing_evidence"}:
        return 403
    if code in {"revision_conflict", "replay_mismatch", "lifecycle_conflict"}:
        return 409
    if code in {"request_body", "content_rejected", "action", "source_filename", "original_filename", "idempotency_key", "evidence_id", "failure_code", "complaint_link_id", "media_type", "actor"}:
        return 400
    return 503


def mount_evidence_workspace(app: Any) -> None:
    """Mount catalog routes on the authenticated case boundary."""

    from fastapi.responses import JSONResponse

    def _service(request: Request) -> EvidenceWorkspace:
        service = getattr(request.app.state, "evidence_workspace", None)
        if not isinstance(service, EvidenceWorkspace):
            raise EvidenceWorkspaceError("evidence_unavailable")
        return service

    def _actor(request: Request) -> str:
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        if not isinstance(actor, str) or actor == "":
            raise EvidenceWorkspaceError("unauthenticated")
        return actor

    def _verify(request: Request):
        sessions = getattr(request.app.state, "browser_sessions", None)
        bound = getattr(request.state, "browser_principal", None)
        token = request.cookies.get(SESSION_COOKIE)
        if not isinstance(sessions, BrowserSessionService) or bound is None:
            raise EvidenceWorkspaceError("unauthenticated")

        def verify() -> None:
            try:
                current = sessions.authenticate_token(token)
            except BrowserSessionError as exc:
                raise EvidenceWorkspaceError("unauthenticated") from exc
            if (current.principal_id != bound.principal_id or current.tenant_id != bound.tenant_id
                    or current.generation != bound.generation):
                raise EvidenceWorkspaceError("unauthenticated")

        return verify

    def _material(request: Request) -> Mapping[str, Any]:
        material = getattr(request.state, "case_catalog_material", None)
        return material if isinstance(material, Mapping) else {}

    def _fail(exc: EvidenceWorkspaceError) -> JSONResponse:
        code = exc.code
        body = {
            "task_id": TASK_ID,
            "error": code,
            "ingestion_status": "unavailable" if code in {"key_unavailable", "evidence_unavailable", "ciphertext_unavailable"} else "",
            "legal": legal_qualities(),
            "receipt_establishes_legal_quality": False,
            "operation_succeeded": False,
            "items": [],
            "allowed_ingestion_statuses": list(INGESTION_STATUSES),
        }
        return JSONResponse(body, status_code=evidence_http_status(code), headers=_NO_STORE_HEADERS)

    @app.post("/api/cases/evidence")
    async def receive_evidence(request: Request):
        try:
            verify = _verify(request)
            verify()
            service, actor, material = _service(request), _actor(request), _material(request)
            verify_key = await run_in_threadpool(service.key_scope_verifier, actor, material)
            verify()
            record = await run_in_threadpool(service.receive, actor, material, verify_request=verify_key)
            await run_in_threadpool(verify_key)
            verify()
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        return JSONResponse(record, status_code=201, headers=_NO_STORE_HEADERS)

    @app.post("/api/cases/evidence/lifecycle")
    async def transition_evidence(request: Request):
        try:
            verify = _verify(request)
            verify()
            service, actor, material = _service(request), _actor(request), _material(request)
            verify_key = await run_in_threadpool(service.key_scope_verifier, actor, material)
            verify()
            record = await run_in_threadpool(service.transition, actor, material, verify_request=verify_key)
            await run_in_threadpool(verify_key)
            verify()
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        status = 200 if record.get("operation_succeeded") else 409 if record.get("ingestion_status") == "failed" else 503
        return JSONResponse(record, status_code=status, headers=_NO_STORE_HEADERS)

    @app.get("/api/cases/evidence")
    async def list_evidence(request: Request):
        try:
            verify = _verify(request)
            verify()
            service, actor, material = _service(request), _actor(request), _material(request)
            verify_key = await run_in_threadpool(service.key_scope_verifier, actor, material)
            verify()
            catalog = await run_in_threadpool(service.list_catalog, actor, material, verify_request=verify_key)
            await run_in_threadpool(verify_key)
            verify()
        except EvidenceWorkspaceError as exc:
            return _fail(exc)
        status = 200 if catalog.get("error") in {None, ""} else 503
        return JSONResponse(catalog, status_code=status, headers=_NO_STORE_HEADERS)
