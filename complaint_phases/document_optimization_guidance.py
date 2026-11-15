"""Optimization guidance delegated from AgenticDocumentOptimizer."""

from __future__ import annotations

from typing import Any, Dict, List

from complaint_phases.document_optimization import (
    _clamp,
    _dedupe_text_values,
    _normalize_intake_objective,
    _safe_float,
    _sorted_count_items,
    _unique_preserving_order,
    summarize_temporal_issue_registry,
)


def _build_workflow_optimization_guidance(
    self,
    *,
    drafting_readiness: Dict[str, Any],
    support_context: Dict[str, Any],
    intake_status: Dict[str, Any],
    intake_case_summary: Dict[str, Any],
    claim_reasoning_review: Dict[str, Any],
    claim_support_temporal_handoff: Dict[str, Any],
) -> Dict[str, Any]:
    intake_sections = (
        intake_case_summary.get("intake_sections")
        if isinstance(intake_case_summary.get("intake_sections"), dict)
        else {}
    )
    question_summary = (
        intake_case_summary.get("question_candidate_summary")
        if isinstance(intake_case_summary.get("question_candidate_summary"), dict)
        else {}
    )
    evidence_summary = (
        intake_case_summary.get("proof_lead_summary")
        if isinstance(intake_case_summary.get("proof_lead_summary"), dict)
        else {}
    )
    evidence_workflow_action_queue = (
        intake_case_summary.get("evidence_workflow_action_queue")
        if isinstance(intake_case_summary.get("evidence_workflow_action_queue"), list)
        else []
    )
    evidence_workflow_action_summary = (
        intake_case_summary.get("evidence_workflow_action_summary")
        if isinstance(intake_case_summary.get("evidence_workflow_action_summary"), dict)
        else {}
    )
    evidence_rows = support_context.get("evidence") if isinstance(support_context.get("evidence"), list) else []
    evidence_modalities = _unique_preserving_order(
        str((row or {}).get("type") or "").strip() for row in evidence_rows if isinstance(row, dict)
    )
    temporal_issue_registry_summary = summarize_temporal_issue_registry(
        intake_case_summary.get("temporal_issue_registry_summary")
    )
    unresolved_temporal_issue_count = int(temporal_issue_registry_summary.get("unresolved_count") or 0)
    resolved_temporal_issue_count = int(temporal_issue_registry_summary.get("resolved_count") or 0)
    claim_types = _unique_preserving_order(
        [
            *[
                str((claim or {}).get("claim_type") or "").strip()
                for claim in (support_context.get("claims") or [])
                if isinstance(claim, dict)
            ],
            *[
                str((claim or {}).get("claim_type") or "").strip()
                for claim in (intake_case_summary.get("candidate_claims") or [])
                if isinstance(claim, dict)
            ],
        ]
    )
    uncovered_objectives = _dedupe_text_values(
        (support_context.get("intake_priorities") or {}).get("uncovered_objectives") or []
    )
    intake_focus_areas = _unique_preserving_order(
        [
            *[
                str(section_name)
                for section_name, section_payload in intake_sections.items()
                if isinstance(section_payload, dict) and str(section_payload.get("status") or "").strip().lower() != "complete"
            ],
            *uncovered_objectives,
        ]
    )
    graph_focus_areas = _unique_preserving_order(
        [
            *[
                str((claim or {}).get("claim_type") or "").strip()
                for claim in (support_context.get("claims") or [])
                if isinstance(claim, dict) and (
                    claim.get("missing_elements") or claim.get("partially_supported_elements")
                )
            ],
            *[
                str(item)
                for item in (claim_support_temporal_handoff.get("temporal_proof_objectives") or [])
                if str(item).strip()
            ],
            *[
                str((action or {}).get("claim_element_label") or (action or {}).get("claim_element_id") or "").strip()
                for action in evidence_workflow_action_queue
                if isinstance(action, dict)
            ],
        ]
    )
    draft_warnings = [
        str((warning or {}).get("message") or "").strip()
        for warning in (drafting_readiness.get("warnings") or [])
        if isinstance(warning, dict) and str((warning or {}).get("message") or "").strip()
    ]
    document_focus_areas = _unique_preserving_order(
        [
            *[
                str(section_name)
                for section_name, section_payload in dict(drafting_readiness.get("sections") or {}).items()
                if isinstance(section_payload, dict) and str(section_payload.get("status") or "").strip().lower() != "ready"
            ],
            *draft_warnings,
        ]
    )
    cross_phase_findings: List[str] = []
    if intake_focus_areas and graph_focus_areas:
        cross_phase_findings.append(
            "Unresolved intake objectives are still suppressing graph-ready claim support and should be closed before final drafting."
        )
    if graph_focus_areas and document_focus_areas:
        cross_phase_findings.append(
            "Graph support gaps are flowing through into document readiness warnings, so claim support and chronology gaps should be resolved before final complaint export."
        )
    if claim_support_temporal_handoff.get("unresolved_temporal_issue_count"):
        cross_phase_findings.append(
            "Temporal support gaps remain unresolved and may weaken both causation analysis and chronology-driven complaint allegations."
        )
    elif resolved_temporal_issue_count > 0:
        cross_phase_findings.append(
            "Resolved chronology history is retained and should still be preserved in factual allegations and claim support to maintain the causation sequence."
        )

    return {
        "phase_scorecards": {
            "intake_questioning": {
                "status": "warning" if intake_focus_areas else "ready",
                "focus_areas": intake_focus_areas,
                "question_candidate_count": int(question_summary.get("count") or 0),
                "proof_lead_count": int(evidence_summary.get("count") or 0),
            },
            "graph_analysis": {
                "status": "warning" if graph_focus_areas else "ready",
                "focus_areas": graph_focus_areas,
                "claim_types": claim_types,
                "evidence_modalities": evidence_modalities,
                "unresolved_temporal_issue_count": unresolved_temporal_issue_count,
                "resolved_temporal_issue_count": resolved_temporal_issue_count,
                "evidence_workflow_action_count": int(evidence_workflow_action_summary.get("count") or 0),
            },
            "document_generation": {
                "status": str(drafting_readiness.get("status") or "ready").strip().lower() or "ready",
                "focus_areas": document_focus_areas,
                "warning_count": int(drafting_readiness.get("warning_count") or 0),
            },
        },
        "cross_phase_findings": cross_phase_findings,
        "workflow_action_queue": [
            *[
                {
                    "rank": int(action.get("rank") or index + 1),
                    "phase_name": str(action.get("phase_name") or "graph_analysis").strip() or "graph_analysis",
                    "status": str(action.get("status") or "warning").strip().lower() or "warning",
                    "action": str(action.get("action") or "").strip(),
                    "focus_areas": list(action.get("focus_areas") or [])[:3],
                    "claim_type": str(action.get("claim_type") or "").strip(),
                    "claim_element_id": str(action.get("claim_element_id") or "").strip(),
                }
                for index, action in enumerate(evidence_workflow_action_queue[:2])
                if isinstance(action, dict) and str(action.get("action") or "").strip()
            ],
            {
                "rank": 100,
                "phase_name": "graph_analysis",
                "status": "warning" if graph_focus_areas else "ready",
                "action": "Close graph and claim-support gaps before final drafting.",
                "focus_areas": graph_focus_areas[:3],
            },
            {
                "rank": 101,
                "phase_name": "document_generation",
                "status": str(drafting_readiness.get("status") or "ready").strip().lower() or "ready",
                "action": "Revise complaint sections still flagged by drafting readiness.",
                "focus_areas": document_focus_areas[:3],
            },
        ],
        "complaint_type_generalization_summary": {
            "complaint_types": claim_types,
            "complaint_type_count": len(claim_types),
        },
        "evidence_modality_generalization_summary": {
            "evidence_modalities": evidence_modalities,
            "evidence_modality_count": len(evidence_modalities),
        },
        "evidence_workflow_action_queue": list(evidence_workflow_action_queue),
        "evidence_workflow_action_summary": dict(evidence_workflow_action_summary),
        "document_handoff_summary": {
            "ready_for_document_optimization": str(drafting_readiness.get("status") or "").strip().lower() == "ready",
            "drafting_status": str(drafting_readiness.get("status") or "ready").strip().lower() or "ready",
            "blocking_warning_count": int(drafting_readiness.get("warning_count") or 0),
        },
        "intake_status": {
            "current_phase": str(intake_status.get("phase") or intake_status.get("current_phase") or "").strip(),
            "ready_to_advance": bool(intake_status.get("ready_to_advance", intake_status.get("ready", False))),
        },
        "claim_reasoning_review": dict(claim_reasoning_review or {}),
    }


