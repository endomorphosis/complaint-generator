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
import hashlib
from copy import deepcopy
from typing import Any, Dict, Mapping, MutableMapping

from starlette.requests import Request

TASK_ID = "CIMP-GUI-29"
DEFINITION_CORRESPONDENCE_TASK_ID = "CIMP-GUI-30"
LEGAL_ANALYSIS_PREFIX = "/api/legal-analysis"
_BODY_CAP = 65536
_VOCABULARY_KEYS = ("actors", "actions", "objects", "qualifiers")


class LegalAnalysisError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def legal_analysis_http_status(code: str) -> int:
    if code == "unauthenticated":
        return 401
    if code in {"legal_analysis_field", "legal_analysis_bounds", "client_case_authority"}:
        return 422
    if code in {"canonical_compiler_unavailable", "definition_owner_unavailable", "legal_analysis_unavailable", "unlock_needed"}:
        return 503
    if code in {"revision_conflict", "legal_source_changed", "legal_source_unavailable"}:
        return 409
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
    """Legacy in-process utility; not the authenticated GUI publication owner."""

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
    projected = deepcopy(stored)
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


def _document_sha256(value: Mapping[str, Any]) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError):
        raise LegalAnalysisError("legal_analysis_field") from None
    return hashlib.sha256(raw).hexdigest()


def current_case_legal_ir_source(case_file: Mapping[str, Any], source_hash: str, *, case_id: str) -> Dict[str, Any]:
    """Revalidate the saved current SourceRecord without compilation or mutation."""
    from integrations.ipfs_datasets.logic import prepare_acquired_authority_record
    digest = source_hash[7:] if isinstance(source_hash, str) and source_hash.startswith("sha256:") else source_hash
    if (not isinstance(digest, str) or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)):
        raise LegalAnalysisError("legal_analysis_field")
    index = case_file.get("legal_source_passage_index")
    stored = index.get(source_hash) if isinstance(index, Mapping) else None
    if not isinstance(stored, Mapping):
        raise LegalAnalysisError("legal_source_unavailable")
    if (stored.get("version_state") == "stale"
            or (stored.get("current_version") and stored.get("current_version") != stored.get("version"))):
        raise LegalAnalysisError("legal_source_changed")
    admission = stored.get("source_admission")
    source = stored.get("canonical_source")
    record = stored.get("reviewed_source_record")
    if not all(isinstance(item, Mapping) for item in (admission, source, record)):
        raise LegalAnalysisError("legal_source_unavailable")
    metadata = record.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    prepared = prepare_acquired_authority_record(source,
        jurisdiction=str(record.get("jurisdiction") or ""), as_of_date=str(metadata.get("as_of_date") or ""))
    record_ids = admission.get("stored_record_ids")
    if (prepared.get("status") != "admitted" or prepared.get("record") != record
            or admission.get("record") != record or admission.get("status") != "admitted"
            or admission.get("proof") is not False or admission.get("hashes") != prepared.get("hashes")
            or admission.get("source_record_sha256") != _document_sha256(record)
            or not isinstance(record_ids, list) or not record_ids
            or any(type(item) is not int or item < 0 for item in record_ids)):
        raise LegalAnalysisError("legal_source_changed")
    text = record.get("content")
    if (not isinstance(text, str) or not text or len(text) > 8192
            or hashlib.sha256(text.encode()).hexdigest() != digest
            or stored.get("content_hash") != source_hash or stored.get("source_passage") != text):
        raise LegalAnalysisError("legal_source_changed")
    reviews = case_file.get("legal_authority_admissions")
    current_review = next((row for row in reversed(reviews) if isinstance(row, Mapping)
        and row.get("content_hash") == source_hash), None) if isinstance(reviews, list) else None
    if (not current_review or current_review.get("case_id") != case_id
            or current_review.get("source_status") != "source_admitted"
            or current_review.get("source_admission") != admission
            or current_review.get("proof") is not False):
        raise LegalAnalysisError("legal_source_unavailable")
    return {"stored": stored, "record": record, "admission": admission,
        "review": current_review, "text": text, "metadata": metadata}


