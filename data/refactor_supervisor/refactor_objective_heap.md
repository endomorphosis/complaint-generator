# Complaint Generator Refactor Objective Heap

Ultimate objective: Refactor complaint-generator safely and incrementally while preserving behavior.

## G1 Stabilize repository boundaries

- Status: active
- Priority: P0
- Bundle: refactor/g1
- Goal: Stabilize repository boundaries
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, mediator/mediator.py, applications/complaint_workspace.py, tests/test_claim_support_review_playwright_smoke.py, docs/ARCHITECTURE.md, pyproject.toml, applications/document_api.py, integrations/ipfs_datasets/loader.py, applications/complaint_cli.py
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
- Evidence: applications/complaint_workspace.py, applications/document_api.py, integrations/ipfs_datasets/loader.py, scripts/agentic_complaint_evidence_scraper.py, scripts/agentic_scraper_cli.py, scripts/backfill_claim_testimony_links.py, scripts/check_hacc_routers.py, scripts/enrich_email_timeline_authorities.py, scripts/generate_decision_trees.py, scripts/generate_email_search_plan.py, scripts/generate_hacc_email_seed_plan.py, scripts/gmail_duckdb_daemon.py, No production entrypoint mutates sys.path for normal imports., Explicit exceptions are isolated to scripts/tests., python -m pytest tests/test_package_imports.py -q, applications/complaint_cli.py, applications/complaint_workspace.py, Production direct imports are replaced or documented., Degraded mode still imports cleanly., python -m pytest tests/test_ipfs_adapter_layer.py -q
- Validation: python -m pytest tests/test_package_imports.py -q, python -m pytest tests/test_ipfs_adapter_layer.py -q

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
- Validation: python -m pytest tests/test_mediator.py tests/test_mediator_three_phase.py -q, python -m pytest tests/test_claim_support_hooks.py tests/test_claim_support_review_dashboard_flow.py -q

## G2.S2 Reduce application surface coupling

- Status: active
- Parent: G2
- Priority: P0
- Bundle: refactor/g2/g2-s2
- Goal: Reduce application surface coupling
- Evidence: applications/complaint_workspace.py, One handler group is isolated., Routes keep the same response shape., python -m pytest tests/test_review_api.py -q, applications/dashboard_ui.py, playwright/server.js, Fixture builders are named and reusable., Playwright smoke tests remain stable., python -m pytest tests/test_claim_support_review_playwright_smoke.py -q
- Validation: python -m pytest tests/test_review_api.py -q, python -m pytest tests/test_claim_support_review_playwright_smoke.py -q

## G3 Harden adapter contracts and degraded mode

- Status: active
- Priority: P0
- Bundle: refactor/g3
- Goal: Harden adapter contracts and degraded mode
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, integrations/ipfs_datasets/capabilities.py, integrations/ipfs_datasets/loader.py, integrations/ipfs_datasets/documents.py, mediator/evidence_hooks.py, integrations/ipfs_datasets/graphs.py, complaint_phases/knowledge_graph.py, integrations/ipfs_datasets/logic.py, lib/formal_logic
- Validation: python -m pytest --collect-only -q

## G3.S1 Normalize IPFS datasets adapter payloads

- Status: active
- Parent: G3
- Priority: P0
- Bundle: refactor/g3/g3-s1
- Goal: Normalize IPFS datasets adapter payloads
- Evidence: integrations/ipfs_datasets/capabilities.py, integrations/ipfs_datasets/loader.py, All adapter groups report stable keys., Missing optional extras produce actionable reasons., python -m pytest tests/test_ipfs_adapter_layer.py -q, integrations/ipfs_datasets/documents.py, mediator/evidence_hooks.py, Evidence, authority, and web ingestion can call one parse contract., Fallback mode preserves current behavior., python -m pytest tests/test_document_pipeline.py tests/test_document_pipeline_fallbacks.py -q
- Validation: python -m pytest tests/test_ipfs_adapter_layer.py -q, python -m pytest tests/test_document_pipeline.py tests/test_document_pipeline_fallbacks.py -q

## G3.S2 Clarify graph, GraphRAG, and logic adapter boundaries

- Status: active
- Parent: G3
- Priority: P0
- Bundle: refactor/g3/g3-s2
- Goal: Clarify graph, GraphRAG, and logic adapter boundaries
- Evidence: integrations/ipfs_datasets/graphs.py, complaint_phases/knowledge_graph.py, Interfaces specify persistence, query, and provenance fields., Fallback graph behavior remains covered., python -m pytest tests/test_complaint_phases.py tests/test_ipfs_adapter_layer.py -q, integrations/ipfs_datasets/logic.py, lib/formal_logic, Logic status distinguishes unavailable, degraded, and implemented., Callers do not branch on fragile strings., python -m pytest tests/test_symbolicai_logic_dependency.py tests/test_ipld_logic_storage_dependency.py -q
- Validation: python -m pytest tests/test_complaint_phases.py tests/test_ipfs_adapter_layer.py -q, python -m pytest tests/test_symbolicai_logic_dependency.py tests/test_ipld_logic_storage_dependency.py -q

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
- Evidence: pytest.ini, Makefile, docs/VERIFICATION_SUMMARY.md, A documented test lane map exists., Each P0 workstream has a named validation command., python -m pytest --collect-only -q, tests, pyproject.toml, Tests catch direct production imports where adapters are required., Tests avoid blocking intentional test-only imports., python -m pytest tests/test_package_imports.py -q
- Validation: python -m pytest --collect-only -q, python -m pytest tests/test_package_imports.py -q

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
- Validation: python scripts/refactor_agent_supervisor.py seed --once, python scripts/refactor_agent_supervisor.py status

