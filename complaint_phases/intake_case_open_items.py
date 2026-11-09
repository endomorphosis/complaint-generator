"""Intake open-item builders moved from intake_case_file."""

from __future__ import annotations

from complaint_phases.intake_case_file import (
    _build_blocker_record,
    _build_temporal_graph_record,
    _coerce_dict,
    _coerce_list,
    _contradiction_support_kind,
    _derive_temporal_issue_missing_predicates,
    _derive_temporal_issue_required_provenance_kinds,
    _has_retaliation_causation_link,
    _is_summary_like_timeline_fact,
    _looks_like_staff_person_name,
    _normalize_canonical_fact_record,
    _normalize_intake_target_links,
    _normalize_proof_lead_record,
    _normalize_scope_key,
    _normalize_text,
    _temporal_record_claim_keys,
    _temporal_record_element_keys,
    _timeline_capable_facts,
    _unique_metadata_strings,
    _unique_normalized_strings,
    re,
    refresh_explicit_legal_context,
)


def build_temporal_issue_registry(
    canonical_facts: List[Dict[str, Any]],
    contradiction_queue: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    registry: List[Dict[str, Any]] = []
    seen_issue_ids = set()
    issue_index_by_signature: Dict[tuple[str, str, tuple[str, ...]], int] = {}
    structured_group_facts: Dict[str, List[Dict[str, Any]]] = {}
    duplicate_timeline_text_counts: Dict[str, int] = {}

    for fact in _timeline_capable_facts(canonical_facts):
        structured_group = _normalize_text(fact.get("structured_timeline_group") or "")
        if structured_group:
            structured_group_facts.setdefault(structured_group, []).append(fact)
        text_value = _normalize_text(fact.get("text") or "").lower()
        if text_value:
            duplicate_timeline_text_counts[text_value] = duplicate_timeline_text_counts.get(text_value, 0) + 1

    for fact in _timeline_capable_facts(canonical_facts):
        fact_id = _normalize_text(fact.get("fact_id") or "")
        temporal_context = _coerce_dict(fact.get("temporal_context"))
        if temporal_context.get("start_date"):
            continue
        if _is_summary_like_timeline_fact(fact, structured_group_facts):
            continue
        normalized_text = _normalize_text(fact.get("text") or "").lower()
        if (
            normalized_text
            and duplicate_timeline_text_counts.get(normalized_text, 0) > 1
            and _normalize_text(fact.get("structured_timeline_group") or "") == ""
            and not _unique_normalized_strings(temporal_context.get("relative_markers") or [])
        ):
            continue

        relative_markers = _unique_normalized_strings(temporal_context.get("relative_markers") or [])
        issue_type = "relative_only_ordering" if relative_markers else "missing_anchor"
        left_node_name = _normalize_text(fact.get("text") or "") or None
        structured_group = _normalize_text(fact.get("structured_timeline_group") or "")
        grouped_facts = structured_group_facts.get(structured_group, []) if structured_group else []
        has_structured_sequence_support = (
            bool(structured_group)
            and len(grouped_facts) > 1
            and isinstance(fact.get("sequence_index"), int)
        )
        group_has_any_anchor = any(
            bool(_coerce_dict(item.get("temporal_context")).get("start_date"))
            for item in grouped_facts
            if isinstance(item, dict)
        )
        group_has_relative_support = any(
            bool(_coerce_dict(item.get("temporal_context")).get("relative_markers"))
            for item in grouped_facts
            if isinstance(item, dict)
        )
        issue_severity = "blocking"
        issue_blocking = True
        recommended_resolution_lane = "clarify_with_complainant"
        if has_structured_sequence_support and (group_has_any_anchor or group_has_relative_support):
            issue_severity = "warning"
            issue_blocking = False
            recommended_resolution_lane = "capture_testimony"
        signature = (issue_type, (left_node_name or "").lower(), tuple(relative_markers))
        if signature in issue_index_by_signature:
            existing_issue = registry[issue_index_by_signature[signature]]
            existing_issue["fact_ids"] = _unique_normalized_strings(
                list(existing_issue.get("fact_ids") or []) + ([fact_id] if fact_id else [])
            )
            existing_issue["claim_types"] = _unique_normalized_strings(
                list(existing_issue.get("claim_types") or []) + list(fact.get("claim_types") or [])
            )
            existing_issue["element_tags"] = _unique_normalized_strings(
                list(existing_issue.get("element_tags") or []) + list(fact.get("element_tags") or [])
            )
            existing_issue["missing_temporal_predicates"] = _derive_temporal_issue_missing_predicates(
                existing_issue.get("issue_type"),
                existing_issue.get("fact_ids") or [],
                existing_issue.get("relative_markers") or [],
            )
            existing_issue["required_provenance_kinds"] = _derive_temporal_issue_required_provenance_kinds(
                existing_issue.get("issue_type"),
                existing_issue.get("recommended_resolution_lane"),
            )
            continue
        issue_id = f"temporal_issue:{issue_type}:{fact_id or len(registry) + 1}"
        if issue_id in seen_issue_ids:
            continue
        seen_issue_ids.add(issue_id)

        summary = (
            (
                f"Timeline fact {fact_id or 'unidentified_fact'} only has relative ordering "
                f"({next((marker for marker in relative_markers if 'day' in marker or 'week' in marker or 'month' in marker or 'year' in marker), relative_markers[0])}) and still needs anchoring."
            )
            if relative_markers
            else f"Timeline fact {fact_id or 'unidentified_fact'} still lacks a normalized temporal anchor."
        )
        registry.append(
            {
                "issue_id": issue_id,
                "registry_version": "temporal_issue_registry.v1",
                "issue_type": issue_type,
                "category": issue_type,
                "summary": summary,
                "severity": issue_severity,
                "blocking": issue_blocking,
                "recommended_resolution_lane": recommended_resolution_lane,
                "fact_ids": [fact_id] if fact_id else [],
                "claim_types": _unique_normalized_strings(fact.get("claim_types") or []),
                "element_tags": _unique_normalized_strings(fact.get("element_tags") or []),
                "left_node_name": left_node_name,
                "right_node_name": None,
                "status": "open",
                "current_resolution_status": "open",
                "relative_markers": relative_markers,
                "missing_temporal_predicates": _derive_temporal_issue_missing_predicates(
                    issue_type,
                    [fact_id] if fact_id else [],
                    relative_markers,
                ),
                "required_provenance_kinds": _derive_temporal_issue_required_provenance_kinds(
                    issue_type,
                    recommended_resolution_lane,
                ),
                "source_kind": "temporal_fact_registry",
                "source_ref": fact_id or None,
                "inference_mode": "derived_from_temporal_context",
            }
        )
        issue_index_by_signature[signature] = len(registry) - 1

    # T1: canonical issue type aliases so that contradiction-queue entries tagged with
    # the "temporal_" prefix resolve to the same canonical category that rule profiles
    # and downstream consumers (e.g. evaluate_temporal_rule_profile) expect.
    # Entries not present in this mapping pass through unchanged — they are already
    # in canonical form (e.g. "temporal_reverse_before" is not normalised further).
    _TEMPORAL_ISSUE_CATEGORY_ALIASES: Dict[str, str] = {
        "temporal_contradictory_dates": "contradictory_dates",
        "temporal_limitations_risk": "limitations_risk",
        "temporal_missing_anchor": "missing_anchor",
        "temporal_relative_only_ordering": "relative_only_ordering",
    }

    for contradiction in contradiction_queue if isinstance(contradiction_queue, list) else []:
        candidate = _coerce_dict(contradiction)
        raw_category = _normalize_text(candidate.get("category") or candidate.get("type") or "").lower()
        if not raw_category.startswith("temporal"):
            continue
        # Normalise to the canonical category expected by rule profiles.
        category = _TEMPORAL_ISSUE_CATEGORY_ALIASES.get(raw_category, raw_category)
        issue_id = _normalize_text(candidate.get("contradiction_id") or candidate.get("dependency_id") or "")
        issue_id = issue_id or f"temporal_issue:{category}:{len(registry) + 1}"
        if issue_id in seen_issue_ids:
            continue
        seen_issue_ids.add(issue_id)
        registry.append(
            {
                "issue_id": issue_id,
                "registry_version": "temporal_issue_registry.v1",
                "issue_type": category,
                "category": category,
                "summary": _normalize_text(candidate.get("summary") or candidate.get("topic") or category),
                "severity": _normalize_text(candidate.get("severity") or "important").lower() or "important",
                "blocking": _normalize_text(candidate.get("severity") or "").lower() == "blocking",
                "recommended_resolution_lane": _normalize_text(
                    candidate.get("recommended_resolution_lane") or "clarify_with_complainant"
                ).lower() or "clarify_with_complainant",
                "fact_ids": _unique_normalized_strings(candidate.get("fact_ids") or []),
                "claim_types": _unique_normalized_strings(
                    candidate.get("affected_claim_types") or candidate.get("claim_types") or []
                ),
                "element_tags": _unique_normalized_strings(
                    candidate.get("affected_element_ids") or candidate.get("element_tags") or []
                ),
                "left_node_name": _normalize_text(candidate.get("left_node_name") or "") or None,
                "right_node_name": _normalize_text(candidate.get("right_node_name") or "") or None,
                "status": _normalize_text(candidate.get("current_resolution_status") or candidate.get("status") or "open").lower() or "open",
                "current_resolution_status": _normalize_text(candidate.get("current_resolution_status") or candidate.get("status") or "open").lower() or "open",
                "missing_temporal_predicates": _unique_normalized_strings(candidate.get("missing_temporal_predicates") or [])
                or _derive_temporal_issue_missing_predicates(category, candidate.get("fact_ids") or []),
                "required_provenance_kinds": _unique_normalized_strings(candidate.get("required_provenance_kinds") or [])
                or _derive_temporal_issue_required_provenance_kinds(
                    category,
                    candidate.get("recommended_resolution_lane") or "clarify_with_complainant",
                ),
                "source_kind": "contradiction_queue",
                "source_ref": _normalize_text(candidate.get("contradiction_id") or candidate.get("dependency_id") or "") or None,
                "inference_mode": "imported_temporal_contradiction",
            }
        )

    return registry
def build_claim_temporal_graphs(
    temporal_fact_registry: List[Dict[str, Any]],
    temporal_relation_registry: List[Dict[str, Any]],
    temporal_issue_registry: List[Dict[str, Any]],
    candidate_claims: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Assemble deterministic claim and element temporal partial-order graphs.

    The graph is intentionally derived from the canonical temporal registries so
    packet readiness, proof bundles, and review payloads can all trace back to the
    same fact/relation/issue IDs.
    """
    facts = [
        _coerce_dict(fact)
        for fact in (temporal_fact_registry if isinstance(temporal_fact_registry, list) else [])
        if isinstance(fact, dict)
    ]
    relations = [
        _coerce_dict(relation)
        for relation in (temporal_relation_registry if isinstance(temporal_relation_registry, list) else [])
        if isinstance(relation, dict)
    ]
    issues = [
        _coerce_dict(issue)
        for issue in (temporal_issue_registry if isinstance(temporal_issue_registry, list) else [])
        if isinstance(issue, dict)
    ]
    facts_by_id = {
        _normalize_text(fact.get("fact_id") or fact.get("temporal_fact_id") or ""): fact
        for fact in facts
        if _normalize_text(fact.get("fact_id") or fact.get("temporal_fact_id") or "")
    }

    claim_labels_by_key: Dict[str, str] = {}
    for claim in candidate_claims if isinstance(candidate_claims, list) else []:
        if not isinstance(claim, dict):
            continue
        label = _normalize_text(claim.get("claim_type") or claim.get("label") or claim.get("claim_id") or "")
        key = _normalize_scope_key(label)
        if key:
            claim_labels_by_key.setdefault(key, label)
    for record in [*facts, *relations, *issues]:
        for claim_key in _temporal_record_claim_keys(record):
            claim_labels_by_key.setdefault(claim_key, claim_key)
    if not claim_labels_by_key and facts:
        claim_labels_by_key["unscoped_claim"] = "unscoped_claim"

    single_claim_key = next(iter(claim_labels_by_key)) if len(claim_labels_by_key) == 1 else ""
    claim_graphs: Dict[str, Dict[str, Any]] = {}
    aggregate_fact_ids: List[str] = []
    aggregate_relation_ids: List[str] = []
    aggregate_issue_ids: List[str] = []

    for claim_key in sorted(claim_labels_by_key):
        claim_type = claim_labels_by_key[claim_key]
        selected_fact_ids = {
            _normalize_text(fact.get("fact_id") or fact.get("temporal_fact_id") or "")
            for fact in facts
            if (
                claim_key in _temporal_record_claim_keys(fact)
                or (single_claim_key == claim_key and not _temporal_record_claim_keys(fact))
            )
            and _normalize_text(fact.get("fact_id") or fact.get("temporal_fact_id") or "")
        }
        selected_relations: List[Dict[str, Any]] = []
        for relation in relations:
            relation_claim_keys = _temporal_record_claim_keys(relation)
            source_fact_id = _normalize_text(relation.get("source_fact_id") or relation.get("source_temporal_fact_id") or "")
            target_fact_id = _normalize_text(relation.get("target_fact_id") or relation.get("target_temporal_fact_id") or "")
            relation_matches_claim = claim_key in relation_claim_keys or (single_claim_key == claim_key and not relation_claim_keys)
            relation_touches_claim_fact = bool(selected_fact_ids & {source_fact_id, target_fact_id})
            if relation_matches_claim or relation_touches_claim_fact:
                selected_relations.append(relation)
                if source_fact_id:
                    selected_fact_ids.add(source_fact_id)
                if target_fact_id:
                    selected_fact_ids.add(target_fact_id)

        selected_facts = [
            facts_by_id[fact_id]
            for fact_id in sorted(selected_fact_ids)
            if fact_id in facts_by_id
        ]
        selected_fact_labels = {
            _normalize_text(fact.get("text") or fact.get("event_label") or "").lower()
            for fact in selected_facts
            if _normalize_text(fact.get("text") or fact.get("event_label") or "")
        }
        selected_issues: List[Dict[str, Any]] = []
        for issue in issues:
            issue_claim_keys = _temporal_record_claim_keys(issue)
            issue_fact_ids = {
                _normalize_text(fact_id)
                for fact_id in _coerce_list(issue.get("fact_ids"))
                if _normalize_text(fact_id)
            }
            issue_node_labels = {
                _normalize_text(issue.get("left_node_name") or "").lower(),
                _normalize_text(issue.get("right_node_name") or "").lower(),
            }
            issue_node_labels.discard("")
            issue_matches_claim = claim_key in issue_claim_keys or (single_claim_key == claim_key and not issue_claim_keys)
            if (
                issue_matches_claim
                or (issue_fact_ids and bool(issue_fact_ids & selected_fact_ids))
                or (issue_node_labels and bool(issue_node_labels & selected_fact_labels))
            ):
                selected_issues.append(issue)

        element_keys: Dict[str, str] = {}
        for record in [*selected_facts, *selected_relations, *selected_issues]:
            for element_key in _temporal_record_element_keys(record):
                element_keys.setdefault(element_key, element_key)

        element_graphs: Dict[str, Dict[str, Any]] = {}
        for element_key in sorted(element_keys):
            element_seed_fact_ids = {
                _normalize_text(fact.get("fact_id") or fact.get("temporal_fact_id") or "")
                for fact in selected_facts
                if element_key in _temporal_record_element_keys(fact)
                and _normalize_text(fact.get("fact_id") or fact.get("temporal_fact_id") or "")
            }
            element_relations: List[Dict[str, Any]] = []
            for relation in selected_relations:
                source_fact_id = _normalize_text(relation.get("source_fact_id") or relation.get("source_temporal_fact_id") or "")
                target_fact_id = _normalize_text(relation.get("target_fact_id") or relation.get("target_temporal_fact_id") or "")
                if element_key in _temporal_record_element_keys(relation) or element_seed_fact_ids & {source_fact_id, target_fact_id}:
                    element_relations.append(relation)
                    if source_fact_id:
                        element_seed_fact_ids.add(source_fact_id)
                    if target_fact_id:
                        element_seed_fact_ids.add(target_fact_id)
            element_facts = [
                facts_by_id[fact_id]
                for fact_id in sorted(element_seed_fact_ids)
                if fact_id in facts_by_id
            ]
            element_fact_labels = {
                _normalize_text(fact.get("text") or fact.get("event_label") or "").lower()
                for fact in element_facts
                if _normalize_text(fact.get("text") or fact.get("event_label") or "")
            }
            element_issues = []
            for issue in selected_issues:
                issue_fact_ids = {
                    _normalize_text(fact_id)
                    for fact_id in _coerce_list(issue.get("fact_ids"))
                    if _normalize_text(fact_id)
                }
                issue_node_labels = {
                    _normalize_text(issue.get("left_node_name") or "").lower(),
                    _normalize_text(issue.get("right_node_name") or "").lower(),
                }
                issue_node_labels.discard("")
                if (
                    element_key in _temporal_record_element_keys(issue)
                    or (issue_fact_ids and bool(issue_fact_ids & element_seed_fact_ids))
                    or (issue_node_labels and bool(issue_node_labels & element_fact_labels))
                ):
                    element_issues.append(issue)
            if not element_facts and not element_relations and not element_issues:
                continue
            element_graphs[element_key] = _build_temporal_graph_record(
                graph_id=f"claim_temporal_graph:{claim_key}:{element_key}",
                claim_type=claim_type,
                element_id=element_key,
                element_label=element_keys[element_key],
                facts=element_facts,
                relations=element_relations,
                issues=element_issues,
            )

        claim_graph = _build_temporal_graph_record(
            graph_id=f"claim_temporal_graph:{claim_key}",
            claim_type=claim_type,
            facts=selected_facts,
            relations=selected_relations,
            issues=selected_issues,
        )
        claim_graph["elements"] = element_graphs
        claim_graphs[claim_key] = claim_graph
        for fact_id in claim_graph.get("fact_ids", []):
            if fact_id not in aggregate_fact_ids:
                aggregate_fact_ids.append(fact_id)
        for relation_id in claim_graph.get("relation_ids", []):
            if relation_id not in aggregate_relation_ids:
                aggregate_relation_ids.append(relation_id)
        for issue_id in claim_graph.get("issue_ids", []):
            if issue_id not in aggregate_issue_ids:
                aggregate_issue_ids.append(issue_id)

    return {
        "contract_version": "claim_temporal_graph_assembly.v1",
        "claim_count": len(claim_graphs),
        "claims": claim_graphs,
        "claim_keys": list(claim_graphs.keys()),
        "fact_ids": aggregate_fact_ids,
        "relation_ids": aggregate_relation_ids,
        "issue_ids": aggregate_issue_ids,
    }
def build_open_items(intake_case_file: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build the unresolved-work queue for the current intake record."""
    case_file = _coerce_dict(intake_case_file)
    sections = _coerce_dict(case_file.get("intake_sections"))
    candidate_claims = _coerce_list(case_file.get("candidate_claims"))
    canonical_facts = _coerce_list(case_file.get("canonical_facts"))
    proof_leads = _coerce_list(case_file.get("proof_leads"))
    timeline_consistency_summary = _coerce_dict(case_file.get("timeline_consistency_summary"))
    temporal_issue_registry = _coerce_list(case_file.get("temporal_issue_registry"))
    source_text = _normalize_text(case_file.get("source_complaint_text") or "").lower()
    contradiction_queue = _coerce_list(case_file.get("contradiction_queue"))
    blocker_follow_up_summary = _coerce_dict(case_file.get("blocker_follow_up_summary"))
    open_item_by_id: Dict[str, Dict[str, Any]] = {}

    blocking_rank = {"blocking": 0, "important": 1}
    support_rank = {"intake_clarification": 0, "testimony": 1, "evidence": 2, "manual_review": 3}
    strategy_rank = {
        "capture_hearing_timeline": 0,
        "capture_appeal_rights_timeline": 1,
        "capture_response_timeline": 2,
        "capture_staff_identity": 3,
        "capture_causation_sequence": 4,
        "capture_exact_date_for_timeline_fact": 5,
        "anchor_relative_timeline_fact": 6,
        "capture_policy_document_evidence": 7,
        "capture_file_evidence": 8,
        "targeted_blocker_follow_up": 9,
        "satisfy_claim_element": 10,
    }
    kind_rank = {
        "blocker_follow_up": 0,
        "timeline_anchor_gap": 1,
        "anchor_gap": 2,
        "temporal_issue_gap": 3,
        "claim_element_gap": 4,
        "contradiction": 5,
        "evidence_modality_gap": 6,
        "section_gap": 7,
    }

    def _sort_key(item: Dict[str, Any]) -> tuple[int, int, int, int, str]:
        return (
            blocking_rank.get(_normalize_text(item.get("blocking_level") or "").lower(), 2),
            kind_rank.get(_normalize_text(item.get("kind") or "").lower(), 50),
            strategy_rank.get(_normalize_text(item.get("next_question_strategy") or "").lower(), 50),
            support_rank.get(_normalize_text(item.get("recommended_support_kind") or "").lower(), 10),
            _normalize_text(item.get("open_item_id") or ""),
        )

    def _add_item(item: Dict[str, Any]) -> None:
        normalized_id = _normalize_text(item.get("open_item_id") or "")
        if not normalized_id:
            return
        target_claim_type = _normalize_text(item.get("target_claim_type") or "")
        target_element_id = _normalize_text(item.get("target_element_id") or "")
        evidence_classes = _unique_normalized_strings(item.get("evidence_classes") or [])
        # Build target_element_metadata: look up the matching element in candidate_claims so the
        # caller gets a richer object with label, blocking status, and evidence classes.
        resolved_element_metadata: Dict[str, Any] = {}
        if target_element_id and target_claim_type:
            for claim in candidate_claims:
                if not isinstance(claim, dict):
                    continue
                if _normalize_text(str(claim.get("claim_type") or "")).lower() != target_claim_type.lower():
                    continue
                for element in (claim.get("required_elements") or []):
                    if not isinstance(element, dict):
                        continue
                    if _normalize_text(str(element.get("element_id") or "")).lower() == target_element_id.lower():
                        resolved_element_metadata = {
                            "element_id": _normalize_text(str(element.get("element_id") or "")),
                            "label": _normalize_text(str(element.get("label") or element.get("element_id") or "")),
                            "blocking": bool(element.get("blocking", True)),
                            "evidence_classes": _unique_normalized_strings(
                                evidence_classes + list(element.get("evidence_classes") or [])
                            ),
                            "claim_type": target_claim_type,
                        }
                        break
                if resolved_element_metadata:
                    break
        if not resolved_element_metadata and target_element_id:
            resolved_element_metadata = {
                "element_id": target_element_id,
                "label": target_element_id,
                "claim_type": target_claim_type,
                "evidence_classes": evidence_classes,
            }
        normalized_item = {
            **item,
            "open_item_id": normalized_id,
            "kind": _normalize_text(item.get("kind") or "gap").lower() or "gap",
            "status": "open",
            "blocking_level": _normalize_text(item.get("blocking_level") or "important").lower() or "important",
            "section": _normalize_text(item.get("section") or "general").lower() or "general",
            "reason": _normalize_text(item.get("reason") or "Follow-up required."),
            "target_claim_type": target_claim_type,
            "target_element_id": target_element_id,
            "target_claim_types": [target_claim_type] if target_claim_type else [],
            "target_element_ids": [target_element_id] if target_element_id else [],
            "target_element_metadata": resolved_element_metadata,
            "element_links": _normalize_intake_target_links(
                item.get("element_links"),
                claim_types=[target_claim_type] if target_claim_type else [],
                element_ids=[target_element_id] if target_element_id else [],
            ),
            "next_question_strategy": _normalize_text(item.get("next_question_strategy") or "targeted_blocker_follow_up").lower() or "targeted_blocker_follow_up",
            "recommended_support_kind": _normalize_text(item.get("recommended_support_kind") or "intake_clarification").lower() or "intake_clarification",
            "proof_path_status": _normalize_text(item.get("proof_path_status") or "missing").lower() or "missing",
        }
        existing = open_item_by_id.get(normalized_id)
        if existing is None or _sort_key(normalized_item) < _sort_key(existing):
            open_item_by_id[normalized_id] = normalized_item

    normalized_facts = [
        _normalize_canonical_fact_record(fact)
        for fact in canonical_facts
        if isinstance(fact, dict)
    ]
    fact_texts: List[str] = []
    hearing_fact_ids = set()
    hearing_dated_fact_ids = set()
    response_dated_fact_ids = set()
    staff_title_pattern = re.compile(r"\b(manager|supervisor|director|officer|specialist|coordinator|landlord|owner|hr)\b", flags=re.IGNORECASE)
    has_named_staff = _looks_like_staff_person_name(case_file.get("source_complaint_text") or "")
    has_staff_title = bool(staff_title_pattern.search(case_file.get("source_complaint_text") or ""))
    has_causation_sequence = _has_retaliation_causation_link(candidate_claims, normalized_facts, source_text)

    for index, fact in enumerate(normalized_facts, start=1):
        fact_dict = _coerce_dict(fact)
        fact_id = _normalize_text(fact_dict.get("fact_id") or "") or f"timeline_fact_{index}"
        text_value = _normalize_text(fact_dict.get("text") or fact_dict.get("event_label") or "").lower()
        predicate_family = _normalize_text(fact_dict.get("predicate_family") or "").lower()
        temporal_context = _coerce_dict(fact_dict.get("temporal_context"))
        start_date = _normalize_text(temporal_context.get("start_date") or "")
        fact_texts.append(text_value)
        if any(token in text_value for token in ("grievance", "hearing", "appeal")) or predicate_family == "hearing_process":
            hearing_fact_ids.add(fact_id)
            if start_date:
                hearing_dated_fact_ids.add(fact_id)
        if predicate_family == "response_timeline" or any(token in text_value for token in ("respond", "denied", "approved", "ignored", "no response", "decision")):
            if start_date:
                response_dated_fact_ids.add(fact_id)
        if _looks_like_staff_person_name(_normalize_text(fact_dict.get("text") or fact_dict.get("event_label") or "")):
            has_named_staff = True
        if staff_title_pattern.search(_normalize_text(fact_dict.get("text") or fact_dict.get("event_label") or "")):
            has_staff_title = True

    legal_context = case_file.get("legal_context")
    if not isinstance(legal_context, dict):
        legal_context = refresh_explicit_legal_context(case_file)
        case_file["legal_context"] = legal_context
    for question in _coerce_list(legal_context.get("questions")):
        question_dict = _coerce_dict(question)
        question_id = _normalize_text(question_dict.get("question_id") or "")
        if not question_id:
            continue
        _add_item(
            {
                "open_item_id": f"legal_context:{question_id}",
                "kind": "legal_context_gap",
                "blocking_level": "blocking" if question_dict.get("field") == "jurisdiction" else "important",
                "section": "legal_context",
                "reason": _normalize_text(question_dict.get("prompt") or "Legal context is unresolved."),
                "next_question_strategy": f"ask_{_normalize_text(question_dict.get('field') or 'legal_context')}",
                "recommended_support_kind": "intake_clarification",
                "proof_path_status": "missing",
                "question": question_dict,
            }
        )

    for claim in candidate_claims:
        claim_dict = _coerce_dict(claim)
        claim_type = _normalize_text(claim_dict.get("claim_type"))
        claim_label = _normalize_text(claim_dict.get("label") or claim_type)
        for element in _coerce_list(claim_dict.get("required_elements")):
            element_dict = _coerce_dict(element)
            if _normalize_text(element_dict.get("status")).lower() == "present":
                continue
            element_id = _normalize_text(element_dict.get("element_id"))
            element_label = _normalize_text(element_dict.get("label") or element_id)
            evidence_classes = list(element_dict.get("evidence_classes", []) or [])
            next_strategy = "satisfy_claim_element"
            if element_id in {"grievance_hearing", "hearing_request_timing"}:
                next_strategy = "capture_hearing_timeline"
            elif element_id in {"appeal_rights", "appeal_timing"}:
                next_strategy = "capture_appeal_rights_timeline"
            elif element_id in {"causation", "retaliation_causation_sequence"}:
                next_strategy = "capture_causation_sequence"
            _add_item(
                {
                    "open_item_id": f"element:{claim_type}:{element_id}",
                    "kind": "claim_element_gap",
                    "blocking_level": "blocking" if bool(element_dict.get("blocking", False)) else "important",
                    "section": "claim_elements",
                    "reason": f"{claim_label} is still missing {element_label}.",
                    "target_claim_type": claim_type,
                    "target_element_id": element_id,
                    "next_question_strategy": next_strategy,
                    "evidence_classes": evidence_classes,
                    "recommended_support_kind": "testimony" if any("testimony" in str(item).lower() for item in evidence_classes) else "evidence",
                    "proof_path_status": "missing",
                }
            )

    for contradiction in contradiction_queue:
        contradiction_dict = _coerce_dict(contradiction)
        if _normalize_text(contradiction_dict.get("status") or "open").lower() == "resolved":
            continue
        contradiction_id = _normalize_text(contradiction_dict.get("contradiction_id") or "contradiction")
        resolution_lane = _normalize_text(
            contradiction_dict.get("recommended_resolution_lane") or "clarify_with_complainant"
        ).lower() or "clarify_with_complainant"
        external_corroboration_required = bool(contradiction_dict.get("external_corroboration_required", False))
        _add_item(
            {
                "open_item_id": f"contradiction:{contradiction_id}",
                "kind": "contradiction",
                "blocking_level": _normalize_text(contradiction_dict.get("severity") or "important").lower() or "important",
                "section": "contradictions",
                "reason": f"Resolve contradiction about {_normalize_text(contradiction_dict.get('topic') or 'intake contradiction')}.",
                "next_question_strategy": resolution_lane,
                "recommended_support_kind": _contradiction_support_kind(resolution_lane),
                "recommended_resolution_lane": resolution_lane,
                "external_corroboration_required": external_corroboration_required,
                "proof_path_status": "conflicted_external_corroboration_required" if external_corroboration_required else "conflicted",
            }
        )

    for blocker in _coerce_list(blocker_follow_up_summary.get("blocking_items")):
        blocker_dict = _coerce_dict(blocker)
        blocker_id = _normalize_text(blocker_dict.get("blocker_id") or "")
        section = _normalize_text(blocker_dict.get("section") or "chronology").lower() or "chronology"
        _add_item(
            {
                "open_item_id": f"blocker:{blocker_id or len(open_item_by_id) + 1}",
                "kind": "blocker_follow_up",
                "blocking_level": "blocking",
                "section": section,
                "reason": _normalize_text(blocker_dict.get("reason") or "Critical intake blocker requires follow-up."),
                "target_claim_type": _normalize_text(blocker_dict.get("target_claim_type") or ""),
                "target_element_id": _normalize_text(blocker_dict.get("target_element_id") or ""),
                "next_question_strategy": _normalize_text(
                    blocker_dict.get("next_question_strategy")
                    or blocker_dict.get("question_strategy")
                    or "targeted_blocker_follow_up"
                ).lower() or "targeted_blocker_follow_up",
                "recommended_support_kind": _normalize_text(
                    blocker_dict.get("recommended_support_kind")
                    or ("evidence" if section in {"proof_leads", "chronology"} else "intake_clarification")
                ).lower() or "intake_clarification",
                "proof_path_status": _normalize_text(blocker_dict.get("proof_path_status") or "missing").lower() or "missing",
                "blocker_tags": _unique_normalized_strings(blocker_dict.get("blocker_tags") or []),
                "primary_objective": _normalize_text(blocker_dict.get("primary_objective") or ""),
                "blocker_objectives": _unique_normalized_strings(blocker_dict.get("blocker_objectives") or []),
                "extraction_targets": _unique_normalized_strings(blocker_dict.get("extraction_targets") or []),
                "workflow_phases": _unique_normalized_strings(blocker_dict.get("workflow_phases") or []),
                "issue_family": _normalize_text(blocker_dict.get("issue_family") or ""),
            }
        )

    for issue in temporal_issue_registry:
        issue_dict = _coerce_dict(issue)
        issue_status = _normalize_text(
            issue_dict.get("current_resolution_status") or issue_dict.get("status") or "open"
        ).lower()
        if issue_status == "resolved":
            continue
        issue_id = _normalize_text(issue_dict.get("issue_id") or "")
        if not issue_id:
            continue
        issue_type = _normalize_text(issue_dict.get("issue_type") or "").lower()
        resolution_lane = _normalize_text(
            issue_dict.get("recommended_resolution_lane")
            or ("anchor_relative_timeline_fact" if issue_type == "relative_only_ordering" else "capture_exact_date_for_timeline_fact")
        ).lower() or "clarify_with_complainant"
        _add_item(
            {
                "open_item_id": f"temporal_issue:{issue_id}",
                "kind": "temporal_issue_gap",
                "blocking_level": _normalize_text(issue_dict.get("severity") or "blocking").lower() or "blocking",
                "section": "chronology",
                "reason": _normalize_text(issue_dict.get("summary") or "Timeline sequencing still needs anchoring."),
                "next_question_strategy": resolution_lane,
                "recommended_support_kind": _contradiction_support_kind(resolution_lane),
                "proof_path_status": "relative_only" if issue_type == "relative_only_ordering" else "missing",
                "issue_type": issue_type,
                "fact_ids": _unique_normalized_strings(issue_dict.get("fact_ids") or []),
                "relative_markers": _unique_normalized_strings(issue_dict.get("relative_markers") or []),
            }
        )

    missing_temporal_fact_ids = _unique_normalized_strings(
        timeline_consistency_summary.get("missing_temporal_fact_ids") or []
    )
    relative_only_fact_ids = set(
        _unique_normalized_strings(timeline_consistency_summary.get("relative_only_fact_ids") or [])
    )
    for fact_id in missing_temporal_fact_ids:
        is_relative_only = fact_id in relative_only_fact_ids
        _add_item(
            {
                "open_item_id": f"timeline_fact:{fact_id}",
                "kind": "timeline_anchor_gap",
                "blocking_level": "blocking",
                "section": "chronology",
                "reason": (
                    f"Timeline fact {fact_id} only has relative ordering and needs anchoring."
                    if is_relative_only
                    else f"Timeline fact {fact_id} needs an exact date anchor."
                ),
                "next_question_strategy": "anchor_relative_timeline_fact" if is_relative_only else "capture_exact_date_for_timeline_fact",
                "recommended_support_kind": "intake_clarification",
                "proof_path_status": "relative_only" if is_relative_only else "missing",
                "target_fact_id": fact_id,
            }
        )

    weak_claim_types = {"housing_discrimination", "hacc_research_engine"}
    active_weak_claim_types = {
        _normalize_text(_coerce_dict(claim).get("claim_type") or "").lower()
        for claim in candidate_claims
        if isinstance(claim, dict)
    }.intersection(weak_claim_types)
    if active_weak_claim_types:
        lead_texts = [
            f"{_normalize_text(_coerce_dict(lead).get('lead_type') or '').lower()} {_normalize_text(_coerce_dict(lead).get('description') or '').lower()}"
            for lead in proof_leads
            if isinstance(lead, dict)
        ]
        has_policy_document = any(any(token in lead_text for token in ("policy_document", "policy", "handbook", "procedure")) for lead_text in lead_texts)
        has_file_evidence = any(any(token in lead_text for token in ("file_evidence", "file", "attachment", "record", "document")) for lead_text in lead_texts)
        primary_claim_type = sorted(active_weak_claim_types)[0]
        if not has_policy_document:
            _add_item(
                {
                    "open_item_id": "evidence_modality:policy_document",
                    "kind": "evidence_modality_gap",
                    "blocking_level": "important",
                    "section": "proof_leads",
                    "reason": "Add a policy_document source with policy language, issue date, and issuing authority.",
                    "target_claim_type": primary_claim_type,
                    "next_question_strategy": "capture_policy_document_evidence",
                    "recommended_support_kind": "evidence",
                    "proof_path_status": "missing",
                }
            )
        if not has_file_evidence:
            _add_item(
                {
                    "open_item_id": "evidence_modality:file_evidence",
                    "kind": "evidence_modality_gap",
                    "blocking_level": "important",
                    "section": "proof_leads",
                    "reason": "Add file_evidence records with document title, date, source, and custodian details.",
                    "target_claim_type": primary_claim_type,
                    "next_question_strategy": "capture_file_evidence",
                    "recommended_support_kind": "evidence",
                    "proof_path_status": "missing",
                }
            )

    hearing_referenced = (
        any(token in source_text for token in ("grievance hearing", "hearing request", "hearing", "appeal"))
        or any(any(token in text for token in ("grievance", "hearing", "appeal")) for text in fact_texts)
    )
    if hearing_referenced and not hearing_dated_fact_ids:
        _add_item(
            {
                "open_item_id": "anchor:grievance_hearing",
                "kind": "anchor_gap",
                "blocking_level": "blocking",
                "section": "chronology",
                "reason": "Confirm grievance_hearing request date, request method, decision-maker name/title, and source record.",
                "target_element_id": "grievance_hearing",
                "next_question_strategy": "capture_hearing_timeline",
                "recommended_support_kind": "intake_clarification",
                "proof_path_status": "missing",
            }
        )
    if hearing_referenced and not response_dated_fact_ids:
        _add_item(
            {
                "open_item_id": "anchor:appeal_rights",
                "kind": "anchor_gap",
                "blocking_level": "blocking",
                "section": "chronology",
                "reason": "Confirm appeal_rights notice date, filing deadline, agency response date, and supporting record.",
                "target_element_id": "appeal_rights",
                "next_question_strategy": "capture_appeal_rights_timeline",
                "recommended_support_kind": "intake_clarification",
                "proof_path_status": "missing",
            }
        )

    if has_named_staff and not has_staff_title:
        _add_item(
            {
                "open_item_id": "actors:staff_name_title_mapping",
                "kind": "anchor_gap",
                "blocking_level": "blocking",
                "section": "actors",
                "reason": "Map each named staff person to role/title and decision authority.",
                "next_question_strategy": "capture_staff_identity",
                "recommended_support_kind": "intake_clarification",
                "proof_path_status": "missing",
            }
        )

    if not has_causation_sequence:
        _add_item(
            {
                "open_item_id": "conduct:causation_sequence",
                "kind": "anchor_gap",
                "blocking_level": "blocking",
                "section": "conduct",
                "reason": "Capture sequence linking protected activity, actor knowledge, adverse action, and timing.",
                "next_question_strategy": "capture_causation_sequence",
                "recommended_support_kind": "intake_clarification",
                "proof_path_status": "missing",
            }
        )

    section_strategy_map = {
        "chronology": "fill_chronology_with_exact_dates",
        "actors": "fill_actors_and_titles",
        "conduct": "fill_conduct_and_causation_sequence",
        "claim_elements": "satisfy_claim_element",
        "proof_leads": "fill_evidence_paths",
    }
    concrete_sections = {
        _normalize_text(item.get("section") or "").lower()
        for item in open_item_by_id.values()
        if _normalize_text(item.get("kind") or "").lower() != "section_gap"
    }
    for section_name, section in sections.items():
        normalized_section_name = _normalize_text(section_name).lower()
        section_dict = _coerce_dict(section)
        status = _normalize_text(section_dict.get("status")).lower() or "missing"
        if status == "complete" or normalized_section_name in concrete_sections:
            continue
        missing_items = _coerce_list(section_dict.get("missing_items"))
        _add_item(
            {
                "open_item_id": f"section:{normalized_section_name}",
                "kind": "section_gap",
                "blocking_level": "blocking" if normalized_section_name in {"chronology", "actors", "conduct", "claim_elements"} else "important",
                "section": normalized_section_name,
                "reason": "; ".join(missing_items) or f"{normalized_section_name} is incomplete",
                "next_question_strategy": section_strategy_map.get(normalized_section_name, f"fill_{normalized_section_name}"),
                "recommended_support_kind": "evidence" if normalized_section_name == "proof_leads" else "intake_clarification",
                "proof_path_status": "missing",
            }
        )

    deduped_items = list(open_item_by_id.values())
    deduped_items.sort(key=_sort_key)
    return deduped_items
def build_blocker_follow_up_summary(
    *,
    candidate_claims: List[Dict[str, Any]],
    canonical_facts: List[Dict[str, Any]],
    proof_leads: List[Dict[str, Any]],
    source_text: str,
) -> Dict[str, Any]:
    """Build explicit follow-up blockers for intake questioning and document generation."""
    facts = [_normalize_canonical_fact_record(item) for item in canonical_facts if isinstance(item, dict)]
    leads = [_normalize_proof_lead_record(item) for item in proof_leads if isinstance(item, dict)]
    full_text = _normalize_text(source_text).lower()

    def _fact_text(fact: Dict[str, Any]) -> str:
        return _normalize_text(fact.get("text") or fact.get("event_label") or "").lower()

    def _has_day_level_date(value: str) -> bool:
        return bool(
            re.search(
                (
                    r"\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|"
                    r"sep|sept|september|oct|october|nov|november|dec|december)\s+\d{1,2},\s+\d{4}\b"
                    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
                    r"|\b\d{4}-\d{2}-\d{2}\b"
                ),
                value or "",
                flags=re.IGNORECASE,
            )
        )

    def _has_structured_artifact_backed_sequence(fact: Dict[str, Any], families: set[str], tokens: tuple[str, ...]) -> bool:
        predicate_family = _normalize_text(fact.get("predicate_family") or "").lower()
        text_value = _fact_text(fact)
        structured_group = _normalize_text(fact.get("structured_timeline_group") or "")
        sequence_index = fact.get("sequence_index")
        source_artifact_ids = _unique_normalized_strings(fact.get("source_artifact_ids") or [])
        event_support_refs = _unique_normalized_strings(fact.get("event_support_refs") or [])
        return bool(
            structured_group
            and isinstance(sequence_index, int)
            and (predicate_family in families or any(token in text_value for token in tokens))
            and (source_artifact_ids or event_support_refs)
        )

    blocking_items: List[Dict[str, Any]] = []
    seen_ids = set()

    def _add_blocker(blocker: Dict[str, Any]) -> None:
        blocker_id = _normalize_text(blocker.get("blocker_id") or "")
        if not blocker_id or blocker_id in seen_ids:
            return
        seen_ids.add(blocker_id)
        blocking_items.append(blocker)

    has_notice_reference = any(token in full_text for token in ("notice", "letter", "email", "message"))
    notice_lead_present = any(
        any(token in _normalize_text(lead.get("description") or "").lower() for token in ("notice", "letter", "email", "message"))
        for lead in leads
    )
    if has_notice_reference and not notice_lead_present:
        _add_blocker(
            _build_blocker_record("missing_written_notice_chain", {
                "blocker_id": "missing_written_notice_chain",
                "section": "proof_leads",
                "reason": "Written notice chain is referenced but the sending party/date/source artifact is still missing.",
                "next_question_strategy": "capture_notice_chain",
                "recommended_support_kind": "evidence",
                "proof_path_status": "missing",
                "blocker_tags": ["notice_chain", "exact_dates"],
            })
        )

    hearing_reference = any(token in full_text for token in ("hearing", "appeal", "grievance"))
    hearing_facts = [fact for fact in facts if any(token in _fact_text(fact) for token in ("hearing", "appeal", "grievance"))]
    hearing_has_date = any(
        _has_day_level_date(_normalize_text(fact.get("event_date_or_range") or ""))
        or bool(_coerce_dict(fact.get("temporal_context")).get("start_date"))
        for fact in hearing_facts
    )
    hearing_has_structured_sequence_support = any(
        _has_structured_artifact_backed_sequence(fact, {"hearing_process"}, ("hearing", "appeal", "grievance", "review"))
        for fact in hearing_facts
    )
    if hearing_reference and not hearing_has_date and not hearing_has_structured_sequence_support:
        _add_blocker(
            _build_blocker_record("missing_hearing_request_timing", {
                "blocker_id": "missing_hearing_request_timing",
                "section": "chronology",
                "reason": "Hearing/appeal request timing is missing day-level anchors.",
                "next_question_strategy": "capture_hearing_timeline",
                "recommended_support_kind": "intake_clarification",
                "proof_path_status": "missing",
                "blocker_tags": ["exact_dates", "hearing_timeline"],
            })
        )

    response_reference = any(token in full_text for token in ("response", "responded", "replied", "denied", "approved", "ignored", "no response"))
    response_facts = [fact for fact in facts if any(token in _fact_text(fact) for token in ("response", "responded", "replied", "denied", "approved", "ignored"))]
    response_has_date = any(
        _has_day_level_date(_normalize_text(fact.get("event_date_or_range") or ""))
        or bool(_coerce_dict(fact.get("temporal_context")).get("start_date"))
        for fact in response_facts
    )
    response_has_structured_sequence_support = any(
        _has_structured_artifact_backed_sequence(fact, {"response_timeline"}, ("response", "responded", "replied", "denied", "approved", "ignored"))
        for fact in response_facts
    )
    if response_reference and not response_has_date and not response_has_structured_sequence_support:
        _add_blocker(
            _build_blocker_record("missing_response_timing", {
                "blocker_id": "missing_response_timing",
                "section": "chronology",
                "reason": "Response or non-response events are described without date anchors.",
                "next_question_strategy": "capture_response_timeline",
                "recommended_support_kind": "intake_clarification",
                "proof_path_status": "missing",
                "blocker_tags": ["exact_dates", "response_timeline"],
            })
        )

    has_named_staff = _looks_like_staff_person_name(source_text or "") or any(
        _looks_like_staff_person_name(fact.get("text") or fact.get("event_label") or "")
        for fact in facts
    )
    has_staff_title = bool(
        re.search(r"\b(manager|supervisor|director|officer|specialist|landlord|owner|hr)\b", full_text)
    )
    if has_named_staff and not has_staff_title:
        _add_blocker(
            _build_blocker_record("missing_staff_name_title_mapping", {
                "blocker_id": "missing_staff_name_title_mapping",
                "section": "actors",
                "reason": "Named staff are present but title/role mapping is incomplete.",
                "next_question_strategy": "capture_staff_identity",
                "recommended_support_kind": "intake_clarification",
                "proof_path_status": "missing",
                "blocker_tags": ["staff_identity"],
            })
        )

    retaliation_claim = any(
        _normalize_text(_coerce_dict(claim).get("claim_type") or "").lower() == "retaliation"
        for claim in candidate_claims if isinstance(candidate_claims, list)
    )
    if retaliation_claim:
        protected_present = any(
            "protected activity" in _fact_text(fact)
            or "complain" in _fact_text(fact)
            or "reported" in _fact_text(fact)
            or _normalize_text(fact.get("predicate_family") or "").lower() == "protected_activity"
            for fact in facts
        ) or any(token in full_text for token in ("protected activity", "complained", "reported", "grievance"))
        adverse_present = any(
            any(token in _fact_text(fact) for token in ("fired", "terminated", "demoted", "disciplined", "evicted", "reduced hours", "cut hours"))
            or _normalize_text(fact.get("predicate_family") or "").lower() == "adverse_action"
            for fact in facts
        ) or any(token in full_text for token in ("fired", "terminated", "demoted", "disciplined", "evicted", "reduced hours", "cut hours"))
        causation_connector = any(
            any(token in _fact_text(fact) for token in ("because", "after", "soon after", "in response to", "due to"))
            or _normalize_text(fact.get("predicate_family") or "").lower() == "causation"
            for fact in facts
        ) or any(token in full_text for token in ("because", "after", "soon after", "in response to", "due to"))
        if not (protected_present and adverse_present and causation_connector):
            _add_blocker(
                _build_blocker_record("missing_retaliation_causation_sequence", {
                    "blocker_id": "missing_retaliation_causation_sequence",
                    "section": "conduct",
                    "reason": "Retaliation theory still lacks protected-activity to adverse-action sequencing and causation links.",
                    "next_question_strategy": "capture_retaliation_sequence",
                    "recommended_support_kind": "intake_clarification",
                    "proof_path_status": "missing",
                    "blocker_tags": ["retaliation_sequence", "exact_dates", "staff_identity"],
                })
            )

    summary_objectives = _unique_metadata_strings([
        objective
        for blocker in blocking_items
        for objective in _coerce_list(_coerce_dict(blocker).get("blocker_objectives"))
    ])
    summary_targets = _unique_metadata_strings([
        target
        for blocker in blocking_items
        for target in _coerce_list(_coerce_dict(blocker).get("extraction_targets"))
    ])
    summary_phases = _unique_metadata_strings([
        phase
        for blocker in blocking_items
        for phase in _coerce_list(_coerce_dict(blocker).get("workflow_phases"))
    ])
    return {
        "blocking_items": blocking_items,
        "blocking_item_count": len(blocking_items),
        "blocking_objectives": summary_objectives,
        "extraction_targets": summary_targets,
        "workflow_phases": summary_phases,
    }
