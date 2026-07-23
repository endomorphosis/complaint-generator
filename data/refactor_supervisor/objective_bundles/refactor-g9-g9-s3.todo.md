# Objective Bundle: refactor/g9/g9-s3

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-42: REF-042 Schedule lanes from live resources and llm_router provider capacity

## REF-042 Schedule lanes from live resources and llm_router provider capacity

- Status: completed
- Completion: manual
- Priority: P1
- Track: G9
- Depends on: REF-037, REF-041
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/resource_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_resource_scheduler.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_resource_scheduler.py -q
- Bundle: refactor/g9/g9-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G9.S3
- Missing evidence: Resource class, capability fit, and lane capacity are currently static even when workers are idle or providers are rate-limited.
- AST symbols: logger, BundleLaneSpec, resolve_repo_path, lane_state_prefix, implementation_supervisor_command, plan_bundle_lanes, launch_bundle_lanes, check_lane_health, write_bundle_lane_manifest, default_state_root, build_arg_parser, run_bundle_supervisor, main, to_dict, path, command, payload, parser, implement_group, repo_root, state_root, worktree_root, log_dir, manifest_path, bundle_index_path, lanes, started, args, bundle_key, safe_key
- Merge key: refactor/g9/g9-s3
- Candidate kind: seed
- Todo vector key: ref-042-schedulelanesfromliveresourcesandllm-routerprovi
- Acceptance: Heartbeats report measured CPU, memory, disk, active phase, and available worker capacity.; Scheduler honors llm_router health, quota, latency, context, and token-budget constraints.; Concurrency scales within configured limits and applies backpressure before provider or host exhaustion.; Idle lanes advertise zero occupied capacity and can be reassigned.

- [x] Task checkbox-43: REF-043 Add impact-selected cached and parallel validation stages

## REF-043 Add impact-selected cached and parallel validation stages

- Status: completed
- Completion: manual
- Priority: P1
- Track: G9
- Depends on: REF-038
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_commands.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_validation_scheduler.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_validation_scheduler.py -q
- Bundle: refactor/g9/g9-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G9.S3
- Missing evidence: Validation commands currently run serially without changed-file impact selection or reusable baseline results.
- AST symbols: split_validation_commands, text, in_single_quote, in_double_quote, escaped, flush, command, REPO_ROOT, logger, TASK_HEADER_PREFIX, DEFAULT_TRACKS, PRIORITY_ORDER, DEFAULT_IMPLEMENTATION_TIMEOUT_SECONDS, LLM_MERGE_RESOLVER_COMMAND_ENV, LLM_MERGE_RESOLVER_TIMEOUT_ENV, DAEMON_MERGE_RECONCILIATION_MAX_ENV, DEFAULT_DAEMON_MERGE_RECONCILIATION_MAX, DAEMON_MERGED_WORKTREE_CLEANUP_MAX_ENV, DEFAULT_DAEMON_MERGED_WORKTREE_CLEANUP_MAX, DAEMON_HOOK_TIMEOUT_ENV, DEFAULT_DAEMON_HOOK_TIMEOUT_SECONDS, MERGE_RECONCILIATION_MAX_AGE_ENV, DEFAULT_MERGE_RECONCILIATION_MAX_AGE_SECONDS, UNSUPPORTED_TYPESCRIPT_VALIDATION_FLAGS, RECENT_NO_CHANGE_COOLDOWN_SECONDS, NO_CHANGE_SELECTION_PENALTY, UNRESOLVED_MERGE_SELECTION_PENALTY, TRANSIENT_MERGE_LOCK_REASONS, TRANSIENT_MERGE_RETRY_BUDGET_WHEN_DISABLED, IMPLEMENTATION_TASK_CLAIM_LOCK_KIND
- Merge key: refactor/g9/g9-s3
- Candidate kind: seed
- Todo vector key: ref-043-addimpact-selectedcachedandparallelvalidationsta
- Acceptance: Cheap deterministic checks run before expensive tests and fail fast.; Independent validations run in parallel under a bounded resource budget.; Cache keys include target commit, command, relevant environment, and dependency state.; Impact selection is conservative, explainable, and escalates to broader validation before merge completion.