def _heuristic_review(
    self,
    *,
    draft: Dict[str, Any],
    drafting_readiness: Dict[str, Any],
    support_context: Dict[str, Any],
) -> Dict[str, Any]:
    factual_allegations = self._normalize_lines(draft.get("factual_allegations") or draft.get("summary_of_facts") or [])
    claims = draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []
    affidavit = draft.get("affidavit") if isinstance(draft.get("affidavit"), dict) else {}
    certificate = draft.get("certificate_of_service") if isinstance(draft.get("certificate_of_service"), dict) else {}
    exhibits = draft.get("exhibits") if isinstance(draft.get("exhibits"), list) else []

    section_scores = {
        "factual_allegations": self._score_factual_allegations(factual_allegations, claims),
        "claims_for_relief": self._score_claims_section(claims, support_context),
        "requested_relief": self._score_requested_relief_section(
            self._normalize_lines(draft.get("requested_relief") or []),
            claims,
            drafting_readiness,
        ),
        "affidavit": self._score_affidavit_section(affidavit, exhibits),
        "certificate_of_service": self._score_certificate_section(certificate),
        "packet_projection": self._score_packet_projection(
            support_context.get("packet_projection") if isinstance(support_context.get("packet_projection"), dict) else {}
        ),
        "intake_questioning": self._score_intake_questioning(
            factual_allegations=factual_allegations,
            support_context=support_context,
        ),
    }
    guardrail = (
        support_context.get("document_generation_guardrail")
        if isinstance(support_context.get("document_generation_guardrail"), dict)
        else {}
    )
    assessment_blocked = bool(guardrail.get("assessment_blocked"))
    guardrail_phase_status = str(guardrail.get("phase_status") or "").strip().lower()
    guardrail_coverage = _safe_float(guardrail.get("coverage"), 0.0)
    graph_gate_active = bool(guardrail.get("gate_on_graph_completeness"))
    guardrail_blockers = _dedupe_text_values(guardrail.get("blockers") or [])
    unresolved_factual_gaps = self._normalize_lines(guardrail.get("unresolved_factual_gaps") or [])
    unresolved_legal_gaps = self._normalize_lines(guardrail.get("unresolved_legal_gaps") or [])
    structured_handoff = (
        support_context.get("structured_handoff")
        if isinstance(support_context.get("structured_handoff"), dict)
        else {}
    )
    promoted_factual_lines = self._normalize_lines(
        list(structured_handoff.get("factual_allegation_lines") or [])
    )
    promoted_claim_support_map = (
        structured_handoff.get("claim_support_lines_by_type")
        if isinstance(structured_handoff.get("claim_support_lines_by_type"), dict)
        else {}
    )
    promoted_exhibit_lines = self._normalize_lines(
        list(structured_handoff.get("exhibit_description_lines") or [])
    )
    if promoted_factual_lines:
        section_scores["factual_allegations"] = _clamp(float(section_scores.get("factual_allegations") or 0.0) + 0.08)
    if promoted_claim_support_map:
        section_scores["claims_for_relief"] = _clamp(float(section_scores.get("claims_for_relief") or 0.0) + 0.07)
    if promoted_exhibit_lines:
        section_scores["affidavit"] = _clamp(float(section_scores.get("affidavit") or 0.0) + 0.04)
        section_scores["packet_projection"] = _clamp(float(section_scores.get("packet_projection") or 0.0) + 0.03)
    if assessment_blocked:
        document_cap = 0.4 if guardrail_phase_status == "critical" or guardrail_coverage <= 0.0 else 0.55
        for section_name in (
            "claims_for_relief",
            "requested_relief",
            "affidavit",
            "certificate_of_service",
            "packet_projection",
        ):
            section_scores[section_name] = min(float(section_scores.get(section_name) or 0.0), document_cap)
    if graph_gate_active:
        section_scores["factual_allegations"] = min(float(section_scores.get("factual_allegations") or 0.0), 0.62)
        section_scores["claims_for_relief"] = min(float(section_scores.get("claims_for_relief") or 0.0), 0.58)
    ordered_sections = sorted(
        ((name, score) for name, score in section_scores.items() if name in self.VALID_FOCUS_SECTIONS),
        key=lambda item: item[1],
    )
    workflow_phase_targeting = self._build_workflow_phase_targeting(
        section_scores=section_scores,
        support_context=support_context,
    )
    phase_focus_order = list(workflow_phase_targeting.get("phase_focus_order") or self.WORKFLOW_PHASE_FOCUS_ORDER)
    phase_target_sections = dict(workflow_phase_targeting.get("phase_target_sections") or {})
    prioritized_phase = str(phase_focus_order[0] if phase_focus_order else "graph_analysis")
    recommended_focus = str(
        phase_target_sections.get(prioritized_phase)
        or (ordered_sections[0][0] if ordered_sections else "factual_allegations")
    )
    if assessment_blocked:
        forced_phase_order = ["graph_analysis", "intake_questioning", "document_generation"]
        phase_focus_order = forced_phase_order
        prioritized_phase = forced_phase_order[0]
        recommended_focus = str(
            phase_target_sections.get(prioritized_phase)
            or "factual_allegations"
        )

    weaknesses: List[str] = []
    suggestions: List[str] = []
    for section_name, score in ordered_sections:
        if score >= 0.8:
            continue
        if section_name == "factual_allegations":
            weaknesses.append("Factual allegations should read like pleading-ready declarative paragraphs grounded in the support record.")
            suggestions.append("Rewrite factual allegations into short declarative prose anchored to the support packet.")
        elif section_name == "claims_for_relief":
            weaknesses.append("Claims for relief still contain support gaps or thin claim-specific fact statements.")
            suggestions.append("Backfill claim-specific support facts for the weakest claim before rendering artifacts.")
        elif section_name == "requested_relief":
            weaknesses.append("Requested relief is incomplete or does not yet reflect the remedies supported by the current claim record.")
            suggestions.append("Confirm the prayer for relief includes the concrete damages, equitable remedies, and injunctive terms supported by the packet.")
        elif section_name == "affidavit":
            weaknesses.append("The affidavit is missing completeness or exhibit-consistency signals needed for a filing-ready packet.")
            suggestions.append("Revise affidavit facts and mirrored exhibit support so the affidavit matches the complaint record.")
        elif section_name == "certificate_of_service":
            weaknesses.append("The certificate of service is thin on recipient detail or service metadata.")
            suggestions.append("Add structured recipient details and method-specific service language before export.")

    intake_questioning_score = float(section_scores.get("intake_questioning") or 0.0)
    intake_priorities = support_context.get("intake_priorities") if isinstance(support_context.get("intake_priorities"), dict) else {}
    unresolved_objectives = [
        str(item).strip()
        for item in list(intake_priorities.get("critical_unresolved_objectives") or [])
        if str(item).strip()
    ]
    if intake_questioning_score < 0.75:
        weaknesses.append(
            "Intake follow-up detail is missing closure on key blockers (exact dates, staff names/titles, hearing-request timing, response dates, and protected-activity-to-adverse-action causation)."
        )
        if unresolved_objectives:
            objective_labels = ", ".join(unresolved_objectives[:5])
            suggestions.append(
                f"Ask targeted follow-up questions to close unresolved intake objectives: {objective_labels}."
            )
        suggestions.append(
            "Ask targeted follow-up questions to lock dates, each HACC actor decision, hearing and response timing, and direct causation facts linking protected activity to adverse treatment."
        )
    if guardrail_blockers:
        weaknesses.append(
            "Drafting readiness still has active blockers that must be reflected in formalization gating."
        )
        suggestions.append(
            "Carry unresolved blockers into drafting readiness and pause final formalization until blockers are closed."
        )
    if unresolved_factual_gaps:
        weaknesses.append("Unresolved factual gaps remain in the drafting handoff and weaken complaint specificity.")
        suggestions.append(
            "Promote structured intake facts and blocker-closing answers directly into factual allegations and claim support."
        )
    if unresolved_legal_gaps:
        weaknesses.append("Unresolved legal gaps remain in the drafting handoff and weaken claim formalization readiness.")
        suggestions.append("Address unresolved legal gaps before final complaint export.")
    if graph_gate_active:
        weaknesses.append("Graph completeness signals indicate unresolved dependencies that should block formalization.")
        suggestions.append("Close graph-analysis dependencies before running final document generation.")
    if assessment_blocked:
        weaknesses.append(
            str(guardrail.get("summary") or "No successful sessions were available to assess drafting handoff quality.")
        )
        for action in list(guardrail.get("recommended_actions") or []):
            action_text = str(action).strip()
            if not action_text:
                continue
            suggestions.append(action_text)

    readiness_status = str(drafting_readiness.get("status") or "ready").strip().lower()
    procedural_score = 0.95 if readiness_status == "ready" else 0.75 if readiness_status == "warning" else 0.45
    if assessment_blocked:
        procedural_score = min(
            procedural_score,
            0.35 if guardrail_phase_status == "critical" or guardrail_coverage <= 0.0 else 0.6,
        )
    if graph_gate_active:
        procedural_score = min(procedural_score, 0.45)
    if unresolved_factual_gaps:
        procedural_score = max(0.0, procedural_score - min(0.18, 0.04 * len(unresolved_factual_gaps)))
    if unresolved_legal_gaps:
        procedural_score = max(0.0, procedural_score - min(0.12, 0.04 * len(unresolved_legal_gaps)))
    completeness_score = sum(section_scores.values()) / max(len(section_scores), 1)
    grounding_score = self._score_grounding(support_context)
    coherence_score = self._score_coherence(factual_allegations)
    renderability_score = (
        section_scores["affidavit"]
        + section_scores["certificate_of_service"]
        + section_scores["packet_projection"]
    ) / 3.0

    overall_score = _clamp(
        (completeness_score * 0.35)
        + (grounding_score * 0.2)
        + (coherence_score * 0.2)
        + (procedural_score * 0.15)
        + (renderability_score * 0.1)
    )
    if assessment_blocked:
        overall_score = min(
            overall_score,
            0.55 if guardrail_phase_status == "critical" or guardrail_coverage <= 0.0 else 0.7,
        )
    strengths = []
    if support_context.get("claims"):
        strengths.append("Support packets are available.")
    if section_scores["affidavit"] >= 0.85:
        strengths.append("Affidavit content is structurally complete.")
    if section_scores["certificate_of_service"] >= 0.85:
        strengths.append("Service metadata is present for export.")
    if section_scores["packet_projection"] >= 0.85:
        strengths.append("Render-target packet projection is structurally complete.")
    if section_scores["intake_questioning"] >= 0.85:
        strengths.append("Intake questioning captures timeline, actor, and causation anchors.")

    return {
        "overall_score": overall_score,
        "dimension_scores": {
            "completeness": completeness_score,
            "grounding": grounding_score,
            "coherence": coherence_score,
            "procedural": procedural_score,
            "renderability": renderability_score,
        },
        "section_scores": section_scores,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "suggestions": suggestions,
        "recommended_focus": recommended_focus,
        "workflow_phase_order": phase_focus_order,
        "workflow_phase_scores": dict(workflow_phase_targeting.get("phase_scores") or {}),
        "workflow_phase_target_sections": phase_target_sections,
        "prioritized_workflow_phase": prioritized_phase,
        "document_generation_guardrail": dict(guardrail),
    }


