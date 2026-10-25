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
REVIEW_TRANSITION_TASK_ID = "CIMP-GUI-47"
LAWYER_REVIEW_ROUTE = "/api/legal-analysis/{case_id}/lawyer-reviews"
LAWYER_WORKSPACE_ROUTE = "/api/legal-analysis/{case_id}/lawyer-workspace"
REVIEW_ITEMS_ROUTE = "/api/legal-analysis/{case_id}/review-items"
REVIEW_TRANSITIONS_ROUTE = "/api/legal-analysis/{case_id}/review-transitions"
_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "lawyer_workspace.html"
_BODY_CAP = 65536
_HUMAN = "human_legal_review"
_MODEL = "model_suggestion"
_MACHINE = "machine_proof"
_KINDS = (_HUMAN, _MODEL, _MACHINE)
_DECISIONS = {"approved", "rejected", "withheld"}
_REVIEW_ITEM_TYPES = {"review_task", "review_comment", "review_proposal"}
_REVIEW_CREATE = {
    "create_task": "review_task",
    "create_comment": "review_comment",
    "create_proposal": "review_proposal",
}
_REVIEW_TARGETS = {"fact", "answer", "legal_admission", "draft_revision"}
_REVIEW_STATE_KEYS = ("facts", "answers", "legal_admissions", "draft_revisions")
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
    if code in {"stale_revision", "stale_approval", "replay_mismatch", "stale_review_revision", "stale_target_revision"}:
        return 409
    if code in {"review_field", "review_bounds"}:
        return 422
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
    projected["accepted_for_bound_revision"] = bool(current and human_approval and record.get("operation") == "review" and live.get("source_bound", True))
    projected["promoted_for_current_revisions"] = bool(current and promoted and live.get("source_bound", True))
    projected["promotes_changed_law"] = False
    projected["promotes_changed_facts"] = False
    projected["governing_legal_authority"] = False
    projected["legal_sufficiency"] = False
    projected["admitted_law"] = False
    projected["admitted_facts"] = False
    return projected


def project_lawyer_reviews(case_file: Mapping[str, Any], *, case_revision: int, live_context=None) -> Dict[str, Any]:
    live = dict(live_context) if live_context is not None else live_revisions(case_file, case_revision=case_revision)
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
        if (key=='case_revision' and type(value) is not int) or (key!='case_revision' and not isinstance(value,str)):
            raise CaseReviewError('lawyer_review_field')
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


def submit_review_record(case_file: MutableMapping[str, Any], body: Mapping[str, Any], *, actor_principal_id: str,
                         canonical_owner_principal_id: str, case_revision: int, membership: str, live_context=None) -> Dict[str, Any]:
    """Append one attributed review record. Stale revisions are not stored as current."""

    if membership != "assigned-lawyer":
        raise CaseReviewError("lawyer_assignment_required")
    if not isinstance(body, Mapping) or len(json.dumps(body, default=str)) > _BODY_CAP:
        raise CaseReviewError("lawyer_review_bounds")
    operation = _text(body.get("operation"), limit=40, required=True)
    if operation not in {"propose", "review", "promote", "record_model_suggestion", "record_machine_proof"}:
        raise CaseReviewError("lawyer_review_field")
    live = dict(live_context) if live_context is not None else live_revisions(case_file, case_revision=case_revision)
    _require_live(body, live)
    stored = case_file.get("lawyer_review_ledger")
    ledger = stored if isinstance(stored, list) else []
    request_id = _text(body.get("request_id"), limit=80, required=True)
    for existing in ledger:
        if isinstance(existing, dict) and existing.get("request_id") == request_id:
            if existing.get("operation") != operation:
                raise CaseReviewError("replay_mismatch")
            projected = project_lawyer_reviews(case_file, case_revision=case_revision, live_context=live)
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
    projected = project_lawyer_reviews(case_file, case_revision=case_revision, live_context=live)
    projected["record"] = _annotate(record, live)
    projected["operation"] = operation
    return projected


def _review_items(case_file: MutableMapping[str, Any]) -> list:
    stored = case_file.get("collaborative_review_items")
    if not isinstance(stored, list):
        stored = []
        case_file["collaborative_review_items"] = stored
    return stored


def _review_service(mediator: Any):
    service = getattr(mediator, "workflow_service", None)
    if service is not None and hasattr(service, "apply_authorized_review_transition"):
        return service
    from mediator.workflow_service import WorkflowActionService

    service = WorkflowActionService(mediator)
    mediator.workflow_service = service
    return service