## G6 Pay down error-handling and observability debt

- Status: active
- Priority: P1
- Bundle: refactor/g6
- Goal: Pay down error-handling and observability debt
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, mediator/mediator.py, mediator/evidence_hooks.py, integrations/ipfs_datasets/search.py, applications/ui_review.py, complaint_generator/ui_optimizer_daemon.py, mediator/state.py, integrations/ipfs_datasets/scraper_daemon.py, scripts/gmail_duckdb_daemon.py, docs/OBSERVABILITY_INDEX.md, docs/observability/TROUBLESHOOTING.md
- Validation: python -m pytest --collect-only -q

## G6.S1 Replace silent failures with typed outcomes

- Status: active
- Parent: G6
- Priority: P1
- Bundle: refactor/g6/g6-s1
- Goal: Replace silent failures with typed outcomes
- Evidence: mediator/mediator.py, mediator/evidence_hooks.py, integrations/ipfs_datasets/search.py, Top production broad-exception clusters are documented., At least one cluster returns a typed degraded result., python -m pytest tests/test_mediator.py tests/test_ipfs_adapter_layer.py -q, applications/ui_review.py, complaint_generator/ui_optimizer_daemon.py, mediator/state.py, Intentional ignores are named., Unexpected failures leave diagnostic breadcrumbs., python -m pytest tests/test_ui_optimizer_daemon_cli.py tests/test_review_api.py -q
- Validation: python -m pytest tests/test_mediator.py tests/test_ipfs_adapter_layer.py -q, python -m pytest tests/test_ui_optimizer_daemon_cli.py tests/test_review_api.py -q

## G6.S2 Unify runtime status payloads

- Status: active
- Parent: G6
- Priority: P1
- Bundle: refactor/g6/g6-s2
- Goal: Unify runtime status payloads
- Evidence: complaint_generator/ui_optimizer_daemon.py, integrations/ipfs_datasets/scraper_daemon.py, scripts/gmail_duckdb_daemon.py, Status payloads include status, pid, updated_at, artifacts, and last_error where applicable., Existing CLI tests remain compatible., python -m pytest tests/test_ui_optimizer_daemon_cli.py tests/test_gmail_duckdb_daemon_cli.py -q, docs/OBSERVABILITY_INDEX.md, docs/observability/TROUBLESHOOTING.md, Docs explain where to find pid, log, status, and queue files., Troubleshooting includes stale running task recovery., python scripts/refactor_agent_supervisor.py status
- Validation: python -m pytest tests/test_ui_optimizer_daemon_cli.py tests/test_gmail_duckdb_daemon_cli.py -q, python scripts/refactor_agent_supervisor.py status

## G7 Rationalize frontend and review surfaces

- Status: active
- Priority: P1
- Bundle: refactor/g7
- Goal: Rationalize frontend and review surfaces
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, applications/review_api.py, applications/ui_review.py, mediator/claim_support_hooks.py, tests/test_claim_support_review_playwright_smoke.py, tests/test_review_surface_site_playwright.py
- Validation: python -m pytest --collect-only -q

## G7.S1 Separate review API contracts from display assembly

- Status: active
- Parent: G7
- Priority: P1
- Bundle: refactor/g7/g7-s1
- Goal: Separate review API contracts from display assembly
- Evidence: applications/review_api.py, applications/ui_review.py, mediator/claim_support_hooks.py, DTO helpers cover coverage, follow-up, and support-path summaries., Route response snapshots stay stable., python -m pytest tests/test_review_api.py tests/test_claim_support_review_dashboard_flow.py -q, tests/test_claim_support_review_playwright_smoke.py, tests/test_review_surface_site_playwright.py, Shared builders remove repeated setup., Screenshots still render with representative support states., python -m pytest tests/test_claim_support_review_playwright_smoke.py tests/test_review_surface_site_playwright.py -q
- Validation: python -m pytest tests/test_review_api.py tests/test_claim_support_review_dashboard_flow.py -q, python -m pytest tests/test_claim_support_review_playwright_smoke.py tests/test_review_surface_site_playwright.py -q

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
- Validation: python scripts/refactor_agent_supervisor.py seed --once, python scripts/refactor_agent_supervisor.py status

## G8.S2 Keep generated artifacts reviewable

- Status: active
- Parent: G8
- Priority: P0
- Bundle: refactor/g8/g8-s2
- Goal: Keep generated artifacts reviewable
- Evidence: scripts/refactor_agent_supervisor.py, Status output or a new command lists next tasks by priority., Output is stable enough for automation., python scripts/refactor_agent_supervisor.py status, tests/test_refactor_agent_supervisor.py, scripts/refactor_agent_supervisor.py, Running seed twice does not duplicate active tasks., Payloads include goal, subgoal, priority, acceptance, and validation., python -m pytest tests/test_refactor_agent_supervisor.py -q
- Validation: python scripts/refactor_agent_supervisor.py status, python -m pytest tests/test_refactor_agent_supervisor.py -q
