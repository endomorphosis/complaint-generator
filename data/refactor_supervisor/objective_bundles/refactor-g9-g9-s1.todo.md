# Objective Bundle: refactor/g9/g9-s1

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [ ] Task checkbox-36: REF-036 Introduce canonical task identity and a durable supervisor task ledger

## REF-036 Introduce canonical task identity and a durable supervisor task ledger

- Status: todo
- Completion: manual
- Priority: P0
- Track: G9
- Depends on: 
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_identity.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/persistent_task_queue.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q
- Bundle: refactor/g9/g9-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G9.S1
- Missing evidence: Bundle-local numeric task ids currently collide across boards and make global reconciliation ambiguous.
- AST symbols: DEFAULT_EMBEDDING_DIMENSIONS, DEFAULT_EMBEDDING_MIN_SCORE, DEFAULT_BUNDLE_CLUSTER_MIN_SCORE, DEFAULT_OBJECTIVE_TASK_SUMMARY_PREFIX, parse_python_ast_quietly, DEFAULT_DISCOVERY_OUTPUT_PATH, DEFAULT_SURPLUS_FINDINGS_PER_GOAL, DEFAULT_SURPLUS_MIN_TERMS_PER_TODO, DEFAULT_SCAN_OVERSAMPLE_MULTIPLIER, DEFAULT_TASK_PREFIX, DEFAULT_AST_DATASET_MAX_CHARS, LAUNCH_PLAYWRIGHT_VALIDATION_COMMAND, LAUNCH_PLAYWRIGHT_VALIDATION_MARKERS, LAUNCH_PLAYWRIGHT_VALIDATION_GATE_EVIDENCE, SCAN_SUFFIXES, SKIP_DIRS, ObjectiveGoal, ObjectiveFinding, ObjectiveTaskRecord, ObjectiveHeapRecord, BundleWriteResult, utc_now, split_terms, objective_tokens, text_embedding, cosine, normalize_field_key, parse_goal_heap, safe_bundle_key, repo_relative_path
- Merge key: refactor/g9/g9-s1
- Candidate kind: seed
- Todo vector key: ref-036-introducecanonicaltaskidentityandadurablesupervi
- Acceptance: Every task has a stable canonical key or CID independent of board path and display id.; Legacy markdown tasks migrate idempotently with board namespace provenance.; Branches, events, retries, cooldowns, leases, and receipts carry canonical identity.; Refill cannot create a second active task for the same canonical work item.

- [ ] Task checkbox-37: REF-037 Replace static bundle launch with a dynamic leased worker pool

## REF-037 Replace static bundle launch with a dynamic leased worker pool

- Status: todo
- Completion: manual
- Priority: P0
- Track: G9
- Depends on: REF-036
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/multi_supervisor_runner.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py -q
- Bundle: refactor/g9/g9-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G9.S1
- Missing evidence: The current bundle supervisor starts the first N lexical bundles once and cannot reclaim idle lanes or discover refilled work.
- AST symbols: logger, BundleLaneSpec, resolve_repo_path, lane_state_prefix, implementation_supervisor_command, plan_bundle_lanes, launch_bundle_lanes, check_lane_health, write_bundle_lane_manifest, default_state_root, build_arg_parser, run_bundle_supervisor, main, to_dict, path, command, payload, parser, implement_group, repo_root, state_root, worktree_root, log_dir, manifest_path, bundle_index_path, lanes, started, args, bundle_key, safe_key
- Merge key: refactor/g9/g9-s1
- Candidate kind: seed
- Todo vector key: ref-037-replacestaticbundlelaunchwithadynamicleasedworke
- Acceptance: A persistent scheduler discovers new and refilled tasks without restart.; Workers claim ready tasks, release drained or blocked leases, and steal conflict-safe work.; Lane count remains within configured capacity and no task executes under two accepted leases.; The manifest is an authoritative live projection rather than a launch-time snapshot.

- [ ] Task checkbox-38: REF-038 Integrate a deduplicating single-consumer merge train

## REF-038 Integrate a deduplicating single-consumer merge train

- Status: todo
- Completion: manual
- Priority: P0
- Track: G9
- Depends on: REF-037
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_queue.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_train.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_resolver.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_merge_train.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_merge_train.py -q
- Bundle: refactor/g9/g9-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G9.S1
- Missing evidence: Independent lanes currently race to merge and repeatedly retry the same failed branches.
- AST symbols: MergeRequest, _PRIORITY_ORDER, MergeQueue, to_dict, from_dict, __init__, enqueue, dequeue, complete, fail, requeue, pending_count, processing_count, has_pending_for_task, _purge_stale, status, now, request_id, request, file_name, file_path, tmp_path, pending, completed, purged, processing_path, completed_path, pending_path, data, failed_path
- Merge key: refactor/g9/g9-s1
- Candidate kind: seed
- Todo vector key: ref-038-integrateadeduplicatingsingle-consumermergetrain
- Acceptance: All implementation lanes enqueue merge candidates instead of racing the target checkout.; The train deduplicates by canonical task and commit, rebases on the latest target, and preserves priority plus age fairness.; One conflict fingerprint invokes at most one active resolver attempt.; Bounded failures enter quarantine with a durable receipt instead of a polling retry loop.
