# Complaint Generator Refactor Objective Heap

Ultimate objective: Refactor complaint-generator safely and incrementally while preserving behavior.

## G1 Stabilize repository boundaries

- Status: active
- Priority: P0
- Bundle: refactor/g1
- Goal: Stabilize repository boundaries
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, mediator/mediator.py, applications/complaint_workspace.py, tests/test_claim_support_review_playwright_smoke.py, docs/ARCHITECTURE.md, pyproject.toml, scripts/graphrag_email_manifest.py, scripts/import_gmail_evidence.py, scripts/import_local_eml_directory.py, applications/dashboard_ui.py, complaint_generator/agentic_evidence_download.py, complaint_generator/data_migration.py, data/refactor_supervisor/discovery/2026-07-22-ref-057-objective-validation-repair.md, objective validation repair
- Validation: python -m pytest --collect-only -q

## G1.S1 Map package ownership and runtime entrypoints

- Status: active
- Parent: G1
- Priority: P0
- Bundle: refactor/g1/g1-s1
- Goal: Map package ownership and runtime entrypoints
- Evidence: mediator/mediator.py, applications/complaint_workspace.py, tests/test_claim_support_review_playwright_smoke.py, scripts/synthesize_hacc_complaint.py, tests/test_review_api.py, complaint_phases/denoiser.py, A short module ownership map exists., Entrypoints are grouped by CLI, web, mediator, and workflow role., python -m pytest tests/test_package_imports.py -q, docs/ARCHITECTURE.md, pyproject.toml, Architecture docs identify allowed imports., New work has a simple rule for where shared code belongs., python -m pytest tests/test_package_imports.py -q
- Validation: python -m pytest tests/test_package_imports.py -q

## G1.S2 Remove ad hoc import path behavior from production surfaces

- Status: active
- Parent: G1
- Priority: P0
- Bundle: refactor/g1/g1-s2
- Goal: Remove ad hoc import path behavior from production surfaces
- Evidence: scripts/graphrag_email_manifest.py, scripts/import_gmail_evidence.py, scripts/import_local_eml_directory.py, scripts/master_case_email.py, scripts/process_hacc_pdfs_to_kg.py, scripts/run_gmail_duckdb_pipeline.py, scripts/run_hacc_adversarial_report.py, scripts/run_hacc_grounded_pipeline.py, scripts/run_hacc_preset_matrix.py, No production entrypoint mutates sys.path for normal imports., Explicit exceptions are isolated to scripts/tests., python -m pytest tests/test_package_imports.py -q, applications/dashboard_ui.py, complaint_generator/agentic_evidence_download.py, complaint_generator/data_migration.py, complaint_generator/email_agentic_search.py, complaint_generator/email_authority_enrichment.py, complaint_generator/email_credentials.py, complaint_generator/email_graphrag.py, complaint_generator/email_import.py, complaint_generator/email_oauth.py, complaint_generator/email_pipeline.py, complaint_generator/email_seed_planner.py, complaint_generator/email_timeline_handoff.py, complaint_generator/evidence_relevance.py, integrations/ipfs_datasets/llm.py, Production direct imports are replaced or documented., Degraded mode still imports cleanly., python -m pytest tests/test_ipfs_adapter_layer.py -q, data/refactor_supervisor/discovery/2026-07-22-ref-070-objective-validation-repair.md, objective validation repair
- Validation: python -m pytest tests/test_package_imports.py -q; python -m pytest tests/test_ipfs_adapter_layer.py -q

## G2 Decompose oversized orchestration modules

- Status: active
- Priority: P0
- Bundle: refactor/g2
- Goal: Decompose oversized orchestration modules
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, mediator/mediator.py, mediator/__init__.py, mediator/claim_support_hooks.py, applications/complaint_workspace.py, applications/dashboard_ui.py, playwright/server.js
- Validation: python -m pytest --collect-only -q

## G2.S1 Extract mediator service seams

