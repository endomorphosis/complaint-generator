# Objective Bundle: refactor/g10/g10-s4

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [ ] Task checkbox-210: REF-210 Generate bounded goals, subgoals, and tasks from uncovered or inconclusive evidence

## REF-210 Generate bounded goals, subgoals, and tasks from uncovered or inconclusive evidence

- Status: todo
- Completion: manual
- Priority: P1
- Track: G10
- Depends on: REF-205, REF-207, REF-209
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_coverage.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_generation.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_generation.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py -q
- Bundle: refactor/g10/g10-s4
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S4
- Missing evidence: Uncovered acceptance criteria and inconclusive analysis should become reviewable, dependency-linked work instead of silently draining the board.
- AST symbols: DEFAULT_EMBEDDING_DIMENSIONS, DEFAULT_EMBEDDING_MIN_SCORE, DEFAULT_BUNDLE_CLUSTER_MIN_SCORE, DEFAULT_OBJECTIVE_TASK_SUMMARY_PREFIX, parse_python_ast_quietly, DEFAULT_DISCOVERY_OUTPUT_PATH, DEFAULT_SURPLUS_FINDINGS_PER_GOAL, DEFAULT_SURPLUS_MIN_TERMS_PER_TODO, DEFAULT_SCAN_OVERSAMPLE_MULTIPLIER, DEFAULT_TASK_PREFIX, DEFAULT_AST_DATASET_MAX_CHARS, AST_DATASET_RECORD_SCHEMA_VERSION, LAUNCH_PLAYWRIGHT_VALIDATION_COMMAND, LAUNCH_PLAYWRIGHT_VALIDATION_MARKERS, LAUNCH_PLAYWRIGHT_VALIDATION_GATE_EVIDENCE, SCAN_SUFFIXES, SKIP_DIRS, ObjectiveGoal, ObjectiveFinding, ObjectiveTaskRecord, ObjectiveHeapRecord, DEPENDENCY_EDGE_KINDS, SUCCESSFUL_MERGE_RECEIPT_STATUSES, DependencyEdge, TaskDependencyNode, DependencyRepairEvidence, TaskScheduleRecord, TaskDependencyGraph, TaskDependencyDAG, TaskPlanningGraph
- Merge key: refactor/g10/g10-s4
- Candidate kind: seed
- Todo vector key: ref-210-generateboundedgoalssubgoalsandtasksfromuncovere
- Acceptance: Deterministic rules and llm_router proposals can create bounded child goals, subgoals, and tasks from uncovered criteria, unsupported surfaces, or contradiction receipts.; Generated work records parent objective terms, expected evidence delta, dependencies, predicted files and symbols, validation, confidence, cost, and novelty.; Canonical identity and semantic deduplication prevent equivalent goals or tasks from being regenerated across cycles.; Depth, breadth, token, retry, and open-work limits keep autonomous refinement finite and scheduler-aware.

- [ ] Task checkbox-211: REF-211 Migrate existing goals and expose trustworthy completion diagnostics

## REF-211 Migrate existing goals and expose trustworthy completion diagnostics

- Status: todo
- Completion: manual
- Priority: P0
- Track: G10
- Depends on: REF-202, REF-206, REF-208, REF-209, REF-210
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_tracker.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scheduler_metrics.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/implementation_supervisor_runner.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_implementation_supervisor_runner.py -q
- Bundle: refactor/g10/g10-s4
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S4
- Missing evidence: Existing completed goals need a safe migration path and operators need to see confidence and missing proof without reading raw event logs.
- AST symbols: DEFAULT_ULTIMATE_GOAL, DEFAULT_ROOT_EVIDENCE, DEFAULT_GOAL_PREFIX, DEFAULT_TRACKING_DOCUMENT_TITLE, DEFAULT_ROOT_GOAL_TITLE, OPEN_TASK_STATUSES_FOR_GOAL_COMPLETION, TASK_GOAL_METADATA_KEYS, ObjectiveTrackingResult, ObjectiveCompletionResult, RepositoryComponent, fibonacci_number, fibonacci_priority, infer_goal_prefix, next_goal_id, render_goal_block, rewrite_goal_fields, completion_evidence_summary, open_goal_ids_from_todo_board, open_goal_ids_from_todo_boards, run_goal_validation, reconcile_objective_goal_completion, ensure_objective_tracking_document, COMPONENT_SCAN_SKIP_DIRS, COMPONENT_MANIFEST_NAMES, INTERFACE_DESCRIPTOR_SUFFIXES, _unique_paths, discover_gitmodule_paths, discover_gitlink_paths, discover_submodule_paths, _component_relative_path
- Merge key: refactor/g10/g10-s4
- Candidate kind: seed
- Todo vector key: ref-211-migrateexistinggoalsandexposetrustworthycompleti
- Acceptance: Legacy completed goals migrate idempotently to provisional or verified state based on available evidence, never by optimistic default.; Status and manifest projections show lifecycle state, confidence, uncovered criteria, stale evidence, analyzer health, exhaustion quorum, and reopen reasons.; Schema versioning and compatibility readers preserve existing boards, events, and automation during rollout.; The migration can be previewed and resumed safely after interruption.

