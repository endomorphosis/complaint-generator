# Refinement Strategy Guide

## Overview

The **Refinement Strategy** system provides intelligent recommendations for improving ontology quality. The `OntologyMediator.suggest_refinement_strategy()` method analyzes ontology quality scores and recommends the next most impactful refinement action, enabling iterative ontology improvement.

## Quick Start

### Basic Usage

```python
from ipfs_datasets_py.optimizers.graphrag import (
    OntologyMediator,
    OntologyCritic,
    OntologyGenerationContext
)

# Initialize components
critic = OntologyCritic()
mediator = OntologyMediator()

# Generate and evaluate ontology
ontology = generate_ontology(text, context)
score = critic.evaluate_ontology(ontology, context)

# Get refinement recommendation
strategy = mediator.suggest_refinement_strategy(ontology, score, context)

print(f"Action: {strategy['action']}")
print(f"Priority: {strategy['priority']}")
print(f"Rationale: {strategy['rationale']}")
print(f"Estimated Impact: +{strategy['estimated_impact']:.2f}")
```

### Strategy Output Structure

Every refinement strategy returns a dictionary with:

```python
{
    "action": str,                    # Recommended action name
    "priority": str,                  # "critical", "high", "medium", or "low"
    "rationale": str,                 # Explanation of recommendation
    "estimated_impact": float,        # Estimated score improvement (0-1)
    "alternative_actions": list,      # [str, ...] fallback actions
    "affected_entity_count": int,     # How many entities affected
}
```

## Refinement Actions

The system recommends the following refinement actions based on analysis:

### 1. `add_missing_properties`

**Trigger:** Low clarity score + multiple property-related recommendations

**What it does:** Adds or enriches entity properties to improve clarity.

**Quality dimension affected:** **Clarity** (↑ 0.12)

**Use case:**
- Entities lack property definitions (e.g., `name`, `description`, `type`)
- Critic recommends adding more details
- Clarity score < 0.55 with ≥2 property recommendations

**Alternative actions:** `normalize_names`, `split_entity`

**Example:**
```python
# Before: Entity lacks properties
entity = {"id": "ent1", "type": "Person"}

# After: Properties enriched
entity = {
    "id": "ent1",
    "type": "Person",
    "properties": {
        "full_name": "John Doe",
        "title": "Senior Attorney",
        "email": "john@example.com"
    }
}
```

### 2. `merge_duplicates`

**Trigger:** Low consistency score + multiple duplicate entity recommendations

**What it does:** Merges duplicate entities to improve consistency.

**Quality dimension affected:** **Consistency** (↑ 0.15)

**Use case:**
- Same concept represented by multiple entities (e.g., "Court" and "CourtOfLaw")
- Consistency score < 0.55 with ≥2 duplicate recommendations
- Multiple entities have overlapping or identical semantics

**Alternative actions:** `normalize_names`, `add_missing_properties`

**Example:**
```python
# Before: Duplicates
entities = [
    {"id": "ent1", "text": "John Doe", "type": "Person"},
    {"id": "ent2", "text": "John D.", "type": "Person"},
    {"id": "ent3", "text": "J. Doe", "type": "Person"}
]

# After: Merged to single entity
entities = [
    {"id": "ent1", "text": "John Doe", "type": "Person", "aliases": ["John D.", "J. Doe"]}
]
```

### 3. `add_missing_relationships`

**Trigger:** Low completeness score + multiple relationship recommendations

**What it does:** Adds missing relationships between entities.

**Quality dimension affected:** **Completeness** (↑ 0.18)

**Use case:**
- Entities are present but disconnected
- Completeness score < 0.55 with ≥2 relationship recommendations
- Many entities have no relationships (orphans)
- Typical case: entity_count >> relationship_count

**Alternative actions:** `split_entity`, `prune_orphans`

**Example:**
```python
# Before: Orphaned entities
entities = [
    {"id": "ent1", "text": "John Doe", "type": "Person"},
    {"id": "ent2", "text": "Law Firm ABC", "type": "Organization"},
    {"id": "ent3", "text": "Federal Court", "type": "Organization"}
]
relationships = []  # No connections

# After: Relationships added
relationships = [
    {"source": "ent1", "target": "ent2", "type": "works_at"},
    {"source": "ent2", "target": "ent3", "type": "files_cases_at"}
]
```

