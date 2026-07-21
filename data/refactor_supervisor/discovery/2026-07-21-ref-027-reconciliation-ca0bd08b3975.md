# REF-027 Reconciliation Guardrail

Date: 2026-07-21
Fingerprint: ebc903c15c398edeb9eabd86f6eaa1fc3e15fab8
Kind: main_checkout_dirty
Reason: main_checkout_dirty
Candidate count: 2
Priority: P1
Track: ops

## Main Checkout Status

- ` M data/refactor_supervisor/refactor_goals.json`
- ` M docs/REFACTOR_SUPERVISOR_TASKBOARD.md`
- ` M integrations/ipfs_datasets/loader.py`
- ` M tests/test_package_imports.py`

## Main Checkout Evidence

- Path categories: `modified=4`
- Status paths:
  - `data/refactor_supervisor/refactor_goals.json`
  - `docs/REFACTOR_SUPERVISOR_TASKBOARD.md`
  - `integrations/ipfs_datasets/loader.py`
  - `tests/test_package_imports.py`
- Name status:
  - `M	data/refactor_supervisor/refactor_goals.json`
  - `M	docs/REFACTOR_SUPERVISOR_TASKBOARD.md`
  - `M	integrations/ipfs_datasets/loader.py`
  - `M	tests/test_package_imports.py`
- Diff stat:
  - `data/refactor_supervisor/refactor_goals.json | 6 +++---`
  - ` docs/REFACTOR_SUPERVISOR_TASKBOARD.md        | 8 ++++----`
  - ` integrations/ipfs_datasets/loader.py         | 4 ++++`
  - ` tests/test_package_imports.py                | 2 ++`
  - ` 4 files changed, 13 insertions(+), 7 deletions(-)`

## Sample Branches Or Worktrees

- `implementation/ref-001-attempt-1-1784661950` at `/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-001-attempt-1-1784661950`
- `implementation/ref-028-attempt-1-1784669974` at `/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-028-attempt-1-1784669974`

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

Work surface: `2` candidates, `2` sampled records.

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
  "candidate_count": 2,
  "conflict_path_counts": {},
  "dedupe_key": "reconciliation_guardrail:main_checkout_dirty",
  "fingerprint": "ebc903c15c398edeb9eabd86f6eaa1fc3e15fab8",
  "kind": "main_checkout_dirty",
  "main_dirty_evidence": {
    "diff_stat": "data/refactor_supervisor/refactor_goals.json | 6 +++---\n docs/REFACTOR_SUPERVISOR_TASKBOARD.md        | 8 ++++----\n integrations/ipfs_datasets/loader.py         | 4 ++++\n tests/test_package_imports.py                | 2 ++\n 4 files changed, 13 insertions(+), 7 deletions(-)",
    "name_status": "M\tdata/refactor_supervisor/refactor_goals.json\nM\tdocs/REFACTOR_SUPERVISOR_TASKBOARD.md\nM\tintegrations/ipfs_datasets/loader.py\nM\ttests/test_package_imports.py",
    "path_categories": {
      "modified": 4
    },
    "status_paths": [
      "data/refactor_supervisor/refactor_goals.json",
      "docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
      "integrations/ipfs_datasets/loader.py",
      "tests/test_package_imports.py"
    ],
    "status_short": [
      " M data/refactor_supervisor/refactor_goals.json",
      " M docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
      " M integrations/ipfs_datasets/loader.py",
      " M tests/test_package_imports.py"
    ]
  },
  "reason": "main_checkout_dirty",
  "safety_constraints": [
    "Do not discard dirty or untracked content unless it is proven redundant with the target ref.",
    "Prefer commits, merges, or explicit follow-up tasks over destructive cleanup.",
    "Keep todo, objective, discovery, and strategy files parseable after reconciliation."
  ],
  "sample_branches": [
    "implementation/ref-001-attempt-1-1784661950",
    "implementation/ref-028-attempt-1-1784669974"
  ],
  "sample_count": 2,
  "sample_status_paths": [
    "data/refactor_supervisor/refactor_goals.json",
    "docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
    "integrations/ipfs_datasets/loader.py",
    "tests/test_package_imports.py"
  ],
  "sample_worktrees": [
    "/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-001-attempt-1-1784661950",
    "/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-028-attempt-1-1784669974"
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
