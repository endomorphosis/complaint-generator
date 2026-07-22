# Objective Bundle: refactor/g8/g8-s2

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [ ] Task checkbox-25: REF-025 Add a taskboard inspection command that prints queued refactor tasks compactly

## REF-025 Add a taskboard inspection command that prints queued refactor tasks compactly

- Status: completed
- Completion: manual
- Priority: P1
- Track: G8
- Depends on: 
- Outputs: scripts/refactor_agent_supervisor.py
- Validation: python scripts/refactor_agent_supervisor.py status
- Bundle: refactor/g8/g8-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G8.S2
- Missing evidence: Agents need a simple way to see the next work without opening DuckDB manually.
- AST symbols: PROJECT_ROOT, ACCELERATE_REPO, STATE_ROOT, QUEUE_PATH, GOALS_PATH, OBJECTIVE_PATH, TODO_PATH, BUNDLE_DIR, DATASET_DIR, DISCOVERY_DIR, GRAPH_PATH, STRATEGY_PATH, EVENTS_PATH, REFILL_STATE_PATH, SUPERVISOR_STATE_DIR, WORKTREE_ROOT, BUNDLE_LANE_ROOT, BUNDLE_LANE_MANIFEST, BUNDLE_COORDINATION_PATH, STATUS_PATH, PID_PATH, LOG_PATH, TASKBOARD_DOC_PATH, TASK_PREFIX, TASK_HEADER_PREFIX, TASK_TYPES, MODEL_NAME, _ensure_accelerate_import_path, _task_queue_class, _upstream_objective_runner
- Merge key: refactor/g8/g8-s2
- Candidate kind: seed
- Todo vector key: ref-025-addataskboardinspectioncommandthatprintsqueuedre
- Acceptance: Status output or a new command lists next tasks by priority.; Output is stable enough for automation.

- [ ] Task checkbox-26: REF-026 Create tests for refactor supervisor seed idempotence and task payload schema

## REF-026 Create tests for refactor supervisor seed idempotence and task payload schema

- Status: todo
- Completion: manual
- Priority: P1
- Track: G8
- Depends on: 
- Outputs: tests/test_refactor_agent_supervisor.py, scripts/refactor_agent_supervisor.py
- Validation: python -m pytest tests/test_refactor_agent_supervisor.py -q
- Bundle: refactor/g8/g8-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G8.S2
- Missing evidence: The supervisor itself should not duplicate tasks or emit malformed payloads.
- AST symbols: PROJECT_ROOT, ACCELERATE_REPO, STATE_ROOT, QUEUE_PATH, GOALS_PATH, OBJECTIVE_PATH, TODO_PATH, BUNDLE_DIR, DATASET_DIR, DISCOVERY_DIR, GRAPH_PATH, STRATEGY_PATH, EVENTS_PATH, REFILL_STATE_PATH, SUPERVISOR_STATE_DIR, WORKTREE_ROOT, BUNDLE_LANE_ROOT, BUNDLE_LANE_MANIFEST, BUNDLE_COORDINATION_PATH, STATUS_PATH, PID_PATH, LOG_PATH, TASKBOARD_DOC_PATH, TASK_PREFIX, TASK_HEADER_PREFIX, TASK_TYPES, MODEL_NAME, _ensure_accelerate_import_path, _task_queue_class, _upstream_objective_runner
- Merge key: refactor/g8/g8-s2
- Candidate kind: seed
- Todo vector key: ref-026-createtestsforrefactorsupervisorseedidempotencea
- Acceptance: Running seed twice does not duplicate active tasks.; Payloads include goal, subgoal, priority, acceptance, and validation.

## REF-027 Resolve dirty main checkout blocking 1 worktree merges

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Fingerprint: bf5436592889fd504010705a6d3f0a081a801e69
- Dedupe key: reconciliation_guardrail:main_checkout_dirty
- Depends on:
- Outputs: data/refactor_supervisor/bundle_lanes/refactor-g8-g8-s2/discovery, data/refactor_supervisor/objective_bundles/refactor-g8-g8-s2.todo.md
- Validation: test -f /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g8-g8-s2/discovery/2026-07-22-ref-027-reconciliation-bf5436592889.md
- Acceptance: Reconciliation guardrail filed this because 1 branch or worktree cleanup candidates are blocked by main_checkout_dirty. Use evidence and the machine-readable reconciliation plan in /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g8-g8-s2/discovery/2026-07-22-ref-027-reconciliation-bf5436592889.md, reconcile the dirty checkout or dirty worktree group deliberately, then rerun the supervisor cleanup/reconciliation pass and confirm that the blocked candidate count decreases.
