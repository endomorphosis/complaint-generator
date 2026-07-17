from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Set


def _normalize_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_")


def _latest_anchored_date(facts: List[Dict[str, Any]]) -> Optional[str]:
    """Return the latest start_date found across a list of temporal facts, or None."""
    best: Optional[str] = None
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        tc = fact.get("temporal_context") if isinstance(fact.get("temporal_context"), dict) else {}
        start = str(tc.get("start_date") or "").strip()
        if not start:
            continue
        if best is None or start > best:
            best = start
    return best


def _is_retaliation_claim_type(claim_type: Any) -> bool:
    normalized = _normalize_key(claim_type)
    return normalized == "retaliation" or normalized.endswith("retaliation") or "retaliation" in normalized.split("_")


def _element_role(element: Dict[str, Any]) -> str:
    candidates = [
        _normalize_key(element.get("element_id")),
        _normalize_key(element.get("element_text")),
    ]
    for candidate in candidates:
        if candidate in {"protected_activity", "protectedactivity"}:
            return "protected_activity"
        if candidate in {"adverse_action", "adverseaction"}:
            return "adverse_action"
        if candidate in {"causal_connection", "causation", "causal_link", "causal_nexus"}:
            return "causal_connection"
    return ""


def _record_tags(record: Dict[str, Any]) -> Set[str]:
    tags: Set[str] = set()
    for field_name in ("element_tags", "affected_element_ids"):
        values = record.get(field_name)
        if isinstance(values, list):
            for value in values:
                normalized = _normalize_key(value)
                if normalized:
                    tags.add(normalized)
    return tags


