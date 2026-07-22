# Objective Bundle: refactor/g10/g10-s3

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-206: REF-206 Define an evidence-backed goal lifecycle and completion state machine

## REF-206 Define an evidence-backed goal lifecycle and completion state machine

- Status: completed
- Completion: manual
- Priority: P0
- Track: G10
- Depends on: REF-200
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_tracker.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q
- Bundle: refactor/g10/g10-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S3
- Missing evidence: The objective graph currently treats completed task statuses as sufficient even when completion evidence and validation receipts are absent.
- AST symbols: DEFAULT_ULTIMATE_GOAL, DEFAULT_ROOT_EVIDENCE, DEFAULT_GOAL_PREFIX, DEFAULT_TRACKING_DOCUMENT_TITLE, DEFAULT_ROOT_GOAL_TITLE, OPEN_TASK_STATUSES_FOR_GOAL_COMPLETION, TASK_GOAL_METADATA_KEYS, ObjectiveTrackingResult, ObjectiveCompletionResult, RepositoryComponent, fibonacci_number, fibonacci_priority, infer_goal_prefix, next_goal_id, render_goal_block, rewrite_goal_fields, completion_evidence_summary, open_goal_ids_from_todo_board, open_goal_ids_from_todo_boards, run_goal_validation, reconcile_objective_goal_completion, ensure_objective_tracking_document, COMPONENT_SCAN_SKIP_DIRS, COMPONENT_MANIFEST_NAMES, INTERFACE_DESCRIPTOR_SUFFIXES, _unique_paths, discover_gitmodule_paths, discover_gitlink_paths, discover_submodule_paths, _component_relative_path
- Merge key: refactor/g10/g10-s3
- Candidate kind: seed
- Todo vector key: ref-206-defineanevidence-backedgoallifecycleandcompletio
- Acceptance: Goals distinguish active, provisionally complete, verified complete, analysis inconclusive, blocked, and reopened states with legal transitions.; Completion evidence names acceptance criterion, producing task or scan, validation receipt, repository tree, freshness, and provenance CID.; Task completion alone can make a goal provisional but cannot make it verified.; Missing, stale, failed, or contradictory evidence fails closed with an actionable reason.

- [ ] Task checkbox-207: REF-207 Build goal-to-task, code, AST, acceptance, and validation coverage maps

## REF-207 Build goal-to-task, code, AST, acceptance, and validation coverage maps

- Status: todo
- Completion: manual
- Priority: P0
- Track: G10
- Depends on: REF-201, REF-206
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_coverage.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_vector_index.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/conflict_graph.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_coverage.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_coverage.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q
- Bundle: refactor/g10/g10-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S3
- Missing evidence: Goal completion cannot be assessed when acceptance criteria are not mapped to implementation surfaces and proof-producing validations.
- AST symbols: DEFAULT_EMBEDDING_DIMENSIONS, DEFAULT_EMBEDDING_MIN_SCORE, DEFAULT_BUNDLE_CLUSTER_MIN_SCORE, DEFAULT_OBJECTIVE_TASK_SUMMARY_PREFIX, parse_python_ast_quietly, DEFAULT_DISCOVERY_OUTPUT_PATH, DEFAULT_SURPLUS_FINDINGS_PER_GOAL, DEFAULT_SURPLUS_MIN_TERMS_PER_TODO, DEFAULT_SCAN_OVERSAMPLE_MULTIPLIER, DEFAULT_TASK_PREFIX, DEFAULT_AST_DATASET_MAX_CHARS, AST_DATASET_RECORD_SCHEMA_VERSION, LAUNCH_PLAYWRIGHT_VALIDATION_COMMAND, LAUNCH_PLAYWRIGHT_VALIDATION_MARKERS, LAUNCH_PLAYWRIGHT_VALIDATION_GATE_EVIDENCE, SCAN_SUFFIXES, SKIP_DIRS, ObjectiveGoal, ObjectiveFinding, ObjectiveTaskRecord, ObjectiveHeapRecord, DEPENDENCY_EDGE_KINDS, SUCCESSFUL_MERGE_RECEIPT_STATUSES, DependencyEdge, TaskDependencyNode, DependencyRepairEvidence, TaskScheduleRecord, TaskDependencyGraph, TaskDependencyDAG, TaskPlanningGraph
- Merge key: refactor/g10/g10-s3
- Candidate kind: seed
- Todo vector key: ref-207-buildgoal-to-taskcodeastacceptanceandvalidationc
- Acceptance: Every acceptance criterion maps to tasks, predicted and changed files, AST symbols or interfaces, validation commands, and resulting receipts with provenance.; The graph reports uncovered, weakly inferred, stale, contradicted, and verified surfaces separately.; Dynamic codebase findings attach to the most relevant registered goals while preserving a clearly labeled unmapped bucket.; Coverage calculations are deterministic and explain the evidence behind each edge.