def compile_current_case_legal_ir(case_file: Mapping[str, Any], knowledge_graph: Mapping[str, Any],
                                  body: Mapping[str, Any], *, case_id: str,
                                  source_scope_sha256: str) -> Dict[str, Any]:
    """Compile one freshly read, reviewed SourceRecord; grant no access here.

    The authenticated Workspace owner supplies the copied current case and KG.
    Client fields select a stored source and annotate exact spans only. Neither
    source admission nor compiler execution appoints governing law or a proof.
    """
    from complaint_phases.knowledge_graph import KnowledgeGraph
    from integrations.ipfs_datasets.logic import attach_canonical_legal_ir_source_obligations
    from mediator.integrations.graph_tools import project_factual_kg

    if not isinstance(body, Mapping) or not isinstance(case_file, Mapping):
        raise LegalAnalysisError("legal_analysis_field")
    forbidden = {"source_text", "current_source", "legal_context", "applicability_context", "user_facts",
        "factual_premises", "admitted_law", "source_record", "canonical_source", "receipt", "canonical_receipt"}
    if forbidden.intersection(body):
        raise LegalAnalysisError("client_case_authority")
    allowed = {"request_id", "source_content_hash", "vocabulary", "typed_obligations", "emitted_lean",
        "expected_private_revision", "expected_session_revision"}
    if set(body) - allowed or len(json.dumps(body, default=str)) > _BODY_CAP:
        raise LegalAnalysisError("legal_analysis_bounds")
    source_hash = body.get("source_content_hash")
    selected = current_case_legal_ir_source(case_file, source_hash, case_id=case_id)
    stored, record, admission = selected["stored"], selected["record"], selected["admission"]
    current_review, text, metadata = selected["review"], selected["text"], selected["metadata"]
    fields = _request_body({**dict(body), "source_text": text})
    fields.pop("supplied_receipt")
    context = case_file.get("legal_context")
    context = context if isinstance(context, Mapping) else {}
    applicability = current_review.get("governing_applicability")
    if applicability not in {"applicable", "inapplicable", "limited", "unknown"}:
        applicability = "unknown"
    # A source can be admitted to storage while its case applicability remains
    # unresolved. Retain that distinction instead of manufacturing applicable law.
    declared_applicability = case_file.get("legal_context_applicability")
    if (declared_applicability != "explicit"
            or admission.get("source_scope_sha256") != source_scope_sha256):
        applicability = "unknown"
    source_context = {"authority_version": str(metadata.get("authority_version") or ""),
        "effective_date": str(metadata.get("effective_date") or ""), "applicability": applicability}
    for name, value in (("jurisdiction", context.get("jurisdiction")),
                        ("forum", case_file.get("legal_context_forum"))):
        if isinstance(value, str) and value.strip():
            source_context[name] = value
    try:
        graph = KnowledgeGraph.from_dict(deepcopy(dict(knowledge_graph)))
        factual = project_factual_kg(graph, case_id=case_id)
    except (TypeError, ValueError, KeyError, AttributeError):
        raise LegalAnalysisError("legal_analysis_unavailable") from None
    facts = [row for row in factual.get("user_statements", [])
        if isinstance(row, dict) and row.get("admitted_user_fact") is True]
    bounded = [row for row in facts if isinstance(row.get("text"), str) and len(row["text"]) <= 512][:16]
    fields.update(current_source=text, user_facts=[row["text"] for row in bounded],
        applicability_context=source_context,
        legal_context={"citation": str(record.get("citation") or ""),
            "authority_locator": str(metadata.get("source_locator") or ""),
            "authority_version": str(metadata.get("authority_version") or ""), "source_text": text})
    payload = attach_canonical_legal_ir_source_obligations(**fields)
    if payload.get("status") == "unavailable":
        raise LegalAnalysisError("canonical_compiler_unavailable")
    payload.update(task_id=TASK_ID, case_id=case_id, admitted_law=False, proof=False, legal_sufficiency=False,
        source_binding={"content_hash": source_hash, "source_record_sha256": _document_sha256(record),
            "source_scope_sha256": source_scope_sha256,
            "authority_locator": str(metadata.get("source_locator") or ""),
            "authority_version": str(metadata.get("authority_version") or ""),
            "source_storage_admitted": True, "governing_applicability": applicability},
        factual_premise_bindings=[{"assertion_id": row["assertion_id"], "source_identity": row["source_identity"]}
            for row in bounded], factual_premises_truncated=len(bounded) != len(facts))
    return payload


