"""Workflow-phase planning delegated from Optimizer."""

from __future__ import annotations

from pathlib import Path

from complaint_phases.document_surface import build_workflow_phase_plan

def _build_workflow_phase_plan(
    self,
    *,
    question_quality_avg: float,
    information_extraction_avg: float,
    efficiency_avg: float,
    coverage_avg: float,
    graph_summary: Dict[str, Any],
    coverage_remediation: Dict[str, Any],
    document_evidence_targeting_summary: Optional[Dict[str, Any]] = None,
    document_provenance_summary: Optional[Dict[str, Any]] = None,
    intake_question_structure_summary: Optional[Dict[str, Any]] = None,
    document_grounding_improvement_summary: Optional[Dict[str, Any]] = None,
    document_grounding_lane_outcome_summary: Optional[Dict[str, Any]] = None,
    document_workflow_execution_summary: Optional[Dict[str, Any]] = None,
    document_chronology_reasoning_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    document_evidence_targeting_summary = dict(document_evidence_targeting_summary or {})
    document_provenance_summary = dict(document_provenance_summary or {})
    intake_question_structure_summary = dict(intake_question_structure_summary or {})
    document_grounding_improvement_summary = dict(document_grounding_improvement_summary or {})
    document_grounding_lane_outcome_summary = dict(document_grounding_lane_outcome_summary or {})
    document_workflow_execution_summary = dict(document_workflow_execution_summary or {})
    document_chronology_reasoning_summary = dict(document_chronology_reasoning_summary or {})
    intake_actions = list((coverage_remediation.get("intake_priorities") or {}).get("recommended_actions") or [])
    intake_signals: List[str] = []
    intake_recommendations: List[Dict[str, Any]] = []
    intake_severity = 0

    if intake_actions:
        intake_signals.append(f"{len(intake_actions)} intake objectives remain uncovered")
        intake_severity += 3
        for item in intake_actions[:3]:
            intake_recommendations.append(
                {
                    "focus": str(item.get("objective") or "intake_priority"),
                    "signal": "intake_coverage_gap",
                    "recommended_action": str(item.get("recommended_action") or "Add a dedicated intake fallback question."),
                }
            )
    if question_quality_avg < 0.7:
        intake_signals.append(f"question quality average is {question_quality_avg:.2f}")
        intake_severity += 2 if question_quality_avg < 0.6 else 1
        intake_recommendations.append(
            {
                "focus": "mediator_questioning",
                "signal": "question_quality",
                "recommended_action": "Tighten mediator prompts so each question is specific to the unresolved factual gap and references the strongest available evidence anchor.",
            }
        )
    if efficiency_avg < 0.7:
        intake_signals.append(f"efficiency average is {efficiency_avg:.2f}")
        intake_severity += 2 if efficiency_avg < 0.6 else 1
        intake_recommendations.append(
            {
                "focus": "question_deduplication",
                "signal": "efficiency",
                "recommended_action": "Prefer unanswered objectives before revisiting covered topics, and deduplicate repeated mediator questions across turns.",
            }
        )
    if coverage_avg < 0.7:
        intake_signals.append(f"coverage average is {coverage_avg:.2f}")
        intake_severity += 2 if coverage_avg < 0.6 else 1
        intake_recommendations.append(
            {
                "focus": "intake_flow",
                "signal": "coverage",
                "recommended_action": "Keep timeline, actors, documents, witnesses, and harm/remedy prompts ahead of generic wrap-up questions so intake exits with fewer factual gaps.",
            }
        )

    graph_signals: List[str] = []
    graph_recommendations: List[Dict[str, Any]] = []
    graph_severity = 0
    kg_with = int(graph_summary.get("kg_sessions_with_data") or 0)
    dg_with = int(graph_summary.get("dg_sessions_with_data") or 0)
    kg_empty = int(graph_summary.get("kg_sessions_empty") or 0)
    dg_empty = int(graph_summary.get("dg_sessions_empty") or 0)
    kg_avg_entities = self._safe_float(graph_summary.get("kg_avg_total_entities"))
    dg_avg_nodes = self._safe_float(graph_summary.get("dg_avg_total_nodes"))
    kg_avg_gaps = self._safe_float(graph_summary.get("kg_avg_gaps"))
    kg_gap_delta = self._safe_float(graph_summary.get("kg_avg_gaps_delta_per_iter"))
    kg_entities_delta = self._safe_float(graph_summary.get("kg_avg_entities_delta_per_iter"))
    kg_relationships_delta = self._safe_float(graph_summary.get("kg_avg_relationships_delta_per_iter"))
    dg_satisfaction_rate = self._safe_float(graph_summary.get("dg_avg_satisfaction_rate"))
    kg_not_reducing = int(graph_summary.get("kg_sessions_gaps_not_reducing") or 0)

    if kg_with == 0:
        graph_signals.append("knowledge graph summaries are missing from analyzed sessions")
        graph_severity += 2
        graph_recommendations.append(
            {
                "focus": "knowledge_graph_capture",
                "signal": "kg_missing",
                "recommended_action": "Ensure adversarial sessions persist knowledge-graph summaries so optimizer feedback can steer entity extraction and gap reduction.",
            }
        )
    elif kg_empty == kg_with:
        graph_signals.append("knowledge graphs are empty across analyzed sessions")
        graph_severity += 3
        graph_recommendations.append(
            {
                "focus": "knowledge_graph_extraction",
                "signal": "kg_empty",
                "recommended_action": "Strengthen entity and relationship extraction so intake answers produce a usable knowledge graph before denoising or drafting.",
            }
        )
    elif kg_avg_entities is not None and kg_avg_entities < 2.0:
        graph_signals.append(f"knowledge graphs average only {kg_avg_entities:.2f} entities")
        graph_severity += 1
        graph_recommendations.append(
            {
                "focus": "knowledge_graph_growth",
                "signal": "kg_small",
                "recommended_action": "Add lightweight structured extraction for dates, actors, actions, injuries, and documents so the knowledge graph is not too sparse for downstream reasoning.",
            }
        )

    if dg_with == 0:
        graph_signals.append("dependency graph summaries are missing from analyzed sessions")
        graph_severity += 2
        graph_recommendations.append(
            {
                "focus": "dependency_graph_capture",
                "signal": "dg_missing",
                "recommended_action": "Ensure dependency-graph summaries are captured so missing legal elements can be targeted during denoising.",
            }
        )
    elif dg_empty == dg_with:
        graph_signals.append("dependency graphs are empty across analyzed sessions")
        graph_severity += 3
        graph_recommendations.append(
            {
                "focus": "dependency_graph_population",
                "signal": "dg_empty",
                "recommended_action": "Expand claim-to-requirement modeling so dependency graphs capture missing legal elements and evidence dependencies before drafting.",
            }
        )
    elif dg_avg_nodes is not None and dg_avg_nodes < 2.0:
        graph_signals.append(f"dependency graphs average only {dg_avg_nodes:.2f} nodes")
        graph_severity += 1

    if kg_avg_gaps is not None and kg_avg_gaps >= 3.0:
        graph_signals.append(f"knowledge graphs average {kg_avg_gaps:.2f} unresolved gaps")
        graph_severity += 2
        graph_recommendations.append(
            {
                "focus": "gap_reduction",
                "signal": "kg_gap_count",
                "recommended_action": "Improve denoiser gap selection and answer processing so each turn closes a concrete knowledge-graph gap instead of only restating the narrative.",
            }
        )
    if kg_not_reducing > 0 or (kg_gap_delta is not None and kg_gap_delta >= 0.0):
        graph_signals.append("knowledge-graph gaps are not reliably shrinking across iterations")
        graph_severity += 2
        graph_recommendations.append(
            {
                "focus": "iterative_graph_updates",
                "signal": "kg_gap_delta",
                "recommended_action": "Make answer processing update entities, relationships, and satisfied requirements deterministically when the complainant supplies the missing field.",
            }
        )
    if kg_entities_delta is not None and kg_entities_delta < 0.1:
        graph_signals.append("knowledge-graph entity growth per iteration is low")
        graph_severity += 1
    if kg_relationships_delta is not None and kg_relationships_delta < 0.05:
        graph_signals.append("knowledge-graph relationship growth per iteration is low")
        graph_severity += 1
    if dg_satisfaction_rate is not None and dg_satisfaction_rate < 0.2:
        graph_signals.append(f"dependency satisfaction rate is only {dg_satisfaction_rate:.2f}")
        graph_severity += 2

    chronology_pressure_flag = bool(document_chronology_reasoning_summary.get("chronology_pressure_flag"))
    unresolved_temporal_issue_count = int(
        document_chronology_reasoning_summary.get("unresolved_temporal_issue_count") or 0
    )
    chronology_task_count = int(document_chronology_reasoning_summary.get("chronology_task_count") or 0)
    proof_artifact_element_count = int(
        document_chronology_reasoning_summary.get("proof_artifact_element_count") or 0
    )
    proof_artifact_available_element_count = int(
        document_chronology_reasoning_summary.get("proof_artifact_available_element_count") or 0
    )
    if chronology_pressure_flag:
        graph_signals.append(
            "chronology and proof-review gaps require stronger graph propagation into timeline and actor modeling"
        )
        graph_severity += 2 if unresolved_temporal_issue_count > 0 else 1
        graph_recommendations.append(
            {
                "focus": "chronology_graph_handoff",
                "signal": "document_chronology_reasoning",
                "recommended_action": (
                    "Preserve chronology tasks, proof bundle ids, and unresolved temporal issues in graph updates so "
                    "timeline and causation reasoning stay available to downstream drafting."
                ),
            }
        )

    document_signals: List[str] = []
    document_recommendations: List[Dict[str, Any]] = []
    document_severity = 0
    uncovered_objectives = [
        str(value)
        for value in list((coverage_remediation.get("intake_priorities") or {}).get("uncovered_objectives") or [])
        if str(value)
    ]
    graph_blocker_objectives = [
        objective
        for objective in uncovered_objectives
        if objective in {"exact_dates", "staff_names_titles", "hearing_request_timing", "response_dates", "causation_sequence", "timeline", "actors"}
    ]
    if graph_blocker_objectives:
        graph_signals.append(
            "graph-blocking intake objectives remain uncovered: " + ", ".join(graph_blocker_objectives[:4])
        )
        graph_severity += 2
        graph_recommendations.append(
            {
                "focus": "blocker_closure",
                "signal": "intake_graph_blockers",
                "recommended_action": "Promote exact dates, staff names/titles, hearing-request timing, response dates, and causation sequencing into graph updates before broadening the next question set.",
            }
        )
    if "documents" in uncovered_objectives:
        document_signals.append("document-focused intake objectives are still uncovered")
        document_severity += 2
        document_recommendations.append(
            {
                "focus": "exhibit_collection",
                "signal": "documents_objective",
                "recommended_action": "Carry early document-request prompts into drafting handoff so exhibits, notices, grievances, and emails are reflected in the complaint package.",
            }
        )
    if "harm_remedy" in uncovered_objectives:
        document_signals.append("harm/remedy objectives are still uncovered")
        document_severity += 1
        document_recommendations.append(
            {
                "focus": "requested_relief",
                "signal": "harm_remedy_objective",
                "recommended_action": "Strengthen the handoff from intake to requested-relief generation so the draft captures both the injury and the remedy sought.",
            }
        )
    if any(
        objective in {"staff_names_titles", "hearing_request_timing", "response_dates", "causation_sequence"}
        for objective in uncovered_objectives
    ):
        document_signals.append("drafting still lacks chronology, staff-identity, or causation-sequence details needed for pleading-ready allegations")
        document_severity += 1
        document_recommendations.append(
            {
                "focus": "pleading_anchors",
                "signal": "intake_blocker_handoff",
                "recommended_action": "Carry blocker-closing intake answers directly into factual allegations, claim support, and exhibit descriptions so drafted complaints preserve timing, actor identity, and causation sequence.",
            }
        )
    if information_extraction_avg < 0.7:
        document_signals.append(f"information extraction average is {information_extraction_avg:.2f}")
        document_severity += 2 if information_extraction_avg < 0.6 else 1
        document_recommendations.append(
            {
                "focus": "drafting_handoff",
                "signal": "information_extraction",
                "recommended_action": "Promote structured intake facts, anchors, and evidence references directly into summary-of-facts and claim-support generation before document optimization runs.",
            }
        )
    if coverage_avg < 0.7:
        document_signals.append(f"overall coverage average is {coverage_avg:.2f}")
        document_severity += 1
    if graph_severity > 0:
        document_signals.append("drafting depends on stronger graph and denoising handoffs")
        document_severity += 1
        document_recommendations.append(
            {
                "focus": "graph_to_document_handoff",
                "signal": "graph_dependency",
                "recommended_action": "Gate document generation on graph completeness signals and surface unresolved factual or legal gaps in drafting readiness before formalization.",
            }
        )
    fact_backed_ratio = self._safe_float((document_provenance_summary or {}).get("avg_fact_backed_ratio"))
    low_grounding_flag = bool((document_provenance_summary or {}).get("low_grounding_flag"))
    if low_grounding_flag or (fact_backed_ratio is not None and fact_backed_ratio < 0.6):
        document_signals.append(
            "draft output is not grounded enough in canonical facts or evidence-backed support rows"
        )
        document_severity += 2 if (fact_backed_ratio is not None and fact_backed_ratio < 0.4) else 1
        document_recommendations.append(
            {
                "focus": "document_provenance_grounding",
                "signal": "document_provenance",
                "recommended_action": (
                    "Carry canonical fact ids, support traces, and artifact-backed support rows through drafting so the complaint text is grounded in traceable evidence."
                ),
            }
        )
    if chronology_pressure_flag:
        chronology_parts: List[str] = []
        if unresolved_temporal_issue_count > 0:
            chronology_parts.append(f"{unresolved_temporal_issue_count} unresolved temporal issues")
        if chronology_task_count > 0:
            chronology_parts.append(f"{chronology_task_count} chronology tasks")
        if proof_artifact_element_count > 0:
            chronology_parts.append(
                f"{proof_artifact_available_element_count}/{proof_artifact_element_count} proof artifacts available"
            )
        chronology_summary = ", ".join(chronology_parts) or "chronology review metadata is present"
        document_signals.append(
            "drafting still carries chronology and proof-review pressure: " + chronology_summary
        )
        document_severity += 3 if unresolved_temporal_issue_count > 0 else 2
        document_recommendations.insert(
            0,
            {
                "focus": "chronology_reasoning_handoff",
                "signal": "document_chronology_reasoning",
                "recommended_action": (
                    "Thread unresolved chronology issues, proof artifact availability, and temporal proof bundle ids "
                    "through drafting-target selection so factual allegations and claim support stay timeline-complete."
                ),
            },
        )
    targeted_document_elements = [
        str(name)
        for name, _count in sorted(
            dict((document_evidence_targeting_summary or {}).get("claim_element_counts") or {}).items(),
            key=lambda item: (-int(item[1] or 0), item[0]),
        )[:2]
        if str(name)
    ]
    first_executed_document_element = str(
        (document_workflow_execution_summary or {}).get("first_targeted_claim_element") or ""
    ).strip()
    if (
        targeted_document_elements
        and first_executed_document_element
        and first_executed_document_element != targeted_document_elements[0]
    ):
        document_signals.append(
            "document execution is not starting with the highest-priority targeted legal element"
        )
        document_severity = max(document_severity + 4, intake_severity + 1)
        document_recommendations.insert(
            0,
            {
                "focus": "document_execution_alignment",
                "signal": "document_execution_mismatch",
                "recommended_action": (
                    "Make the drafting loop prioritize "
                    + targeted_document_elements[0]
                    + " before "
                    + first_executed_document_element
                    + " when selecting focus sections and support rows."
                ),
            }
        )

    phases = {
        "intake_questioning": {
            "status": self._phase_status(intake_severity),
            "severity": intake_severity,
            "summary": "Improve complainant and mediator questioning so intake exits with stronger factual, evidentiary, and anchor coverage.",
            "signals": self._dedupe_text(intake_signals),
            "recommended_actions": intake_recommendations[:4],
            "target_files": [
                "adversarial_harness/session.py",
                "mediator/mediator.py",
                "adversarial_harness/complainant.py",
            ],
        },
        "graph_analysis": {
            "status": self._phase_status(graph_severity),
            "severity": graph_severity,
            "summary": "Improve knowledge-graph and dependency-graph population so denoising and legal reasoning operate on structured facts instead of raw narrative alone.",
            "signals": self._dedupe_text(graph_signals),
            "recommended_actions": graph_recommendations[:4],
            "target_files": [
                "complaint_phases/knowledge_graph.py",
                "complaint_phases/dependency_graph.py",
                "complaint_phases/denoiser.py",
                "complaint_phases/intake_case_file.py",
            ],
        },
        "document_generation": {
            "status": self._phase_status(document_severity),
            "severity": document_severity,
            "summary": "Improve drafting handoff so complaint generation reflects the collected facts, exhibits, and unresolved gaps at formalization time.",
            "signals": self._dedupe_text(document_signals),
            "recommended_actions": document_recommendations[:4],
            "target_files": [
                "document_pipeline.py",
                "document_optimization.py",
                "scripts/synthesize_hacc_complaint.py",
                "mediator/formal_document.py",
            ],
        },
    }

    ordered_names = [
        name
        for name, _payload in sorted(
            phases.items(),
            key=lambda item: (-int(item[1].get("severity") or 0), item[0]),
        )
    ]
    for priority, name in enumerate(ordered_names, start=1):
        phases[name]["priority"] = priority
        phases[name].pop("severity", None)

    return build_workflow_phase_plan(
        phases,
        status_rank={"critical": 0, "warning": 1, "ready": 2},
    )


def _workflow_phase_constraints(
    phase_name: str,
    target_paths: List[Path],
    report: Optional[OptimizationReport] = None,
) -> Dict[str, Any]:
    target_map: Dict[str, List[str]] = {}
    intake_targeting_summary = dict(report.intake_targeting_summary or {}) if report else {}
    graph_targeting_summary = dict(report.graph_element_targeting_summary or {}) if report else {}
    document_targeting_summary = dict(report.document_evidence_targeting_summary or {}) if report else {}
    intake_targeted_elements = {
        str(name)
        for name in dict(intake_targeting_summary.get("claim_element_counts") or {}).keys()
        if str(name)
    }
    intake_focus_areas = {
        str(name)
        for name in dict(intake_targeting_summary.get("focus_area_counts") or {}).keys()
        if str(name)
    }
    graph_targeted_elements = {
        str(name)
        for name in dict(graph_targeting_summary.get("claim_element_counts") or {}).keys()
        if str(name)
    }
    graph_focus_areas = {
        str(name)
        for name in dict(graph_targeting_summary.get("focus_area_counts") or {}).keys()
        if str(name)
    }
    targeted_focus_sections = {
        str(item.get("focus_section") or "").strip()
        for item in list(document_targeting_summary.get("targets") or [])
        if isinstance(item, dict) and str(item.get("focus_section") or "").strip()
    }
    targeted_support_kinds = {
        str(name)
        for name in dict(document_targeting_summary.get("support_kind_counts") or {}).keys()
        if str(name)
    }
    for path in target_paths:
        key = path.as_posix()
        if str(phase_name) == "intake_questioning":
            if path.name == "session.py":
                target_map[key] = [
                    "_inject_intake_prompt_questions",
                ]
            elif path.name == "mediator.py":
                target_map[key] = [
                    "build_inquiry_gap_context",
                ]
            elif path.name == "complainant.py":
                target_map[key] = [
                    "_build_actor_critic_guidance",
                ]
        elif str(phase_name) == "graph_analysis":
            if path.name == "knowledge_graph.py":
                target_map[key] = [
                    "build_from_text",
                ]
                if {"chronology", "timeline", "actors"} & graph_focus_areas:
                    target_map[key].append("_detect_claim_types")
            elif path.name == "dependency_graph.py":
                target_map[key] = [
                    "get_claim_readiness",
                ]
                if graph_targeted_elements:
                    target_map[key].append("build_from_claims")
            elif path.name == "denoiser.py":
                target_map[key] = [
                    "process_answer",
                ]
                if graph_targeted_elements:
                    target_map[key].extend(
                        [
                            "collect_question_candidates",
                            "generate_questions",
                        ]
                    )
            elif path.name == "intake_case_file.py":
                target_map[key] = [
                    "build_timeline_consistency_summary",
                ]
        elif str(phase_name) == "document_generation":
            if path.name == "document_pipeline.py":
                target_map[key] = [
                    "_build_runtime_workflow_phase_plan",
                ]
            elif path.name == "document_optimization.py":
                target_map[key] = [
                    "_build_workflow_phase_targeting",
                ]
                if targeted_support_kinds:
                    target_map[key].extend(
                        [
                            "_select_support_context",
                            "_build_document_evidence_targeting_summary",
                        ]
                    )
            elif path.name == "synthesize_hacc_complaint.py":
                target_map[key] = [
                    "_merge_seed_with_grounding",
                ]
                if "factual_allegations" in targeted_focus_sections:
                    target_map[key].append("_factual_background")
            elif path.name == "formal_document.py":
                target_map[key] = [
                    "render_text",
                ]
    if not target_map:
        return {}
    return {
        "target_symbols": target_map,
        "workflow_phase": str(phase_name),
        "preserve_interfaces": True,
    }


def _select_workflow_phase_targets(
    phase_name: str,
    phase_payload: Dict[str, Any],
    report: OptimizationReport,
    *,
    max_targets: int = 1,
) -> List[Path]:
    target_paths = [Path(path) for path in list(phase_payload.get("target_files") or [])]
    if not target_paths:
        return []

    uncovered_objectives = {
        str(value)
        for value in list((report.coverage_remediation or {}).get("intake_priorities", {}).get("uncovered_objectives") or [])
        if str(value)
    }
    blocker_objectives = uncovered_objectives.intersection(
        {"exact_dates", "staff_names_titles", "hearing_request_timing", "response_dates", "causation_sequence"}
    )

    if str(phase_name) == "graph_analysis":
        targeting_summary = dict(report.graph_element_targeting_summary or {})
        targeted_elements = {
            str(name)
            for name in dict(targeting_summary.get("claim_element_counts") or {}).keys()
            if str(name)
        }
        targeted_focus_areas = {
            str(name)
            for name in dict(targeting_summary.get("focus_area_counts") or {}).keys()
            if str(name)
        }
        priorities: List[str] = []
        kg_empty = int(report.kg_sessions_empty or 0) > 0 or float(report.kg_avg_total_entities or 0.0) <= 2.0
        dg_weak = float(report.dg_avg_satisfaction_rate or 0.0) < 0.5
        gaps_high = float(report.kg_avg_gaps or 0.0) >= 1.0 or int(report.kg_sessions_gaps_not_reducing or 0) > 0

        if targeted_elements:
            priorities.extend(["denoiser.py", "dependency_graph.py"])
        if {"chronology", "timeline", "actors"} & targeted_focus_areas:
            priorities.extend(["intake_case_file.py", "knowledge_graph.py"])
        if blocker_objectives:
            priorities.extend(["dependency_graph.py", "denoiser.py", "knowledge_graph.py"])

        if dg_weak:
            priorities.append("dependency_graph.py")
        if gaps_high:
            priorities.append("denoiser.py")
        if kg_empty:
            priorities.append("knowledge_graph.py")
        priorities.append("intake_case_file.py")
        priorities.extend(["dependency_graph.py", "denoiser.py", "knowledge_graph.py", "intake_case_file.py"])

        selected: List[Path] = []
        seen = set()
        for name in priorities:
            for path in target_paths:
                if path.name == name and path.name not in seen:
                    seen.add(path.name)
                    selected.append(path)
                    break
            if len(selected) >= max(1, int(max_targets or 1)):
                break
        return selected or target_paths[: max(1, int(max_targets or 1))]

    if str(phase_name) == "document_generation":
        targeting_summary = dict(report.document_evidence_targeting_summary or {})
        targeted_focus_sections = {
            str(item.get("focus_section") or "").strip()
            for item in list(targeting_summary.get("targets") or [])
            if isinstance(item, dict) and str(item.get("focus_section") or "").strip()
        }
        targeted_support_kinds = {
            str(name)
            for name in dict(targeting_summary.get("support_kind_counts") or {}).keys()
            if str(name)
        }
        priorities: List[str] = []
        if targeted_support_kinds:
            priorities.append("document_optimization.py")
        if "factual_allegations" in targeted_focus_sections:
            priorities.append("synthesize_hacc_complaint.py")
        if "claims_for_relief" in targeted_focus_sections:
            priorities.append("formal_document.py")
        if blocker_objectives:
            priorities.extend(["document_optimization.py", "synthesize_hacc_complaint.py", "formal_document.py", "document_pipeline.py"])
        else:
            priorities.extend(
                [
                    "document_optimization.py",
                    "synthesize_hacc_complaint.py",
                    "document_pipeline.py",
                    "formal_document.py",
                ]
            )
        selected: List[Path] = []
        seen = set()
        for name in priorities:
            for path in target_paths:
                if path.name == name and path.name not in seen:
                    seen.add(path.name)
                    selected.append(path)
                    break
            if len(selected) >= max(1, int(max_targets or 1)):
                break
        return selected or target_paths[: max(1, int(max_targets or 1))]

    if str(phase_name) == "intake_questioning":
        if int(report.num_sessions_analyzed or 0) == 0:
            for path in target_paths:
                if path.name == "session.py":
                    return [path]
            return target_paths[:1]
        targeting_summary = dict(report.intake_targeting_summary or {})
        targeted_elements = {
            str(name)
            for name in dict(targeting_summary.get("claim_element_counts") or {}).keys()
            if str(name)
        }
        targeted_focus_areas = {
            str(name)
            for name in dict(targeting_summary.get("focus_area_counts") or {}).keys()
            if str(name)
        }
        priorities = (
            ["session.py", "mediator.py", "complainant.py"]
            if blocker_objectives
            else [
                "session.py",
                "complainant.py",
                "mediator.py",
            ]
        )
        if targeted_elements:
            priorities = ["mediator.py", *priorities]
        if {"timeline", "chronology", "proof_leads"} & targeted_focus_areas:
            priorities = ["session.py", "mediator.py", *priorities]
        if {"actors", "harm_remedy"} & targeted_focus_areas:
            priorities = ["complainant.py", *priorities]
        selected: List[Path] = []
        seen = set()
        for name in priorities:
            for path in target_paths:
                if path.name == name and path.name not in seen:
                    seen.add(path.name)
                    selected.append(path)
                    break
            if len(selected) >= max(1, int(max_targets or 1)):
                break
        return selected or target_paths[: max(1, int(max_targets or 1))]

    return target_paths


def _build_phase_scorecards(
    self,
    *,
    report: OptimizationReport,
    graph_summary: Dict[str, Any],
    intake_targeting_summary: Dict[str, Any],
    complaint_type_summary: Dict[str, Any],
    evidence_modality_summary: Dict[str, Any],
    document_handoff_summary: Dict[str, Any],
    graph_element_targeting_summary: Dict[str, Any],
    document_evidence_targeting_summary: Dict[str, Any],
    document_provenance_summary: Dict[str, Any],
    intake_question_structure_summary: Dict[str, Any],
    document_theory_alignment_summary: Dict[str, Any],
    document_grounding_improvement_summary: Dict[str, Any],
    document_grounding_lane_outcome_summary: Dict[str, Any],
    document_workflow_execution_summary: Dict[str, Any],
    document_execution_drift_summary: Dict[str, Any],
    document_chronology_reasoning_summary: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    workflow_phases = dict((report.workflow_phase_plan or {}).get("phases") or {})
    weakest_objectives = self._top_uncovered_intake_objectives(report, limit=5)
    targeted_intake_objectives = [
        str(name)
        for name, _count in sorted(
            dict((intake_targeting_summary or {}).get("objective_counts") or {}).items(),
            key=lambda item: (-int(item[1] or 0), item[0]),
        )[:3]
        if str(name)
    ]
    weakest_complaint_types = [
        str(item.get("name") or "")
        for item in list((complaint_type_summary or {}).get("weakest") or [])
        if str(item.get("name") or "")
    ]
    weakest_modalities = [
        str(item.get("name") or "")
        for item in list((evidence_modality_summary or {}).get("weakest") or [])
        if str(item.get("name") or "")
    ]
    graph_targeted_claim_elements = [
        str(name)
        for name, _count in sorted(
            dict((graph_element_targeting_summary or {}).get("claim_element_counts") or {}).items(),
            key=lambda item: (-int(item[1] or 0), item[0]),
        )[:3]
        if str(name)
    ]
    targeted_claim_elements = [
        str(name)
        for name, _count in sorted(
            dict((document_evidence_targeting_summary or {}).get("claim_element_counts") or {}).items(),
            key=lambda item: (-int(item[1] or 0), item[0]),
        )[:3]
        if str(name)
    ]
    executed_claim_elements = [
        str(name)
        for name, _count in sorted(
            dict((document_workflow_execution_summary or {}).get("targeted_claim_element_counts") or {}).items(),
            key=lambda item: (-int(item[1] or 0), item[0]),
        )[:3]
        if str(name)
    ]
    first_executed_claim_element = str(
        (document_workflow_execution_summary or {}).get("first_targeted_claim_element") or ""
    ).strip()
    intake_exhibit_ready_ratio = self._safe_float(
        (intake_question_structure_summary or {}).get("avg_documentary_exhibit_ready_ratio")
    ) or 0.0
    intake_needs_exhibit_grounding = int(
        (intake_question_structure_summary or {}).get("sessions_needing_exhibit_grounding") or 0
    ) > 0
    document_theory_alignment_ratio = self._safe_float(
        (document_theory_alignment_summary or {}).get("avg_expected_tag_coverage")
    ) or 0.0
    document_fact_backed_ratio = self._safe_float((document_provenance_summary or {}).get("avg_fact_backed_ratio")) or 0.0
    document_exhibit_backed_ratio = self._safe_float((document_provenance_summary or {}).get("avg_exhibit_backed_ratio")) or 0.0
    execution_mismatch_flag = bool(
        targeted_claim_elements
        and first_executed_claim_element
        and first_executed_claim_element != targeted_claim_elements[0]
    )
    kg_avg_gaps = self._safe_float((graph_summary or {}).get("kg_avg_gaps")) or 0.0
    dg_satisfaction_rate = self._safe_float((graph_summary or {}).get("dg_avg_satisfaction_rate")) or 0.0
    chronology_pressure_flag = bool((document_chronology_reasoning_summary or {}).get("chronology_pressure_flag"))
    return {
        "intake_questioning": {
            "status": str((workflow_phases.get("intake_questioning") or {}).get("status") or "ready"),
            "score": round(
                (float(report.question_quality_avg or 0.0) + float(report.efficiency_avg or 0.0) + float(report.coverage_avg or 0.0)) / 3.0,
                4,
            ),
            "focus_areas": [
                *(["exhibit_ready_questions"] if intake_needs_exhibit_grounding and intake_exhibit_ready_ratio < 0.6 else []),
                *weakest_objectives[:2],
                *targeted_intake_objectives[:2],
            ][:3],
            "generalization_targets": weakest_complaint_types[:3],
            "evidence_targets": weakest_modalities[:3],
            "targeted_intake_objectives": targeted_intake_objectives,
            "intake_question_structure_summary": dict(intake_question_structure_summary or {}),
            "documentary_exhibit_ready_ratio": round(intake_exhibit_ready_ratio, 4),
        },
        "graph_analysis": {
            "status": str((workflow_phases.get("graph_analysis") or {}).get("status") or "ready"),
            "score": round(
                (float(report.information_extraction_avg or 0.0) + max(0.0, 1.0 - min(1.0, kg_avg_gaps / 5.0)) + float(dg_satisfaction_rate or 0.0)) / 3.0,
                4,
            ),
            "focus_areas": [
                "gap_reduction" if kg_avg_gaps >= 1.0 else "graph_stability",
                "dependency_satisfaction" if dg_satisfaction_rate < 0.7 else "dependency_coverage",
            ],
            "generalization_targets": weakest_complaint_types[:3],
            "evidence_targets": weakest_modalities[:3],
            "targeted_claim_elements": graph_targeted_claim_elements,
        },
        "document_generation": {
            "status": str((workflow_phases.get("document_generation") or {}).get("status") or "ready"),
            "score": round(
                (
                    float(report.coverage_avg or 0.0)
                    + float(report.information_extraction_avg or 0.0)
                    + (1.0 if bool((document_handoff_summary or {}).get("ready_for_document_optimization")) else 0.0)
                ) / 3.0,
                4,
            ),
            "focus_areas": [
                *(["theory_alignment"] if bool((document_theory_alignment_summary or {}).get("low_alignment_flag")) else []),
                *(["exhibit_grounding"] if document_exhibit_backed_ratio < 0.6 else []),
                *(["chronology_closure"] if chronology_pressure_flag else []),
                *list((document_handoff_summary or {}).get("unresolved_intake_objectives") or [])[:2],
                *targeted_claim_elements[:2],
            ][:3],
            "generalization_targets": weakest_complaint_types[:3],
            "evidence_targets": weakest_modalities[:3],
            "targeted_claim_elements": targeted_claim_elements,
            "executed_claim_elements": executed_claim_elements,
            "first_executed_claim_element": first_executed_claim_element,
            "first_focus_section": str((document_workflow_execution_summary or {}).get("first_focus_section") or ""),
            "first_top_support_kind": str((document_workflow_execution_summary or {}).get("first_top_support_kind") or ""),
            "document_fact_backed_ratio": round(document_fact_backed_ratio, 4),
            "document_exhibit_backed_ratio": round(document_exhibit_backed_ratio, 4),
            "document_theory_alignment_ratio": round(document_theory_alignment_ratio, 4),
            "document_low_grounding_flag": bool((document_provenance_summary or {}).get("low_grounding_flag")),
            "document_provenance_summary": dict(document_provenance_summary or {}),
            "document_theory_alignment_summary": dict(document_theory_alignment_summary or {}),
            "document_grounding_improvement_summary": dict(document_grounding_improvement_summary or {}),
            "document_grounding_lane_outcome_summary": dict(document_grounding_lane_outcome_summary or {}),
            "document_grounding_improved_flag": bool((document_grounding_improvement_summary or {}).get("improved_flag")),
            "execution_mismatch_flag": execution_mismatch_flag,
            "execution_drift_summary": dict(document_execution_drift_summary or {}),
            "unresolved_temporal_issue_count": int((document_chronology_reasoning_summary or {}).get("unresolved_temporal_issue_count") or 0),
            "chronology_task_count": int((document_chronology_reasoning_summary or {}).get("chronology_task_count") or 0),
            "proof_artifact_element_count": int((document_chronology_reasoning_summary or {}).get("proof_artifact_element_count") or 0),
            "proof_artifact_available_element_count": int((document_chronology_reasoning_summary or {}).get("proof_artifact_available_element_count") or 0),
            "document_chronology_reasoning_summary": dict(document_chronology_reasoning_summary or {}),
            "chronology_pressure_flag": chronology_pressure_flag,
        },
    }