- Status: active
- Parent: G2
- Priority: P0
- Bundle: refactor/g2/g2-s1
- Goal: Extract mediator service seams
- Evidence: mediator/mediator.py, mediator/__init__.py, One cohesive service is extracted., Existing imports continue to resolve., python -m pytest tests/test_mediator.py tests/test_mediator_three_phase.py -q, mediator/claim_support_hooks.py, At least one cohesive helper group moves behind a stable import., No payload contract changes without tests., python -m pytest tests/test_claim_support_hooks.py tests/test_claim_support_review_dashboard_flow.py -q
- Validation: python -m pytest tests/test_mediator.py tests/test_mediator_three_phase.py -q; python -m pytest tests/test_claim_support_hooks.py tests/test_claim_support_review_dashboard_flow.py -q

## G2.S2 Reduce application surface coupling

- Status: active
- Parent: G2
- Priority: P0
- Bundle: refactor/g2/g2-s2
- Goal: Reduce application surface coupling
- Evidence: applications/complaint_workspace.py, One handler group is isolated., Routes keep the same response shape., python -m pytest tests/test_review_api.py -q, applications/dashboard_ui.py, playwright/server.js, Fixture builders are named and reusable., Playwright smoke tests remain stable., python -m pytest tests/test_claim_support_review_playwright_smoke.py -q
- Validation: python -m pytest tests/test_review_api.py -q; python -m pytest tests/test_claim_support_review_playwright_smoke.py -q

## G3 Harden adapter contracts and degraded mode

- Status: active
- Priority: P0
- Bundle: refactor/g3
- Goal: Harden adapter contracts and degraded mode
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, integrations/ipfs_datasets/capabilities.py, integrations/ipfs_datasets/loader.py, integrations/ipfs_datasets/documents.py, mediator/evidence_hooks.py, integrations/ipfs_datasets/graphs.py, complaint_phases/knowledge_graph.py, integrations/ipfs_datasets/logic.py, lib/formal_logic, data/refactor_supervisor/discovery/2026-07-22-ref-066-objective-validation-repair.md, objective validation repair
- Validation: python -m pytest --collect-only -q

## G3.S1 Normalize IPFS datasets adapter payloads

- Status: active
- Parent: G3
- Priority: P0
- Bundle: refactor/g3/g3-s1
- Goal: Normalize IPFS datasets adapter payloads
- Evidence: integrations/ipfs_datasets/capabilities.py, integrations/ipfs_datasets/loader.py, All adapter groups report stable keys., Missing optional extras produce actionable reasons., python -m pytest tests/test_ipfs_adapter_layer.py -q, integrations/ipfs_datasets/documents.py, integrations/ipfs_datasets/provenance.py, mediator/evidence_hooks.py, mediator/legal_authority_hooks.py, mediator/web_evidence_hooks.py, tests/test_document_ingestion_contract.py, tests/test_web_evidence_hooks.py, Evidence, authority, and web ingestion can call one parse contract., Fallback mode preserves current behavior., python -m pytest tests/test_document_pipeline.py tests/test_document_pipeline_fallbacks.py -q, data/refactor_supervisor/discovery/2026-07-23-ref-317-objective-validation-repair.md, objective validation repair
- Validation: python -m pytest tests/test_ipfs_adapter_layer.py -q; python -m pytest tests/test_document_pipeline.py tests/test_document_pipeline_fallbacks.py -q

## G3.S2 Clarify graph, GraphRAG, and logic adapter boundaries

- Status: active
- Parent: G3
- Priority: P0
- Bundle: refactor/g3/g3-s2
- Goal: Clarify graph, GraphRAG, and logic adapter boundaries
- Evidence: integrations/ipfs_datasets/graphs.py, complaint_phases/knowledge_graph.py, integrations/ipfs_datasets/graphrag.py, Interfaces specify persistence, query, and provenance fields., Fallback graph behavior remains covered., python -m pytest tests/test_complaint_phases.py tests/test_ipfs_adapter_layer.py -q, integrations/ipfs_datasets/logic.py, lib/formal_logic, tests/test_logic_capability_contract.py, Logic status distinguishes unavailable, degraded, and implemented., Callers do not branch on fragile strings., python -m pytest tests/test_symbolicai_logic_dependency.py tests/test_ipld_logic_storage_dependency.py -q, data/refactor_supervisor/discovery/2026-07-23-ref-318-objective-validation-repair.md, objective validation repair
- Validation: python -m pytest tests/test_complaint_phases.py tests/test_ipfs_adapter_layer.py -q; python -m pytest tests/test_symbolicai_logic_dependency.py tests/test_ipld_logic_storage_dependency.py -q

