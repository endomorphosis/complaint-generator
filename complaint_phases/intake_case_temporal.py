"""Intake temporal registry builders moved from intake_case_file."""

from __future__ import annotations

from itertools import combinations
import re
from typing import Any, Dict, List

from complaint_phases.intake_case_file import (
    _MONTH_NAME_TO_NUMBER,
    _coerce_dict,
    _coerce_list,
    _coerce_provenance_refs,
    _coerce_two_digit_year,
    _derive_relative_temporal_context_from_anchor,
    _month_bounds,
    _normalize_canonical_fact_record,
    _normalize_date_iso,
    _normalize_scope_key,
    _normalize_text,
    _parse_relative_offset,
    _relative_reference_families,
    _temporal_issue_id,
    _temporal_relation_preview,
    _timeline_capable_facts,
    _unique_normalized_strings,
    _year_bounds,
)


def _parse_single_temporal_expression(value: str) -> Dict[str, Any]:
    normalized = _normalize_text(value)
    if not normalized:
        return {
            "start_date": None,
            "end_date": None,
            "granularity": "unknown",
            "matched_text": "",
        }

    month_names = "|".join(_MONTH_NAME_TO_NUMBER)

    iso_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", normalized)
    if iso_match:
        year, month, day = (int(item) for item in iso_match.groups())
        iso_date = _normalize_date_iso(year, month, day)
        return {
            "start_date": iso_date,
            "end_date": iso_date,
            "granularity": "day",
            "matched_text": iso_match.group(0),
        }

    month_day_year_match = re.search(
        rf"\b({month_names})\s+(\d{{1,2}}),\s*(\d{{4}})\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if month_day_year_match:
        month_name, day_text, year_text = month_day_year_match.groups()
        month = _MONTH_NAME_TO_NUMBER[month_name.lower()]
        day = int(day_text)
        year = int(year_text)
        iso_date = _normalize_date_iso(year, month, day)
        return {
            "start_date": iso_date,
            "end_date": iso_date,
            "granularity": "day",
            "matched_text": month_day_year_match.group(0),
        }

    numeric_date_match = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", normalized)
    if numeric_date_match:
        month_text, day_text, year_text = numeric_date_match.groups()
        month = int(month_text)
        day = int(day_text)
        year = _coerce_two_digit_year(int(year_text))
        iso_date = _normalize_date_iso(year, month, day)
        return {
            "start_date": iso_date,
            "end_date": iso_date,
            "granularity": "day",
            "matched_text": numeric_date_match.group(0),
        }

    month_year_match = re.search(
        rf"\b({month_names})\s+(\d{{4}})\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if month_year_match:
        month_name, year_text = month_year_match.groups()
        month = _MONTH_NAME_TO_NUMBER[month_name.lower()]
        year = int(year_text)
        start_date, end_date = _month_bounds(year, month)
        return {
            "start_date": start_date,
            "end_date": end_date,
            "granularity": "month",
            "matched_text": month_year_match.group(0),
        }

    year_match = re.search(r"\b(19\d{2}|20\d{2}|21\d{2})\b", normalized)
    if year_match:
        year = int(year_match.group(1))
        start_date, end_date = _year_bounds(year)
        return {
            "start_date": start_date,
            "end_date": end_date,
            "granularity": "year",
            "matched_text": year_match.group(0),
        }

    return {
        "start_date": None,
        "end_date": None,
        "granularity": "unknown",
        "matched_text": "",
    }


def _enrich_canonical_facts_with_relative_anchor_dates(canonical_facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized_facts = [
        _normalize_canonical_fact_record(record)
        for record in canonical_facts if isinstance(record, dict)
    ]
    anchored_by_family: Dict[str, List[Dict[str, Any]]] = {}
    for fact in normalized_facts:
        predicate_family = _normalize_text(fact.get("predicate_family") or "").lower()
        start_date = _coerce_dict(fact.get("temporal_context")).get("start_date")
        if predicate_family and start_date:
            anchored_by_family.setdefault(predicate_family, []).append(fact)

    enriched_facts: List[Dict[str, Any]] = []
    for fact in normalized_facts:
        temporal_context = _coerce_dict(fact.get("temporal_context"))
        if temporal_context.get("start_date") or not temporal_context.get("relative_markers"):
            enriched_facts.append(fact)
            continue

        relative_offset = _parse_relative_offset(list(temporal_context.get("relative_markers") or []))
        reference_families = _relative_reference_families(fact)
        predicate_family = _normalize_text(fact.get("predicate_family") or "").lower()
        if not relative_offset or not reference_families:
            enriched_facts.append(fact)
            continue

        candidate_anchors: List[Dict[str, Any]] = []
        for family in reference_families:
            if family == predicate_family:
                continue
            candidate_anchors.extend(anchored_by_family.get(family, []))

        if not candidate_anchors:
            enriched_facts.append(fact)
            continue

        candidate_anchors = sorted(
            candidate_anchors,
            key=lambda anchor: _normalize_text(_coerce_dict(anchor.get("temporal_context")).get("start_date") or ""),
        )
        anchor_fact = candidate_anchors[-1] if relative_offset.get("direction") == "after" else candidate_anchors[0]
        derived_context = _derive_relative_temporal_context_from_anchor(fact, anchor_fact, relative_offset)
        if not derived_context:
            enriched_facts.append(fact)
            continue

        enriched_facts.append({
            **fact,
            "temporal_context": derived_context,
        })

    anchored_protected_activity_exists = any(
        _normalize_text(fact.get("predicate_family") or "").lower() == "protected_activity"
        and bool(_coerce_dict(fact.get("temporal_context")).get("start_date"))
        for fact in enriched_facts
    )
    if not anchored_protected_activity_exists:
        return enriched_facts

    collapsed_facts: List[Dict[str, Any]] = []
    for fact in enriched_facts:
        predicate_family = _normalize_text(fact.get("predicate_family") or "").lower()
        temporal_context = _coerce_dict(fact.get("temporal_context"))
        text_value = _normalize_text(fact.get("text") or "")
        if (
            predicate_family == "protected_activity"
            and not temporal_context.get("start_date")
            and temporal_context.get("relative_markers")
            and any(
                _normalize_text(other.get("text") or "") == text_value
                and _normalize_text(other.get("predicate_family") or "").lower() in {"adverse_action", "causation"}
                and bool(_coerce_dict(other.get("temporal_context")).get("start_date"))
                for other in enriched_facts
                if other is not fact
            )
        ):
            continue
        collapsed_facts.append(fact)

    return collapsed_facts


def build_temporal_relation_registry(
    canonical_facts: List[Dict[str, Any]],
    timeline_relations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    fact_index = {
        _normalize_text(fact.get("fact_id") or ""): fact
        for fact in _timeline_capable_facts(canonical_facts)
        if _normalize_text(fact.get("fact_id") or "")
    }
    registry: List[Dict[str, Any]] = []

    # Track explicit fact pairs so inferred relations only fill gaps.
    explicit_pairs: set = set()

    for index, relation in enumerate(timeline_relations if isinstance(timeline_relations, list) else [], start=1):
        if not isinstance(relation, dict):
            continue
        raw_relation_id = _normalize_text(relation.get("relation_id") or "")
        relation_id = raw_relation_id or f"timeline_relation_{index:03d}"
        source_fact_id = _normalize_text(relation.get("source_fact_id") or "")
        target_fact_id = _normalize_text(relation.get("target_fact_id") or "")
        source_fact = _coerce_dict(fact_index.get(source_fact_id))
        target_fact = _coerce_dict(fact_index.get(target_fact_id))
        claim_types = _unique_normalized_strings(
            list(source_fact.get("claim_types") or []) + list(target_fact.get("claim_types") or [])
        )
        element_tags = _unique_normalized_strings(
            list(source_fact.get("element_tags") or []) + list(target_fact.get("element_tags") or [])
        )
        source_artifact_ids = _unique_normalized_strings(
            list(source_fact.get("source_artifact_ids") or [])
            + list(target_fact.get("source_artifact_ids") or [])
        )
        testimony_record_ids = _unique_normalized_strings(
            list(source_fact.get("testimony_record_ids") or [])
            + list(target_fact.get("testimony_record_ids") or [])
        )
        raw_inference_basis = _normalize_text(relation.get("inference_basis") or "")
        relation_id_looks_generated = bool(raw_relation_id and raw_relation_id.startswith("timeline_relation_"))
        inference_basis = raw_inference_basis or (
            "normalized_temporal_context" if relation_id_looks_generated else "explicit_relation"
        )
        inference_mode = _normalize_text(relation.get("inference_mode") or "")
        if not inference_mode:
            inference_mode = (
                "derived_from_structured_sequence"
                if inference_basis == "structured_timeline_sequence"
                else (
                    "derived_from_temporal_context"
                    if inference_basis == "normalized_temporal_context"
                    else "explicit"
                )
            )
        registry.append(
            {
                **relation,
                "relation_id": relation_id,
                "registry_version": "temporal_relation_registry.v1",
                "source_fact_id": source_fact_id,
                "target_fact_id": target_fact_id,
                "source_temporal_fact_id": str(source_fact.get("temporal_fact_id") or source_fact_id or "") or None,
                "target_temporal_fact_id": str(target_fact.get("temporal_fact_id") or target_fact_id or "") or None,
                "claim_types": claim_types,
                "element_tags": element_tags,
                "source_fact_text": _normalize_text(source_fact.get("text") or "") or None,
                "target_fact_text": _normalize_text(target_fact.get("text") or "") or None,
                "source_artifact_ids": source_artifact_ids,
                "testimony_record_ids": testimony_record_ids,
                "source_span_refs": _coerce_provenance_refs(
                    list(source_fact.get("source_span_refs") or [])
                    + list(target_fact.get("source_span_refs") or [])
                ),
                "inference_mode": inference_mode,
                "inference_basis": inference_basis,
                "explanation": (
                    f"{source_fact_id or 'unknown_fact'} {str(relation.get('relation_type') or 'related_to')} "
                    f"{target_fact_id or 'unknown_fact'} based on normalized temporal context."
                ),
            }
        )
        if source_fact_id and target_fact_id:
            explicit_pairs.add((source_fact_id, target_fact_id))
            explicit_pairs.add((target_fact_id, source_fact_id))

    # T1: Infer ordering relations from date anchors for pairs without an explicit relation.
    # When two timeline-capable facts both carry a start_date, derive before/same_time/after
    # so that proof-bundle and rule-profile evaluation can use a complete partial-order graph
    # even when the upstream relation extractor missed the pair.
    #
    # Guard: skip inference when the anchored-fact set is large to avoid O(n²) overhead.
    # Typical temporal-capable sets are small (≤ ~20 facts); a 50-fact ceiling keeps the
    # worst-case below 1 250 pairs while protecting against degenerate inputs.
    _MAX_INFERRED_ANCHOR_FACTS = 50
    anchored_facts = [
        (
            _normalize_text(fact.get("fact_id") or ""),
            str(_coerce_dict(fact.get("temporal_context")).get("start_date") or "").strip(),
            fact,
        )
        for fact in _timeline_capable_facts(canonical_facts)
        if _normalize_text(fact.get("fact_id") or "")
        and str(_coerce_dict(fact.get("temporal_context")).get("start_date") or "").strip()
    ]
    inferred_index = len(registry)
    if len(anchored_facts) <= _MAX_INFERRED_ANCHOR_FACTS:
        for (id_a, date_a, fact_a), (id_b, date_b, fact_b) in combinations(anchored_facts, 2):
            pair_key = (id_a, id_b)
            if pair_key in explicit_pairs:
                continue
            if date_a < date_b:
                relation_type = "before"
                source_fact_id, target_fact_id = id_a, id_b
                source_fact, target_fact = fact_a, fact_b
                source_date, target_date = date_a, date_b
            elif date_a > date_b:
                relation_type = "before"
                source_fact_id, target_fact_id = id_b, id_a
                source_fact, target_fact = fact_b, fact_a
                source_date, target_date = date_b, date_a
            else:
                relation_type = "same_time"
                source_fact_id, target_fact_id = id_a, id_b
                source_fact, target_fact = fact_a, fact_b
                source_date, target_date = date_a, date_b
            inferred_index += 1
            relation_id = f"inferred_relation_{inferred_index:03d}"
            claim_types = _unique_normalized_strings(
                list(source_fact.get("claim_types") or []) + list(target_fact.get("claim_types") or [])
            )
            element_tags = _unique_normalized_strings(
                list(source_fact.get("element_tags") or []) + list(target_fact.get("element_tags") or [])
            )
            source_artifact_ids = _unique_normalized_strings(
                list(source_fact.get("source_artifact_ids") or [])
                + list(target_fact.get("source_artifact_ids") or [])
            )
            testimony_record_ids = _unique_normalized_strings(
                list(source_fact.get("testimony_record_ids") or [])
                + list(target_fact.get("testimony_record_ids") or [])
            )
            registry.append(
                {
                    "relation_id": relation_id,
                    "registry_version": "temporal_relation_registry.v1",
                    "relation_type": relation_type,
                    "source_fact_id": source_fact_id,
                    "target_fact_id": target_fact_id,
                    "source_temporal_fact_id": str(source_fact.get("temporal_fact_id") or source_fact_id or "") or None,
                    "target_temporal_fact_id": str(target_fact.get("temporal_fact_id") or target_fact_id or "") or None,
                    "claim_types": claim_types,
                    "element_tags": element_tags,
                    "source_fact_text": _normalize_text(source_fact.get("text") or "") or None,
                    "target_fact_text": _normalize_text(target_fact.get("text") or "") or None,
                    "source_artifact_ids": source_artifact_ids,
                    "testimony_record_ids": testimony_record_ids,
                    "source_span_refs": _coerce_provenance_refs(
                        list(source_fact.get("source_span_refs") or [])
                        + list(target_fact.get("source_span_refs") or [])
                    ),
                    "inference_mode": "derived_from_date_anchors",
                    "inference_basis": (
                        f"{source_fact_id}.start_date:{source_date} vs {target_fact_id}.start_date:{target_date}"
                    ),
                    "explanation": (
                        f"{source_fact_id} {relation_type} {target_fact_id} inferred from date anchors "
                        f"({source_date} vs {target_date})."
                    ),
                }
            )
    return registry


def build_timeline_consistency_summary(
    canonical_facts: List[Dict[str, Any]],
    timeline_anchors: List[Dict[str, Any]],
    timeline_relations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    timeline_facts = _timeline_capable_facts(canonical_facts)
    anchors = _coerce_list(timeline_anchors)
    relations = _coerce_list(timeline_relations)

    relation_type_counts: Dict[str, int] = {}
    temporal_conflict_relation_count = 0
    for relation in relations:
        relation_dict = _coerce_dict(relation)
        if not relation_dict:
            continue
        relation_type = _normalize_text(relation_dict.get("relation_type") or "").lower()
        if not relation_type:
            continue
        relation_type_counts[relation_type] = relation_type_counts.get(relation_type, 0) + 1
        if relation_type in {"temporal_conflict", "contradiction", "overlap_conflict"}:
            temporal_conflict_relation_count += 1

    timeline_fact_ids = {
        _normalize_text(_coerce_dict(fact).get("fact_id") or "") or f"timeline_fact_{index}"
        for index, fact in enumerate(timeline_facts, start=1)
        if isinstance(fact, dict)
    }
    anchored_fact_ids = {
        _normalize_text(_coerce_dict(anchor).get("source_fact_id") or _coerce_dict(anchor).get("fact_id") or "")
        for anchor in anchors
        if isinstance(anchor, dict)
    }
    anchored_fact_ids.discard("")

    missing_temporal_fact_ids: List[str] = []
    relative_only_fact_ids: List[str] = []
    approximate_fact_ids: List[str] = []
    range_fact_ids: List[str] = []
    non_day_precision_fact_ids: List[str] = []
    day_precision_fact_ids: List[str] = []
    ordered_fact_count = 0

    for index, fact in enumerate(timeline_facts, start=1):
        fact_dict = _coerce_dict(fact)
        if not fact_dict:
            continue
        fact_id = _normalize_text(fact_dict.get("fact_id") or "") or f"timeline_fact_{index}"
        temporal_context = _coerce_dict(fact_dict.get("temporal_context"))
        start_date = _normalize_text(temporal_context.get("start_date") or "")
        end_date = _normalize_text(temporal_context.get("end_date") or "")
        granularity = _normalize_text(temporal_context.get("granularity") or "").lower()
        relative_markers = _unique_normalized_strings(temporal_context.get("relative_markers") or [])
        has_anchor = bool(start_date)

        if has_anchor:
            ordered_fact_count += 1
            if granularity == "day" and len(start_date) == 10:
                day_precision_fact_ids.append(fact_id)
            else:
                non_day_precision_fact_ids.append(fact_id)
        else:
            missing_temporal_fact_ids.append(fact_id)
            if relative_markers:
                relative_only_fact_ids.append(fact_id)

        if bool(temporal_context.get("is_approximate", False)):
            approximate_fact_ids.append(fact_id)
        if bool(temporal_context.get("is_range", False)) or (start_date and end_date and start_date != end_date):
            range_fact_ids.append(fact_id)

    orphan_anchor_count = sum(
        1
        for anchor in anchors
        if _normalize_text(_coerce_dict(anchor).get("source_fact_id") or _coerce_dict(anchor).get("fact_id") or "")
        and _normalize_text(_coerce_dict(anchor).get("source_fact_id") or _coerce_dict(anchor).get("fact_id") or "")
        not in timeline_fact_ids
    )

    warnings: List[str] = []
    if missing_temporal_fact_ids:
        warnings.append("Some timeline facts still lack normalized dates or ranges.")
    if relative_only_fact_ids:
        warnings.append("Some timeline facts only express relative ordering and still need anchoring.")
    if temporal_conflict_relation_count:
        warnings.append("Timeline relations include unresolved temporal conflicts.")
    if non_day_precision_fact_ids:
        warnings.append("Some anchored facts are only month/year precision and may still need day-level dates.")

    return {
        "event_count": len(timeline_facts),
        "anchor_count": len(anchors),
        "ordered_fact_count": ordered_fact_count,
        "unsequenced_fact_count": len(missing_temporal_fact_ids),
        "approximate_fact_count": len(approximate_fact_ids),
        "range_fact_count": len(range_fact_ids),
        "relation_count": len(relations),
        "relation_type_counts": relation_type_counts,
        "missing_temporal_fact_ids": missing_temporal_fact_ids,
        "relative_only_fact_ids": relative_only_fact_ids,
        "warnings": warnings,
        "partial_order_ready": bool(timeline_facts) and not missing_temporal_fact_ids and not temporal_conflict_relation_count,
        "day_precision_fact_count": len(day_precision_fact_ids),
        "non_day_precision_fact_ids": non_day_precision_fact_ids,
        "temporal_conflict_relation_count": temporal_conflict_relation_count,
        "orphan_anchor_count": orphan_anchor_count,
    }


def _build_temporal_graph_record(
    *,
    graph_id: str,
    claim_type: str,
    facts: List[Dict[str, Any]],
    relations: List[Dict[str, Any]],
    issues: List[Dict[str, Any]],
    element_id: str = "",
    element_label: str = "",
) -> Dict[str, Any]:
    fact_ids = [
        _normalize_text(fact.get("fact_id") or fact.get("temporal_fact_id") or "")
        for fact in facts
        if _normalize_text(fact.get("fact_id") or fact.get("temporal_fact_id") or "")
    ]
    relation_ids = [
        _normalize_text(relation.get("relation_id") or "")
        for relation in relations
        if _normalize_text(relation.get("relation_id") or "")
    ]
    issue_ids: List[str] = []
    open_issue_ids: List[str] = []
    blocking_issue_ids: List[str] = []
    issue_type_counts: Dict[str, int] = {}
    issue_status_counts: Dict[str, int] = {}
    severity_counts: Dict[str, int] = {}
    missing_temporal_predicates: List[str] = []
    required_provenance_kinds: List[str] = []
    warnings: List[str] = []

    for issue in issues:
        issue_id = _temporal_issue_id(issue)
        if issue_id and issue_id not in issue_ids:
            issue_ids.append(issue_id)
        issue_type = _normalize_text(issue.get("issue_type") or issue.get("category") or "").lower()
        if issue_type:
            issue_type_counts[issue_type] = issue_type_counts.get(issue_type, 0) + 1
        status_value = _normalize_text(issue.get("current_resolution_status") or issue.get("status") or "open").lower() or "open"
        issue_status_counts[status_value] = issue_status_counts.get(status_value, 0) + 1
        severity = _normalize_text(issue.get("severity") or "").lower()
        if severity:
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        if status_value != "resolved" and issue_id:
            open_issue_ids.append(issue_id)
        if status_value != "resolved" and (bool(issue.get("blocking")) or severity == "blocking") and issue_id:
            blocking_issue_ids.append(issue_id)
        for predicate in issue.get("missing_temporal_predicates") if isinstance(issue.get("missing_temporal_predicates"), list) else []:
            normalized_predicate = _normalize_text(predicate)
            if normalized_predicate and normalized_predicate not in missing_temporal_predicates:
                missing_temporal_predicates.append(normalized_predicate)
        for provenance_kind in issue.get("required_provenance_kinds") if isinstance(issue.get("required_provenance_kinds"), list) else []:
            normalized_kind = _normalize_text(provenance_kind)
            if normalized_kind and normalized_kind not in required_provenance_kinds:
                required_provenance_kinds.append(normalized_kind)
        if status_value != "resolved":
            summary = _normalize_text(issue.get("summary") or issue_type or issue_id)
            if summary and summary not in warnings:
                warnings.append(summary)

    relation_type_counts: Dict[str, int] = {}
    relation_preview: List[str] = []
    for relation in relations:
        relation_type = _normalize_text(relation.get("relation_type") or "").lower()
        if relation_type:
            relation_type_counts[relation_type] = relation_type_counts.get(relation_type, 0) + 1
        preview = _temporal_relation_preview(relation)
        if preview and preview not in relation_preview:
            relation_preview.append(preview)

    anchored_fact_ids: List[str] = []
    unanchored_fact_ids: List[str] = []
    timeline_anchor_ids: List[str] = []
    for fact in facts:
        fact_id = _normalize_text(fact.get("fact_id") or fact.get("temporal_fact_id") or "")
        temporal_context = _coerce_dict(fact.get("temporal_context"))
        has_anchor = bool(
            temporal_context.get("start_date")
            or fact.get("start_time")
            or _coerce_list(fact.get("timeline_anchor_ids"))
        )
        if fact_id and has_anchor:
            anchored_fact_ids.append(fact_id)
        elif fact_id:
            unanchored_fact_ids.append(fact_id)
        for anchor_id in fact.get("timeline_anchor_ids") if isinstance(fact.get("timeline_anchor_ids"), list) else []:
            normalized_anchor_id = _normalize_text(anchor_id)
            if normalized_anchor_id and normalized_anchor_id not in timeline_anchor_ids:
                timeline_anchor_ids.append(normalized_anchor_id)

    partial_order_ready = bool(facts) and not open_issue_ids and not blocking_issue_ids and not unanchored_fact_ids
    graph_record = {
        "contract_version": "claim_temporal_graph.v1",
        "graph_id": graph_id,
        "claim_type": claim_type,
        "claim_key": _normalize_scope_key(claim_type),
        "element_id": element_id,
        "element_key": _normalize_scope_key(element_id or element_label),
        "element_label": element_label,
        "fact_count": len(facts),
        "relation_count": len(relations),
        "issue_count": len(issues),
        "fact_ids": fact_ids,
        "temporal_fact_ids": fact_ids,
        "anchored_fact_ids": anchored_fact_ids,
        "unanchored_fact_ids": unanchored_fact_ids,
        "relation_ids": relation_ids,
        "temporal_relation_ids": relation_ids,
        "issue_ids": issue_ids,
        "temporal_issue_ids": issue_ids,
        "open_issue_ids": open_issue_ids,
        "blocking_issue_ids": blocking_issue_ids,
        "timeline_anchor_ids": timeline_anchor_ids,
        "relation_type_counts": relation_type_counts,
        "relation_preview": relation_preview[:10],
        "issue_type_counts": issue_type_counts,
        "issue_status_counts": issue_status_counts,
        "severity_counts": severity_counts,
        "missing_temporal_predicates": missing_temporal_predicates,
        "required_provenance_kinds": required_provenance_kinds,
        "warning_count": len(warnings),
        "warnings": warnings,
        "partial_order_ready": partial_order_ready,
        "readiness": {
            "ready_for_temporal_formalization": partial_order_ready,
            "trace_fact_ids": fact_ids,
            "trace_relation_ids": relation_ids,
            "trace_issue_ids": issue_ids,
            "blocking_issue_ids": blocking_issue_ids,
            "missing_temporal_predicates": missing_temporal_predicates,
            "required_provenance_kinds": required_provenance_kinds,
        },
        "facts": facts,
        "relations": relations,
        "issues": issues,
    }
    return graph_record
