# Complaint Generator Refactor Objective Heap

Ultimate objective: Refactor complaint-generator safely and incrementally while preserving behavior.

## G1 Stabilize repository boundaries

- Status: completed
- Priority: P0
- Bundle: refactor/g1
- Goal: Stabilize repository boundaries
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, mediator/mediator.py, applications/complaint_workspace.py, tests/test_claim_support_review_playwright_smoke.py, docs/ARCHITECTURE.md, pyproject.toml, scripts/graphrag_email_manifest.py, scripts/import_gmail_evidence.py, scripts/import_local_eml_directory.py, applications/complaint_cli.py, applications/dashboard_ui.py
- Validation: python -m pytest --collect-only -q
- Completed at: 2026-07-22T00:32:40.179493+00:00
- Completion evidence: docs/ARCHITECTURE.md => docs/ARCHITECTURE.md (path), DOCUMENTATION_INDEX.md (exact), README.md (exact); docs/REFACTOR_SUPERVISOR_TASKBOARD.md => docs/REFACTOR_SUPERVISOR_TASKBOARD.md (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/complainant.py (ast); mediator/mediator.py => mediator/mediator.py (path), .github/workflows/claim-support-regression.yml (exact), .github/workflows/standard-regression.yml (exact); applications/complaint_workspace.py => applications/complaint_workspace.py (path), .complaint_workspace/sessions/demo-user.json (embedding:0.31), .github/workflows/claim-support-regression.yml (exact); tests/test_claim_support_review_playwright_smoke.py => tests/test_claim_support_review_playwright_smoke.py (path), .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast); pyproject.toml => pyproject.toml (path), .github/workflows/claim-support-regression.yml (exact), .github/workflows/standard-regression.yml (exact); scripts/graphrag_email_manifest.py => scripts/graphrag_email_manifest.py (path), complaint_generator/email_agentic_search.py (embedding:0.64), complaint_generator/email_graphrag.py (embedding:0.59); scripts/import_gmail_evidence.py => scripts/import_gmail_evidence.py (path), .complaint_workspace/sessions/alias-script-user.json (ast), .complaint_workspace/sessions/demo-user.json (ast); scripts/import_local_eml_directory.py => scripts/import_local_eml_directory.py (path), adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast); applications/complaint_cli.py => applications/complaint_cli.py (path), .complaint_workspace/sessions/demo-user.json (embedding:0.32), .github/workflows/claim-support-regression.yml (exact); applications/dashboard_ui.py => applications/dashboard_ui.py (path), .github/workflows/claim-support-regression.yml (embedding:0.39), .github/workflows/standard-regression.yml (embedding:0.43)
- Completion validation: 0

## G1.S1 Map package ownership and runtime entrypoints