def _build_workflow_phase_targeting(
    self,
    *,
    section_scores: Dict[str, float],
    support_context: Dict[str, Any],
) -> Dict[str, Any]:
    priorities = support_context.get("intake_priorities") if isinstance(support_context.get("intake_priorities"), dict) else {}
    unresolved_objectives = {
        _normalize_intake_objective(item)
        for item in list(priorities.get("unresolved_objectives") or [])
        if _normalize_intake_objective(item)
    }
    critical_unresolved = {
        _normalize_intake_objective(item)
        for item in list(priorities.get("critical_unresolved_objectives") or [])
        if _normalize_intake_objective(item)
    }
    blocker_extraction_targets = {
        str(item).strip().lower()
        for item in list(priorities.get("blocker_extraction_targets") or [])
        if str(item).strip()
    }
    blocker_workflow_phases = {
        str(item).strip().lower()
        for item in list(priorities.get("blocker_workflow_phases") or [])
        if str(item).strip()
    }
    blocker_issue_families = {
        str(item).strip().lower()
        for item in list(priorities.get("blocker_issue_families") or [])
        if str(item).strip()
    }
    blocker_count = int(priorities.get("blocker_count") or 0)
    chronology_context_active = any(
        (
            bool(priorities.get("anchored_chronology_summary")),
            int(priorities.get("claim_temporal_gap_count") or 0) > 0,
            int(priorities.get("unresolved_temporal_issue_count", priorities.get("temporal_issue_count", 0)) or 0) > 0,
            int(priorities.get("resolved_temporal_issue_count") or 0) > 0,
        )
    )
    graph_blockers = unresolved_objectives.intersection(
        {
            "exact_dates",
            "timeline",
            "actors",
            "staff_names_titles",
            "causation_link",
            "causation_sequence",
            "anchor_adverse_action",
            "anchor_appeal_rights",
            "hearing_request_timing",
            "response_dates",
        }
    )
    document_blockers = unresolved_objectives.intersection(
        {
            "documents",
            "harm_remedy",
            "exact_dates",
            "anchor_adverse_action",
            "anchor_appeal_rights",
            "staff_names_titles",
            "hearing_request_timing",
            "response_dates",
        }
    )

    factual_pressure = max(0.0, 1.0 - float(section_scores.get("factual_allegations") or 0.0))
    claims_pressure = max(0.0, 1.0 - float(section_scores.get("claims_for_relief") or 0.0))
    requested_relief_pressure = max(0.0, 1.0 - float(section_scores.get("requested_relief") or 0.0))
    affidavit_pressure = max(0.0, 1.0 - float(section_scores.get("affidavit") or 0.0))
    certificate_pressure = max(0.0, 1.0 - float(section_scores.get("certificate_of_service") or 0.0))
    packet_pressure = max(0.0, 1.0 - float(section_scores.get("packet_projection") or 0.0))
    intake_pressure = max(0.0, 1.0 - float(section_scores.get("intake_questioning") or 0.0))

    phase_scores = {
        "graph_analysis": _clamp(
            factual_pressure * 0.55
            + claims_pressure * 0.15
            + min(len(graph_blockers) * 0.08, 0.28)
            + min(len(critical_unresolved.intersection(graph_blockers)) * 0.05, 0.15)
            + (0.08 if blocker_workflow_phases.intersection({"graph_analysis"}) else 0.0)
            + min(len(blocker_extraction_targets.intersection({"timeline_anchors", "actor_role_mapping", "retaliation_sequence", "hearing_process", "response_timeline"})) * 0.03, 0.15)
        ),
        "document_generation": _clamp(
            claims_pressure * 0.2
            + requested_relief_pressure * 0.2
            + affidavit_pressure * 0.2
            + certificate_pressure * 0.15
            + packet_pressure * 0.15
            + min(len(document_blockers) * 0.06, 0.18)
            + (0.05 if blocker_workflow_phases.intersection({"document_generation"}) else 0.0)
        ),
        "intake_questioning": _clamp(
            (intake_pressure * 0.55)
            + min(len(unresolved_objectives) * 0.05, 0.2)
            + min(len(critical_unresolved) * 0.04, 0.12)
            + min(blocker_count * 0.03, 0.12)
            + (0.04 if blocker_workflow_phases.intersection({"intake_questioning"}) else 0.0)
        ),
    }
    if blocker_issue_families.intersection({"notice_chain", "response_timeline", "hearing_process"}):
        phase_scores["document_generation"] = _clamp(float(phase_scores.get("document_generation") or 0.0) + 0.04)
    if graph_blockers and factual_pressure >= 0.35:
        phase_scores["graph_analysis"] = _clamp(
            max(
                float(phase_scores.get("graph_analysis") or 0.0),
                float(phase_scores.get("intake_questioning") or 0.0) + 0.05,
            )
        )

    phase_focus_order = [
        name
        for name, _score in sorted(
            phase_scores.items(),
            key=lambda item: (-float(item[1]), self.WORKFLOW_PHASE_FOCUS_ORDER.index(item[0])),
        )
    ]
    phase_target_sections = {
        phase_name: self._select_phase_target_section(
            phase_name=phase_name,
            section_scores=section_scores,
            unresolved_objectives=unresolved_objectives,
            chronology_context_active=chronology_context_active,
        )
        for phase_name in phase_focus_order
    }
    return {
        "phase_scores": phase_scores,
        "phase_focus_order": phase_focus_order,
        "phase_target_sections": phase_target_sections,
    }