- [ ] Task checkbox-208: REF-208 Enforce a completion gate using validation, coverage, health, freshness, and exhaustion proof

## REF-208 Enforce a completion gate using validation, coverage, health, freshness, and exhaustion proof

- Status: todo
- Completion: manual
- Priority: P0
- Track: G10
- Depends on: REF-204, REF-207
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_coverage.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/audit_scanner.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_task_janitor.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_task_janitor.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_task_janitor.py -q
- Bundle: refactor/g10/g10-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S3
- Missing evidence: Goal reconciliation must require proof of the stated objective rather than infer success from a drained or deduplicated task list.
- AST symbols: logger, _plan_value_dict, objective_record_plan_context, _evaluated_branch_dict, plan_objective_records, persist_objective_plan_evaluations, default_repo_root, default_objective_path, default_todo_path, default_state_root, split_csv, parse_goal_completion_todo_boards, discovery_fingerprints, build_arg_parser, run_objective_daemon, main, to_dict, finding, validation, validation_commands, predicted_files, predicted_symbols, branch, branch_payload, branch_id, scores, rationales, wrapped_score, wrapped_rationale, payload
- Merge key: refactor/g10/g10-s3
- Candidate kind: seed
- Todo vector key: ref-208-enforceacompletiongateusingvalidationcoveragehea
- Acceptance: Verified completion requires all mandatory acceptance criteria covered, required validations successful, evidence fresh, analyzer healthy, and configured exhaustion quorum satisfied.; Partial, skipped, failed, timed-out, duplicate-only, or unsupported analysis cannot satisfy the gate.; The gate emits machine-readable pass and fail reasons plus the exact evidence set it evaluated.; Parent goals aggregate child proof without hiding an inconclusive or reopened descendant.

- [ ] Task checkbox-209: REF-209 Detect contradictory evidence and automatically reopen affected goals

## REF-209 Detect contradictory evidence and automatically reopen affected goals

- Status: todo
- Completion: manual
- Priority: P0
- Track: G10
- Depends on: REF-208
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_coverage.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_task_janitor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_task_janitor.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_goal_completion.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_task_janitor.py -q
- Bundle: refactor/g10/g10-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S3
- Missing evidence: A completed goal currently remains completed even when a later codebase scan creates directly relevant work or validation regresses.
- AST symbols: ACTIVE_GOAL_STATUSES, OPEN_TASK_STATUSES, JANITOR_RECEIPT_SCHEMA, LAUNCH_PLAYWRIGHT_VALIDATION_GATE_EVIDENCE, LAUNCH_PLAYWRIGHT_VALIDATION_COMMAND, LAUNCH_PLAYWRIGHT_VALIDATION_MARKERS, DEFAULT_MISSION_TERMS, GOAL_METADATA_KEYS, CODEBASE_SCAN_BACKLOG_TITLE_PREFIXES, CODEBASE_SCAN_BACKLOG_MARKERS, WORKTREE_CLEANUP_BACKLOG_MARKERS, GUARDRAIL_REPAIR_MARKERS, DYNAMIC_GOAL_REGISTRATION_VALUES, COMPLETED_TASK_STATUSES, JANITOR_BLOCKED_REASON_MARKER, ObjectiveTaskJanitorReceipt, _unique, _split_terms, _task_goal_ids, _task_haystack, _goal_haystack, _goal_requires_launch_playwright_gate, _matches_any_term, _is_generated_objective_task, _is_guardrail_repair_task, _is_codebase_scan_backlog_task, _is_mission_critical_codebase_scan_task, _is_worktree_cleanup_backlog_task, _critical_goal_ids, _janitor_owned_task_ids
- Merge key: refactor/g10/g10-s3
- Candidate kind: seed
- Todo vector key: ref-209-detectcontradictoryevidenceandautomaticallyreope
- Acceptance: Novel mapped findings, failed required validations, changed evidence surfaces, and invalidated audit receipts reopen verified or provisional goals deterministically.; Reopening records the contradiction, impacted criteria, invalidated evidence, source receipt, and newly scheduled work.; Unrelated findings do not churn completed goals, and repeated identical contradictions are idempotent.; Parent and dependent goal states are recalculated without erasing historical completion receipts.