- Status: completed
- Parent: G1
- Priority: P0
- Bundle: refactor/g1/g1-s1
- Goal: Map package ownership and runtime entrypoints
- Evidence: mediator/mediator.py, applications/complaint_workspace.py, tests/test_claim_support_review_playwright_smoke.py, scripts/synthesize_hacc_complaint.py, tests/test_review_api.py, complaint_phases/denoiser.py, A short module ownership map exists., Entrypoints are grouped by CLI, web, mediator, and workflow role., python -m pytest tests/test_package_imports.py -q, docs/ARCHITECTURE.md, pyproject.toml, Architecture docs identify allowed imports., New work has a simple rule for where shared code belongs., python -m pytest tests/test_package_imports.py -q
- Validation: python -m pytest tests/test_package_imports.py -q
- Completed at: 2026-07-22T00:32:40.179493+00:00
- Completion evidence: mediator/mediator.py => mediator/mediator.py (path), .github/workflows/claim-support-regression.yml (exact), .github/workflows/standard-regression.yml (exact); applications/complaint_workspace.py => applications/complaint_workspace.py (path), .complaint_workspace/sessions/demo-user.json (embedding:0.31), .github/workflows/claim-support-regression.yml (exact); tests/test_claim_support_review_playwright_smoke.py => tests/test_claim_support_review_playwright_smoke.py (path), .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast); scripts/synthesize_hacc_complaint.py => scripts/synthesize_hacc_complaint.py (path), .github/workflows/hacc-unit-regression.yml (exact), .vscode/launch.json (embedding:0.37); tests/test_review_api.py => tests/test_review_api.py (path), .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast); complaint_phases/denoiser.py => complaint_phases/denoiser.py (path), .github/workflows/claim-support-regression.yml (embedding:0.45), .github/workflows/standard-regression.yml (embedding:0.51); A short module ownership map exists. => .vscode/launch.json (ast), docs/LLM_ROUTER.md (ast), docs/REFACTOR_SUPERVISOR_TASKBOARD.md (exact); Entrypoints are grouped by CLI => .vscode/tasks.json (ast), adversarial_harness/complainant.py (ast), adversarial_harness/critic.py (ast); web => .complaint_workspace/sessions/did-key-web-inspect.json (exact), .vscode/tasks.json (exact), AUTONOMOUS_SESSION_REPORT.md (exact); mediator => mediator (path), .github/workflows/claim-support-regression.yml (exact), .github/workflows/standard-regression.yml (exact); and workflow role. => .complaint_workspace/sessions/demo-user.json (ast), docs/ARCHITECTURE.md (embedding:0.31), docs/CHRONOLOGY_FIRST_INTAKE_EVIDENCE_NEXT_BATCH_PLAN.md (ast); python -m pytest tests/test_package_imports.py -q => .github/workflows/claim-support-regression.yml (embedding:0.55), .github/workflows/standard-regression.yml (embedding:0.60), .vscode/tasks.json (embedding:0.37); docs/ARCHITECTURE.md => docs/ARCHITECTURE.md (path), DOCUMENTATION_INDEX.md (exact), README.md (exact); pyproject.toml => pyproject.toml (path), .github/workflows/claim-support-regression.yml (exact), .github/workflows/standard-regression.yml (exact); Architecture docs identify allowed imports. => .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast), .complaint_workspace/sessions/site-sdk-user2.json (ast); New work has a simple rule for where shared code belongs. => SESSION_84_FINAL_SUMMARY.md (ast), SESSION_SUMMARY_2026_02_24_COMPLETE.md (ast), adversarial_harness/complainant.py (ast)
- Completion validation: 0

## G1.S2 Remove ad hoc import path behavior from production surfaces

- Status: active
- Parent: G1
- Priority: P0
- Bundle: refactor/g1/g1-s2
- Goal: Remove ad hoc import path behavior from production surfaces
- Evidence: scripts/graphrag_email_manifest.py, scripts/import_gmail_evidence.py, scripts/import_local_eml_directory.py, scripts/master_case_email.py, scripts/process_hacc_pdfs_to_kg.py, scripts/run_gmail_duckdb_pipeline.py, scripts/run_hacc_adversarial_report.py, scripts/run_hacc_grounded_pipeline.py, scripts/run_hacc_preset_matrix.py, No production entrypoint mutates sys.path for normal imports., Explicit exceptions are isolated to scripts/tests., python -m pytest tests/test_package_imports.py -q, applications/complaint_cli.py, applications/complaint_workspace.py, applications/dashboard_ui.py, complaint_generator/agentic_evidence_download.py, complaint_generator/data_migration.py, complaint_generator/email_agentic_search.py, complaint_generator/email_authority_enrichment.py, complaint_generator/email_credentials.py, complaint_generator/email_graphrag.py, Production direct imports are replaced or documented., Degraded mode still imports cleanly., python -m pytest tests/test_ipfs_adapter_layer.py -q
- Validation: python -m pytest tests/test_package_imports.py -q, python -m pytest tests/test_ipfs_adapter_layer.py -q

## G2 Decompose oversized orchestration modules