### 4. `prune_orphans`

**Trigger:** Orphan entity recommendations detected

**What it does:** Removes isolated entities that don't participate in relationships.

**Quality dimension affected:** **Completeness** (↑ 0.08)

**Use case:**
- Entities exist but participate in no relationships
- Orphan count ≈ entity_count - relationship_count
- Often combined with strategy to add missing relationships
- ~N entities not in any relationship

**Alternative actions:** `add_missing_relationships`, `split_entity`

**Example:**
```python
# Before: Orphaned entities
entities = [ent1, ent2, ent3, ent4, ent5]  # 5 entities
relationships = [  # Only 2 relationships (ent1-ent2, ent2-ent3)
    {"source": "ent1", "target": "ent2", "type": "..."},
    {"source": "ent2", "target": "ent3", "type": "..."}
]
# → ent4, ent5 are orphans

# After: Orphans pruned or connected
entities = [ent1, ent2, ent3]  # Orphans removed
# OR
relationships = [
    ...,
    {"source": "ent2", "target": "ent4", "type": "..."},
    {"source": "ent3", "target": "ent5", "type": "..."}
]  # Orphans connected
```

### 5. `split_entity`

**Trigger:** Granularity recommendations + entity count < 50

**What it does:** Splits overly-broad entities into more granular, specific entities.

**Quality dimension affected:** **Granularity** (↑ 0.10)

**Use case:**
- Single entity represents multiple concepts
- Critic recommends splitting for better granularity
- Entity count is relatively small (< 50) — room to split
- Recommendation patterns indicate over-broad concepts

**Alternative actions:** `add_missing_properties`, `normalize_names`

**Example:**
```python
# Before: Over-broad entity
entity = {
    "id": "ent1",
    "text": "John Doe, attorney at ABC Law Firm",
    "type": "Person"
    # Mixes person with employment context
}

# After: Split into focused entities
entities = [
    {
        "id": "ent1",
        "text": "John Doe",
        "type": "Person",
        "properties": {"title": "Attorney"}
    },
    {
        "id": "ent2",
        "text": "ABC Law Firm",
        "type": "Organization"
    }
]
relationships = [
    {"source": "ent1", "target": "ent2", "type": "works_at"}
]
```

### 6. `normalize_names`

**Trigger:** Multiple naming convention recommendations

**What it does:** Standardizes entity and relationship naming patterns.

**Quality dimension affected:** **Clarity** / **Consistency** (↑ 0.07)

**Use case:**
- Inconsistent naming conventions (e.g., "firstName" vs "first_name")
- Case inconsistencies across similar entities
- Multiple convention recommendations detected
- ≥2 naming pattern recommendations

**Alternative actions:** `add_missing_properties`, `merge_duplicates`

**Example:**
```python
# Before: Inconsistent naming
entities = [
    {"id": "ent1", "text": "John Doe", ...},
    {"id": "ent2", "text": "jane_smith", ...},  # Different case style
    {"id": "ent3", "text": "Bob Johnson", ...}
]

# After: Normalized naming
entities = [
    {"id": "ent1", "text": "john_doe", ...},
    {"id": "ent2", "text": "jane_smith", ...},
    {"id": "ent3", "text": "bob_johnson", ...}
]
```

### 7. `converged` / `no_action_needed`

**Trigger:** Overall quality ≥ 0.85 or no issues detected

**What it does:** Indicates ontology has reached satisfactory quality.

**Quality dimension affected:** None (all dimensions adequate)

**Use case:**
- Ontology quality is already excellent
- All dimensions above 0.70
- Diminishing returns on further refinement
- Convergence reached

**Priority:** Low (stop refining)

## Strategy Selection Algorithm

The `suggest_refinement_strategy()` method uses a **decision tree** based on:

1. **Overall Quality Score**: If ≥ 0.85, recommend convergence
2. **Bottleneck Dimensions**: Identify the lowest-scoring dimensions
3. **Recommendation Patterns**: Count recommendations mentioning specific issues
4. **Entity/Relationship Statistics**: Analyze graph structure
5. **Action History**: Avoid repeating recent refinements (in extended versions)

