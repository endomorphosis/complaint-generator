"""Bounded legal-source candidate acquisition for one authorized case.

The route is mounted by ``compose_case_routes``. Session and case-action checks
run before these handlers. Acquisition goes through the bound mediator's
``build_legal_acquisition_request`` and ``legal_authority_search`` owners.
Search hits, snippets, missing archives, and model text stay candidates or
research gaps. This module does not admit law and does not claim WebSocket
or SSE support.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Mapping, MutableMapping

from starlette.requests import Request

TASK_ID = "CIMP-GUI-25"
LEGAL_RESEARCH_PREFIX = "/api/legal-research"
PURPOSES = ("citation_acquisition", "public_law_citation")
RETRIEVAL_MODES = ("cache", "offline", "live")
LOCAL_MODES = ("cache", "offline")
QUERY_MAX_CHARS = 256
RESULT_CAP = 5
TIMEOUT_CAP_SECONDS = 5.0
BYTE_CAP = 4096
_GAP_REASONS = {
    "snippet": "snippet_not_law",
    "snippet_only": "snippet_not_law",
    "model_text": "model_text_not_law",
    "missing_archive": "missing_archive",
    "archive_missing": "missing_archive",
}


class LegalResearchError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def legal_research_http_status(code: str) -> int:
    if code in {"unauthenticated", "legal_research_unavailable"}:
        return 401
    if code in {"consent_revision_conflict", "legal_research_revision_conflict"}:
        return 409
    if code in {"legal_research_bounds", "legal_research_field", "purpose_not_allowed"}:
        return 422
    if code in {"acquisition_unavailable", "research_hook_unavailable"}:
        return 503
    return 403


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
    raise LegalResearchError("legal_research_unavailable")


def _purpose_decision(view: Mapping[str, Any], purpose: str) -> Dict[str, Any]:
    rows = view.get("decisions")
    if isinstance(rows, list):
        matches = [item for item in rows if isinstance(item, dict) and item.get("purpose") == purpose]
    elif isinstance(rows, dict) and isinstance(rows.get(purpose), dict):
        matches = [rows[purpose]]
    else:
        matches = []
    if len(matches) != 1:
        raise LegalResearchError("purpose_consent_required")
    return matches[0]


def _require_purpose_consent(authority: Any, workspace: Any, purpose: str, expected_generation: int, retrieval_mode: str) -> Dict[str, Any]:
    try:
        view = authority.processing_consent(
            purpose=purpose,
            actor_principal_id=authority.actor_principal_id,
            workspace=workspace,
        )
    except LegalResearchError:
        raise
    except Exception as exc:
        code = str(getattr(exc, "code", "") or "")
        if code in {"consent_revoked", "purpose_consent_required", "case_purpose_consent_required"}:
            raise LegalResearchError("purpose_consent_required") from exc
        raise LegalResearchError("purpose_consent_required") from exc
    if not isinstance(view, dict):
        raise LegalResearchError("purpose_consent_required")
    choice = _purpose_decision(view, purpose)
    generation = choice.get("generation")
    if type(generation) is not int or isinstance(generation, bool) or generation < 1:
        raise LegalResearchError("purpose_consent_required")
    if generation != expected_generation:
        raise LegalResearchError("consent_revision_conflict")
    if retrieval_mode == "live":
        if choice.get("egress_authorized") is not True or choice.get("revoked") is True or choice.get("explicit") is not True:
            raise LegalResearchError("purpose_consent_required")
    elif choice.get("revoked") is True and choice.get("mode") not in {None, "", "local_private"}:
        raise LegalResearchError("consent_revoked")
    return {
        "purpose": purpose,
        "generation": generation,
        "mode": choice.get("mode") or "local_private",
        "egress_authorized": choice.get("egress_authorized") is True,
        "data_class": choice.get("data_class") or "public_legal_source_graph",
        "revoked": choice.get("revoked") is True,
    }


def _bounds(body: Mapping[str, Any]) -> Dict[str, Any]:
    purpose = body.get("purpose")
    if purpose not in PURPOSES:
        raise LegalResearchError("purpose_not_allowed")
    query = body.get("query")
    if not isinstance(query, str) or not query.strip() or len(query) > QUERY_MAX_CHARS or query != query.strip():
        raise LegalResearchError("legal_research_bounds")
    max_results = body.get("max_results", RESULT_CAP)
    if type(max_results) is not int or isinstance(max_results, bool) or not 1 <= max_results <= RESULT_CAP:
        raise LegalResearchError("legal_research_bounds")
    deadline = body.get("deadline_seconds", TIMEOUT_CAP_SECONDS)
    if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
        raise LegalResearchError("legal_research_bounds")
    deadline_seconds = float(deadline)
    if not deadline_seconds > 0 or deadline_seconds > TIMEOUT_CAP_SECONDS:
        raise LegalResearchError("legal_research_bounds")
    max_bytes = body.get("max_bytes", BYTE_CAP)
    if type(max_bytes) is not int or isinstance(max_bytes, bool) or not 1 <= max_bytes <= BYTE_CAP:
        raise LegalResearchError("legal_research_bounds")
    retrieval_mode = body.get("retrieval_mode", "cache")
    if retrieval_mode not in RETRIEVAL_MODES:
        raise LegalResearchError("legal_research_bounds")
    expected = body.get("expected_consent_generation")
    if type(expected) is not int or isinstance(expected, bool) or expected < 0:
        raise LegalResearchError("legal_research_field")
    operation_id = body.get("operation_id", "")
    if not isinstance(operation_id, str) or len(operation_id) > 64:
        raise LegalResearchError("legal_research_field")
    if body.get("cancelled") not in {True, False, None}:
        raise LegalResearchError("legal_research_field")
    local_rows = body.get("local_rows")
    if local_rows is not None and not isinstance(local_rows, dict):
        raise LegalResearchError("legal_research_field")
    if isinstance(local_rows, dict) and len(json.dumps(local_rows, default=str)) > BYTE_CAP:
        raise LegalResearchError("legal_research_bounds")
    return {
        "purpose": purpose,
        "query": query,
        "max_results": max_results,
        "deadline_seconds": deadline_seconds,
        "max_bytes": max_bytes,
        "retrieval_mode": retrieval_mode,
        "expected_consent_generation": expected,
        "operation_id": operation_id,
        "cancelled": body.get("cancelled") is True,
        "local_rows": local_rows,
    }


def _gap(reason: str, *, source_id: str = "", version: str = "", locator: str = "") -> Dict[str, Any]:
    return {
        "kind": "research_gap",
        "reason": reason,
        "admitted_law": False,
        "proof": False,
        "support_eligible": False,
        "applicable": False,
        "source_id": source_id,
        "version": version,
        "locator": locator,
        "content_hash": "",
    }


def _candidate_receipt(item: Mapping[str, Any]) -> Dict[str, Any]:
    retrieval = item.get("retrieval") if isinstance(item.get("retrieval"), dict) else {}
    version = str(item.get("version") or item.get("authority_version") or retrieval.get("corpus_version") or "")
    locator = str(item.get("locator") or "")
    source_id = str(item.get("source_id") or retrieval.get("corpus_id") or locator or "")
    content_hash = str(retrieval.get("content_hash") or item.get("content_hash") or "")
    passage_status = str(item.get("passage_status") or "")
    archive_status = str(item.get("archive_status") or item.get("archive") or "")
    if item.get("model_text") or item.get("model_inference_used") is True or passage_status == "model_text":
        return _gap("model_text_not_law", source_id=source_id, version=version, locator=locator)
    if item.get("snippet") or passage_status in {"snippet", "snippet_only"}:
        return _gap("snippet_not_law", source_id=source_id, version=version, locator=locator)
    if archive_status in {"missing", "missing_archive", "archive_missing"} or item.get("archive_missing") is True:
        return _gap("missing_archive", source_id=source_id, version=version, locator=locator)
    source_text = item.get("source_text") if isinstance(item.get("source_text"), str) else ""
    if not source_text or not version.strip() or not locator:
        reason = "source_text_missing" if not source_text else "source_version_missing"
        return _gap(reason, source_id=source_id, version=version, locator=locator)
    if not content_hash:
        content_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    return {
        "kind": "candidate",
        "reason": "",
        "admitted_law": False,
        "proof": False,
        "support_eligible": False,
        "applicable": False,
        "source_id": source_id,
        "version": version.strip(),
        "locator": locator,
        "locator_kind": str(item.get("locator_kind") or ""),
        "content_hash": content_hash,
        "source_family": str(item.get("source_family") or retrieval.get("source_family") or ""),
        "byte_length": len(source_text.encode("utf-8")),
    }


def _project_acquisition(acquisition: Mapping[str, Any], *, bounds: Mapping[str, Any], consent: Mapping[str, Any], replayed: bool) -> Dict[str, Any]:
    raw_candidates = acquisition.get("candidates") if isinstance(acquisition.get("candidates"), list) else []
    receipts = [_candidate_receipt(item) for item in raw_candidates if isinstance(item, dict)]
    for operation in acquisition.get("operations") or []:
        if not isinstance(operation, dict):
            continue
        status = str(operation.get("status") or "")
        error_code = str(operation.get("error_code") or "")
        if status in {"missing_edition", "incomplete", "empty", "unavailable", "timeout", "error"} or error_code in _GAP_REASONS:
            receipts.append(_gap(
                _GAP_REASONS.get(error_code, error_code or status or "research_gap"),
                source_id=str(operation.get("source_family") or ""),
                version=str(operation.get("version") or ""),
            ))
        for withheld in operation.get("withheld") or []:
            if isinstance(withheld, dict):
                reason = str(withheld.get("reason") or "research_gap")
                receipts.append(_gap(reason, source_id=str(operation.get("source_family") or "")))
    for receipt in receipts:
        receipt["admitted_law"] = False
        receipt["proof"] = False
    status = str(acquisition.get("status") or "unavailable")
    if bounds.get("cancelled"):
        status = "cancelled"
    return {
        "task_id": TASK_ID,
        "action": "legal_source_candidates",
        "admitted_law": False,
        "proof": False,
        "legal_sufficiency": False,
        "stored_as_answer": False,
        "status": status,
        "error_code": "cancelled" if bounds.get("cancelled") else str(acquisition.get("error_code") or ""),
        "replayed": replayed,
        "dispatched": not replayed,
        "cancelled": bool(bounds.get("cancelled")),
        "purpose": consent.get("purpose"),
        "consent_generation": consent.get("generation"),
        "retrieval_mode": bounds.get("retrieval_mode"),
        "bounds": {
            "max_results": bounds.get("max_results"),
            "deadline_seconds": bounds.get("deadline_seconds"),
            "max_bytes": bounds.get("max_bytes"),
            "query_chars": len(str(bounds.get("query") or "")),
        },
        "source_version_receipts": receipts,
        "candidate_count": sum(1 for item in receipts if item.get("kind") == "candidate"),
        "research_gap_count": sum(1 for item in receipts if item.get("kind") == "research_gap"),
        "model_inference_used": False,
        "limitations": [
            "Search results, snippets, missing archives, and model text are candidates or research gaps.",
            "Nothing returned by this route is admitted law.",
            "WebSocket and SSE transports are not supported.",
        ],
    }


def acquire_bounded_legal_sources(mediator: Any, workspace: Any, authority: Any, body: Mapping[str, Any]) -> Dict[str, Any]:
    """Invoke the bound research hook once. Results are never admitted law."""
    if not isinstance(body, Mapping):
        raise LegalResearchError("legal_research_field")
    bounds = _bounds(body)
    consent = _require_purpose_consent(
        authority,
        workspace,
        bounds["purpose"],
        bounds["expected_consent_generation"],
        bounds["retrieval_mode"],
    )
    case_file = _case_file_from_mediator(mediator)
    seen = getattr(mediator, "_gui_legal_research_operations", None)
    if not isinstance(seen, dict):
        seen = {}
        mediator._gui_legal_research_operations = seen
    operation_id = bounds["operation_id"]
    if operation_id and operation_id in seen:
        replay = dict(seen[operation_id])
        replay["replayed"] = True
        replay["dispatched"] = False
        replay["admitted_law"] = False
        return replay
    builder = getattr(mediator, "build_legal_acquisition_request", None)
    search = getattr(mediator, "legal_authority_search", None)
    acquire = getattr(search, "acquire_bounded_canonical_sources", None)
    if not callable(builder) or not callable(acquire):
        raise LegalResearchError("research_hook_unavailable")
    binding = builder(
        case_file,
        query_terms=[bounds["query"]],
        max_results=bounds["max_results"],
        timeout_seconds=bounds["deadline_seconds"],
        storage_available=True,
    )
    acquisition = acquire(
        binding,
        owner_id=str(getattr(authority, "actor_principal_id", "") or ""),
        case_id=str(getattr(authority, "case_id", "") or ""),
        purpose=bounds["purpose"],
        data_class=consent["data_class"],
        provider_kind="local" if bounds["retrieval_mode"] in LOCAL_MODES else "legal_corpus",
        retrieval_mode=bounds["retrieval_mode"],
        local_rows=bounds["local_rows"],
        deadline_seconds=bounds["deadline_seconds"],
        max_bytes=bounds["max_bytes"],
        max_results=bounds["max_results"],
        cancelled=bounds["cancelled"],
    )
    if not isinstance(acquisition, dict):
        raise LegalResearchError("acquisition_unavailable")
    receipt = _project_acquisition(acquisition, bounds=bounds, consent=consent, replayed=False)
    receipt["operation_id"] = operation_id
    case_file["legal_source_candidate_receipt"] = receipt
    if operation_id:
        seen[operation_id] = dict(receipt)
    return receipt


def project_legal_research(case_file: Mapping[str, Any]) -> Dict[str, Any]:
    stored = case_file.get("legal_source_candidate_receipt") if isinstance(case_file, Mapping) else None
    if not isinstance(stored, dict):
        return {
            "task_id": TASK_ID,
            "action": "legal_source_candidates",
            "admitted_law": False,
            "status": "empty",
            "source_version_receipts": [],
            "candidate_count": 0,
            "research_gap_count": 0,
            "limitations": [
                "No legal-source acquisition has been recorded.",
                "Search results are not admitted law.",
            ],
        }
    projected = dict(stored)
    projected["admitted_law"] = False
    projected["proof"] = False
    receipts = projected.get("source_version_receipts")
    if isinstance(receipts, list):
        for item in receipts:
            if isinstance(item, dict):
                item["admitted_law"] = False
                item["proof"] = False
    return projected


def mount_legal_research_routes(app: Any) -> None:
    """Mount bounded legal-research routes. Authorization middleware protects the prefix."""

    from fastapi.responses import JSONResponse

    from applications.case_routes import _BOUND_HANDLERS
    from applications.workspace_case_authority import current_workspace_case_authority

    def _fail(exc: LegalResearchError) -> JSONResponse:
        return JSONResponse({"error": exc.code, "status": "denied", "admitted_law": False}, status_code=legal_research_http_status(exc.code))

    def _authorized(request: Request, case_id: str):
        decision = getattr(request.state, "case_authorization", None)
        if decision is None or getattr(decision, "permits_case_content", False) is not True:
            raise LegalResearchError("legal_research_ungranted")
        action = getattr(decision, "action", "")
        method = request.method.upper()
        expected = "case.read" if method in {"GET", "HEAD"} else "case.update"
        if action != expected:
            raise LegalResearchError("legal_research_ungranted")
        authorized_case = str(getattr(decision, "case_id", "") or "")
        query_case = str(request.query_params.get("case_id") or "")
        if authorized_case != case_id or (query_case and query_case != authorized_case):
            raise LegalResearchError("cross_case_id")
        resolver = _BOUND_HANDLERS.get()
        if resolver is None:
            raise LegalResearchError("legal_research_unavailable")
        try:
            mediator, workspace, _root = resolver()
            authority = current_workspace_case_authority()
        except Exception as exc:
            raise LegalResearchError("legal_research_unavailable") from exc
        if authority is None or getattr(authority, "case_id", None) != case_id:
            raise LegalResearchError("legal_research_ungranted")
        return mediator, workspace, authority

    @app.get(LEGAL_RESEARCH_PREFIX + "/{case_id}")
    async def read_legal_research(case_id: str, request: Request):
        try:
            mediator, _workspace, _authority = _authorized(request, case_id)
            payload = project_legal_research(_case_file_from_mediator(mediator))
        except LegalResearchError as exc:
            return _fail(exc)
        payload["case_id"] = case_id
        payload["admitted_law"] = False
        return JSONResponse(payload)

    @app.post(LEGAL_RESEARCH_PREFIX + "/{case_id}")
    async def update_legal_research(case_id: str, request: Request):
        try:
            mediator, workspace, authority = _authorized(request, case_id)
            body = await request.json()
            if not isinstance(body, dict):
                raise LegalResearchError("legal_research_field")
            payload = acquire_bounded_legal_sources(mediator, workspace, authority, body)
        except LegalResearchError as exc:
            return _fail(exc)
        payload["case_id"] = case_id
        payload["admitted_law"] = False
        return JSONResponse(payload)