## G4 Improve validation speed and confidence

- Status: active
- Priority: P1
- Bundle: refactor/g4
- Goal: Improve validation speed and confidence
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, pytest.ini, Makefile, docs/VERIFICATION_SUMMARY.md, tests, pyproject.toml
- Validation: python -m pytest --collect-only -q

## G4.S1 Create focused test lanes for refactor work

- Status: active
- Parent: G4
- Priority: P1
- Bundle: refactor/g4/g4-s1
- Goal: Create focused test lanes for refactor work
- Evidence: pytest.ini, Makefile, docs/VERIFICATION_SUMMARY.md, A documented test lane map exists., Each P0 workstream has a named validation command., python -m pytest --collect-only -q, tests, pyproject.toml, Tests catch direct production imports where adapters are required., Tests avoid blocking intentional test-only imports., python -m pytest tests/test_package_imports.py -q, data/refactor_supervisor/discovery/2026-07-22-ref-071-objective-validation-repair.md, objective validation repair
- Validation: python -m pytest --collect-only -q; python -m pytest tests/test_package_imports.py -q

## G5 Make automation observable and refillable

- Status: active
- Priority: P0
- Bundle: refactor/g5
- Goal: Make automation observable and refillable
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, scripts/refactor_agent_supervisor.py, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, data/refactor_supervisor
- Validation: python -m pytest --collect-only -q

## G5.S1 Operate a durable refactor taskboard

- Status: active
- Parent: G5
- Priority: P0
- Bundle: refactor/g5/g5-s1
- Goal: Operate a durable refactor taskboard
- Evidence: scripts/refactor_agent_supervisor.py, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, Queued task count is maintained above the configured floor., Docs and JSON state are regenerated each cycle., python scripts/refactor_agent_supervisor.py seed --once, data/refactor_supervisor, Status JSON includes pid, heartbeat, scan summary, and counts., Stop command terminates the daemon cleanly., python scripts/refactor_agent_supervisor.py status
- Validation: python scripts/refactor_agent_supervisor.py seed --once; python scripts/refactor_agent_supervisor.py status

## G6 Pay down error-handling and observability debt

- Status: active
- Priority: P1
- Bundle: refactor/g6
- Goal: Pay down error-handling and observability debt
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, mediator/mediator.py, mediator/evidence_hooks.py, integrations/ipfs_datasets/search.py, applications/ui_review.py, complaint_generator/ui_optimizer_daemon.py, mediator/state.py, integrations/ipfs_datasets/scraper_daemon.py, scripts/gmail_duckdb_daemon.py, docs/OBSERVABILITY_INDEX.md, docs/observability/TROUBLESHOOTING.md, data/refactor_supervisor/discovery/2026-07-21-ref-032-objective-validation-repair.md, objective validation repair
- Validation: python -m pytest --collect-only -q

## G6.S1 Replace silent failures with typed outcomes

- Status: active
- Parent: G6
- Priority: P1
- Bundle: refactor/g6/g6-s1
- Goal: Replace silent failures with typed outcomes
- Evidence: mediator/mediator.py, mediator/evidence_hooks.py, integrations/ipfs_datasets/search.py, Top production broad-exception clusters are documented., At least one cluster returns a typed degraded result., python -m pytest tests/test_mediator.py tests/test_ipfs_adapter_layer.py -q, applications/ui_review.py, complaint_generator/ui_optimizer_daemon.py, mediator/state.py, Intentional ignores are named., Unexpected failures leave diagnostic breadcrumbs., python -m pytest tests/test_ui_optimizer_daemon_cli.py tests/test_review_api.py -q
- Validation: python -m pytest tests/test_mediator.py tests/test_ipfs_adapter_layer.py -q; python -m pytest tests/test_ui_optimizer_daemon_cli.py tests/test_review_api.py -q

## G6.S2 Unify runtime status payloads

