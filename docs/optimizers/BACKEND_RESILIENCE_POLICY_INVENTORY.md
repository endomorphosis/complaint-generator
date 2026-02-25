# Backend Resilience Policy Inventory

_Last updated: 2026-02-25_

Scope: `ipfs_datasets_py/ipfs_datasets_py/optimizers`

Goal: track timeout/retry/circuit-breaker policy coverage for external/backend calls.

## Canonical Policy Primitive
- `optimizers/common/backend_resilience.py`
  - `BackendCallPolicy`
  - `execute_with_resilience(...)`
- Common exceptions used by wrappers:
  - `OptimizerTimeoutError`
  - `RetryableBackendError`
  - `CircuitBreakerOpenError`

## Current Coverage Matrix

### Covered by shared resilience wrapper
- `graphrag/ontology_generator.py`
  - `_invoke_llm_extraction_backend(...)` wraps callable/generate/complete backend calls.
- `graphrag/ontology_refinement_agent.py`
  - `propose_feedback(...)` wraps LLM backend invocation.
- `agentic/llm_integration.py`
  - `OptimizerLLMRouter.generate(...)` wraps provider calls with per-provider policy + breaker.
- `logic_theorem_optimizer/logic_extractor.py`
  - `_query_llm(...)` uses shared wrapper around backend adapter calls.
- `logic_theorem_optimizer/llm_backend.py`
  - `LLMBackendAdapter.generate(...)` uses per-backend policy + persistent breaker map.

### Uses circuit-breaker style protection (non-shared wrapper path)
- `llm_lazy_loader.py`
  - lazy backend call wrappers protect calls with local circuit-breaker mechanism.
  - Follow-up: evaluate migration to `execute_with_resilience(...)` for policy consistency.

## Gaps / Follow-Ups
- Verify all remaining external-call surfaces that do not currently route through:
  - `execute_with_resilience(...)`, or
  - an equivalent policy object with explicit timeout/retry/breaker settings.
- Add a policy-conformance test that scans production modules (excluding tests/docs)
  for known backend invocation patterns and asserts they are covered by a resilience path.
- Document default policy values per optimizer type and define allowed overrides.
- Ensure error code mapping for timeout/retry/circuit-open outcomes is consistent in logs/metrics.

## Suggested Next Execution Order
1. Add a lightweight conformance test for backend-call wrappers (security lane).
2. Normalize `llm_lazy_loader.py` to shared policy primitives (architecture/security lane).
3. Add troubleshooting docs section mapping resilience exceptions to operator actions (docs/obs lane).

