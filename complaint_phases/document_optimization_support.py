"""Support-context construction delegated from AgenticDocumentOptimizer."""

from __future__ import annotations

from complaint_phases.document_optimization import (
    ComplaintPhase,
    _INTAKE_OBJECTIVE_PRIORITY,
    _OBJECTIVE_PROMPTS,
    _build_anchored_chronology_summary,
    _build_blocker_prompt,
    _build_claim_temporal_gap_hints,
    _clamp,
    _dedupe_text_values,
    _normalize_blocker_records,
    _normalize_intake_objective,
    _normalize_intake_objectives,
    _safe_float,
    _safe_int,
    _unique_preserving_order,
    build_intake_case_review_summary,
    build_intake_status_summary,
    summarize_temporal_issue_registry,
)


def _build_support_context(
    self,
    *,
    user_id: Optional[str],
    draft: Dict[str, Any],
    drafting_readiness: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    config_payload = config if isinstance(config, dict) else {}
    claims = draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []
    claim_entries = drafting_readiness.get("claims") if isinstance(drafting_readiness.get("claims"), list) else []
    readiness_by_claim = {}
    for entry in claim_entries:
        if not isinstance(entry, dict):
            continue
        claim_type = str(entry.get("claim_type") or "").strip()
        if claim_type:
            readiness_by_claim[claim_type] = entry

    support_summary_payload = self._call_mediator("summarize_claim_support", user_id=user_id) or {}
    support_summary_claims = support_summary_payload.get("claims") if isinstance(support_summary_payload, dict) else {}
    support_summary_claims = support_summary_claims if isinstance(support_summary_claims, dict) else {}

    evidence_rows = self._call_mediator("get_user_evidence", user_id=user_id) or []
    evidence_summaries = []
    for row in evidence_rows if isinstance(evidence_rows, list) else []:
        if not isinstance(row, dict):
            continue
        text = str(row.get("parsed_text_preview") or row.get("description") or row.get("title") or "").strip()
        if not text:
            continue
        evidence_summaries.append(
            {
                "claim_type": str(row.get("claim_type") or "").strip(),
                "text": text,
                "cid": str(row.get("cid") or "").strip(),
                "type": str(row.get("type") or "").strip(),
            }
        )

    phase_manager = getattr(self.mediator, "phase_manager", None)
    intake_case_file = {}
    if phase_manager is not None and hasattr(phase_manager, "get_phase_data"):
        try:
            intake_case_file = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file") or {}
        except Exception:
            intake_case_file = {}
    intake_case_file = intake_case_file if isinstance(intake_case_file, dict) else {}
    intake_case_summary = build_intake_case_review_summary(self.mediator)
    intake_case_summary = intake_case_summary if isinstance(intake_case_summary, dict) else {}
    fallback_temporal_issue_registry_summary = summarize_temporal_issue_registry(
        intake_case_summary.get("temporal_issue_registry_summary")
    )
    fallback_packet_summary = (
        intake_case_summary.get("claim_support_packet_summary")
        if isinstance(intake_case_summary.get("claim_support_packet_summary"), dict)
        else {}
    )
    fallback_alignment_task_summary = (
        intake_case_summary.get("alignment_task_summary")
        if isinstance(intake_case_summary.get("alignment_task_summary"), dict)
        else {}
    )

    claim_contexts = []
    claim_temporal_gap_summary = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        claim_type = str(claim.get("claim_type") or claim.get("count_title") or "").strip()
        claim_name = str(claim.get("count_title") or claim.get("claim_type") or "").strip()
        support_facts = self._call_mediator("get_claim_support_facts", claim_type=claim_type, user_id=user_id) or []
        overview = self._call_mediator("get_claim_overview", claim_type=claim_type, user_id=user_id) or {}
        overview_claim = {}
        if isinstance(overview, dict):
            overview_claims = overview.get("claims") if isinstance(overview.get("claims"), dict) else {}
            overview_claim = overview_claims.get(claim_type) if isinstance(overview_claims.get(claim_type), dict) else {}
        support_summary = support_summary_claims.get(claim_type) if isinstance(support_summary_claims.get(claim_type), dict) else {}
        readiness_entry = readiness_by_claim.get(claim_type, {})
        support_texts = self._extract_support_texts(support_facts)
        temporal_gap_hints = _build_claim_temporal_gap_hints(
            intake_case_file,
            claim_type=claim_type,
            claim_name=claim_name,
        )
        missing_elements = _unique_preserving_order(
            [
                *self._extract_element_texts(overview_claim.get("missing")),
                *self._normalize_lines(claim.get("missing_elements") or []),
                *temporal_gap_hints,
            ]
        )
        claim_contexts.append(
            {
                "claim_type": claim_type,
                "missing_elements": missing_elements,
                "partially_supported_elements": self._extract_element_texts(overview_claim.get("partially_supported")),
                "proof_gap_count": int(readiness_entry.get("proof_gap_count") or 0),
                "temporal_gap_hint_count": int(
                    claim.get("support_summary", {}).get("temporal_gap_hint_count") or len(temporal_gap_hints)
                ),
                "support_summary": {
                    "total_elements": int(support_summary.get("total_elements") or claim.get("support_summary", {}).get("total_elements") or 0),
                    "covered_elements": int(support_summary.get("covered_elements") or claim.get("support_summary", {}).get("covered_elements") or 0),
                    "uncovered_elements": int(support_summary.get("uncovered_elements") or claim.get("support_summary", {}).get("uncovered_elements") or 0),
                    "source_family_counts": dict(support_summary.get("support_packet_summary", {}).get("source_family_counts") or claim.get("support_summary", {}).get("source_family_counts") or {}),
                    "temporal_gap_hint_count": int(
                        claim.get("support_summary", {}).get("temporal_gap_hint_count") or len(temporal_gap_hints)
                    ),
                },
                "support_facts": support_texts[:8],
                "readiness_warnings": [
                    str(item.get("message") or "").strip()
                    for item in readiness_entry.get("warnings", [])
                    if isinstance(item, dict) and str(item.get("message") or "").strip()
                ],
            }
        )
        if temporal_gap_hints:
            claim_temporal_gap_summary.append(
                {
                    "claim_type": claim_type,
                    "gap_count": len(temporal_gap_hints),
                    "gaps": temporal_gap_hints,
                }
            )

    intake_status = build_intake_status_summary(self.mediator)
    workflow_guidance = (
        drafting_readiness.get("workflow_optimization_guidance")
        if isinstance(drafting_readiness.get("workflow_optimization_guidance"), dict)
        else {}
    )
    document_drafting_next_action = (
        workflow_guidance.get("document_drafting_next_action")
        if isinstance(workflow_guidance.get("document_drafting_next_action"), dict)
        else intake_status.get("document_drafting_next_action")
    )
    document_drafting_next_action = (
        dict(document_drafting_next_action)
        if isinstance(document_drafting_next_action, dict)
        else {}
    )
    document_grounding_improvement_next_action = (
        workflow_guidance.get("document_grounding_improvement_next_action")
        if isinstance(workflow_guidance.get("document_grounding_improvement_next_action"), dict)
        else intake_status.get("document_grounding_improvement_next_action")
    )
    document_grounding_improvement_next_action = (
        dict(document_grounding_improvement_next_action)
        if isinstance(document_grounding_improvement_next_action, dict)
        else {}
    )
    intake_handoff = intake_status.get("intake_summary_handoff") if isinstance(intake_status, dict) else {}
    intake_handoff = intake_handoff if isinstance(intake_handoff, dict) else {}
    blocker_follow_up_summary = intake_case_file.get("blocker_follow_up_summary") if isinstance(intake_case_file.get("blocker_follow_up_summary"), dict) else {}
    blocker_items = _normalize_blocker_records(blocker_follow_up_summary.get("blocking_items"))
    open_items = _normalize_blocker_records(intake_case_file.get("open_items"))
    blocker_open_items = [
        item for item in open_items
        if str(item.get("kind") or "").strip().lower() == "blocker_follow_up"
    ]
    confirmation = (
        intake_handoff.get("complainant_summary_confirmation")
        if isinstance(intake_handoff.get("complainant_summary_confirmation"), dict)
        else {}
    )
    confirmation_snapshot = (
        confirmation.get("confirmed_summary_snapshot")
        if isinstance(confirmation.get("confirmed_summary_snapshot"), dict)
        else {}
    )
    intake_priority_summary = (
        confirmation_snapshot.get("adversarial_intake_priority_summary")
        if isinstance(confirmation_snapshot.get("adversarial_intake_priority_summary"), dict)
        else {}
    )

    covered_objectives = _normalize_intake_objectives(intake_priority_summary.get("covered_objectives") or [])
    uncovered_objectives = _normalize_intake_objectives(intake_priority_summary.get("uncovered_objectives") or [])
    objective_question_counts = {
        _normalize_intake_objective(key): int(value or 0)
        for key, value in dict(intake_priority_summary.get("objective_question_counts") or {}).items()
        if _normalize_intake_objective(key)
    }
    objective_question_counts = {
        key: value
        for key, value in objective_question_counts.items()
        if key
    }
    blocker_objectives = _normalize_intake_objectives(
        list(blocker_follow_up_summary.get("blocking_objectives") or [])
        + [objective for blocker in blocker_items for objective in list(blocker.get("blocker_objectives") or [])]
        + [item.get("primary_objective") for item in blocker_open_items]
    )
    blocker_extraction_targets = _dedupe_text_values(
        list(blocker_follow_up_summary.get("extraction_targets") or [])
        + [target for blocker in blocker_items for target in list(blocker.get("extraction_targets") or [])]
        + [target for item in blocker_open_items for target in list(item.get("extraction_targets") or [])]
    )
    blocker_workflow_phases = _dedupe_text_values(
        list(blocker_follow_up_summary.get("workflow_phases") or [])
        + [phase for blocker in blocker_items for phase in list(blocker.get("workflow_phases") or [])]
        + [phase for item in blocker_open_items for phase in list(item.get("workflow_phases") or [])]
    )
    blocker_issue_families = _dedupe_text_values(
        [blocker.get("issue_family") for blocker in blocker_items]
        + [item.get("issue_family") for item in blocker_open_items]
    )
    unresolved_objectives = _dedupe_text_values(
        list(uncovered_objectives)
        + list(blocker_objectives)
        + [key for key, count in objective_question_counts.items() if count <= 0]
    )
    critical_unresolved = [
        objective
        for objective in _INTAKE_OBJECTIVE_PRIORITY
        if objective in unresolved_objectives
    ]
    blocker_follow_up_prompts = _dedupe_text_values(
        [_build_blocker_prompt(blocker) for blocker in blocker_items]
        + [_build_blocker_prompt(item) for item in blocker_open_items]
    )
    anchored_chronology_summary = _build_anchored_chronology_summary(intake_case_file)
    temporal_issue_registry = intake_case_file.get("temporal_issue_registry") if isinstance(intake_case_file.get("temporal_issue_registry"), list) else []
    case_file_temporal_issue_registry_summary = summarize_temporal_issue_registry(
        {
            "count": len(temporal_issue_registry),
            "issues": temporal_issue_registry,
        }
    )
    temporal_issue_status_counts = dict(fallback_temporal_issue_registry_summary.get("status_counts") or {})
    for status_name, count in dict(case_file_temporal_issue_registry_summary.get("status_counts") or {}).items():
        temporal_issue_status_counts[str(status_name)] = max(
            int(temporal_issue_status_counts.get(str(status_name)) or 0),
            int(count or 0),
        )
    unresolved_temporal_issue_count = max(
        int(case_file_temporal_issue_registry_summary.get("unresolved_count") or 0),
        int(fallback_temporal_issue_registry_summary.get("unresolved_count") or 0),
        int(fallback_packet_summary.get("claim_support_unresolved_temporal_issue_count") or 0),
    )
    resolved_temporal_issue_count = max(
        int(case_file_temporal_issue_registry_summary.get("resolved_count") or 0),
        int(fallback_temporal_issue_registry_summary.get("resolved_count") or 0),
    )
    temporal_issue_count = max(
        len(temporal_issue_registry),
        int(case_file_temporal_issue_registry_summary.get("count") or 0),
        int(fallback_temporal_issue_registry_summary.get("count") or 0),
        unresolved_temporal_issue_count + resolved_temporal_issue_count,
    )

    metric_aliases = {
        "empathy_avg": "empathy",
        "avg_empathy": "empathy",
        "question_quality_avg": "question_quality",
        "avg_question_quality": "question_quality",
        "information_extraction_avg": "information_extraction",
        "avg_information_extraction": "information_extraction",
        "coverage_avg": "coverage",
        "avg_coverage": "coverage",
        "efficiency_avg": "efficiency",
        "avg_efficiency": "efficiency",
    }
    raw_baseline_metrics = (
        config_payload.get("baseline_metrics")
        if isinstance(config_payload.get("baseline_metrics"), dict)
        else {}
    )
    baseline_metrics: Dict[str, float] = {}
    for raw_key, raw_value in dict(raw_baseline_metrics).items():
        key = metric_aliases.get(str(raw_key).strip().lower(), str(raw_key).strip().lower())
        if key not in {"empathy", "question_quality", "information_extraction", "coverage", "efficiency"}:
            continue
        baseline_metrics[key] = _clamp(_safe_float(raw_value, 0.0))

    actor_critic_priority = 70
    for candidate in (
        config_payload.get("priority"),
        config_payload.get("actor_critic_priority"),
        (config_payload.get("actor_critic_optimizer") or {}).get("priority")
        if isinstance(config_payload.get("actor_critic_optimizer"), dict)
        else None,
    ):
        if candidate is None:
            continue
        try:
            actor_critic_priority = max(1, min(100, int(candidate)))
            break
        except Exception:
            continue

    warning_messages = [
        str((warning or {}).get("message") or "")
        for warning in (drafting_readiness.get("warnings") or [])
        if isinstance(warning, dict)
    ]
    readiness_blockers = _dedupe_text_values(
        str(item).strip()
        for item in list(drafting_readiness.get("blockers") or [])
        if str(item).strip()
    )
    unresolved_factual_gaps = self._normalize_lines(
        list(drafting_readiness.get("unresolved_factual_gaps") or [])
    )
    unresolved_legal_gaps = self._normalize_lines(
        list(drafting_readiness.get("unresolved_legal_gaps") or [])
    )
    graph_signals = (
        dict(drafting_readiness.get("graph_completeness_signals") or {})
        if isinstance(drafting_readiness.get("graph_completeness_signals"), dict)
        else {}
    )
    graph_status = str(graph_signals.get("status") or "ready").strip().lower() or "ready"
    graph_remaining_gap_count = max(
        int(graph_signals.get("remaining_gap_count", 0) or 0),
        int(graph_signals.get("current_gap_count", 0) or 0),
    )
    graph_gate_active = any(
        (
            graph_status != "ready",
            graph_remaining_gap_count > 0,
            graph_signals and not bool(graph_signals.get("knowledge_graph_available", True)),
            graph_signals and not bool(graph_signals.get("dependency_graph_available", True)),
        )
    )
    workflow_phase_plan = (
        config_payload.get("workflow_phase_plan")
        if isinstance(config_payload.get("workflow_phase_plan"), dict)
        else {}
    )
    phase_payloads = (
        workflow_phase_plan.get("phases")
        if isinstance(workflow_phase_plan.get("phases"), dict)
        else {}
    )
    document_phase = (
        phase_payloads.get("document_generation")
        if isinstance(phase_payloads.get("document_generation"), dict)
        else {}
    )
    document_signals = (
        document_phase.get("signals")
        if isinstance(document_phase.get("signals"), dict)
        else {}
    )
    document_summary = str(document_phase.get("summary") or "").strip()
    summary_candidates = [
        document_summary,
        str(config_payload.get("phase_goal") or "").strip(),
        str(config_payload.get("document_phase_goal") or "").strip(),
        *warning_messages,
    ]
    no_success_signal = any(
        "no successful sessions" in value.lower() and "drafting handoff" in value.lower()
        for value in summary_candidates
        if value
    )

    successful_session_count = max(
        0,
        _safe_int(document_signals.get("adversarial_successful_session_count"), 0),
        _safe_int(config_payload.get("successful_session_count"), 0),
        _safe_int(config_payload.get("successful_sessions"), 0),
        _safe_int((config_payload.get("adversarial_batch") or {}).get("successful_session_count"), 0)
        if isinstance(config_payload.get("adversarial_batch"), dict)
        else 0,
    )
    session_count = max(
        0,
        _safe_int(document_signals.get("adversarial_session_count"), 0),
        _safe_int(config_payload.get("session_count"), 0),
        _safe_int(config_payload.get("sessions"), 0),
        _safe_int((config_payload.get("adversarial_batch") or {}).get("session_count"), 0)
        if isinstance(config_payload.get("adversarial_batch"), dict)
        else 0,
    )
    phase_status = (
        str(document_phase.get("status") or "").strip().lower()
        or str(drafting_readiness.get("phase_status") or drafting_readiness.get("status") or "ready").strip().lower()
    )
    coverage = max(
        0.0,
        _safe_float(document_signals.get("drafting_coverage"), -1.0),
        _safe_float(config_payload.get("coverage"), -1.0),
        _safe_float(drafting_readiness.get("coverage"), -1.0),
    )
    if coverage < 0.0:
        coverage = 0.0
    session_flow_stable = bool(document_signals.get("adversarial_session_flow_stable")) if "adversarial_session_flow_stable" in document_signals else True
    has_session_flow_signal = any(
        (
            no_success_signal,
            session_count > 0,
            phase_status == "critical",
            not session_flow_stable,
            bool(document_phase),
        )
    )
    assessment_blocked = (
        successful_session_count <= 0
        and has_session_flow_signal
        and (
            no_success_signal
            or session_count > 0
            or phase_status == "critical"
            or coverage <= 0.0
            or not session_flow_stable
        )
    )
    if graph_gate_active or unresolved_factual_gaps or unresolved_legal_gaps:
        assessment_blocked = True
    gating_blockers = _dedupe_text_values(
        list(readiness_blockers)
        + (["uncovered_intake_objectives"] if unresolved_objectives else [])
        + (["graph_analysis_not_ready"] if graph_gate_active else [])
        + (
            ["document_generation_not_ready"]
            if (
                phase_status in {"warning", "blocked", "critical"}
                or unresolved_objectives
                or unresolved_factual_gaps
                or unresolved_legal_gaps
                or assessment_blocked
            )
            else []
        )
    )
    recommended_actions = _dedupe_text_values(
        [
            *[
                str((action or {}).get("recommended_action") or "").strip()
                for action in list(document_phase.get("recommended_actions") or [])
                if isinstance(action, dict)
            ],
            *[
                str(action).strip()
                for action in list(config_payload.get("recommended_actions") or [])
                if str(action).strip()
            ],
            "Promote blocker-closing intake answers into factual allegations, claim support, and exhibit descriptions before formalization."
            if unresolved_objectives
            else "",
            "Close graph completeness blockers and unresolved chronology dependencies before document-generation optimization."
            if graph_gate_active
            else "",
            "Resolve unresolved factual and legal readiness gaps before formalization."
            if (unresolved_factual_gaps or unresolved_legal_gaps)
            else "",
            "Restore a stable adversarial session flow before tuning document-generation handoffs."
            if assessment_blocked
            else "",
        ]
    )
    actor_critic_metrics = {
        "empathy": _clamp(baseline_metrics.get("empathy", 0.0)),
        "question_quality": _clamp(baseline_metrics.get("question_quality", 0.0)),
        "information_extraction": _clamp(baseline_metrics.get("information_extraction", 0.0)),
        "coverage": _clamp(baseline_metrics.get("coverage", coverage)),
        "efficiency": _clamp(baseline_metrics.get("efficiency", 0.0)),
    }
    canonical_facts = [
        dict(item)
        for item in list(intake_case_file.get("canonical_facts") or [])
        if isinstance(item, dict)
    ]
    timeline_fact_lines: List[str] = []
    claim_support_lines_by_type: Dict[str, List[str]] = {}
    claim_support_shared: List[str] = []
    blocker_closing_answers: List[str] = []
    for fact in canonical_facts:
        fact_text = str(fact.get("text") or "").strip()
        if not fact_text:
            continue
        timeline_fact_lines.append(fact_text)
        lower_text = fact_text.lower()
        if any(token in lower_text for token in ("because", "after", "as a result", "retaliat", "responded", "hearing", "review")):
            claim_support_shared.append(fact_text)
        claim_types_for_fact = _dedupe_text_values(
            list(fact.get("claim_types") or [])
            + [fact.get("claim_type")]
            + [fact.get("supports_claim_type")]
        )
        for claim_type in claim_types_for_fact:
            key = str(claim_type).strip().lower()
            if not key:
                continue
            claim_support_lines_by_type.setdefault(key, [])
            claim_support_lines_by_type[key].append(fact_text)
    blocker_closing_answers.extend(blocker_follow_up_prompts)
    blocker_closing_answers.extend(
        str(item.get("reason") or "").strip()
        for item in blocker_items
        if str(item.get("reason") or "").strip()
    )
    blocker_closing_answers.extend(anchored_chronology_summary)
    evidence_reference_lines = self._normalize_lines(
        [
            (
                f"Exhibit evidence ({row.get('type') or 'evidence'}; cid {row.get('cid')}) supports the chronology and actor sequence: {row.get('text')}."
                if row.get("cid")
                else f"Exhibit evidence ({row.get('type') or 'evidence'}) supports the chronology and actor sequence: {row.get('text')}."
            )
            for row in evidence_summaries[:8]
            if isinstance(row, dict) and str(row.get("text") or "").strip()
        ]
    )
    structured_handoff = {
        "factual_allegation_lines": self._normalize_lines(
            timeline_fact_lines + anchored_chronology_summary + blocker_closing_answers + evidence_reference_lines
        )[:14],
        "summary_of_facts_lines": self._normalize_lines(
            anchored_chronology_summary + timeline_fact_lines + evidence_reference_lines
        )[:12],
        "claim_support_lines_by_type": {
            key: self._normalize_lines(values)[:8]
            for key, values in claim_support_lines_by_type.items()
            if key
        },
        "claim_support_lines_shared": self._normalize_lines(
            claim_support_shared + anchored_chronology_summary + evidence_reference_lines
        )[:10],
        "blocker_closing_answers": self._normalize_lines(blocker_closing_answers)[:10],
        "exhibit_description_lines": evidence_reference_lines[:8],
        "unresolved_objectives": unresolved_objectives[:8],
        "unresolved_factual_gaps": unresolved_factual_gaps[:6],
        "unresolved_legal_gaps": unresolved_legal_gaps[:6],
    }

    return {
        "claims": claim_contexts,
        "evidence": evidence_summaries[:10],
        "sections": dict(drafting_readiness.get("sections") or {}) if isinstance(drafting_readiness, dict) else {},
        "packet_projection": self._build_packet_projection(draft),
        "structured_handoff": structured_handoff,
        "actor_critic": {
            "priority": actor_critic_priority,
            "baseline_metrics": baseline_metrics,
            "metrics": actor_critic_metrics,
        },
        "document_generation_guardrail": {
            "phase_status": phase_status or "ready",
            "coverage": _clamp(coverage),
            "successful_session_count": successful_session_count,
            "session_count": session_count,
            "assessment_blocked": assessment_blocked,
            "gate_on_graph_completeness": bool(graph_gate_active),
            "graph_phase_status": graph_status,
            "graph_remaining_gap_count": int(graph_remaining_gap_count),
            "blockers": gating_blockers,
            "unresolved_factual_gaps": unresolved_factual_gaps[:6],
            "unresolved_legal_gaps": unresolved_legal_gaps[:6],
            "summary": (
                "Formalization gate is active: unresolved graph/document blockers must be closed before complaint generation."
                if assessment_blocked
                else ""
            ),
            "recommended_actions": recommended_actions,
            "priority": actor_critic_priority,
        },
        "workflow_targeting_summary": dict(
            (workflow_guidance.get("workflow_targeting_summary") or {})
            if isinstance(workflow_guidance, dict)
            else {}
        ),
        "evidence_workflow_action_queue": list(
            (workflow_guidance.get("evidence_workflow_action_queue") or [])
            if isinstance(workflow_guidance, dict)
            else []
        ),
        "evidence_workflow_action_summary": dict(
            (workflow_guidance.get("evidence_workflow_action_summary") or {})
            if isinstance(workflow_guidance, dict)
            else {}
        ),
        "workflow_action_queue": list(
            (workflow_guidance.get("workflow_action_queue") or [])
            if isinstance(workflow_guidance, dict)
            else []
        ),
        "document_drafting_next_action": document_drafting_next_action,
        "document_grounding_improvement_next_action": document_grounding_improvement_next_action,
        "intake_priorities": {
            "covered_objectives": covered_objectives,
            "uncovered_objectives": uncovered_objectives,
            "objective_question_counts": objective_question_counts,
            "unresolved_objectives": unresolved_objectives,
            "critical_unresolved_objectives": critical_unresolved,
            "blocker_count": int(blocker_follow_up_summary.get("blocking_item_count") or len(blocker_items) or 0),
            "blocker_items": blocker_items,
            "blocker_open_items": blocker_open_items,
            "blocking_objectives": blocker_objectives,
            "blocker_extraction_targets": blocker_extraction_targets,
            "blocker_workflow_phases": blocker_workflow_phases,
            "blocker_issue_families": blocker_issue_families,
            "anchored_chronology_summary": anchored_chronology_summary,
            "temporal_issue_count": temporal_issue_count,
            "unresolved_temporal_issue_count": unresolved_temporal_issue_count,
            "resolved_temporal_issue_count": resolved_temporal_issue_count,
            "temporal_issue_status_counts": temporal_issue_status_counts,
            "claim_temporal_gap_count": max(
                sum(
                int(item.get("gap_count") or 0)
                for item in claim_temporal_gap_summary
                if isinstance(item, dict)
                ),
                int(fallback_alignment_task_summary.get("temporal_gap_task_count") or 0),
            ),
            "claim_temporal_gap_summary": claim_temporal_gap_summary,
            "recommended_follow_up_prompts": [
                _OBJECTIVE_PROMPTS[objective]
                for objective in critical_unresolved
                if objective in _OBJECTIVE_PROMPTS
            ] + blocker_follow_up_prompts,
        },
        "capabilities": self._router_status(),
    }