- Status: active
- Parent: G6
- Priority: P1
- Bundle: refactor/g6/g6-s2
- Goal: Unify runtime status payloads
- Evidence: complaint_generator/ui_optimizer_daemon.py, integrations/ipfs_datasets/scraper_daemon.py, scripts/gmail_duckdb_daemon.py, Status payloads include status, pid, updated_at, artifacts, and last_error where applicable., Existing CLI tests remain compatible., python -m pytest tests/test_ui_optimizer_daemon_cli.py tests/test_gmail_duckdb_daemon_cli.py -q, docs/OBSERVABILITY_INDEX.md, docs/observability/TROUBLESHOOTING.md, Docs explain where to find pid, log, status, and queue files., Troubleshooting includes stale running task recovery., python scripts/refactor_agent_supervisor.py status
- Validation: python -m pytest tests/test_ui_optimizer_daemon_cli.py tests/test_gmail_duckdb_daemon_cli.py -q; python scripts/refactor_agent_supervisor.py status

## G7 Rationalize frontend and review surfaces

- Status: active
- Priority: P1
- Bundle: refactor/g7
- Goal: Rationalize frontend and review surfaces
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, applications/review_api.py, applications/ui_review.py, mediator/claim_support_hooks.py, tests/test_claim_support_review_playwright_smoke.py, tests/test_review_surface_site_playwright.py, data/refactor_supervisor/discovery/2026-07-21-ref-033-objective-validation-repair.md, objective validation repair
- Validation: python -m pytest --collect-only -q

## G7.S1 Separate review API contracts from display assembly

- Status: active
- Parent: G7
- Priority: P1
- Bundle: refactor/g7/g7-s1
- Goal: Separate review API contracts from display assembly
- Evidence: applications/review_api.py, applications/ui_review.py, mediator/claim_support_hooks.py, DTO helpers cover coverage, follow-up, and support-path summaries., Route response snapshots stay stable., python -m pytest tests/test_review_api.py tests/test_claim_support_review_dashboard_flow.py -q, tests/test_claim_support_review_playwright_smoke.py, tests/test_review_surface_site_playwright.py, Shared builders remove repeated setup., Screenshots still render with representative support states., python -m pytest tests/test_claim_support_review_playwright_smoke.py tests/test_review_surface_site_playwright.py -q
- Validation: python -m pytest tests/test_review_api.py tests/test_claim_support_review_dashboard_flow.py -q; python -m pytest tests/test_claim_support_review_playwright_smoke.py tests/test_review_surface_site_playwright.py -q

## G8 Prepare incremental implementation slices

- Status: active
- Priority: P0
- Bundle: refactor/g8
- Goal: Prepare incremental implementation slices
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, data/refactor_supervisor/refactor_goals.json, scripts/refactor_agent_supervisor.py, tests/test_refactor_agent_supervisor.py
- Validation: python -m pytest --collect-only -q

## G8.S1 Convert existing roadmaps into executable slices

- Status: active
- Parent: G8
- Priority: P0
- Bundle: refactor/g8/g8-s1
- Goal: Convert existing roadmaps into executable slices
- Evidence: docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, Each P0 backlog workstream maps to at least one refactor goal., Duplicated tasks are merged or explicitly scoped., python scripts/refactor_agent_supervisor.py seed --once, data/refactor_supervisor/refactor_goals.json, The first three claims are small, testable, and dependency-ordered., Each claim names exact validation commands., python scripts/refactor_agent_supervisor.py status
- Validation: python scripts/refactor_agent_supervisor.py seed --once; python scripts/refactor_agent_supervisor.py status

## G8.S2 Keep generated artifacts reviewable

- Status: active
- Parent: G8
- Priority: P0
- Bundle: refactor/g8/g8-s2
- Goal: Keep generated artifacts reviewable
- Evidence: scripts/refactor_agent_supervisor.py, Status output or a new command lists next tasks by priority., Output is stable enough for automation., python scripts/refactor_agent_supervisor.py status, tests/test_refactor_agent_supervisor.py, scripts/refactor_agent_supervisor.py, Running seed twice does not duplicate active tasks., Payloads include goal, subgoal, priority, acceptance, and validation., python -m pytest tests/test_refactor_agent_supervisor.py -q
- Validation: python scripts/refactor_agent_supervisor.py status; python -m pytest tests/test_refactor_agent_supervisor.py -q

## G9 Increase agent-supervisor planning quality and throughput

- Status: active
- Priority: P0
- Bundle: refactor/g9
- Goal: Increase agent-supervisor planning quality and throughput
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_identity.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_queue.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_train.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_resolver.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/conflict_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/resource_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_commands.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scheduler_metrics.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/event_log.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/supervisor_watchdog.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/dataset_store.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/worktrees.py, data/refactor_supervisor/discovery/2026-07-22-ref-061-objective-validation-repair.md, objective validation repair
- Validation: python -m pytest --collect-only -q

