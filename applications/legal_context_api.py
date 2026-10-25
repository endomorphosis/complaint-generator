"""Explicit jurisdiction, forum, and legal-date selection for one authorized case.

The route is mounted by ``compose_case_routes``. Session and case-action checks
run before these handlers. A path or query case id that does not match the
authorized decision is refused. HTTP uses the bound encrypted workspace, never
a mediator cache. Selection uses the same pure intake-context owner as the
encrypted workspace transaction. It never invents governing law.

Unknown and disputed applicability stay unknown or disputed. A context change
invalidates affected legal dependencies and proofs, keeps factual provenance,
and retains the prior context version. This module does not claim WebSocket
or SSE support.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping, MutableMapping, Optional

from starlette.requests import Request

TASK_ID = "CIMP-GUI-24"
LEGAL_CONTEXT_PREFIX = "/api/legal-context"
APPLICABILITY_VALUES = ("unknown", "disputed", "explicit")
_UNKNOWN_TOKENS = {"unknown", "unresolved", "unsure", "not sure", "n/a", "na"}
_DISPUTED_TOKENS = {"disputed", "dispute", "contested", "in dispute"}
_REJECTED_DEFAULTS = {"governing_law", "governing law", "default", "default_jurisdiction"}
_DATE_FIELDS = (
    "applicable_law_date",
    "event_date",
    "event_dates",
    "filing_reference_date",
    "corpus_retrieval_date",
)
_PROVENANCE_KEYS = (
    "source_id",
    "immutable_source_id",
    "provenance",
    "factual_premise_ids",
    "fact_ids",
    "stable_id",
)


class LegalContextError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def legal_context_http_status(code: str) -> int:
    if code == "unauthenticated":
        return 401
    if code == "legal_context_revision_conflict":
        return 409
    if code in {"governing_law_not_admitted", "applicability_not_admitted", "legal_context_field"}:
        return 422
    if code in {"legal_dependency_refresh_unavailable", "legal_context_unavailable", "unlock_needed"}:
        return 503
    return 403


def _token(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _applicability_token(value: Any) -> str:
    token = _token(value).lower()
    if token in _DISPUTED_TOKENS:
        return "disputed"
    if token in _UNKNOWN_TOKENS or token == "":
        return "unknown"
    if token in _REJECTED_DEFAULTS:
        raise LegalContextError("governing_law_not_admitted")
    return "explicit"


def _case_file_from_mediator(mediator: Any) -> MutableMapping[str, Any]:
    phase_manager = getattr(mediator, "phase_manager", None)
    if phase_manager is not None and hasattr(phase_manager, "get_phase_data"):
        from complaint_phases.phase_manager import ComplaintPhase

        stored = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
        if isinstance(stored, dict):
            return stored
    stored = getattr(mediator, "intake_case_file", None)
    if isinstance(stored, dict):
        return stored
    raise LegalContextError("legal_context_unavailable")


def _current_context(case_file: Mapping[str, Any]) -> Dict[str, Any]:
    current = case_file.get("legal_context")
    return dict(current) if isinstance(current, dict) else {}


def _snapshot_version(case_file: MutableMapping[str, Any]) -> None:
    context = _current_context(case_file)
    versions = case_file.get("legal_context_versions")
    if not isinstance(versions, list):
        versions = []
        case_file["legal_context_versions"] = versions
    versions.append({
        "context_revision": int(context.get("context_revision") or 0),
        "legal_context": deepcopy(context),
        "forum": deepcopy(case_file.get("legal_context_forum")),
        "applicability": case_file.get("legal_context_applicability") or "unknown",
        "legal_dependencies": deepcopy(case_file.get("legal_dependencies") or []),
    })


def _invalidate_records(records: Any, reason: str) -> list:
    invalidated = []
    for item in records or []:
        if not isinstance(item, dict):
            continue
        updated = dict(item)
        state = str(updated.get("proof_state") or updated.get("status") or "unknown").strip().lower()
        if state not in {"", "unknown", "invalidated"}:
            updated["proof_state"] = "invalidated"
            updated["invalidated_by"] = reason
            updated["invalidated_from_proof_state"] = state
        for key in _PROVENANCE_KEYS:
            if key in item:
                updated[key] = deepcopy(item[key])
        invalidated.append(updated)
    return invalidated


def _mark_dependencies_invalid(case_file: MutableMapping[str, Any], *, bump: bool, reason: str) -> None:
    context = _current_context(case_file)
    proofs = _invalidate_records(case_file.get("proof_leads"), reason)
    dependencies = _invalidate_records(case_file.get("legal_dependencies"), reason)
    case_file["proof_leads"] = proofs
    case_file["legal_dependencies"] = dependencies
    context["dependent_proof"] = deepcopy(proofs)
    applicability = str(context.get("selected_rule_applicability") or "unknown")
    if applicability not in {"", "unknown"}:
        context["invalidated_rule_applicability"] = applicability
        context["selected_rule_applicability"] = "invalidated"
    proof_state = str(context.get("proof_state") or "unknown").strip().lower()
    if proof_state not in {"", "unknown"}:
        context["proof_state"] = "invalidated"
    changed = list(context.get("changed_fields") or [])
    if reason not in changed:
        changed.append(reason)
    context["changed_fields"] = changed
    if bump:
        context["context_revision"] = int(context.get("context_revision") or 0) + 1
    case_file["legal_context"] = context


def _apply_law_fields(mediator: Any, case_file: MutableMapping[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    method = getattr(mediator, "apply_explicit_legal_context", None)
    if callable(method):
        updated = method(case_file, **updates)
    else:
        from complaint_phases.intake_case_file import apply_explicit_legal_context

        updated = apply_explicit_legal_context(case_file, **updates)
    if isinstance(updated, dict) and isinstance(updated.get("legal_context"), dict):
        return updated
    return case_file


def _refresh_dependencies(mediator: Any, change: Dict[str, Any]) -> None:
    refresh = getattr(mediator, "refresh_verified_legal_dependencies", None)
    if not callable(refresh):
        return
    try:
        refresh(change)
    except LegalContextError:
        raise
    except Exception as exc:
        raise LegalContextError("legal_dependency_refresh_unavailable") from exc


def select_explicit_legal_context(mediator: Any, updates: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Compatibility owner using the same pure selection as encrypted workspaces.

    No side-effecting Mediator.apply_explicit_legal_context call is made: that
    method already refreshes dependencies and formerly caused a second refresh.
    """
    from applications.legal_context_selection import apply_legal_context_selection
    from complaint_phases.dependency_graph import DependencyGraph
    from complaint_phases.phase_manager import ComplaintPhase

    if mediator is None:
        raise LegalContextError("legal_context_unavailable")
    case_file = _case_file_from_mediator(mediator)
    manager = getattr(mediator, "phase_manager", None)
    graph = manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph") if (
        manager is not None and callable(getattr(manager, "get_phase_data", None))) else None
    if graph is not None and not isinstance(graph, DependencyGraph):
        raise LegalContextError("legal_dependency_refresh_unavailable")
    selected = apply_legal_context_selection(case_file, updates or {}, dependency_graph=graph)
    if not selected["changed"]:
        return selected["projection"]
    before = deepcopy(case_file)
    case_file.clear()
    case_file.update(selected["case_file"])
    try:
        if graph is not None:
            update = getattr(manager, "update_phase_data", None)
            if not callable(update):
                raise LegalContextError("legal_dependency_refresh_unavailable")
            update(ComplaintPhase.INTAKE, "dependency_graph", selected["dependency_graph"])
            update(ComplaintPhase.INTAKE, "intake_case_file", case_file)
        else:
            _refresh_dependencies(mediator, selected["change"])
    except Exception:
        case_file.clear()
        case_file.update(before)
        raise
    return selected["projection"]


