# Objective Bundle: refactor/g1/g1-s2

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-3: REF-003 Replace production sys.path mutation with package-level imports or adapter loader calls

## REF-003 Replace production sys.path mutation with package-level imports or adapter loader calls

- Status: completed
- Completion: manual
- Priority: P0
- Track: G1
- Depends on: 
- Outputs: applications/complaint_workspace.py, applications/document_api.py, integrations/ipfs_datasets/loader.py, scripts/agentic_complaint_evidence_scraper.py, scripts/agentic_scraper_cli.py, scripts/backfill_claim_testimony_links.py, scripts/check_hacc_routers.py, scripts/enrich_email_timeline_authorities.py, scripts/generate_decision_trees.py, scripts/generate_email_search_plan.py, scripts/generate_hacc_email_seed_plan.py, scripts/gmail_duckdb_daemon.py
- Validation: python -m pytest tests/test_package_imports.py -q
- Bundle: refactor/g1/g1-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G1.S2
- Missing evidence: The scan found production-style sys.path mutation that makes runtime behavior environment-sensitive.
- AST symbols: _ensure_local_ipfs_datasets_path, DEFAULT_USER_ID, DEFAULT_UI_UX_OPTIMIZER_METHOD, DEFAULT_UI_UX_OPTIMIZER_PRIORITY, DEFAULT_LLM_DRAFT_PROVIDER, DEFAULT_LLM_DRAFT_TIMEOUT_SECONDS, MIKE_STATUS_CONTRACT_VERSION, MIKE_HANDOFF_CONTRACT_VERSION, MIKE_SYNC_CONTRACT_VERSION, MAX_MIKE_HANDOFF_PARAGRAPHS, MAX_MIKE_WEAK_LINKS_DISPLAY, DEFAULT_UI_UX_SCREENSHOT_TARGET, _DATA_DIR, _SESSION_DIR, _DOCKET_ISSUE_ENTITY_KEYWORDS, _utc_now, _slugify_user_id, _split_lines, _unique_preserve_order, _slugify_graph_id, _normalize_annotation_tags, _build_schema_guided_tooling_recommendations, _normalize_fragment, _extract_person_name, _extract_defendant_name, _condense_timeline_text, _sentence_fragment, _event_fragment, _adverse_action_clause, _pleading_activity_fragment
- Merge key: refactor/g1/g1-s2
- Candidate kind: seed
- Todo vector key: ref-003-replaceproductionsys-pathmutationwithpackage-lev
- Acceptance: No production entrypoint mutates sys.path for normal imports.; Explicit exceptions are isolated to scripts/tests.

- [x] Task checkbox-4: REF-004 Route direct ipfs_datasets_py imports through integrations/ipfs_datasets adapters where production-facing

## REF-004 Route direct ipfs_datasets_py imports through integrations/ipfs_datasets adapters where production-facing

- Status: completed
- Completion: manual
- Priority: P0
- Track: G1
- Depends on: 
- Outputs: applications/complaint_cli.py, applications/complaint_workspace.py
- Validation: python -m pytest tests/test_ipfs_adapter_layer.py -q
- Bundle: refactor/g1/g1-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G1.S2
- Missing evidence: Optional dependency behavior should stay behind the adapter boundary.
- AST symbols: DEFAULT_UI_UX_SCREENSHOT_TARGET, DEFAULT_UI_UX_OPTIMIZER_METHOD, DEFAULT_UI_UX_OPTIMIZER_PRIORITY, app, service, _print, _split_multiline_values, _parse_json_option, session, identity, questions, claim_elements, tools, answer, chat_turn, chat, add_evidence, import_gmail_evidence_command, import_local_evidence_command, migrate_legacy_session_command, run_gmail_duckdb_pipeline_command, search_email_duckdb_command, review, mediator_prompt, complaint_readiness, ui_readiness, client_release_gate, capabilities, tooling_contract, workspace_data_schema
- Merge key: refactor/g1/g1-s2
- Candidate kind: seed
- Todo vector key: ref-004-routedirectipfs-datasets-pyimportsthroughintegra
- Acceptance: Production direct imports are replaced or documented.; Degraded mode still imports cleanly.

## REF-005 Resolve 1 preflight-conflicting backlogged worktree merges

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Fingerprint: db50ee4f0701bf764df9051f8a2d4ccd371d4768
- Dedupe key: reconciliation_guardrail:preflight_merge_conflict
- Depends on:
- Outputs: data/refactor_supervisor/bundle_lanes/refactor-g1-g1-s2/discovery, data/refactor_supervisor/objective_bundles/refactor-g1-g1-s2.todo.md
- Validation: test -f /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g1-g1-s2/discovery/2026-07-21-ref-005-reconciliation-db50ee4f0701.md
- Acceptance: Reconciliation guardrail filed this because 1 branch or worktree cleanup candidates are blocked by preflight_merge_conflict. Use evidence and the machine-readable reconciliation plan in /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g1-g1-s2/discovery/2026-07-21-ref-005-reconciliation-db50ee4f0701.md, reconcile the dirty checkout or dirty worktree group deliberately, then rerun the supervisor cleanup/reconciliation pass and confirm that the blocked candidate count decreases.

