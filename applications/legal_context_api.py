"""Explicit jurisdiction, forum, and legal-date selection for one authorized case.

The route is mounted by ``compose_case_routes``. Session and case-action checks
run before these handlers. A path or query case id that does not match the
authorized decision is refused. Selection goes through the bound case mediator
when that mediator exposes ``apply_explicit_legal_context``; otherwise the
shared intake owner is used. Neither path invents governing law.

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
    if code in {"unauthenticated", "legal_context_unavailable"}:
        return 401
    if code == "legal_context_revision_conflict":
        return 409
    if code in {"governing_law_not_admitted", "applicability_not_admitted", "legal_context_field"}:
        return 422
    if code == "legal_dependency_refresh_unavailable":
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
    """Record an explicit legal context on the bound case file.

    ``governing_law`` is never copied into jurisdiction or forum. Omitted
    applicability stays unknown. Disputed stays disputed.
    """
    if mediator is None:
        raise LegalContextError("legal_context_unavailable")
    body = dict(updates or {})
    rejected = [key for key in body if str(key) in _REJECTED_DEFAULTS or str(key).startswith("governing_")]
    if rejected or any(str(value).strip().lower() in _REJECTED_DEFAULTS for value in body.values() if not isinstance(value, (dict, list))):
        if any(str(key) in _REJECTED_DEFAULTS or str(key).startswith("governing_") for key in body):
            raise LegalContextError("governing_law_not_admitted")
    for key, value in list(body.items()):
        if isinstance(value, str) and value.strip().lower() in _REJECTED_DEFAULTS and key in {"jurisdiction", "forum", "applicability"}:
            raise LegalContextError("governing_law_not_admitted")
    case_file = _case_file_from_mediator(mediator)
    context = _current_context(case_file)
    current_revision = int(context.get("context_revision") or 0)
    if "expected_context_revision" not in body:
        raise LegalContextError("legal_context_revision_conflict")
    try:
        expected = int(body.get("expected_context_revision"))
    except (TypeError, ValueError):
        raise LegalContextError("legal_context_revision_conflict") from None
    if expected != current_revision:
        raise LegalContextError("legal_context_revision_conflict")

    applicability_requested = body.get("applicability") if "applicability" in body else None
    if applicability_requested is not None and _token(applicability_requested).lower() not in set(APPLICABILITY_VALUES) | _UNKNOWN_TOKENS | _DISPUTED_TOKENS:
        if _token(applicability_requested).lower() in _REJECTED_DEFAULTS:
            raise LegalContextError("governing_law_not_admitted")
        raise LegalContextError("applicability_not_admitted")
    overall = _applicability_token(applicability_requested) if applicability_requested is not None else str(case_file.get("legal_context_applicability") or "unknown")
    if overall not in APPLICABILITY_VALUES:
        overall = "unknown"

    jurisdiction_mode = "unchanged"
    if "jurisdiction" in body:
        jurisdiction_mode = _applicability_token(body.get("jurisdiction"))
    forum_mode = "unchanged"
    if "forum" in body:
        forum_mode = _applicability_token(body.get("forum"))
    if overall == "disputed":
        if jurisdiction_mode == "explicit":
            jurisdiction_mode = "disputed"
        if forum_mode == "explicit":
            forum_mode = "disputed"
    if overall == "unknown" and "applicability" in body:
        if jurisdiction_mode == "explicit":
            jurisdiction_mode = "unknown"
        if forum_mode == "explicit":
            forum_mode = "unknown"

    law_updates: Dict[str, Any] = {}
    current_jurisdiction = str(context.get("jurisdiction") or "unknown")
    if jurisdiction_mode == "explicit":
        law_updates["jurisdiction"] = _token(body.get("jurisdiction"))
    elif jurisdiction_mode in {"unknown", "disputed"} and current_jurisdiction not in {"", "unknown"}:
        law_updates["jurisdiction"] = ""
    for field in _DATE_FIELDS:
        if field in body:
            law_updates[field] = body.get(field)

    prior_forum = case_file.get("legal_context_forum") if isinstance(case_file.get("legal_context_forum"), dict) else {
        "value": "unknown", "applicability": "unknown",
    }
    next_forum = dict(prior_forum)
    if forum_mode == "explicit":
        next_forum = {"value": _token(body.get("forum")), "applicability": "explicit"}
    elif forum_mode == "disputed":
        next_forum = {"value": "disputed", "applicability": "disputed", "candidate": _token(body.get("forum"))}
    elif forum_mode == "unknown":
        next_forum = {"value": "unknown", "applicability": "unknown"}
    forum_changed = next_forum != prior_forum

    candidate_jurisdiction = None
    if jurisdiction_mode == "disputed":
        candidate_jurisdiction = _token(body.get("jurisdiction")) or "disputed"
    elif jurisdiction_mode == "unknown" and "jurisdiction" in body:
        candidate_jurisdiction = _token(body.get("jurisdiction")) or "unknown"

    prior_overall = str(case_file.get("legal_context_applicability") or "unknown")
    applicability_changed = "applicability" in body and overall != prior_overall
    jurisdiction_overlay = jurisdiction_mode == "disputed" or (
        jurisdiction_mode == "unknown" and str(context.get("jurisdiction_applicability") or "unknown") != "unknown"
    )
    if not law_updates and not forum_changed and not applicability_changed and not jurisdiction_overlay:
        return project_legal_context(case_file)

    provenance_before = deepcopy(case_file.get("factual_provenance"))
    facts_before = deepcopy(case_file.get("canonical_facts"))
    _snapshot_version(case_file)
    revision_before = current_revision
    if law_updates:
        case_file = _apply_law_fields(mediator, case_file, law_updates)
    context = _current_context(case_file)
    revision_after_law = int(context.get("context_revision") or 0)
    law_invalidated = revision_after_law != revision_before

    if jurisdiction_mode == "disputed":
        context["jurisdiction"] = "unknown"
        context["jurisdiction_explicit"] = False
        context["jurisdiction_applicability"] = "disputed"
        context["candidate_jurisdiction"] = candidate_jurisdiction
        context["status"] = "disputed"
    elif jurisdiction_mode == "unknown":
        context["jurisdiction_applicability"] = "unknown"
        context["candidate_jurisdiction"] = candidate_jurisdiction
        if str(context.get("jurisdiction") or "unknown") == "unknown":
            context["status"] = "unknown"
    elif jurisdiction_mode == "explicit":
        resolved = str(context.get("jurisdiction") or "unknown")
        context["jurisdiction_applicability"] = "explicit" if resolved not in {"", "unknown"} else "unknown"
        context.pop("candidate_jurisdiction", None)
        if context["jurisdiction_applicability"] != "explicit" and overall == "explicit":
            overall = "unknown"
    case_file["legal_context"] = context
    case_file["legal_context_forum"] = next_forum
    if next_forum.get("applicability") == "disputed" or context.get("jurisdiction_applicability") == "disputed":
        if overall == "explicit":
            overall = "disputed"
    applicability_changed = overall != prior_overall
    case_file["legal_context_applicability"] = overall

    dependency_reason = None
    if law_invalidated:
        dependency_reason = "legal_context_change"
        _mark_dependencies_invalid(case_file, bump=False, reason=dependency_reason)
    elif forum_changed or applicability_changed or jurisdiction_overlay:
        dependency_reason = "forum" if forum_changed else ("applicability" if applicability_changed else "jurisdiction")
        _mark_dependencies_invalid(case_file, bump=True, reason=dependency_reason)
    if dependency_reason is None and not law_invalidated:
        versions = case_file.get("legal_context_versions")
        if isinstance(versions, list) and versions:
            versions.pop()
        if case_file.get("factual_provenance") != provenance_before:
            case_file["factual_provenance"] = provenance_before
        return project_legal_context(case_file)

    if case_file.get("factual_provenance") != provenance_before or case_file.get("canonical_facts") != facts_before:
        case_file["factual_provenance"] = provenance_before
        case_file["canonical_facts"] = facts_before

    change = {}
    if jurisdiction_mode != "unchanged":
        change["jurisdiction_changed"] = True
    if any(field in law_updates for field in _DATE_FIELDS):
        change["date_changed"] = True
    if forum_changed:
        change["forum_changed"] = True
    if change and (law_invalidated or forum_changed or dependency_reason):
        _refresh_dependencies(mediator, change)
    return project_legal_context(case_file)


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

    from applications.case_routes import _BOUND_HANDLERS

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
            mediator, _workspace, _root = resolver()
        except Exception as exc:
            raise LegalContextError("legal_context_unavailable") from exc
        return mediator

    @app.get(LEGAL_CONTEXT_PREFIX + "/{case_id}")
    async def read_legal_context(case_id: str, request: Request):
        try:
            mediator = _authorized(request, case_id)
            payload = project_legal_context(_case_file_from_mediator(mediator))
        except LegalContextError as exc:
            return _fail(exc)
        payload["case_id"] = case_id
        return JSONResponse(payload)

    @app.post(LEGAL_CONTEXT_PREFIX + "/{case_id}")
    async def update_legal_context(case_id: str, request: Request):
        try:
            mediator = _authorized(request, case_id)
            body = await request.json()
            if not isinstance(body, dict):
                raise LegalContextError("legal_context_field")
            payload = select_explicit_legal_context(mediator, body)
        except LegalContextError as exc:
            return _fail(exc)
        payload["case_id"] = case_id
        return JSONResponse(payload)
