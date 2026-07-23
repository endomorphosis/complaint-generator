# Objective Bundle: refactor/g11/g11-s1

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-244: REF-244 Probe formal-logic providers, toolchains, and optional dependency health

## REF-244 Probe formal-logic providers, toolchains, and optional dependency health

- Status: completed
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
- AST symbols: FORMAL_VERIFICATION_CAPABILITY_SCHEMA_VERSION, FORMAL_VERIFICATION_CAPABILITY_REPORT_VERSION, PROOF_PROVIDER_CAPABILITY_SCHEMA_VERSION, DEFAULT_CAPABILITY_CACHE_TTL_SECONDS, DEFAULT_CAPABILITY_PROBE_TIMEOUT_SECONDS, DEFAULT_CAPABILITY_PROBE_MAX_CHECKS, CapabilityHealth, CapabilityDimension, ProofProviderOperation, ProofProviderIsolation, _PROVIDER_OPERATION_ORDER, ProofProviderCapability, ProviderCapabilities, _DIMENSION_ORDER, CapabilityHealthCheck, FormalVerificationProviderCapability, FormalVerificationCapabilityReport, FormalVerificationProbeConfig, PackageFinder, ExecutableFinder, DistributionVersionFinder, _find_spec_without_import, FormalVerificationCapabilityProbe, _DEFAULT_PROBE, probe_formal_verification_capabilities, clear_formal_verification_capability_cache, __all__, AVAILABLE, DEGRADED, UNAVAILABLE
- Merge key: refactor/g11/g11-s1
- Candidate kind: seed
- Todo vector key: ref-244-probeformal-logicproviderstoolchainsandoptionald
- Acceptance: A versioned capability report covers Hammer, TDFOL, external provers, Lean, Leanstral, frame logic, knowledge graphs, and ZKP backends.; Provider, executable, package, model, circuit, and optional dependency health are reported separately.; Missing spaCy, model weights, Python bindings, or prover executables produce explicit degraded or unavailable reasons without breaking supervisor import.; Capability probes are bounded, cacheable, and never count availability as proof success.

- [x] Task checkbox-245: REF-245 Define canonical proof obligations, plans, receipts, and assurance levels

## REF-245 Define canonical proof obligations, plans, receipts, and assurance levels

- Status: completed
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
- AST symbols: CONTRACT_VERSION, SCHEMA_VERSION, CODE_PROOF_OBLIGATION_SCHEMA, PROOF_PLAN_SCHEMA, PROOF_PLAN_STEP_SCHEMA, PROOF_ATTEMPT_SCHEMA, PROOF_RECEIPT_SCHEMA, PROOF_EVIDENCE_SCHEMA, RESOURCE_BUDGET_SCHEMA, ASSURANCE_ASSESSMENT_SCHEMA, ContractValidationError, AssuranceLevel, RequiredAssuranceLevel, AuthoritativeAssuranceLevel, ProofAssuranceLevel, ProofStage, AttemptStatus, ProofVerdict, EvidenceKind, ProofEvidenceKind, EvidenceAuthority, EvidenceVerdict, EvidenceFreshness, TEnum, _enum, _canonical_value, canonical_json_bytes, canonical_json, content_identity, _text
- Merge key: refactor/g11/g11-s1
- Candidate kind: seed
- Todo vector key: ref-245-definecanonicalproofobligationsplansreceiptsanda
- Acceptance: CodeProofObligation, ProofPlan, ProofAttempt, ProofReceipt, and assurance enums have deterministic JSON encodings and content identities.; Receipts bind repository trees, AST scopes, premises, translators, solvers, kernels, toolchains, policy, and resource budgets.; Authoritative assurance is derived from evidence and cannot be asserted directly by a provider.; LLM output, ATP or SMT candidates, stale cache entries, and simulated ZKP cannot become kernel-verified or attested.

- [x] Task checkbox-246: REF-246 Introduce an optional isolated proof-provider protocol

## REF-246 Introduce an optional isolated proof-provider protocol

