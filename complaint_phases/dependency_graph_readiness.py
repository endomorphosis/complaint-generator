"""Claim readiness and blocker follow-up delegated from the dependency graph."""

from __future__ import annotations

from complaint_phases.dependency_graph import (
    Any,
    Dependency,
    DependencyGraph,
    DependencyNode,
    DependencyType,
    Dict,
    List,
    NodeType,
    Optional,
    _ACTOR_CRITIC_FOCUS_METRICS,
    _ACTOR_CRITIC_PHASE_FOCUS_ORDER,
    _ACTOR_CRITIC_PRIORITY,
    _ACTOR_CRITIC_WEAK_CLAIM_TYPES,
    _ACTOR_CRITIC_WEAK_EVIDENCE_MODALITIES,
    _CONFIRMATION_PLACEHOLDER_PATTERN,
    _DATE_TOKEN_PATTERN,
    _LEGALLY_SOURCED_CLASS,
    _NAME_PATTERN,
    _utc_now_isoformat,
    deepcopy,
    logger,
    re,
)

def get_claim_readiness(self) -> Dict[str, Any]:
    """
    Assess overall readiness of all claims.

    Returns summary of which claims are ready to file and which need work.
    """
    def _normalize_key_fragment(value: Any) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        return normalized

    def _as_text(value: Any) -> str:
        return str(value or "").strip()

    def _is_unspecified_value(value: Any) -> bool:
        text = _as_text(value)
        if not text:
            return True
        return bool(_CONFIRMATION_PLACEHOLDER_PATTERN.search(text))

    def _contains_name(text: str) -> bool:
        if not text:
            return False
        if _NAME_PATTERN.search(text):
            return True
        if any(token in text.lower() for token in {"manager", "director", "officer", "agent", "supervisor"}):
            return True
        return False

    def _contains_date_token(text: str) -> bool:
        if not text:
            return False
        return bool(_DATE_TOKEN_PATTERN.search(text))

    def _core_structured_gap(gap_type: str) -> bool:
        return gap_type in {
            "missing_exact_action_dates",
            "missing_hearing_request_date",
            "missing_response_dates",
            "missing_hearing_timing",
            "missing_staff_identity",
            "missing_staff_title",
            "retaliation_missing_causation_link",
            "retaliation_missing_causation",
            "retaliation_missing_sequencing_dates",
            "retaliation_missing_sequence",
            "missing_decision_timeline",
        }

    def _infer_gap_type(
        claim_type: str,
        source_name: str,
        source_description: str,
        source_attrs: Dict[str, Any],
        requirement_key: str,
        evidence_modality: str,
    ) -> str:
        explicit = _as_text(source_attrs.get("gap_type")).lower()
        if explicit:
            return explicit
        corpus = " ".join(
            [
                claim_type,
                source_name,
                source_description,
                requirement_key,
                _as_text(source_attrs.get("requirement_label")),
                _as_text(source_attrs.get("question_hint")),
            ]
        ).lower()
        if "hearing request" in corpus and "date" in corpus:
            return "missing_hearing_request_date"
        if "hearing" in corpus and any(token in corpus for token in {"timing", "deadline", "within", "days", "date"}):
            return "missing_hearing_timing"
        if any(token in corpus for token in {"response date", "response timing", "reply date", "date of response", "responded on"}):
            return "missing_response_dates"
        if "written notice" in corpus or ("notice" in corpus and "written" in corpus):
            return "missing_written_notice"
        if any(token in corpus for token in {"staff name", "decision maker", "who denied", "who approved", "who decided", "responsible staff", "manager name", "director name"}):
            return "missing_staff_identity"
        if any(token in corpus for token in {"staff title", "job title", "position title", "role of"}):
            return "missing_staff_title"
        if "retaliat" in corpus and any(token in corpus for token in {"causation", "because", "in response to", "motivated by"}):
            return "retaliation_missing_causation_link"
        if "retaliat" in corpus and any(token in corpus for token in {"sequence", "timeline", "before", "after", "chronology"}):
            return "retaliation_missing_sequencing_dates"
        if any(token in corpus for token in {"timeline", "chronology", "date", "dated", "when", "before", "after"}):
            return "missing_exact_action_dates"
        if evidence_modality == "policy_document":
            return "missing_written_notice"
        if evidence_modality == "file_evidence":
            return "missing_response_dates"
        return "missing_claim_element"

    def _required_fields_for_gap(gap_type: str) -> List[str]:
        mapping = {
            "missing_exact_action_dates": ["event_date", "adverse_action"],
            "missing_hearing_request_date": ["hearing_request_date", "hearing_request_actor"],
            "missing_response_dates": ["response_date", "response_actor"],
            "missing_hearing_timing": ["adverse_action_date", "hearing_request_date"],
            "missing_staff_identity": ["staff_name", "staff_role"],
            "missing_staff_title": ["staff_name", "staff_title"],
            "retaliation_missing_causation": ["protected_activity", "adverse_action", "causation_link"],
            "retaliation_missing_causation_link": ["protected_activity", "adverse_action", "causation_link"],
            "retaliation_missing_sequence": ["protected_activity_date", "adverse_action_date"],
            "retaliation_missing_sequencing_dates": ["protected_activity_date", "adverse_action_date"],
            "missing_written_notice": ["document_name", "document_date", "issuing_actor"],
            "missing_decision_timeline": ["decision_date", "decision_actor"],
            "missing_claim_element": ["supporting_fact"],
        }
        return list(mapping.get(gap_type, ["supporting_fact"]))

    def _modality_precision_fields(evidence_modality: str) -> List[str]:
        modality = _as_text(evidence_modality).lower()
        if modality == "policy_document":
            return ["document_name", "document_date", "issuing_actor"]
        if modality == "file_evidence":
            return ["document_name", "document_date", "issuing_actor"]
        return []

    def _field_aliases(field_name: str) -> List[str]:
        aliases = {
            "event_date": ["event_date", "date", "incident_date", "action_date"],
            "adverse_action": ["adverse_action", "action", "decision", "denial_reason"],
            "hearing_request_date": ["hearing_request_date", "appeal_date", "hearing_date_requested"],
            "hearing_request_actor": ["hearing_request_actor", "requestor", "requesting_party"],
            "response_date": ["response_date", "reply_date", "decision_date", "response_timing_date"],
            "response_actor": ["response_actor", "responding_staff", "decision_maker", "staff_name"],
            "adverse_action_date": ["adverse_action_date", "adverse_date", "denial_date", "decision_date"],
            "staff_name": ["staff_name", "decision_maker", "actor_name", "employee_name"],
            "staff_role": ["staff_role", "role", "position", "job_title", "staff_title"],
            "staff_title": ["staff_title", "job_title", "position_title", "title"],
            "protected_activity": ["protected_activity", "complaint_activity", "report_activity"],
            "causation_link": ["causation_link", "causal_statement", "retaliation_link", "motive"],
            "protected_activity_date": ["protected_activity_date", "activity_date", "complaint_date"],
            "document_name": ["document_name", "file_name", "policy_name", "notice_name"],
            "document_date": ["document_date", "notice_date", "file_date", "issued_date"],
            "issuing_actor": ["issuing_actor", "issuer", "author", "issuing_staff"],
            "decision_date": ["decision_date", "adverse_action_date", "response_date"],
            "decision_actor": ["decision_actor", "decision_maker", "staff_name", "actor_name"],
            "supporting_fact": ["supporting_fact", "fact", "detail", "narrative_detail"],
        }
        canonical = str(field_name or "").strip()
        return list(dict.fromkeys([canonical, *aliases.get(canonical, [])]))

    def _ordered_unique(values: List[str]) -> List[str]:
        return list(dict.fromkeys(str(value).strip() for value in values if str(value or "").strip()))

    def _first_value(attrs: Dict[str, Any], keys: List[str]) -> str:
        for key in keys:
            if key in attrs and not _is_unspecified_value(attrs.get(key)):
                return _as_text(attrs.get(key))
        return ""

    def _field_value(attrs: Dict[str, Any], field_name: str) -> str:
        return _first_value(attrs, _field_aliases(field_name))

    def _missing_required_fields(required_fields: List[str], source_attrs: Dict[str, Any]) -> List[str]:
        missing: List[str] = []
        for field_name in required_fields:
            aliases = _field_aliases(field_name)
            if not _first_value(source_attrs, aliases):
                missing.append(field_name)
        return missing

    def _satisfaction_rules_for_gap(gap_type: str, requirement_key: str) -> Dict[str, Any]:
        rules = {
            "satisfy_when": "all_required_fields_present",
            "mark_requirement_keys": [requirement_key] if requirement_key else [],
            "mark_evidence_modalities": [],
            "promote_to_graph_first": [],
            "sequence_checks": [],
        }
        if gap_type in {"missing_exact_action_dates", "missing_hearing_request_date", "missing_response_dates", "missing_hearing_timing", "retaliation_missing_sequence", "retaliation_missing_sequencing_dates", "missing_decision_timeline"}:
            rules["promote_to_graph_first"].append("timeline")
            rules["sequence_checks"].append("validate_chronology")
        if gap_type in {"missing_staff_identity", "missing_staff_title", "missing_decision_timeline"}:
            rules["promote_to_graph_first"].append("staff_identity")
        if gap_type in {"missing_written_notice", "missing_response_dates"}:
            rules["mark_evidence_modalities"].append("policy_document_or_file_evidence")
        if gap_type in {"retaliation_missing_causation", "retaliation_missing_causation_link"}:
            rules["promote_to_graph_first"].append("causation_edge")
            rules["sequence_checks"].append("protected_activity_before_adverse_action")
        return rules

    def _critical_gap_signal(gap_type: str) -> float:
        critical = {
            "missing_exact_action_dates": 1.0,
            "missing_hearing_request_date": 1.0,
            "missing_response_dates": 1.0,
            "missing_hearing_timing": 0.95,
            "missing_staff_identity": 0.95,
            "missing_staff_title": 0.85,
            "retaliation_missing_causation_link": 1.0,
            "retaliation_missing_causation": 0.95,
            "retaliation_missing_sequencing_dates": 0.95,
            "retaliation_missing_sequence": 0.9,
            "missing_decision_timeline": 0.9,
            "missing_written_notice": 0.85,
        }
        return float(critical.get(gap_type, 0.6))

    def _extraction_targets_for_gap(gap_type: str) -> List[str]:
        mapping = {
            "missing_exact_action_dates": ["exact_dates", "event_order", "adverse_action"],
            "missing_hearing_request_date": ["exact_dates", "hearing_request", "decision_maker"],
            "missing_response_dates": ["exact_dates", "response_timing", "notice_chain"],
            "missing_hearing_timing": ["exact_dates", "event_order", "response_timing"],
            "missing_staff_identity": ["actor_name", "actor_role", "decision_maker"],
            "missing_staff_title": ["actor_name", "actor_role"],
            "retaliation_missing_causation": ["protected_activity", "adverse_action", "causation_link"],
            "retaliation_missing_causation_link": ["protected_activity", "adverse_action", "causation_link"],
            "retaliation_missing_sequence": ["exact_dates", "event_order", "causation_link"],
            "retaliation_missing_sequencing_dates": ["exact_dates", "event_order", "causation_link"],
            "missing_written_notice": ["document_type", "document_date", "document_owner"],
            "missing_decision_timeline": ["exact_dates", "event_order", "decision_maker"],
            "missing_claim_element": ["supporting_fact"],
        }
        return list(mapping.get(gap_type, ["supporting_fact"]))

    def _relation_updates_for_field(field_name: str) -> List[str]:
        mapping = {
            "event_date": ["link_event_sequence", "validate_temporal_order"],
            "adverse_action_date": ["link_event_sequence", "validate_temporal_order"],
            "hearing_request_date": ["link_response_to_hearing_or_action", "validate_temporal_order"],
            "response_date": ["link_response_to_hearing_or_action", "validate_temporal_order"],
            "protected_activity_date": ["link_causation_chain", "validate_temporal_order"],
            "staff_name": ["link_staff_to_action"],
            "staff_role": ["link_staff_to_action"],
            "staff_title": ["link_staff_to_action"],
            "decision_actor": ["link_staff_to_action"],
            "causation_link": ["link_causation_chain"],
            "document_name": ["link_document_to_claim"],
            "document_date": ["link_document_to_claim", "link_event_sequence"],
            "issuing_actor": ["link_document_to_claim", "link_staff_to_action"],
        }
        return list(mapping.get(field_name, []))

    def _entity_updates_for_field(field_name: str) -> List[str]:
        mapping = {
            "event_date": ["timeline_fact"],
            "adverse_action_date": ["timeline_fact"],
            "hearing_request_date": ["timeline_fact"],
            "response_date": ["timeline_fact"],
            "protected_activity_date": ["timeline_fact"],
            "staff_name": ["staff_actor"],
            "staff_role": ["staff_actor"],
            "staff_title": ["staff_actor"],
            "decision_actor": ["staff_actor"],
            "causation_link": ["causation_fact"],
            "document_name": ["document_evidence"],
            "document_date": ["document_evidence", "timeline_fact"],
            "issuing_actor": ["document_evidence", "staff_actor"],
        }
        return list(mapping.get(field_name, ["claim_fact"]))

    def _requirement_update_tokens_for_field(field_name: str, requirement_key: str) -> List[str]:
        updates = [requirement_key] if requirement_key else []
        if field_name in {"event_date", "adverse_action_date", "hearing_request_date", "response_date", "protected_activity_date"}:
            updates.append("chronology_complete")
        if field_name in {"staff_name", "staff_role", "staff_title", "decision_actor"}:
            updates.append("staff_identity_complete")
        if field_name == "causation_link":
            updates.append("causation_link_complete")
        if field_name in {"document_name", "document_date", "issuing_actor"}:
            updates.append("document_traceability_complete")
        return _ordered_unique(updates)

    def _gap_type_rank(gap_type: str) -> int:
        order = [
            "missing_exact_action_dates",
            "missing_hearing_request_date",
            "missing_response_dates",
            "missing_hearing_timing",
            "missing_staff_identity",
            "missing_staff_title",
            "retaliation_missing_causation_link",
            "retaliation_missing_causation",
            "retaliation_missing_sequencing_dates",
            "retaliation_missing_sequence",
            "missing_decision_timeline",
            "missing_written_notice",
            "missing_claim_element",
            "missing_proof_leads",
        ]
        if gap_type in order:
            return order.index(gap_type)
        return len(order)

    def _build_answer_contract(
        gap_type: str,
        deterministic_update_key: str,
        requirement_key: str,
        source_attrs: Dict[str, Any],
        evidence_modality: str,
        weak_claim_focus: bool,
    ) -> Dict[str, Any]:
        required_fields = _ordered_unique(
            [
                *_required_fields_for_gap(gap_type),
                *_modality_precision_fields(evidence_modality),
            ]
        )
        missing_fields = _missing_required_fields(required_fields, source_attrs)
        present_fields = [field_name for field_name in required_fields if field_name not in missing_fields]
        relationship_updates: List[str] = []
        if "actor_name" in _extraction_targets_for_gap(gap_type):
            relationship_updates.append("link_staff_to_action")
        if "exact_dates" in _extraction_targets_for_gap(gap_type):
            relationship_updates.append("link_event_sequence")
        if "document_type" in _extraction_targets_for_gap(gap_type):
            relationship_updates.append("link_document_to_claim")
        if "causation_link" in _extraction_targets_for_gap(gap_type):
            relationship_updates.append("link_causation_chain")
        if "event_order" in _extraction_targets_for_gap(gap_type):
            relationship_updates.append("validate_temporal_order")
        if "response_timing" in _extraction_targets_for_gap(gap_type):
            relationship_updates.append("link_response_to_hearing_or_action")

        entity_updates = ["claim_fact"]
        if "exact_dates" in _extraction_targets_for_gap(gap_type):
            entity_updates.append("timeline_fact")
        if "actor_name" in _extraction_targets_for_gap(gap_type):
            entity_updates.append("staff_actor")
        if "document_type" in _extraction_targets_for_gap(gap_type):
            entity_updates.append("document_evidence")

        satisfaction_rules = _satisfaction_rules_for_gap(gap_type=gap_type, requirement_key=requirement_key)
        closure_confidence = 0.0
        if required_fields:
            closure_confidence = max(0.0, min(1.0, len(present_fields) / len(required_fields)))

        field_resolution_contract = {}
        missing_field_update_plan = []
        for field_name in required_fields:
            field_value = _field_value(source_attrs, field_name)
            field_present = bool(field_value and not _is_unspecified_value(field_value))
            requirement_updates = _requirement_update_tokens_for_field(field_name, requirement_key)
            entity_updates = _entity_updates_for_field(field_name)
            relationship_updates_for_field = _relation_updates_for_field(field_name)
            field_resolution_contract[field_name] = {
                "field_present": field_present,
                "field_value": field_value if field_present else "",
                "entity_updates": entity_updates,
                "relationship_updates": relationship_updates_for_field,
                "requirement_updates": requirement_updates,
                "satisfies_gap_when_present": field_name in missing_fields,
            }
            if not field_present:
                missing_field_update_plan.append(
                    {
                        "field_name": field_name,
                        "resolution_key": f"{deterministic_update_key}:{field_name}" if deterministic_update_key else field_name,
                        "entity_updates": entity_updates,
                        "relationship_updates": relationship_updates_for_field,
                        "requirement_updates": requirement_updates,
                        "satisfies_gap_when_present": True,
                        "close_gap_after_update": len(missing_fields) == 1,
                    }
                )

        core_structured = _core_structured_gap(gap_type)
        deterministic_update_operations = _ordered_unique(
            [
                operation
                for update in missing_field_update_plan
                for operation in [
                    *(update.get("entity_updates") or []),
                    *(update.get("relationship_updates") or []),
                    *(update.get("requirement_updates") or []),
                ]
            ]
        )
        deterministically_closable = bool(
            deterministic_update_key
            and missing_fields
            and all(_field_aliases(field_name) for field_name in missing_fields)
        )
        modality_precision_fields = _modality_precision_fields(evidence_modality)
        modality_precision_missing = [
            field_name for field_name in modality_precision_fields if field_name in missing_fields
        ]
        weak_focus_weight = 1.0 if weak_claim_focus else 0.0
        return {
            "required_fields": required_fields,
            "missing_required_fields": missing_fields,
            "present_required_fields": present_fields,
            "entity_updates": entity_updates,
            "relationship_updates": relationship_updates,
            "requirement_updates": [requirement_key] if requirement_key else [],
            "resolution_key": deterministic_update_key,
            "satisfaction_rules": satisfaction_rules,
            "field_resolution_contract": field_resolution_contract,
            "missing_field_update_plan": missing_field_update_plan,
            "deterministic_update_operations": deterministic_update_operations,
            "closure_confidence": round(closure_confidence, 4),
            "single_turn_closable": len(missing_fields) <= 2,
            "single_field_closable": len(missing_fields) == 1,
            "deterministically_closable": deterministically_closable,
            "core_structured_gap": core_structured,
            "modality_precision_fields": modality_precision_fields,
            "modality_precision_missing_fields": modality_precision_missing,
            "modality_precision_complete": not modality_precision_missing,
            "weak_focus_weight": weak_focus_weight,
            "preferred_next_field": missing_fields[0] if missing_fields else "",
            "question_strategy": (
                "single_gap_closure"
                if core_structured and missing_fields
                else "collect_supporting_context"
            ),
        }

    def _build_deterministic_update_key(
        claim_id: str,
        claim_type: str,
        source_node: Optional[DependencyNode],
        source_attrs: Dict[str, Any],
        gap_type: str = "",
        requirement_key: str = "",
    ) -> str:
        explicit_gap_key = str(source_attrs.get("gap_key") or "").strip()
        if explicit_gap_key:
            return explicit_gap_key
        req_key = str(requirement_key or source_attrs.get("requirement_key") or "").strip()
        if req_key:
            type_fragment = _normalize_key_fragment(claim_type) or "claim"
            req_fragment = _normalize_key_fragment(req_key) or "requirement"
            return f"{type_fragment}:{req_fragment}"
        if gap_type:
            type_fragment = _normalize_key_fragment(claim_type) or "claim"
            gap_fragment = _normalize_key_fragment(gap_type) or "gap"
            return f"{type_fragment}:{gap_fragment}"

        source_fragment = _normalize_key_fragment(source_node.id if source_node else "") or "unknown_source"
        claim_fragment = _normalize_key_fragment(claim_type) or _normalize_key_fragment(claim_id) or "claim"
        return f"{claim_fragment}:{source_fragment}"

    claims = self.get_nodes_by_type(NodeType.CLAIM)
    nodes_by_id = self.nodes
    incoming_required_by_target: Dict[str, List[Dependency]] = {}
    for dep in self.dependencies.values():
        if dep.required:
            incoming_required_by_target.setdefault(dep.target_id, []).append(dep)

    ready_claims = []
    incomplete_claims = []
    total_missing_dependencies = 0
    total_satisfaction_ratio = 0.0
    recommended_next_gaps = []
    total_required_dependencies = 0
    total_satisfied_required_dependencies = 0
    underspecified_claims = 0
    weak_claim_gap_count = 0
    weak_modality_gap_count = 0
    structured_required_dependencies = 0
    structured_satisfied_dependencies = 0
    deterministic_gap_targets = 0
    deterministic_gap_targets_satisfied = 0
    core_structured_gap_count = 0
    core_structured_single_turn_closable = 0
    single_turn_closure_candidate_count = 0
    deterministic_field_update_total = 0
    deterministic_field_update_ready = 0
    concrete_gap_candidates = 0
    weak_modality_precision_field_total = 0
    weak_modality_precision_field_ready = 0

    for claim in claims:
        required_deps = incoming_required_by_target.get(claim.id, [])
        satisfied_count = 0
        missing_dependencies = []
        for dep in required_deps:
            source_node = nodes_by_id.get(dep.source_id)
            if source_node and source_node.satisfied:
                satisfied_count += 1
            else:
                missing_dependencies.append(
                    {
                        'dependency_id': dep.id,
                        'source_node_id': dep.source_id,
                        'source_name': source_node.name if source_node else 'Unknown',
                        'dependency_type': dep.dependency_type.value,
                    }
                )
        claim_type = str((claim.attributes or {}).get('claim_type') or '').strip().lower()
        total_required_for_claim = len(required_deps)
        claim_satisfaction_ratio = (
            satisfied_count / total_required_for_claim if total_required_for_claim > 0 else 1.0
        )
        claim_is_satisfied = claim_satisfaction_ratio >= 1.0
        claim_is_underspecified = total_required_for_claim == 0
        if claim_is_underspecified:
            underspecified_claims += 1

        total_required_dependencies += total_required_for_claim
        total_satisfied_required_dependencies += satisfied_count

        ranked_missing_dependencies = []
        claim_structured_required_count = 0
        claim_structured_satisfied_count = 0
        claim_deterministic_target_count = 0
        claim_deterministic_target_satisfied_count = 0
        missing_by_source_id = {str(dep.get("source_node_id") or "") for dep in missing_dependencies}
        for dep in required_deps:
            source_node = nodes_by_id.get(dep.source_id)
            source_attrs = source_node.attributes if source_node and isinstance(source_node.attributes, dict) else {}
            source_node_type = source_node.node_type.value if source_node else "unknown"
            requirement_key = str(source_attrs.get("requirement_key") or "").strip().lower()
            expected_modality = str(source_attrs.get("expected_evidence_modality") or "").strip().lower()
            has_structured_target = bool(
                requirement_key
                or expected_modality
                or source_node_type in {"legal_element", "requirement", "fact", "evidence"}
            )
            if has_structured_target:
                claim_structured_required_count += 1
            inferred_gap_type = _infer_gap_type(
                claim_type=claim_type,
                source_name=source_node.name if source_node else "",
                source_description=source_node.description if source_node else "",
                source_attrs=source_attrs,
                requirement_key=requirement_key,
                evidence_modality=expected_modality,
            )
            deterministic_key = _build_deterministic_update_key(
                claim_id=claim.id,
                claim_type=claim_type,
                source_node=source_node,
                source_attrs=source_attrs,
                gap_type=inferred_gap_type,
                requirement_key=requirement_key,
            )
            has_deterministic_key = bool(deterministic_key)
            if has_deterministic_key:
                claim_deterministic_target_count += 1
            if dep.source_id not in missing_by_source_id:
                if has_structured_target:
                    claim_structured_satisfied_count += 1
                if has_deterministic_key:
                    claim_deterministic_target_satisfied_count += 1

        structured_required_dependencies += claim_structured_required_count
        structured_satisfied_dependencies += claim_structured_satisfied_count
        deterministic_gap_targets += claim_deterministic_target_count
        deterministic_gap_targets_satisfied += claim_deterministic_target_satisfied_count

        for dep in missing_dependencies:
            source_node = self.get_node(str(dep.get('source_node_id') or ''))
            source_attrs = source_node.attributes if source_node and isinstance(source_node.attributes, dict) else {}
            blocking = bool(source_attrs.get('blocking', source_node.node_type in {NodeType.REQUIREMENT, NodeType.LEGAL_ELEMENT} if source_node else False))
            source_node_type = source_node.node_type.value if source_node else 'unknown'
            requirement_key = str(source_attrs.get('requirement_key') or '').strip().lower()
            evidence_modality = str(source_attrs.get('expected_evidence_modality') or '').strip().lower()
            gap_type = _infer_gap_type(
                claim_type=claim_type,
                source_name=source_node.name if source_node else "",
                source_description=source_node.description if source_node else "",
                source_attrs=source_attrs,
                requirement_key=requirement_key,
                evidence_modality=evidence_modality,
            )
            deterministic_update_key = _build_deterministic_update_key(
                claim_id=claim.id,
                claim_type=claim_type,
                source_node=source_node,
                source_attrs=source_attrs,
                gap_type=gap_type,
                requirement_key=requirement_key,
            )
            gap_id = deterministic_update_key or str(source_attrs.get('gap_key') or f"{claim.id}:{dep.get('source_node_id')}")
            structured_gap = bool(
                requirement_key
                or evidence_modality
                or source_node_type in {'legal_element', 'requirement', 'fact', 'evidence'}
            )
            weak_claim_focus = claim_type in _ACTOR_CRITIC_WEAK_CLAIM_TYPES
            weak_modality_focus = evidence_modality in _ACTOR_CRITIC_WEAK_EVIDENCE_MODALITIES
            source_text = " ".join(
                [
                    source_node.name if source_node else "",
                    source_node.description if source_node else "",
                    requirement_key,
                    str(source_attrs.get("question_hint") or ""),
                ]
            )
            contains_date = _contains_date_token(source_text)
            contains_name = _contains_name(source_text)
            extraction_targets = _extraction_targets_for_gap(gap_type)
            answer_contract = _build_answer_contract(
                gap_type=gap_type,
                deterministic_update_key=deterministic_update_key,
                requirement_key=requirement_key,
                source_attrs=source_attrs,
                evidence_modality=evidence_modality,
                weak_claim_focus=weak_claim_focus,
            )
            missing_required_fields = list(answer_contract.get("missing_required_fields") or [])
            required_fields = list(answer_contract.get("required_fields") or [])
            completion_ratio = (
                1.0 - (len(missing_required_fields) / len(required_fields))
                if required_fields
                else 1.0
            )
            missing_field_plan = list(answer_contract.get("missing_field_update_plan") or [])
            per_turn_closure_score = 0.0
            if answer_contract.get("single_field_closable"):
                per_turn_closure_score = 1.0
            elif answer_contract.get("single_turn_closable"):
                per_turn_closure_score = 0.8
            elif len(missing_required_fields) == 3:
                per_turn_closure_score = 0.45
            elif missing_required_fields:
                per_turn_closure_score = 0.2
            deterministic_plan_ratio = (
                min(1.0, len(missing_field_plan) / max(1, len(missing_required_fields)))
                if missing_required_fields
                else 1.0
            )
            closure_expected_gain = round(
                max(0.0, min(1.0, (per_turn_closure_score * 0.65) + (deterministic_plan_ratio * 0.35))),
                4,
            )
            actor_score = 0.0
            if blocking:
                actor_score += 4.0
            if weak_claim_focus:
                actor_score += 2.5
            if weak_modality_focus:
                actor_score += 2.0
            actor_score += max(0.0, 2.5 - (0.2 * _gap_type_rank(gap_type)))
            if structured_gap:
                actor_score += 1.5
            if contains_date:
                actor_score += 1.1
            if contains_name:
                actor_score += 0.9
            actor_score += _critical_gap_signal(gap_type) * 1.8
            actor_score += closure_expected_gain * 2.0
            if answer_contract.get("single_field_closable"):
                actor_score += 1.4
            if answer_contract.get("deterministically_closable"):
                actor_score += 1.2
            if weak_modality_focus and answer_contract.get("modality_precision_complete"):
                actor_score += 0.8
            critic_score = 0.0
            if structured_gap:
                critic_score += 3.5
            if deterministic_update_key:
                critic_score += 3.0
            if source_node_type in {'legal_element', 'requirement'}:
                critic_score += 1.8
            if evidence_modality in _ACTOR_CRITIC_WEAK_EVIDENCE_MODALITIES:
                critic_score += 1.2
            if dep.get('dependency_type') == DependencyType.REQUIRES.value:
                critic_score += 0.8
            if completion_ratio >= 0.5:
                critic_score += 1.2
            if answer_contract.get("single_turn_closable"):
                critic_score += 1.0
            if answer_contract.get("single_field_closable"):
                critic_score += 1.3
            if answer_contract.get("deterministically_closable"):
                critic_score += 1.5
            if weak_modality_focus and answer_contract.get("modality_precision_complete"):
                critic_score += 0.9
            critic_score += deterministic_plan_ratio * 1.2
            combined_priority = (actor_score * 0.55) + (critic_score * 0.45)
            concretely_answerable = not any(
                _is_unspecified_value(source_attrs.get(field_name))
                for field_name in ("question_hint", "placeholder", "expected_value")
            )
            if weak_claim_focus:
                weak_claim_gap_count += 1
            if weak_modality_focus:
                weak_modality_gap_count += 1
                modality_precision_fields = list(answer_contract.get("modality_precision_fields") or [])
                modality_precision_missing = list(answer_contract.get("modality_precision_missing_fields") or [])
                weak_modality_precision_field_total += len(modality_precision_fields)
                weak_modality_precision_field_ready += len(
                    [field for field in modality_precision_fields if field not in modality_precision_missing]
                )
            if answer_contract.get("core_structured_gap"):
                core_structured_gap_count += 1
                if answer_contract.get("single_turn_closable"):
                    core_structured_single_turn_closable += 1
            if deterministic_update_key and answer_contract.get("single_turn_closable"):
                concrete_gap_candidates += 1
            if answer_contract.get("single_turn_closable"):
                single_turn_closure_candidate_count += 1
            deterministic_field_update_total += len(required_fields)
            deterministic_field_update_ready += len([field for field in required_fields if field not in missing_required_fields])
            ranked_missing_dependencies.append(
                {
                    **dep,
                    'gap_id': gap_id,
                    'claim_type': claim_type,
                    'source_node_type': source_node_type,
                    'source_description': source_node.description if source_node else '',
                    'requirement_key': requirement_key,
                    'gap_type': gap_type,
                    'evidence_modality': evidence_modality,
                    'structured_gap': structured_gap,
                    'deterministic_update_key': deterministic_update_key,
                    'weak_claim_focus': weak_claim_focus,
                    'weak_modality_focus': weak_modality_focus,
                    'contains_date_signal': contains_date,
                    'contains_name_signal': contains_name,
                    'extraction_targets': extraction_targets,
                    'required_fields': required_fields,
                    'missing_required_fields': missing_required_fields,
                    'field_completion_ratio': round(max(0.0, min(1.0, completion_ratio)), 4),
                    'closure_expected_gain': closure_expected_gain,
                    'deterministic_plan_ratio': round(max(0.0, min(1.0, deterministic_plan_ratio)), 4),
                    'answer_contract': answer_contract,
                    'concretely_answerable': concretely_answerable,
                    'core_structured_gap': bool(answer_contract.get("core_structured_gap")),
                    'actor_score': round(actor_score, 4),
                    'critic_score': round(critic_score, 4),
                    'priority_score': round(combined_priority, 4),
                    'blocking': blocking,
                }
            )

        ranked_missing_dependencies.sort(
            key=lambda item: (
                0 if item.get('blocking') else 1,
                0 if item.get('weak_claim_focus') else 1,
                0 if item.get('weak_modality_focus') else 1,
                0 if item.get('answer_contract', {}).get('single_field_closable') else 1,
                0 if item.get('answer_contract', {}).get('deterministically_closable') else 1,
                0 if item.get('core_structured_gap') else 1,
                0 if item.get('structured_gap') else 1,
                _gap_type_rank(str(item.get('gap_type') or '').strip().lower()),
                0 if item.get('answer_contract', {}).get('single_turn_closable') else 1,
                -float(item.get('closure_expected_gain') or 0.0),
                -float(item.get('deterministic_plan_ratio') or 0.0),
                -float(item.get('field_completion_ratio') or 0.0),
                0 if item.get('concretely_answerable') else 1,
                -float(item.get('priority_score') or 0.0),
                0 if str(item.get('source_node_type') or '') in {'legal_element', 'requirement'} else 1,
                str(item.get('source_name') or '').lower(),
            )
        )

        total_missing_dependencies += len(ranked_missing_dependencies)
        total_satisfaction_ratio += claim_satisfaction_ratio
        next_gap = ranked_missing_dependencies[0] if ranked_missing_dependencies else None
        if claim_is_satisfied:
            ready_claims.append({
                'claim_id': claim.id,
                'claim_name': claim.name,
                'confidence': claim.confidence,
                'claim_type': claim_type,
                'dependency_satisfaction': 1.0,
                'underspecified': claim_is_underspecified,
                'required_dependency_count': total_required_for_claim,
                'structured_required_count': claim_structured_required_count,
                'structured_satisfied_count': claim_structured_satisfied_count,
                'deterministic_target_count': claim_deterministic_target_count,
                'deterministic_target_satisfied_count': claim_deterministic_target_satisfied_count,
            })
        else:
            incomplete_claims.append({
                'claim_id': claim.id,
                'claim_name': claim.name,
                'claim_type': claim_type,
                'satisfaction_ratio': claim_satisfaction_ratio,
                'dependency_satisfaction': claim_satisfaction_ratio,
                'missing_count': len(ranked_missing_dependencies),
                'missing_dependencies': ranked_missing_dependencies,
                'next_required_gap': next_gap,
                'underspecified': claim_is_underspecified,
                'required_dependency_count': total_required_for_claim,
                'structured_required_count': claim_structured_required_count,
                'structured_satisfied_count': claim_structured_satisfied_count,
                'deterministic_target_count': claim_deterministic_target_count,
                'deterministic_target_satisfied_count': claim_deterministic_target_satisfied_count,
            })
            if next_gap:
                recommended_next_gaps.append(
                    {
                        'claim_id': claim.id,
                        'claim_name': claim.name,
                        'claim_type': claim_type,
                        **next_gap,
                    }
                )

    claim_level_satisfaction = (
        total_satisfaction_ratio / len(claims) if claims else 0.0
    )

    dependency_coverage = (
        total_satisfied_required_dependencies / total_required_dependencies
        if total_required_dependencies > 0
        else (1.0 if claims else 0.0)
    )
    overall_dependency_satisfaction = (
        claim_level_satisfaction * 0.45 + dependency_coverage * 0.55
    ) if claims else 0.0
    structured_dependency_coverage = (
        structured_satisfied_dependencies / structured_required_dependencies
        if structured_required_dependencies > 0
        else dependency_coverage
    )
    deterministic_gap_closure = (
        deterministic_gap_targets_satisfied / deterministic_gap_targets
        if deterministic_gap_targets > 0
        else dependency_coverage
    )
    graph_population_score = (
        (
            ((len(claims) - underspecified_claims) / len(claims)) * 0.55
            + structured_dependency_coverage * 0.45
        )
        if claims
        else 0.0
    )
    graph_analysis_confidence = max(
        0.0,
        min(
            1.0,
            dependency_coverage * 0.35
            + structured_dependency_coverage * 0.30
            + deterministic_gap_closure * 0.20
            + graph_population_score * 0.15,
        ),
    )
    deterministic_field_update_coverage = (
        deterministic_field_update_ready / deterministic_field_update_total
        if deterministic_field_update_total > 0
        else deterministic_gap_closure
    )
    concrete_gap_closure_ratio = (
        concrete_gap_candidates / total_missing_dependencies
        if total_missing_dependencies > 0
        else (1.0 if claims else 0.0)
    )
    weak_modality_precision_coverage = (
        weak_modality_precision_field_ready / weak_modality_precision_field_total
        if weak_modality_precision_field_total > 0
        else 1.0
    )
    gap_closure_efficiency = (
        core_structured_single_turn_closable / core_structured_gap_count
        if core_structured_gap_count > 0
        else 0.0
    )
    avg_gaps = total_missing_dependencies / len(claims) if claims else 0.0

    readiness_history = self.metadata.setdefault('readiness_history', {})
    previous_avg_gaps = float(readiness_history.get('avg_gaps', avg_gaps))
    gap_delta_per_iter = avg_gaps - previous_avg_gaps
    previous_stall_count = int(readiness_history.get('gap_stall_sessions', 0))
    if avg_gaps > 0.0 and gap_delta_per_iter >= -1e-9:
        gap_stall_sessions = previous_stall_count + 1
    else:
        gap_stall_sessions = 0
    readiness_history.update(
        {
            'avg_gaps': avg_gaps,
            'gap_stall_sessions': gap_stall_sessions,
            'updated_at': _utc_now_isoformat(),
        }
    )
    self.metadata['readiness_history'] = readiness_history

    recommended_actions = []
    if not claims:
        recommended_actions.append(
            "Restore a stable adversarial session flow before tuning graph extraction and dependency tracking."
        )
    if total_required_dependencies == 0 and claims:
        recommended_actions.append(
            "No required dependencies are linked to claims; populate requirement/evidence edges before denoising."
        )
    if gap_stall_sessions >= 2 and avg_gaps > 0.0:
        recommended_actions.append(
            "Gap count is not improving across iterations; prioritize blocker-focused follow-ups in graph_analysis."
        )
    if weak_claim_gap_count > 0:
        recommended_actions.append(
            "Prioritize deterministic requirement closure for housing_discrimination and hacc_research_engine gaps."
        )
    if weak_modality_gap_count > 0:
        recommended_actions.append(
            "Request policy_document and file_evidence fields with exact document name, date, and issuing/source actor."
        )
    if deterministic_gap_closure < 0.6 and total_required_dependencies > 0:
        recommended_actions.append(
            "Map each follow-up question to a deterministic_update_key so each answer closes a concrete graph requirement."
        )
    if deterministic_field_update_coverage < 0.7 and total_required_dependencies > 0:
        recommended_actions.append(
            "Emit a missing_field_update_plan per gap and process answers by field-level entity/relationship/requirement updates."
        )
    if weak_modality_gap_count > 0 and weak_modality_precision_coverage < 0.7:
        recommended_actions.append(
            "For policy_document and file_evidence, require document_name, document_date, and issuing/source actor before advancing."
        )
    if concrete_gap_closure_ratio < 0.6 and total_missing_dependencies > 0:
        recommended_actions.append(
            "Select next_required_gap from single-field deterministic closures first so each turn closes one concrete graph gap."
        )
    if gap_closure_efficiency < 0.5 and core_structured_gap_count > 0:
        recommended_actions.append(
            "Bias questioning toward single-field or single-turn closure gaps to reduce stall sessions."
        )
    if core_structured_gap_count > 0:
        recommended_actions.append(
            "Close exact date, staff identity/title, hearing timing, response date, and causation sequencing gaps before broader narrative prompts."
        )

    recommended_next_gaps.sort(
        key=lambda item: (
            0 if item.get('blocking') else 1,
            0 if item.get('weak_claim_focus') else 1,
            0 if item.get('weak_modality_focus') else 1,
            0 if item.get('answer_contract', {}).get('single_field_closable') else 1,
            0 if item.get('answer_contract', {}).get('deterministically_closable') else 1,
            0 if item.get('core_structured_gap') else 1,
            0 if item.get('structured_gap') else 1,
            _gap_type_rank(str(item.get('gap_type') or '').strip().lower()),
            0 if item.get('answer_contract', {}).get('single_turn_closable') else 1,
            -float(item.get('closure_expected_gain') or 0.0),
            -float(item.get('deterministic_plan_ratio') or 0.0),
            -float(item.get('field_completion_ratio') or 0.0),
            -float(item.get('priority_score') or 0.0),
            str(item.get('claim_name') or '').lower(),
            str(item.get('source_name') or '').lower(),
        )
    )

    return {
        'total_claims': len(claims),
        'ready_claims': len(ready_claims),
        'incomplete_claims': len(incomplete_claims),
        'ready_claim_details': ready_claims,
        'incomplete_claim_details': incomplete_claims,
        'overall_readiness': overall_dependency_satisfaction,
        'overall_dependency_satisfaction': overall_dependency_satisfaction,
        'dependency_satisfaction': overall_dependency_satisfaction,
        'claim_level_dependency_satisfaction': claim_level_satisfaction,
        'dependency_coverage': dependency_coverage,
        'structured_dependency_coverage': structured_dependency_coverage,
        'deterministic_gap_closure': deterministic_gap_closure,
        'graph_population_score': graph_population_score,
        'graph_analysis_confidence': graph_analysis_confidence,
        'total_missing_dependencies': total_missing_dependencies,
        'avg_gaps': avg_gaps,
        'gap_delta_per_iter': gap_delta_per_iter,
        'gap_stall_sessions': gap_stall_sessions,
        'underspecified_claims': underspecified_claims,
        'weak_claim_gap_count': weak_claim_gap_count,
        'weak_modality_gap_count': weak_modality_gap_count,
        'core_structured_gap_count': core_structured_gap_count,
        'core_structured_single_turn_closable': core_structured_single_turn_closable,
        'single_turn_closure_candidate_count': single_turn_closure_candidate_count,
        'deterministic_field_update_coverage': deterministic_field_update_coverage,
        'concrete_gap_closure_ratio': concrete_gap_closure_ratio,
        'gap_closure_efficiency': gap_closure_efficiency,
        'weak_modality_precision_coverage': weak_modality_precision_coverage,
        'recommended_actions': recommended_actions,
        'recommended_next_gaps': recommended_next_gaps,
        'actor_critic': {
            'optimizer': 'actor_critic',
            'priority': _ACTOR_CRITIC_PRIORITY,
            'phase_focus_order': list(_ACTOR_CRITIC_PHASE_FOCUS_ORDER),
            'focus_metrics': dict(_ACTOR_CRITIC_FOCUS_METRICS),
            'graph_analysis': {
                'dependency_coverage': dependency_coverage,
                'structured_dependency_coverage': structured_dependency_coverage,
                'deterministic_gap_closure': deterministic_gap_closure,
                'graph_population_score': graph_population_score,
                'graph_analysis_confidence': graph_analysis_confidence,
                'avg_gaps': avg_gaps,
                'gap_delta_per_iter': gap_delta_per_iter,
                'gap_stall_sessions': gap_stall_sessions,
                'weak_claim_types': sorted(_ACTOR_CRITIC_WEAK_CLAIM_TYPES),
                'weak_evidence_modalities': sorted(_ACTOR_CRITIC_WEAK_EVIDENCE_MODALITIES),
                'weak_claim_gap_count': weak_claim_gap_count,
                'weak_modality_gap_count': weak_modality_gap_count,
                'core_structured_gap_count': core_structured_gap_count,
                'core_structured_single_turn_closable': core_structured_single_turn_closable,
                'single_turn_closure_candidate_count': single_turn_closure_candidate_count,
                'deterministic_field_update_coverage': deterministic_field_update_coverage,
                'concrete_gap_closure_ratio': concrete_gap_closure_ratio,
                'gap_closure_efficiency': gap_closure_efficiency,
                'weak_modality_precision_coverage': weak_modality_precision_coverage,
                'recommended_actions': recommended_actions,
            },
        },
    }