def evaluate_temporal_rule_profile(
    claim_type: Any,
    element: Dict[str, Any],
    temporal_context: Dict[str, Any],
    *,
    reference_date: Optional[date] = None,
) -> Dict[str, Any]:
    if not _is_retaliation_claim_type(claim_type):
        return {
            "available": False,
            "evaluated": False,
            "profile_id": "",
            "rule_frame_id": "",
            "status": "not_applicable",
            "reason": "No temporal rule profile for this claim type.",
        }

    role = _element_role(element if isinstance(element, dict) else {})
    if not role:
        return {
            "available": True,
            "evaluated": False,
            "profile_id": "retaliation_temporal_profile_v1",
            "rule_frame_id": "retaliation_temporal_frame",
            "status": "not_targeted",
            "reason": "Element is not covered by the retaliation temporal profile.",
        }

    facts = temporal_context.get("temporal_facts", []) if isinstance(temporal_context, dict) else []
    relations = temporal_context.get("temporal_relations", []) if isinstance(temporal_context, dict) else []
    issues = temporal_context.get("temporal_issues", []) if isinstance(temporal_context, dict) else []

    protected_facts = [fact for fact in facts if isinstance(fact, dict) and "protected_activity" in _record_tags(fact)]
    adverse_facts = [fact for fact in facts if isinstance(fact, dict) and "adverse_action" in _record_tags(fact)]
    protected_fact_ids = [str(fact.get("fact_id") or "").strip() for fact in protected_facts if str(fact.get("fact_id") or "").strip()]
    adverse_fact_ids = [str(fact.get("fact_id") or "").strip() for fact in adverse_facts if str(fact.get("fact_id") or "").strip()]
    anchored_protected_fact_ids = [
        fact_id
        for fact_id, fact in ((str(fact.get("fact_id") or "").strip(), fact) for fact in protected_facts if isinstance(fact, dict))
        if fact_id and isinstance(fact.get("temporal_context"), dict) and fact["temporal_context"].get("start_date")
    ]
    anchored_adverse_fact_ids = [
        fact_id
        for fact_id, fact in ((str(fact.get("fact_id") or "").strip(), fact) for fact in adverse_facts if isinstance(fact, dict))
        if fact_id and isinstance(fact.get("temporal_context"), dict) and fact["temporal_context"].get("start_date")
    ]

    before_relations: List[Dict[str, Any]] = []
    reverse_before_relations: List[Dict[str, Any]] = []
    partial_relations: List[Dict[str, Any]] = []
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        source_fact_id = str(relation.get("source_fact_id") or "").strip()
        target_fact_id = str(relation.get("target_fact_id") or "").strip()
        relation_type = _normalize_key(relation.get("relation_type"))
        if source_fact_id in protected_fact_ids and target_fact_id in adverse_fact_ids:
            if relation_type == "before":
                before_relations.append(relation)
            elif relation_type in {"same_time", "overlaps"}:
                partial_relations.append(relation)
        elif source_fact_id in adverse_fact_ids and target_fact_id in protected_fact_ids and relation_type == "before":
            reverse_before_relations.append(relation)

    relevant_issue_types = {
        _normalize_key(issue.get("issue_type") or issue.get("category"))
        for issue in issues
        if isinstance(issue, dict)
    }

    blocking_reasons: List[str] = []
    warnings: List[str] = []
    recommended_follow_ups: List[Dict[str, str]] = []
    matched_fact_ids: List[str] = []
    matched_relation_ids: List[str] = []
    status = "missing"

    if role == "protected_activity":
        matched_fact_ids = protected_fact_ids
        if anchored_protected_fact_ids:
            status = "satisfied"
        elif protected_fact_ids:
            status = "partial"
            blocking_reasons.append("Protected activity is identified but lacks a normalized time anchor.")
            recommended_follow_ups.append({
                "lane": "clarify_with_complainant",
                "reason": "Anchor when the protected activity occurred.",
            })
        else:
            blocking_reasons.append("No temporally identified protected activity event is present.")
            recommended_follow_ups.append({
                "lane": "capture_testimony",
                "reason": "Identify the protected activity and when it occurred.",
            })
    elif role == "adverse_action":
        matched_fact_ids = adverse_fact_ids
        if anchored_adverse_fact_ids:
            status = "satisfied"
        elif adverse_fact_ids:
            status = "partial"
            blocking_reasons.append("Adverse action is identified but lacks a normalized time anchor.")
            recommended_follow_ups.append({
                "lane": "request_document",
                "reason": "Anchor the adverse action with a dated document or testimony.",
            })
        else:
            blocking_reasons.append("No temporally identified adverse action event is present.")
            recommended_follow_ups.append({
                "lane": "request_document",
                "reason": "Collect dated records showing the adverse action.",
            })
    else:
        matched_fact_ids = list(dict.fromkeys(protected_fact_ids + adverse_fact_ids))
        matched_relation_ids = [
            str(relation.get("relation_id") or "").strip()
            for relation in before_relations + reverse_before_relations + partial_relations
            if str(relation.get("relation_id") or "").strip()
        ]
        if reverse_before_relations or "temporal_reverse_before" in relevant_issue_types:
            status = "failed"
            blocking_reasons.append("Available chronology places the adverse action before the protected activity.")
            recommended_follow_ups.append({
                "lane": "request_document",
                "reason": "Resolve the reverse-order chronology with dated records.",
            })
        elif before_relations:
            status = "satisfied"
        elif protected_fact_ids and adverse_fact_ids:
            status = "partial"
            if partial_relations:
                warnings.append("Protected activity and adverse action are only tied by overlapping or same-time chronology.")
            else:
                warnings.append("Protected activity and adverse action are both present but lack an ordering relation.")
            blocking_reasons.append("Retaliation causation lacks a clear temporal ordering from protected activity to adverse action.")
            recommended_follow_ups.append({
                "lane": "clarify_with_complainant",
                "reason": "Clarify whether the protected activity occurred before the adverse action.",
            })
        else:
            if not protected_fact_ids:
                blocking_reasons.append("Retaliation chronology is missing a protected activity event.")
            if not adverse_fact_ids:
                blocking_reasons.append("Retaliation chronology is missing an adverse action event.")
            recommended_follow_ups.append({
                "lane": "capture_testimony",
                "reason": "Collect the missing retaliation chronology events and their dates.",
            })

    if role in {"protected_activity", "adverse_action"} and "relative_only_ordering" in relevant_issue_types:
        warnings.append("Relevant chronology still relies on relative-only ordering.")

    # T2: Contradictory-dates detection — applies primarily to causal_connection but checked for all roles.
    has_contradictory_dates = "contradictory_dates" in relevant_issue_types
    if has_contradictory_dates:
        warnings.append("Contradictory date records are present; chronological ordering is uncertain.")
        if role not in {"protected_activity", "adverse_action"} and status == "satisfied":
            # A satisfied causal ordering claim is weakened when dates contradict.
            status = "partial"
            blocking_reasons.append("Contradictory dates prevent confident ordering confirmation.")
        if role not in {"protected_activity", "adverse_action"}:
            recommended_follow_ups.append({
                "lane": "request_document",
                "reason": "Resolve date contradictions with a dated document or authoritative record.",
            })

    # T2: Limitations-risk detection.  Check both the issue registry and, where anchored
    # adverse-action dates are available, compute the elapsed days against the EEOC filing
    # window.  Two thresholds exist in practice: 180 days in non-deferral states (no state
    # or local fair employment practices agency) and 300 days in deferral states (where a
    # state or local agency exists).  We flag the risk at 180 days so that both non-deferral
    # and deferral cases are caught early; callers can inspect limitations_risk_days to
    # determine which window applies.  This is a warning, not a hard blocker, because the
    # exact limitations period depends on jurisdiction and filing date facts that may not
    # always be in the record.
    has_limitations_risk = "limitations_risk" in relevant_issue_types
    limitations_risk_days: Optional[int] = None
    if not has_limitations_risk and reference_date is not None and anchored_adverse_fact_ids:
        latest_adverse_date = _latest_anchored_date(adverse_facts)
        if latest_adverse_date:
            try:
                event_date = date.fromisoformat(latest_adverse_date[:10])
                days_elapsed = (reference_date - event_date).days
                if days_elapsed > 180:
                    has_limitations_risk = True
                    limitations_risk_days = days_elapsed
            except (ValueError, TypeError):
                pass
    if has_limitations_risk:
        if limitations_risk_days is not None:
            warnings.append(
                f"Adverse action occurred approximately {limitations_risk_days} days ago, "
                "which may be outside the standard EEOC filing window (300 days in deferral "
                "states, 180 days in non-deferral states)."
            )
        else:
            warnings.append(
                "A limitations risk issue is present; the adverse action may be outside the "
                "standard EEOC filing window (300 days in deferral states, 180 days in "
                "non-deferral states)."
            )
        recommended_follow_ups.append({
            "lane": "seek_external_record",
            "reason": "Verify the adverse action date against applicable filing deadlines to assess limitations risk.",
        })

    return {
        "available": True,
        "evaluated": True,
        "profile_id": "retaliation_temporal_profile_v1",
        "rule_frame_id": "retaliation_temporal_frame",
        "claim_type": str(claim_type or ""),
        "element_role": role,
        "status": status,
        "matched_fact_ids": matched_fact_ids,
        "matched_relation_ids": matched_relation_ids,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "recommended_follow_ups": recommended_follow_ups,
        "has_contradictory_dates": has_contradictory_dates,
        "has_limitations_risk": has_limitations_risk,
    }