- Status: completed
- Priority: P0
- Bundle: refactor/g2
- Goal: Decompose oversized orchestration modules
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, mediator/mediator.py, mediator/__init__.py, mediator/claim_support_hooks.py, applications/complaint_workspace.py, applications/dashboard_ui.py, playwright/server.js
- Validation: python -m pytest --collect-only -q
- Completed at: 2026-07-22T00:32:40.179493+00:00
- Completion evidence: docs/ARCHITECTURE.md => docs/ARCHITECTURE.md (path), DOCUMENTATION_INDEX.md (exact), README.md (exact); docs/REFACTOR_SUPERVISOR_TASKBOARD.md => docs/REFACTOR_SUPERVISOR_TASKBOARD.md (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/complainant.py (ast); mediator/mediator.py => mediator/mediator.py (path), .github/workflows/claim-support-regression.yml (exact), .github/workflows/standard-regression.yml (exact); mediator/__init__.py => mediator/__init__.py (path), .github/workflows/claim-support-regression.yml (embedding:0.54), .github/workflows/standard-regression.yml (exact); mediator/claim_support_hooks.py => mediator/claim_support_hooks.py (path), .github/workflows/claim-support-regression.yml (exact), .github/workflows/standard-regression.yml (exact); applications/complaint_workspace.py => applications/complaint_workspace.py (path), .complaint_workspace/sessions/demo-user.json (embedding:0.31), .github/workflows/claim-support-regression.yml (exact); applications/dashboard_ui.py => applications/dashboard_ui.py (path), .github/workflows/claim-support-regression.yml (embedding:0.39), .github/workflows/standard-regression.yml (embedding:0.43); playwright/server.js => playwright/server.js (path), TESTING.md (exact), applications/launcher.py (ast)
- Completion validation: 0

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

- Status: completed
- Priority: P0
- Bundle: refactor/g3
- Goal: Harden adapter contracts and degraded mode
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, integrations/ipfs_datasets/capabilities.py, integrations/ipfs_datasets/loader.py, integrations/ipfs_datasets/documents.py, mediator/evidence_hooks.py, integrations/ipfs_datasets/graphs.py, complaint_phases/knowledge_graph.py, integrations/ipfs_datasets/logic.py, lib/formal_logic
- Validation: python -m pytest --collect-only -q
- Completed at: 2026-07-22T00:32:40.179493+00:00
- Completion evidence: docs/ARCHITECTURE.md => docs/ARCHITECTURE.md (path), DOCUMENTATION_INDEX.md (exact), README.md (exact); docs/REFACTOR_SUPERVISOR_TASKBOARD.md => docs/REFACTOR_SUPERVISOR_TASKBOARD.md (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/complainant.py (ast); integrations/ipfs_datasets/capabilities.py => integrations/ipfs_datasets/capabilities.py (path), SESSION_84_FINAL_SUMMARY.md (ast), TODO.md (embedding:0.31); integrations/ipfs_datasets/loader.py => integrations/ipfs_datasets/loader.py (path), P3_INFRASTRUCTURE_COMPLETION_SESSION.md (embedding:0.54), P3_SESSION_4_INFRASTRUCTURE_SUMMARY.md (embedding:0.33); integrations/ipfs_datasets/documents.py => integrations/ipfs_datasets/documents.py (path), .complaint_workspace/sessions/alias-script-user.json (ast), .complaint_workspace/sessions/demo-user.json (ast); mediator/evidence_hooks.py => mediator/evidence_hooks.py (path), .complaint_workspace/sessions/alias-script-user.json (ast), .complaint_workspace/sessions/demo-user.json (ast); integrations/ipfs_datasets/graphs.py => integrations/ipfs_datasets/graphs.py (path), BATCH_328_API_RETURN_TYPES_SUMMARY.md (embedding:0.33), DOCUMENTATION_INDEX.md (embedding:0.56); complaint_phases/knowledge_graph.py => complaint_phases/knowledge_graph.py (path), AUTONOMOUS_SESSION_REPORT.md (embedding:0.30), BATCH_328_API_RETURN_TYPES_SUMMARY.md (embedding:0.32); integrations/ipfs_datasets/logic.py => integrations/ipfs_datasets/logic.py (path), BATCH_328_API_RETURN_TYPES_SUMMARY.md (embedding:0.33), DOCUMENTATION_INDEX.md (embedding:0.57); lib/formal_logic => lib/formal_logic (path), adversarial_harness/search_hooks.py (ast), complaint_phases/deontic_logic.py (embedding:0.65)
- Completion validation: 0

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

- Status: completed
- Priority: P1
- Bundle: refactor/g4
- Goal: Improve validation speed and confidence
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, pytest.ini, Makefile, docs/VERIFICATION_SUMMARY.md, tests, pyproject.toml
- Validation: python -m pytest --collect-only -q
- Completed at: 2026-07-22T00:32:40.179493+00:00
- Completion evidence: docs/ARCHITECTURE.md => docs/ARCHITECTURE.md (path), DOCUMENTATION_INDEX.md (exact), README.md (exact); docs/REFACTOR_SUPERVISOR_TASKBOARD.md => docs/REFACTOR_SUPERVISOR_TASKBOARD.md (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/complainant.py (ast); pytest.ini => pytest.ini (path), .github/workflows/claim-support-regression.yml (exact), .github/workflows/hacc-unit-regression.yml (exact); Makefile => Makefile (path), .github/workflows/standard-regression.yml (exact), README.md (exact); docs/VERIFICATION_SUMMARY.md => docs/VERIFICATION_SUMMARY.md (path), .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast); tests => tests (path), .github/pull_request_template.md (exact), .github/workflows/claim-support-regression.yml (exact); pyproject.toml => pyproject.toml (path), .github/workflows/claim-support-regression.yml (exact), .github/workflows/standard-regression.yml (exact)
- Completion validation: 0

## G4.S1 Create focused test lanes for refactor work

- Status: active
- Parent: G4
- Priority: P1
- Bundle: refactor/g4/g4-s1
- Goal: Create focused test lanes for refactor work
- Evidence: pytest.ini, Makefile, docs/VERIFICATION_SUMMARY.md, A documented test lane map exists., Each P0 workstream has a named validation command., python -m pytest --collect-only -q, tests, pyproject.toml, Tests catch direct production imports where adapters are required., Tests avoid blocking intentional test-only imports., python -m pytest tests/test_package_imports.py -q
- Validation: python -m pytest --collect-only -q, python -m pytest tests/test_package_imports.py -q

## G5 Make automation observable and refillable

- Status: completed
- Priority: P0
- Bundle: refactor/g5
- Goal: Make automation observable and refillable
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, scripts/refactor_agent_supervisor.py, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, data/refactor_supervisor
- Validation: python -m pytest --collect-only -q
- Completed at: 2026-07-22T00:32:40.179493+00:00
- Completion evidence: docs/ARCHITECTURE.md => docs/ARCHITECTURE.md (path), DOCUMENTATION_INDEX.md (exact), README.md (exact); docs/REFACTOR_SUPERVISOR_TASKBOARD.md => docs/REFACTOR_SUPERVISOR_TASKBOARD.md (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/complainant.py (ast); scripts/refactor_agent_supervisor.py => scripts/refactor_agent_supervisor.py (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/complainant.py (ast); data/refactor_supervisor => data/refactor_supervisor (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/complainant.py (ast)
- Completion validation: 0

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

- Status: completed
- Priority: P0
- Bundle: refactor/g8
- Goal: Prepare incremental implementation slices
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, data/refactor_supervisor/refactor_goals.json, scripts/refactor_agent_supervisor.py, tests/test_refactor_agent_supervisor.py
- Validation: python -m pytest --collect-only -q
- Completed at: 2026-07-22T00:32:40.179493+00:00
- Completion evidence: docs/ARCHITECTURE.md => docs/ARCHITECTURE.md (path), DOCUMENTATION_INDEX.md (exact), README.md (exact); docs/REFACTOR_SUPERVISOR_TASKBOARD.md => docs/REFACTOR_SUPERVISOR_TASKBOARD.md (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/complainant.py (ast); docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md => docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md (path), BATCH_305_306_SESSION_SUMMARY.md (embedding:0.42), DOCUMENTATION_INDEX.md (exact); data/refactor_supervisor/refactor_goals.json => data/refactor_supervisor/refactor_goals.json (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/complainant.py (ast); scripts/refactor_agent_supervisor.py => scripts/refactor_agent_supervisor.py (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/complainant.py (ast); tests/test_refactor_agent_supervisor.py => .complaint_workspace/sessions/demo-user.json (ast), .github/workflows/standard-regression.yml (embedding:0.64), SESSION_SUMMARY_2026_02_24_COMPLETE.md (ast)
- Completion validation: 0

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

## G9 Increase agent-supervisor planning quality and throughput

- Status: completed
- Priority: P0
- Bundle: refactor/g9
- Goal: Increase agent-supervisor planning quality and throughput
- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_identity.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_queue.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_train.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_resolver.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/conflict_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/resource_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_commands.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scheduler_metrics.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/event_log.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/supervisor_watchdog.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/dataset_store.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/worktrees.py
- Validation: python -m pytest --collect-only -q
- Completed at: 2026-07-22T00:32:40.179493+00:00
- Completion evidence: docs/ARCHITECTURE.md => docs/ARCHITECTURE.md (path), DOCUMENTATION_INDEX.md (exact), README.md (exact); docs/REFACTOR_SUPERVISOR_TASKBOARD.md => docs/REFACTOR_SUPERVISOR_TASKBOARD.md (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/complainant.py (ast); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_identity.py => ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_identity.py (path), .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py => ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py (path), .complaint_workspace/sessions/demo-user.json (ast), AUTONOMOUS_SESSION_REPORT.md (ast); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py => ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py (path), .complaint_workspace/sessions/demo-user.json (ast), complaint_generator/local_evidence_import.py (ast); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py => ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py (path), .complaint_workspace/sessions/demo-user.json (ast), docs/FEATURE_WIRING_MATRIX.json (ast); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py => ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py (path), .complaint_workspace/sessions/demo-user.json (ast), docs/FEATURE_WIRING_MATRIX.json (ast); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_queue.py => ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_queue.py (path), .complaint_workspace/sessions/demo-user.json (ast), applications/ui_review.py (ast); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_train.py => .complaint_workspace/sessions/demo-user.json (ast), docs/ARCHITECTURE.md (embedding:0.31), docs/DOCUMENT_GENERATION_AGENTIC_OPTIMIZATION_PLAN.md (embedding:0.65); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_resolver.py => ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_resolver.py (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/complainant.py (ast); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/conflict_graph.py => .complaint_workspace/sessions/demo-user.json (ast), docs/FEATURE_WIRING_MATRIX.json (ast), docs/FEATURE_WIRING_MATRIX.md (embedding:0.58); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py => ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/demo_autopatch.py (ast); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py => .complaint_workspace/sessions/demo-user.json (ast), docs/FEATURE_WIRING_MATRIX.json (ast), docs/HACC_VS_IPFS_DATASETS_QUICK.md (embedding:0.66); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py => ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py (path), .complaint_workspace/sessions/demo-user.json (ast), AUTONOMOUS_SESSION_REPORT.md (ast); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/resource_scheduler.py => .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast), .complaint_workspace/sessions/site-sdk-user2.json (ast); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_commands.py => ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_commands.py (path), .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_scheduler.py => .complaint_workspace/sessions/demo-user.json (ast), .complaint_workspace/sessions/site-sdk-user.json (ast), .complaint_workspace/sessions/site-sdk-user2.json (ast); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py => ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py (path), .complaint_workspace/sessions/demo-user.json (ast), SESSION_SUMMARY_2026_02_23.md (ast); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scheduler_metrics.py => .complaint_workspace/sessions/demo-user.json (ast), docs/ADVERSARIAL_IMPLEMENTATION_SUMMARY.md (ast), docs/FEATURE_WIRING_MATRIX.json (ast); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/event_log.py => ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/event_log.py (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/search_hooks.py (ast); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/supervisor_watchdog.py => ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/supervisor_watchdog.py (path), .complaint_workspace/sessions/demo-user.json (ast), docs/FEATURE_WIRING_MATRIX.json (ast); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/dataset_store.py => ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/dataset_store.py (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/complainant.py (ast); ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/worktrees.py => ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/worktrees.py (path), .complaint_workspace/sessions/demo-user.json (ast), adversarial_harness/complainant.py (ast)
- Completion validation: 0

## G9.S1 Establish canonical coordination and merge flow

- Status: active
- Parent: G9
- Priority: P0
- Bundle: refactor/g9/g9-s1
- Goal: Establish canonical coordination and merge flow
- Evidence: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_identity.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/persistent_task_queue.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py, Every task has a stable canonical key or CID independent of board path and display id., Legacy markdown tasks migrate idempotently with board namespace provenance., Branches, events, retries, cooldowns, leases, and receipts carry canonical identity., Refill cannot create a second active task for the same canonical work item., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/multi_supervisor_runner.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py, A persistent scheduler discovers new and refilled tasks without restart., Workers claim ready tasks, release drained or blocked leases, and steal conflict-safe work., Lane count remains within configured capacity and no task executes under two accepted leases., The manifest is an authoritative live projection rather than a launch-time snapshot., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_queue.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_train.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_resolver.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_merge_train.py, All implementation lanes enqueue merge candidates instead of racing the target checkout., The train deduplicates by canonical task and commit, rebases on the latest target, and preserves priority plus age fairness., One conflict fingerprint invokes at most one active resolver attempt., Bounded failures enter quarantine with a durable receipt instead of a polling retry loop., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_merge_train.py -q
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q, PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py -q, PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_merge_train.py -q

## G9.S2 Plan from dependencies, conflicts, and objective value

- Status: active
- Parent: G9
- Priority: P0
- Bundle: refactor/g9/g9-s2
- Goal: Plan from dependencies, conflicts, and objective value
- Evidence: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py, Goal, import, interface, output-input, migration, and validation prerequisites become explicit DAG edges with provenance., Only tasks whose prerequisite merge receipts succeeded are claimable., Priority includes critical-path length, slack, downstream unlock value, age, and configured objective priority., Cycles and missing dependencies produce bounded repair evidence rather than deadlock., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/conflict_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_vector_index.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py, Conflict surfaces include all predicted files, AST symbols, interfaces, submodules, and generated artifacts., Lane planning colors the conflict graph so overlapping tasks do not run concurrently unless explicitly allowed., Actual branch diffs and conflict receipts update future conflict weights., Planner output explains every co-location or separation decision., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py, Each eligible subgoal can produce multiple schema-validated plan branches through llm_router., Candidates declare predicted files and symbols, dependencies, validation proof, cost, risk, and expected objective delta., A deterministic evaluator selects a branch and retains rejected alternatives plus rationale., Router failure falls back to deterministic planning without blocking ready work., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py -q
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q, PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q, PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py -q

## G9.S3 Adapt execution capacity and validation cost

- Status: active
- Parent: G9
- Priority: P0
- Bundle: refactor/g9/g9-s3
- Goal: Adapt execution capacity and validation cost
- Evidence: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/resource_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_resource_scheduler.py, Heartbeats report measured CPU, memory, disk, active phase, and available worker capacity., Scheduler honors llm_router health, quota, latency, context, and token-budget constraints., Concurrency scales within configured limits and applies backpressure before provider or host exhaustion., Idle lanes advertise zero occupied capacity and can be reassigned., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_resource_scheduler.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_commands.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_scheduler.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_validation_scheduler.py, Cheap deterministic checks run before expensive tests and fail fast., Independent validations run in parallel under a bounded resource budget., Cache keys include target commit, command, relevant environment, and dependency state., Impact selection is conservative, explainable, and escalates to broader validation before merge completion., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_validation_scheduler.py -q
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_resource_scheduler.py -q, PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_validation_scheduler.py -q

## G9.S4 Close the scheduler feedback and lifecycle loop

- Status: active
- Parent: G9
- Priority: P0
- Bundle: refactor/g9/g9-s4
- Goal: Close the scheduler feedback and lifecycle loop
- Evidence: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scheduler_metrics.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/event_log.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/supervisor_watchdog.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py, One event-derived snapshot reports ready, active, idle, blocked, validation, merge, and resolver phases., Metrics include queue wait, implementation and validation duration, merge wait, conflict and retry rate, completions, tokens, and cost., Every metric is keyed by canonical goal, subgoal, task, lane, and provider identity., Scheduler decisions consume the same snapshot exposed to operators., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/dataset_store.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/worktrees.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py, AST and evidence records are reused by blob hash and only changed files are reparsed., Deleted and renamed files invalidate stale evidence deterministically., Clean worktrees and dependency setups can be pooled without sharing task-local mutations., Cold and warm paths produce equivalent plans and validation results with measured warm-path savings., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py -q
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py -q, PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py -q