## G9.S1 Establish canonical coordination and merge flow

- Status: active
- Parent: G9
- Priority: P0
- Bundle: refactor/g9/g9-s1
- Goal: Establish canonical coordination and merge flow
- Evidence: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_identity.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/persistent_task_queue.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py, Every task has a stable canonical key or CID independent of board path and display id., Legacy markdown tasks migrate idempotently with board namespace provenance., Branches, events, retries, cooldowns, leases, and receipts carry canonical identity., Refill cannot create a second active task for the same canonical work item., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/multi_supervisor_runner.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py, A persistent scheduler discovers new and refilled tasks without restart., Workers claim ready tasks, release drained or blocked leases, and steal conflict-safe work., Lane count remains within configured capacity and no task executes under two accepted leases., The manifest is an authoritative live projection rather than a launch-time snapshot., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_queue.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_train.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_resolver.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_merge_train.py, All implementation lanes enqueue merge candidates instead of racing the target checkout., The train deduplicates by canonical task and commit, rebases on the latest target, and preserves priority plus age fairness., One conflict fingerprint invokes at most one active resolver attempt., Bounded failures enter quarantine with a durable receipt instead of a polling retry loop., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_merge_train.py -q
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_merge_train.py -q

## G9.S2 Plan from dependencies, conflicts, and objective value

- Status: active
- Parent: G9
- Priority: P0
- Bundle: refactor/g9/g9-s2
- Goal: Plan from dependencies, conflicts, and objective value
- Evidence: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py, Goal, import, interface, output-input, migration, and validation prerequisites become explicit DAG edges with provenance., Only tasks whose prerequisite merge receipts succeeded are claimable., Priority includes critical-path length, slack, downstream unlock value, age, and configured objective priority., Cycles and missing dependencies produce bounded repair evidence rather than deadlock., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/conflict_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_vector_index.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py, Conflict surfaces include all predicted files, AST symbols, interfaces, submodules, and generated artifacts., Lane planning colors the conflict graph so overlapping tasks do not run concurrently unless explicitly allowed., Actual branch diffs and conflict receipts update future conflict weights., Planner output explains every co-location or separation decision., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py, Each eligible subgoal can produce multiple schema-validated plan branches through llm_router., Candidates declare predicted files and symbols, dependencies, validation proof, cost, risk, and expected objective delta., A deterministic evaluator selects a branch and retains rejected alternatives plus rationale., Router failure falls back to deterministic planning without blocking ready work., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py -q
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py -q

## G9.S3 Adapt execution capacity and validation cost

- Status: active
- Parent: G9
- Priority: P0
- Bundle: refactor/g9/g9-s3
- Goal: Adapt execution capacity and validation cost
- Evidence: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/resource_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_resource_scheduler.py, Heartbeats report measured CPU, memory, disk, active phase, and available worker capacity., Scheduler honors llm_router health, quota, latency, context, and token-budget constraints., Concurrency scales within configured limits and applies backpressure before provider or host exhaustion., Idle lanes advertise zero occupied capacity and can be reassigned., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_resource_scheduler.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_commands.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_validation_scheduler.py, Cheap deterministic checks run before expensive tests and fail fast., Independent validations run in parallel under a bounded resource budget., Cache keys include target commit, command, relevant environment, and dependency state., Impact selection is conservative, explainable, and escalates to broader validation before merge completion., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_validation_scheduler.py -q, data/refactor_supervisor/discovery/2026-07-23-ref-315-objective-validation-repair.md, objective validation repair
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_resource_scheduler.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_validation_scheduler.py -q

## G9.S4 Close the scheduler feedback and lifecycle loop