def _select_support_context(
    self,
    *,
    focus_section: str,
    draft: Dict[str, Any],
    support_context: Dict[str, Any],
) -> Dict[str, Any]:
    query = self._focus_query_text(focus_section, draft)
    claim_rows = support_context.get("claims") if isinstance(support_context.get("claims"), list) else []
    candidate_rows = []
    for claim_row in claim_rows:
        if not isinstance(claim_row, dict):
            continue
        claim_type = str(claim_row.get("claim_type") or "").strip()
        for text in claim_row.get("support_facts") or []:
            candidate_rows.append({"claim_type": claim_type, "text": str(text)})
        for text in claim_row.get("missing_elements") or []:
            candidate_rows.append({"claim_type": claim_type, "text": str(text), "kind": "missing_element"})
    for evidence_row in support_context.get("evidence") or []:
        if isinstance(evidence_row, dict) and evidence_row.get("text"):
            candidate_rows.append(dict(evidence_row))
    intake_priorities = support_context.get("intake_priorities") if isinstance(support_context.get("intake_priorities"), dict) else {}
    for prompt_text in intake_priorities.get("recommended_follow_up_prompts") or []:
        normalized_prompt = str(prompt_text or "").strip()
        if not normalized_prompt:
            continue
        candidate_rows.append(
            {
                "claim_type": "intake_follow_up",
                "text": normalized_prompt,
                "kind": "intake_objective_prompt",
            }
        )
    for blocker in intake_priorities.get("blocker_items") or []:
        if not isinstance(blocker, dict):
            continue
        blocker_reason = str(blocker.get("reason") or "").strip()
        if blocker_reason:
            candidate_rows.append(
                {
                    "claim_type": "intake_blocker",
                    "text": blocker_reason,
                    "kind": "blocker_reason",
                }
            )
    evidence_workflow_action_queue = (
        support_context.get("evidence_workflow_action_queue")
        if isinstance(support_context.get("evidence_workflow_action_queue"), list)
        else []
    )
    for action_entry in evidence_workflow_action_queue:
        if not isinstance(action_entry, dict):
            continue
        action_text = str(action_entry.get("action") or "").strip()
        if not action_text:
            continue
        claim_element_label = str(
            action_entry.get("claim_element_label")
            or action_entry.get("claim_element_id")
            or ""
        ).strip()
        preferred_support_kind = str(action_entry.get("preferred_support_kind") or "").strip()
        evidence_focus = " ".join(
            part for part in [
                action_text,
                claim_element_label,
                preferred_support_kind,
            ]
            if part
        ).strip()
        candidate_rows.append(
            {
                "claim_type": str(action_entry.get("claim_type") or action_entry.get("phase_name") or "graph_analysis").strip(),
                "text": evidence_focus or action_text,
                "kind": "evidence_workflow_action",
                "status": str(action_entry.get("status") or "").strip(),
                "claim_element_id": str(action_entry.get("claim_element_id") or "").strip(),
                "preferred_support_kind": preferred_support_kind,
            }
        )
    workflow_action_queue = support_context.get("workflow_action_queue") if isinstance(support_context.get("workflow_action_queue"), list) else []
    for action_entry in workflow_action_queue:
        if not isinstance(action_entry, dict):
            continue
        action_text = str(action_entry.get("action") or "").strip()
        if not action_text:
            continue
        candidate_rows.append(
            {
                "claim_type": str(action_entry.get("phase_name") or "workflow").strip(),
                "text": action_text,
                "kind": "workflow_action",
                "status": str(action_entry.get("status") or "").strip(),
            }
        )
    document_drafting_next_action = (
        support_context.get("document_drafting_next_action")
        if isinstance(support_context.get("document_drafting_next_action"), dict)
        else {}
    )
    if str(document_drafting_next_action.get("action") or "").strip().lower() == "realign_document_drafting":
        target_claim_element = str(document_drafting_next_action.get("claim_element_id") or "").strip()
        executed_claim_element = str(document_drafting_next_action.get("executed_claim_element_id") or "").strip()
        preferred_support_kind = str(document_drafting_next_action.get("preferred_support_kind") or "").strip()
        focus_section_hint = str(document_drafting_next_action.get("focus_section") or "").strip()
        candidate_rows.append(
            {
                "claim_type": "document_generation",
                "text": (
                    f"Realign drafting toward {target_claim_element.replace('_', ' ')}"
                    + (
                        f" instead of {executed_claim_element.replace('_', ' ')}."
                        if executed_claim_element
                        else "."
                    )
                ),
                "kind": "document_drafting_next_action",
                "claim_element_id": target_claim_element,
                "executed_claim_element_id": executed_claim_element,
                "preferred_support_kind": preferred_support_kind,
                "focus_section": focus_section_hint,
            }
        )
    document_grounding_improvement_next_action = (
        support_context.get("document_grounding_improvement_next_action")
        if isinstance(support_context.get("document_grounding_improvement_next_action"), dict)
        else {}
    )
    grounding_action_code = str(document_grounding_improvement_next_action.get("action") or "").strip().lower()
    if grounding_action_code in {"refine_document_grounding_strategy", "retarget_document_grounding"}:
        target_claim_element = str(
            document_grounding_improvement_next_action.get("suggested_claim_element_id")
            or document_grounding_improvement_next_action.get("claim_element_id")
            or ""
        ).strip()
        original_claim_element = str(document_grounding_improvement_next_action.get("claim_element_id") or "").strip()
        current_support_kind = str(document_grounding_improvement_next_action.get("preferred_support_kind") or "").strip()
        suggested_support_kind = str(document_grounding_improvement_next_action.get("suggested_support_kind") or "").strip()
        candidate_rows.append(
            {
                "claim_type": "document_generation",
                "text": (
                    (
                        f"Retarget grounding from {original_claim_element.replace('_', ' ')} to {target_claim_element.replace('_', ' ')}."
                        if grounding_action_code == "retarget_document_grounding" and target_claim_element and original_claim_element and target_claim_element != original_claim_element
                        else (
                            f"Refine grounding for {target_claim_element.replace('_', ' ')}"
                            + (
                                f" by trying {suggested_support_kind.replace('_', ' ')} instead of {current_support_kind.replace('_', ' ')}."
                                if target_claim_element and suggested_support_kind and current_support_kind
                                else "."
                            )
                        )
                    )
                ),
                "kind": "document_grounding_improvement_next_action",
                "claim_element_id": target_claim_element,
                "original_claim_element_id": original_claim_element,
                "preferred_support_kind": suggested_support_kind or current_support_kind,
                "focus_section": str(document_grounding_improvement_next_action.get("focus_section") or "").strip(),
            }
        )
    workflow_targeting_summary = (
        support_context.get("workflow_targeting_summary")
        if isinstance(support_context.get("workflow_targeting_summary"), dict)
        else {}
    )
    for claim_element_id, count in _sorted_count_items(
        workflow_targeting_summary.get("shared_claim_element_counts") or {}
    )[:4]:
        candidate_rows.append(
            {
                "claim_type": "workflow_targeting",
                "text": f"Strengthen complaint support for {claim_element_id.replace('_', ' ')}.",
                "kind": "workflow_targeting_claim_element",
                "claim_element_id": claim_element_id,
                "target_count": count,
            }
        )
    for focus_area, count in _sorted_count_items(
        workflow_targeting_summary.get("shared_focus_area_counts") or {}
    )[:4]:
        candidate_rows.append(
            {
                "claim_type": "workflow_targeting",
                "text": f"Strengthen drafting around {focus_area.replace('_', ' ')}.",
                "kind": "workflow_targeting_focus_area",
                "target_focus_area": focus_area,
                "target_count": count,
            }
        )

    ranked_rows = self._rank_candidates(query=query, candidates=candidate_rows)
    return {
        "focus_section": focus_section,
        "query": query,
        "top_support": ranked_rows[:6],
    }
