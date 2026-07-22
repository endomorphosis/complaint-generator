# REF-061 Objective Validation Repair

Date: 2026-07-22
Goal id: G9
Goal title: Increase agent-supervisor planning quality and throughput
Gap source: data/refactor_supervisor/discovery/2026-07-22-ref-061-objective-gap-6686ce3fc621.md
Objective heap: data/refactor_supervisor/refactor_objective_heap.md
Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g9.todo.md
Todo vector key: 8ac5bc4a64ea0dd0
Merge key: efb4c826202e946c
Merge family: objective/G9

## Repair Summary

The objective scan forced a fresh validation gate for G9 and filed REF-061
because the parent-goal evidence did not contain the synthetic missing evidence
term `objective validation repair`. The planning and throughput work is already
divided into four independently testable child goals:

- G9.S1 owns canonical task identity, persistent leasing, live lane scheduling,
  and a serialized merge train with durable conflict handling.
- G9.S2 owns dependency and conflict graphs, objective-value prioritization,
  structured plan alternatives, deterministic evaluation, and router fallback.
- G9.S3 owns resource-aware execution capacity, validation ordering, bounded
  parallel checks, and validation-cache correctness.
- G9.S4 owns event-derived scheduler metrics, lifecycle feedback, incremental
  evidence indexing, invalidation, and reusable clean runtime resources.

Each child names explicit implementation surfaces, acceptance criteria, focused
test targets, and executable validation commands in the objective heap. These
four scopes cover coordination, planning quality, execution throughput, and
feedback without overlap. A fifth child goal solely for the repository-wide
validation gate would duplicate that decomposition, so the heap needs no
additional child goal. This validation repair records objective coverage; it
does not mark active child-goal implementation work complete.

REF-061 reran the objective's repository-wide collection command successfully.
This record is linked from G9 in the objective heap and from REF-061 in the
bundle-local supervisor backlog. The task remains supervisor-owned and is not
marked complete manually.

## Evidence Covered

- Missing evidence term: objective validation repair
- Present coordination and merge evidence: G9.S1 and
  `ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py`,
  `test_agent_supervisor_scheduler.py`, and
  `test_agent_supervisor_merge_train.py`
- Present dependency and conflict-planning evidence: G9.S2 and
  `ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py`,
  plus `test_agent_supervisor_conflict_graph.py`
- Present scheduler feedback evidence: G9.S4 and
  `ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py`
- Remaining structured-plan, capacity, validation-scheduling, and incremental
  runtime targets stay explicitly owned by G9.S2 through G9.S4; this parent
  validation repair neither duplicates them nor changes their active status.
- Child-goal decomposition: G9.S1 through G9.S4 in
  `data/refactor_supervisor/refactor_objective_heap.md`
- Heap evidence:
  `data/refactor_supervisor/discovery/2026-07-22-ref-061-objective-validation-repair.md`
- Bundle evidence: REF-061 in
  `data/refactor_supervisor/objective_bundles/refactor-g9.todo.md`

## Validation

Command: `python -m pytest --collect-only -q`

Result: passed on 2026-07-22; 4,659 tests collected in 33.52 seconds, exit code
0. The only diagnostic was the existing `pytest-asyncio` deprecation warning
for the unset `asyncio_default_fixture_loop_scope` option.