def _state_view(case_file: Mapping[str, Any]) -> Dict[str, Any]:
    state = case_file.get("review_case_state")
    if not isinstance(state, dict):
        state = {}
    return {key: state.get(key) if isinstance(state.get(key), dict) else {} for key in _REVIEW_STATE_KEYS}


def project_collaborative_reviews(case_file: Mapping[str, Any]) -> Dict[str, Any]:
    """Project typed review items separately from case-state targets."""

    items = [dict(item) for item in case_file.get("collaborative_review_items") or [] if isinstance(item, dict)]
    state = case_file.get("review_case_state") if isinstance(case_file.get("review_case_state"), dict) else {}
    support = [dict(item) for item in state.get("downstream_support") or [] if isinstance(item, dict)]
    grouped = {kind: [item for item in items if item.get("item_type") == kind] for kind in sorted(_REVIEW_ITEM_TYPES)}
    return {
        "task_id": REVIEW_TRANSITION_TASK_ID,
        "operation": "project_collaborative_reviews",
        "status": "visible" if items or state else "empty",
        "item_types": sorted(_REVIEW_ITEM_TYPES),
        "items": items,
        "review_tasks": grouped["review_task"],
        "review_comments": grouped["review_comment"],
        "review_proposals": grouped["review_proposal"],
        "dissent": [item for item in items if item.get("operation") == "dissent"],
        "acceptance_history": list(state.get("acceptance_history") or []),
        "review_revision": int(state.get("review_revision") or 0) if type(state.get("review_revision")) is int else 0,
        "facts": _state_view(case_file)["facts"],
        "answers": _state_view(case_file)["answers"],
        "legal_admissions": _state_view(case_file)["legal_admissions"],
        "draft_revisions": _state_view(case_file)["draft_revisions"],
        "downstream_support": support,
        "comments_update_case_state": False,
        "tasks_update_case_state": False,
        "unaccepted_proposals_update_case_state": False,
        "governing_legal_authority": False,
        "legal_sufficiency": False,
        "limitations": [
            "Review tasks, comments, and proposals have explicit item types.",
            "Only an authorized accepted review_proposal updates facts, answers, legal admissions, or draft revisions.",
            "Concurrent acceptance uses the expected review revision and expected target revision.",
            "Dissent and prior target history are preserved.",
            "Downstream support for a replaced revision is invalidated and retained.",
            "Acceptance is not governing law or legal sufficiency.",
            "WebSocket and SSE transports are not supported.",
        ],
    }


def _snapshot_targets(case_file: Mapping[str, Any]) -> str:
    return json.dumps(_state_view(case_file), sort_keys=True, default=str)


