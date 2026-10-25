"""Attach canonical legal IR and source obligations for one authorized case.

The route is mounted by ``compose_case_routes``. Session and case-action checks
run before these handlers. Formalization goes through
``attach_canonical_legal_ir_source_obligations``, which reuses
``compile_canonical_legal_ir`` and current-source receipt verification.
Parsed IR, consistency, and emitted Lean text stay non-authority. This module
does not claim WebSocket or SSE support.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Mapping, MutableMapping

from starlette.requests import Request

TASK_ID = "CIMP-GUI-29"
DEFINITION_CORRESPONDENCE_TASK_ID = "CIMP-GUI-30"
PROOF_TRACE_TASK_ID = "CIMP-GUI-31"
LEGAL_ANALYSIS_PREFIX = "/api/legal-analysis"
DEFINITION_CORRESPONDENCE_ROUTE = LEGAL_ANALYSIS_PREFIX + "/{case_id}/definition-correspondence"
PROOF_TRACE_ROUTE = LEGAL_ANALYSIS_PREFIX + "/{case_id}/proof-traces"
_TRACE_STATUSES = ("executed", "degraded", "not_executed", "missing_prover", "timeout", "source_drift")
_UNAVAILABLE_TRACE_STATUSES = ("missing_prover", "timeout", "source_drift")
_BODY_CAP = 65536
_VOCABULARY_KEYS = ("actors", "actions", "objects", "qualifiers")


class LegalAnalysisError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def legal_analysis_http_status(code: str) -> int:
    if code in {"unauthenticated", "legal_analysis_unavailable"}:
        return 401
    if code in {"legal_analysis_field", "legal_analysis_bounds"}:
        return 422
    if code in {"canonical_compiler_unavailable", "definition_owner_unavailable"}:
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
    raise LegalAnalysisError("legal_analysis_unavailable")


def _string_list(value: Any, *, label: str, limit: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limit:
        raise LegalAnalysisError("legal_analysis_bounds")
    rows: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > 512:
            raise LegalAnalysisError("legal_analysis_field")
        rows.append(item)
    if label == "user_facts" and any(len(item) > 512 for item in rows):
        raise LegalAnalysisError("legal_analysis_bounds")
    return rows


def _request_body(body: Mapping[str, Any]) -> Dict[str, Any]:
    if len(json.dumps(body, default=str)) > _BODY_CAP:
        raise LegalAnalysisError("legal_analysis_bounds")
    source_text = body.get("source_text")
    if not isinstance(source_text, str) or not source_text.strip() or len(source_text) > 8192:
        raise LegalAnalysisError("legal_analysis_field")
    request_id = body.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 80:
        raise LegalAnalysisError("legal_analysis_field")
    vocabulary = body.get("vocabulary")
    if not isinstance(vocabulary, dict):
        raise LegalAnalysisError("legal_analysis_field")
    cleaned_vocabulary: Dict[str, list[str]] = {}
    for key in _VOCABULARY_KEYS:
        cleaned_vocabulary[key] = _string_list(vocabulary.get(key), label=key, limit=32)
    applicability = body.get("applicability_context", {})
    if not isinstance(applicability, dict):
        raise LegalAnalysisError("legal_analysis_field")
    legal_context = body.get("legal_context")
    if legal_context is not None and not isinstance(legal_context, dict):
        raise LegalAnalysisError("legal_analysis_field")
    typed = body.get("typed_obligations")
    if typed is not None and (not isinstance(typed, list) or len(typed) > 32):
        raise LegalAnalysisError("legal_analysis_bounds")
    current_source = body.get("current_source", source_text)
    if not isinstance(current_source, str):
        raise LegalAnalysisError("legal_analysis_field")
    emitted_lean = body.get("emitted_lean")
    if emitted_lean is not None and (not isinstance(emitted_lean, str) or len(emitted_lean) > 4096):
        raise LegalAnalysisError("legal_analysis_field")
    return {
        "source_text": source_text,
        "request_id": request_id,
        "vocabulary": cleaned_vocabulary,
        "applicability_context": applicability,
        "legal_context": legal_context,
        "user_facts": _string_list(body.get("user_facts"), label="user_facts", limit=16),
        "typed_obligations": typed,
        "current_source": current_source,
        "emitted_lean": emitted_lean,
        "supplied_receipt": body.get("receipt") if isinstance(body.get("receipt"), dict) else body.get("canonical_receipt"),
    }


def attach_case_canonical_legal_ir(mediator: Any, body: Mapping[str, Any]) -> Dict[str, Any]:
    """Public case entry. Stores the attachment on the intake case file."""

    from integrations.ipfs_datasets.logic import attach_canonical_legal_ir_source_obligations

    case_file = _case_file_from_mediator(mediator)
    fields = _request_body(body)
    supplied = fields.pop("supplied_receipt")
    payload = attach_canonical_legal_ir_source_obligations(supplied_receipt=supplied if isinstance(supplied, dict) else None, **fields)
    payload["task_id"] = TASK_ID
    payload["admitted_law"] = False
    payload["proof"] = False
    payload["legal_sufficiency"] = False
    if payload.get("status") == "unavailable":
        raise LegalAnalysisError("canonical_compiler_unavailable")
    case_file["canonical_legal_ir_attachment"] = payload
    return payload


def project_canonical_legal_ir(case_file: Mapping[str, Any]) -> Dict[str, Any]:
    stored = case_file.get("canonical_legal_ir_attachment") if isinstance(case_file, Mapping) else None
    if not isinstance(stored, dict):
        return {
            "task_id": TASK_ID,
            "operation": "attach_canonical_legal_ir_source_obligations",
            "status": "empty",
            "typed_obligations": [],
            "source_spans": [],
            "executed_proof": False,
            "governing_legal_authority": False,
            "ir_parse_is_proof": False,
            "consistency_is_proof": False,
            "lean_text_is_proof": False,
            "proof": False,
            "admitted_law": False,
            "limitations": ["No canonical legal IR attachment has been recorded."],
        }
    projected = dict(stored)
    projected["task_id"] = TASK_ID
    projected["executed_proof"] = False
    projected["governing_legal_authority"] = False
    projected["ir_parse_is_proof"] = False
    projected["consistency_is_proof"] = False
    projected["lean_text_is_proof"] = False
    projected["proof"] = False
    projected["admitted_law"] = False
    obligations = projected.get("typed_obligations")
    if isinstance(obligations, list):
        for item in obligations:
            if isinstance(item, dict):
                item["executed_proof"] = False
                item["governing_legal_authority"] = False
                item["discharged"] = False
    return projected


def _population_ids(value: Any) -> Dict[str, list[str]]:
    if not isinstance(value, dict):
        raise LegalAnalysisError("legal_analysis_field")
    cleaned: Dict[str, list[str]] = {}
    for key, items in value.items():
        if not isinstance(key, str) or not isinstance(items, list) or len(items) > 32:
            raise LegalAnalysisError("legal_analysis_bounds")
        rows = []
        for item in items:
            if not isinstance(item, str) or not item.strip() or len(item) > 256:
                raise LegalAnalysisError("legal_analysis_field")
            rows.append(item)
        cleaned[key] = rows
    return cleaned


def _owner_bundle(value: Any) -> Dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise LegalAnalysisError("legal_analysis_field")
    return value


def bind_case_definition_correspondence(mediator: Any, body: Mapping[str, Any]) -> Dict[str, Any]:
    """Public case entry for current definition and correspondence owners."""

    from integrations.ipfs_datasets.logic import bind_current_definition_correspondence_owners

    source_text = body.get("source_text")
    request_id = body.get("request_id")
    if not isinstance(source_text, str) or not isinstance(request_id, str):
        raise LegalAnalysisError("legal_analysis_field")
    case_file = _case_file_from_mediator(mediator)
    payload = bind_current_definition_correspondence_owners(
        source_text,
        request_id=request_id,
        declared_populations=_population_ids(body.get("declared_populations") or {}),
        scope_correspondence=_owner_bundle(body.get("scope_correspondence")),
        correspondence_requests=_owner_bundle(body.get("correspondence_requests")),
        applicability=_owner_bundle(body.get("applicability")),
        contextual_review=_owner_bundle(body.get("contextual_review")),
        supplied_receipt=body.get("receipt") if isinstance(body.get("receipt"), dict) else None,
        training_metrics=body.get("training_metrics"),
        graph_join=body.get("graph_join"),
    )
    payload["task_id"] = DEFINITION_CORRESPONDENCE_TASK_ID
    payload["authorizes_law"] = False
    payload["authorizes_proof"] = False
    payload["executed_proof"] = False
    payload["governing_legal_authority"] = False
    payload["proof"] = False
    if payload.get("status") == "unavailable":
        raise LegalAnalysisError("definition_owner_unavailable")
    case_file["definition_correspondence_binding"] = payload
    return payload


def project_definition_correspondence(case_file: Mapping[str, Any]) -> Dict[str, Any]:
    stored = case_file.get("definition_correspondence_binding") if isinstance(case_file, Mapping) else None
    if not isinstance(stored, dict):
        return {
            "task_id": DEFINITION_CORRESPONDENCE_TASK_ID,
            "operation": "bind_current_definition_correspondence_owners",
            "status": "empty",
            "owners": {},
            "authorizes_law": False,
            "authorizes_proof": False,
            "executed_proof": False,
            "governing_legal_authority": False,
            "proof": False,
            "limitations": ["No definition correspondence binding has been recorded."],
        }
    projected = dict(stored)
    projected["task_id"] = DEFINITION_CORRESPONDENCE_TASK_ID
    projected["authorizes_law"] = False
    projected["authorizes_proof"] = False
    projected["executed_proof"] = False
    projected["governing_legal_authority"] = False
    projected["proof"] = False
    return projected


def _bounded_text(value: Any, *, limit: int, required: bool) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or len(value) > limit:
        raise LegalAnalysisError("legal_analysis_field")
    text = value.strip()
    if required and not text:
        raise LegalAnalysisError("legal_analysis_field")
    return text


def _canonical_obligation_rows(case_file: Mapping[str, Any]) -> list[Dict[str, str]]:
    stored = case_file.get("canonical_legal_ir_attachment") if isinstance(case_file, Mapping) else None
    if not isinstance(stored, dict):
        return []
    rows = stored.get("typed_obligations")
    if not isinstance(rows, list):
        return []
    projected: list[Dict[str, str]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        obligation_id = str(item.get("obligation_id") or item.get("id") or "").strip()
        if not obligation_id:
            continue
        statement = str(item.get("statement") or item.get("text") or item.get("goal") or "").strip()
        source_span = str(item.get("source_span") or item.get("span") or item.get("source_binding") or "").strip()
        source_identity = str(item.get("source_identity") or stored.get("source_identity") or "").strip()
        projected.append({
            "obligation_id": obligation_id[:128],
            "statement": statement[:512],
            "source_span": source_span[:512],
            "source_identity": source_identity[:256],
        })
    return projected


def _classify_trace_row(row: Mapping[str, Any], *, envelope_source: str, expected_source: str) -> Dict[str, Any]:
    status = _bounded_text(row.get("proof_status"), limit=32, required=True)
    if status not in _TRACE_STATUSES:
        raise LegalAnalysisError("legal_analysis_field")
    obligation_source = _bounded_text(row.get("source_identity"), limit=256, required=False) or envelope_source
    engine_name = _bounded_text(row.get("engine_name"), limit=80, required=False)
    engine_version = _bounded_text(row.get("engine_version"), limit=80, required=False)
    counterexample = _bounded_text(row.get("counterexample"), limit=1024, required=False)
    timed_out = row.get("timed_out") is True or status == "timeout"
    prover_missing = row.get("prover_missing") is True or status == "missing_prover"
    drifted = (
        status == "source_drift"
        or (expected_source and envelope_source != expected_source)
        or (obligation_source and envelope_source and obligation_source != envelope_source)
    )
    if drifted:
        status = "source_drift"
    elif timed_out:
        status = "timeout"
    elif prover_missing or (status == "executed" and (not engine_name or not engine_version)):
        status = "missing_prover"
    elif status == "degraded":
        status = "degraded"
    elif status == "not_executed":
        status = "not_executed"
    elif status == "executed":
        status = "executed"
    green = status == "executed" and not counterexample and not drifted and not timed_out and not prover_missing
    if status in _UNAVAILABLE_TRACE_STATUSES or status in {"degraded", "not_executed"}:
        green = False
    return {
        "obligation_id": _bounded_text(row.get("obligation_id"), limit=128, required=True),
        "statement": _bounded_text(row.get("statement"), limit=512, required=True),
        "source_span": _bounded_text(row.get("source_span"), limit=512, required=True),
        "source_identity": obligation_source,
        "source_bound": bool(obligation_source and row.get("source_span")),
        "proof_status": status,
        "engine_name": engine_name,
        "engine_version": engine_version,
        "counterexample": counterexample,
        "green_checkmark": green,
        "legal_sufficiency": False,
        "executed_proof": False,
        "governing_legal_authority": False,
        "supplied_legal_sufficiency_ignored": row.get("legal_sufficiency") is True or row.get("green_checkmark") is True,
    }


def record_case_proof_traces(mediator: Any, body: Mapping[str, Any]) -> Dict[str, Any]:
    """Record a display trace. Caller flags cannot create legal sufficiency."""

    if not isinstance(body, Mapping) or len(json.dumps(body, default=str)) > _BODY_CAP:
        raise LegalAnalysisError("legal_analysis_bounds")
    request_id = _bounded_text(body.get("request_id"), limit=80, required=True)
    source_identity = _bounded_text(body.get("source_identity"), limit=256, required=True)
    expected_source = _bounded_text(body.get("expected_source_identity"), limit=256, required=False) or source_identity
    supplied = body.get("obligations")
    if not isinstance(supplied, list) or len(supplied) > 24:
        raise LegalAnalysisError("legal_analysis_bounds")
    case_file = _case_file_from_mediator(mediator)
    rows = [
        _classify_trace_row(item, envelope_source=source_identity, expected_source=expected_source)
        for item in supplied
        if isinstance(item, dict)
    ]
    if len(rows) != len(supplied):
        raise LegalAnalysisError("legal_analysis_field")
    seen = {item["obligation_id"] for item in rows}
    for canonical in _canonical_obligation_rows(case_file):
        if canonical["obligation_id"] in seen:
            continue
        rows.append(_classify_trace_row({
            "obligation_id": canonical["obligation_id"],
            "statement": canonical["statement"] or "source-bound obligation",
            "source_span": canonical["source_span"] or "unspecified-span",
            "source_identity": canonical["source_identity"] or source_identity,
            "proof_status": "not_executed",
            "engine_name": "",
            "engine_version": "",
        }, envelope_source=source_identity, expected_source=expected_source))
    engines = []
    seen_engines = set()
    counterexamples = []
    for item in rows:
        if item["engine_name"] and item["engine_version"]:
            key = (item["engine_name"], item["engine_version"])
            if key not in seen_engines:
                seen_engines.add(key)
                engines.append({"name": item["engine_name"], "version": item["engine_version"]})
        if item["counterexample"]:
            counterexamples.append({
                "obligation_id": item["obligation_id"],
                "trace": item["counterexample"],
                "legal_sufficiency": False,
                "green_checkmark": False,
            })
    payload = {
        "task_id": PROOF_TRACE_TASK_ID,
        "operation": "record_case_proof_traces",
        "request_id": request_id,
        "status": "visible" if rows else "empty",
        "source_identity": source_identity,
        "expected_source_identity": expected_source,
        "source_drift": source_identity != expected_source or any(item["proof_status"] == "source_drift" for item in rows),
        "obligations": rows,
        "counterexamples": counterexamples,
        "engine_versions": engines,
        "proof_status_counts": {name: sum(1 for item in rows if item["proof_status"] == name) for name in _TRACE_STATUSES},
        "legal_sufficiency": False,
        "proof": False,
        "executed_proof": False,
        "governing_legal_authority": False,
        "admitted_law": False,
        "supplied_legal_sufficiency_ignored": body.get("legal_sufficiency") is True or any(item["supplied_legal_sufficiency_ignored"] for item in rows),
        "limitations": [
            "Displayed proof status is not legal sufficiency.",
            "Missing prover, timeout, and source drift stay visible and are not green checkmarks.",
            "This view does not execute a prover and does not admit law.",
        ],
    }
    case_file["proof_trace_display"] = payload
    return payload


def project_proof_traces(case_file: Mapping[str, Any]) -> Dict[str, Any]:
    stored = case_file.get("proof_trace_display") if isinstance(case_file, Mapping) else None
    if not isinstance(stored, dict):
        return {
            "task_id": PROOF_TRACE_TASK_ID,
            "operation": "record_case_proof_traces",
            "status": "empty",
            "obligations": [],
            "counterexamples": [],
            "engine_versions": [],
            "proof_status_counts": {name: 0 for name in _TRACE_STATUSES},
            "legal_sufficiency": False,
            "proof": False,
            "executed_proof": False,
            "governing_legal_authority": False,
            "admitted_law": False,
            "source_drift": False,
            "limitations": ["No proof trace has been recorded. Absence is not a successful proof."],
        }
    projected = dict(stored)
    projected["task_id"] = PROOF_TRACE_TASK_ID
    projected["legal_sufficiency"] = False
    projected["proof"] = False
    projected["executed_proof"] = False
    projected["governing_legal_authority"] = False
    projected["admitted_law"] = False
    obligations = projected.get("obligations")
    if isinstance(obligations, list):
        for item in obligations:
            if isinstance(item, dict):
                item["legal_sufficiency"] = False
                item["executed_proof"] = False
                item["governing_legal_authority"] = False
                if item.get("proof_status") in _UNAVAILABLE_TRACE_STATUSES or item.get("proof_status") in {"degraded", "not_executed"}:
                    item["green_checkmark"] = False
                if item.get("counterexample"):
                    item["green_checkmark"] = False
    return projected


def mount_legal_analysis_routes(app: Any) -> None:
    """Mount canonical IR attachment routes. Authorization middleware protects the prefix."""

    from fastapi.responses import JSONResponse

    from applications.case_routes import _BOUND_HANDLERS
    from applications.workspace_case_authority import current_workspace_case_authority

    def _fail(exc: LegalAnalysisError) -> JSONResponse:
        return JSONResponse(
            {
                "error": exc.code,
                "status": "denied",
                "executed_proof": False,
                "governing_legal_authority": False,
                "proof": False,
            },
            status_code=legal_analysis_http_status(exc.code),
        )

    def _authorized(request: Request, case_id: str):
        decision = getattr(request.state, "case_authorization", None)
        if decision is None or getattr(decision, "permits_case_content", False) is not True:
            raise LegalAnalysisError("legal_analysis_ungranted")
        action = getattr(decision, "action", "")
        method = request.method.upper()
        expected = "case.read" if method in {"GET", "HEAD"} else "case.update"
        if action != expected:
            raise LegalAnalysisError("legal_analysis_ungranted")
        authorized_case = str(getattr(decision, "case_id", "") or "")
        query_case = str(request.query_params.get("case_id") or "")
        if authorized_case != case_id or (query_case and query_case != authorized_case):
            raise LegalAnalysisError("cross_case_id")
        resolver = _BOUND_HANDLERS.get()
        if resolver is None:
            raise LegalAnalysisError("legal_analysis_unavailable")
        try:
            mediator, _workspace, _root = resolver()
            authority = current_workspace_case_authority()
        except Exception as exc:
            raise LegalAnalysisError("legal_analysis_unavailable") from exc
        if authority is None or getattr(authority, "case_id", None) != case_id:
            raise LegalAnalysisError("legal_analysis_ungranted")
        return mediator

    @app.get(LEGAL_ANALYSIS_PREFIX + "/{case_id}")
    async def read_legal_analysis(case_id: str, request: Request):
        try:
            mediator = _authorized(request, case_id)
            payload = project_canonical_legal_ir(_case_file_from_mediator(mediator))
        except LegalAnalysisError as exc:
            return _fail(exc)
        payload["case_id"] = case_id
        return JSONResponse(payload)

    @app.post(LEGAL_ANALYSIS_PREFIX + "/{case_id}")
    async def attach_legal_analysis(case_id: str, request: Request):
        try:
            mediator = _authorized(request, case_id)
            body = await request.json()
            if not isinstance(body, dict):
                raise LegalAnalysisError("legal_analysis_field")
            payload = attach_case_canonical_legal_ir(mediator, body)
        except LegalAnalysisError as exc:
            return _fail(exc)
        payload["case_id"] = case_id
        payload["executed_proof"] = False
        payload["governing_legal_authority"] = False
        return JSONResponse(payload)

    @app.get(LEGAL_ANALYSIS_PREFIX + "/{case_id}/definition-correspondence")
    async def read_definition_correspondence(case_id: str, request: Request):
        try:
            mediator = _authorized(request, case_id)
            payload = project_definition_correspondence(_case_file_from_mediator(mediator))
        except LegalAnalysisError as exc:
            return _fail(exc)
        payload["case_id"] = case_id
        payload["authorizes_law"] = False
        payload["authorizes_proof"] = False
        return JSONResponse(payload)

    @app.post(LEGAL_ANALYSIS_PREFIX + "/{case_id}/definition-correspondence")
    async def bind_definition_correspondence(case_id: str, request: Request):
        try:
            mediator = _authorized(request, case_id)
            body = await request.json()
            if not isinstance(body, dict):
                raise LegalAnalysisError("legal_analysis_field")
            if len(json.dumps(body, default=str)) > _BODY_CAP:
                raise LegalAnalysisError("legal_analysis_bounds")
            payload = bind_case_definition_correspondence(mediator, body)
        except LegalAnalysisError as exc:
            return _fail(exc)
        payload["case_id"] = case_id
        payload["authorizes_law"] = False
        payload["authorizes_proof"] = False
        payload["executed_proof"] = False
        payload["governing_legal_authority"] = False
        return JSONResponse(payload)

    @app.get(LEGAL_ANALYSIS_PREFIX + "/{case_id}/proof-traces")
    async def read_proof_traces(case_id: str, request: Request):
        try:
            mediator = _authorized(request, case_id)
            payload = project_proof_traces(_case_file_from_mediator(mediator))
        except LegalAnalysisError as exc:
            return _fail(exc)
        payload["case_id"] = case_id
        payload["legal_sufficiency"] = False
        payload["executed_proof"] = False
        return JSONResponse(payload)

    @app.post(LEGAL_ANALYSIS_PREFIX + "/{case_id}/proof-traces")
    async def record_proof_traces(case_id: str, request: Request):
        try:
            mediator = _authorized(request, case_id)
            body = await request.json()
            if not isinstance(body, dict):
                raise LegalAnalysisError("legal_analysis_field")
            payload = record_case_proof_traces(mediator, body)
        except LegalAnalysisError as exc:
            return _fail(exc)
        payload["case_id"] = case_id
        payload["legal_sufficiency"] = False
        payload["executed_proof"] = False
        payload["governing_legal_authority"] = False
        return JSONResponse(payload)
