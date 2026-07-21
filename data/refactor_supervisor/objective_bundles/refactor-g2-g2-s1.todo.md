# Objective Bundle: refactor/g2/g2-s1

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [ ] Task checkbox-5: REF-005 Split mediator/mediator.py by workflow service while preserving public API compatibility

## REF-005 Split mediator/mediator.py by workflow service while preserving public API compatibility

- Status: completed
- Completion: manual
- Priority: P0
- Track: G2
- Depends on: 
- Outputs: mediator/mediator.py, mediator/__init__.py
- Validation: python -m pytest tests/test_mediator.py tests/test_mediator_three_phase.py -q
- Bundle: refactor/g2/g2-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G2.S1
- Missing evidence: The mediator is the largest runtime file and carries high regression risk.
- AST symbols: ALIGNMENT_TASK_UPDATE_HISTORY_LIMIT, FOLLOW_UP_REVIEWABLE_ESCALATION_STATUSES, Mediator, __init__, reset, resume, get_state, set_state, response, select_intake_question_candidates, _phase_focus_rank, _phase_focus_bonus, _is_document_question_candidate, _build_exhibit_ready_document_question, _apply_exhibit_ready_intake_questioning, _is_exact_dates_closure_match, _is_staff_names_titles_closure_match, _is_hearing_request_timing_closure_match, _is_response_dates_closure_match, _is_causation_sequence_match, _build_intake_claim_pressure_map, _build_intake_selector_legal_graph, _build_intake_matching_pressure_map, _build_intake_workflow_action_queue, _summarize_intake_workflow_action_queue, _build_evidence_workflow_action_queue, _get_document_provenance_summary, _get_document_grounding_lane_outcome_summary, _get_document_grounding_recovery_action, _get_document_grounding_improvement_next_action
- Merge key: refactor/g2/g2-s1
- Candidate kind: seed
- Todo vector key: ref-005-splitmediator-mediator-pybyworkflowservicewhilep
- Acceptance: One cohesive service is extracted.; Existing imports continue to resolve.

- [ ] Task checkbox-6: REF-006 Move claim support orchestration helpers into focused private modules

## REF-006 Move claim support orchestration helpers into focused private modules

- Status: todo
- Completion: manual
- Priority: P0
- Track: G2
- Depends on: 
- Outputs: mediator/claim_support_hooks.py
- Validation: python -m pytest tests/test_claim_support_hooks.py tests/test_claim_support_review_dashboard_flow.py -q
- Bundle: refactor/g2/g2-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G2.S1
- Missing evidence: Claim support hooks are large enough to hide unrelated concerns.
- AST symbols: ClaimSupportHook, DUCKDB_AVAILABLE, _CONTENT_ORIGIN_ARTIFACT_FAMILY, _ARTIFACT_FAMILY_CORPUS_FAMILY, __init__, _get_default_db_path, _with_intake_summary_handoff, _resolve_artifact_identity, _prepare_duckdb_path, _check_duckdb_availability, _initialize_schema, _make_element_id, _make_testimony_id, _summarize_testimony_records, _testimony_quality_summary, _build_testimony_fact_text, _build_testimony_support_label, _build_testimony_support_link, _get_testimony_support_links, _get_enriched_claim_support_links, _tokenize_text, _extract_match_text, _normalize_graph_summary, _build_graph_trace, _summarize_graph_traces, _summarize_authority_treatment_signals, _summarize_authority_rule_candidates, _recommended_support_gap_action, _build_support_trace, _extract_record_parse_summary
- Merge key: refactor/g2/g2-s1
- Candidate kind: seed
- Todo vector key: ref-006-moveclaimsupportorchestrationhelpersintofocusedp
- Acceptance: At least one cohesive helper group moves behind a stable import.; No payload contract changes without tests.

## REF-007 Resolve dirty main checkout blocking 1 worktree merges

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Fingerprint: a92a0e5a0feb048b0ef041cb44d09c0cc1976425
- Dedupe key: reconciliation_guardrail:main_checkout_dirty
- Depends on:
- Outputs: data/refactor_supervisor/bundle_lanes/refactor-g2-g2-s1/discovery, data/refactor_supervisor/objective_bundles/refactor-g2-g2-s1.todo.md
- Validation: test -f /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g2-g2-s1/discovery/2026-07-21-ref-007-reconciliation-a92a0e5a0feb.md
- Acceptance: Reconciliation guardrail filed this because 1 branch or worktree cleanup candidates are blocked by main_checkout_dirty. Use evidence and the machine-readable reconciliation plan in /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g2-g2-s1/discovery/2026-07-21-ref-007-reconciliation-a92a0e5a0feb.md, reconcile the dirty checkout or dirty worktree group deliberately, then rerun the supervisor cleanup/reconciliation pass and confirm that the blocked candidate count decreases.
- Reconciliation result: Main checkout dirt was preserved in commit `f20703f1bb2a732fa78daf8c031fb315232baa1e`, the lane reconciliation pass reran at `2026-07-21T20:06:01Z`, and the `main_checkout_dirty` blocker count for this guardrail decreased from `1` to `0`; remaining merge candidates are preflight conflicts tracked separately.