def submit_collaborative_record(case_file: MutableMapping[str, Any], body: Mapping[str, Any], *, actor_principal_id: str,
                                canonical_owner_principal_id: str, case_id: str, membership: str,
                                authorized: bool, workflow_owner=None) -> Dict[str, Any]:
    """Record a typed review item. This path does not change case state."""

    if membership not in {"assigned-lawyer", "owner"}:
        raise CaseReviewError("lawyer_assignment_required")
    if not isinstance(body, Mapping) or len(json.dumps(body, default=str)) > _BODY_CAP:
        raise CaseReviewError("review_bounds")
    operation = _text(body.get("operation"), limit=40, required=True)
    if operation not in set(_REVIEW_CREATE) | {"dissent", "bind_support"}:
        raise CaseReviewError("review_field")
    before = _snapshot_targets(case_file)
    items = _review_items(case_file)
    request_id = _text(body.get("request_id"), limit=80, required=True)
    for existing in items:
        if isinstance(existing, dict) and existing.get("request_id") == request_id:
            if existing.get("operation") != operation:
                raise CaseReviewError("replay_mismatch")
            projected = project_collaborative_reviews(case_file)
            projected["record"] = dict(existing)
            projected["replayed"] = True
            return projected
    if actor_principal_id == canonical_owner_principal_id:
        raise CaseReviewError("actor_is_not_canonical_owner")
    record: Dict[str, Any] = {
        "task_id": REVIEW_TRANSITION_TASK_ID,
        "request_id": request_id,
        "operation": operation,
        "actor_principal_id": actor_principal_id,
        "canonical_owner_principal_id": canonical_owner_principal_id,
        "actor_is_canonical_owner": False,
        "membership": membership,
        "case_id": case_id,
        "updates_case_state": False,
    }
    if operation in _REVIEW_CREATE:
        item_type = _REVIEW_CREATE[operation]
        record["item_type"] = item_type
        record["item_id"] = _digest("review-item", request_id + "\n" + item_type + "\n" + actor_principal_id)
        record["body"] = _text(body.get("body"), limit=2000, required=True)
        if item_type == "review_proposal":
            target_kind = _text(body.get("target_kind"), limit=40, required=True)
            if target_kind not in _REVIEW_TARGETS:
                raise CaseReviewError("review_field")
            record["target_kind"] = target_kind
            record["target_id"] = _text(body.get("target_id"), limit=80, required=True)
            record["proposed_text"] = _text(body.get("proposed_text"), limit=2000, required=True)
            record["status"] = "proposed"
        elif item_type == "review_task":
            record["title"] = _text(body.get("title"), limit=200, required=True)
            record["status"] = "open"
        else:
            record["proposal_id"] = _text(body.get("proposal_id"), limit=80, required=False)
            record["status"] = "comment"
    elif operation == "dissent":
        proposal_id = _text(body.get("proposal_id"), limit=80, required=True)
        proposal = next((item for item in items if item.get("item_id") == proposal_id and item.get("item_type") == "review_proposal"), None)
        if proposal is None:
            raise CaseReviewError("proposal_required")
        record["item_type"] = "review_comment"
        record["item_id"] = _digest("review-dissent", request_id + "\n" + proposal_id)
        record["proposal_id"] = proposal_id
        record["body"] = _text(body.get("body"), limit=2000, required=True)
        record["dissent"] = True
        record["status"] = "dissent"
    else:
        if workflow_owner is None:
            raise CaseReviewError("review_transition_owner_unavailable")
        service = workflow_owner
        receipt = service.register_review_downstream_support(
            case_id=case_id,
            support_id=_text(body.get("support_id"), limit=80, required=True),
            depends_on_kind=_text(body.get("depends_on_kind"), limit=40, required=True),
            depends_on_id=_text(body.get("depends_on_id"), limit=80, required=True),
            depends_on_revision=body.get("depends_on_revision"),
            request_id=request_id,
        )
        if receipt.get("status") != "bound":
            code = (receipt.get("error") or {}).get("code") or "review_field"
            raise CaseReviewError(str(code))
        record["item_type"] = "downstream_support_binding"
        record["item_id"] = _digest("review-support", request_id)
        record["support_id"] = body.get("support_id")
        record["status"] = "support_bound"
        record["body"] = "Downstream support is bound to the current target revision."
    if _snapshot_targets(case_file) != before:
        raise CaseReviewError("review_state_mutated")
    items.append(record)
    projected = project_collaborative_reviews(case_file)
    projected["record"] = dict(record)
    projected["replayed"] = False
    return projected



def submit_collaborative_review(mediator: Any, body: Mapping[str, Any], **scope) -> Dict[str, Any]:
    return submit_collaborative_record(_case_file(mediator), body,
        workflow_owner=_review_service(mediator) if body.get('operation') == 'bind_support' else None, **scope)


