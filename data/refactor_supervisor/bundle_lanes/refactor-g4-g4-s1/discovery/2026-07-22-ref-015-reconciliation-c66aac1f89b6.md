# REF-015 Reconciliation Guardrail

Date: 2026-07-22
Fingerprint: b594c6a97b301266455d1e44271d960d8bf7b21c
Kind: main_checkout_dirty
Reason: main_checkout_dirty
Candidate count: 2
Priority: P1
Track: ops

## Main Checkout Status

- ` M data/refactor_supervisor/bundle_lanes/bundle_lanes.json`
- ` M data/refactor_supervisor/objective_bundles/refactor-g8-g8-s1.todo.md`
- `?? data/refactor_supervisor/bundle_lanes/refactor-g8-g8-s1/`

## Main Checkout Evidence

- Path categories: `modified=2, untracked=1`
- Status paths:
  - `data/refactor_supervisor/bundle_lanes/bundle_lanes.json`
  - `data/refactor_supervisor/objective_bundles/refactor-g8-g8-s1.todo.md`
  - `data/refactor_supervisor/bundle_lanes/refactor-g8-g8-s1`
- Name status:
  - `M	data/refactor_supervisor/bundle_lanes/bundle_lanes.json`
  - `M	data/refactor_supervisor/objective_bundles/refactor-g8-g8-s1.todo.md`
- Diff stat:
  - `.../bundle_lanes/bundle_lanes.json                 | 937345 +++++++++++++++++-`
  - ` .../objective_bundles/refactor-g8-g8-s1.todo.md    |     13 +`
  - ` 2 files changed, 937134 insertions(+), 224 deletions(-)`
- Untracked paths:
  - `data/refactor_supervisor/bundle_lanes/refactor-g8-g8-s1`

## Sample Branches Or Worktrees

