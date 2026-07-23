# Objective Bundle: refactor/g11/g11-s1

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [ ] Task checkbox-244: REF-244 Probe formal-logic providers, toolchains, and optional dependency health

## REF-244 Probe formal-logic providers, toolchains, and optional dependency health

- Status: todo
- Completion: manual
- Priority: P0
- Track: G11
- Depends on:
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/docs/architecture/AGENT_SUPERVISOR_FORMAL_VERIFICATION_PLAN.md, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_capabilities.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_capabilities.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_capabilities.py -q
- Bundle: refactor/g11/g11-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S1
- Missing evidence: The supervisor needs a truthful runtime capability matrix before it can route or require proof work.
- AST symbols: 
- Merge key: refactor/g11/g11-s1
- Candidate kind: seed
- Todo vector key: ref-244-probeformal-logicproviderstoolchainsandoptionald
- Acceptance: A versioned capability report covers Hammer, TDFOL, external provers, Lean, Leanstral, frame logic, knowledge graphs, and ZKP backends.; Provider, executable, package, model, circuit, and optional dependency health are reported separately.; Missing spaCy, model weights, Python bindings, or prover executables produce explicit degraded or unavailable reasons without breaking supervisor import.; Capability probes are bounded, cacheable, and never count availability as proof success.

- [ ] Task checkbox-245: REF-245 Define canonical proof obligations, plans, receipts, and assurance levels

## REF-245 Define canonical proof obligations, plans, receipts, and assurance levels

- Status: todo
- Completion: manual
- Priority: P0
- Track: G11
- Depends on:
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_contracts.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_contracts.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_contracts.py -q
- Bundle: refactor/g11/g11-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S1
- Missing evidence: Proof-aware scheduling needs one versioned contract and a sound trust lattice shared by providers, caches, merge gates, and goal evidence.
- AST symbols: 
- Merge key: refactor/g11/g11-s1
- Candidate kind: seed
- Todo vector key: ref-245-definecanonicalproofobligationsplansreceiptsanda
- Acceptance: CodeProofObligation, ProofPlan, ProofAttempt, ProofReceipt, and assurance enums have deterministic JSON encodings and content identities.; Receipts bind repository trees, AST scopes, premises, translators, solvers, kernels, toolchains, policy, and resource budgets.; Authoritative assurance is derived from evidence and cannot be asserted directly by a provider.; LLM output, ATP or SMT candidates, stale cache entries, and simulated ZKP cannot become kernel-verified or attested.

- [ ] Task checkbox-246: REF-246 Introduce an optional isolated proof-provider protocol

## REF-246 Introduce an optional isolated proof-provider protocol

- Status: todo
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-244, REF-245
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_provider.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_capabilities.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_provider.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_provider.py -q
- Bundle: refactor/g11/g11-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S1
- Missing evidence: A mandatory import from the acceleration submodule into its parent datasets package would create a brittle package and submodule cycle.
- AST symbols: 
- Merge key: refactor/g11/g11-s1
- Candidate kind: seed
- Todo vector key: ref-246-introduceanoptionalisolatedproof-providerprotoco
- Acceptance: A versioned provider protocol supports capability, translate, prove, reconstruct, verify, and attest operations.; Providers can be discovered lazily in process or invoked through a bounded subprocess JSON protocol.; Timeout, cancellation, resource, network, and malformed-response failures are explicit and fail closed.; The supervisor imports and runs with no ipfs_datasets_py proof provider installed.

- [ ] Task checkbox-247: REF-247 Define risk-selected proof and rollout policy

## REF-247 Define risk-selected proof and rollout policy

- Status: todo
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-245
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_policy.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_policy.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_policy.py -q
- Bundle: refactor/g11/g11-s1
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S1
- Missing evidence: Formal verification should protect modeled high-risk invariants without blocking unrelated or unsupported Python changes.
- AST symbols: 
- Merge key: refactor/g11/g11-s1
- Candidate kind: seed
- Todo vector key: ref-247-definerisk-selectedproofandrolloutpolicy
- Acceptance: Policy maps changed paths, AST scopes, risk, and invariant classes to required assurance and fallback validation.; Disabled, shadow, canary, and enforcement modes have explicit promotion and override behavior.; Unsupported, unavailable, timed-out, and inconclusive results cannot silently satisfy an enforcement gate.; Overrides require bounded scope, actor, reason, expiration, and a durable receipt.
