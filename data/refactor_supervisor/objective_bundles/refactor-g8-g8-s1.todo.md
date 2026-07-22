# Objective Bundle: refactor/g8/g8-s1

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [ ] Task checkbox-23: REF-023 Cross-link IPFS datasets execution backlog tasks to refactor supervisor goals

## REF-023 Cross-link IPFS datasets execution backlog tasks to refactor supervisor goals

- Status: completed
- Completion: manual
- Priority: P0
- Track: G8
- Depends on: 
- Outputs: docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md
- Validation: python scripts/refactor_agent_supervisor.py seed --once
- Bundle: refactor/g8/g8-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G8.S1
- Missing evidence: Existing roadmap work should feed the automated taskboard rather than drift separately.
- AST symbols: 
- Merge key: refactor/g8/g8-s1
- Candidate kind: seed
- Todo vector key: ref-023-cross-linkipfsdatasetsexecutionbacklogtaskstoref
- Acceptance: Each P0 backlog workstream maps to at least one refactor goal.; Duplicated tasks are merged or explicitly scoped.

- [x] Task checkbox-24: REF-024 Define first three implementation claims from the queued taskboard

## REF-024 Define first three implementation claims from the queued taskboard

- Status: completed
- Completion: manual
- Priority: P0
- Track: G8
- Depends on: 
- Outputs: data/refactor_supervisor/refactor_goals.json
- Validation: python scripts/refactor_agent_supervisor.py status
- Bundle: refactor/g8/g8-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G8.S1
- Missing evidence: A robust board still needs a practical starting order.
- AST symbols: 
- Merge key: refactor/g8/g8-s1
- Candidate kind: seed
- Todo vector key: ref-024-definefirstthreeimplementationclaimsfromthequeue
- Acceptance: The first three claims are small, testable, and dependency-ordered.; Each claim names exact validation commands.

## REF-025 Resolve dirty main checkout blocking 1 worktree merges

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Fingerprint: d70172dd2341f6e7cb439bd4d06873e15d0364b8
- Dedupe key: reconciliation_guardrail:main_checkout_dirty
- Depends on:
- Outputs: data/refactor_supervisor/bundle_lanes/refactor-g8-g8-s1/discovery, data/refactor_supervisor/objective_bundles/refactor-g8-g8-s1.todo.md
- Validation: test -f /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g8-g8-s1/discovery/2026-07-22-ref-025-reconciliation-d70172dd2341.md
- Acceptance: Reconciliation guardrail filed this because 1 branch or worktree cleanup candidates are blocked by main_checkout_dirty. Use evidence and the machine-readable reconciliation plan in /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g8-g8-s1/discovery/2026-07-22-ref-025-reconciliation-d70172dd2341.md, reconcile the dirty checkout or dirty worktree group deliberately, then rerun the supervisor cleanup/reconciliation pass and confirm that the blocked candidate count decreases.
- Reconciliation result: Generated checkout changes were preserved in commit `2880ee1eae8f36abc95542a12e80967c71dcc4e0`; the scoped reconciliation pass reran at `2026-07-22T04:12:35Z` with both `main_checkout_dirty` and `raw_main_checkout_dirty` false, and the dirty-main blocked candidate count decreased from `1` to `0`. The candidate was processed and its separate preflight conflicts were filed as REF-026.

## REF-026 Resolve 1 preflight-conflicting backlogged worktree merges

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Fingerprint: fc7e21256d1f56af80ccaa2a28a6acefd2614035
- Dedupe key: reconciliation_guardrail:preflight_merge_conflict
- Depends on:
- Outputs: data/refactor_supervisor/bundle_lanes/refactor-g8-g8-s1/discovery, data/refactor_supervisor/objective_bundles/refactor-g8-g8-s1.todo.md
- Validation: test -f /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g8-g8-s1/discovery/2026-07-22-ref-026-reconciliation-fc7e21256d1f.md
- Acceptance: Reconciliation guardrail filed this because 1 branch or worktree cleanup candidates are blocked by preflight_merge_conflict. Use evidence and the machine-readable reconciliation plan in /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g8-g8-s1/discovery/2026-07-22-ref-026-reconciliation-fc7e21256d1f.md, reconcile the dirty checkout or dirty worktree group deliberately, then rerun the supervisor cleanup/reconciliation pass and confirm that the blocked candidate count decreases.