def project_legal_context(case_file: Mapping[str, Any]) -> Dict[str, Any]:
    """Public read model. Governing law is not filled in for missing fields."""
    context = _current_context(case_file)
    forum = case_file.get("legal_context_forum") if isinstance(case_file.get("legal_context_forum"), dict) else {
        "value": "unknown", "applicability": "unknown",
    }
    applicability = str(case_file.get("legal_context_applicability") or context.get("jurisdiction_applicability") or "unknown")
    if applicability not in APPLICABILITY_VALUES:
        applicability = "unknown"
    jurisdiction_applicability = str(context.get("jurisdiction_applicability") or (
        "explicit" if context.get("jurisdiction_explicit") else "unknown"
    ))
    if jurisdiction_applicability not in APPLICABILITY_VALUES:
        jurisdiction_applicability = "unknown"
    versions = case_file.get("legal_context_versions") if isinstance(case_file.get("legal_context_versions"), list) else []
    return {
        "task_id": TASK_ID,
        "status": context.get("status") or "unknown",
        "jurisdiction": context.get("jurisdiction") or "unknown",
        "jurisdiction_applicability": jurisdiction_applicability,
        "candidate_jurisdiction": context.get("candidate_jurisdiction"),
        "forum": forum.get("value") or "unknown",
        "forum_applicability": forum.get("applicability") or "unknown",
        "forum_candidate": forum.get("candidate"),
        "applicability": applicability,
        "governing_law_defaulted": False,
        "applicable_law_date": context.get("applicable_law_date"),
        "event_date": context.get("event_date"),
        "event_dates": list(context.get("event_dates") or []),
        "filing_reference_date": context.get("filing_reference_date"),
        "corpus_retrieval_date": context.get("corpus_retrieval_date"),
        "selected_rule_applicability": context.get("selected_rule_applicability") or "unknown",
        "proof_state": context.get("proof_state") or "unknown",
        "changed_fields": list(context.get("changed_fields") or []),
        "context_revision": int(context.get("context_revision") or 0),
        "questions": list(context.get("questions") or []),
        "dependent_proof": deepcopy(context.get("dependent_proof") or case_file.get("proof_leads") or []),
        "legal_dependencies": deepcopy(case_file.get("legal_dependencies") or []),
        "factual_provenance": deepcopy(case_file.get("factual_provenance") or []),
        "prior_versions": [
            {
                "context_revision": item.get("context_revision"),
                "jurisdiction": (item.get("legal_context") or {}).get("jurisdiction"),
                "forum": (item.get("forum") or {}).get("value") if isinstance(item.get("forum"), dict) else None,
                "applicability": item.get("applicability"),
            }
            for item in versions if isinstance(item, dict)
        ],
        "limitations": [
            "Unknown and disputed applicability are retained and are not treated as governing law.",
            "Search snippets, model text, and unexecuted proofs are not admitted law.",
            "WebSocket and SSE transports are not supported.",
        ],
    }


