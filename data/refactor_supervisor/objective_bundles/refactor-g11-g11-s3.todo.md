# Objective Bundle: refactor/g11/g11-s3

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-253: REF-253 Adapt code obligations to the ipfs_datasets_py Hammer portfolio

## REF-253 Adapt code obligations to the ipfs_datasets_py Hammer portfolio

- Status: completed
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-246, REF-249
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/ipfs_datasets_logic_provider.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_provider.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_ipfs_datasets_logic_provider.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_ipfs_datasets_logic_provider.py -q
- Bundle: refactor/g11/g11-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S3
- Missing evidence: The mature Hammer portfolio should be consumed through the provider boundary rather than copied into the supervisor.
- AST symbols: PROOF_PROVIDER_PROTOCOL_VERSION, PROOF_PROVIDER_SUPPORTED_PROTOCOL_VERSIONS, PROOF_PROVIDER_REQUEST_SCHEMA, PROOF_PROVIDER_RESPONSE_SCHEMA, PROOF_PROVIDER_ENTRY_POINT_GROUP, PROOF_PROVIDER_ENVIRONMENT, DEFAULT_PROVIDER_TIMEOUT_SECONDS, DEFAULT_PROVIDER_MAX_REQUEST_BYTES, DEFAULT_PROVIDER_MAX_RESPONSE_BYTES, DEFAULT_PROVIDER_MEMORY_BYTES, DEFAULT_PROVIDER_CPU_TIME_SECONDS, DEFAULT_PROVIDER_MAX_PROCESSES, ProviderFailureCode, ProviderFailure, ProofProviderError, ProviderInvocationError, NetworkAccessDenied, CancellationToken, _json_value, _json_object, _object_without_duplicate_keys, _strict_json_loads, _resource_budget, ProviderRequest, ProviderResponse, ProofProvider, ProviderInvocationConfig, _request_timeout, _duration_ms, _exception_failure
- Merge key: refactor/g11/g11-s3
- Candidate kind: seed
- Todo vector key: ref-253-adaptcodeobligationstotheipfs-datasets-pyhammerp
- Acceptance: Supported obligations translate deterministically into Hammer requests with explicit premises and environment locks.; Solver allowlists, timeouts, CPU, memory, network denial, and maximum premise counts flow from supervisor policy.; Portfolio attempts and candidate proofs preserve upstream receipt provenance.; Unsupported translation families return a typed unsupported result and configured fallback checks.

- [ ] Task checkbox-254: REF-254 Add trust-aware proof caching and single-flight execution

## REF-254 Add trust-aware proof caching and single-flight execution

- Status: todo
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-245, REF-253
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_cache.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/ipfs_datasets_logic_provider.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_cache.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_formal_verification_cache.py -q
- Bundle: refactor/g11/g11-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S3
- Missing evidence: Parallel lanes must reuse sound results without executing the same expensive obligation or trusting a stale or weaker cache entry.
- AST symbols: 
- Merge key: refactor/g11/g11-s3
- Candidate kind: seed
- Todo vector key: ref-254-addtrust-awareproofcachingandsingle-flightexecut
- Acceptance: Cache keys bind obligation, premises, translator, solver, kernel, toolchain, theorem registry, policy, resource budget, and candidate tree.; Only results meeting the requested assurance and freshness can satisfy a lookup.; A cross-thread and cross-process single-flight lease deduplicates active proof work.; Poisoned, malformed, stale, partial, solver-only, and simulated-attestation cache entries are rejected with reason codes.

- [ ] Task checkbox-255: REF-255 Enforce independent kernel reconstruction and verdict derivation

## REF-255 Enforce independent kernel reconstruction and verdict derivation

- Status: todo
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-245, REF-253
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/kernel_verification.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/formal_verification_contracts.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_kernel_verification.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_kernel_verification.py -q
- Bundle: refactor/g11/g11-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S3
- Missing evidence: A solver candidate or LLM proof draft is not formal verification until an allowed target kernel accepts the exact reconstructed obligation.
- AST symbols: CONTRACT_VERSION, SCHEMA_VERSION, CODE_PROOF_OBLIGATION_SCHEMA, PROOF_PLAN_SCHEMA, PROOF_PLAN_STEP_SCHEMA, PROOF_ATTEMPT_SCHEMA, PROOF_RECEIPT_SCHEMA, PROOF_EVIDENCE_SCHEMA, RESOURCE_BUDGET_SCHEMA, ASSURANCE_ASSESSMENT_SCHEMA, ContractValidationError, AssuranceLevel, RequiredAssuranceLevel, AuthoritativeAssuranceLevel, ProofAssuranceLevel, ProofStage, AttemptStatus, ProofVerdict, EvidenceKind, ProofEvidenceKind, EvidenceAuthority, EvidenceVerdict, EvidenceFreshness, TEnum, _enum, _canonical_value, canonical_json_bytes, canonical_json, content_identity, _text
- Merge key: refactor/g11/g11-s3
- Candidate kind: seed
- Todo vector key: ref-255-enforceindependentkernelreconstructionandverdict
- Acceptance: Lean, Coq, and Isabelle reconstruction records are mapped without weakening upstream trust semantics.; Kernel unavailability, timeout, mismatch, forbidden declarations, sorry or admit, and changed theorem statements fail closed.; The authoritative verdict is derived from reconstruction evidence and cannot be upgraded by provider status text.; Negative and corrupt proof fixtures never produce kernel-verified receipts.

- [ ] Task checkbox-256: REF-256 Route counterexamples and unsupported obligations into focused validation

## REF-256 Route counterexamples and unsupported obligations into focused validation

- Status: todo
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-247, REF-249, REF-255
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_fallbacks.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_commands.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_fallbacks.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_fallbacks.py -q
- Bundle: refactor/g11/g11-s3
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S3
- Missing evidence: Disproved, unsupported, or inconclusive obligations should reduce model search and trigger actionable checks instead of becoming generic failures.
- AST symbols: INLINE_CODE_COMMAND_RE, ValidationStage, ValidationCommand, ValidationSelectionItem, ValidationSelection, _CHEAP_PATTERNS, _TEST_RUNNER_RE, _ENV_ASSIGNMENT_RE, _GLOBAL_IMPACT_NAMES, _DEPENDENCY_SUFFIXES, normalize_validation_command_text, split_validation_commands, _shell_tokens, _normalize_path, _looks_like_impact_path, infer_validation_impact_paths, classify_validation_command, build_validation_commands, is_global_impact_change, _path_related, select_validation_commands, ValidationCommandSpec, select_impacted_validations, CHEAP, TARGETED, BROAD, label, with_stage, to_dict, selected
- Merge key: refactor/g11/g11-s3
- Candidate kind: seed
- Todo vector key: ref-256-routecounterexamplesandunsupportedobligationsint
- Acceptance: Counterexamples and unsat cores are normalized into bounded task diagnostics and regression fixtures.; Unsupported obligations map to declared focused tests, static checks, or manual-review requirements.; Shadow mode can continue through fallback validation while enforcement mode honors required assurance.; Repeated equivalent failures deduplicate by obligation, tree, and counterexample identity.
