"""Follow-up summary functions moved from claim_support_review."""

from __future__ import annotations

from mediator.claim_support_review import (
    _aggregate_adaptive_retry_metrics,
    _aggregate_authority_search_program_metrics,
    _aggregate_fact_targeting_metrics,
    _aggregate_graph_gap_context_metrics,
    _aggregate_graph_support_metrics,
    _aggregate_quality_routing_metrics,
    _aggregate_rule_candidate_metrics,
    _aggregate_search_warning_metrics,
    _select_last_adaptive_retry,
)


def summarize_follow_up_history_claim(
    history_entries: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    entries = history_entries if isinstance(history_entries, list) else []
    status_counts: Dict[str, int] = {}
    support_kind_counts: Dict[str, int] = {}
    execution_mode_counts: Dict[str, int] = {}
    query_strategy_counts: Dict[str, int] = {}
    follow_up_focus_counts: Dict[str, int] = {}
    resolution_status_counts: Dict[str, int] = {}
    resolution_applied_counts: Dict[str, int] = {}
    temporal_rule_status_counts: Dict[str, int] = {}
    temporal_rule_blocking_reason_counts: Dict[str, int] = {}
    temporal_resolution_status_counts: Dict[str, int] = {}
    adaptive_query_strategy_counts: Dict[str, int] = {}
    adaptive_retry_reason_counts: Dict[str, int] = {}
    selected_authority_program_type_counts: Dict[str, int] = {}
    selected_authority_intent_counts: Dict[str, int] = {}
    selected_authority_jurisdiction_counts: Dict[str, int] = {}
    selected_authority_forum_counts: Dict[str, int] = {}
    selected_authority_family_counts: Dict[str, int] = {}
    selected_authority_defense_theme_counts: Dict[str, int] = {}
    selected_authority_time_window_counts: Dict[str, int] = {}
    selected_authority_graph_gap_bias_counts: Dict[str, int] = {}
    selected_authority_program_bias_counts: Dict[str, int] = {}
    selected_authority_program_rule_bias_counts: Dict[str, int] = {}
    source_family_counts: Dict[str, int] = {}
    record_scope_counts: Dict[str, int] = {}
    artifact_family_counts: Dict[str, int] = {}
    corpus_family_counts: Dict[str, int] = {}
    content_origin_counts: Dict[str, int] = {}
    adaptive_retry_entry_count = 0
    priority_penalized_entry_count = 0
    zero_result_entry_count = 0
    last_adaptive_retry: Optional[Dict[str, Any]] = None
    fact_targeting_metrics = _aggregate_fact_targeting_metrics(entries)
    quality_routing_metrics = _aggregate_quality_routing_metrics(entries)
    graph_gap_context_metrics = _aggregate_graph_gap_context_metrics(entries)

    def _increment_count(counts: Dict[str, int], value: Any) -> None:
        normalized = str(value or "").strip()
        if normalized:
            counts[normalized] = counts.get(normalized, 0) + 1

    def _time_window_label(value: Any) -> str:
        if not isinstance(value, dict):
            return ""
        parts = [
            str(value.get("time_window_type") or "").strip(),
            str(value.get("profile_id") or "").strip(),
            str(value.get("status") or "").strip(),
        ]
        return ":".join([part for part in parts if part])

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status") or "unknown")
        support_kind = str(entry.get("support_kind") or "unknown")
        execution_mode = str(entry.get("execution_mode") or "unknown")
        query_strategy = str(entry.get("query_strategy") or "unknown")
        follow_up_focus = str(entry.get("follow_up_focus") or "unknown")
        resolution_status = str(entry.get("resolution_status") or "")
        resolution_applied = str(entry.get("resolution_applied") or "")
        temporal_rule_status = str(entry.get("temporal_rule_status") or "")
        adaptive_retry_applied = bool(entry.get("adaptive_retry_applied", False))
        adaptive_query_strategy = str(entry.get("adaptive_query_strategy") or "")
        adaptive_retry_reason = str(entry.get("adaptive_retry_reason") or "")
        adaptive_priority_penalty = int(entry.get("adaptive_priority_penalty", 0) or 0)
        zero_result = bool(entry.get("zero_result", False))
        selected_search_program_type = str(entry.get("selected_search_program_type") or "")
        selected_search_program_intent = str(
            entry.get("selected_search_program_intent") or entry.get("authority_intent") or ""
        )
        selected_search_program_jurisdiction = str(
            entry.get("selected_search_program_jurisdiction") or ""
        )
        selected_search_program_forum = str(entry.get("selected_search_program_forum") or "")
        selected_search_program_families = (
            entry.get("selected_search_program_families")
            if isinstance(entry.get("selected_search_program_families"), list)
            else []
        )
        selected_search_program_defense_themes = (
            entry.get("selected_search_program_defense_themes")
            if isinstance(entry.get("selected_search_program_defense_themes"), list)
            else []
        )
        selected_search_program_time_window = (
            entry.get("selected_search_program_time_window")
            if isinstance(entry.get("selected_search_program_time_window"), dict)
            else {}
        )
        selected_search_program_bias = str(entry.get("selected_search_program_bias") or "")
        selected_search_program_rule_bias = str(entry.get("selected_search_program_rule_bias") or "")
        selected_search_program_graph_gap_bias = str(
            entry.get("selected_search_program_graph_gap_bias") or ""
        )
        source_family = str(entry.get("source_family") or "")
        record_scope = str(entry.get("record_scope") or "")
        artifact_family = str(entry.get("artifact_family") or "")
        corpus_family = str(entry.get("corpus_family") or "")
        content_origin = str(entry.get("content_origin") or "")

        status_counts[status] = status_counts.get(status, 0) + 1
        support_kind_counts[support_kind] = support_kind_counts.get(support_kind, 0) + 1
        execution_mode_counts[execution_mode] = execution_mode_counts.get(execution_mode, 0) + 1
        query_strategy_counts[query_strategy] = query_strategy_counts.get(query_strategy, 0) + 1
        follow_up_focus_counts[follow_up_focus] = follow_up_focus_counts.get(follow_up_focus, 0) + 1
        if resolution_status:
            resolution_status_counts[resolution_status] = resolution_status_counts.get(resolution_status, 0) + 1
        if resolution_applied:
            resolution_applied_counts[resolution_applied] = (
                resolution_applied_counts.get(resolution_applied, 0) + 1
            )
        if temporal_rule_status:
            temporal_rule_status_counts[temporal_rule_status] = (
                temporal_rule_status_counts.get(temporal_rule_status, 0) + 1
            )
        for reason in (entry.get("temporal_rule_blocking_reasons") or []):
            normalized_reason = str(reason or "").strip()
            if not normalized_reason:
                continue
            temporal_rule_blocking_reason_counts[normalized_reason] = (
                temporal_rule_blocking_reason_counts.get(normalized_reason, 0) + 1
            )
        if follow_up_focus == "temporal_gap_closure" and resolution_status:
            temporal_resolution_status_counts[resolution_status] = (
                temporal_resolution_status_counts.get(resolution_status, 0) + 1
            )
        if adaptive_retry_applied:
            adaptive_retry_entry_count += 1
        if adaptive_priority_penalty > 0:
            priority_penalized_entry_count += 1
        if adaptive_query_strategy:
            adaptive_query_strategy_counts[adaptive_query_strategy] = (
                adaptive_query_strategy_counts.get(adaptive_query_strategy, 0) + 1
            )
        if adaptive_retry_reason:
            adaptive_retry_reason_counts[adaptive_retry_reason] = (
                adaptive_retry_reason_counts.get(adaptive_retry_reason, 0) + 1
            )
        if selected_search_program_type:
            selected_authority_program_type_counts[selected_search_program_type] = (
                selected_authority_program_type_counts.get(selected_search_program_type, 0) + 1
            )
        if selected_search_program_intent:
            selected_authority_intent_counts[selected_search_program_intent] = (
                selected_authority_intent_counts.get(selected_search_program_intent, 0) + 1
            )
        _increment_count(
            selected_authority_jurisdiction_counts,
            selected_search_program_jurisdiction,
        )
        _increment_count(selected_authority_forum_counts, selected_search_program_forum)
        for family in selected_search_program_families:
            _increment_count(selected_authority_family_counts, family)
        for theme in selected_search_program_defense_themes:
            _increment_count(selected_authority_defense_theme_counts, theme)
        _increment_count(
            selected_authority_time_window_counts,
            _time_window_label(selected_search_program_time_window),
        )
        if selected_search_program_bias:
            selected_authority_program_bias_counts[selected_search_program_bias] = (
                selected_authority_program_bias_counts.get(selected_search_program_bias, 0) + 1
            )
        if selected_search_program_rule_bias:
            selected_authority_program_rule_bias_counts[selected_search_program_rule_bias] = (
                selected_authority_program_rule_bias_counts.get(selected_search_program_rule_bias, 0) + 1
            )
        if selected_search_program_graph_gap_bias:
            selected_authority_graph_gap_bias_counts[selected_search_program_graph_gap_bias] = (
                selected_authority_graph_gap_bias_counts.get(selected_search_program_graph_gap_bias, 0) + 1
            )
        if source_family:
            source_family_counts[source_family] = source_family_counts.get(source_family, 0) + 1
        if record_scope:
            record_scope_counts[record_scope] = record_scope_counts.get(record_scope, 0) + 1
        if artifact_family:
            artifact_family_counts[artifact_family] = artifact_family_counts.get(artifact_family, 0) + 1
        if corpus_family:
            corpus_family_counts[corpus_family] = corpus_family_counts.get(corpus_family, 0) + 1
        if content_origin:
            content_origin_counts[content_origin] = content_origin_counts.get(content_origin, 0) + 1
        if zero_result:
            zero_result_entry_count += 1
        if adaptive_retry_applied:
            last_adaptive_retry = _select_last_adaptive_retry(
                last_adaptive_retry,
                timestamp=entry.get("timestamp"),
                claim_element_id=entry.get("claim_element_id"),
                claim_element_text=entry.get("claim_element_text"),
                adaptive_query_strategy=adaptive_query_strategy,
                reason=adaptive_retry_reason,
            )

    warning_metrics = _aggregate_search_warning_metrics(entries)
    summary = {
        "total_entry_count": len([entry for entry in entries if isinstance(entry, dict)]),
        "status_counts": status_counts,
        "support_kind_counts": support_kind_counts,
        "execution_mode_counts": execution_mode_counts,
        "query_strategy_counts": query_strategy_counts,
        "follow_up_focus_counts": follow_up_focus_counts,
        "resolution_status_counts": resolution_status_counts,
        "resolution_applied_counts": resolution_applied_counts,
        "temporal_gap_task_count": len(
            [
                entry
                for entry in entries
                if isinstance(entry, dict)
                and entry.get("follow_up_focus") == "temporal_gap_closure"
            ]
        ),
        "temporal_gap_targeted_task_count": len(
            [
                entry
                for entry in entries
                if isinstance(entry, dict)
                and entry.get("query_strategy") == "temporal_gap_targeted"
            ]
        ),
        "ontology_quality_gap_task_count": len(
            [
                entry
                for entry in entries
                if isinstance(entry, dict)
                and entry.get("follow_up_focus") == "ontology_quality_gap_closure"
            ]
        ),
        "ontology_quality_gap_targeted_task_count": len(
            [
                entry
                for entry in entries
                if isinstance(entry, dict)
                and entry.get("query_strategy") == "ontology_quality_gap_targeted"
            ]
        ),
        "temporal_rule_status_counts": temporal_rule_status_counts,
        "temporal_rule_blocking_reason_counts": temporal_rule_blocking_reason_counts,
        "temporal_resolution_status_counts": temporal_resolution_status_counts,
        "quality_signal_counts": quality_routing_metrics["quality_signal_counts"],
        "primary_quality_signal_counts": quality_routing_metrics["primary_quality_signal_counts"],
        "quality_follow_up_action_counts": quality_routing_metrics["quality_follow_up_action_counts"],
        "adaptive_retry_entry_count": adaptive_retry_entry_count,
        "priority_penalized_entry_count": priority_penalized_entry_count,
        "adaptive_query_strategy_counts": adaptive_query_strategy_counts,
        "adaptive_retry_reason_counts": adaptive_retry_reason_counts,
        "selected_authority_program_type_counts": selected_authority_program_type_counts,
        "selected_authority_intent_counts": selected_authority_intent_counts,
        "selected_authority_jurisdiction_counts": selected_authority_jurisdiction_counts,
        "selected_authority_forum_counts": selected_authority_forum_counts,
        "selected_authority_family_counts": selected_authority_family_counts,
        "selected_authority_defense_theme_counts": selected_authority_defense_theme_counts,
        "selected_authority_time_window_counts": selected_authority_time_window_counts,
        "selected_authority_program_bias_counts": selected_authority_program_bias_counts,
        "selected_authority_program_rule_bias_counts": selected_authority_program_rule_bias_counts,
        "selected_authority_graph_gap_bias_counts": selected_authority_graph_gap_bias_counts,
        "source_family_counts": source_family_counts,
        "record_scope_counts": record_scope_counts,
        "artifact_family_counts": artifact_family_counts,
        "corpus_family_counts": corpus_family_counts,
        "content_origin_counts": content_origin_counts,
        "graph_gap_context_task_count": graph_gap_context_metrics["graph_gap_context_task_count"],
        "graph_gap_has_support_task_count": graph_gap_context_metrics["graph_gap_has_support_task_count"],
        "graph_gap_empty_task_count": graph_gap_context_metrics["graph_gap_empty_task_count"],
        "graph_gap_total_fact_count": graph_gap_context_metrics["graph_gap_total_fact_count"],
        "graph_gap_unique_fact_count": graph_gap_context_metrics["graph_gap_unique_fact_count"],
        "graph_gap_duplicate_fact_count": graph_gap_context_metrics["graph_gap_duplicate_fact_count"],
        "graph_gap_semantic_cluster_count": graph_gap_context_metrics["graph_gap_semantic_cluster_count"],
        "graph_gap_semantic_duplicate_count": graph_gap_context_metrics["graph_gap_semantic_duplicate_count"],
        "graph_gap_strength_counts": graph_gap_context_metrics["graph_gap_strength_counts"],
        "graph_gap_recommended_action_counts": graph_gap_context_metrics["graph_gap_recommended_action_counts"],
        "graph_gap_priority_adjustment_counts": graph_gap_context_metrics["graph_gap_priority_adjustment_counts"],
        "graph_gap_source_family_counts": graph_gap_context_metrics["graph_gap_source_family_counts"],
        "graph_gap_artifact_family_counts": graph_gap_context_metrics["graph_gap_artifact_family_counts"],
        "graph_gap_corpus_family_counts": graph_gap_context_metrics["graph_gap_corpus_family_counts"],
        "graph_gap_content_origin_counts": graph_gap_context_metrics["graph_gap_content_origin_counts"],
        "graph_gap_fact_registry_summary": graph_gap_context_metrics["graph_gap_fact_registry_summary"],
        "graph_gap_query_task_count": graph_gap_context_metrics["graph_gap_query_task_count"],
        "graph_gap_query_has_support_task_count": graph_gap_context_metrics[
            "graph_gap_query_has_support_task_count"
        ],
        "graph_gap_query_empty_task_count": graph_gap_context_metrics["graph_gap_query_empty_task_count"],
        "graph_gap_query_result_count": graph_gap_context_metrics["graph_gap_query_result_count"],
        "graph_gap_query_missing_support_kind_counts": graph_gap_context_metrics[
            "graph_gap_query_missing_support_kind_counts"
        ],
        "graph_gap_query_strength_counts": graph_gap_context_metrics["graph_gap_query_strength_counts"],
        "graph_gap_query_recommended_action_counts": graph_gap_context_metrics[
            "graph_gap_query_recommended_action_counts"
        ],
        "graph_gap_query_priority_adjustment_counts": graph_gap_context_metrics[
            "graph_gap_query_priority_adjustment_counts"
        ],
        "primary_missing_fact_counts": fact_targeting_metrics["primary_missing_fact_counts"],
        "missing_fact_bundle_counts": fact_targeting_metrics["missing_fact_bundle_counts"],
        "satisfied_fact_bundle_counts": fact_targeting_metrics["satisfied_fact_bundle_counts"],
        "zero_result_entry_count": zero_result_entry_count,
        "last_adaptive_retry": last_adaptive_retry,
        "manual_review_entry_count": len(
            [
                entry
                for entry in entries
                if isinstance(entry, dict) and entry.get("support_kind") == "manual_review"
            ]
        ),
        "resolved_entry_count": len(
            [
                entry
                for entry in entries
                if isinstance(entry, dict)
                and (
                    entry.get("status") == "resolved_manual_review"
                    or bool(entry.get("resolution_status"))
                )
            ]
        ),
        "contradiction_related_entry_count": len(
            [
                entry
                for entry in entries
                if isinstance(entry, dict)
                and (
                    entry.get("follow_up_focus") == "contradiction_resolution"
                    or entry.get("validation_status") == "contradicted"
                )
            ]
        ),
        "latest_attempted_at": (
            entries[0].get("timestamp")
            if entries and isinstance(entries[0], dict)
            else None
        ),
    }
    if warning_metrics["search_warning_summary"]:
        summary.update(warning_metrics)
    return summary
def _summarize_follow_up_execution_claim(claim_execution: Dict[str, Any]) -> Dict[str, Any]:
    executed_tasks = claim_execution.get("tasks", []) if isinstance(claim_execution, dict) else []
    skipped_tasks = (
        claim_execution.get("skipped_tasks", []) if isinstance(claim_execution, dict) else []
    )
    all_tasks = [task for task in executed_tasks + skipped_tasks if isinstance(task, dict)]
    suppressed = [task for task in skipped_tasks if "suppressed" in task.get("skipped", {})]
    manual_review_skips = [
        task for task in skipped_tasks if "manual_review" in task.get("skipped", {})
    ]
    cooldown_skips = [
        task
        for task in skipped_tasks
        if any(
            value.get("reason") == "duplicate_within_cooldown"
            for value in task.get("skipped", {}).values()
            if isinstance(value, dict)
        )
    ]
    follow_up_focus_counts: Dict[str, int] = {}
    query_strategy_counts: Dict[str, int] = {}
    proof_decision_source_counts: Dict[str, int] = {}
    resolution_status_counts: Dict[str, int] = {}
    resolution_applied_counts: Dict[str, int] = {}
    temporal_rule_status_counts: Dict[str, int] = {}
    temporal_rule_blocking_reason_counts: Dict[str, int] = {}
    temporal_resolution_status_counts: Dict[str, int] = {}
    selected_authority_program_type_counts: Dict[str, int] = {}
    selected_authority_intent_counts: Dict[str, int] = {}
    selected_authority_jurisdiction_counts: Dict[str, int] = {}
    selected_authority_forum_counts: Dict[str, int] = {}
    selected_authority_family_counts: Dict[str, int] = {}
    selected_authority_defense_theme_counts: Dict[str, int] = {}
    selected_authority_time_window_counts: Dict[str, int] = {}
    selected_authority_graph_gap_bias_counts: Dict[str, int] = {}

    def _increment_count(counts: Dict[str, int], value: Any) -> None:
        normalized = str(value or "").strip()
        if normalized:
            counts[normalized] = counts.get(normalized, 0) + 1

    def _time_window_label(value: Any) -> str:
        if not isinstance(value, dict):
            return ""
        return ":".join(
            [
                part
                for part in [
                    str(value.get("time_window_type") or "").strip(),
                    str(value.get("profile_id") or "").strip(),
                    str(value.get("status") or "").strip(),
                ]
                if part
            ]
        )

    for task in all_tasks:
        focus = str(task.get("follow_up_focus") or "unknown")
        follow_up_focus_counts[focus] = follow_up_focus_counts.get(focus, 0) + 1
        strategy = str(task.get("query_strategy") or "unknown")
        query_strategy_counts[strategy] = query_strategy_counts.get(strategy, 0) + 1
        decision_source = str(task.get("proof_decision_source") or "unknown")
        proof_decision_source_counts[decision_source] = (
            proof_decision_source_counts.get(decision_source, 0) + 1
        )
        resolution_status = str(task.get("resolution_status") or "")
        if resolution_status:
            resolution_status_counts[resolution_status] = (
                resolution_status_counts.get(resolution_status, 0) + 1
            )
        resolution_applied = str(task.get("resolution_applied") or "")
        if resolution_applied:
            resolution_applied_counts[resolution_applied] = (
                resolution_applied_counts.get(resolution_applied, 0) + 1
            )
        temporal_rule_status = str(task.get("temporal_rule_status") or "")
        if temporal_rule_status:
            temporal_rule_status_counts[temporal_rule_status] = (
                temporal_rule_status_counts.get(temporal_rule_status, 0) + 1
            )
        for reason in (task.get("temporal_rule_blocking_reasons") or []):
            normalized_reason = str(reason or "").strip()
            if not normalized_reason:
                continue
            temporal_rule_blocking_reason_counts[normalized_reason] = (
                temporal_rule_blocking_reason_counts.get(normalized_reason, 0) + 1
            )
        if focus == "temporal_gap_closure" and resolution_status:
            temporal_resolution_status_counts[resolution_status] = (
                temporal_resolution_status_counts.get(resolution_status, 0) + 1
            )
        _increment_count(
            selected_authority_program_type_counts,
            task.get("selected_search_program_type"),
        )
        _increment_count(
            selected_authority_intent_counts,
            task.get("selected_search_program_intent") or task.get("authority_intent"),
        )
        _increment_count(
            selected_authority_jurisdiction_counts,
            task.get("selected_search_program_jurisdiction"),
        )
        _increment_count(
            selected_authority_forum_counts,
            task.get("selected_search_program_forum"),
        )
        selected_families = (
            task.get("selected_search_program_families")
            if isinstance(task.get("selected_search_program_families"), list)
            else []
        )
        for family in selected_families:
            _increment_count(selected_authority_family_counts, family)
        selected_themes = (
            task.get("selected_search_program_defense_themes")
            if isinstance(task.get("selected_search_program_defense_themes"), list)
            else []
        )
        for theme in selected_themes:
            _increment_count(selected_authority_defense_theme_counts, theme)
        selected_time_window = (
            task.get("selected_search_program_time_window")
            if isinstance(task.get("selected_search_program_time_window"), dict)
            else {}
        )
        _increment_count(
            selected_authority_time_window_counts,
            _time_window_label(selected_time_window),
        )
        _increment_count(
            selected_authority_graph_gap_bias_counts,
            task.get("selected_search_program_graph_gap_bias"),
        )
    graph_support_metrics = _aggregate_graph_support_metrics(executed_tasks + skipped_tasks)
    graph_gap_context_metrics = _aggregate_graph_gap_context_metrics(all_tasks)
    adaptive_retry_metrics = _aggregate_adaptive_retry_metrics(all_tasks)
    authority_search_program_metrics = _aggregate_authority_search_program_metrics(all_tasks)
    rule_candidate_metrics = _aggregate_rule_candidate_metrics(all_tasks)
    fact_targeting_metrics = _aggregate_fact_targeting_metrics(all_tasks)
    quality_routing_metrics = _aggregate_quality_routing_metrics(all_tasks)
    warning_metrics = _aggregate_search_warning_metrics(all_tasks)
    summary = {
        "executed_task_count": len(executed_tasks),
        "skipped_task_count": len(skipped_tasks),
        "suppressed_task_count": len(suppressed),
        "manual_review_task_count": len(manual_review_skips),
        "cooldown_skipped_task_count": len(cooldown_skips),
        "contradiction_task_count": len(
            [task for task in all_tasks if task.get("follow_up_focus") == "contradiction_resolution"]
        ),
        "reasoning_gap_task_count": len(
            [task for task in all_tasks if task.get("follow_up_focus") == "reasoning_gap_closure"]
        ),
        "temporal_gap_task_count": len(
            [task for task in all_tasks if task.get("follow_up_focus") == "temporal_gap_closure"]
        ),
        "fact_gap_task_count": len(
            [task for task in all_tasks if task.get("follow_up_focus") == "fact_gap_closure"]
        ),
        "adverse_authority_task_count": len(
            [
                task
                for task in all_tasks
                if task.get("follow_up_focus") == "adverse_authority_review"
            ]
        ),
        "confirm_good_law_task_count": len(
            [task for task in all_tasks if task.get("follow_up_focus") == "confirm_good_law"]
        ),
        "find_better_authority_task_count": len(
            [task for task in all_tasks if task.get("follow_up_focus") == "find_better_authority"]
        ),
        "parse_quality_task_count": len(
            [task for task in all_tasks if task.get("follow_up_focus") == "parse_quality_improvement"]
        ),
        "ontology_quality_gap_task_count": len(
            [
                task
                for task in all_tasks
                if task.get("follow_up_focus") == "ontology_quality_gap_closure"
            ]
        ),
        "quality_gap_targeted_task_count": len(
            [task for task in all_tasks if task.get("query_strategy") == "quality_gap_targeted"]
        ),
        "ontology_quality_gap_targeted_task_count": len(
            [
                task
                for task in all_tasks
                if task.get("query_strategy") == "ontology_quality_gap_targeted"
            ]
        ),
        "temporal_gap_targeted_task_count": len(
            [task for task in all_tasks if task.get("query_strategy") == "temporal_gap_targeted"]
        ),
        "semantic_cluster_count": graph_support_metrics["semantic_cluster_count"],
        "semantic_duplicate_count": graph_support_metrics["semantic_duplicate_count"],
        "support_by_kind": graph_support_metrics["support_by_kind"],
        "support_by_source": graph_support_metrics["support_by_source"],
        "source_family_counts": graph_support_metrics["source_family_counts"],
        "record_scope_counts": graph_support_metrics["record_scope_counts"],
        "artifact_family_counts": graph_support_metrics["artifact_family_counts"],
        "corpus_family_counts": graph_support_metrics["corpus_family_counts"],
        "content_origin_counts": graph_support_metrics["content_origin_counts"],
        "graph_gap_context_task_count": graph_gap_context_metrics["graph_gap_context_task_count"],
        "graph_gap_has_support_task_count": graph_gap_context_metrics["graph_gap_has_support_task_count"],
        "graph_gap_empty_task_count": graph_gap_context_metrics["graph_gap_empty_task_count"],
        "graph_gap_total_fact_count": graph_gap_context_metrics["graph_gap_total_fact_count"],
        "graph_gap_unique_fact_count": graph_gap_context_metrics["graph_gap_unique_fact_count"],
        "graph_gap_duplicate_fact_count": graph_gap_context_metrics["graph_gap_duplicate_fact_count"],
        "graph_gap_semantic_cluster_count": graph_gap_context_metrics["graph_gap_semantic_cluster_count"],
        "graph_gap_semantic_duplicate_count": graph_gap_context_metrics["graph_gap_semantic_duplicate_count"],
        "graph_gap_strength_counts": graph_gap_context_metrics["graph_gap_strength_counts"],
        "graph_gap_recommended_action_counts": graph_gap_context_metrics["graph_gap_recommended_action_counts"],
        "graph_gap_priority_adjustment_counts": graph_gap_context_metrics["graph_gap_priority_adjustment_counts"],
        "graph_gap_source_family_counts": graph_gap_context_metrics["graph_gap_source_family_counts"],
        "graph_gap_artifact_family_counts": graph_gap_context_metrics["graph_gap_artifact_family_counts"],
        "graph_gap_corpus_family_counts": graph_gap_context_metrics["graph_gap_corpus_family_counts"],
        "graph_gap_content_origin_counts": graph_gap_context_metrics["graph_gap_content_origin_counts"],
        "graph_gap_fact_registry_summary": graph_gap_context_metrics["graph_gap_fact_registry_summary"],
        "graph_gap_query_task_count": graph_gap_context_metrics["graph_gap_query_task_count"],
        "graph_gap_query_has_support_task_count": graph_gap_context_metrics[
            "graph_gap_query_has_support_task_count"
        ],
        "graph_gap_query_empty_task_count": graph_gap_context_metrics["graph_gap_query_empty_task_count"],
        "graph_gap_query_result_count": graph_gap_context_metrics["graph_gap_query_result_count"],
        "graph_gap_query_missing_support_kind_counts": graph_gap_context_metrics[
            "graph_gap_query_missing_support_kind_counts"
        ],
        "graph_gap_query_strength_counts": graph_gap_context_metrics["graph_gap_query_strength_counts"],
        "graph_gap_query_recommended_action_counts": graph_gap_context_metrics[
            "graph_gap_query_recommended_action_counts"
        ],
        "graph_gap_query_priority_adjustment_counts": graph_gap_context_metrics[
            "graph_gap_query_priority_adjustment_counts"
        ],
        "primary_missing_fact_counts": fact_targeting_metrics["primary_missing_fact_counts"],
        "missing_fact_bundle_counts": fact_targeting_metrics["missing_fact_bundle_counts"],
        "satisfied_fact_bundle_counts": fact_targeting_metrics["satisfied_fact_bundle_counts"],
        "quality_signal_counts": quality_routing_metrics["quality_signal_counts"],
        "primary_quality_signal_counts": quality_routing_metrics["primary_quality_signal_counts"],
        "quality_follow_up_action_counts": quality_routing_metrics["quality_follow_up_action_counts"],
        "follow_up_focus_counts": follow_up_focus_counts,
        "query_strategy_counts": query_strategy_counts,
        "proof_decision_source_counts": proof_decision_source_counts,
        "resolution_status_counts": resolution_status_counts,
        "temporal_resolution_status_counts": temporal_resolution_status_counts,
        "selected_authority_program_type_counts": selected_authority_program_type_counts,
        "selected_authority_intent_counts": selected_authority_intent_counts,
        "selected_authority_jurisdiction_counts": selected_authority_jurisdiction_counts,
        "selected_authority_forum_counts": selected_authority_forum_counts,
        "selected_authority_family_counts": selected_authority_family_counts,
        "selected_authority_defense_theme_counts": selected_authority_defense_theme_counts,
        "selected_authority_time_window_counts": selected_authority_time_window_counts,
        "selected_authority_graph_gap_bias_counts": selected_authority_graph_gap_bias_counts,
        "resolution_applied_counts": resolution_applied_counts,
        "temporal_rule_status_counts": temporal_rule_status_counts,
        "temporal_rule_blocking_reason_counts": temporal_rule_blocking_reason_counts,
        "adaptive_retry_task_count": adaptive_retry_metrics["adaptive_retry_task_count"],
        "priority_penalized_task_count": adaptive_retry_metrics[
            "priority_penalized_task_count"
        ],
        "adaptive_query_strategy_counts": adaptive_retry_metrics[
            "adaptive_query_strategy_counts"
        ],
        "adaptive_retry_reason_counts": adaptive_retry_metrics[
            "adaptive_retry_reason_counts"
        ],
        "last_adaptive_retry": adaptive_retry_metrics["last_adaptive_retry"],
        "authority_search_program_task_count": authority_search_program_metrics[
            "authority_search_program_task_count"
        ],
        "authority_search_program_count": authority_search_program_metrics[
            "authority_search_program_count"
        ],
        "authority_search_program_type_counts": authority_search_program_metrics[
            "authority_search_program_type_counts"
        ],
        "authority_search_intent_counts": authority_search_program_metrics[
            "authority_search_intent_counts"
        ],
        "authority_jurisdiction_counts": authority_search_program_metrics[
            "authority_jurisdiction_counts"
        ],
        "authority_forum_counts": authority_search_program_metrics[
            "authority_forum_counts"
        ],
        "authority_family_counts": authority_search_program_metrics[
            "authority_family_counts"
        ],
        "authority_defense_theme_counts": authority_search_program_metrics[
            "authority_defense_theme_counts"
        ],
        "authority_time_window_counts": authority_search_program_metrics[
            "authority_time_window_counts"
        ],
        "authority_graph_gap_bias_counts": authority_search_program_metrics[
            "authority_graph_gap_bias_counts"
        ],
        "primary_authority_program_type_counts": authority_search_program_metrics[
            "primary_authority_program_type_counts"
        ],
        "primary_authority_intent_counts": authority_search_program_metrics[
            "primary_authority_intent_counts"
        ],
        "primary_authority_program_bias_counts": authority_search_program_metrics[
            "primary_authority_program_bias_counts"
        ],
        "primary_authority_program_rule_bias_counts": authority_search_program_metrics[
            "primary_authority_program_rule_bias_counts"
        ],
        "primary_authority_graph_gap_bias_counts": authority_search_program_metrics[
            "primary_authority_graph_gap_bias_counts"
        ],
        "rule_candidate_backed_task_count": rule_candidate_metrics[
            "rule_candidate_backed_task_count"
        ],
        "total_rule_candidate_count": rule_candidate_metrics[
            "total_rule_candidate_count"
        ],
        "matched_claim_element_rule_count": rule_candidate_metrics[
            "matched_claim_element_rule_count"
        ],
        "rule_candidate_type_counts": rule_candidate_metrics[
            "rule_candidate_type_counts"
        ],
    }
    if warning_metrics["search_warning_summary"]:
        summary.update(warning_metrics)
    return summary
