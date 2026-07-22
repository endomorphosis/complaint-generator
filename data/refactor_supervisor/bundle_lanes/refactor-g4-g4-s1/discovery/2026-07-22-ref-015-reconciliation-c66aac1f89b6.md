# REF-015 Reconciliation Guardrail

Date: 2026-07-22
Fingerprint: 4a439b7d25c40ec485c7de85df707e389ecd7ae2
Kind: main_checkout_dirty
Reason: main_checkout_dirty
Candidate count: 1
Priority: P1
Track: ops

## Main Checkout Status

- ` M data/refactor_supervisor/bundle_lanes/bundle_lanes.json`
- ` M data/refactor_supervisor/discovery/2026-07-21-ref-027-reconciliation-ca0bd08b3975.md`
- ` M data/refactor_supervisor/objective_bundles/index.json`
- ` M data/refactor_supervisor/objective_bundles/refactor-g8-g8-s1.todo.md`
- ` M data/refactor_supervisor/refactor_goals.json`
- ` M data/refactor_supervisor/refactor_objective_heap.md`
- ` M docs/REFACTOR_SUPERVISOR_TASKBOARD.md`
- `?? data/refactor_supervisor/merge_resolver_registry/`

## Main Checkout Evidence

- Path categories: `modified=7, untracked=1`
- Status paths:
  - `data/refactor_supervisor/bundle_lanes/bundle_lanes.json`
  - `data/refactor_supervisor/discovery/2026-07-21-ref-027-reconciliation-ca0bd08b3975.md`
  - `data/refactor_supervisor/objective_bundles/index.json`
  - `data/refactor_supervisor/objective_bundles/refactor-g8-g8-s1.todo.md`
  - `data/refactor_supervisor/refactor_goals.json`
  - `data/refactor_supervisor/refactor_objective_heap.md`
  - `docs/REFACTOR_SUPERVISOR_TASKBOARD.md`
  - `data/refactor_supervisor/merge_resolver_registry`
- Name status:
  - `M	data/refactor_supervisor/bundle_lanes/bundle_lanes.json`
  - `M	data/refactor_supervisor/discovery/2026-07-21-ref-027-reconciliation-ca0bd08b3975.md`
  - `M	data/refactor_supervisor/objective_bundles/index.json`
  - `M	data/refactor_supervisor/refactor_goals.json`
  - `M	data/refactor_supervisor/refactor_objective_heap.md`
  - `M	docs/REFACTOR_SUPERVISOR_TASKBOARD.md`
- Diff stat:
  - `.../bundle_lanes/bundle_lanes.json                 | 950967 +-----------------`
  - ` ...26-07-21-ref-027-reconciliation-ca0bd08b3975.md |     48 +-`
  - ` .../objective_bundles/index.json                   |     56 +-`
  - ` .../objective_bundles/refactor-g8-g8-s1.todo.md    |      2 +-`
  - ` data/refactor_supervisor/refactor_goals.json       |     47 +-`
  - ` .../refactor_supervisor/refactor_objective_heap.md |     50 +-`
  - ` docs/REFACTOR_SUPERVISOR_TASKBOARD.md              |     14 +-`
  - ` 7 files changed, 31939 insertions(+), 919245 deletions(-)`
- Untracked paths:
  - `data/refactor_supervisor/merge_resolver_registry`

## Sample Branches Or Worktrees

- `rescue/worktree/implementation-ref-013-d4fc48536ac0-attempt-1-1784693051-3c65dce8f628` at `/home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g4-g4-s1/ref-013-d4fc48536ac0-attempt-1-1784693051`

## Why This Blocks Progress

The implementation supervisor can only merge clean inactive implementation
worktrees when the main checkout is safe to mutate. Dirty main checkouts and
dirty backlogged worktrees are preserved until a deliberate reconciliation task
decides whether to commit, merge, discard generated duplicates, or split
unresolved work into follow-up tasks.

## Suggested Repair

Inspect the dirty paths and sampled worktrees, resolve any real work into
reviewable commits or follow-up tasks, rerun the supervisor reconciliation pass,
and verify that either the candidate merge count decreases or the dirty
worktree cleanup skip count decreases.

## Reconciliation Plan

Work surface: `1` candidates, `1` sampled records.

### Suggested Actions

- `classify_main_checkout_changes`: inspect git status, diff stats, submodule status, and generated artifacts before merges
- `preserve_or_split_main_checkout_work`: commit intentional changes or convert unresolved changes into follow-up tasks; never discard unknown work
- `rerun_worktree_reconciliation`: rerun reconcile_backlogged_worktrees once the main checkout is clean enough to mutate

### Safety Constraints

- Do not discard dirty or untracked content unless it is proven redundant with the target ref.
- Prefer commits, merges, or explicit follow-up tasks over destructive cleanup.
- Keep todo, objective, discovery, and strategy files parseable after reconciliation.

### Success Signals

- `candidate_count_decreases`
- `dirty_worktree_group_count_decreases`
- `main_checkout_dirty_becomes_false`
- `cleanup_or_reconciliation_pass_processes_candidates`