- `rescue/worktree/implementation-ref-013-d4fc48536ac0-attempt-1-1784693051-3c65dce8f628` at `/home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g4-g4-s1/ref-013-d4fc48536ac0-attempt-1-1784693051`
- `implementation/ref-015-25ad7db2c606-attempt-1-1784693208` at `/home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g4-g4-s1/ref-015-25ad7db2c606-attempt-1-1784693208`

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
  "fingerprint": "b594c6a97b301266455d1e44271d960d8bf7b21c",
  "kind": "main_checkout_dirty",
  "main_dirty_evidence": {
    "diff_stat": ".../bundle_lanes/bundle_lanes.json                 | 937345 +++++++++++++++++-\n .../objective_bundles/refactor-g8-g8-s1.todo.md    |     13 +\n 2 files changed, 937134 insertions(+), 224 deletions(-)",
    "name_status": "M\tdata/refactor_supervisor/bundle_lanes/bundle_lanes.json\nM\tdata/refactor_supervisor/objective_bundles/refactor-g8-g8-s1.todo.md",
    "path_categories": {
      "modified": 2,
      "untracked": 1
    },
    "status_paths": [
      "data/refactor_supervisor/bundle_lanes/bundle_lanes.json",
      "data/refactor_supervisor/objective_bundles/refactor-g8-g8-s1.todo.md",
      "data/refactor_supervisor/bundle_lanes/refactor-g8-g8-s1"
    ],
    "status_short": [
      " M data/refactor_supervisor/bundle_lanes/bundle_lanes.json",
      " M data/refactor_supervisor/objective_bundles/refactor-g8-g8-s1.todo.md",
      "?? data/refactor_supervisor/bundle_lanes/refactor-g8-g8-s1/"
    ],
    "untracked_paths": [
      "data/refactor_supervisor/bundle_lanes/refactor-g8-g8-s1"
    ]
  },
  "reason": "main_checkout_dirty",
  "safety_constraints": [
    "Do not discard dirty or untracked content unless it is proven redundant with the target ref.",
    "Prefer commits, merges, or explicit follow-up tasks over destructive cleanup.",
    "Keep todo, objective, discovery, and strategy files parseable after reconciliation."
  ],
  "sample_branches": [
    "rescue/worktree/implementation-ref-013-d4fc48536ac0-attempt-1-1784693051-3c65dce8f628",
    "implementation/ref-015-25ad7db2c606-attempt-1-1784693208"
  ],
  "sample_count": 2,
  "sample_status_paths": [
    "data/refactor_supervisor/bundle_lanes/bundle_lanes.json",
    "data/refactor_supervisor/objective_bundles/refactor-g8-g8-s1.todo.md",
    "data/refactor_supervisor/bundle_lanes/refactor-g8-g8-s1"
  ],
  "sample_worktrees": [
    "/home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g4-g4-s1/ref-013-d4fc48536ac0-attempt-1-1784693051",
    "/home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g4-g4-s1/ref-015-25ad7db2c606-attempt-1-1784693208"
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

## Reconciliation Result

Resolved: 2026-07-22T04:09:01Z

The original blocker was reconciled without discarding checkout or worktree
content:

- The sampled REF-014 implementation commit `4ff79d0` was merged into `main`
  by merge commit `93bf1f4`; commit `3bd1384` then recorded REF-014 as
  completed. `git merge-base --is-ancestor 4ff79d0 main` returned `0`.
- The sampled worktree and branch
  `implementation/ref-014-0fe33c0cb7c7-attempt-1-1784692026` no longer exist,
  so they are no longer blocked by the dirty-checkout guardrail.
- The original dirty path was classified as generated supervisor lane-registry
  state. It remained parseable as JSON and was not discarded. The shared main
  checkout continued to receive later supervisor-generated updates while this
  isolated task ran; those later changes were left with their active owner and
  are not attributed to the closed REF-014 candidate.
- The cleanup phase found separate, uncommitted REF-013 worktree changes in
  `docs/REFACTOR_SUPERVISOR_TASKBOARD.md` and
  `tests/test_package_imports.py`. It preserved them on rescue branch
  `rescue/worktree/implementation-ref-013-d4fc48536ac0-attempt-1-1784693051-3c65dce8f628`
  at commit `3aa48e9387d60150d6076030c85b59b5b623368f` rather than deleting them.
  The rerun consequently reported no remaining dirty worktree group.

The scoped reconciliation-only rerun was executed from the clean REF-015
checkout with scan caching disabled:

```sh
PYTHONPATH=/home/barberb/complaint-generator/ipfs_datasets_py/ipfs_accelerate_py \
python -m ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_supervisor \
  --once --reconciliation-only \
  --todo-path "$PWD/data/refactor_supervisor/objective_bundles/refactor-g4-g4-s1.todo.md" \
  --state-dir "$PWD/data/refactor_supervisor/bundle_lanes/refactor-g4-g4-s1/state" \
  --state-prefix agent_refactor_g4_g4_s1_ref015 \
  --task-prefix REF- \
  --worktree-root /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/worktrees/refactor-g4-g4-s1 \
  --worktree-submodule-path ipfs_datasets_py/ipfs_accelerate_py \
  --worktree-reconciliation-max-merges 1 \
  --worktree-reconciliation-dry-run \
  --no-worktree-scan-cache \
  --log-level INFO
```

Fresh result:

- `target_signature`: `3bd1384fba462c47362f62b2ab5b39e3681c925d`
- `main_checkout_dirty`: `false`
- `raw_main_checkout_dirty`: `false`
- `candidate_count`: decreased from `1` to `0`
- `preflight_blocked_count`: `0`
- `dirty_worktree_group_count`: `0`
- REF-013 cleanup disposition: `dirty_worktree_rescued`

The ignored lane event log
`data/refactor_supervisor/bundle_lanes/refactor-g4-g4-s1/state/agent_refactor_g4_g4_s1_ref015_supervisor_events.jsonl`
records the `2026-07-22T04:09:01.698289+00:00` supervisor check with zero
reconciliation candidates and zero dirty worktree groups.

### Machine Readable Result

```json
{
  "blocked_candidate_count_after": 0,
  "blocked_candidate_count_before": 1,
  "candidate_branch": "implementation/ref-014-0fe33c0cb7c7-attempt-1-1784692026",
  "candidate_commit": "4ff79d0",
  "candidate_merge_commit": "93bf1f4",
  "candidate_worktree_present_after": false,
  "dirty_worktree_group_count_after": 0,
  "main_checkout_dirty_after_scoped_rerun": false,
  "preflight_blocked_count_after": 0,
  "reconciliation_rerun_at": "2026-07-22T04:09:01.698289+00:00",
  "reconciliation_target_signature": "3bd1384fba462c47362f62b2ab5b39e3681c925d",
  "rescued_worktree_commit": "3aa48e9387d60150d6076030c85b59b5b623368f",
  "rescued_worktree_ref": "rescue/worktree/implementation-ref-013-d4fc48536ac0-attempt-1-1784693051-3c65dce8f628",
  "result": "resolved"
}
```