### Decision Process

```
if overall_score >= 0.85:
    → Action: converged (stop)

elif clarity < 0.55 AND property_pattern_count >= 2:
    → Action: add_missing_properties (highest impact)

elif consistency < 0.55 AND duplicate_pattern_count >= 2:
    → Action: merge_duplicates

elif completeness < 0.55 AND relationship_pattern_count >= 2:
    → Action: add_missing_relationships (highest impact)

elif orphan_pattern_count >= 1:
    → Action: prune_orphans

elif granular_pattern_count >= 1 AND entity_count < 50:
    → Action: split_entity

elif naming_pattern_count >= 2:
    → Action: normalize_names

elif clarity < 0.65:
    → Action: add_missing_properties (fallback)

else:
    → Action: no_action_needed
```

## Estimated Impact Values

Each strategy includes an `estimated_impact` value (0.0 - 1.0) predicting score improvement:

| Action | Estimated Impact | Duration | Risk |
|--------|------------------|----------|------|
| `add_missing_properties` | ↑ 0.12 | Medium | Low |
| `merge_duplicates` | ↑ 0.15 | Fast | Low |
| `add_missing_relationships` | ↑ 0.18 | Medium | Medium |
| `prune_orphans` | ↑ 0.08 | Fast | Low |
| `split_entity` | ↑ 0.10 | Medium | Medium |
| `normalize_names` | ↑ 0.07 | Fast | Low |
| `converged` | ↑ 0.00 | N/A | N/A |

## Priority Levels

Strategies are assigned priority based on severity and impact:

- **critical**: Immediate action required; major quality gap (< 0.30 dimension score)
- **high**: Should be addressed soon; significant quality issue (< 0.45 dimension score)
- **medium**: Recommended; moderate quality improvement opportunity
- **low**: Optional; minimal expected impact or already converged

## Alternative Actions

Each strategy includes `alternative_actions` — fallback recommendations if the primary action cannot be applied:

```python
strategy = mediator.suggest_refinement_strategy(ontology, score, context)

if can_apply(strategy['action']):
    apply_action(strategy['action'])
else:
    # Try alternatives in order
    for alt_action in strategy['alternative_actions']:
        if can_apply(alt_action):
            apply_action(alt_action)
            break
```

## Advanced Usage

### Iterative Refinement Loop

Implement a loop that applies strategies until convergence:

```python
max_iterations = 10
for iteration in range(max_iterations):
    # Evaluate current ontology
    score = critic.evaluate_ontology(ontology, context)
    
    # Check convergence
    if score.overall >= 0.85:
        print(f"Converged after {iteration} iterations")
        break
    
    # Get strategy
    strategy = mediator.suggest_refinement_strategy(ontology, score, context)
    
    # Apply strategy
    if strategy['action'] != 'no_action_needed':
        ontology = apply_refinement(ontology, strategy)
        print(f"Applied: {strategy['action']} (Est. impact: +{strategy['estimated_impact']:.2f})")
    else:
        break
```

### Selective Refinement (High-Impact Only)

Apply only refinements with high expected impact:

```python
strategy = mediator.suggest_refinement_strategy(ontology, score, context)

if strategy['estimated_impact'] >= 0.10:  # Only apply high-impact actions
    ontology = apply_refinement(ontology, strategy)
```

### Multi-Strategy Batching

Apply multiple compatible strategies in sequence:

```python
strategies = []
remaining_ontology = ontology

for _ in range(3):  # Apply up to 3 strategies
    score = critic.evaluate_ontology(remaining_ontology, context)
    strategy = mediator.suggest_refinement_strategy(remaining_ontology, score, context)
    
    if strategy['action'] == 'no_action_needed':
        break
    
    strategies.append(strategy)
    remaining_ontology = apply_refinement(remaining_ontology, strategy)

print(f"Applied {len(strategies)} strategies")
print(f"Final score: {score.overall:.2f}")
```

### Weighted Strategy Selection

Choose actions based on custom priorities (e.g., speed vs. quality):