- Status: completed
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
- AST symbols: PROOF_PROVIDER_PROTOCOL_VERSION, PROOF_PROVIDER_SUPPORTED_PROTOCOL_VERSIONS, PROOF_PROVIDER_REQUEST_SCHEMA, PROOF_PROVIDER_RESPONSE_SCHEMA, PROOF_PROVIDER_ENTRY_POINT_GROUP, PROOF_PROVIDER_ENVIRONMENT, DEFAULT_PROVIDER_TIMEOUT_SECONDS, DEFAULT_PROVIDER_MAX_REQUEST_BYTES, DEFAULT_PROVIDER_MAX_RESPONSE_BYTES, DEFAULT_PROVIDER_MEMORY_BYTES, DEFAULT_PROVIDER_CPU_TIME_SECONDS, DEFAULT_PROVIDER_MAX_PROCESSES, ProviderFailureCode, ProviderFailure, ProofProviderError, ProviderInvocationError, NetworkAccessDenied, CancellationToken, _json_value, _json_object, _object_without_duplicate_keys, _strict_json_loads, _resource_budget, ProviderRequest, ProviderResponse, ProofProvider, ProviderInvocationConfig, _request_timeout, _duration_ms, _exception_failure
- Merge key: refactor/g11/g11-s1
- Candidate kind: seed
- Todo vector key: ref-246-introduceanoptionalisolatedproof-providerprotoco
- Acceptance: A versioned provider protocol supports capability, translate, prove, reconstruct, verify, and attest operations.; Providers can be discovered lazily in process or invoked through a bounded subprocess JSON protocol.; Timeout, cancellation, resource, network, and malformed-response failures are explicit and fail closed.; The supervisor imports and runs with no ipfs_datasets_py proof provider installed.

- [x] Task checkbox-247: REF-247 Define risk-selected proof and rollout policy

## REF-247 Define risk-selected proof and rollout policy

- Status: completed
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
- AST symbols: POLICY_VERSION, SCHEMA_VERSION, CHANGED_SCOPE_SCHEMA, PROOF_POLICY_RULE_SCHEMA, PROOF_REQUIREMENT_SCHEMA, POLICY_SELECTION_SCHEMA, FORMAL_VERIFICATION_POLICY_SCHEMA, PROOF_OUTCOME_SCHEMA, VALIDATION_OUTCOME_SCHEMA, OVERRIDE_RECEIPT_SCHEMA, ROLLOUT_TRANSITION_RECEIPT_SCHEMA, REQUIREMENT_GATE_RESULT_SCHEMA, POLICY_GATE_DECISION_SCHEMA, MAX_SCOPE_ITEMS, MAX_OVERRIDE_LIFETIME_SECONDS, DEFAULT_MAX_OVERRIDE_SECONDS, PolicyValidationError, RiskLevel, InvariantClass, RolloutMode, ProofResultStatus, _enum, _text, _strings, _mapping, _integer, _normalize_git_path, _normalize_path_pattern, _path_matches, _timestamp
- Merge key: refactor/g11/g11-s1
- Candidate kind: seed
- Todo vector key: ref-247-definerisk-selectedproofandrolloutpolicy
- Acceptance: Policy maps changed paths, AST scopes, risk, and invariant classes to required assurance and fallback validation.; Disabled, shadow, canary, and enforcement modes have explicit promotion and override behavior.; Unsupported, unavailable, timed-out, and inconclusive results cannot silently satisfy an enforcement gate.; Overrides require bounded scope, actor, reason, expiration, and a durable receipt.

## REF-350 Close objective gap: Establish proof contracts, capabilities, and trust policy