def mount_legal_context_routes(app: Any) -> None:
    """Mount explicit legal-context routes. Authorization middleware protects the prefix."""

    from fastapi.responses import JSONResponse
    from starlette.concurrency import run_in_threadpool

    from applications.case_routes import _BOUND_HANDLERS
    from applications.complaint_workspace import (ComplaintWorkspaceService, WorkspaceAccess,
        WorkspaceAuthorizationDenied, WorkspacePersistenceError, workspace_access_scope)
    from applications.workspace_case_authority import (WorkspaceCaseAuthorityError,
        current_workspace_case_authority)

    def _fail(exc: LegalContextError) -> JSONResponse:
        return JSONResponse({"error": exc.code, "status": "denied"}, status_code=legal_context_http_status(exc.code))

    def _authorized(request: Request, case_id: str):
        decision = getattr(request.state, "case_authorization", None)
        if decision is None or getattr(decision, "permits_case_content", False) is not True:
            raise LegalContextError("legal_context_ungranted")
        action = getattr(decision, "action", "")
        method = request.method.upper()
        expected = "case.read" if method in {"GET", "HEAD"} else "case.update"
        if action != expected:
            raise LegalContextError("legal_context_ungranted")
        authorized_case = str(getattr(decision, "case_id", "") or "")
        query_case = str(request.query_params.get("case_id") or "")
        if authorized_case != case_id or (query_case and query_case != authorized_case):
            raise LegalContextError("cross_case_id")
        resolver = _BOUND_HANDLERS.get()
        if resolver is None:
            raise LegalContextError("legal_context_unavailable")
        try:
            _mediator, workspace, _root = resolver()
        except Exception as exc:
            raise LegalContextError("legal_context_unavailable") from exc
        if not isinstance(workspace, ComplaintWorkspaceService):
            raise LegalContextError("legal_context_unavailable")
        authority = current_workspace_case_authority()
        actor = getattr(getattr(request.state, "browser_principal", None), "principal_id", None)
        if authority is None or not actor:
            raise LegalContextError("legal_context_ungranted")
        authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        return workspace, authority, actor

    def _operation(workspace, actor, case_id, body=None):
        with workspace_access_scope(WorkspaceAccess.authenticated(actor, case_id)):
            if body is None:
                return workspace.read_case_legal_context(actor, case_id=case_id)
            return workspace.update_case_legal_context(actor, case_id=case_id, updates=body)

    def _storage_failure(exc):
        code = "legal_context_revision_conflict" if exc.code == "revision_conflict" else (
            "unlock_needed" if exc.code == "unlock_needed" else "legal_context_unavailable")
        return _fail(LegalContextError(code))

    @app.get(LEGAL_CONTEXT_PREFIX + "/{case_id}")
    async def read_legal_context(case_id: str, request: Request):
        try:
            workspace, authority, actor = _authorized(request, case_id)
            payload = await run_in_threadpool(_operation, workspace, actor, case_id)
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        except (WorkspaceAuthorizationDenied, WorkspaceCaseAuthorityError):
            return _fail(LegalContextError("legal_context_ungranted"))
        except WorkspacePersistenceError as exc:
            return _storage_failure(exc)
        except LegalContextError as exc:
            return _fail(exc)
        payload["case_id"] = case_id
        return JSONResponse(payload)

    @app.post(LEGAL_CONTEXT_PREFIX + "/{case_id}")
    async def update_legal_context(case_id: str, request: Request):
        try:
            workspace, authority, actor = _authorized(request, case_id)
            body = await request.json()
            if not isinstance(body, dict):
                raise LegalContextError("legal_context_field")
            payload = await run_in_threadpool(_operation, workspace, actor, case_id, body)
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        except (WorkspaceAuthorizationDenied, WorkspaceCaseAuthorityError):
            return _fail(LegalContextError("legal_context_ungranted"))
        except WorkspacePersistenceError as exc:
            return _storage_failure(exc)
        except LegalContextError as exc:
            return _fail(exc)
        payload["case_id"] = case_id
        return JSONResponse(payload)
