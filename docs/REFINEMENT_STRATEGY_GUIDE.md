# Refinement Strategy Guide

## Overview

The refinement strategy system recommends the next most impactful action for
improving ontology quality. The main entry point is
`OntologyMediator.suggest_refinement_strategy()`, which analyzes critic scores,
recommendation patterns, and graph stats to pick a single action.

Source of truth in code:
- Strategy selection: [suggest_refinement_strategy](ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/ontology_mediator.py#L869-L1038)
- Recommendation-driven action application: [refine_ontology](ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/ontology_mediator.py#L432-L661)
- Pipeline integration: [OntologyPipeline.run](ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/ontology_pipeline.py#L218-L281)

## Quick Start

```python
from ipfs_datasets_py.optimizers.graphrag import (
    OntologyMediator,
    OntologyCritic,
    OntologyGenerationContext,
)

critic = OntologyCritic()
mediator = OntologyMediator()

ontology = generate_ontology(text, context)
score = critic.evaluate_ontology(ontology, context)

strategy = mediator.suggest_refinement_strategy(ontology, score, context)
print(strategy["action"], strategy["priority"], strategy["estimated_impact"])
```

## Strategy Output Schema

```python
{
    "action": str,
    "priority": str,          # "high", "medium", or "low"
    "rationale": str,
    "estimated_impact": float,
    "alternative_actions": list,
    "affected_entity_count": int,
}
```

## How Strategy Selection Works

The mediator evaluates:
- Dimension scores: `completeness`, `consistency`, `clarity`
- Overall score threshold: `overall >= 0.85` -> `converged`
- Recommendation patterns (keyword matching)
- Entity/relationship counts (for orphan detection and granularity)

Recommendation keyword buckets:
- property: `property`, `detail`, `clarity`, `definition`
- naming: `naming`, `convention`, `normalize`, `consistent`, `casing`
- orphan: `orphan`, `prune`, `coverage`
- duplicate: `duplicate`, `consistency`, `dedup`, `merge`
- relationship: contains `relationship`
- granular: `split`, `granular`, `too broad`, `overloaded`

Decision flow:

```
if overall >= 0.85:
    action = converged
elif clarity < 0.55 and property >= 2:
    action = add_missing_properties
elif consistency < 0.55 and duplicate >= 2:
    action = merge_duplicates
elif completeness < 0.55 and relationship >= 2:
    action = add_missing_relationships
elif orphan >= 1:
    action = prune_orphans
elif granular >= 1 and entity_count < 50:
    action = split_entity
elif naming >= 2:
    action = normalize_names
elif clarity < 0.65:
    action = add_missing_properties
else:
    action = no_action_needed
```

## Strategy Actions (suggest_refinement_strategy)

These actions are chosen by the strategy function with explicit thresholds and
estimated impact values:

| Action | Trigger | Estimated Impact |
| --- | --- | --- |
| `add_missing_properties` | clarity < 0.55 and property >= 2 | +0.12 |
| `merge_duplicates` | consistency < 0.55 and duplicate >= 2 | +0.15 |
| `add_missing_relationships` | completeness < 0.55 and relationship >= 2 | +0.18 |
| `prune_orphans` | orphan >= 1 | +0.08 |
| `split_entity` | granular >= 1 and entity_count < 50 | +0.10 |
| `normalize_names` | naming >= 2 | +0.07 |
| `converged` | overall >= 0.85 | +0.00 |
| `no_action_needed` | none matched | +0.00 |

Priority mapping used in code:
- high: dimension score < 0.45
- medium: default for most actions
- low: converged or no_action_needed

## Recommendation-Driven Actions (refine_ontology)

`refine_ontology` applies multiple actions in a single round by iterating over
recommendation strings. It records actions in
`metadata.refinement_actions` and logs a JSON event per round.

Actions triggered by recommendation keywords:
- `add_missing_properties` for property/detail/clarity/definition
- `normalize_names` for naming/convention/normalize/consistent
- `prune_orphans` for orphan/prune/coverage
- `merge_duplicates` for duplicate/consistency/dedup/merge
- `add_missing_relationships` for missing relationship/orphan link/unlinked
- `split_entity` for split/granular/too broad/overloaded
- `rename_entity` for rename/casing/normalise/normalize name/title case

Implementation details:
- `add_missing_relationships` links orphan pairs with `co_occurrence`
  relationships and `confidence=0.3`.
- `split_entity` uses comma/" and " splitting and removes relationships tied to
  removed entity IDs.
- `rename_entity` title-cases entity text only (types are not changed here).

## Pipeline Integration

`OntologyPipeline.run()` calls `refine_ontology` when `refine=True`, then
re-evaluates the ontology and logs a `PIPELINE_RUN` event. It does not call
`suggest_refinement_strategy` directly. See
[OntologyPipeline.run](ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/ontology_pipeline.py#L218-L281).

## Recommended Usage Patterns

### Decision Support Only

Use the strategy function for planning, but let `refine_ontology` apply the
actual changes.

```python
strategy = mediator.suggest_refinement_strategy(ontology, score, context)
refined = mediator.refine_ontology(ontology, score, context)
```

### Manual Action Application

If you want full control, map the strategy action to your own transformation
layer and skip `refine_ontology`.

```python
strategy = mediator.suggest_refinement_strategy(ontology, score, context)
if strategy["action"] not in ("no_action_needed", "converged"):
    ontology = apply_action(ontology, strategy["action"])
```

### Preview Recommendations

```python
recs = mediator.preview_recommendations(ontology, score, context)
```

## Troubleshooting

### Always converged or no_action_needed

- Check overall score (threshold is 0.85).
- Verify recommendations exist and contain the expected keywords.

### Action applies but scores do not improve

- Re-run `critic.evaluate_ontology` after refinement to confirm deltas.
- Validate recommendation text from the critic for correct keywords.

## References

- Strategy logic: [suggest_refinement_strategy](ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/ontology_mediator.py#L869-L1038)
- Action application: [refine_ontology](ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/ontology_mediator.py#L432-L661)
- Pipeline flow: [OntologyPipeline.run](ipfs_datasets_py/ipfs_datasets_py/optimizers/graphrag/ontology_pipeline.py#L218-L281)