```python
# Speed-optimized: prefer fast actions
speed_weights = {
    'merge_duplicates': 1.0,
    'normalize_names': 1.0,
    'prune_orphans': 1.0,
    'add_missing_relationships': 0.5,
    'add_missing_properties': 0.5,
    'split_entity': 0.3,
}

strategy = mediator.suggest_refinement_strategy(ontology, score, context)
while strategy['action'] != 'no_action_needed':
    if strategy['action'] in speed_weights and speed_weights[strategy['action']] > 0.7:
        apply_refinement(ontology, strategy)
    score = critic.evaluate_ontology(ontology, context)
    strategy = mediator.suggest_refinement_strategy(ontology, score, context)
```

## Integration with OntologyPipeline

The `OntologyPipeline` class supports automatic refinement strategy application:

```python
from ipfs_datasets_py.optimizers.graphrag import OntologyPipeline

pipeline = OntologyPipeline(
    critic=critic,
    mediator=mediator,
    max_refinement_iterations=5,  # Auto-refinement enabled
)

result = pipeline.run(
    text=document_text,
    context=context,
    auto_refine=True,  # Apply strategies until convergence
)

print(f"Final ontology score: {result.final_score.overall:.2f}")
print(f"Applied {result.refinement_count} refinement iterations")
```

## Troubleshooting

### Issue: No Strategy Generated (always "no_action_needed")

**Possible causes:**
- Ontology quality already high (overall ≥ 0.85)
- No entities or relationships in ontology
- Critic was called with wrong context type

**Solutions:**
```python
# Verify score
score = critic.evaluate_ontology(ontology, context)
print(f"Overall: {score.overall:.2f}")
print(f"Dimensions: {score.to_dict()['dimensions']}")

# Verify ontology structure
print(f"Entities: {len(ontology.get('entities', []))}")
print(f"Relationships: {len(ontology.get('relationships', []))}")
```

### Issue: Recommended Action Not Applicable

**Possible causes:**
- Entity set too large for `split_entity`
- Entity set too small for pruning
- No suitable entities match action criteria

**Solutions:**
```python
# Use alternative actions
strategy = mediator.suggest_refinement_strategy(ontology, score, context)

for action in [strategy['action']] + strategy['alternative_actions']:
    if is_applicable(action, ontology):
        apply_action(action)
        break
```

### Issue: Infinite Refinement Loop

**Possible causes:**
- Same refinement applied repeatedly
- Refinement not actually improving scores
- Score improvements below threshold

**Solutions:**
```python
# Add termination conditions
prev_score = 0.0
for iteration in range(20):
    score = critic.evaluate_ontology(ontology, context)
    
    # Check convergence and minimum improvement threshold
    if score.overall >= 0.85 or (score.overall - prev_score) < 0.02:
        break
    
    strategy = mediator.suggest_refinement_strategy(ontology, score, context)
    ontology = apply_refinement(ontology, strategy)
    prev_score = score.overall
```

## Best Practices

1. **Start with quality evaluation**: Always call `critic.evaluate_ontology()` before `mediator.suggest_refinement_strategy()`

2. **Use alternative actions**: The primary action may not always be applicable; fallbacks are provided

3. **Monitor convergence**: Set a maximum iteration count to prevent infinite loops

4. **Threshold-based stopping**: Stop refining when score reaches ≥ 0.80-0.85 (diminishing returns)

5. **Batch compatible actions**: Speed up refinement by applying multiple actions to the same ontology

6. **Log refinement history**: Track which actions were applied for auditing and debugging

7. **Validate results**: Always re-evaluate after applying refinements to verify improvements

8. **Handle edge cases**: Empty ontologies, single-entity graphs, and extreme cases have dedicated handling

## Performance Characteristics

- **suggest_refinement_strategy()** execution: < 10ms per call
- **Decision tree depth**: 8 levels (constant worst-case)
- **Recommendation pattern counting**: O(R) where R = recommendation count (typically 3-10)
- **Memory usage**: < 1KB per call (lightweight analysis)

## References

- **CriticScore**: Multi-dimensional evaluation framework (see [Critic Score Guide](CRITIC_SCORE_GUIDE.md))
- **OntologyMediator**: Core refinement planning system
- **OntologyPipeline**: Automated refinement orchestration
- **Decision Tree Logic**: Implemented in `suggest_refinement_strategy()` method (ontology_mediator.py:727-890)
