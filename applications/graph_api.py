"""Authorized read-only projection of one case's factual knowledge graph.

The route is mounted by ``compose_case_routes``. Session and case-action checks
run before this handler. The handler still refuses a path or query case id that
does not match the authorized decision, and it reads the graph only through the
bound case mediator. It does not create a mediator and does not claim
WebSocket or SSE support.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request

from mediator.integrations.graph_tools import (
    FactualGraphProjectionError,
    project_authorized_factual_kg,
)

TASK_ID = "CIMP-GUI-21"
FACTUAL_GRAPH_PREFIX = "/api/graphs"


def factual_graph_http_status(code: str) -> int:
    if code in {"graph_read_ungranted", "cross_case_id"}:
        return 403
    if code in {"mediator_graph_hook_unavailable", "knowledge_graph_unavailable", "data_graph_owner_unavailable"}:
        return 503
    return 403


def mount_factual_graph_routes(app: Any) -> None:
    """Mount the factual projection. Authorization middleware protects the prefix."""

    from fastapi.responses import JSONResponse

    from applications.case_routes import _BOUND_HANDLERS

    def _fail(exc: FactualGraphProjectionError) -> JSONResponse:
        return JSONResponse({"error": exc.code, "status": "denied"}, status_code=factual_graph_http_status(exc.code))

    @app.get(FACTUAL_GRAPH_PREFIX + "/{case_id}/factual")
    async def read_factual_graph(case_id: str, request: Request):
        decision = getattr(request.state, "case_authorization", None)
        if decision is None or getattr(decision, "permits_case_content", False) is not True:
            return _fail(FactualGraphProjectionError("graph_read_ungranted"))
        if getattr(decision, "action", "") != "case.read":
            return _fail(FactualGraphProjectionError("graph_read_ungranted"))
        authorized_case = str(getattr(decision, "case_id", "") or "")
        query_case = str(request.query_params.get("case_id") or "")
        if authorized_case != case_id or (query_case and query_case != authorized_case):
            return _fail(FactualGraphProjectionError("cross_case_id"))
        resolver = _BOUND_HANDLERS.get()
        if resolver is None:
            return _fail(FactualGraphProjectionError("mediator_graph_hook_unavailable"))
        try:
            mediator, _workspace, _root = resolver()
        except Exception:
            return _fail(FactualGraphProjectionError("mediator_graph_hook_unavailable"))
        try:
            payload = project_authorized_factual_kg(
                mediator,
                case_id=authorized_case,
                graph_read_granted=True,
                requested_case_id=case_id,
            )
        except FactualGraphProjectionError as exc:
            return _fail(exc)
        payload["task_id"] = TASK_ID
        return JSONResponse(payload)
