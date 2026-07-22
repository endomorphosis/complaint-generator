# REF-027 Reconciliation Guardrail

Date: 2026-07-22
Fingerprint: a8d69a08a26f001170144d40fdc5219756a29851
Kind: main_checkout_dirty
Reason: main_checkout_dirty
Candidate count: 1
Priority: P1
Track: ops

## Main Checkout Status

- ` M data/refactor_supervisor/refactor_goals.json`
- ` M docs/REFACTOR_SUPERVISOR_TASKBOARD.md`

## Main Checkout Evidence

- Path categories: `modified=2`
- Status paths:
  - `data/refactor_supervisor/refactor_goals.json`
  - `docs/REFACTOR_SUPERVISOR_TASKBOARD.md`
- Name status:
  - `M	data/refactor_supervisor/refactor_goals.json`
  - `M	docs/REFACTOR_SUPERVISOR_TASKBOARD.md`
- Diff stat:
  - `data/refactor_supervisor/refactor_goals.json | 6 +++---`
  - ` docs/REFACTOR_SUPERVISOR_TASKBOARD.md        | 4 ++--`
  - ` 2 files changed, 5 insertions(+), 5 deletions(-)`

## Sample Branches Or Worktrees

- `rescue/worktree/implementation-ref-016-30a2a7d729bd-attempt-1-1784688023-807bc7a20043` at `/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-016-30a2a7d729bd-attempt-1-1784688023`

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
  "fingerprint": "a8d69a08a26f001170144d40fdc5219756a29851",
  "kind": "main_checkout_dirty",
  "main_dirty_evidence": {
    "diff_stat": "data/refactor_supervisor/refactor_goals.json | 6 +++---\n docs/REFACTOR_SUPERVISOR_TASKBOARD.md        | 4 ++--\n 2 files changed, 5 insertions(+), 5 deletions(-)",
    "name_status": "M\tdata/refactor_supervisor/refactor_goals.json\nM\tdocs/REFACTOR_SUPERVISOR_TASKBOARD.md",
    "path_categories": {
      "modified": 2
    },
    "status_paths": [
      "data/refactor_supervisor/refactor_goals.json",
      "docs/REFACTOR_SUPERVISOR_TASKBOARD.md"
    ],
    "status_short": [
      " M data/refactor_supervisor/refactor_goals.json",
      " M docs/REFACTOR_SUPERVISOR_TASKBOARD.md"
    ]
  },
  "reason": "main_checkout_dirty",
  "safety_constraints": [
    "Do not discard dirty or untracked content unless it is proven redundant with the target ref.",
    "Prefer commits, merges, or explicit follow-up tasks over destructive cleanup.",
    "Keep todo, objective, discovery, and strategy files parseable after reconciliation."
  ],
  "sample_branches": [
    "rescue/worktree/implementation-ref-016-30a2a7d729bd-attempt-1-1784688023-807bc7a20043"
  ],
  "sample_count": 1,
  "sample_status_paths": [
    "data/refactor_supervisor/refactor_goals.json",
    "docs/REFACTOR_SUPERVISOR_TASKBOARD.md"
  ],
  "sample_worktrees": [
    "/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-016-30a2a7d729bd-attempt-1-1784688023"
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