def get_blocker_follow_up_issues(self) -> List[Dict[str, Any]]:
    """Return follow-up blocker issues for intake questioning and patch routing."""
    issues: List[Dict[str, Any]] = []
    node_text_by_id = {
        node_id: f"{node.name} {node.description}".strip().lower()
        for node_id, node in self.nodes.items()
    }
    node_rich_text_by_id = {
        node_id: self._node_rich_text(node)
        for node_id, node in self.nodes.items()
    }

    # Hearing/appeal timing blockers: hearing references without explicit temporal edges.
    hearing_node_ids = [
        node_id
        for node_id, text_value in node_text_by_id.items()
        if any(token in text_value for token in ("hearing", "appeal", "grievance"))
    ]
    for node_id in hearing_node_ids:
        temporal_links = [
            dep for dep in self.get_dependencies_for_node(node_id)
            if dep.dependency_type in {DependencyType.BEFORE, DependencyType.SAME_TIME, DependencyType.OVERLAPS}
        ]
        if temporal_links:
            continue
        node = self.get_node(node_id)
        issues.append(
            {
                "issue_id": f"blocker_hearing_timing_{node_id}",
                "issue_type": "missing_hearing_timing",
                "severity": "blocking",
                "question_type": "timeline",
                "recommended_resolution_lane": "request_document",
                "workflow_phase": "graph_analysis",
                "workflow_phase_rank": 0,
                "node_id": node_id,
                "node_name": node.name if node else node_id,
                "summary": "Hearing or appeal activity lacks dated sequencing in dependency graph.",
                "extraction_targets": ["exact_dates", "event_order", "actor_name", "document_owner"],
                "patchability_markers": ["chronology_patch_anchor", "notice_chain_patch_anchor"],
                "suggested_question": (
                    "Please walk me through the hearing or appeal timeline with exact dates, who handled each step, and any notice, email, or letter tied to each response."
                ),
            }
        )

    # Chronology closure blockers: timeline-critical events without exact dates or response timing.
    chronology_focus_tokens = (
        "hearing",
        "appeal",
        "grievance",
        "notice",
        "response",
        "reply",
        "decision",
        "protected activity",
        "complained",
        "reported",
        "adverse action",
        "terminated",
        "disciplined",
        "evicted",
        "suspended",
    )
    chronology_focus_node_ids = [
        node_id
        for node_id, text_value in node_text_by_id.items()
        if any(token in text_value for token in chronology_focus_tokens)
    ]
    chronology_missing_date_nodes = [
        self.get_node(node_id)
        for node_id in chronology_focus_node_ids
        if not self._contains_date_anchor(node_rich_text_by_id.get(node_id, ""))
    ]
    chronology_missing_date_nodes = [node for node in chronology_missing_date_nodes if node is not None]
    if chronology_missing_date_nodes:
        sample_labels = ", ".join(node.name for node in chronology_missing_date_nodes[:3])
        issues.append(
            {
                "issue_id": "blocker_chronology_exact_dates_missing",
                "issue_type": "chronology_exact_dates_missing",
                "severity": "blocking",
                "question_type": "timeline",
                "recommended_resolution_lane": "request_document",
                "workflow_phase": "graph_analysis",
                "workflow_phase_rank": 0,
                "summary": "Chronology-critical events are missing exact date anchors and response timing closure.",
                "node_ids": [node.id for node in chronology_missing_date_nodes],
                "node_names": [node.name for node in chronology_missing_date_nodes],
                "extraction_targets": [
                    "exact_dates",
                    "response_timing",
                    "event_order",
                    "actor_name",
                    "decision_maker",
                    "document_date",
                ],
                "patchability_markers": [
                    "chronology_patch_anchor",
                    "notice_chain_patch_anchor",
                    "decision_actor_patch_anchor",
                ],
                "suggested_question": (
                    f"For chronology items such as {sample_labels}, what exact date did each event occur, "
                    "who handled each step, and how long after each event the next response or decision occurred?"
                ),
            }
        )

    chronology_with_dates = [
        node_id
        for node_id in chronology_focus_node_ids
        if self._contains_date_anchor(node_rich_text_by_id.get(node_id, ""))
    ]
    has_chronology_sequence = any(
        dep.dependency_type in {DependencyType.BEFORE, DependencyType.SAME_TIME, DependencyType.OVERLAPS}
        and dep.source_id in chronology_with_dates
        and dep.target_id in chronology_with_dates
        for dep in self.dependencies.values()
    )
    if len(chronology_with_dates) >= 2 and not has_chronology_sequence:
        issues.append(
            {
                "issue_id": "blocker_chronology_sequence_missing",
                "issue_type": "chronology_sequence_missing",
                "severity": "blocking",
                "question_type": "timeline",
                "recommended_resolution_lane": "request_document",
                "workflow_phase": "graph_analysis",
                "workflow_phase_rank": 0,
                "summary": "Dated chronology events exist but are not connected into a clear sequence in the graph.",
                "node_ids": list(chronology_with_dates),
                "extraction_targets": ["exact_dates", "event_order", "response_timing", "causation_link"],
                "patchability_markers": ["chronology_patch_anchor", "causation_patch_anchor"],
                "suggested_question": (
                    "Using exact dates, what happened first, second, and third, and what was the response timing between each step?"
                ),
            }
        )

    # Staff identity blockers: staff-role references without a concrete named actor node.
    staff_like_nodes = [
        node for node in self.nodes.values()
        if any(token in f"{node.name} {node.description}".lower() for token in ("manager", "supervisor", "hr", "landlord", "officer", "staff"))
    ]
    has_named_actor = any(
        node.node_type in {NodeType.FACT, NodeType.EVIDENCE, NodeType.REQUIREMENT, NodeType.CLAIM}
        and bool(_NAME_PATTERN.search(node.name))
        for node in self.nodes.values()
    )
    if staff_like_nodes and not has_named_actor:
        issues.append(
            {
                "issue_id": "blocker_staff_identity_missing",
                "issue_type": "missing_staff_identity",
                "severity": "blocking",
                "question_type": "responsible_party",
                "recommended_resolution_lane": "clarify_with_complainant",
                "workflow_phase": "graph_analysis",
                "workflow_phase_rank": 0,
                "summary": "Staff-role references exist but no named actor is linked in the dependency graph.",
                "extraction_targets": ["actor_name", "actor_role", "organization_unit"],
                "patchability_markers": ["actor_link_patch_anchor"],
                "suggested_question": "Who specifically took each action (full name and title), what team or office they were in, and how they were connected to your case?",
            }
        )

    # Decision detail blockers: adverse action mentions without precision on decision-maker and action specifics.
    general_adverse_ids = [
        node_id
        for node_id, text_value in node_text_by_id.items()
        if any(
            token in text_value
            for token in (
                "fired",
                "terminated",
                "demoted",
                "disciplined",
                "suspended",
                "adverse action",
                "evicted",
                "reduced hours",
                "cut hours",
                "denied",
            )
        )
    ]
    adverse_nodes_missing_actor_precision = [
        node_id
        for node_id in general_adverse_ids
        if not (
            _NAME_PATTERN.search(node_rich_text_by_id.get(node_id, ""))
            or any(
                token in node_text_by_id.get(node_id, "")
                for token in ("manager", "supervisor", "director", "hr", "officer", "landlord", "administrator")
            )
        )
    ]
    if adverse_nodes_missing_actor_precision:
        issues.append(
            {
                "issue_id": "blocker_adverse_action_decision_precision_missing",
                "issue_type": "adverse_action_decision_precision_missing",
                "severity": "blocking",
                "question_type": "responsible_party",
                "recommended_resolution_lane": "clarify_with_complainant",
                "workflow_phase": "graph_analysis",
                "workflow_phase_rank": 0,
                "summary": "Adverse action facts lack specific decision-maker identity, role, and action detail precision.",
                "node_ids": list(adverse_nodes_missing_actor_precision),
                "extraction_targets": [
                    "decision_maker",
                    "actor_name",
                    "actor_role",
                    "adverse_action",
                    "exact_dates",
                    "organization_unit",
                ],
                "patchability_markers": [
                    "actor_link_patch_anchor",
                    "decision_actor_patch_anchor",
                    "chronology_patch_anchor",
                ],
                "suggested_question": (
                    "For each adverse action, who made or approved it (full name, title, and office), "
                    "what exactly was decided or imposed, and on what exact date?"
                ),
            }
        )

    # Documentary precision blockers: records exist but lack sender/recipient/subject/ID anchors.
    document_like_nodes = [
        node_id
        for node_id, text_value in node_text_by_id.items()
        if any(token in text_value for token in ("notice", "letter", "email", "message", "text", "memo", "record"))
    ]
    has_document_precision = any(
        self._contains_document_precision_marker(node_rich_text_by_id.get(node_id, ""))
        for node_id in document_like_nodes
    )
    if document_like_nodes and not has_document_precision:
        issues.append(
            {
                "issue_id": "blocker_document_artifact_precision_missing",
                "issue_type": "document_artifact_precision_missing",
                "severity": "blocking",
                "question_type": "evidence",
                "recommended_resolution_lane": "request_document",
                "workflow_phase": "document_generation",
                "workflow_phase_rank": 1,
                "summary": "Document artifacts are referenced but missing citation-grade identifiers for patch-ready drafting.",
                "node_ids": list(document_like_nodes),
                "extraction_targets": [
                    "document_type",
                    "document_date",
                    "document_owner",
                    "document_sender",
                    "document_recipient",
                    "document_subject",
                    "document_identifier",
                ],
                "patchability_markers": [
                    "support_patch_anchor",
                    "notice_chain_patch_anchor",
                    "decision_actor_patch_anchor",
                ],
                "suggested_question": (
                    "For each relevant notice/email/message, what is the exact date, sender, recipient, subject line, "
                    "and any case number or document ID we should cite?"
                ),
            }
        )

    # Retaliation sequencing blockers: protected activity and adverse action nodes without BEFORE ordering.
    retaliation_claim_nodes = [
        node for node in self.get_nodes_by_type(NodeType.CLAIM)
        if (
            "retaliat" in node.name.lower()
            or str((node.attributes or {}).get("claim_type") or "").strip().lower() == "retaliation"
        )
    ]
    if retaliation_claim_nodes:
        protected_ids = [
            node_id for node_id, text_value in node_text_by_id.items()
            if any(token in text_value for token in ("protected activity", "complained", "reported", "grievance", "accommodation"))
        ]
        adverse_ids = [
            node_id for node_id, text_value in node_text_by_id.items()
            if any(token in text_value for token in ("fired", "terminated", "demoted", "disciplined", "suspended", "adverse action", "evicted", "reduced hours", "cut hours"))
        ]
        has_ordering = any(
            dep.dependency_type == DependencyType.BEFORE
            and dep.source_id in protected_ids
            and dep.target_id in adverse_ids
            for dep in self.dependencies.values()
        )
        if protected_ids and adverse_ids and not has_ordering:
            issues.append(
                {
                    "issue_id": "blocker_retaliation_sequence_missing",
                    "issue_type": "retaliation_missing_sequence",
                    "severity": "blocking",
                    "question_type": "timeline",
                    "recommended_resolution_lane": "request_document",
                    "workflow_phase": "graph_analysis",
                    "workflow_phase_rank": 0,
                    "summary": "Retaliation theory has protected activity and adverse action nodes but lacks temporal ordering.",
                    "extraction_targets": ["protected_activity", "adverse_action", "exact_dates", "actor_name", "causation_link"],
                    "patchability_markers": ["chronology_patch_anchor", "causation_patch_anchor"],
                    "suggested_question": (
                        "What was your protected activity, on what exact date did it occur, who knew about it, and what adverse actions followed afterward with dates, actor names, and any supporting notice or message?"
                    ),
                }
            )

        # Retaliation issues also need explicit decision-maker identity and rationale.
        decision_terms = ("decid", "approved", "denied", "terminated", "disciplined", "recommended", "ordered")
        role_terms = ("manager", "supervisor", "director", "hr", "officer", "landlord", "administrator", "staff")
        has_decision_maker_signal = any(
            any(term in text_value for term in decision_terms)
            and (bool(_NAME_PATTERN.search(node_rich_text_by_id.get(node_id, ""))) or any(role in text_value for role in role_terms))
            for node_id, text_value in node_text_by_id.items()
        )
        if adverse_ids and not has_decision_maker_signal:
            issues.append(
                {
                    "issue_id": "blocker_retaliation_decision_maker_missing",
                    "issue_type": "retaliation_missing_decision_maker",
                    "severity": "blocking",
                    "question_type": "responsible_party",
                    "recommended_resolution_lane": "clarify_with_complainant",
                    "workflow_phase": "graph_analysis",
                    "workflow_phase_rank": 0,
                    "summary": "Retaliation adverse-action path lacks a named decision-maker identity and role.",
                    "extraction_targets": ["decision_maker", "actor_name", "actor_role", "organization_unit", "exact_dates"],
                    "patchability_markers": ["actor_link_patch_anchor", "decision_actor_patch_anchor", "chronology_patch_anchor"],
                    "suggested_question": (
                        "Who made or approved each adverse decision (full name, title, and office), on what exact date each decision was made, and who communicated it to you?"
                    ),
                }
            )

        # Improve document-generation coverage for causation corroboration.
        has_causation_documents = any(
            any(token in text_value for token in ("notice", "letter", "email", "message", "record", "memo"))
            and any(token in text_value for token in ("protected activity", "complained", "reported", "adverse action", "terminated", "disciplined"))
            for text_value in node_text_by_id.values()
        )
        if (adverse_ids or protected_ids) and not has_causation_documents:
            issues.append(
                {
                    "issue_id": "blocker_retaliation_causation_documents_missing",
                    "issue_type": "retaliation_missing_causation_documents",
                    "severity": "blocking",
                    "question_type": "evidence",
                    "recommended_resolution_lane": "request_document",
                    "workflow_phase": "document_generation",
                    "workflow_phase_rank": 1,
                    "summary": "Causation path lacks anchored records linking protected activity knowledge to adverse action.",
                    "extraction_targets": ["document_type", "document_date", "document_owner", "decision_maker", "causation_link"],
                    "patchability_markers": ["support_patch_anchor", "notice_chain_patch_anchor", "causation_patch_anchor"],
                    "suggested_question": (
                        "Which notice, email, text, meeting record, or memo shows decision-makers knew about your protected activity before the adverse action, and what date and sender/recipient details are on each record?"
                    ),
                }
            )

    # Convert placeholder facts into concrete, draft-ready anchors with phase-ordered follow-up.
    placeholder_nodes = self._nodes_with_confirmation_placeholders(node_rich_text_by_id)
    if placeholder_nodes:
        placeholder_labels = ", ".join(node.name for node in placeholder_nodes[:3])
        issues.append(
            {
                "issue_id": "blocker_confirmation_placeholders_specificity",
                "issue_type": "confirmation_placeholders_needing_specific_facts",
                "severity": "blocking",
                "question_type": "timeline",
                "recommended_resolution_lane": "clarify_with_complainant",
                "workflow_phase": "graph_analysis",
                "workflow_phase_rank": 0,
                "summary": "One or more graph facts still contain confirmation placeholders instead of concrete anchors.",
                "placeholder_node_ids": [node.id for node in placeholder_nodes],
                "placeholder_node_names": [node.name for node in placeholder_nodes],
                "extraction_targets": ["exact_dates", "actor_name", "actor_role", "decision_maker", "event_order"],
                "patchability_markers": ["chronology_patch_anchor", "actor_link_patch_anchor", "decision_actor_patch_anchor"],
                "suggested_question": (
                    f"For each placeholder item ({placeholder_labels}), what are the exact dates, who took each action (full name and title), and what happened immediately before and after?"
                ),
            }
        )
        issues.append(
            {
                "issue_id": "blocker_confirmation_placeholders_document_anchor",
                "issue_type": "confirmation_placeholders_missing_document_anchor",
                "severity": "blocking",
                "question_type": "evidence",
                "recommended_resolution_lane": "request_document",
                "workflow_phase": "document_generation",
                "workflow_phase_rank": 2,
                "summary": "Placeholder facts are not anchored to specific records for patch-ready drafting.",
                "placeholder_node_ids": [node.id for node in placeholder_nodes],
                "placeholder_node_names": [node.name for node in placeholder_nodes],
                "extraction_targets": ["document_type", "document_date", "document_owner", "actor_name"],
                "patchability_markers": ["support_patch_anchor", "notice_chain_patch_anchor"],
                "suggested_question": (
                    "What specific documents, notices, emails, or messages confirm each placeholder fact, and what date, sender, recipient, and subject line should we cite for each one?"
                ),
            }
        )
        issues.append(
            {
                "issue_id": "blocker_confirmation_placeholders_intake_closure",
                "issue_type": "confirmation_placeholders_intake_closure",
                "severity": "important",
                "question_type": "clarification",
                "recommended_resolution_lane": "clarify_with_complainant",
                "workflow_phase": "intake_questioning",
                "workflow_phase_rank": 1,
                "summary": "Intake record still has unresolved placeholders requiring a best-estimate fallback for closure.",
                "placeholder_node_ids": [node.id for node in placeholder_nodes],
                "placeholder_node_names": [node.name for node in placeholder_nodes],
                "extraction_targets": ["date_estimate", "confidence_level", "verification_source", "actor_name"],
                "patchability_markers": ["intake_follow_up_patch_anchor"],
                "suggested_question": (
                    "If any exact detail is still uncertain, give your best date range, who can verify it, and where that verification can be found so we can close the intake gap."
                ),
            }
        )

    return self._optimize_blocker_issues_for_actor_critic(issues)