## REF-008 Resolve 2 preflight-conflicting backlogged worktree merges

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Fingerprint: 4538192cbd791ab39b9ce5d1ff68640cbefb8a81
- Dedupe key: reconciliation_guardrail:preflight_merge_conflict
- Depends on:
- Outputs: data/refactor_supervisor/bundle_lanes/refactor-g2-g2-s1/discovery, data/refactor_supervisor/objective_bundles/refactor-g2-g2-s1.todo.md
- Validation: test -f /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g2-g2-s1/discovery/2026-07-21-ref-008-reconciliation-4538192cbd79.md
- Acceptance: Reconciliation guardrail filed this because 2 branch or worktree cleanup candidates are blocked by preflight_merge_conflict. Use evidence and the machine-readable reconciliation plan in /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g2-g2-s1/discovery/2026-07-21-ref-008-reconciliation-4538192cbd79.md, reconcile the dirty checkout or dirty worktree group deliberately, then rerun the supervisor cleanup/reconciliation pass and confirm that the blocked candidate count decreases.
- Reconciliation result: REF-005's sampled branch was already sanitizer-repaired and merged into `main` by merge commit `ae83e80`, then cleaned up by the lane pass at `2026-07-21T20:28:18Z`. REF-006 branch `implementation/ref-006-attempt-1-1784663578` now has sanitizer commit `0305608`, preserving its validated claim-support extraction while aligning stale non-output `applications/review_api.py` and `scripts/refactor_agent_supervisor.py` drift with the target checkout. REF-006 validation passed (`45 passed`), `git merge-tree --write-tree main implementation/ref-006-attempt-1-1784663578` now returns `0`, and the scoped reconciliation-only dry-run at `2026-07-21T20:35:07Z` reported `preflight_blocked_count` decreased from this guardrail's `2` to `0`.

## REF-009 Resolve merge retry-budget failure for REF-005

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Depends on: 
- Outputs: mediator/mediator.py, mediator/__init__.py, data/refactor_supervisor/bundle_lanes/refactor-g2-g2-s1/discovery
- Validation: test -f /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g2-g2-s1/discovery/2026-07-21-ref-009-ref-005-merge-retry-budget.md
- Acceptance: Merge retry-budget guardrail filed this from repeated merge failures in REF-005. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g2-g2-s1/discovery/2026-07-21-ref-009-ref-005-merge-retry-budget.md to fix the merge blocker, verify the intended implementation changes are committed in their owning repository or submodule, run `ipfs-accelerate-agent-merge-resolver --events-path ... --apply` when the conflict is semantic, then mark this repair task completed so the supervisor can release REF-005 from strategy blocked_tasks.
- Repair result: REF-005 branch `implementation/ref-005-attempt-1-1784663197` now has sanitizer commits `a1e01a3` and `6531aad`; its final diff from baseline is mediator-only, the script add/add conflict no longer appears in `git merge-tree`, and `REF-005` was removed from the lane strategy `blocked_tasks`.

## REF-010 Resolve merge retry-budget failure for REF-006

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Depends on:
- Outputs: mediator/claim_support_hooks.py, data/refactor_supervisor/bundle_lanes/refactor-g2-g2-s1/discovery
- Validation: test -f /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g2-g2-s1/discovery/2026-07-21-ref-010-ref-006-merge-retry-budget.md
- Acceptance: Merge retry-budget guardrail filed this from repeated merge failures in REF-006. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g2-g2-s1/discovery/2026-07-21-ref-010-ref-006-merge-retry-budget.md to fix the merge blocker, verify the intended implementation changes are committed in their owning repository or submodule, run `ipfs-accelerate-agent-merge-resolver --events-path ... --apply` when the conflict is semantic, then mark this repair task completed so the supervisor can release REF-006 from strategy blocked_tasks.
- Repair result: REF-006 branch `implementation/ref-006-attempt-1-1784663578` contains implementation commit `7009a4a` and sanitizer commit `0305608`; this repair branch carries the sanitized claim-support extraction, `git merge-tree` succeeds for both REF-006 and this branch, the merge resolver was run and reported no configured apply command, validation passed (`45 passed`), and `REF-006` was removed from the live lane strategy `blocked_tasks`.
