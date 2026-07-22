# Objective Bundle: refactor/g4/g4-s1

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [ ] Task checkbox-13: REF-013 Define smoke, adapter, mediator, document, and UI test lanes

## REF-013 Define smoke, adapter, mediator, document, and UI test lanes

- Status: todo
- Completion: manual
- Priority: P1
- Track: G4
- Depends on: 
- Outputs: pytest.ini, Makefile, docs/VERIFICATION_SUMMARY.md
- Validation: python -m pytest --collect-only -q
- Bundle: refactor/g4/g4-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G4.S1
- Missing evidence: The repo has many tests; refactor agents need fast confidence lanes.
- AST symbols: 
- Merge key: refactor/g4/g4-s1
- Candidate kind: seed
- Todo vector key: ref-013-definesmokeadaptermediatordocumentanduitestlanes
- Acceptance: A documented test lane map exists.; Each P0 workstream has a named validation command.

- [x] Task checkbox-14: REF-014 Add import and dependency-boundary tests for production modules

## REF-014 Add import and dependency-boundary tests for production modules

- Status: completed
- Completion: manual
- Priority: P1
- Track: G4
- Depends on: 
- Outputs: tests, pyproject.toml
- Validation: python -m pytest tests/test_package_imports.py -q
- Bundle: refactor/g4/g4-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G4.S1
- Missing evidence: Dependency drift is a recurring refactor risk.
- AST symbols: 
- Merge key: refactor/g4/g4-s1
- Candidate kind: seed
- Todo vector key: ref-014-addimportanddependency-boundarytestsforproductio
- Acceptance: Tests catch direct production imports where adapters are required.; Tests avoid blocking intentional test-only imports.

## REF-015 Resolve dirty main checkout blocking 1 worktree merges

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Fingerprint: 3a2a8187bdd6c81d29b026a91c15be4cd0d6dc4f
- Dedupe key: reconciliation_guardrail:main_checkout_dirty
- Depends on:
- Outputs: data/refactor_supervisor/bundle_lanes/refactor-g4-g4-s1/discovery, data/refactor_supervisor/objective_bundles/refactor-g4-g4-s1.todo.md
- Validation: test -f /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g4-g4-s1/discovery/2026-07-22-ref-015-reconciliation-c66aac1f89b6.md
- Acceptance: Reconciliation guardrail filed this because 1 branch or worktree cleanup candidates are blocked by main_checkout_dirty. Use evidence and the machine-readable reconciliation plan in /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g4-g4-s1/discovery/2026-07-22-ref-015-reconciliation-c66aac1f89b6.md, reconcile the dirty checkout or dirty worktree group deliberately, then rerun the supervisor cleanup/reconciliation pass and confirm that the blocked candidate count decreases.
- Reconciliation result: REF-014 commit `4ff79d0` was merged into `main` by `93bf1f4` and its sampled branch/worktree were removed. The scoped reconciliation-only pass at `2026-07-22T04:09:01Z` reported `main_checkout_dirty: false`, `candidate_count` decreased from `1` to `0`, and no dirty worktree groups; separate REF-013 dirt was preserved on rescue commit `3aa48e9` rather than discarded.

## REF-017 Resolve dirty main checkout blocking 2 worktree merges

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Fingerprint: b594c6a97b301266455d1e44271d960d8bf7b21c
- Dedupe key: reconciliation_guardrail:main_checkout_dirty
- Depends on:
- Outputs: data/refactor_supervisor/bundle_lanes/refactor-g4-g4-s1/discovery, data/refactor_supervisor/objective_bundles/refactor-g4-g4-s1.todo.md
- Validation: test -f /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g4-g4-s1/discovery/2026-07-22-ref-015-reconciliation-c66aac1f89b6.md
- Acceptance: Reconciliation guardrail filed this because 2 branch or worktree cleanup candidates are blocked by main_checkout_dirty. Use evidence and the machine-readable reconciliation plan in /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g4-g4-s1/discovery/2026-07-22-ref-015-reconciliation-c66aac1f89b6.md, reconcile the dirty checkout or dirty worktree group deliberately, then rerun the supervisor cleanup/reconciliation pass and confirm that the blocked candidate count decreases.

## REF-016 Resolve dependency guardrail for REF-015

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Depends on:
- Outputs: data/refactor_supervisor/bundle_lanes/refactor-g4-g4-s1/discovery, data/refactor_supervisor/objective_bundles/refactor-g4-g4-s1.todo.md
- Validation: test -f /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g4-g4-s1/discovery/2026-07-22-ref-016-dependency-guardrail.md
- Acceptance: Dependency guardrail filed this because REF-015 has missing, self-referential, cyclic, or duplicate task-id metadata. Use the evidence in /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g4-g4-s1/discovery/2026-07-22-ref-016-dependency-guardrail.md to repair the todo board metadata or add the missing prerequisite task, then verify the original task can become ready once its real dependencies complete.
- Dependency resolution: Preserved the original reconciliation task as REF-015 and reassigned the later, distinct reconciliation snapshot to the unused board-local id REF-017. REF-015 has no task prerequisites; the dependency guardrail reports no remaining findings, so an open REF-015 would be ready immediately.