- Status: todo
- Completion: manual
- Priority: P0
- Track: ops
- Depends on:
- Outputs: data/refactor_supervisor/discovery, data/refactor_supervisor/refactor_objective_heap.md
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_capabilities.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_contracts.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_provider.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_policy.py -q
- Bundle: refactor/g11/g11-s1
- Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g11-g11-s1.todo.md
- Bundle strategy: explicit
- Graph parents: G11
- Graph depth: 1
- Parallel lane: refactor/g11/g11-s1
- Conflict policy: prefer bundle-local changes; invoke the LLM merge resolver for semantic conflicts
- Predicted files:
- Changed paths:
- AST symbols: ipfs_datasets_py/ipfs_accelerate_py/docs/architecture/AGENT_SUPERVISOR_FORMAL_VERIFICATION_PLAN.md, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_capabilities.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_capabilities.py, A versioned capability report covers Hammer, TDFOL, external provers, Lean, Leanstral, frame logic, knowledge graphs, and ZKP backends., Provider, executable, package, model, circuit, and optional dependency health are reported separately., Missing spaCy, model weights, Python bindings, or prover executables produce explicit degraded or unavailable reasons without breaking supervisor import., Capability probes are bounded, cacheable, and never count availability as proof success., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_capabilities.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_contracts.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_contracts.py, CodeProofObligation, ProofPlan, ProofAttempt, ProofReceipt, and assurance enums have deterministic JSON encodings and content identities., Receipts bind repository trees, AST scopes, premises, translators, solvers, kernels, toolchains, policy, and resource budgets., Authoritative assurance is derived from evidence and cannot be asserted directly by a provider., LLM output, ATP or SMT candidates, stale cache entries, and simulated ZKP cannot become kernel-verified or attested., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_contracts.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_provider.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_provider.py, A versioned provider protocol supports capability, translate, prove, reconstruct, verify, and attest operations., Providers can be discovered lazily in process or invoked through a bounded subprocess JSON protocol., Timeout, cancellation, resource, network, and malformed-response failures are explicit and fail closed., The supervisor imports and runs with no ipfs_datasets_py proof provider installed., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_provider.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_policy.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_policy.py, Policy maps changed paths, risk, and invariant classes to required assurance and fallback validation., Disabled, shadow, canary, and enforcement modes have explicit promotion and override behavior., Unsupported, unavailable, timed-out, and inconclusive results cannot silently satisfy an enforcement gate., Overrides require bounded scope, actor, reason, expiration, and a durable receipt., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_policy.py -q, data/refactor_supervisor/discovery/2026-07-23-ref-307-objective-validation-repair.md, objective validation repair
- Interfaces:
- Submodules:
- Generated artifacts:
- Allow concurrent with:
- Goal id: G11.S1
- Canonical task key: task/v1/e67c6a7f4d6478eca87804c5be1faff4310d48ac1dd3b230ecf2b975d7e01f83
- Canonical task CID: baguqeera4z6gu72nmr4ozkdyatc34h5p6qyq2sfmdxj3emhm6k4xlv7ad6bq
- Missing evidence: objective validation repair
- Embedding query: Establish proof contracts, capabilities, and trust policy
- AST query: ipfs_datasets_py/ipfs_accelerate_py/docs/architecture/AGENT_SUPERVISOR_FORMAL_VERIFICATION_PLAN.md, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_capabilities.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_capabilities.py, A versioned capability report covers Hammer, TDFOL, external provers, Lean, Leanstral, frame logic, knowledge graphs, and ZKP backends., Provider, executable, package, model, circuit, and optional dependency health are reported separately., Missing spaCy, model weights, Python bindings, or prover executables produce explicit degraded or unavailable reasons without breaking supervisor import., Capability probes are bounded, cacheable, and never count availability as proof success., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_capabilities.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_contracts.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_contracts.py, CodeProofObligation, ProofPlan, ProofAttempt, ProofReceipt, and assurance enums have deterministic JSON encodings and content identities., Receipts bind repository trees, AST scopes, premises, translators, solvers, kernels, toolchains, policy, and resource budgets., Authoritative assurance is derived from evidence and cannot be asserted directly by a provider., LLM output, ATP or SMT candidates, stale cache entries, and simulated ZKP cannot become kernel-verified or attested., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_contracts.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_provider.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_provider.py, A versioned provider protocol supports capability, translate, prove, reconstruct, verify, and attest operations., Providers can be discovered lazily in process or invoked through a bounded subprocess JSON protocol., Timeout, cancellation, resource, network, and malformed-response failures are explicit and fail closed., The supervisor imports and runs with no ipfs_datasets_py proof provider installed., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_provider.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_policy.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_policy.py, Policy maps changed paths, AST scopes, risk, and invariant classes to required assurance and fallback validation., Disabled, shadow, canary, and enforcement modes have explicit promotion and override behavior., Unsupported, unavailable, timed-out, and inconclusive results cannot silently satisfy an enforcement gate., Overrides require bounded scope, actor, reason, expiration, and a durable receipt., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_policy.py -q, data/refactor_supervisor/discovery/2026-07-23-ref-307-objective-validation-repair.md, objective validation repair
- Surplus group: objective/G11.S1
- Merge key: 8632255e87745d9d
- Merge family: goal_packet/ops/ipfs_datasets_py/c4bb9eba851b
- Merge role: validation_gate
- Work item count: 1
- Work scope: objective_validation_repair; goal_subgoal_packet
- Goal packet: goal_packet/ops/ipfs_datasets_py/c4bb9eba851b
- Goal packet role: packet_member
- Goal packet goals: G11, G11.S1, G11.S2, G11.S3, G11.S4, G11.S7
- Goal packet task count: 6
- Goal packet work item count: 6
- Candidate kind: validation_gate
- Todo vector key: 78e738b038ca0422
- Acceptance: Objective scan filed this gap for G11.S1. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-350-objective-gap-17980a8aba65.md, add code/tests/docs or child goals that prove the missing evidence terms are covered (objective validation repair), and keep the supervisor-fed backlog aligned with the objective heap. This task is part of goal_packet/ops/ipfs_datasets_py/c4bb9eba851b; implement a complete, cohesive change that fully advances the packet goals (G11, G11.S1, G11.S2, G11.S3, G11.S4, G11.S7) and covers all the shared packet evidence in one comprehensive pass. Refine the objective heap if the gap needs smaller child goals.