- Status: active
- Parent: G9
- Priority: P0
- Bundle: refactor/g9/g9-s4
- Goal: Close the scheduler feedback and lifecycle loop
- Evidence: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scheduler_metrics.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/event_log.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/supervisor_watchdog.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py, One event-derived snapshot reports ready, active, idle, blocked, validation, merge, and resolver phases., Metrics include queue wait, implementation and validation duration, merge wait, conflict and retry rate, completions, tokens, and cost., Every metric is keyed by canonical goal, subgoal, task, lane, and provider identity., Scheduler decisions consume the same snapshot exposed to operators., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/dataset_store.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/worktrees.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py, AST and evidence records are reused by blob hash and only changed files are reparsed., Deleted and renamed files invalidate stale evidence deterministically., Clean worktrees and dependency setups can be pooled without sharing task-local mutations., Cold and warm paths produce equivalent plans and validation results with measured warm-path savings., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py -q, data/refactor_supervisor/discovery/2026-07-23-ref-316-objective-validation-repair.md, objective validation repair
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py -q

## G11 Make agent-supervisor proof-aware and context-efficient

- Status: active
- Priority: P0
- Bundle: refactor/g11
- Goal: Make agent-supervisor proof-aware and context-efficient
- Evidence: ipfs_datasets_py/ipfs_accelerate_py/docs/architecture/AGENT_SUPERVISOR_FORMAL_VERIFICATION_PLAN.md, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_contracts.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/code_proof_obligations.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_cache.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_completion.py, data/refactor_supervisor/discovery/2026-07-23-ref-325-objective-validation-repair.md, objective validation repair
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_capabilities.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_contracts.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_provider.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_policy.py -q

## G11.S1 Establish proof contracts, capabilities, and trust policy

- Status: active
- Parent: G11
- Priority: P0
- Bundle: refactor/g11/g11-s1
- Goal: Establish proof contracts, capabilities, and trust policy
- Evidence: ipfs_datasets_py/ipfs_accelerate_py/docs/architecture/AGENT_SUPERVISOR_FORMAL_VERIFICATION_PLAN.md, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_capabilities.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_capabilities.py, A versioned capability report covers Hammer, TDFOL, external provers, Lean, Leanstral, frame logic, knowledge graphs, and ZKP backends., Provider, executable, package, model, circuit, and optional dependency health are reported separately., Missing spaCy, model weights, Python bindings, or prover executables produce explicit degraded or unavailable reasons without breaking supervisor import., Capability probes are bounded, cacheable, and never count availability as proof success., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_capabilities.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_contracts.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_contracts.py, CodeProofObligation, ProofPlan, ProofAttempt, ProofReceipt, and assurance enums have deterministic JSON encodings and content identities., Receipts bind repository trees, AST scopes, premises, translators, solvers, kernels, toolchains, policy, and resource budgets., Authoritative assurance is derived from evidence and cannot be asserted directly by a provider., LLM output, ATP or SMT candidates, stale cache entries, and simulated ZKP cannot become kernel-verified or attested., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_contracts.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_provider.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_provider.py, A versioned provider protocol supports capability, translate, prove, reconstruct, verify, and attest operations., Providers can be discovered lazily in process or invoked through a bounded subprocess JSON protocol., Timeout, cancellation, resource, network, and malformed-response failures are explicit and fail closed., The supervisor imports and runs with no ipfs_datasets_py proof provider installed., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_provider.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_policy.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_policy.py, Policy maps changed paths, AST scopes, risk, and invariant classes to required assurance and fallback validation., Disabled, shadow, canary, and enforcement modes have explicit promotion and override behavior., Unsupported, unavailable, timed-out, and inconclusive results cannot silently satisfy an enforcement gate., Overrides require bounded scope, actor, reason, expiration, and a durable receipt., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_policy.py -q, data/refactor_supervisor/discovery/2026-07-23-ref-307-objective-validation-repair.md, objective validation repair
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_capabilities.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_contracts.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_provider.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_policy.py -q

## G11.S2 Compile AST changes into obligations and bounded graph context

