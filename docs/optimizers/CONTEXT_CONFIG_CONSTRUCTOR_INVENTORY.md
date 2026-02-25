# Context/Config Constructor Inventory (Core Optimizers)

_Last updated: 2026-02-25_

Purpose: baseline signatures for unifying context/config dataclasses across GraphRAG, logic, and agentic optimizer paths.

## GraphRAG Core
- `OntologyGenerator.__init__(ipfs_accelerate_config, use_ipfs_accelerate, logger, llm_backend, enable_semantic_dedup)`
- `OntologyPipeline.__init__(domain, use_llm, max_rounds, logger, metric_sink)`
- `OntologyCritic.__init__(backend_config, use_llm, logger)`
- `OntologyMediator.__init__(...)` (generator/critic/refinement controls)

## Logic Core
- `LogicExtractor.__init__(model, backend, use_ipfs_accelerate, enable_formula_translation, enable_kg_integration, enable_rag_integration)`
- `LogicTheoremOptimizer.__init__(config, llm_backend, extraction_mode, use_provers, enable_caching, domain, metrics_collector, learning_metrics_collector, logger)`

## Agentic Core
- `OptimizerLLMRouter.__init__(preferred_provider, fallback_providers, enable_tracking, enable_caching, cache)`
- `AgenticOptimizer.__init__(...)` (base class with method-specific subclasses)

## Signature Drift Observations
- `domain` is present in pipeline/unified optimizer paths but not consistently first-class in all constructors.
- Logging/metrics injection parameters (`logger`, `metrics_collector`, `metric_sink`) are inconsistent across modules.
- Backend controls (`llm_backend`, provider/backend config, `use_ipfs_accelerate`) are represented with different naming and shapes.
- Some modules center config in typed dataclasses (`OptimizerConfig`), while others still accept broad dict-style config.

## Proposed Minimum Shared Context Fields
- `domain: str`
- `data_source: str | None`
- `data_type: str | None`
- `session_id: str | None`
- `trace_id: str | None`
- `metadata: dict[str, object]`

## Proposed Minimum Shared Backend Config Fields
- `provider: str`
- `model: str`
- `use_llm: bool`
- `timeout_seconds: float`
- `max_retries: int`
- `circuit_failure_threshold: int`

## Next Step
1. Introduce one typed `UnifiedOptimizerContext` dataclass in `optimizers/common/`.
2. Add adapter helpers to map existing constructor kwargs into the dataclass without breaking API compatibility.
3. Add constructor conformance tests for core GraphRAG/logic/agentic entrypoints.

