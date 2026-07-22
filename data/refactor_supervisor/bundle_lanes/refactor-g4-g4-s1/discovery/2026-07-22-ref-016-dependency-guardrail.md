# Dependency Guardrail: REF-015

Created: 2026-07-22T04:29:35.421287+00:00
Fingerprint: 956e7e88cb97153337d06c8872b5706bf00dab88
Source task: REF-015 Duplicate task id
Missing dependencies: none
Self-referential dependencies: none
Dependency cycle: none
Duplicate task id: REF-015
Duplicate source lines: 49, 63

## Duplicate Task Titles

- Resolve dirty main checkout blocking 1 worktree merges
- Resolve dirty main checkout blocking 2 worktree merges

## Why This Blocks Progress

The implementation daemon only selects tasks whose dependencies are completed.
When an open task depends on a task id that is not present on the board, or on
itself, or participates in a dependency cycle, the task can remain waiting
indefinitely while the supervisor reports no ready work. Duplicate task ids are
also ambiguous because status maps, dependency resolution, and guardrail
releases all key by task id.

## Suggested Repair

Inspect the source task metadata and either add the missing prerequisite task,
remove the stale dependency, break the dependency cycle, rename duplicate task
ids so each task is unique, or replace stale references with the correct existing
task id. Keep the todo board parseable after the repair.