- Status: active
- Parent: G11
- Priority: P0
- Bundle: refactor/g11/g11-s2
- Goal: Compile AST changes into obligations and bounded graph context
- Evidence: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/code_proof_obligations.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/conflict_graph.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_code_proof_scopes.py, Python diffs produce qualified symbols, imports, calls, state transitions, interfaces, source hashes, and changed-path scopes., Renames, deletes, generated files, syntax failures, and non-Python changes have explicit conservative handling., Scopes reuse existing AST and conflict-graph records by blob identity., Equivalent cold and warm scans produce the same canonical scope identities., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_code_proof_scopes.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_obligation_templates.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_obligation_templates.py, Initial templates cover legal state transitions, lease uniqueness and fencing, DAG acyclicity, merge idempotence, cache-key completeness, evidence freshness, projection equivalence, and unsupported-proof fail-closed behavior., Every template declares a Python reference predicate, canonical statement, supported backends, assumptions, mutation cases, and fallback tests., Template versions and semantic hashes participate in obligation and cache identity., Unknown or ambiguous code shapes remain unsupported instead of selecting a similar template heuristically., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_obligation_templates.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/code_evidence_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/artifact_store.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_code_evidence_graph.py, The graph uses deterministic nodes and provenance edges derived from AST, task, validation, merge, and proof records., Paired JSON and DuckDB artifacts expose indexed task, tree, symbol, obligation, assurance, freshness, and dependency queries., JSON and DuckDB projections round-trip to equivalent canonical graph records., LLM or GraphRAG enrichment cannot create authoritative proof, merge, coverage, or completion edges., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_code_evidence_graph.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_scope_index.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/dataset_store.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_scope_index.py, Scope indexes map files, qualified symbols, interfaces, assumptions, templates, toolchains, and policies to dependent obligations and receipts., Blob reuse avoids reparsing unchanged scopes while deletes and renames invalidate stale records., Invalidation is transitive across proof-plan dependencies and records a bounded reason chain., Incremental and exhaustive rebuilds produce equivalent active evidence sets., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_scope_index.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_context.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_context.py, Context queries select exact task, symbol, dependency, obligation, receipt, and contradiction neighborhoods., Row, byte, token, graph-hop, source-excerpt, and proof-transcript limits are enforced before prompt assembly., Capsules distinguish trusted facts, untrusted suggestions, unsupported semantics, and required fallback checks., Repository-wide AST records, full graphs, hidden witnesses, and unrelated transcripts never enter a capsule., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_context.py -q, data/refactor_supervisor/discovery/2026-07-23-ref-308-objective-validation-repair.md, objective validation repair
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_code_proof_scopes.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_obligation_templates.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_code_evidence_graph.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_scope_index.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_context.py -q

## G11.S3 Integrate Hammer, kernel reconstruction, and trusted caching

- Status: active
- Parent: G11
- Priority: P0
- Bundle: refactor/g11/g11-s3
- Goal: Integrate Hammer, kernel reconstruction, and trusted caching
- Evidence: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/ipfs_datasets_logic_provider.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_provider.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_ipfs_datasets_logic_provider.py, Supported obligations translate deterministically into Hammer requests with explicit premises and environment locks., Solver allowlists, timeouts, CPU, memory, network denial, and maximum premise counts flow from supervisor policy., Portfolio attempts and candidate proofs preserve upstream receipt provenance., Unsupported translation families return a typed unsupported result and configured fallback checks., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_ipfs_datasets_logic_provider.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_cache.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_cache.py, Cache keys bind obligation, premises, translator, solver, kernel, toolchain, theorem registry, policy, resource budget, and candidate tree., Only results meeting the requested assurance and freshness can satisfy a lookup., A cross-thread and cross-process single-flight lease deduplicates active proof work., Poisoned, malformed, stale, partial, solver-only, and simulated-attestation cache entries are rejected with reason codes., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_cache.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/kernel_verification.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_contracts.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_kernel_verification.py, Lean, Coq, and Isabelle reconstruction records are mapped without weakening upstream trust semantics., Kernel unavailability, timeout, mismatch, forbidden declarations, sorry or admit, and changed theorem statements fail closed., The authoritative verdict is derived from reconstruction evidence and cannot be upgraded by provider status text., Negative and corrupt proof fixtures never produce kernel-verified receipts., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_kernel_verification.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_fallbacks.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_commands.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_fallbacks.py, Counterexamples and unsat cores are normalized into bounded task diagnostics and regression fixtures., Unsupported obligations map to declared focused tests, static checks, or manual-review requirements., Shadow mode can continue through fallback validation while enforcement mode honors required assurance., Repeated equivalent failures deduplicate by obligation, tree, and counterexample identity., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_fallbacks.py -q, data/refactor_supervisor/discovery/2026-07-23-ref-309-objective-validation-repair.md, objective validation repair
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_ipfs_datasets_logic_provider.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_cache.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_kernel_verification.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_fallbacks.py -q

