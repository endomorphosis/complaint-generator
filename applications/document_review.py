"""Document review assembly moved out of the document API."""

from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from complaint_phases.document_surface import (
    build_intake_case_review_summary,
    build_intake_status_summary,
    build_intake_warning_entries,
    humanize_workflow_priority_label,
    resolve_prioritized_workflow_phase,
)

from .document_api import (
    _annotate_checklist_review_links,
    _annotate_workflow_priority_with_temporal_gap_summary,
    _append_review_query_params,
    _build_claim_review_chip_labels,
    _build_document_focus_preview,
    _build_optimization_trace_url,
    _build_optimization_trace_view_url,
    _build_review_intent,
    _build_review_url,
    _claim_type_in_case_summary_queue,
    _dedupe_text_values,
    _default_generated_documents_root,
    _default_support_kind_for_section,
    _merge_claim_temporal_gap_summary,
    _merge_warning_entries,
    _resolve_document_review_url,
    _section_claim_types,
)

def _build_document_review_workflow_phase_priority(
    workflow_phase_plan: Dict[str, Any],
    *,
    user_id: Optional[str],
    default_claim_type: Optional[str],
    dashboard_url: str,
    section_review_map: Dict[str, Dict[str, Any]],
    intake_case_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    prioritized_phase_context = resolve_prioritized_workflow_phase(workflow_phase_plan)
    prioritized_phase_name = str(prioritized_phase_context.get("phase_name") or "").strip()
    prioritized_phase = dict(prioritized_phase_context.get("phase") or {})
    if not prioritized_phase_name or not prioritized_phase:
        return {}

    prioritized_status = str(prioritized_phase_context.get("status") or "ready").strip().lower() or "ready"
    recommended_actions = list(prioritized_phase_context.get("recommended_actions") or [])
    primary_recommended_action = recommended_actions[0] if recommended_actions else ""

    if prioritized_phase_name == "graph_analysis":
        section_key = "summary_of_facts"
        section_target = section_review_map.get(section_key) or {}
        section_context = section_target.get("review_context") if isinstance(section_target.get("review_context"), dict) else {}
        action_url = _append_review_query_params(
            str(
                section_target.get("review_url")
                or _build_review_url(
                    user_id=user_id,
                    claim_type=section_context.get("claim_type") or default_claim_type,
                    section=section_key,
                )
            ),
            follow_up_support_kind=_default_support_kind_for_section(section_key),
        )
        title = (
            "Graph analysis is aligned for drafting"
            if prioritized_status == "ready"
            else "Resolve graph analysis before drafting"
        )
        action_label = "Review graph inputs"
    elif prioritized_phase_name == "document_generation":
        section_key = "claims_for_relief"
        section_target = section_review_map.get(section_key) or {}
        section_context = section_target.get("review_context") if isinstance(section_target.get("review_context"), dict) else {}
        title = (
            "Drafting is aligned with workflow guidance"
            if prioritized_status == "ready"
            else "Resolve drafting readiness before filing"
        )
        action_label = "Open Review Dashboard" if prioritized_status == "ready" else "Review drafting readiness"
        action_url = dashboard_url if prioritized_status == "ready" else _append_review_query_params(
            str(
                section_target.get("review_url")
                or _build_review_url(
                    user_id=user_id,
                    claim_type=section_context.get("claim_type") or default_claim_type,
                    section=section_key,
                )
            ),
            follow_up_support_kind=_default_support_kind_for_section(section_key),
        )
    else:
        return {}

    temporal_issue_registry_summary = (
        intake_case_summary.get("temporal_issue_registry_summary")
        if isinstance(intake_case_summary, dict) and isinstance(intake_case_summary.get("temporal_issue_registry_summary"), dict)
        else {}
    )
    unresolved_registry_temporal_issue_count = int(temporal_issue_registry_summary.get("unresolved_count") or 0)
    resolved_temporal_issue_count = int(temporal_issue_registry_summary.get("resolved_count") or 0)
    chip_labels = [
        f"workflow phase: {humanize_workflow_priority_label(prioritized_phase_name)}",
        f"phase status: {humanize_workflow_priority_label(prioritized_status)}",
        *([f"recommended action: {primary_recommended_action}"] if primary_recommended_action else []),
    ]
    prioritized_signals = dict(prioritized_phase_context.get("signals") or {})
    unresolved_temporal_issue_count = max(
        int(prioritized_signals.get("unresolved_temporal_issue_count") or 0),
        unresolved_registry_temporal_issue_count,
    )
    missing_proof_artifact_count = int(prioritized_signals.get("missing_proof_artifact_count") or 0)
    if unresolved_temporal_issue_count > 0:
        chip_labels.append(f"unresolved chronology issues: {unresolved_temporal_issue_count}")
    if resolved_temporal_issue_count > 0:
        chip_labels.append(f"resolved chronology issues: {resolved_temporal_issue_count}")
    if missing_proof_artifact_count > 0:
        chip_labels.append(f"missing proof artifacts: {missing_proof_artifact_count}")

    return {
        "phase_name": prioritized_phase_name,
        "status": prioritized_status,
        "title": title,
        "description": str(prioritized_phase.get("summary") or "").strip()
        or "Workflow phase guidance still identifies a higher-priority step before drafting.",
        "action_label": action_label,
        "action_url": action_url,
        "action_kind": "link",
        "dashboard_url": dashboard_url,
        "recommended_actions": recommended_actions,
        "chip_labels": chip_labels,
    }


def _build_document_review_workflow_priority(
    *,
    intake_status: Dict[str, Any],
    intake_case_summary: Dict[str, Any],
    workflow_phase_plan: Dict[str, Any],
    document_provenance_summary: Dict[str, Any],
    user_id: Optional[str],
    default_claim_type: Optional[str],
    dashboard_url: str,
    claim_review_map: Dict[str, Dict[str, Any]],
    section_review_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    document_grounding_lane_outcome_summary = (
        intake_case_summary.get("document_grounding_lane_outcome_summary")
        if isinstance(intake_case_summary.get("document_grounding_lane_outcome_summary"), dict)
        else {}
    )
    document_grounding_improvement_next_action = (
        intake_case_summary.get("document_grounding_improvement_next_action")
        if isinstance(intake_case_summary.get("document_grounding_improvement_next_action"), dict)
        else {}
    )
    grounding_action = str(document_grounding_improvement_next_action.get("action") or "").strip().lower()
    if grounding_action in {"refine_document_grounding_strategy", "retarget_document_grounding"}:
        focus_section = str(document_grounding_improvement_next_action.get("focus_section") or "factual_allegations").strip() or "factual_allegations"
        claim_type = str(document_grounding_improvement_next_action.get("claim_type") or default_claim_type or "").strip()
        preferred_support_kind = str(document_grounding_improvement_next_action.get("preferred_support_kind") or "").strip()
        suggested_support_kind = str(document_grounding_improvement_next_action.get("suggested_support_kind") or "").strip()
        suggested_claim_element_id = str(document_grounding_improvement_next_action.get("suggested_claim_element_id") or "").strip()
        attempted_support_kind = str(document_grounding_lane_outcome_summary.get("attempted_support_kind") or "").strip()
        learned_support_kind = str(document_grounding_lane_outcome_summary.get("recommended_future_support_kind") or "").strip()
        if not suggested_claim_element_id:
            suggested_claim_element_id = str(document_grounding_lane_outcome_summary.get("recommended_future_claim_element") or "").strip()
        action_url = _append_review_query_params(
            _resolve_document_review_url(
                user_id=user_id,
                dashboard_url=dashboard_url,
                claim_review_map=claim_review_map,
                section_review_map=section_review_map,
                claim_type=claim_type or default_claim_type,
                section_key=focus_section,
            ),
            claim_type=claim_type,
            follow_up_support_kind=suggested_support_kind or preferred_support_kind or _default_support_kind_for_section(focus_section),
        )
        split_action_url = urlsplit(action_url)
        action_query_pairs = parse_qsl(split_action_url.query, keep_blank_values=True)
        action_query = dict(action_query_pairs)
        ordered_action_query = []
        for key in ("user_id", "claim_type", "section", "follow_up_support_kind"):
            value = str(action_query.pop(key, "") or "").strip()
            if value:
                ordered_action_query.append((key, value))
        for key, value in action_query_pairs:
            if key in {"user_id", "claim_type", "section", "follow_up_support_kind"}:
                continue
            text = str(value or "").strip()
            if text:
                ordered_action_query.append((key, text))
        action_url = urlunsplit(
            (
                split_action_url.scheme,
                split_action_url.netloc,
                split_action_url.path,
                urlencode(ordered_action_query),
                split_action_url.fragment,
            )
        )
        chip_labels = [
            f"grounding status: {humanize_workflow_priority_label(str(document_grounding_improvement_next_action.get('status') or 'stalled').strip() or 'stalled')}"
        ]
        claim_element_id = str(document_grounding_improvement_next_action.get("claim_element_id") or "").strip()
        if claim_element_id:
            chip_labels.append(f"target element: {humanize_workflow_priority_label(claim_element_id)}")
        if suggested_claim_element_id and suggested_claim_element_id != claim_element_id:
            chip_labels.append(f"next target element: {humanize_workflow_priority_label(suggested_claim_element_id)}")
        if preferred_support_kind:
            chip_labels.append(f"current support lane: {humanize_workflow_priority_label(preferred_support_kind)}")
        if attempted_support_kind and attempted_support_kind != preferred_support_kind:
            chip_labels.append(f"attempted lane: {humanize_workflow_priority_label(attempted_support_kind)}")
        if learned_support_kind:
            chip_labels.append(f"learned next lane: {humanize_workflow_priority_label(learned_support_kind)}")
        elif suggested_support_kind:
            chip_labels.append(f"suggested next lane: {humanize_workflow_priority_label(suggested_support_kind)}")
        chip_labels.append(
            f"grounding delta: {float(document_grounding_improvement_next_action.get('fact_backed_ratio_delta') or 0.0):+.2f}"
        )
        description = str(
            document_grounding_improvement_next_action.get("description")
            or "Grounding recovery stalled; switch support lanes or retarget the next grounding cycle."
        ).strip()
        if learned_support_kind:
            description = (
                f"{description} Learned lane preference now favors "
                f"{humanize_workflow_priority_label(learned_support_kind)}."
            )
        if grounding_action == "retarget_document_grounding" and suggested_claim_element_id and suggested_claim_element_id != claim_element_id:
            description = (
                f"{description} Retarget the next grounding pass toward "
                f"{humanize_workflow_priority_label(suggested_claim_element_id)}."
            )
        return {
            "status": "warning",
            "title": (
                "Retarget document grounding"
                if grounding_action == "retarget_document_grounding"
                else "Refine document grounding strategy"
            ),
            "description": description,
            "action_label": (
                "Review grounding retargeting"
                if grounding_action == "retarget_document_grounding"
                else "Review grounding strategy"
            ),
            "action_url": action_url,
            "action_kind": "link",
            "dashboard_url": dashboard_url,
            "chip_labels": chip_labels,
        }

    document_grounding_recovery_action = (
        intake_case_summary.get("document_grounding_recovery_action")
        if isinstance(intake_case_summary.get("document_grounding_recovery_action"), dict)
        else {}
    )
    if str(document_grounding_recovery_action.get("action") or "").strip().lower() == "recover_document_grounding":
        focus_section = str(document_grounding_recovery_action.get("focus_section") or "factual_allegations").strip() or "factual_allegations"
        claim_type = str(document_grounding_recovery_action.get("claim_type") or default_claim_type or "").strip()
        preferred_support_kind = str(document_grounding_recovery_action.get("preferred_support_kind") or "").strip()
        action_url = _append_review_query_params(
            _resolve_document_review_url(
                user_id=user_id,
                dashboard_url=dashboard_url,
                claim_review_map=claim_review_map,
                section_review_map=section_review_map,
                claim_type=claim_type or default_claim_type,
                section_key=focus_section,
            ),
            claim_type=claim_type,
            follow_up_support_kind=preferred_support_kind or _default_support_kind_for_section(focus_section),
        )
        split_action_url = urlsplit(action_url)
        action_query_pairs = parse_qsl(split_action_url.query, keep_blank_values=True)
        action_query = dict(action_query_pairs)
        ordered_action_query = []
        for key in ("user_id", "claim_type", "section", "follow_up_support_kind"):
            value = str(action_query.pop(key, "") or "").strip()
            if value:
                ordered_action_query.append((key, value))
        for key, value in action_query_pairs:
            if key in {"user_id", "claim_type", "section", "follow_up_support_kind"}:
                continue
            text = str(value or "").strip()
            if text:
                ordered_action_query.append((key, text))
        action_url = urlunsplit(
            (
                split_action_url.scheme,
                split_action_url.netloc,
                split_action_url.path,
                urlencode(ordered_action_query),
                split_action_url.fragment,
            )
        )
        chip_labels = [f"fact-backed ratio: {float(document_grounding_recovery_action.get('fact_backed_ratio') or 0.0):.2f}"]
        claim_element_id = str(document_grounding_recovery_action.get("claim_element_id") or "").strip()
        if claim_element_id:
            chip_labels.append(f"target element: {humanize_workflow_priority_label(claim_element_id)}")
        if preferred_support_kind:
            chip_labels.append(f"support lane: {humanize_workflow_priority_label(preferred_support_kind)}")
        missing_fact_bundle = [
            str(item).strip()
            for item in list(document_grounding_recovery_action.get("missing_fact_bundle") or [])
            if str(item).strip()
        ]
        if missing_fact_bundle:
            chip_labels.append(f"missing facts: {', '.join(missing_fact_bundle[:2])}")
        return {
            "status": "warning",
            "title": "Recover document grounding before formalization",
            "description": str(
                document_grounding_recovery_action.get("description")
                or "Strengthen the draft with more fact-backed and artifact-backed support before formalization."
            ).strip(),
            "action_label": "Collect grounding support",
            "action_url": action_url,
            "action_kind": "link",
            "dashboard_url": dashboard_url,
            "chip_labels": chip_labels,
        }

    if isinstance(document_provenance_summary, dict) and document_provenance_summary:
        ratio_present = "fact_backed_ratio" in document_provenance_summary
        fact_backed_ratio = float(document_provenance_summary.get("fact_backed_ratio") or 0.0)
        low_grounding_flag = bool(document_provenance_summary.get("low_grounding_flag"))
        if low_grounding_flag or (ratio_present and fact_backed_ratio < 0.6):
            action_url = _append_review_query_params(
                _resolve_document_review_url(
                    user_id=user_id,
                    dashboard_url=dashboard_url,
                    claim_review_map=claim_review_map,
                    section_review_map=section_review_map,
                    claim_type=default_claim_type,
                    section_key="factual_allegations",
                ),
                follow_up_support_kind=_default_support_kind_for_section("factual_allegations"),
            )
            return {
                "status": "warning",
                "title": "Strengthen document grounding before further revisions",
                "description": (
                    "Increase canonical-fact and artifact-backed support in the draft before broadening revisions."
                ),
                "action_label": "Review factual allegations grounding",
                "action_url": action_url,
                "action_kind": "link",
                "dashboard_url": dashboard_url,
                "chip_labels": [
                    f"fact-backed ratio: {fact_backed_ratio:.2f}",
                    f"summary facts grounded: {int(document_provenance_summary.get('summary_fact_backed_count') or 0)}/{int(document_provenance_summary.get('summary_fact_count') or 0)}",
                    f"claim support grounded: {int(document_provenance_summary.get('claim_supporting_fact_backed_count') or 0)}/{int(document_provenance_summary.get('claim_supporting_fact_count') or 0)}",
                ],
            }

    document_drafting_next_action = (
        intake_case_summary.get("document_drafting_next_action")
        if isinstance(intake_case_summary.get("document_drafting_next_action"), dict)
        else {}
    )
    if str(document_drafting_next_action.get("action") or "").strip().lower() == "realign_document_drafting":
        target_claim_element_id = str(document_drafting_next_action.get("claim_element_id") or "").strip()
        executed_claim_element_id = str(document_drafting_next_action.get("executed_claim_element_id") or "").strip()
        focus_section = str(document_drafting_next_action.get("focus_section") or "claims_for_relief").strip() or "claims_for_relief"
        preferred_support_kind = str(document_drafting_next_action.get("preferred_support_kind") or "").strip()
        action_url = _append_review_query_params(
            _resolve_document_review_url(
                user_id=user_id,
                dashboard_url=dashboard_url,
                claim_review_map=claim_review_map,
                section_review_map=section_review_map,
                claim_type=default_claim_type,
                section_key=focus_section,
            ),
            follow_up_support_kind=_default_support_kind_for_section(focus_section),
        )
        chip_labels = []
        if target_claim_element_id:
            chip_labels.append(f"target element: {humanize_workflow_priority_label(target_claim_element_id)}")
        if executed_claim_element_id:
            chip_labels.append(f"executed first: {humanize_workflow_priority_label(executed_claim_element_id)}")
        if focus_section:
            chip_labels.append(f"focus section: {humanize_workflow_priority_label(focus_section)}")
        if preferred_support_kind:
            chip_labels.append(f"support lane: {humanize_workflow_priority_label(preferred_support_kind)}")
        return {
            "status": "warning",
            "title": "Realign drafting before further revisions",
            "description": str(
                document_drafting_next_action.get("description")
                or "Realign drafting to the top targeted claim element before further revisions."
            ).strip(),
            "action_label": "Open formal complaint builder",
            "action_url": action_url,
            "action_kind": "link",
            "dashboard_url": dashboard_url,
            "chip_labels": chip_labels,
        }

    next_action = intake_status.get("next_action") if isinstance(intake_status.get("next_action"), dict) else {}
    if not next_action and isinstance(intake_case_summary.get("next_action"), dict):
        next_action = intake_case_summary.get("next_action") or {}

    action = str(next_action.get("action") or "").strip().lower()
    if not action:
        return _build_document_review_workflow_phase_priority(
            workflow_phase_plan,
            user_id=user_id,
            default_claim_type=default_claim_type,
            dashboard_url=dashboard_url,
            section_review_map=section_review_map,
            intake_case_summary=intake_case_summary,
        )

    claim_type = str(next_action.get("claim_type") or default_claim_type or "").strip()
    claim_element_id = str(next_action.get("claim_element_id") or "").strip()
    blockers = next_action.get("intake_blockers") if isinstance(next_action.get("intake_blockers"), list) else []
    contradictions = int((intake_case_summary.get("contradiction_summary") or {}).get("count") or 0)
    question_candidates = int((intake_case_summary.get("question_candidate_summary") or {}).get("count") or 0)
    packet_summary = (
        intake_case_summary.get("claim_support_packet_summary")
        if isinstance(intake_case_summary.get("claim_support_packet_summary"), dict)
        else {}
    )
    base_claim_url = _resolve_document_review_url(
        user_id=user_id,
        dashboard_url=dashboard_url,
        claim_review_map=claim_review_map,
        section_review_map=section_review_map,
        claim_type=claim_type,
    )

    status = "warning"
    title = "Review workflow priority before drafting"
    description = "The review dashboard still has a higher-priority step than drafting for this matter."
    action_label = "Open Review Dashboard"
    action_url = dashboard_url
    action_kind = "link"

    if action == "confirm_intake_summary":
        title = "Confirm intake summary before drafting"
        description = "The current intake summary snapshot still needs complainant confirmation before drafting should continue."
        action_label = "Confirm intake summary"
        action_kind = "button"
    elif action == "validate_promoted_support":
        title = "Validate promoted support before drafting"
        description = "Promoted testimony or document support still needs validation before the draft can rely on it."
        action_label = "Review promoted updates"
        action_url = _append_review_query_params(
            base_claim_url,
            alignment_task_update_filter="pending_review",
            alignment_task_update_sort="pending_review_first",
        )
    elif action == "resolve_support_conflicts":
        title = "Resolve support conflicts before drafting"
        description = "Manual-review conflicts are still blocking evidence confidence for a draft-ready complaint."
        action_label = "Review manual conflicts"
        claim_queue_url = base_claim_url
        if _claim_type_in_case_summary_queue(
            intake_case_summary,
            claim_type=claim_type,
            summary_key="manual_review_claim_summary",
        ):
            claim_queue_url = _append_review_query_params(
                claim_queue_url,
                alignment_task_update_filter="manual_review",
                alignment_task_update_sort="manual_review_first",
            )
        elif _claim_type_in_case_summary_queue(
            intake_case_summary,
            claim_type=claim_type,
            summary_key="pending_review_claim_summary",
        ):
            claim_queue_url = _append_review_query_params(
                claim_queue_url,
                alignment_task_update_filter="pending_review",
                alignment_task_update_sort="pending_review_first",
            )
        action_url = _append_review_query_params(
            claim_queue_url,
            alignment_task_update_filter="manual_review",
            alignment_task_update_sort="manual_review_first",
        )
    elif action == "fill_evidence_gaps":
        title = "Fill evidence gaps before drafting"
        description = "The current backend priority still points to missing support for a claim element in this complaint."
        action_label = "Review evidence task"
        action_url = _append_review_query_params(
            base_claim_url,
            follow_up_support_kind="evidence",
            alignment_task_update_filter="active",
        )
    elif action in {"address_gaps", "continue_denoising", "build_knowledge_graph"}:
        if action == "address_gaps":
            title = "Resolve intake gaps before drafting"
            description = "Intake still has unresolved factual gaps that can weaken the document if drafting continues too early."
            action_label = "Review intake gaps"
        elif action == "continue_denoising":
            title = "Continue intake denoising before drafting"
            description = "Contradictions or unanswered intake questions still need another denoising pass before the document stabilizes."
            action_label = "Review denoising queue"
        else:
            title = "Review intake graph inputs before drafting"
            description = "The intake graph inputs are not complete enough to support a stable draft handoff yet."
            action_label = "Review intake graph inputs"
        action_url = _append_review_query_params(
            _resolve_document_review_url(
                user_id=user_id,
                dashboard_url=dashboard_url,
                claim_review_map=claim_review_map,
                section_review_map=section_review_map,
                claim_type=claim_type,
                section_key="summary_of_facts",
            ),
            follow_up_support_kind=_default_support_kind_for_section("summary_of_facts"),
            alignment_task_update_filter="active",
        )
    elif action == "build_dependency_graph":
        title = "Review dependency inputs before drafting"
        description = "Cross-section dependency mapping is still incomplete, so the case theory may not be stable enough for drafting."
        action_label = "Review dependency inputs"
        action_url = _append_review_query_params(
            _resolve_document_review_url(
                user_id=user_id,
                dashboard_url=dashboard_url,
                claim_review_map=claim_review_map,
                section_review_map=section_review_map,
                claim_type=claim_type,
                section_key="chronology",
            ),
            follow_up_support_kind="evidence",
            alignment_task_update_filter="active",
        )
    elif action in {"build_legal_graph", "perform_neurosymbolic_matching"}:
        title = (
            "Review legal graph inputs before drafting"
            if action == "build_legal_graph"
            else "Review matching inputs before drafting"
        )
        description = (
            "Formalization still needs the legal graph that organizes statutes and requirements for this complaint."
            if action == "build_legal_graph"
            else "Formal claim-to-law matching is still pending, so the draft may outrun the current legal targeting."
        )
        action_label = (
            "Review legal graph inputs"
            if action == "build_legal_graph"
            else "Review matching inputs"
        )
        action_url = _append_review_query_params(
            _resolve_document_review_url(
                user_id=user_id,
                dashboard_url=dashboard_url,
                claim_review_map=claim_review_map,
                section_review_map=section_review_map,
                claim_type=claim_type,
                section_key="claims_for_relief",
            ),
            follow_up_support_kind=_default_support_kind_for_section("claims_for_relief"),
            alignment_task_update_filter="manual_review",
            alignment_task_update_sort="manual_review_first",
        )
    elif action == "build_claim_support_packets":
        title = "Build support packets before drafting"
        description = "Evidence has been collected, but the packet-building step still needs to run before the draft can rely on those signals."
        action_label = "Build support packets"
        action_url = _append_review_query_params(
            base_claim_url,
            follow_up_support_kind="evidence",
            alignment_task_update_filter="active",
        )
    elif action == "complete_evidence":
        status = "ready"
        title = "Evidence is ready for formal drafting"
        description = "The backend priority has advanced to document drafting, so continuing here is consistent with the current workflow."
    elif action == "generate_formal_complaint":
        status = "ready"
        title = "Drafting is the current workflow priority"
        description = "The backend priority already points to formal complaint generation, so you can continue drafting here."
    elif action == "complete_formalization":
        status = "ready"
        title = "Formalization is complete"
        description = "Current workflow signals do not show a higher-priority review step blocking this draft."

    chip_labels = [f"recommended action: {action}"]
    if claim_type:
        chip_labels.append(f"focus claim: {humanize_workflow_priority_label(claim_type)}")
    if claim_element_id:
        chip_labels.append(f"focus element: {claim_element_id}")
    if blockers:
        chip_labels.append(f"blockers: {len([item for item in blockers if str(item).strip()])}")
    if contradictions > 0:
        chip_labels.append(f"contradictions: {contradictions}")
    if question_candidates > 0:
        chip_labels.append(f"question candidates: {question_candidates}")
    if action == "resolve_support_conflicts":
        chip_labels.append(
            f"packet escalations: {int(packet_summary.get('claim_support_reviewable_escalation_count') or 0)}"
        )
    if action in {"generate_formal_complaint", "complete_evidence"}:
        chip_labels.append(
            f"proof readiness: {float(packet_summary.get('proof_readiness_score') or 0):.2f}"
        )

    return {
        "status": status,
        "title": title,
        "description": description,
        "action_label": action_label,
        "action_url": action_url,
        "action_kind": action_kind,
        "dashboard_url": dashboard_url,
        "chip_labels": chip_labels,
    }


def _build_document_builder_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else {}
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    drafting_readiness = payload.get("drafting_readiness") if isinstance(payload.get("drafting_readiness"), dict) else {}
    sections = drafting_readiness.get("sections") if isinstance(drafting_readiness.get("sections"), dict) else {}
    claims = drafting_readiness.get("claims") if isinstance(drafting_readiness.get("claims"), list) else []
    guardrails = (
        drafting_readiness.get("drafting_guardrails")
        if isinstance(drafting_readiness.get("drafting_guardrails"), dict)
        else {}
    )
    document_provenance_summary = (
        dict(payload.get("document_provenance_summary") or draft.get("document_provenance_summary") or {})
        if isinstance(payload.get("document_provenance_summary") or draft.get("document_provenance_summary"), dict)
        else {}
    )

    support_status_counts: Dict[str, int] = {}
    section_support: List[Dict[str, Any]] = []
    support_source_refs: List[str] = []
    for section_key, section in sections.items():
        if not isinstance(section, dict):
            continue
        support_status = str(section.get("support_status") or section.get("status") or "ready").strip().lower() or "ready"
        support_status_counts[support_status] = support_status_counts.get(support_status, 0) + 1
        source_refs = [
            str(item or "").strip()
            for item in list(section.get("source_refs") or [])
            if str(item or "").strip()
        ]
        support_source_refs.extend(source_refs)
        section_support.append(
            {
                "section_key": str(section_key or "").strip(),
                "title": section.get("title") or str(section_key or "").replace("_", " ").title(),
                "status": str(section.get("status") or "ready").strip().lower() or "ready",
                "support_status": support_status,
                "claim_element_count": int(section.get("claim_element_count") or len(section.get("claim_elements") or [])),
                "source_ref_count": len(source_refs),
                "explicit_gap_count": len(section.get("explicit_gaps") or []),
                "review_url": section.get("review_url"),
            }
        )

    source_family_counts: Dict[str, int] = {}
    artifact_family_counts: Dict[str, int] = {}
    content_origin_counts: Dict[str, int] = {}
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        for source_key, target in (
            ("source_family_counts", source_family_counts),
            ("artifact_family_counts", artifact_family_counts),
            ("content_origin_counts", content_origin_counts),
        ):
            counts = claim.get(source_key) if isinstance(claim.get(source_key), dict) else {}
            for label, count in counts.items():
                normalized_label = str(label or "").strip()
                if not normalized_label:
                    continue
                target[normalized_label] = target.get(normalized_label, 0) + int(count or 0)

    guardrail_warnings = [
        warning
        for warning in list(guardrails.get("warnings") or [])
        if isinstance(warning, dict)
    ]
    warning_type_counts: Dict[str, int] = {}
    for warning in guardrail_warnings:
        warning_type = str(warning.get("warning_type") or warning.get("code") or "drafting_warning").strip()
        if warning_type:
            warning_type_counts[warning_type] = warning_type_counts.get(warning_type, 0) + 1

    artifact_entries = []
    for format_name, artifact in artifacts.items():
        if not isinstance(artifact, dict):
            continue
        artifact_entries.append(
            {
                "format": str(format_name or "").strip(),
                "filename": artifact.get("filename"),
                "size_bytes": int(artifact.get("size_bytes") or 0),
                "download_url": artifact.get("download_url"),
                "managed_download": bool(artifact.get("download_url")),
            }
        )

    return {
        "status": str(drafting_readiness.get("status") or "ready").strip().lower() or "ready",
        "warning_count": int(drafting_readiness.get("warning_count") or 0),
        "guardrail_warning_count": int(guardrails.get("warning_count") or len(guardrail_warnings)),
        "guardrail_blocker_count": int(guardrails.get("blocker_count") or 0),
        "support_status_counts": support_status_counts,
        "section_support": section_support,
        "source_ref_count": len(_dedupe_text_values(support_source_refs)),
        "source_family_counts": source_family_counts,
        "artifact_family_counts": artifact_family_counts,
        "content_origin_counts": content_origin_counts,
        "warning_type_counts": warning_type_counts,
        "artifact_provenance": {
            "managed_output_dir": str(_default_generated_documents_root()),
            "artifact_count": len(artifact_entries),
            "downloadable_count": len([entry for entry in artifact_entries if entry.get("managed_download")]),
            "artifacts": artifact_entries,
        },
        "document_provenance_summary": document_provenance_summary,
    }


def _annotate_review_links(payload: Dict[str, Any], *, mediator: Any, user_id: Optional[str]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload

    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else {}
    source_context = draft.get("source_context") if isinstance(draft.get("source_context"), dict) else {}
    resolved_user_id = user_id or source_context.get("user_id")
    drafting_readiness = payload.get("drafting_readiness") if isinstance(payload.get("drafting_readiness"), dict) else {}
    claim_entries = drafting_readiness.get("claims") if isinstance(drafting_readiness.get("claims"), list) else []
    section_entries = drafting_readiness.get("sections") if isinstance(drafting_readiness.get("sections"), dict) else {}
    dashboard_url = _build_review_url(user_id=resolved_user_id)
    default_review_intent = _build_review_intent(user_id=resolved_user_id)
    intake_status = build_intake_status_summary(mediator)
    intake_case_summary = build_intake_case_review_summary(mediator)
    intake_warning_entries = build_intake_warning_entries(intake_status)
    intake_summary_handoff = {}
    if isinstance(intake_status.get("intake_summary_handoff"), dict) and intake_status.get("intake_summary_handoff"):
        intake_summary_handoff = dict(intake_status["intake_summary_handoff"])
    elif isinstance(intake_case_summary.get("intake_summary_handoff"), dict) and intake_case_summary.get("intake_summary_handoff"):
        intake_summary_handoff = dict(intake_case_summary["intake_summary_handoff"])

    claim_links = []
    claim_types = []
    claim_review_map: Dict[str, Dict[str, Any]] = {}
    for claim in claim_entries:
        if not isinstance(claim, dict):
            continue
        claim_type = str(claim.get("claim_type") or "").strip()
        if not claim_type:
            continue
        claim_types.append(claim_type)
        claim_review_url = _build_review_url(user_id=resolved_user_id, claim_type=claim_type)
        claim_review_intent = _build_review_intent(
            user_id=resolved_user_id,
            claim_type=claim_type,
        )
        claim["review_url"] = claim_review_url
        claim["review_context"] = {
            "user_id": resolved_user_id,
            "claim_type": claim_type,
        }
        claim["review_intent"] = claim_review_intent
        claim["chip_labels"] = _build_claim_review_chip_labels(claim)
        if str(claim.get("status") or "").strip().lower() in {"warning", "blocked"}:
            claim["warnings"] = _merge_warning_entries(claim.get("warnings"), intake_warning_entries)
        claim_review_map[claim_type] = {
            "review_url": claim_review_url,
            "review_context": claim["review_context"],
            "review_intent": claim_review_intent,
            "chip_labels": list(claim.get("chip_labels") or []),
        }
        claim_links.append(
            {
                "claim_type": claim_type,
                "review_url": claim_review_url,
                "review_intent": claim_review_intent,
                "chip_labels": list(claim.get("chip_labels") or []),
            }
        )

    section_links = []
    section_review_map: Dict[str, Dict[str, Any]] = {}
    for section_key, section in section_entries.items():
        if not isinstance(section, dict):
            continue
        resolved_section_key = str(section_key or "").strip()
        if not resolved_section_key:
            continue
        related_claim_types = _section_claim_types(resolved_section_key, claim_types)
        primary_claim_type = related_claim_types[0] if len(related_claim_types) == 1 else None
        section_review_url = _build_review_url(
            user_id=resolved_user_id,
            claim_type=primary_claim_type,
            section=resolved_section_key,
        )
        section_review_intent = _build_review_intent(
            user_id=resolved_user_id,
            claim_type=primary_claim_type,
            section=resolved_section_key,
            follow_up_support_kind=_default_support_kind_for_section(resolved_section_key),
        )
        section_claim_links = [
            {
                "claim_type": claim_type,
                "review_url": _build_review_url(
                    user_id=resolved_user_id,
                    claim_type=claim_type,
                    section=resolved_section_key,
                ),
                "review_intent": _build_review_intent(
                    user_id=resolved_user_id,
                    claim_type=claim_type,
                    section=resolved_section_key,
                    follow_up_support_kind=_default_support_kind_for_section(resolved_section_key),
                ),
            }
            for claim_type in related_claim_types
        ]
        review_context = {
            "user_id": resolved_user_id,
            "section": resolved_section_key,
            "claim_type": primary_claim_type,
        }
        section["review_url"] = section_review_url
        section["review_context"] = review_context
        section["review_intent"] = section_review_intent
        if str(section.get("status") or "").strip().lower() in {"warning", "blocked"}:
            section["warnings"] = _merge_warning_entries(section.get("warnings"), intake_warning_entries)
        if section_claim_links:
            section["claim_links"] = section_claim_links
        section_review_map[resolved_section_key] = {
            "review_url": section_review_url,
            "review_context": review_context,
            "review_intent": section_review_intent,
        }
        section_links.append(
            {
                "section_key": resolved_section_key,
                "title": section.get("title") or resolved_section_key,
                "review_url": section_review_url,
                "review_context": review_context,
                "review_intent": section_review_intent,
                "claim_links": section_claim_links,
            }
        )

    preferred_section = None
    for section_key, section in section_entries.items():
        if not isinstance(section, dict):
            continue
        if str(section.get("status") or "").lower() in {"warning", "blocked"}:
            preferred_section = str(section_key or "").strip() or None
            break

    preferred_claim_type = None
    for claim in claim_entries:
        if not isinstance(claim, dict):
            continue
        if str(claim.get("status") or "").lower() in {"warning", "blocked"}:
            preferred_claim_type = str(claim.get("claim_type") or "").strip() or None
            break

    if str(drafting_readiness.get("status") or "").strip().lower() in {"warning", "blocked"}:
        drafting_readiness["warnings"] = _merge_warning_entries(
            drafting_readiness.get("warnings"),
            intake_warning_entries,
        )

    document_optimization = payload.get("document_optimization")
    intake_case_summary = _merge_claim_temporal_gap_summary(intake_case_summary, document_optimization)
    if isinstance(document_optimization, dict):
        optimization_intake_status = document_optimization.get("intake_status")
        if isinstance(optimization_intake_status, dict) and optimization_intake_status and not intake_status:
            document_optimization["intake_status"] = dict(optimization_intake_status)
        else:
            document_optimization["intake_status"] = dict(intake_status)

        optimization_case_summary = document_optimization.get("intake_case_summary")
        if intake_case_summary:
            document_optimization["intake_case_summary"] = dict(intake_case_summary)
        elif isinstance(optimization_case_summary, dict) and optimization_case_summary:
            document_optimization["intake_case_summary"] = dict(optimization_case_summary)

        optimization_constraints = document_optimization.get("intake_constraints")
        if intake_warning_entries:
            document_optimization["intake_constraints"] = list(intake_warning_entries)
        elif isinstance(optimization_constraints, list) and optimization_constraints:
            document_optimization["intake_constraints"] = list(optimization_constraints)

        trace_storage = document_optimization.get("trace_storage")
        trace_storage = trace_storage if isinstance(trace_storage, dict) else {}
        trace_cid = str(trace_storage.get("cid") or document_optimization.get("artifact_cid") or "").strip()
        if trace_cid:
            document_optimization["trace_download_url"] = _build_optimization_trace_url(trace_cid)
            document_optimization["trace_view_url"] = _build_optimization_trace_view_url(trace_cid)

    workflow_phase_plan = (
        drafting_readiness.get("workflow_phase_plan")
        if isinstance(drafting_readiness.get("workflow_phase_plan"), dict)
        else {}
    )
    workflow_phase_priority = _build_document_review_workflow_phase_priority(
        workflow_phase_plan,
        user_id=resolved_user_id,
        default_claim_type=preferred_claim_type,
        dashboard_url=dashboard_url,
        section_review_map=section_review_map,
        intake_case_summary=intake_case_summary,
    )
    workflow_priority = _build_document_review_workflow_priority(
        intake_status=intake_status,
        intake_case_summary=intake_case_summary,
        workflow_phase_plan=workflow_phase_plan,
        document_provenance_summary=(
            dict(payload.get("document_provenance_summary") or draft.get("document_provenance_summary") or {})
            if isinstance(payload.get("document_provenance_summary") or draft.get("document_provenance_summary"), dict)
            else {}
        ),
        user_id=resolved_user_id,
        default_claim_type=preferred_claim_type,
        dashboard_url=dashboard_url,
        claim_review_map=claim_review_map,
        section_review_map=section_review_map,
    )
    workflow_priority = _annotate_workflow_priority_with_temporal_gap_summary(
        workflow_priority,
        intake_case_summary,
    )

    payload["review_links"] = {
        "dashboard_url": dashboard_url,
        "claims": claim_links,
        "sections": section_links,
        "intake_status": intake_status,
        "intake_case_summary": intake_case_summary,
        "workflow_targeting_summary": (
            dict(intake_case_summary.get("workflow_targeting_summary") or {})
            if isinstance(intake_case_summary.get("workflow_targeting_summary"), dict)
            else {}
        ),
        "document_workflow_execution_summary": (
            dict(intake_case_summary.get("document_workflow_execution_summary") or {})
            if isinstance(intake_case_summary.get("document_workflow_execution_summary"), dict)
            else {}
        ),
        "document_provenance_summary": (
            dict(payload.get("document_provenance_summary") or draft.get("document_provenance_summary") or {})
            if isinstance(payload.get("document_provenance_summary") or draft.get("document_provenance_summary"), dict)
            else {}
        ),
        "document_focus_preview": _build_document_focus_preview(draft),
        "document_drafting_next_action": (
            dict(intake_case_summary.get("document_drafting_next_action") or {})
            if isinstance(intake_case_summary.get("document_drafting_next_action"), dict)
            else {}
        ),
        "document_grounding_improvement_summary": (
            dict(intake_case_summary.get("document_grounding_improvement_summary") or {})
            if isinstance(intake_case_summary.get("document_grounding_improvement_summary"), dict)
            else {}
        ),
        "document_grounding_lane_outcome_summary": (
            dict(intake_case_summary.get("document_grounding_lane_outcome_summary") or {})
            if isinstance(intake_case_summary.get("document_grounding_lane_outcome_summary"), dict)
            else {}
        ),
        "document_grounding_improvement_next_action": (
            dict(intake_case_summary.get("document_grounding_improvement_next_action") or {})
            if isinstance(intake_case_summary.get("document_grounding_improvement_next_action"), dict)
            else {}
        ),
        "document_grounding_recovery_action": (
            dict(intake_case_summary.get("document_grounding_recovery_action") or {})
            if isinstance(intake_case_summary.get("document_grounding_recovery_action"), dict)
            else {}
        ),
        "recommended_next_action": (
            str((intake_status.get("next_action") or {}).get("action") or "")
            if isinstance(intake_status.get("next_action"), dict)
            else ""
        ),
        "workflow_priority": workflow_priority,
        "workflow_phase_priority": workflow_phase_priority,
        "primary_validation_target": (
            dict(intake_status.get("primary_validation_target"))
            if isinstance(intake_status.get("primary_validation_target"), dict)
            else {}
        ),
    }
    payload["review_intent"] = _build_review_intent(
        user_id=resolved_user_id,
        claim_type=preferred_claim_type,
        section=preferred_section,
        follow_up_support_kind=_default_support_kind_for_section(preferred_section),
    )
    payload["document_builder_summary"] = _build_document_builder_summary(payload)
    if intake_summary_handoff:
        payload["intake_summary_handoff"] = intake_summary_handoff
        document_optimization = payload.get("document_optimization")
        if isinstance(document_optimization, dict):
            document_optimization["intake_summary_handoff"] = dict(intake_summary_handoff)
    return _annotate_checklist_review_links(
        payload,
        dashboard_url=dashboard_url,
        claim_review_map=claim_review_map,
        section_review_map=section_review_map,
        default_review_intent=payload["review_intent"],
        intake_status=payload["review_links"]["intake_status"],
    )
