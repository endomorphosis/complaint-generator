# API Reference

## Overview

This is the top-level API reference index for the complaint-generator workspace.
It links to the detailed module references maintained per subsystem.

## Core Modules

- GraphRAG optimizer API: [API_REFERENCE_GRAPHRAG.md](API_REFERENCE_GRAPHRAG.md)
- Common optimizer interfaces: [API_REFERENCE_COMMON.md](API_REFERENCE_COMMON.md)
- Agentic optimizer API: [API_REFERENCE_AGENTIC.md](API_REFERENCE_AGENTIC.md)

## Quick Entry Points

### GraphRAG

```python
from ipfs_datasets_py.optimizers.graphrag import (
    OntologyGenerator,
    OntologyCritic,
    OntologyMediator,
    OntologyPipeline,
)
```

Primary flow:
- `OntologyGenerator.extract_entities()` -> `EntityExtractionResult`
- `OntologyCritic.evaluate_ontology()` -> `CriticScore`
- `OntologyMediator.refine_ontology()` -> refined ontology dict
- `OntologyPipeline.run()` -> `PipelineResult`

### Common Optimizer Interfaces

```python
from ipfs_datasets_py.optimizers.common import (
    BaseOptimizer,
    BaseCritic,
    BaseSession,
)
```

These provide shared contracts for generator/critic/optimizer stacks.

### Agentic

```python
from ipfs_datasets_py.optimizers.agentic import (
    AgenticOptimizer,
)
```

Use the agentic layer for autonomous refinement and change control.

## Data Structures

- `CriticScore` (GraphRAG): multi-dimensional score with `overall` property.
- `Entity`, `Relationship`: entity/edge structures produced by extraction.
- `EntityExtractionResult`: entity + relationship result bundle with metadata.

See the GraphRAG API reference for field-level details.

## Additional References

- Extraction config guide: [EXTRACTION_CONFIG_GUIDE.md](EXTRACTION_CONFIG_GUIDE.md)
- Refinement strategy guide: [REFINEMENT_STRATEGY_GUIDE.md](REFINEMENT_STRATEGY_GUIDE.md)
- Performance tuning: [PERFORMANCE_TUNING.md](PERFORMANCE_TUNING.md)