def build_from_claims(self, claims: List[Dict[str, Any]], 
                      legal_requirements: Optional[Dict[str, Any]] = None,
                      *,
                      require_verified_legal_sources: bool = False) -> DependencyGraph:
    """
    Build a dependency graph from claims and legal requirements.

    Args:
        claims: List of claim dictionaries with name, type, description
        legal_requirements: Optional legal requirement mappings

    Returns:
        A DependencyGraph instance
    """
    graph = DependencyGraph()

    # Create claim nodes
    claim_nodes = []
    for claim_data in claims:
        node = DependencyNode(
            id=self._get_node_id(),
            node_type=NodeType.CLAIM,
            name=claim_data.get('name', 'Unnamed Claim'),
            description=claim_data.get('description', ''),
            attributes={'claim_type': claim_data.get('type', 'unknown')}
        )
        graph.add_node(node)
        claim_nodes.append(node)

    def has_date(text_value: str) -> bool:
        if not text_value:
            return False
        # A user's explicit law-query date selects a legal version; it is
        # not an event date and cannot close a factual chronology gap.
        # Preserve the original claim/source text and all other dates.
        patterns = [
            r'\b(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{1,2},\s+\d{4}\b',
            r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
            r'\b\d{4}-\d{2}-\d{2}\b',
        ]
        legal_date = (r'(?i:\b(?:applicable law date|law in effect on|law applicable on))\s*[: ]\s*(?:'
                      + '|'.join(patterns) + ')')
        text_value = re.sub(legal_date, '', text_value)
        return any(re.search(p, text_value) for p in patterns)

    def has_actor_signal(text_value: str) -> bool:
        if not text_value:
            return False
        lower = text_value.lower()
        actor_keywords = [
            "employer", "company", "organization", "business", "manager", "supervisor",
            "boss", "hr", "human resources", "landlord", "owner", "agency", "department",
            "school", "university", "hospital", "clinic", "doctor", "nurse", "teacher",
            "principal", "officer", "agent", "neighbor", "coworker", "co-worker",
            "colleague", "respondent",
        ]
        return any(k in lower for k in actor_keywords)

    def has_protected_activity_signal(text_value: str) -> bool:
        if not text_value:
            return False
        lower = text_value.lower()
        return any(
            token in lower
            for token in [
                "protected activity",
                "complained",
                "reported",
                "grievance",
                "whistle",
                "requested accommodation",
                "requested help",
            ]
        )

    def has_adverse_action_signal(text_value: str) -> bool:
        if not text_value:
            return False
        lower = text_value.lower()
        return any(
            token in lower
            for token in [
                "fired",
                "terminated",
                "demoted",
                "suspended",
                "disciplined",
                "reduced hours",
                "cut hours",
                "evicted",
            ]
        )

    def has_notice_signal(text_value: str) -> bool:
        if not text_value:
            return False
        lower = text_value.lower()
        return any(token in lower for token in ["notice", "letter", "email", "message"])

    def has_hearing_signal(text_value: str) -> bool:
        if not text_value:
            return False
        lower = text_value.lower()
        return any(token in lower for token in ["hearing", "grievance", "appeal"])

    def has_causation_signal(text_value: str) -> bool:
        if not text_value:
            return False
        lower = text_value.lower()
        has_connector = any(
            token in lower
            for token in ["because", "due to", "in response to", "soon after", "after", "as a result"]
        )
        return has_connector and has_protected_activity_signal(text_value) and has_adverse_action_signal(text_value)

    # Add lightweight fact dependencies to avoid empty graphs when legal requirements are absent.
    for claim_node in claim_nodes:
        claim_text = f"{claim_node.name} {claim_node.description}".strip()
        claim_type = str(claim_node.attributes.get("claim_type") or "").strip().lower()

        if not has_date(claim_text):
            timeline_node = DependencyNode(
                id=self._get_node_id(),
                node_type=NodeType.FACT,
                name="Timeline of events",
                description="Dates or sequence of key events related to this claim",
                satisfied=False,
                confidence=0.0
            )
            graph.add_node(timeline_node)
            graph.add_dependency(Dependency(
                id=self._get_dependency_id(),
                source_id=timeline_node.id,
                target_id=claim_node.id,
                dependency_type=DependencyType.DEPENDS_ON,
                required=True
            ))
        if not (has_date(claim_text) and has_actor_signal(claim_text)):
            decision_timeline_node = DependencyNode(
                id=self._get_node_id(),
                node_type=NodeType.FACT,
                name="Actor-by-actor decision timeline",
                description=(
                    "For each actor, identify the decision/action taken and the date anchor "
                    "(or best estimate) for that step"
                ),
                satisfied=False,
                confidence=0.0,
            )
            graph.add_node(decision_timeline_node)
            graph.add_dependency(Dependency(
                id=self._get_dependency_id(),
                source_id=decision_timeline_node.id,
                target_id=claim_node.id,
                dependency_type=DependencyType.DEPENDS_ON,
                required=True,
            ))

        if not has_actor_signal(claim_text):
            actor_node = DependencyNode(
                id=self._get_node_id(),
                node_type=NodeType.FACT,
                name="Responsible party",
                description="Who took the action or decision tied to this claim",
                satisfied=False,
                confidence=0.0
            )
            graph.add_node(actor_node)
            graph.add_dependency(Dependency(
                id=self._get_dependency_id(),
                source_id=actor_node.id,
                target_id=claim_node.id,
                dependency_type=DependencyType.DEPENDS_ON,
                required=True
            ))

        # Retaliation claims need explicit causation sequencing (protected activity -> adverse action).
        retaliation_like = "retaliat" in claim_type or "retaliat" in claim_text.lower()
        if retaliation_like:
            if not has_protected_activity_signal(claim_text):
                protected_activity_node = DependencyNode(
                    id=self._get_node_id(),
                    node_type=NodeType.FACT,
                    name="Protected activity facts",
                    description="What protected activity occurred, to whom it was reported, and when",
                    satisfied=False,
                    confidence=0.0,
                )
                graph.add_node(protected_activity_node)
                graph.add_dependency(Dependency(
                    id=self._get_dependency_id(),
                    source_id=protected_activity_node.id,
                    target_id=claim_node.id,
                    dependency_type=DependencyType.DEPENDS_ON,
                    required=True,
                ))

            if not has_adverse_action_signal(claim_text):
                adverse_action_node = DependencyNode(
                    id=self._get_node_id(),
                    node_type=NodeType.FACT,
                    name="Adverse action facts",
                    description="What happened after protected activity, by whom, and on what date",
                    satisfied=False,
                    confidence=0.0,
                )
                graph.add_node(adverse_action_node)
                graph.add_dependency(Dependency(
                    id=self._get_dependency_id(),
                    source_id=adverse_action_node.id,
                    target_id=claim_node.id,
                    dependency_type=DependencyType.DEPENDS_ON,
                    required=True,
                ))

            if not (has_date(claim_text) and has_actor_signal(claim_text)):
                causation_node = DependencyNode(
                    id=self._get_node_id(),
                    node_type=NodeType.FACT,
                    name="Retaliation causation chronology",
                    description="Sequence from protected activity to adverse action with dates and actor identities",
                    satisfied=False,
                    confidence=0.0,
                )
                graph.add_node(causation_node)
                graph.add_dependency(Dependency(
                    id=self._get_dependency_id(),
                    source_id=causation_node.id,
                    target_id=claim_node.id,
                    dependency_type=DependencyType.DEPENDS_ON,
                    required=True,
                ))
            if not has_causation_signal(claim_text):
                causation_link_node = DependencyNode(
                    id=self._get_node_id(),
                    node_type=NodeType.FACT,
                    name="Retaliation causation link facts",
                    description=(
                        "Facts that directly connect protected activity to the adverse treatment, "
                        "including actors and date anchors for each step"
                    ),
                    satisfied=False,
                    confidence=0.0,
                )
                graph.add_node(causation_link_node)
                graph.add_dependency(Dependency(
                    id=self._get_dependency_id(),
                    source_id=causation_link_node.id,
                    target_id=claim_node.id,
                    dependency_type=DependencyType.DEPENDS_ON,
                    required=True,
                ))

        if has_notice_signal(claim_text) and not has_date(claim_text):
            notice_node = DependencyNode(
                id=self._get_node_id(),
                node_type=NodeType.FACT,
                name="Written notice date",
                description="Date and sender of any written notice, letter, email, or message",
                satisfied=False,
                confidence=0.0,
            )
            graph.add_node(notice_node)
            graph.add_dependency(Dependency(
                id=self._get_dependency_id(),
                source_id=notice_node.id,
                target_id=claim_node.id,
                dependency_type=DependencyType.DEPENDS_ON,
                required=True,
            ))

        if has_hearing_signal(claim_text) and not has_date(claim_text):
            hearing_node = DependencyNode(
                id=self._get_node_id(),
                node_type=NodeType.FACT,
                name="Hearing request date",
                description="Date a hearing/grievance/appeal was requested and any response date",
                satisfied=False,
                confidence=0.0,
            )
            graph.add_node(hearing_node)
            graph.add_dependency(Dependency(
                id=self._get_dependency_id(),
                source_id=hearing_node.id,
                target_id=claim_node.id,
                dependency_type=DependencyType.DEPENDS_ON,
                required=True,
            ))

    self._mark_factual_clarifications(graph)
    graph.metadata["heuristic_law_derived_invoked"] = False
    graph.metadata["legal_requirement_mode"] = (
        "verified_sources" if require_verified_legal_sources else "caller_supplied"
    )
    graph.metadata["legal_source_gaps"] = []

    supplied_requirements = legal_requirements if isinstance(legal_requirements, dict) else {}
    # SummaryJudgmentHook returns dict[str, list[str]]. Those strings are
    # adapted to unresolved entries before this loop. A raw string still
    # must not be stored as a legal element.
    if any(
        isinstance(item, str)
        for items in supplied_requirements.values()
        if isinstance(items, list)
        for item in items
    ):
        from integrations.ipfs_datasets.legal import adapt_sourced_legal_requirements
        supplied_requirements = adapt_sourced_legal_requirements(supplied_requirements)

    # Add legal requirements for each claim. Verified intake never promotes
    # heuristic or template text into a law-derived element.
    if supplied_requirements:
        for claim_node in claim_nodes:
            claim_type = claim_node.attributes.get('claim_type')
            requirements = supplied_requirements.get(claim_type, [])
            if not isinstance(requirements, list):
                requirements = []
            for req_data in requirements:
                if not isinstance(req_data, dict):
                    self._add_unresolved_legal_requirement(
                        graph, claim_node, "ambiguous_authority",
                    )
                    continue
                if self._is_user_law_assertion(req_data) or req_data.get("intake_requirement_status") == "unresolved" or req_data.get("proof_status") in {"unresolved", "not_authoritative"}:
                    self._add_unresolved_legal_requirement(
                        graph,
                        claim_node,
                        str(req_data.get("unresolved_reason") or "ambiguous_authority"),
                        req_data,
                    )
                    continue
                if require_verified_legal_sources and not self._is_verified_legal_requirement(req_data):
                    self._add_unresolved_legal_requirement(
                        graph,
                        claim_node,
                        "ambiguous_or_unverified_authority",
                        req_data,
                    )
                    continue
                self._add_legal_requirement_node(graph, claim_node, req_data)

    if require_verified_legal_sources:
        self._add_legal_source_gaps(graph, claim_nodes)

    logger.info(f"Built dependency graph: {graph.summary()}")
    return graph