## G11.S4 Schedule proof work under shared CPU budgets

- Status: active
- Parent: G11
- Priority: P0
- Bundle: refactor/g11/g11-s4
- Goal: Schedule proof work under shared CPU budgets
- Evidence: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_contracts.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_scheduler.py, The scheduler executes ready proof-plan nodes in dependency order and exposes critical-path and downstream-unlock priority., Independent translator, solver, kernel, validation, and artifact nodes can overlap within configured limits., Conclusive results cancel redundant portfolio attempts and propagate blocked or unsupported dependencies explicitly., Restarts recover from durable plan, lease, attempt, and receipt state without duplicate authoritative receipts., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_scheduler.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/resource_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_resource_scheduler.py, Resource classes distinguish translation, solver, kernel, validation, model-draft, and artifact work., One supervisor-level lease budget is propagated into child portfolio and kernel limits., CPU, process, memory, disk, provider quota, context, token, and latency backpressure remain authoritative., Model concurrency is accounted separately from CPU proof concurrency and idle capacity is reclaimable., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_resource_scheduler.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_commands.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_validation_scheduler.py, Cheap deterministic checks precede translation, solver candidates, kernel reconstruction, focused tests, and broad tests., Independent checks run in parallel under the shared resource budget., Impact selection explains every included, omitted, escalated, and fallback check., Validation reports retain separate deterministic, solver, kernel, test, and attestation verdicts., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_validation_scheduler.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_metrics.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/artifact_store.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scheduler_metrics.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_metrics.py, JSON and DuckDB tables expose obligations, attempts, receipts, dependencies, cache outcomes, resource samples, and assurance counts., Metrics include queue, solver, kernel, model, validation, merge, cancellation, and cache latency., Every metric is keyed by canonical goal, subgoal, task, tree, provider, template, and resource class., Queryable aggregates do not include hidden witnesses or unbounded proof transcripts., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_metrics.py -q, data/refactor_supervisor/discovery/2026-07-23-ref-310-objective-validation-repair.md, objective validation repair
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_scheduler.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_resource_scheduler.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_validation_scheduler.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_metrics.py -q

## G11.S7 Enforce proof-aware merge and goal completion

- Status: active
- Parent: G11
- Priority: P0
- Bundle: refactor/g11/g11-s7
- Goal: Enforce proof-aware merge and goal completion
- Evidence: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/goal_completion.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_contracts.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_goal_completion.py, CompletionEvidence can reference obligation, proof receipt, assurance, tree, freshness, and provenance identities., Required assurance is evaluated independently from validation success and task status., Parent goals aggregate child proof requirements without hiding unsupported, inconclusive, stale, or contradicted descendants., Legacy evidence remains readable but cannot be optimistically upgraded., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_goal_completion.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_train.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_policy.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_merge_gate.py, Changed scopes select proof requirements, fallback checks, and rollout mode deterministically., Shadow records outcomes, canary blocks configured paths, and enforcement fails closed for missing required assurance., The merge receipt identifies the exact proof plan, receipts, validations, policy, tree, and any operator override., Retries reuse valid cache evidence and do not weaken policy after a timeout or provider failure., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_merge_gate.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_task_janitor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_scope_index.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_invalidation.py, Transitive invalidation records the changed input, affected obligations, receipts, criteria, goals, and source tree., Affected provisional or verified goals reopen deterministically while unrelated goals remain stable., Repeated identical invalidations are idempotent and historical receipts remain auditable., Replacement tasks retain dependency and conflict edges to the invalidated scope., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_invalidation.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_context.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_aware_planning.py, Plan candidates declare obligation impact, required assurance, proof cost, cache likelihood, dependencies, and expected evidence delta., Priority accounts for proof critical path, downstream unlock value, risk, freshness, and available resource classes., The router receives only a bounded proof context capsule and rejected alternatives retain rationale., Unsupported or failed obligations generate finite template, test, premise, or manual-review work with semantic deduplication., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_aware_planning.py -q, data/refactor_supervisor/discovery/2026-07-23-ref-311-objective-validation-repair.md, objective validation repair
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_goal_completion.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_merge_gate.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_invalidation.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_aware_planning.py -q