## REF-356 Close objective gap: Establish proof contracts, capabilities, and trust policy

- Status: todo
- Completion: manual
- Priority: P0
- Track: ops
- Depends on:
- Outputs: data/refactor_supervisor/discovery, data/refactor_supervisor/refactor_objective_heap.md
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_capabilities.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_contracts.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_provider.py -q; PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_policy.py -q
- Bundle: refactor/g11/g11-s1
- Bundle shard: data/refactor_supervisor/objective_bundles/refactor-g11-g11-s1.todo.md
- Bundle strategy: explicit
- Graph parents: G11
- Graph depth: 1
- Parallel lane: refactor/g11/g11-s1
- Conflict policy: prefer bundle-local changes; invoke the LLM merge resolver for semantic conflicts
- Predicted files:
- Changed paths:
- AST symbols: ipfs_datasets_py/ipfs_accelerate_py/docs/architecture/AGENT_SUPERVISOR_FORMAL_VERIFICATION_PLAN.md, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_capabilities.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_capabilities.py, A versioned capability report covers Hammer, TDFOL, external provers, Lean, Leanstral, frame logic, knowledge graphs, and ZKP backends., Provider, executable, package, model, circuit, and optional dependency health are reported separately., Missing spaCy, model weights, Python bindings, or prover executables produce explicit degraded or unavailable reasons without breaking supervisor import., Capability probes are bounded, cacheable, and never count availability as proof success., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_capabilities.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_contracts.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_contracts.py, CodeProofObligation, ProofPlan, ProofAttempt, ProofReceipt, and assurance enums have deterministic JSON encodings and content identities., Receipts bind repository trees, AST scopes, premises, translators, solvers, kernels, toolchains, policy, and resource budgets., Authoritative assurance is derived from evidence and cannot be asserted directly by a provider., LLM output, ATP or SMT candidates, stale cache entries, and simulated ZKP cannot become kernel-verified or attested., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_contracts.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_provider.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_provider.py, A versioned provider protocol supports capability, translate, prove, reconstruct, verify, and attest operations., Providers can be discovered lazily in process or invoked through a bounded subprocess JSON protocol., Timeout, cancellation, resource, network, and malformed-response failures are explicit and fail closed., The supervisor imports and runs with no ipfs_datasets_py proof provider installed., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_provider.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_policy.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_policy.py, Policy maps changed paths, risk, and invariant classes to required assurance and fallback validation., Disabled, shadow, canary, and enforcement modes have explicit promotion and override behavior., Unsupported, unavailable, timed-out, and inconclusive results cannot silently satisfy an enforcement gate., Overrides require bounded scope, actor, reason, expiration, and a durable receipt., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_policy.py -q, data/refactor_supervisor/discovery/2026-07-23-ref-307-objective-validation-repair.md, objective validation repair
- Interfaces:
- Submodules:
- Generated artifacts:
- Allow concurrent with:
- Goal id: G11.S1
- Canonical task key: task/v1/e67c6a7f4d6478eca87804c5be1faff4310d48ac1dd3b230ecf2b975d7e01f83
- Canonical task CID: baguqeera4z6gu72nmr4ozkdyatc34h5p6qyq2sfmdxj3emhm6k4xlv7ad6bq
- Missing evidence: objective validation repair
- Embedding query: Establish proof contracts, capabilities, and trust policy
- AST query: ipfs_datasets_py/ipfs_accelerate_py/docs/architecture/AGENT_SUPERVISOR_FORMAL_VERIFICATION_PLAN.md, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_capabilities.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_capabilities.py, A versioned capability report covers Hammer, TDFOL, external provers, Lean, Leanstral, frame logic, knowledge graphs, and ZKP backends., Provider, executable, package, model, circuit, and optional dependency health are reported separately., Missing spaCy, model weights, Python bindings, or prover executables produce explicit degraded or unavailable reasons without breaking supervisor import., Capability probes are bounded, cacheable, and never count availability as proof success., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_capabilities.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_contracts.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_contracts.py, CodeProofObligation, ProofPlan, ProofAttempt, ProofReceipt, and assurance enums have deterministic JSON encodings and content identities., Receipts bind repository trees, AST scopes, premises, translators, solvers, kernels, toolchains, policy, and resource budgets., Authoritative assurance is derived from evidence and cannot be asserted directly by a provider., LLM output, ATP or SMT candidates, stale cache entries, and simulated ZKP cannot become kernel-verified or attested., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_contracts.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_provider.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_provider.py, A versioned provider protocol supports capability, translate, prove, reconstruct, verify, and attest operations., Providers can be discovered lazily in process or invoked through a bounded subprocess JSON protocol., Timeout, cancellation, resource, network, and malformed-response failures are explicit and fail closed., The supervisor imports and runs with no ipfs_datasets_py proof provider installed., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_provider.py -q, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_policy.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_policy.py, Policy maps changed paths, AST scopes, risk, and invariant classes to required assurance and fallback validation., Disabled, shadow, canary, and enforcement modes have explicit promotion and override behavior., Unsupported, unavailable, timed-out, and inconclusive results cannot silently satisfy an enforcement gate., Overrides require bounded scope, actor, reason, expiration, and a durable receipt., PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_policy.py -q, data/refactor_supervisor/discovery/2026-07-23-ref-307-objective-validation-repair.md, objective validation repair
- Surplus group: objective/G11.S1
- Merge key: 8632255e87745d9d
- Merge family: goal_packet/ops/ipfs_datasets_py/c4bb9eba851b
- Merge role: validation_gate
- Work item count: 1
- Work scope: objective_validation_repair; goal_subgoal_packet
- Goal packet: goal_packet/ops/ipfs_datasets_py/c4bb9eba851b
- Goal packet role: packet_member
- Goal packet goals: G11, G11.S1, G11.S2, G11.S3, G11.S4, G11.S7
- Goal packet task count: 6
- Goal packet work item count: 6
- Candidate kind: validation_gate
- Todo vector key: 78e738b038ca0422
- Acceptance: Objective scan filed this gap for G11.S1. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-23-ref-356-objective-gap-17980a8aba65.md, add code/tests/docs or child goals that prove the missing evidence terms are covered (objective validation repair), and keep the supervisor-fed backlog aligned with the objective heap. This task is part of goal_packet/ops/ipfs_datasets_py/c4bb9eba851b; implement a complete, cohesive change that fully advances the packet goals (G11, G11.S1, G11.S2, G11.S3, G11.S4, G11.S7) and covers all the shared packet evidence in one comprehensive pass. Refine the objective heap if the gap needs smaller child goals.
