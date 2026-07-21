# Objective Bundle: refactor/g2

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: bundle objective-generated tasks so parallel daemons can work one lane at a time.
Conflict policy: keep edits inside this bundle when possible; use the LLM merge resolver for semantic conflicts.

## REF-029 Close objective gap: Decompose oversized orchestration modules

- Status: todo
- Completion: manual
- Priority: P0
- Track: ops
- Depends on: 
- Outputs: data/refactor_supervisor/discovery, data/refactor_supervisor/refactor_objective_heap.md
- Validation: python -m pytest --collect-only -q
- Bundle: refactor/g2
- Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g2.todo.md
- Bundle strategy: explicit
- Graph parents: none
- Graph depth: 0
- Parallel lane: refactor/g2
- Conflict policy: prefer bundle-local changes; invoke the LLM merge resolver for semantic conflicts
- Goal id: G2
- Missing evidence: objective validation repair
- Embedding query: Decompose oversized orchestration modules
- AST query: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, mediator/mediator.py, mediator/__init__.py, mediator/claim_support_hooks.py, applications/complaint_workspace.py, applications/dashboard_ui.py, playwright/server.js
- Surplus group: objective/G2
- Merge key: 711e65b47b204d01
- Merge family: objective/G2
- Merge role: validation_gate
- Work item count: 1
- Work scope: objective_validation_repair
- Goal packet: 
- Goal packet role: 
- Goal packet goals: 
- Goal packet task count: 0
- Goal packet work item count: 0
- Candidate kind: validation_gate
- Todo vector key: ce8c3a3f03eb4308
- Repair evidence: data/refactor_supervisor/discovery/2026-07-21-ref-029-objective-validation-repair.md; objective validation repair
- Acceptance: Objective scan filed this gap for G2. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-21-ref-029-objective-gap-eac2cf021fa2.md, add code/tests/docs or child goals that prove the missing evidence terms are covered (objective validation repair), and keep the supervisor-fed backlog aligned with the objective heap.  Refine the objective heap if the gap needs smaller child goals.