def mount_legal_analysis_routes(app: Any) -> None:
    """Serve only the current encrypted owner, under the issued case capability."""
    from fastapi.responses import JSONResponse
    from starlette.concurrency import run_in_threadpool
    from applications.case_routes import _BOUND_HANDLERS
    from applications.complaint_workspace import (ComplaintWorkspaceService, WorkspaceAccess,
        WorkspaceAuthorizationDenied, WorkspacePersistenceError, workspace_access_scope)
    from applications.workspace_case_authority import (current_workspace_case_authority,
        WorkspaceCaseAuthorityError)

    def fail(code):
        return JSONResponse({"error": code, "status": "denied", "executed_proof": False,
            "governing_legal_authority": False, "proof": False}, status_code=legal_analysis_http_status(code))

    def authorized(request, case_id):
        decision = getattr(request.state, "case_authorization", None)
        expected = "case.read" if request.method.upper() in {"GET", "HEAD"} else "case.update"
        if (decision is None or getattr(decision, "permits_case_content", False) is not True
                or getattr(decision, "action", "") != expected):
            raise LegalAnalysisError("legal_analysis_ungranted")
        query_case = str(request.query_params.get("case_id") or "")
        if getattr(decision, "case_id", "") != case_id or (query_case and query_case != case_id):
            raise LegalAnalysisError("cross_case_id")
        resolver = _BOUND_HANDLERS.get()
        if resolver is None:
            raise LegalAnalysisError("legal_analysis_unavailable")
        try:
            _mediator, workspace, _root = resolver()
        except Exception:
            raise LegalAnalysisError("legal_analysis_unavailable") from None
        if not isinstance(workspace, ComplaintWorkspaceService):
            raise LegalAnalysisError("legal_analysis_unavailable")
        principal = getattr(request.state, "browser_principal", None)
        actor = getattr(principal, "principal_id", None)
        authority = current_workspace_case_authority()
        if not actor or authority is None or authority.case_id != case_id:
            raise LegalAnalysisError("legal_analysis_ungranted")
        authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
        return workspace, authority, actor

    def execute(workspace, actor, case_id, body):
        with workspace_access_scope(WorkspaceAccess.authenticated(actor, case_id)):
            if body is None:
                return workspace.read_case_legal_analysis(actor, case_id=case_id)
            return workspace.attach_case_legal_analysis(actor, case_id=case_id, request=body)

    async def dispatch(request, case_id, write):
        try:
            workspace, authority, actor = authorized(request, case_id)
            body = None
            if write:
                try:
                    body = await request.json()
                except (UnicodeDecodeError, ValueError):
                    raise LegalAnalysisError("legal_analysis_field") from None
                if not isinstance(body, dict):
                    raise LegalAnalysisError("legal_analysis_field")
            # Permit real logout/revocation to complete while local compilation
            # runs; copied ContextVars retain only this issued request scope.
            payload = await run_in_threadpool(execute, workspace, actor, case_id, body)
            authority.revalidate(actor_principal_id=actor, workspace=workspace, require_owner=True)
            return JSONResponse(payload)
        except (WorkspaceAuthorizationDenied, WorkspaceCaseAuthorityError):
            return fail("legal_analysis_ungranted")
        except WorkspacePersistenceError as exc:
            return fail("revision_conflict" if exc.code == "revision_conflict" else (
                "unlock_needed" if exc.code == "unlock_needed" else "legal_analysis_unavailable"))
        except LegalAnalysisError as exc:
            return fail(exc.code)

    @app.get(LEGAL_ANALYSIS_PREFIX + "/{case_id}")
    async def read_legal_analysis(case_id: str, request: Request):
        return await dispatch(request, case_id, False)

    @app.post(LEGAL_ANALYSIS_PREFIX + "/{case_id}")
    async def attach_legal_analysis(case_id: str, request: Request):
        return await dispatch(request, case_id, True)


    # Retain the Native30 owner path during isolated characterization.
    def _authorized(request, case_id):
        authorized(request, case_id)
        return _BOUND_HANDLERS.get()()[0]

    def _fail(exc):
        return fail(exc.code)

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

