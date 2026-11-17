"""Diagnostic receipts, support views, and dependency-lane publication.

These helpers keep the bodies that previously lived on the denoiser owner.
The owner re-exports the public names.
"""

from typing import Any, Dict, List, Optional

from .denoiser import (
    _CONDITION_COPY,
    _FIELD_CHAR_BUDGET,
    _PRIVATE_DIAGNOSTIC_KEYS,
    _SUPPORT_STATE_NAMES,
    _SUPPORT_STATE_TOKENS,
    _WHY_DISPLAY_CHAR_BUDGET,
)

INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"


def _clip_public(value: Any, limit: int = _FIELD_CHAR_BUDGET) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _state_token(value: Any) -> str:
    token = str(value or "").strip().lower().replace(" ", "_")
    if token in _SUPPORT_STATE_TOKENS:
        return token
    return "recorded" if token else "unknown"


def _mapping(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _factual_target_view(inquiry: Dict[str, Any]) -> Dict[str, str]:
    raw = _mapping(inquiry.get("factual_target"))
    unresolved = _mapping(inquiry.get("unresolved_target"))
    kind = str(raw.get("kind") or unresolved.get("target_kind") or inquiry.get("target_kind") or inquiry.get("gap_family") or "")
    target_id = str(raw.get("target_id") or "").strip()
    label = str(raw.get("label") or raw.get("name") or "").strip()
    factual_kinds = {"factual", "factual_uncertainty", "timeline", "clarification"}
    if not target_id and kind.strip().lower() in factual_kinds:
        target_id = str(unresolved.get("target_id") or inquiry.get("target_id") or "").strip()
    if not label and kind.strip().lower() in factual_kinds:
        label = str(unresolved.get("label") or unresolved.get("name") or "").strip()
    return {
        "target_id": _clip_public(target_id) or "unknown",
        "label": _clip_public(label) or "unknown",
        "kind": "factual",
    }


def _law_requirement_view(inquiry: Dict[str, Any], factual: Dict[str, str]) -> Dict[str, str]:
    raw = _mapping(inquiry.get("law_derived_requirement") or inquiry.get("legal_requirement"))
    requirement_id = str(raw.get("requirement_id") or raw.get("element_id") or "").strip()
    label = str(raw.get("label") or raw.get("name") or raw.get("element") or "").strip()
    law_derived = raw.get("law_derived")
    if law_derived is None:
        law_derived = bool(requirement_id or label) or str(inquiry.get("gap_family") or "") == "legal_element_support"
    if not requirement_id and str(inquiry.get("gap_family") or "") == "legal_element_support":
        requirement_id = str(inquiry.get("requirement_id") or "").strip()
    # A factual target id is not a law-derived requirement, even when it is the only id present.
    if requirement_id and requirement_id == factual.get("target_id") and factual.get("target_id") != "unknown":
        if not raw:
            requirement_id = ""
    if label and label == factual.get("label") and factual.get("label") != "unknown" and not raw:
        label = ""
    return {
        "requirement_id": _clip_public(requirement_id) or "unknown",
        "label": _clip_public(label) or "unknown",
        "law_derived": "true" if law_derived and (requirement_id or label) else "false",
    }


def _admitted_authorities(inquiry: Dict[str, Any]) -> List[Dict[str, str]]:
    raw = inquiry.get("admitted_authorities")
    if not isinstance(raw, list):
        raw = inquiry.get("authority_references")
    if not isinstance(raw, list):
        single = _mapping(inquiry.get("admitted_authority"))
        raw = [single] if single else []
    admitted: List[Dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or item.get("admission") or "").strip().lower()
        if item.get("admitted") is False or status in {"rejected", "unknown", "candidate", "unavailable"}:
            continue
        if item.get("admitted") is not True and status not in {"admitted", "admitted_authority"}:
            continue
        citation = _clip_public(item.get("citation") or item.get("cite") or "")
        version = _clip_public(item.get("version") or item.get("edition") or "")
        span = _clip_public(item.get("span") or item.get("span_id") or item.get("span_ref") or "")
        if not (citation or version or span):
            continue
        admitted.append({
            "citation": citation or "unknown",
            "version": version or "unknown",
            "span": span or "unknown",
        })
        if len(admitted) >= 4:
            break
    return admitted


def _support_states(inquiry: Dict[str, Any]) -> Dict[str, str]:
    raw = _mapping(inquiry.get("support_states"))
    states = {name: _state_token(raw.get(name, inquiry.get(name))) for name in _SUPPORT_STATE_NAMES}
    score = inquiry.get("retrieval_score", inquiry.get("relevance_score"))
    raw_proof = raw.get("proof", inquiry.get("proof"))
    raw_proof_text = str(raw_proof).strip() if raw_proof is not None else ""
    score_text = str(score).strip() if score is not None else ""
    # A retrieval score never fills proof, including when a caller copies the score into proof.
    if not raw_proof_text or (score_text and raw_proof_text == score_text):
        states["proof"] = "unknown"
    return states


def _support_conditions(inquiry: Dict[str, Any], authorities: List[Dict[str, str]]) -> List[Dict[str, str]]:
    authority_status = str(inquiry.get("authority_status") or "").strip().lower()
    source_status = str(inquiry.get("source_status") or inquiry.get("legal_source_status") or "").strip().lower()
    definition_status = str(inquiry.get("definition_status") or "").strip().lower()
    review_status = str(inquiry.get("review_status") or "").strip().lower()
    reasons = {str(item).strip().lower() for item in (inquiry.get("unknown_reasons") or [])}
    family = str(inquiry.get("gap_family") or "").strip().lower()
    flags = {
        "unknown_authority": (not authorities) or authority_status in {"unknown", "missing"},
        "source_outage": source_status in {"outage", "unavailable", "source_outage"} or "source_outage" in reasons,
        "contradiction": family == "contradiction" or bool(inquiry.get("contradiction")) or "contradiction" in reasons,
        "missing_definition": definition_status in {"missing", "unknown"} or bool(inquiry.get("missing_definition")) or "missing_definition" in reasons,
        "missing_review": review_status in {"missing", "needs_review"} or bool(inquiry.get("missing_review")) or "missing_review" in reasons,
    }
    # Unknown authority is the standing case. Other conditions appear only when the inquiry says so.
    if authority_status in {"admitted", "known"} and authorities:
        flags["unknown_authority"] = False
    conditions: List[Dict[str, str]] = []
    for kind, enabled in flags.items():
        if not enabled:
            continue
        message, action = _CONDITION_COPY[kind]
        conditions.append({"kind": kind, "message": message, "next_action": action})
    return conditions


def question_support_view(inquiry: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Separate factual, law-derived, authority, and support facts for /why.

    Retrieval rank stays a retrieval fact. It is not proof, applicability, or admission.
    """
    record = inquiry if isinstance(inquiry, dict) else {}
    factual = _factual_target_view(record)
    requirement = _law_requirement_view(record, factual)
    authorities = _admitted_authorities(record)
    states = _support_states(record)
    conditions = _support_conditions(record, authorities)
    score = record.get("retrieval_score", record.get("relevance_score"))
    score_text = "none"
    if score is not None and str(score).strip():
        score_text = _clip_public(score, 32)
    return {
        "factual_target": factual,
        "law_derived_requirement": requirement,
        "admitted_authorities": authorities,
        "authority_status": "admitted" if authorities else "unknown",
        "support_states": states,
        "retrieval_score": score_text,
        "retrieval_score_is_proof": False,
        "conditions": conditions,
        "legal_sufficiency": False,
        "proof_established": states.get("proof") == "proved",
    }


def _support_display_lines(support: Dict[str, Any]) -> List[str]:
    factual = support["factual_target"]
    requirement = support["law_derived_requirement"]
    lines = [
        f"Factual target: {factual['label']} [{factual['target_id']}]",
        (
            "Law-derived requirement: "
            f"{requirement['label']} [{requirement['requirement_id']}] "
            f"law_derived={requirement['law_derived']}"
        ),
    ]
    authorities = support["admitted_authorities"]
    if authorities:
        for item in authorities:
            lines.append(
                "Admitted authority: "
                f"citation={item['citation']}; version={item['version']}; span={item['span']}"
            )
    else:
        lines.append("Admitted authority: unknown")
    state_text = "; ".join(f"{name}={support['support_states'][name]}" for name in _SUPPORT_STATE_NAMES)
    lines.append(f"Support states: {state_text}")
    lines.append(
        f"Retrieval score: {support['retrieval_score']}. A retrieval score is not proof, corroboration, applicability, or admission."
    )
    for condition in support["conditions"]:
        lines.append(f"Condition {condition['kind']}: {condition['message']}")
        lines.append(f"Next action: {condition['next_action']}")
    rendered: List[str] = []
    budget = _WHY_DISPLAY_CHAR_BUDGET
    for line in lines:
        safe = line.encode("ascii", "replace").decode("ascii")
        if budget <= 0:
            rendered.append("Further support lines omitted to keep this explanation bounded.")
            break
        if len(safe) > budget:
            safe = safe[: max(0, budget - 3)] + "..."
        rendered.append(safe)
        budget -= len(safe) + 1
    return rendered


def public_why_diagnostic_receipt(why: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Codes and references only. Question text and narrative stay out of the receipt."""
    payload = why if isinstance(why, dict) else {}
    support = payload.get("question_support") if isinstance(payload.get("question_support"), dict) else {}
    factual = _mapping(support.get("factual_target"))
    requirement = _mapping(support.get("law_derived_requirement"))
    states = _mapping(support.get("support_states"))
    conditions = [item for item in (support.get("conditions") or []) if isinstance(item, dict)]
    authorities = [item for item in (support.get("admitted_authorities") or []) if isinstance(item, dict)]
    return {
        "schema": "why-diagnostic-receipt-v1",
        "command": "/why",
        "objective_id": _clip_public(payload.get("objective_id") or "unknown", 80) or "unknown",
        "target_id": _clip_public(payload.get("target_id") or "unknown", 80) or "unknown",
        "factual_target_id": _clip_public(factual.get("target_id") or "unknown", 80),
        "law_requirement_id": _clip_public(requirement.get("requirement_id") or "unknown", 80),
        "authority_status": "admitted" if authorities else "unknown",
        "authority_count": len(authorities),
        "authority_citations": [_clip_public(item.get("citation") or "unknown", 80) for item in authorities],
        "support_states": {name: _state_token(states.get(name)) for name in _SUPPORT_STATE_NAMES},
        "retrieval_score_is_proof": False,
        "condition_kinds": [str(item.get("kind") or "") for item in conditions],
        "next_actions": [str(item.get("next_action") or "") for item in conditions],
        "legal_sufficiency": False,
        "contains_private_content": False,
        "awaiting_user": True,
        "worker_stalled": False,
    }


def redact_diagnostic_value(value: Any) -> Any:
    """Drop private complaint text from a diagnostic receipt before it is shown."""
    if isinstance(value, dict):
        redacted: Dict[str, Any] = {}
        for key, item in value.items():
            if str(key).strip().lower() in _PRIVATE_DIAGNOSTIC_KEYS:
                continue
            redacted[str(key)] = redact_diagnostic_value(item)
        redacted.setdefault("contains_private_content", False)
        return redacted
    if isinstance(value, list):
        return [redact_diagnostic_value(item) for item in value[:20]]
    if isinstance(value, str):
        if len(value) > 180:
            return "[redacted]"
        return value
    return value


def format_terminal_why(inquiry: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Render a /why explanation a person can read without seeing ranking internals."""
    if not isinstance(inquiry, dict) or not (
        str(inquiry.get("question") or "").strip() or str(inquiry.get("why_it_matters") or "").strip()
    ):
        support = question_support_view({})
        display = (
            "There is no current question to explain. "
            "The interview is waiting for a selected gap, and this is not a stalled worker.\n"
            + "\n".join(_support_display_lines(support))
        )
        payload = {
            "command": "/why",
            "display": display,
            "stored_as_answer": False,
            "awaiting_user": True,
            "worker_stalled": False,
            "inquiry": None,
            "legal_sufficiency": False,
            "question_support": support,
        }
        payload["diagnostic_receipt"] = public_why_diagnostic_receipt(payload)
        return payload
    why = str(inquiry.get("why_it_matters") or inquiry.get("question_reason") or "").strip()
    if not why:
        why = "This question asks for information that is still missing from the complaint record."
    question = str(inquiry.get("question") or "").strip()
    objective_id = str(inquiry.get("objective_id") or "")
    target_id = str(inquiry.get("target_id") or inquiry.get("inquiry_id") or "")
    answer_contract = inquiry.get("expected_answer_contract") if isinstance(inquiry.get("expected_answer_contract"), dict) else {}
    update_contract = inquiry.get("expected_update_contract") if isinstance(inquiry.get("expected_update_contract"), dict) else {}
    expected = str(
        answer_contract.get("expected_information")
        or inquiry.get("expected_information")
        or "facts, dates, people, or documents you observed"
    ).strip()
    update_kind = str(update_contract.get("update_kind") or "record the answer against this target").replace("_", " ")
    support = question_support_view(inquiry)
    support_lines = "\n".join(_support_display_lines(support))
    display = (
        f"Why this question: {why}\n"
        f"Question: {question}\n"
        f"Objective id: {objective_id}\n"
        f"Target id: {target_id}\n"
        f"Expected answer: {expected}.\n"
        f"Expected update: {update_kind} for this target. "
        "An unknown, refused, or skipped answer is recorded as that response and does not satisfy the underlying legal requirement.\n"
        f"{support_lines}"
    )
    if len(display) > _WHY_DISPLAY_CHAR_BUDGET:
        display = display[: _WHY_DISPLAY_CHAR_BUDGET - 3] + "..."
    payload = {
        "command": "/why",
        "display": display,
        "stored_as_answer": False,
        "awaiting_user": True,
        "worker_stalled": False,
        "objective_id": objective_id,
        "target_id": target_id,
        "why_it_matters": why,
        "expected_answer_contract": answer_contract,
        "expected_update_contract": update_contract,
        "question_support": support,
        "legal_sufficiency": False,
    }
    payload["diagnostic_receipt"] = public_why_diagnostic_receipt(payload)
    return payload

def project_stopping_policy(
    stop: Optional[Dict[str, Any]] = None,
    *,
    paused: bool = False,
    needs_review: bool = False,
) -> Dict[str, Any]:
    """Public stopping outcome. Saturation never claims legal sufficiency or complete proof."""
    payload = stop if isinstance(stop, dict) else {}
    summary = payload.get("unresolved_issue_summary") if isinstance(payload.get("unresolved_issue_summary"), dict) else {}
    items = [item for item in (summary.get("items") or []) if isinstance(item, dict)]
    shortcuts = [str(item) for item in (summary.get("rejected_shortcuts") or [])]
    state = str(payload.get("state") or "").strip()
    try:
        open_count = int(summary.get("open_answerable_count") or 0)
    except (TypeError, ValueError):
        open_count = 0
    bound_hit = bool(
        {"repeat_attempt_bound", "no_information_bound", "model_retry_bound"} & set(shortcuts)
    )
    if paused or state == "paused":
        outcome = "paused"
    elif state in {"provider_unavailable", "blocked_provider"}:
        outcome = "blocked_provider"
    elif state in {"limit_reached", "no_progress", "cancelled"} or bound_hit:
        outcome = "no_progress"
    elif state == "needs_answer" and open_count == 0 and shortcuts:
        outcome = "no_progress"
    elif state == "needs_review" or (needs_review and open_count == 0):
        outcome = "needs_review"
    elif state in {"deferred_unknown", "deferred_needs_evidence"}:
        outcome = "deferred_needs_evidence"
    elif state == "saturated" and needs_review:
        outcome = "needs_review"
    elif state == "saturated" and payload.get("intake_complete") and not items:
        outcome = "complete"
    elif state == "saturated":
        outcome = "saturated"
    elif state == "needs_answer" or open_count:
        outcome = "awaiting_user"
    else:
        stored = str(payload.get("outcome") or "").strip()
        outcome = stored if stored in {
            "saturated", "complete", "paused", "awaiting_user",
            "deferred_needs_evidence", "blocked_provider", "no_progress", "needs_review",
        } else "awaiting_user"
    if paused:
        outcome = "paused"
    stalled = bool(payload.get("worker_stalled"))
    if stalled and outcome in {"awaiting_user", "paused"}:
        outcome = "no_progress"
    lane = str(payload.get("dependency_lane") or "").strip()
    standing = {
        "reason": "interview_stop_is_not_legal_sufficiency",
        "legal_sufficiency": False,
        "core_facts_complete": False,
        "proof_requirements_satisfied": False,
    }
    remaining = [standing, *items]
    next_actions = {
        "paused": "resume_when_user_returns",
        "awaiting_user": "answer_pending_question",
        "deferred_needs_evidence": "collect_evidence_then_resume",
        "blocked_provider": "retry_when_provider_available",
        "no_progress": "review_unresolved_issues_then_resume",
        "needs_review": "manual_review_then_resume",
        "saturated": "review_unresolved_issues_then_resume",
        "complete": "review_evidence_gaps_before_filing",
    }
    distinction = {
        "awaiting_user": "awaiting_user",
        "paused": "awaiting_user",
        "deferred_needs_evidence": "evidence_request",
        "blocked_provider": "unavailable_provider",
        "no_progress": "no_progress",
        "needs_review": "review",
        "saturated": "saturated",
        "complete": "complete",
    }.get(outcome, outcome or "awaiting_user")
    action = next_actions.get(outcome, "review_unresolved_issues_then_resume")
    concrete = {
        "source_research": "acquire_legal_sources",
        "evidence_request": "ingest_private_evidence",
        "review": "refresh_grounding",
    }
    if lane in concrete and outcome not in {"no_progress", "blocked_provider", "paused", "awaiting_user"}:
        distinction = lane
        action = concrete[lane]
    elif outcome == "saturated" and lane == "source_research":
        distinction = "source_research"
        action = concrete["source_research"]
    return {
        "outcome": outcome,
        "state": state or None,
        "dependency_lane": lane or None,
        "stopping_distinction": distinction,
        "operation_terminated": outcome == "no_progress",
        "busy_loop": False,
        "reads_developer_stdin": False,
        "remaining_issues": remaining,
        "unresolved_issue_summary": summary,
        "resumable_next_action": {
            "action": action,
            "resumable": outcome != "no_progress" or not stalled,
            "reason": outcome,
            "worker_stalled": stalled,
            "supervisory_restart": False,
            "reads_developer_stdin": False,
            "busy_loop": False,
        },
        "legal_sufficiency": False,
        "core_facts_complete": False,
        "proof_requirements_satisfied": False,
        "filing_ready": False,
        "intake_complete": bool(payload.get("intake_complete")) and outcome == "complete",
        "rejected_shortcuts": shortcuts,
    }


_DEPENDENCY_LANE_ALIASES = {
    "source_research": "source_research",
    "source": "source_research",
    "legal_source": "source_research",
    "authority": "source_research",
    "evidence_request": "evidence_request",
    "evidence": "evidence_request",
    "proof": "evidence_request",
    "review": "review",
    "contradiction": "review",
    "grounding": "review",
}
_DEPENDENCY_LANE_ACTIONS = {
    "source_research": "acquire_legal_sources",
    "evidence_request": "ingest_private_evidence",
    "review": "refresh_grounding",
}
MAX_DEPENDENCY_ACTION_ATTEMPTS = 3


def dependency_lane_for(item: Any) -> Optional[str]:
    """Map one open dependency to a source, evidence, or review lane."""
    if not isinstance(item, dict):
        return None
    for key in ("lane", "dependency_lane", "kind", "target_kind", "dependency_kind"):
        token = str(item.get(key) or "").strip().lower()
        if token in _DEPENDENCY_LANE_ALIASES:
            return _DEPENDENCY_LANE_ALIASES[token]
    disposition = str(item.get("disposition") or "").strip().lower()
    if disposition == "contradictory":
        return "review"
    if item.get("needs_legal_source") or item.get("legal_source_open"):
        return "source_research"
    if item.get("needs_evidence") or item.get("evidence_open"):
        return "evidence_request"
    if item.get("needs_review"):
        return "review"
    return None


def publish_authorized_dependency_action(
    stop: Optional[Dict[str, Any]],
    *,
    attempt: int = 0,
    context: Optional[Dict[str, Any]] = None,
    hook_completed: bool = False,
) -> Dict[str, Any]:
    """Publish one authorized next action, or terminate when the bound is spent.

    A completed hook, an empty question pool, and a stalled worker do not
    establish factual, legal, proof, or filing sufficiency. This function
    decides once. It does not loop and it does not read developer stdin.
    """
    payload = stop if isinstance(stop, dict) else {}
    if payload.get("stopping_distinction"):
        policy = payload
    else:
        policy = project_stopping_policy(payload)
    distinction = str(policy.get("stopping_distinction") or "")
    resumed = context if isinstance(context, dict) else {}
    try:
        used = int(attempt)
    except (TypeError, ValueError):
        used = 0
    if used < 0:
        used = 0
    resumable_context = {
        "case_id": resumed.get("case_id"),
        "target_id": resumed.get("target_id"),
        "target_revision": resumed.get("target_revision"),
        "graph_revision": resumed.get("graph_revision"),
        "session_revision": resumed.get("session_revision"),
        "attempt": used,
        "max_attempts": MAX_DEPENDENCY_ACTION_ATTEMPTS,
    }
    packet = {
        "legal_sufficiency": False,
        "core_facts_complete": False,
        "proof_requirements_satisfied": False,
        "filing_ready": False,
        "hook_completed": bool(hook_completed),
        "hook_completed_is_sufficiency": False,
        "busy_loop": False,
        "reads_developer_stdin": False,
        "worker_stalled": bool((policy.get("resumable_next_action") or {}).get("worker_stalled")),
        "awaiting_user": policy.get("outcome") in {"awaiting_user", "paused"} and not policy.get("operation_terminated"),
        "attempt": used,
        "max_attempts": MAX_DEPENDENCY_ACTION_ATTEMPTS,
        "resumable_context": resumable_context,
        "stopping_distinction": distinction or None,
        "operation": _DEPENDENCY_LANE_ACTIONS.get(distinction),
    }
    if policy.get("operation_terminated") or distinction in {"no_progress", "unavailable_provider"}:
        packet.update({
            "status": "terminated" if distinction == "no_progress" or policy.get("operation_terminated") else "unavailable",
            "published": False,
            "authorized": False,
            "awaiting_user": False,
            "operation_terminated": distinction == "no_progress" or bool(policy.get("operation_terminated")),
            "reason": distinction or "terminated",
        })
        return packet
    if distinction not in _DEPENDENCY_LANE_ACTIONS:
        packet.update({
            "status": "withheld",
            "published": False,
            "authorized": False,
            "operation": None,
            "reason": distinction or "awaiting_user",
        })
        return packet
    if used >= MAX_DEPENDENCY_ACTION_ATTEMPTS:
        packet.update({
            "status": "terminated",
            "published": False,
            "authorized": False,
            "awaiting_user": False,
            "operation_terminated": True,
            "reason": "attempt_bound",
        })
        return packet
    packet.update({
        "status": "published",
        "published": True,
        "authorized": True,
        "bounded": True,
        "action": _DEPENDENCY_LANE_ACTIONS[distinction],
        "operation": _DEPENDENCY_LANE_ACTIONS[distinction],
        "reason": distinction,
        "operation_terminated": False,
    })
    packet["resumable_context"]["attempt"] = used + 1
    packet["attempt"] = used + 1
    return packet