- [ ] Task checkbox-212: REF-212 Add end-to-end regression tests for truthful goal completion and autonomous refill

## REF-212 Add end-to-end regression tests for truthful goal completion and autonomous refill

- Status: todo
- Completion: manual
- Priority: P0
- Track: G10
- Depends on: REF-203, REF-204, REF-205, REF-208, REF-209, REF-210, REF-211
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_lifecycle_e2e.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_lifecycle_e2e.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py -q
- Bundle: refactor/g10/g10-s4
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S4
- Missing evidence: The completion and refill contract needs system-level regression coverage across restart, concurrency, stale evidence, analyzer failure, and contradiction scenarios.
- AST symbols: _git, _seed_repo, _git_dir, test_commit_generated_dirty_outputs_commits_nested_repo_and_parent_gitlink, test_commit_generated_dirty_outputs_repairs_recursive_clean_gitlinks, test_commit_generated_dirty_outputs_repairs_stale_nested_index_lock, test_commit_generated_dirty_outputs_defers_during_merge, test_namespace_recorder_factories_bind_standard_paths, test_configured_backlog_recorder_bundle_delegates_to_runtime_factories, _write_todo, test_backlog_refinery_appends_missing_task_blocks_in_order, test_backlog_refinery_codebase_scan_refills_low_backlog, test_codebase_scan_writes_file_local_ast_bundle, test_codebase_scan_synchronizes_fingerprints_across_strategy_files, test_codebase_scan_retires_later_duplicate_vector_tasks, test_codebase_scan_reserves_ids_from_discovery_artifacts, test_backlog_refinery_annotation_scan_ignores_literal_status_strings, test_backlog_refinery_codebase_scan_skips_vanished_git_roots, test_backlog_refinery_repairs_invalid_strategy_file, test_backlog_refinery_iter_jsonl_quarantines_malformed_events, test_backlog_refinery_dependency_guardrail_adds_ready_repair_task, test_backlog_refinery_dependency_guardrail_detects_dependency_cycle, test_backlog_refinery_dependency_guardrail_detects_duplicate_task_ids, test_backlog_refinery_releases_completed_guardrail_block, test_backlog_refinery_releases_completed_and_duplicate_stale_strategy_blocks, test_backlog_refinery_releases_historical_completed_retry_repairs, test_backlog_refinery_releases_orphaned_block_without_repair_path, test_backlog_refinery_releases_recursive_retry_repair_block, test_backlog_refinery_retires_ready_recursive_retry_repair_task, test_backlog_refinery_releases_stale_dependency_guardrail_after_metadata_repaired
- Merge key: refactor/g10/g10-s4
- Candidate kind: seed
- Todo vector key: ref-212-addend-to-endregressiontestsfortruthfulgoalcompl
- Acceptance: Tests distinguish threshold skip, cooldown, duplicate-only, healthy exhaustion, parser failure, timeout, partial coverage, and successful generation.; Scenarios prove that stale fingerprints cannot certify completion and that later relevant findings reopen goals and refill the board.; Concurrent serial and bundle supervisors emit one canonical receipt and do not duplicate generated goals or tasks.; Restart and migration preserve evidence lineage, quorum state, dependencies, and truthful operator projections.
