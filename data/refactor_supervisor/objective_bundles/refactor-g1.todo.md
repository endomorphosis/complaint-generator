# Objective Bundle: refactor/g1

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: bundle objective-generated tasks so parallel daemons can work one lane at a time.
Conflict policy: keep edits inside this bundle when possible; use the LLM merge resolver for semantic conflicts.

## REF-028 Close objective gap: Stabilize repository boundaries

- Status: todo
- Completion: manual
- Priority: P0
- Track: ops
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, data/refactor_supervisor/refactor_objective_heap.md
- Validation: python -m pytest --collect-only -q
- Bundle: refactor/g1
- Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g1.todo.md
- Bundle strategy: explicit
- Graph parents: none
- Graph depth: 0
- Parallel lane: refactor/g1
- Conflict policy: prefer bundle-local changes; invoke the LLM merge resolver for semantic conflicts
- Goal id: G1
- Missing evidence: objective validation repair
- Embedding query: Stabilize repository boundaries
- AST query: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, mediator/mediator.py, applications/complaint_workspace.py, tests/test_claim_support_review_playwright_smoke.py, docs/ARCHITECTURE.md, pyproject.toml, applications/document_api.py, integrations/ipfs_datasets/loader.py, applications/complaint_cli.py
- Surplus group: objective/G1
- Merge key: 9c3d2b35296e9add
- Merge family: objective/G1
- Merge role: validation_gate
- Work item count: 1
- Work scope: objective_validation_repair
- Goal packet: 
- Goal packet role: 
- Goal packet goals: 
- Goal packet task count: 0
- Goal packet work item count: 0
- Candidate kind: validation_gate
- Todo vector key: 5bcc4ed60686d81a
- Acceptance: Objective scan filed this gap for G1. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-21-ref-028-objective-gap-08d9b0956fd6.md, add code/tests/docs or child goals that prove the missing evidence terms are covered (objective validation repair), and keep the supervisor-fed backlog aligned with the objective heap.  Refine the objective heap if the gap needs smaller child goals.