def accept_review_transition(mediator: Any, body: Mapping[str, Any], *, actor_principal_id: str,
                             canonical_owner_principal_id: str, case_id: str, membership: str,
                             authorized: bool) -> Dict[str, Any]:
    """Accept one proposal into case state when the caller and revisions match."""

    if not authorized or membership not in {"assigned-lawyer", "owner"}:
        raise CaseReviewError("actor_not_permitted")
    if not isinstance(body, Mapping) or len(json.dumps(body, default=str)) > _BODY_CAP:
        raise CaseReviewError("review_bounds")
    if _text(body.get("operation"), limit=40, required=True) != "accept":
        raise CaseReviewError("not_an_accepted_transition")
    case_file = _case_file(mediator)
    items = _review_items(case_file)
    request_id = _text(body.get("request_id"), limit=80, required=True)
    proposal_id = _text(body.get("proposal_id"), limit=80, required=True)
    proposal = next((item for item in items if item.get("item_id") == proposal_id), None)
    if proposal is None:
        raise CaseReviewError("proposal_required")
    if proposal.get("item_type") != "review_proposal":
        raise CaseReviewError("not_an_accepted_transition")
    replacement = _text(body.get("replacement"), limit=2000, required=True)
    if replacement != str(proposal.get("proposed_text") or ""):
        raise CaseReviewError("proposal_mismatch")
    target_kind = _text(body.get("target_kind"), limit=40, required=True)
    target_id = _text(body.get("target_id"), limit=80, required=True)
    if target_kind != proposal.get("target_kind") or target_id != proposal.get("target_id"):
        raise CaseReviewError("proposal_mismatch")
    for existing in items:
        if existing.get("request_id") == request_id and existing.get("operation") == "accept":
            projected = project_collaborative_reviews(case_file)
            projected["record"] = dict(existing)
            projected["replayed"] = True
            projected["applied"] = False
            return projected
    dissent_ids = [item.get("item_id") for item in items if item.get("dissent") is True and item.get("proposal_id") == proposal_id]
    service = _review_service(mediator)
    receipt = service.apply_authorized_review_transition(
        case_id=case_id,
        actor_principal_id=actor_principal_id,
        canonical_owner_principal_id=canonical_owner_principal_id,
        authorized=True,
        item_type="review_proposal",
        item_id=proposal_id,
        target_kind=target_kind,
        target_id=target_id,
        replacement=replacement,
        expected_review_revision=body.get("expected_review_revision"),
        expected_target_revision=body.get("expected_target_revision"),
        request_id=request_id,
    )
    if receipt.get("status") != "applied":
        code = (receipt.get("error") or {}).get("code") or "review_field"
        raise CaseReviewError(str(code))
    record = {
        "task_id": REVIEW_TRANSITION_TASK_ID,
        "request_id": request_id,
        "operation": "accept",
        "item_type": "review_proposal",
        "item_id": _digest("review-accept", request_id + "\n" + proposal_id),
        "proposal_id": proposal_id,
        "actor_principal_id": actor_principal_id,
        "canonical_owner_principal_id": canonical_owner_principal_id,
        "actor_is_canonical_owner": False,
        "membership": membership,
        "case_id": case_id,
        "target_kind": target_kind,
        "target_id": target_id,
        "target_revision": receipt["acceptance"]["target_revision"],
        "review_revision": receipt["review_revision"],
        "preserved_dissent_ids": dissent_ids,
        "invalidated_support_ids": list(receipt.get("invalidated_support_ids") or []),
        "updates_case_state": True,
        "status": "accepted",
        "governing_legal_authority": False,
        "legal_sufficiency": False,
    }
    items.append(record)
    projected = project_collaborative_reviews(case_file)
    projected["record"] = record
    projected["applied"] = True
    projected["replayed"] = False
    for dissent_id in dissent_ids:
        if not any(item.get("item_id") == dissent_id for item in projected["dissent"]):
            raise CaseReviewError("dissent_lost")
    return projected

def submit_lawyer_review(mediator: Any, body: Mapping[str, Any], **scope) -> Dict[str, Any]:
    """Legacy pure reported-record helper; mounted routes use the encrypted owner."""
    return submit_review_record(_case_file(mediator), body, **scope)


def render_lawyer_workspace(projection: Mapping[str, Any]) -> str:
    """Fill the lawyer workspace template. The page does not treat stale rows as current."""

    template = _TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(projection, sort_keys=True)
    safe = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    if "__LAWYER_REVIEW_JSON__" not in template:
        raise CaseReviewError("lawyer_review_unavailable")
    return template.replace("__LAWYER_REVIEW_JSON__", safe)


