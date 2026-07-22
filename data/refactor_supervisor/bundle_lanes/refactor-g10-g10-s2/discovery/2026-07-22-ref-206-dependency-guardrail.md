# Dependency Guardrail: REF-203

Created: 2026-07-22T19:15:30.581498+00:00
Fingerprint: edc220700521cb9aef984deb96ec6588a4249ae7
Source task: REF-203 Add analyzer canaries, parser failure budgets, and fail-closed health classification
Missing dependencies: REF-201
Self-referential dependencies: none
Dependency cycle: none
Duplicate task id: none
Duplicate source lines: none

## Duplicate Task Titles

- none

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
