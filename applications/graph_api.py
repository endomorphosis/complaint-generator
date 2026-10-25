"""Read one current encrypted case graph under live browser/case authority.

A mediator cache is not a private-read capability. The bound workspace decrypts
the current session twice around the pure projection. Changed source, locked
keys, or expired request authority refuse publication. This owner-key path does
not issue delegated decryption authority or claim WebSocket/SSE support.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from applications.complaint_workspace import (
    ComplaintWorkspaceService, WorkspaceAccess, WorkspaceAuthorizationDenied,
    WorkspacePersistenceError, workspace_access_scope,
)
from applications.workspace_case_authority import (
    WorkspaceCaseAuthorityError, current_workspace_case_authority,
)
from complaint_phases.knowledge_graph import FactualReviewError, KnowledgeGraph
from mediator.integrations.graph_tools import FactualGraphProjectionError, project_factual_kg

TASK_ID = "CIMP-GUI-21"
REVIEW_TASK_ID = "CIMP-GUI-22"
FACTUAL_GRAPH_PREFIX = "/api/graphs"


def factual_graph_http_status(code: str) -> int:
    if code in {"graph_revision_changed", "stale_graph_revision", "event_conflict"}:
        return 409
    if code in {"unknown_target", "proposal_missing"}:
        return 404
    if code in {"constrained_text", "constrained_record", "source_required", "source_not_user_fact",
                "proposal_required", "proposal_not_hypothesis", "target_required", "unknown_action",
                "revision_refused"}:
        return 400
    if code in {"graph_read_ungranted", "cross_case_id", "actor_authority_required", "actor_not_permitted"}:
        return 403
    if code in {"mediator_graph_hook_unavailable", "knowledge_graph_unavailable", "data_graph_owner_unavailable",
                "workspace_graph_read_unavailable", "private_graph_unavailable", "unlock_needed"}:
        return 503
    return 403


def _read_snapshot(workspace, authority, actor, case_id):
    """Use the public read-only session seam; never an in-memory mediator graph."""
    decision = authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
    if authority.action != "case.read" or authority.case_id != case_id:
        raise FactualGraphProjectionError("graph_read_ungranted")
    response = workspace.get_session(actor, case_id=case_id)
    state = response.get("session") if isinstance(response, dict) else None
    if (not isinstance(state, dict) or state.get("case_id") != case_id
            or state.get("user_id") != decision.canonical_owner_principal_id):
        raise FactualGraphProjectionError("cross_case_id")
    interview = state.get("shared_interview")
    graph = interview.get("knowledge_graph") if isinstance(interview, dict) else None
    if not isinstance(graph, dict) or not graph:
        raise FactualGraphProjectionError("knowledge_graph_unavailable")
    try:
        identity = hashlib.sha256(json.dumps({
            "owner": state["user_id"], "case_id": case_id,
            "private_revision": state.get("private_revision"), "shared_interview": interview,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
        hydrated = KnowledgeGraph.from_dict(graph)
    except (ValueError, TypeError, KeyError):
        raise FactualGraphProjectionError("knowledge_graph_unavailable") from None
    authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
    return hydrated, identity


def _project_current(workspace, authority, actor, case_id):
    with workspace_access_scope(WorkspaceAccess.authenticated(actor, case_id)):
        graph, before = _read_snapshot(workspace, authority, actor, case_id)
        payload = project_factual_kg(graph, case_id=case_id)
        _current_graph, after = _read_snapshot(workspace, authority, actor, case_id)
        if before != after:
            raise FactualGraphProjectionError("graph_revision_changed")
        authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        payload["factual_review_revision"] = graph.factual_review_revision()
        return payload


def _json_object(raw: bytes) -> dict:
    if not raw:
        raise FactualReviewError("constrained_text")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise FactualReviewError("constrained_text") from None
    if not isinstance(payload, dict):
        raise FactualReviewError("constrained_text")
    return payload


def _owner_graph_state(workspace, authority, actor, case_id):
    """Load the encrypted graph without the read path's case.update save."""
    decision = authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
    if authority.action != "case.update" or authority.case_id != case_id or decision.membership != "owner":
        raise FactualReviewError("actor_authority_required")
    backend = getattr(getattr(workspace, "request_handlers", None), "workspace", None)
    if backend is None or not hasattr(backend, "_load_state"):
        raise FactualGraphProjectionError("workspace_graph_read_unavailable")
    state = backend._load_state(decision.canonical_owner_principal_id, case_id=case_id)
    if str(state.get("user_id") or "") != decision.canonical_owner_principal_id or state.get("case_id") != case_id:
        raise FactualGraphProjectionError("cross_case_id")
    interview = state.get("shared_interview")
    graph_payload = interview.get("knowledge_graph") if isinstance(interview, dict) else None
    if not isinstance(graph_payload, dict) or not graph_payload:
        raise FactualGraphProjectionError("knowledge_graph_unavailable")
    try:
        identity = hashlib.sha256(json.dumps({
            "owner": state["user_id"], "case_id": case_id,
            "private_revision": state.get("private_revision"), "knowledge_graph": graph_payload,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
        hydrated = KnowledgeGraph.from_dict(graph_payload)
    except (ValueError, TypeError, KeyError):
        raise FactualGraphProjectionError("knowledge_graph_unavailable") from None
    return backend, state, hydrated, identity


def _review_current(workspace, authority, actor, case_id, body: dict):
    """Review one proposal on the decrypted graph, then seal that session."""
    decision = authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
    with workspace_access_scope(WorkspaceAccess.authenticated(actor, case_id)):
        backend, state, graph, before = _owner_graph_state(workspace, authority, actor, case_id)
        result = graph.apply_factual_review(
            actor_role="user",
            actor_principal_id=decision.actor_principal_id,
            authority_granted=True,
            expected_revision=str(body.get("expected_graph_revision") or ""),
            action=str(body.get("review_action") or ""),
            text=body.get("text") if isinstance(body.get("text"), str) else "",
            source_text=body.get("source_text") if isinstance(body.get("source_text"), str) else "",
            message_id=str(body.get("message_id") or ""),
            target_stable_id=str(body.get("target_stable_id") or ""),
            proposal_id=str(body.get("proposal_id") or ""),
            origin=str(body.get("origin") or "actor"),
            event_id=str(body.get("event_id") or ""),
            case_id=case_id,
            record_class=str(body.get("record_class") or ""),
        )
        _backend_again, _state_again, _graph_again, after = _owner_graph_state(workspace, authority, actor, case_id)
        if before != after:
            raise FactualGraphProjectionError("graph_revision_changed")
        interview = state.get("shared_interview")
        if not isinstance(interview, dict):
            raise FactualGraphProjectionError("knowledge_graph_unavailable")
        interview["knowledge_graph"] = graph.to_dict()
        state["shared_interview"] = interview
        backend._save_state(state)
        authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        result["case_id"] = case_id
        result["task_id"] = REVIEW_TASK_ID
        return result


def mount_factual_graph_routes(app: Any) -> None:
    """Mount the factual projection. Authorization middleware protects the prefix."""

    from fastapi.responses import JSONResponse

    from applications.case_routes import _BOUND_HANDLERS

    def _fail(exc: FactualGraphProjectionError) -> JSONResponse:
        return JSONResponse({"error": exc.code, "status": "denied"}, status_code=factual_graph_http_status(exc.code))

    def _review_fail(exc: FactualReviewError) -> JSONResponse:
        return JSONResponse({"error": exc.code, "status": "refused"}, status_code=factual_graph_http_status(exc.code))

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
            _mediator, workspace, _root = resolver()
        except Exception:
            return _fail(FactualGraphProjectionError("mediator_graph_hook_unavailable"))
        if not isinstance(workspace, ComplaintWorkspaceService):
            return _fail(FactualGraphProjectionError("workspace_graph_read_unavailable"))
        try:
            principal = getattr(request.state, "browser_principal", None)
            actor = getattr(principal, "principal_id", None)
            authority = current_workspace_case_authority()
            if not actor or authority is None:
                raise FactualGraphProjectionError("graph_read_ungranted")
            # ContextVars carry the real issued capability into the managed
            # thread; concurrent logout/revoke can still complete on the loop.
            payload = await run_in_threadpool(_project_current, workspace, authority, actor, authorized_case)
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        except (WorkspaceAuthorizationDenied, WorkspaceCaseAuthorityError):
            return _fail(FactualGraphProjectionError("graph_read_ungranted"))
        except WorkspacePersistenceError as exc:
            code = "unlock_needed" if exc.code == "unlock_needed" else "private_graph_unavailable"
            return _fail(FactualGraphProjectionError(code))
        except FactualGraphProjectionError as exc:
            return _fail(exc)
        payload["task_id"] = TASK_ID
        return JSONResponse(payload)

    @app.post(FACTUAL_GRAPH_PREFIX + "/{case_id}/factual/reviews")
    async def review_factual_graph(case_id: str, request: Request):
        decision = getattr(request.state, "case_authorization", None)
        if decision is None or getattr(decision, "permits_case_content", False) is not True:
            return _fail(FactualGraphProjectionError("graph_read_ungranted"))
        if getattr(decision, "action", "") != "case.update":
            return _review_fail(FactualReviewError("actor_authority_required"))
        if getattr(decision, "membership", "") != "owner":
            return _review_fail(FactualReviewError("actor_not_permitted"))
        authorized_case = str(getattr(decision, "case_id", "") or "")
        if authorized_case != case_id:
            return _fail(FactualGraphProjectionError("cross_case_id"))
        resolver = _BOUND_HANDLERS.get()
        if resolver is None:
            return _fail(FactualGraphProjectionError("mediator_graph_hook_unavailable"))
        try:
            _mediator, workspace, _root = resolver()
        except Exception:
            return _fail(FactualGraphProjectionError("mediator_graph_hook_unavailable"))
        if not isinstance(workspace, ComplaintWorkspaceService):
            return _fail(FactualGraphProjectionError("workspace_graph_read_unavailable"))
        try:
            raw = await request.body()
            body = _json_object(raw)
            supplied_case = str(body.get("case_id") or "")
            if supplied_case and supplied_case != authorized_case:
                return _fail(FactualGraphProjectionError("cross_case_id"))
            principal = getattr(request.state, "browser_principal", None)
            actor = getattr(principal, "principal_id", None)
            authority = current_workspace_case_authority()
            if not actor or authority is None:
                raise FactualReviewError("actor_authority_required")
            payload = await run_in_threadpool(
                _review_current, workspace, authority, actor, authorized_case, body,
            )
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        except (WorkspaceAuthorizationDenied, WorkspaceCaseAuthorityError):
            return _review_fail(FactualReviewError("actor_authority_required"))
        except WorkspacePersistenceError as exc:
            code = "unlock_needed" if exc.code == "unlock_needed" else "private_graph_unavailable"
            return _fail(FactualGraphProjectionError(code))
        except FactualReviewError as exc:
            return _review_fail(exc)
        except FactualGraphProjectionError as exc:
            return _fail(exc)
        return JSONResponse(payload)