def mount_lawyer_review_routes(app: Any) -> None:
    """Only the explicitly configured encrypted review owner serves this prefix."""
    from fastapi.responses import HTMLResponse, JSONResponse
    from starlette.concurrency import run_in_threadpool
    from applications.case_review_store import CaseReviewService, CaseReviewStoreError
    from applications.workspace_case_authority import current_workspace_case_authority

    def context(request, case_id):
        service = getattr(request.app.state, 'case_reviews', None)
        decision = getattr(request.state, 'case_authorization', None)
        authority = current_workspace_case_authority()
        if type(service) is not CaseReviewService:
            raise CaseReviewStoreError('review_unavailable')
        if decision is None or decision.case_id != case_id or authority is None:
            raise CaseReviewStoreError('lawyer_review_ungranted')
        return service, decision, authority

    def failed(exc):
        code = str(getattr(exc, 'code', '') or 'review_unavailable')
        allowed = {'lawyer_assignment_required','lawyer_review_ungranted','cross_case_id','review_key_locked',
            'review_source_changed','review_source_unbound','review_unavailable','review_integrity','review_key_grant_required',
            'review_membership_required','lawyer_review_field','lawyer_review_bounds','stale_revision','stale_approval',
            'replay_mismatch','proof_producer_unavailable','owner_share_required','recipient_review_grant_required',
            'proposal_required','approval_required','model_cannot_approve','machine_proof_cannot_approve',
            'review_transition_owner_unavailable','review_field','review_bounds','revision_conflict',
            'review_target_capability_unavailable','proposal_already_accepted','unlock_needed'}
        if code not in allowed:
            code = 'lawyer_review_ungranted' if code in {'grant_revoked','key_grant_rejected','late_result_after_cutoff',
                'membership_removed','membership_expired','workspace_authorization_denied'} else 'review_unavailable'
        status = 409 if code in {'stale_revision','stale_approval','replay_mismatch','review_source_changed','revision_conflict','proposal_already_accepted'} else 422 if code in {
            'lawyer_review_field','lawyer_review_bounds','review_field','review_bounds'} else 503 if code in {'review_unavailable','review_key_locked',
            'review_source_unbound','proof_producer_unavailable','recipient_review_grant_required','review_transition_owner_unavailable',
            'review_target_capability_unavailable','unlock_needed'} else 403
        return JSONResponse({'task_id':TASK_ID,'error':code,'status':'unavailable' if status==503 else 'refused',
            'human_legal_reviews':[],'model_suggestions':[],'machine_proofs':[],'proof':False,
            'governing_legal_authority':False,'legal_sufficiency':False,'admitted_law':False,
            'promotes_changed_law':False,'promotes_changed_facts':False,
            'message':'Complaint changed; owner must share latest version.' if code=='review_source_changed' else 'Review access could not be verified.'},status_code=status)

    async def projection(request,case_id):
        service,decision,authority=context(request,case_id)
        value=await run_in_threadpool(service.read,decision.actor_principal_id,case_id=case_id,authority=authority)
        value.update(actor_principal_id=decision.actor_principal_id,
            case_context={'tenant_id':decision.tenant_id,'case_id':case_id,'resource_id':decision.resource_id,
                'revision':decision.revision,'membership_revision':decision.membership_revision},
            session_generation=request.state.browser_principal.generation)
        return value

    @app.get(LAWYER_WORKSPACE_ROUTE)
    async def read_lawyer_workspace(case_id: str, request: Request):
        try:
            return HTMLResponse(render_lawyer_workspace(await projection(request,case_id)))
        except Exception as exc:
            return failed(exc)

    @app.get(LAWYER_REVIEW_ROUTE)
    async def read_lawyer_reviews(case_id: str, request: Request):
        try:
            return JSONResponse(await projection(request,case_id))
        except Exception as exc:
            return failed(exc)

    @app.post(LAWYER_REVIEW_ROUTE)
    async def write_lawyer_review(case_id: str, request: Request):
        try:
            service,decision,authority=context(request,case_id)
            value=await run_in_threadpool(service.write,decision.actor_principal_id,case_id=case_id,
                request=await request.json(),authority=authority)
            return JSONResponse(value)
        except Exception as exc:
            return failed(exc)

    @app.get(LAWYER_REVIEW_ROUTE+'/sharing')
    async def read_sharing(case_id: str, request: Request):
        try:
            service,decision,authority=context(request,case_id)
            return JSONResponse(await run_in_threadpool(service.sharing_status,decision.actor_principal_id,
                case_id=case_id,authority=authority))
        except Exception as exc:
            return failed(exc)

    @app.post(LAWYER_REVIEW_ROUTE+'/share')
    async def share_review_source(case_id: str, request: Request):
        try:
            service,decision,authority=context(request,case_id)
            return JSONResponse(await run_in_threadpool(service.share_source,decision.actor_principal_id,
                case_id=case_id,request=await request.json(),authority=authority))
        except Exception as exc:
            return failed(exc)

    @app.get(REVIEW_ITEMS_ROUTE)
    async def read_review_items(case_id: str, request: Request):
        try:
            service,decision,authority=context(request,case_id)
            value=await run_in_threadpool(service.read,decision.actor_principal_id,case_id=case_id,authority=authority)
            return JSONResponse({**value['collaborative_reviews'],'case_id':case_id,'review_revision':value['review_revision'],
                'private_revision':value['private_revision'],'live_revisions':value['live_revisions'],'read_only':True})
        except Exception as exc:return failed(exc)

    @app.post(REVIEW_ITEMS_ROUTE)
    async def write_review_items(case_id: str, request: Request):
        try:
            service,decision,authority=context(request,case_id)
            return JSONResponse(await run_in_threadpool(service.write_item,decision.actor_principal_id,case_id=case_id,
                request=await request.json(),authority=authority))
        except Exception as exc:return failed(exc)

    @app.post(REVIEW_TRANSITIONS_ROUTE)
    async def write_review_transition(case_id: str, request: Request):
        try:
            service,decision,authority=context(request,case_id)
            return JSONResponse(await run_in_threadpool(service.accept_owner_transition,decision.actor_principal_id,
                case_id=case_id,request=await request.json(),authority=authority))
        except Exception as exc:return failed(exc)