## REF-006 Resolve dirty main checkout blocking 1 worktree merges

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Fingerprint: fde3722148ab64b3223caf20029a0bf7d0467dad
- Dedupe key: reconciliation_guardrail:main_checkout_dirty
- Depends on:
- Outputs: data/refactor_supervisor/bundle_lanes/refactor-g1-g1-s2/discovery, data/refactor_supervisor/objective_bundles/refactor-g1-g1-s2.todo.md
- Validation: test -f /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g1-g1-s2/discovery/2026-07-21-ref-006-reconciliation-fde3722148ab.md
- Acceptance: Reconciliation guardrail filed this because 1 branch or worktree cleanup candidates are blocked by main_checkout_dirty. Use evidence and the machine-readable reconciliation plan in /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g1-g1-s2/discovery/2026-07-21-ref-006-reconciliation-fde3722148ab.md, reconcile the dirty checkout or dirty worktree group deliberately, then rerun the supervisor cleanup/reconciliation pass and confirm that the blocked candidate count decreases.
- Reconciliation result: Main checkout dirt was preserved in commit `f20703f1bb2a732fa78daf8c031fb315232baa1e`, current generated guardrail dirt was preserved in commit `81ab5a8ff25abe126f321a2894f328c7f0272597`, the lane reconciliation pass reran at `2026-07-21T20:24:41Z`, and the `main_checkout_dirty` blocker count for this guardrail decreased from `1` to `0`; the remaining processed candidate is a separate `preflight_merge_conflict` on `scripts/refactor_agent_supervisor.py`.

## REF-007 Resolve merge retry-budget failure for REF-003

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Depends on: 
- Outputs: applications/complaint_workspace.py, applications/document_api.py, integrations/ipfs_datasets/loader.py, scripts/agentic_complaint_evidence_scraper.py, scripts/agentic_scraper_cli.py, scripts/backfill_claim_testimony_links.py, scripts/check_hacc_routers.py, scripts/enrich_email_timeline_authorities.py, scripts/generate_decision_trees.py, scripts/generate_email_search_plan.py, scripts/generate_hacc_email_seed_plan.py, scripts/gmail_duckdb_daemon.py, data/refactor_supervisor/bundle_lanes/refactor-g1-g1-s2/discovery
- Validation: test -f /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g1-g1-s2/discovery/2026-07-21-ref-007-ref-003-merge-retry-budget.md
- Acceptance: Merge retry-budget guardrail filed this from repeated merge failures in REF-003. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g1-g1-s2/discovery/2026-07-21-ref-007-ref-003-merge-retry-budget.md to fix the merge blocker, verify the intended implementation changes are committed in their owning repository or submodule, run `ipfs-accelerate-agent-merge-resolver --events-path ... --apply` when the conflict is semantic, then mark this repair task completed so the supervisor can release REF-003 from strategy blocked_tasks.
- Repair result: REF-003 was merged into `implementation/ref-007-attempt-1-1784665947` in commit `b733f65`; the semantic conflict in `scripts/refactor_agent_supervisor.py` kept the newer merge-resolver environment wrapper, `ipfs-accelerate-agent-merge-resolver --events-path /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g1-g1-s2/state/agent_refactor_g1_g1_s2_events.jsonl --apply` reported `applied: true`, and REF-003 was removed from `blocked_tasks`.

## REF-008 Resolve merge retry-budget failure for REF-004

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Depends on: 
- Outputs: applications/complaint_cli.py, applications/complaint_workspace.py, data/refactor_supervisor/bundle_lanes/refactor-g1-g1-s2/discovery
- Validation: test -f /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g1-g1-s2/discovery/2026-07-21-ref-008-ref-004-merge-retry-budget.md
- Acceptance: Merge retry-budget guardrail filed this from repeated merge failures in REF-004. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g1-g1-s2/discovery/2026-07-21-ref-008-ref-004-merge-retry-budget.md to fix the merge blocker, verify the intended implementation changes are committed in their owning repository or submodule, run `ipfs-accelerate-agent-merge-resolver --events-path ... --apply` when the conflict is semantic, then mark this repair task completed so the supervisor can release REF-004 from strategy blocked_tasks.

