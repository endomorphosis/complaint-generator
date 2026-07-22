# Objective Bundle: refactor/g10/g10-s2

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-203: REF-203 Add analyzer canaries, parser failure budgets, and fail-closed health classification

## REF-203 Add analyzer canaries, parser failure budgets, and fail-closed health classification

- Status: completed
- Completion: manual
- Priority: P0
- Track: G10
- Depends on: REF-201
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/analyzer_health.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/backlog_refinery.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_analyzer_health.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_analyzer_health.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_backlog_refinery.py -q
- Bundle: refactor/g10/g10-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S2
- Missing evidence: A scanner that silently stops recognizing syntax can otherwise report the same zero findings as a complete repository.
- AST symbols: logger, DEFAULT_CODEBASE_SCAN_MIN_OPEN_TASKS, DEFAULT_CODEBASE_SCAN_MAX_FINDINGS, DEFAULT_CODEBASE_SCAN_COOLDOWN_SECONDS, DEFAULT_OBJECTIVE_SCAN_MIN_OPEN_TASKS, DEFAULT_OBJECTIVE_SCAN_MAX_FINDINGS, DEFAULT_OBJECTIVE_SCAN_COOLDOWN_SECONDS, DEFAULT_VALIDATION_RETRY_BUDGET, DEFAULT_MERGE_RETRY_BUDGET, DEFAULT_IMPLEMENTATION_RETRY_BUDGET, DEFAULT_STALE_GIT_LOCK_SECONDS, DEFAULT_GENERATED_DIRTY_HARD_PATH_CAP, DEFAULT_GENERATED_DIRTY_MAX_DELETE_PATHS, DEFAULT_GENERATED_DIRTY_ALLOW_DELETIONS, DEFAULT_DEPENDENCY_GUARDRAIL_MAX_FINDINGS, DEFAULT_RECONCILIATION_GUARDRAIL_MAX_FINDINGS, DEFAULT_TASK_ID_PREFIX, DEFAULT_TASK_HEADER_PREFIX, CODEBASE_SCAN_MAX_FILE_BYTES, CODEBASE_SCAN_SUFFIXES, CODEBASE_SCAN_SKIP_PARTS, CODEBASE_SCAN_SKIP_PREFIXES, ANNOTATION_FOLLOWUP_RE, CodebaseFinding, utc_now, task_id_prefix, task_header_prefix, split_csv, task_ids_from_todo_text, task_block_is_present
- Merge key: refactor/g10/g10-s2
- Candidate kind: seed
- Todo vector key: ref-203-addanalyzercanariesparserfailurebudgetsandfail-c
- Acceptance: Deterministic fixtures exercise every supported finding kind and parser path on each analyzer version.; Missing canaries, excessive skips, parser failures, incomplete git-root discovery, and impossible candidate funnels classify the scan as unhealthy or partial.; Health thresholds are configurable, recorded in the receipt, and cannot silently downgrade a failed scan to exhausted.; The daemon continues safe implementation work while preventing unhealthy analysis from closing goals.

- [ ] Task checkbox-204: REF-204 Implement fingerprint-independent audit scans and exhaustion quorum

## REF-204 Implement fingerprint-independent audit scans and exhaustion quorum

