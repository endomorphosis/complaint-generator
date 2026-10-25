"""Scoped lawyer review of sourced interpretations, separate from model and proof records.

Assigned lawyers propose and review under ``case.review``. Each human approval
stores the exact case, source, fact, and proof revisions it saw. A later change
to law or facts leaves that approval in place and refuses promotion. Model
suggestions and machine proof stay in their own attributed lists. None of these
records is governing law, legal sufficiency, or an owner-key grant.

This module does not claim WebSocket, SSE, or streaming support.
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping

from starlette.requests import Request

TASK_ID = "CIMP-GUI-32"
LAWYER_REVIEW_ROUTE = "/api/legal-analysis/{case_id}/lawyer-reviews"
LAWYER_WORKSPACE_ROUTE = "/api/legal-analysis/{case_id}/lawyer-workspace"
_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "lawyer_workspace.html"
_BODY_CAP = 65536
_HUMAN = "human_legal_review"
_MODEL = "model_suggestion"
_MACHINE = "machine_proof"
_KINDS = (_HUMAN, _MODEL, _MACHINE)
_DECISIONS = {"approved", "rejected", "withheld"}
_SOURCE_UNBOUND = "source-unbound"
_FACTS_UNBOUND = "facts-unbound"
_PROOF_UNBOUND = "proof-unbound"


class CaseReviewError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def case_review_http_status(code: str) -> int:
    if code in {"unauthenticated", "lawyer_review_unavailable"}:
        return 401
    if code in {"lawyer_review_field", "lawyer_review_bounds"}:
        return 422
    if code in {"stale_revision", "stale_approval", "replay_mismatch"}:
        return 409
    return 403


def _digest(kind: str, material: str) -> str:
    payload = f"{kind}\n{material}".encode("utf-8")
    return kind + "-" + hashlib.sha256(payload).hexdigest()[:32]


def _text(value: Any, *, limit: int, required: bool) -> str:
    if value is None or value == "":
        if required:
            raise CaseReviewError("lawyer_review_field")
        return ""
    if not isinstance(value, str):
        raise CaseReviewError("lawyer_review_field")
    stripped = value.strip()
    if required and not stripped:
        raise CaseReviewError("lawyer_review_field")
    if len(value) > limit:
        raise CaseReviewError("lawyer_review_bounds")
    return stripped


def _case_file(mediator: Any) -> MutableMapping[str, Any]:
    phase_manager = getattr(mediator, "phase_manager", None)
    if phase_manager is not None and hasattr(phase_manager, "get_phase_data"):
        from complaint_phases.phase_manager import ComplaintPhase

        stored = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
        if isinstance(stored, dict):
            return stored
    stored = getattr(mediator, "intake_case_file", None)
    if isinstance(stored, dict):
        return stored
    raise CaseReviewError("lawyer_review_unavailable")


def _source_material(case_file: Mapping[str, Any]) -> tuple[str, str]:
    anchor = case_file.get("review_source_anchor")
    if isinstance(anchor, dict):
        identity = str(anchor.get("source_identity") or "").strip()
        text = str(anchor.get("source_text") or "")
        if identity and text.strip():
            return identity[:256], text
    attachment = case_file.get("canonical_legal_ir_attachment")
    if isinstance(attachment, dict):
        identity = str(attachment.get("source_identity") or "").strip()
        text = str(attachment.get("source_text") or "")
        if not text.strip():
            obligations = attachment.get("typed_obligations")
            if isinstance(obligations, list):
                text = json.dumps(obligations, sort_keys=True, default=str)
        if identity and text.strip():
            return identity[:256], text
    return "", ""


def _fact_material(case_file: Mapping[str, Any]) -> str:
    facts = case_file.get("review_fact_anchor")
    if isinstance(facts, str) and facts.strip():
        return facts
    if isinstance(facts, list) and facts:
        return "\n".join(str(item) for item in facts)
    return ""


def _proof_material(case_file: Mapping[str, Any]) -> str:
    trace = case_file.get("proof_trace_display")
    if not isinstance(trace, dict):
        return ""
    rows = []
    obligations = trace.get("obligations")
    if isinstance(obligations, list):
        for item in obligations:
            if not isinstance(item, dict):
                continue
            rows.append("|".join((
                str(item.get("obligation_id") or ""),
                str(item.get("proof_status") or ""),
                str(item.get("source_identity") or ""),
                str(item.get("source_span") or ""),
                str(item.get("engine_name") or ""),
                str(item.get("engine_version") or ""),
            )))
    return str(trace.get("source_identity") or "") + "\n" + "\n".join(rows)


def live_revisions(case_file: Mapping[str, Any], *, case_revision: int) -> Dict[str, Any]:
    """Revision tuple a review must match. Absence is an explicit unbound token."""

    if type(case_revision) is not int or isinstance(case_revision, bool) or case_revision < 0:
        raise CaseReviewError("lawyer_review_field")
    identity, text = _source_material(case_file)
    facts = _fact_material(case_file)
    proof = _proof_material(case_file)
    return {
        "case_revision": case_revision,
        "source_identity": identity,
        "source_revision": _digest("source", identity + "\n" + text) if identity else _SOURCE_UNBOUND,
        "fact_revision": _digest("facts", facts) if facts else _FACTS_UNBOUND,
        "proof_revision": _digest("proof", proof) if proof else _PROOF_UNBOUND,
        "proof_bound": bool(proof),
        "governing_legal_authority": False,
        "legal_sufficiency": False,
        "admitted_law": False,
        "promotes_changed_law": False,
        "promotes_changed_facts": False,
    }


def _matches(record: Mapping[str, Any], live: Mapping[str, Any]) -> bool:
    return (
        record.get("case_revision") == live["case_revision"]
        and record.get("source_revision") == live["source_revision"]
        and record.get("fact_revision") == live["fact_revision"]
        and record.get("proof_revision") == live["proof_revision"]
    )


def _annotate(record: Mapping[str, Any], live: Mapping[str, Any]) -> Dict[str, Any]:
    current = _matches(record, live)
    human_approval = (
        record.get("record_kind") == _HUMAN
        and record.get("author_kind") == "human"
        and record.get("decision") == "approved"
    )
    promoted = record.get("operation") == "promote" and record.get("status") == "promoted_for_revision"
    projected = dict(record)
    projected["applies_to_current_revisions"] = current
    projected["stale"] = not current
    projected["accepted_for_bound_revision"] = bool(current and human_approval and record.get("operation") == "review")
    projected["promoted_for_current_revisions"] = bool(current and promoted)
    projected["promotes_changed_law"] = False
    projected["promotes_changed_facts"] = False
    projected["governing_legal_authority"] = False
    projected["legal_sufficiency"] = False
    projected["admitted_law"] = False
    projected["admitted_facts"] = False
    return projected


def project_lawyer_reviews(case_file: Mapping[str, Any], *, case_revision: int) -> Dict[str, Any]:
    live = live_revisions(case_file, case_revision=case_revision)
    stored = case_file.get("lawyer_review_ledger")
    rows = [_annotate(item, live) for item in stored if isinstance(item, dict)] if isinstance(stored, list) else []
    human = [item for item in rows if item.get("record_kind") == _HUMAN]
    model = [item for item in rows if item.get("record_kind") == _MODEL]
    machine = [item for item in rows if item.get("record_kind") == _MACHINE]
    current_promotion = next((item for item in reversed(human) if item.get("promoted_for_current_revisions")), None)
    return {
        "task_id": TASK_ID,
        "operation": "project_lawyer_reviews",
        "status": "visible" if rows else "empty",
        "live_revisions": live,
        "human_legal_reviews": human,
        "model_suggestions": model,
        "machine_proofs": machine,
        "records_are_separate": True,
        "current_promotion": current_promotion,
        "stale_approvals_promote": False,
        "promotes_changed_law": False,
        "promotes_changed_facts": False,
        "governing_legal_authority": False,
        "legal_sufficiency": False,
        "admitted_law": False,
        "admitted_facts": False,
        "limitations": [
            "Human legal review, model suggestions, and machine proof are separate attributed records.",
            "A stale approval does not promote changed law or changed facts.",
            "Lawyer review is not governing law, legal sufficiency, or an owner-key grant.",
            "Machine proof status is not a human approval.",
        ],
    }


def _require_live(body: Mapping[str, Any], live: Mapping[str, Any]) -> None:
    expected = {
        "case_revision": body.get("expected_case_revision"),
        "source_revision": body.get("expected_source_revision"),
        "fact_revision": body.get("expected_fact_revision"),
        "proof_revision": body.get("expected_proof_revision"),
    }
    for key, value in expected.items():
        if value != live[key]:
            raise CaseReviewError("stale_revision")


def _base_record(body: Mapping[str, Any], live: Mapping[str, Any], *, actor_principal_id: str,
                 canonical_owner_principal_id: str, membership: str, kind: str, author_kind: str,
                 operation: str) -> Dict[str, Any]:
    if actor_principal_id == canonical_owner_principal_id:
        raise CaseReviewError("actor_is_not_canonical_owner")
    return {
        "task_id": TASK_ID,
        "record_id": _digest("record", actor_principal_id + "\n" + operation + "\n" + _text(body.get("request_id"), limit=80, required=True) + "\n" + str(len(json.dumps(live)))),
        "request_id": _text(body.get("request_id"), limit=80, required=True),
        "record_kind": kind,
        "author_kind": author_kind,
        "operation": operation,
        "actor_principal_id": actor_principal_id,
        "canonical_owner_principal_id": canonical_owner_principal_id,
        "actor_is_canonical_owner": False,
        "membership": membership,
        "case_revision": live["case_revision"],
        "source_identity": live["source_identity"],
        "source_revision": live["source_revision"],
        "fact_revision": live["fact_revision"],
        "proof_revision": live["proof_revision"],
        "governing_legal_authority": False,
        "legal_sufficiency": False,
        "admitted_law": False,
        "admitted_facts": False,
        "promotes_changed_law": False,
        "promotes_changed_facts": False,
    }


def submit_lawyer_review(mediator: Any, body: Mapping[str, Any], *, actor_principal_id: str,
                         canonical_owner_principal_id: str, case_revision: int, membership: str) -> Dict[str, Any]:
    """Append one attributed review record. Stale revisions are not stored as current."""

    if membership != "assigned-lawyer":
        raise CaseReviewError("lawyer_assignment_required")
    if not isinstance(body, Mapping) or len(json.dumps(body, default=str)) > _BODY_CAP:
        raise CaseReviewError("lawyer_review_bounds")
    operation = _text(body.get("operation"), limit=40, required=True)
    if operation not in {"propose", "review", "promote", "record_model_suggestion", "record_machine_proof"}:
        raise CaseReviewError("lawyer_review_field")
    case_file = _case_file(mediator)
    live = live_revisions(case_file, case_revision=case_revision)
    _require_live(body, live)
    stored = case_file.get("lawyer_review_ledger")
    ledger = stored if isinstance(stored, list) else []
    request_id = _text(body.get("request_id"), limit=80, required=True)
    for existing in ledger:
        if isinstance(existing, dict) and existing.get("request_id") == request_id:
            if existing.get("operation") != operation:
                raise CaseReviewError("replay_mismatch")
            projected = project_lawyer_reviews(case_file, case_revision=case_revision)
            projected["record"] = _annotate(existing, live)
            projected["operation"] = operation
            return projected

    if operation in {"propose", "review", "promote"}:
        record = _base_record(body, live, actor_principal_id=actor_principal_id,
            canonical_owner_principal_id=canonical_owner_principal_id, membership=membership,
            kind=_HUMAN, author_kind="human", operation=operation)
        record["interpretation"] = _text(body.get("interpretation"), limit=2000, required=operation == "propose")
        if operation == "propose":
            record["decision"] = "proposed"
            record["status"] = "proposed"
            citation = _text(body.get("source_citation"), limit=512, required=True)
            record["source_citation"] = citation
        elif operation == "review":
            decision = _text(body.get("decision"), limit=32, required=True)
            if decision not in _DECISIONS:
                raise CaseReviewError("lawyer_review_field")
            proposal_id = _text(body.get("proposal_id"), limit=80, required=True)
            proposal = next((item for item in ledger if isinstance(item, dict) and item.get("record_id") == proposal_id), None)
            if proposal is None or proposal.get("record_kind") != _HUMAN or proposal.get("operation") != "propose":
                raise CaseReviewError("proposal_required")
            if not _matches(proposal, live):
                raise CaseReviewError("stale_approval")
            record["decision"] = decision
            record["status"] = decision
            record["proposal_id"] = proposal_id
            record["interpretation"] = str(proposal.get("interpretation") or "")
            record["source_citation"] = str(proposal.get("source_citation") or "")
        else:
            approval_id = _text(body.get("approval_id"), limit=80, required=True)
            approval = next((item for item in ledger if isinstance(item, dict) and item.get("record_id") == approval_id), None)
            if approval is None or approval.get("record_kind") != _HUMAN or approval.get("decision") != "approved":
                raise CaseReviewError("approval_required")
            if not _matches(approval, live):
                raise CaseReviewError("stale_approval")
            record["decision"] = "approved"
            record["status"] = "promoted_for_revision"
            record["approval_id"] = approval_id
            record["proposal_id"] = approval.get("proposal_id")
            record["interpretation"] = str(approval.get("interpretation") or "")
            record["source_citation"] = str(approval.get("source_citation") or "")
            record["accepted_for_bound_revision"] = True
    elif operation == "record_model_suggestion":
        if body.get("decision") in _DECISIONS or body.get("approved") is True:
            raise CaseReviewError("model_cannot_approve")
        record = _base_record(body, live, actor_principal_id=actor_principal_id,
            canonical_owner_principal_id=canonical_owner_principal_id, membership=membership,
            kind=_MODEL, author_kind="model", operation=operation)
        record["model_id"] = _text(body.get("model_id"), limit=80, required=True)
        record["suggestion"] = _text(body.get("suggestion"), limit=2000, required=True)
        record["decision"] = "suggestion"
        record["status"] = "not_a_human_review"
        record["submitted_by_actor_principal_id"] = actor_principal_id
    else:
        if body.get("decision") in _DECISIONS or body.get("approved") is True:
            raise CaseReviewError("machine_proof_cannot_approve")
        record = _base_record(body, live, actor_principal_id=actor_principal_id,
            canonical_owner_principal_id=canonical_owner_principal_id, membership=membership,
            kind=_MACHINE, author_kind="machine", operation=operation)
        record["engine_name"] = _text(body.get("engine_name"), limit=80, required=False)
        record["engine_version"] = _text(body.get("engine_version"), limit=80, required=False)
        record["proof_status"] = "referenced" if live["proof_bound"] else "not_executed"
        record["decision"] = "machine_proof"
        record["status"] = "not_a_human_review"
        record["executed_proof_is_legal_sufficiency"] = False
    if body.get("governing_legal_authority") is True or body.get("legal_sufficiency") is True or body.get("admitted_law") is True:
        record["supplied_authority_ignored"] = True
    if case_file.get("lawyer_review_ledger") is not ledger:
        case_file["lawyer_review_ledger"] = ledger
    ledger.append(record)
    projected = project_lawyer_reviews(case_file, case_revision=case_revision)
    projected["record"] = _annotate(record, live)
    projected["operation"] = operation
    return projected


def render_lawyer_workspace(projection: Mapping[str, Any]) -> str:
    """Fill the lawyer workspace template. The page does not treat stale rows as current."""

    template = _TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(projection, sort_keys=True)
    safe = html.escape(payload, quote=True)
    if "__LAWYER_REVIEW_JSON__" not in template:
        raise CaseReviewError("lawyer_review_unavailable")
    return template.replace("__LAWYER_REVIEW_JSON__", safe)


def mount_lawyer_review_routes(app: Any) -> None:
    """Mount lawyer review beside legal analysis. Middleware still authorizes the prefix."""

    from fastapi.responses import HTMLResponse, JSONResponse

    from applications.case_routes import _BOUND_HANDLERS
    from applications.workspace_case_authority import current_workspace_case_authority

    def _fail(exc: CaseReviewError) -> JSONResponse:
        return JSONResponse(
            {
                "error": exc.code,
                "task_id": TASK_ID,
                "promotes_changed_law": False,
                "promotes_changed_facts": False,
                "governing_legal_authority": False,
                "legal_sufficiency": False,
                "admitted_law": False,
            },
            status_code=case_review_http_status(exc.code),
        )

    def _authorized(request: Request, case_id: str, *, write: bool):
        decision = getattr(request.state, "case_authorization", None)
        if decision is None or getattr(decision, "permits_case_content", False) is not True:
            raise CaseReviewError("lawyer_review_ungranted")
        expected = "case.review" if write else "case.read"
        if getattr(decision, "action", "") != expected:
            raise CaseReviewError("lawyer_review_ungranted")
        if str(getattr(decision, "case_id", "") or "") != case_id:
            raise CaseReviewError("cross_case_id")
        query_case = str(request.query_params.get("case_id") or "")
        if query_case and query_case != case_id:
            raise CaseReviewError("cross_case_id")
        resolver = _BOUND_HANDLERS.get()
        if resolver is None:
            raise CaseReviewError("lawyer_review_unavailable")
        try:
            mediator, _workspace, _root = resolver()
            authority = current_workspace_case_authority()
        except Exception as exc:
            raise CaseReviewError("lawyer_review_unavailable") from exc
        if authority is None or getattr(authority, "case_id", None) != case_id:
            raise CaseReviewError("lawyer_review_ungranted")
        revision = getattr(decision, "revision", None)
        if type(revision) is not int:
            raise CaseReviewError("lawyer_review_field")
        return mediator, decision, revision

    @app.get(LAWYER_WORKSPACE_ROUTE)
    async def read_lawyer_workspace(case_id: str, request: Request):
        try:
            mediator, _decision, revision = _authorized(request, case_id, write=False)
            projection = project_lawyer_reviews(_case_file(mediator), case_revision=revision)
            projection["case_id"] = case_id
            page = render_lawyer_workspace(projection)
        except CaseReviewError as exc:
            return _fail(exc)
        return HTMLResponse(page)

    @app.get(LAWYER_REVIEW_ROUTE)
    async def read_lawyer_reviews(case_id: str, request: Request):
        try:
            mediator, _decision, revision = _authorized(request, case_id, write=False)
            payload = project_lawyer_reviews(_case_file(mediator), case_revision=revision)
        except CaseReviewError as exc:
            return _fail(exc)
        payload["case_id"] = case_id
        return JSONResponse(payload)

    @app.post(LAWYER_REVIEW_ROUTE)
    async def write_lawyer_review(case_id: str, request: Request):
        try:
            mediator, decision, revision = _authorized(request, case_id, write=True)
            body = await request.json()
            if not isinstance(body, dict):
                raise CaseReviewError("lawyer_review_field")
            payload = submit_lawyer_review(
                mediator,
                body,
                actor_principal_id=str(getattr(decision, "actor_principal_id", "") or ""),
                canonical_owner_principal_id=str(getattr(decision, "canonical_owner_principal_id", "") or ""),
                case_revision=revision,
                membership=str(getattr(decision, "membership", "") or ""),
            )
        except CaseReviewError as exc:
            return _fail(exc)
        payload["case_id"] = case_id
        payload["promotes_changed_law"] = False
        payload["promotes_changed_facts"] = False
        return JSONResponse(payload)