## REF-070 Close objective gap: Remove ad hoc import path behavior from production surfaces

- Status: todo
- Completion: manual
- Priority: P0
- Track: ops
- Depends on:
- Outputs: data/refactor_supervisor/discovery, data/refactor_supervisor/refactor_objective_heap.md
- Validation: python -m pytest tests/test_package_imports.py -q; python -m pytest tests/test_ipfs_adapter_layer.py -q
- Bundle: refactor/g1/g1-s2
- Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g1-g1-s2.todo.md
- Bundle strategy: explicit
- Graph parents: G1
- Graph depth: 1
- Parallel lane: refactor/g1/g1-s2
- Conflict policy: prefer bundle-local changes; invoke the LLM merge resolver for semantic conflicts
- Predicted files:
- Changed paths:
- AST symbols: scripts/graphrag_email_manifest.py, scripts/import_gmail_evidence.py, scripts/import_local_eml_directory.py, scripts/master_case_email.py, scripts/process_hacc_pdfs_to_kg.py, scripts/run_gmail_duckdb_pipeline.py, scripts/run_hacc_adversarial_report.py, scripts/run_hacc_grounded_pipeline.py, scripts/run_hacc_preset_matrix.py, No production entrypoint mutates sys.path for normal imports., Explicit exceptions are isolated to scripts/tests., python -m pytest tests/test_package_imports.py -q, applications/dashboard_ui.py, complaint_generator/agentic_evidence_download.py, complaint_generator/data_migration.py, complaint_generator/email_agentic_search.py, complaint_generator/email_authority_enrichment.py, complaint_generator/email_credentials.py, complaint_generator/email_graphrag.py, complaint_generator/email_import.py, complaint_generator/email_oauth.py, complaint_generator/email_pipeline.py, complaint_generator/email_seed_planner.py, complaint_generator/email_timeline_handoff.py, complaint_generator/evidence_relevance.py, integrations/ipfs_datasets/llm.py, Production direct imports are replaced or documented., Degraded mode still imports cleanly., python -m pytest tests/test_ipfs_adapter_layer.py -q
- Interfaces:
- Submodules:
- Generated artifacts:
- Allow concurrent with:
- Goal id: G1.S2
- Canonical task key: task/v1/ad23811d9d14aedb7013be18cb8208f23af01bb88f24e7b8d47b41d7c18ec810
- Canonical task CID: baguqeeravurychm5csxnw4atxymmxaqi6i5pag5yr4sopogupna5pqmozaia
- Missing evidence: objective validation repair
- Embedding query: Remove ad hoc import path behavior from production surfaces
- AST query: scripts/graphrag_email_manifest.py, scripts/import_gmail_evidence.py, scripts/import_local_eml_directory.py, scripts/master_case_email.py, scripts/process_hacc_pdfs_to_kg.py, scripts/run_gmail_duckdb_pipeline.py, scripts/run_hacc_adversarial_report.py, scripts/run_hacc_grounded_pipeline.py, scripts/run_hacc_preset_matrix.py, No production entrypoint mutates sys.path for normal imports., Explicit exceptions are isolated to scripts/tests., python -m pytest tests/test_package_imports.py -q, applications/dashboard_ui.py, complaint_generator/agentic_evidence_download.py, complaint_generator/data_migration.py, complaint_generator/email_agentic_search.py, complaint_generator/email_authority_enrichment.py, complaint_generator/email_credentials.py, complaint_generator/email_graphrag.py, complaint_generator/email_import.py, complaint_generator/email_oauth.py, complaint_generator/email_pipeline.py, complaint_generator/email_seed_planner.py, complaint_generator/email_timeline_handoff.py, complaint_generator/evidence_relevance.py, integrations/ipfs_datasets/llm.py, Production direct imports are replaced or documented., Degraded mode still imports cleanly., python -m pytest tests/test_ipfs_adapter_layer.py -q
- Surplus group: objective/G1.S2
- Merge key: b74aae0dd2672d61
- Merge family: objective/G1.S2
- Merge role: validation_gate
- Work item count: 1
- Work scope: objective_validation_repair
- Goal packet:
- Goal packet role:
- Goal packet goals:
- Goal packet task count: 0
- Goal packet work item count: 0
- Candidate kind: validation_gate
- Todo vector key: 80d513659b600256
- Repair evidence: data/refactor_supervisor/discovery/2026-07-22-ref-070-objective-validation-repair.md; objective validation repair
- Acceptance: Objective scan filed this gap for G1.S2. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-070-objective-gap-514368960e0e.md, add code/tests/docs or child goals that prove the missing evidence terms are covered (objective validation repair), and keep the supervisor-fed backlog aligned with the objective heap. Refine the objective heap if the gap needs smaller child goals.
