# Objective Bundle: refactor/g1/g1-s1

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [ ] Task checkbox-1: REF-001 Create an entrypoint and ownership map for the largest runtime modules

## REF-001 Create an entrypoint and ownership map for the largest runtime modules

- Status: todo
- Completion: manual
- Priority: P0
- Track: G1
- Depends on: 
- Outputs: mediator/mediator.py, applications/complaint_workspace.py, tests/test_claim_support_review_playwright_smoke.py, scripts/synthesize_hacc_complaint.py, tests/test_review_api.py, complaint_phases/denoiser.py
- Validation: python -m pytest tests/test_package_imports.py -q
- Bundle: refactor/g1/g1-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G1.S1
- Missing evidence: Large modules dominate change risk and need explicit boundaries before extraction.
- AST symbols: ALIGNMENT_TASK_UPDATE_HISTORY_LIMIT, FOLLOW_UP_REVIEWABLE_ESCALATION_STATUSES, Mediator, __init__, reset, resume, get_state, set_state, response, select_intake_question_candidates, _phase_focus_rank, _phase_focus_bonus, _is_document_question_candidate, _build_exhibit_ready_document_question, _apply_exhibit_ready_intake_questioning, _is_exact_dates_closure_match, _is_staff_names_titles_closure_match, _is_hearing_request_timing_closure_match, _is_response_dates_closure_match, _is_causation_sequence_match, _build_intake_claim_pressure_map, _build_intake_selector_legal_graph, _build_intake_matching_pressure_map, _build_intake_workflow_action_queue, _summarize_intake_workflow_action_queue, _build_evidence_workflow_action_queue, _get_document_provenance_summary, _get_document_grounding_lane_outcome_summary, _get_document_grounding_recovery_action, _get_document_grounding_improvement_next_action
- Merge key: refactor/g1/g1-s1
- Candidate kind: seed
- Todo vector key: ref-001-createanentrypointandownershipmapforthelargestru
- Acceptance: A short module ownership map exists.; Entrypoints are grouped by CLI, web, mediator, and workflow role.

- [ ] Task checkbox-2: REF-002 Document allowed dependency direction between applications, mediator, phases, integrations, and lib

## REF-002 Document allowed dependency direction between applications, mediator, phases, integrations, and lib

- Status: todo
- Completion: manual
- Priority: P0
- Track: G1
- Depends on: 
- Outputs: docs/ARCHITECTURE.md, pyproject.toml
- Validation: python -m pytest tests/test_package_imports.py -q
- Bundle: refactor/g1/g1-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G1.S1
- Missing evidence: Refactors need a clear import direction to avoid moving complexity around.
- AST symbols: 
- Merge key: refactor/g1/g1-s1
- Candidate kind: seed
- Todo vector key: ref-002-documentalloweddependencydirectionbetweenapplica
- Acceptance: Architecture docs identify allowed imports.; New work has a simple rule for where shared code belongs.

## REF-048 Close objective gap: Map package ownership and runtime entrypoints

- Status: todo
- Completion: manual
- Priority: P0
- Track: ops
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, data/refactor_supervisor/refactor_objective_heap.md
- Validation: python -m pytest tests/test_package_imports.py -q
- Bundle: refactor/g1/g1-s1
- Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g1-g1-s1.todo.md
- Bundle strategy: explicit
- Graph parents: G1
- Graph depth: 1
- Parallel lane: refactor/g1/g1-s1
- Conflict policy: prefer bundle-local changes; invoke the LLM merge resolver for semantic conflicts
- Goal id: G1.S1
- Canonical task key: task/v1/cba035a6013e2ca56c7624d03ca454d9965b4c9fbc75e3c2186b835478bdb080
- Canonical task CID: baguqeerazoqdljqbhywkk3dwetidzjcu3glfwte7xr26hqqynobvi6f5wcaa
- Missing evidence: objective validation repair
- Embedding query: Map package ownership and runtime entrypoints
- AST query: mediator/mediator.py, applications/complaint_workspace.py, tests/test_claim_support_review_playwright_smoke.py, scripts/synthesize_hacc_complaint.py, tests/test_review_api.py, complaint_phases/denoiser.py, A short module ownership map exists., Entrypoints are grouped by CLI, web, mediator, and workflow role., python -m pytest tests/test_package_imports.py -q, docs/ARCHITECTURE.md, pyproject.toml, Architecture docs identify allowed imports., New work has a simple rule for where shared code belongs., python -m pytest tests/test_package_imports.py -q
- Surplus group: objective/G1.S1
- Merge key: 4003ea72cdc5444e
- Merge family: objective/G1.S1
- Merge role: validation_gate
- Work item count: 1
- Work scope: objective_validation_repair
- Goal packet: 
- Goal packet role: 
- Goal packet goals: 
- Goal packet task count: 0
- Goal packet work item count: 0
- Candidate kind: validation_gate
- Todo vector key: 9ca9d1d1566fc3e7
- Acceptance: Objective scan filed this gap for G1.S1. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-21-ref-048-objective-gap-f307b3b05fa3.md, add code/tests/docs or child goals that prove the missing evidence terms are covered (objective validation repair), and keep the supervisor-fed backlog aligned with the objective heap.  Refine the objective heap if the gap needs smaller child goals.