- Status: completed
- Completion: manual
- Priority: P0
- Track: G10
- Depends on: REF-201, REF-202
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/audit_scanner.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scan_receipts.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/backlog_refinery.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/dataset_store.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_audit_scanner.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_audit_scanner.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py -q
- Bundle: refactor/g10/g10-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S2
- Missing evidence: A saturated or corrupt seen-fingerprint set can make normal refill scans appear exhausted without independently re-evaluating the codebase.
- AST symbols: logger, DEFAULT_CODEBASE_SCAN_MIN_OPEN_TASKS, DEFAULT_CODEBASE_SCAN_MAX_FINDINGS, DEFAULT_CODEBASE_SCAN_COOLDOWN_SECONDS, DEFAULT_OBJECTIVE_SCAN_MIN_OPEN_TASKS, DEFAULT_OBJECTIVE_SCAN_MAX_FINDINGS, DEFAULT_OBJECTIVE_SCAN_COOLDOWN_SECONDS, DEFAULT_VALIDATION_RETRY_BUDGET, DEFAULT_MERGE_RETRY_BUDGET, DEFAULT_IMPLEMENTATION_RETRY_BUDGET, DEFAULT_STALE_GIT_LOCK_SECONDS, DEFAULT_GENERATED_DIRTY_HARD_PATH_CAP, DEFAULT_GENERATED_DIRTY_MAX_DELETE_PATHS, DEFAULT_GENERATED_DIRTY_ALLOW_DELETIONS, DEFAULT_DEPENDENCY_GUARDRAIL_MAX_FINDINGS, DEFAULT_RECONCILIATION_GUARDRAIL_MAX_FINDINGS, DEFAULT_TASK_ID_PREFIX, DEFAULT_TASK_HEADER_PREFIX, CODEBASE_SCAN_MAX_FILE_BYTES, CODEBASE_SCAN_SUFFIXES, CODEBASE_SCAN_SKIP_PARTS, CODEBASE_SCAN_SKIP_PREFIXES, ANNOTATION_FOLLOWUP_RE, CodebaseFinding, utc_now, task_id_prefix, task_header_prefix, split_csv, task_ids_from_todo_text, task_block_is_present
- Merge key: refactor/g10/g10-s2
- Candidate kind: seed
- Todo vector key: ref-204-implementfingerprint-independentauditscansandexh
- Acceptance: Audit mode scans without mutating or trusting the normal seen set and reports known, stale, changed, and novel findings separately.; Exhaustion requires a configurable quorum of healthy exhaustive receipts tied to repository tree, analyzer version, configuration, and objective revision.; Relevant code, configuration, analyzer, or objective changes invalidate prior quorum members deterministically.; Repeated scans of an unchanged tree are deduplicated and cannot manufacture quorum confidence.

- [ ] Task checkbox-205: REF-205 Escalate low-backlog analysis through AST and llm_router planning before declaring exhaustion

## REF-205 Escalate low-backlog analysis through AST and llm_router planning before declaring exhaustion

- Status: completed
- Completion: manual
- Priority: P1
- Track: G10
- Depends on: REF-203, REF-204
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/analyzer_health.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/audit_scanner.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_analysis_escalation.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_analysis_escalation.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py -q
- Bundle: refactor/g10/g10-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G10.S2
- Missing evidence: Static pattern exhaustion should trigger bounded semantic and goal-directed analysis rather than leave the board below its configured floor without explanation.
- AST symbols: PromptBuilder, BootstrapCallback, DEFAULT_OPEN_TASK_STATUSES, DEFAULT_TASK_PROPOSAL_TEST_OUTPUT, TaskProposalRouterError, TaskProposalRouterConfig, TaskProposalRouterCliConfig, TaskProposalRoutePaths, TaskProposalRouteSpec, _repo_path, build_task_proposal_route_paths, _task_values, _task_value, task_metadata_lines, build_task_proposal_prompt, standard_task_proposal_requested_outputs, build_task_proposal_prompt_builder, build_task_proposal_router_cli_config, run_configured_task_proposal_router_cli, ConfiguredTaskProposalRouterRunner, build_configured_task_proposal_router_runner, build_repo_task_proposal_router_runner, build_repo_task_proposal_route_runner, build_repo_task_proposal_route_runner_from_spec, select_proposal_task, _artifact_relative_path, run_task_proposal_router, build_task_proposal_router_parser, run_task_proposal_router_cli, StructuredRouter
- Merge key: refactor/g10/g10-s2
- Candidate kind: seed
- Todo vector key: ref-205-escalatelow-backloganalysisthroughastandllm-rout
- Acceptance: A policy escalates from incremental static scan to exhaustive AST coverage and then schema-constrained llm_router proposals when healthy backlog remains below target.; Each escalation records cost, scope, novelty, confidence, rejected candidates, and the objective terms it attempted to cover.; Router failure or low-confidence output produces an analysis-inconclusive result and deterministic fallback, never a false completion.; Rate, token, retry, and novelty limits prevent an unbounded task-generation loop.
