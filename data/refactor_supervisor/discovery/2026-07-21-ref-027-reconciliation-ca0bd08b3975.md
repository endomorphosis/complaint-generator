# REF-027 Reconciliation Guardrail

Date: 2026-07-22
Fingerprint: bc2e46a8c33920d52a1c6229e6655e4950c6f80c
Kind: main_checkout_dirty
Reason: main_checkout_dirty
Candidate count: 4
Priority: P1
Track: ops

## Main Checkout Status

- `?? data/refactor_supervisor/merge_resolver_registry/`

## Main Checkout Evidence

- Path categories: `untracked=1`
- Status paths:
  - `data/refactor_supervisor/merge_resolver_registry`
- Untracked paths:
  - `data/refactor_supervisor/merge_resolver_registry`

## Sample Branches Or Worktrees

- `implementation/ref-005-a73e3df5fb38-attempt-1-1784693241` at `/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-005-a73e3df5fb38-attempt-1-1784693241`
- `implementation/ref-006-98d6193364c1-attempt-1-1784693668` at `/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-006-98d6193364c1-attempt-1-1784693668`
- `rescue/worktree/implementation-ref-016-30a2a7d729bd-attempt-1-1784688023-807bc7a20043` at `/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-016-30a2a7d729bd-attempt-1-1784688023`
- `rescue/worktree/implementation-ref-016-30a2a7d729bd-attempt-1-1784690090-6077ba322261` at `/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-016-30a2a7d729bd-attempt-1-1784690090`

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

Work surface: `4` candidates, `4` sampled records.

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
  "candidate_count": 4,
  "conflict_path_counts": {},
  "dedupe_key": "reconciliation_guardrail:main_checkout_dirty",
  "fingerprint": "bc2e46a8c33920d52a1c6229e6655e4950c6f80c",
  "kind": "main_checkout_dirty",
  "main_dirty_evidence": {
    "path_categories": {
      "untracked": 1
    },
    "status_paths": [
      "data/refactor_supervisor/merge_resolver_registry"
    ],
    "status_short": [
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
    "implementation/ref-005-a73e3df5fb38-attempt-1-1784693241",
    "implementation/ref-006-98d6193364c1-attempt-1-1784693668",
    "rescue/worktree/implementation-ref-016-30a2a7d729bd-attempt-1-1784688023-807bc7a20043",
    "rescue/worktree/implementation-ref-016-30a2a7d729bd-attempt-1-1784690090-6077ba322261"
  ],
  "sample_count": 4,
  "sample_status_paths": [
    "data/refactor_supervisor/merge_resolver_registry"
  ],
  "sample_worktrees": [
    "/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-005-a73e3df5fb38-attempt-1-1784693241",
    "/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-006-98d6193364c1-attempt-1-1784693668",
    "/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-016-30a2a7d729bd-attempt-1-1784688023",
    "/home/barberb/complaint-generator/data/refactor_supervisor/worktrees/ref-016-30a2a7d729bd-attempt-1-1784690090"
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