## Machine Readable Manifest

```json
{
  "actions": [
    {
      "action": "classify_main_checkout_changes",
      "automation": "inspect git status, diff stats, submodule status, and generated artifacts before merges",
      "scope": "repo_root"
    },
    {
      "action": "preserve_or_split_main_checkout_work",
      "automation": "commit intentional changes or convert unresolved changes into follow-up tasks; never discard unknown work",
      "scope": "repo_root"
    },
    {
      "action": "rerun_worktree_reconciliation",
      "automation": "rerun reconcile_backlogged_worktrees once the main checkout is clean enough to mutate",
      "scope": "backlogged_worktrees"
    }
  ],
  "candidate_count": 1,
  "conflict_path_counts": {},
  "dedupe_key": "reconciliation_guardrail:main_checkout_dirty",
  "fingerprint": "4a439b7d25c40ec485c7de85df707e389ecd7ae2",
  "kind": "main_checkout_dirty",
  "main_dirty_evidence": {
    "diff_stat": ".../bundle_lanes/bundle_lanes.json                 | 950967 +-----------------\n ...26-07-21-ref-027-reconciliation-ca0bd08b3975.md |     48 +-\n .../objective_bundles/index.json                   |     56 +-\n .../objective_bundles/refactor-g8-g8-s1.todo.md    |      2 +-\n data/refactor_supervisor/refactor_goals.json       |     47 +-\n .../refactor_supervisor/refactor_objective_heap.md |     50 +-\n docs/REFACTOR_SUPERVISOR_TASKBOARD.md              |     14 +-\n 7 files changed, 31939 insertions(+), 919245 deletions(-)",
    "name_status": "M\tdata/refactor_supervisor/bundle_lanes/bundle_lanes.json\nM\tdata/refactor_supervisor/discovery/2026-07-21-ref-027-reconciliation-ca0bd08b3975.md\nM\tdata/refactor_supervisor/objective_bundles/index.json\nM\tdata/refactor_supervisor/refactor_goals.json\nM\tdata/refactor_supervisor/refactor_objective_heap.md\nM\tdocs/REFACTOR_SUPERVISOR_TASKBOARD.md",
    "path_categories": {
      "modified": 7,
      "untracked": 1
    },
    "status_paths": [
      "data/refactor_supervisor/bundle_lanes/bundle_lanes.json",
      "data/refactor_supervisor/discovery/2026-07-21-ref-027-reconciliation-ca0bd08b3975.md",
      "data/refactor_supervisor/objective_bundles/index.json",
      "data/refactor_supervisor/objective_bundles/refactor-g8-g8-s1.todo.md",
      "data/refactor_supervisor/refactor_goals.json",
      "data/refactor_supervisor/refactor_objective_heap.md",
      "docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
      "data/refactor_supervisor/merge_resolver_registry"
    ],
    "status_short": [
      " M data/refactor_supervisor/bundle_lanes/bundle_lanes.json",
      " M data/refactor_supervisor/discovery/2026-07-21-ref-027-reconciliation-ca0bd08b3975.md",
      " M data/refactor_supervisor/objective_bundles/index.json",
      " M data/refactor_supervisor/objective_bundles/refactor-g8-g8-s1.todo.md",
      " M data/refactor_supervisor/refactor_goals.json",
      " M data/refactor_supervisor/refactor_objective_heap.md",
      " M docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
      "?? data/refactor_supervisor/merge_resolver_registry/"
    ],
    "untracked_paths": [
      "data/refactor_supervisor/merge_resolver_registry"
    ]
  },
  "reason": "main_checkout_dirty",
  "safety_constraints": [
    "Do not discard dirty or untracked content unless it is proven redundant with the target ref.",
    "Prefer commits, merges, or explicit follow-up tasks over destructive cleanup.",
    "Keep todo, objective, discovery, and strategy files parseable after reconciliation."
  ],
  "sample_branches": [
    "rescue/worktree/implementation-ref-013-d4fc48536ac0-attempt-1-1784693051-3c65dce8f628"
  ],
  "sample_count": 1,
  "sample_status_paths": [
    "data/refactor_supervisor/bundle_lanes/bundle_lanes.json",
    "data/refactor_supervisor/discovery/2026-07-21-ref-027-reconciliation-ca0bd08b3975.md",
    "data/refactor_supervisor/objective_bundles/index.json",
    "data/refactor_supervisor/objective_bundles/refactor-g8-g8-s1.todo.md",
    "data/refactor_supervisor/refactor_goals.json",
    "data/refactor_supervisor/refactor_objective_heap.md",
    "docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
    "data/refactor_supervisor/merge_resolver_registry"
  ],
  "sample_worktrees": [
    "/home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g4-g4-s1/ref-013-d4fc48536ac0-attempt-1-1784693051"
  ],
  "success_signals": [
    "candidate_count_decreases",
    "dirty_worktree_group_count_decreases",
    "main_checkout_dirty_becomes_false",
    "cleanup_or_reconciliation_pass_processes_candidates"
  ],
  "top_conflict_paths": []
}
```