def refresh_affected_dependencies(
    self,
    graph: DependencyGraph,
    change: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Recompute dependencies touched by a fact, jurisdiction, date, or rule change.

    Unaffected nodes keep their satisfaction and dependency ids. Affected
    legal satisfaction is marked stale instead of remaining trusted.
    """
    if not isinstance(graph, DependencyGraph):
        return {"affected_node_ids": [], "preserved_node_ids": [], "recomputed_dependency_ids": []}
    payload = change if isinstance(change, dict) else {}
    clarification_keys = {str(item) for item in (payload.get("clarification_keys") or []) if str(item).strip()}
    fact_ids = {str(item) for item in (payload.get("fact_ids") or []) if str(item).strip()}
    rule_ids = {str(item) for item in (payload.get("rule_ids") or []) if str(item).strip()}
    jurisdiction_changed = bool(payload.get("jurisdiction_changed"))
    date_changed = bool(payload.get("date_changed") or payload.get("date_roles"))
    forum_changed = bool(payload.get("forum_changed"))
    applicability_changed = bool(payload.get("applicability_changed"))
    context_changed = bool(payload.get("context_changed"))
    version_changed = bool(payload.get("version_changed") or payload.get("authority_version_changed"))
    treatment_changed = bool(payload.get("treatment_changed") or payload.get("adverse_treatment_changed"))
    definition_changed = bool(payload.get("definition_changed"))
    source_outage = bool(payload.get("source_outage"))
    fact_change = bool(payload.get("fact_change") or fact_ids or clarification_keys)
    updated_requirements = payload.get("updated_requirements") if isinstance(payload.get("updated_requirements"), dict) else {}
    user_facts = {
        node.id: (node.name, node.description, bool(node.satisfied), deepcopy(node.attributes))
        for node in graph.nodes.values()
        if node.node_type == NodeType.FACT or (isinstance(node.attributes, dict) and node.attributes.get("about_complainant") is True and node.attributes.get("dependency_class") != _LEGALLY_SOURCED_CLASS)
    }

    affected_ids = []
    preserved_ids = []
    invalidated = []
    for node in list(graph.nodes.values()):
        if self._dependency_change_affects(
            node, clarification_keys, fact_ids, rule_ids, jurisdiction_changed, date_changed, fact_change,
            version_changed=version_changed, treatment_changed=treatment_changed,
            source_outage=source_outage, definition_changed=definition_changed,
            definition_identity=payload.get("definition_identity"),
            premise_identity=payload.get("premise_identity"),
            adverse_treatment_identity=payload.get("adverse_treatment_identity"),
            forum_changed=forum_changed, applicability_changed=applicability_changed,
            context_changed=context_changed,
        ):
            affected_ids.append(node.id)
        else:
            preserved_ids.append(node.id)

    replaced_rule_ids = []
    if rule_ids and "updated_requirements" in payload:
        replaced_rule_ids = self._replace_changed_rules(graph, rule_ids, updated_requirements)
        affected_ids = [node_id for node_id in affected_ids if node_id in graph.nodes]
        for node in graph.nodes.values():
            scope = node.attributes.get("dependency_scope") if isinstance(node.attributes, dict) else {}
            if isinstance(scope, dict) and str(scope.get("rule_id") or "") in rule_ids and node.id not in affected_ids:
                affected_ids.append(node.id)
        preserved_ids = [node_id for node_id in graph.nodes if node_id not in set(affected_ids)]

    recomputed = []
    preserved_dependency_ids = []
    affected_set = set(affected_ids)
    rewritten: Dict[str, Dependency] = {}
    for dependency_id, dependency in list(graph.dependencies.items()):
        touches = dependency.source_id in affected_set or dependency.target_id in affected_set
        if not touches:
            rewritten[dependency_id] = dependency
            preserved_dependency_ids.append(dependency_id)
            continue
        recomputed_id = self._get_dependency_id()
        rewritten[recomputed_id] = Dependency(
            id=recomputed_id,
            source_id=dependency.source_id,
            target_id=dependency.target_id,
            dependency_type=dependency.dependency_type,
            required=dependency.required,
            strength=dependency.strength,
        )
        recomputed.append({
            "previous_id": dependency_id,
            "id": recomputed_id,
            "source_id": dependency.source_id,
            "target_id": dependency.target_id,
        })
    if recomputed:
        graph.dependencies = rewritten

    for node_id in affected_ids:
        node = graph.nodes.get(node_id)
        if node is None or not isinstance(node.attributes, dict):
            continue
        prior_satisfied = bool(node.satisfied)
        if prior_satisfied or node.attributes.get("satisfaction_state") == "satisfied":
            node.attributes["invalidated_satisfaction"] = {
                "satisfied": prior_satisfied,
                "confidence": node.confidence,
                "satisfaction_state": node.attributes.get("satisfaction_state"),
            }
            node.satisfied = False
            node.attributes["satisfaction_state"] = "invalidated"
            node.attributes["stale_satisfaction"] = True
            invalidated.append(node_id)
        node.attributes["satisfaction_revision"] = int(node.attributes.get("satisfaction_revision") or 0) + 1
        node.attributes["dependency_recomputed"] = True
        if (version_changed or treatment_changed or source_outage or definition_changed
                or context_changed or forum_changed or applicability_changed):
            node.attributes["legal_support_invalidated"] = True
            node.attributes["support_eligible"] = False
            if source_outage:
                node.attributes["invalidation_reason"] = "source_outage"
                node.attributes["source_available"] = False
            elif version_changed:
                node.attributes["invalidation_reason"] = "authority_version_changed"
            elif definition_changed:
                node.attributes["invalidation_reason"] = "definition_changed"
            elif treatment_changed:
                node.attributes["invalidation_reason"] = "treatment_changed"
            elif jurisdiction_changed:
                node.attributes["invalidation_reason"] = "jurisdiction_changed"
            elif date_changed:
                node.attributes["invalidation_reason"] = "date_changed"
            elif forum_changed:
                node.attributes["invalidation_reason"] = "forum_changed"
            elif applicability_changed:
                node.attributes["invalidation_reason"] = "applicability_changed"
            elif context_changed:
                node.attributes["invalidation_reason"] = "legal_context_changed"
        if node.attributes.get("dependency_class") == _LEGALLY_SOURCED_CLASS:
            self._recompute_support_proof_and_question_targets(node)
        if node.attributes.get("proof_cache_identity"):
            node.attributes["rejected_proof_cache_identity"] = node.attributes.get("proof_cache_identity")
            node.attributes["proof_cache_reusable"] = False
            if isinstance(node.attributes.get("proof_cache"), dict):
                node.attributes["proof_cache"]["reusable"] = False
                node.attributes["proof_cache"]["satisfied"] = False

    chronology_issue = str(payload.get("chronology_issue") or "").strip().lower()
    if chronology_issue in {"contradictory_dates", "relative_only_ordering"}:
        from integrations.ipfs_datasets.logic import chronology_follow_ups

        follow_ups = chronology_follow_ups(chronology_issue)
        for node in graph.nodes.values():
            attributes = node.attributes if isinstance(node.attributes, dict) else {}
            scope = attributes.get("dependency_scope") if isinstance(attributes.get("dependency_scope"), dict) else {}
            if not (attributes.get("timeline_fact_node") or attributes.get("date_sensitive") or scope.get("date_sensitive")):
                continue
            if node.satisfied or attributes.get("satisfaction_state") == "satisfied":
                attributes["invalidated_satisfaction"] = {
                    "satisfied": bool(node.satisfied),
                    "confidence": node.confidence,
                    "satisfaction_state": attributes.get("satisfaction_state"),
                }
            node.satisfied = False
            attributes["satisfaction_state"] = "uncertain"
            attributes["stale_satisfaction"] = True
            attributes["proof_cache_reusable"] = False
            attributes["chronology_issue"] = chronology_issue
            attributes["recommended_follow_ups"] = follow_ups
            if node.id not in affected_ids:
                affected_ids.append(node.id)
                invalidated.append(node.id)
        affected_set = set(affected_ids)

    report = {
        "affected_node_ids": list(affected_ids),
        "preserved_node_ids": [node_id for node_id in graph.nodes if node_id not in affected_set],
        "invalidated_node_ids": invalidated,
        "recomputed_dependencies": recomputed,
        "preserved_dependency_ids": preserved_dependency_ids,
        "replaced_rule_ids": replaced_rule_ids,
        "jurisdiction_changed": jurisdiction_changed,
        "date_changed": date_changed,
        "forum_changed": forum_changed,
        "applicability_changed": applicability_changed,
        "context_changed": context_changed,
        "fact_change": fact_change,
        "fact_ids": sorted(fact_ids),
        "factual_revision": payload.get("factual_revision"),
        "version_changed": version_changed,
        "treatment_changed": treatment_changed,
        "definition_changed": definition_changed,
        "source_outage": source_outage,
        "user_facts_modified": False,
        "graph_replaced": False,
        "empty_success": False,
    }
    if (version_changed or treatment_changed or source_outage or definition_changed) and not chronology_issue:
        for node_id, (name, description, satisfied, attributes) in user_facts.items():
            node = graph.nodes.get(node_id)
            if node is None:
                report["user_facts_modified"] = True
                continue
            if node.name != name or node.description != description or bool(node.satisfied) != satisfied or node.attributes != attributes:
                node.name = name
                node.description = description
                node.satisfied = satisfied
                node.attributes = attributes
            if node_id in report["affected_node_ids"]:
                report["affected_node_ids"] = [item for item in report["affected_node_ids"] if item != node_id]
                report["invalidated_node_ids"] = [item for item in report["invalidated_node_ids"] if item != node_id]
                if node_id not in report["preserved_node_ids"]:
                    report["preserved_node_ids"].append(node_id)
    if graph.metadata.get("legal_requirement_mode") == "verified_sources":
        self._refresh_legal_source_gaps(graph)
    if source_outage:
        graph.metadata["source_outage"] = True
        graph.metadata["empty_success"] = False
        graph.metadata["admission_status"] = "unavailable"
    graph.metadata["last_dependency_refresh"] = {
        "affected_count": len(affected_ids),
        "preserved_count": len(report["preserved_node_ids"]),
        "recomputed_count": len(recomputed),
    }
    graph._update_metadata()
    return report
