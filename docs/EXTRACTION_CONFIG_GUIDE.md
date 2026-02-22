# ExtractionConfig Configuration Guide

## Overview

`ExtractionConfig` provides typed configuration for the GraphRAG ontology extraction pipeline. It controls entity extraction, relationship inference, confidence scoring, and quality filtering. All fields are optional with sensible defaults.

## Quick Start

```python
from ipfs_datasets_py.optimizers.graphrag import ExtractionConfig

# Default configuration (permissive, good for exploration)
config = ExtractionConfig()

# Strict configuration (high-quality entities only)
strict_config = ExtractionConfig(
    confidence_threshold=0.75,
    min_entity_length=3,
    max_entities=100,
    llm_fallback_threshold=0.6
)

# Domain-specific configuration (legal domain)
legal_config = ExtractionConfig(
    domain_vocab={
        "person": ["plaintiff", "defendant", "attorney", "judge"],
        "organization": ["court", "law firm", "corporation"],
        "document": ["complaint", "motion", "brief", "order"]
    },
    stopwords=["the", "a", "an", "and", "or", "but"],
    allowed_entity_types=["person", "organization", "document", "date"]
)
```

## Field Reference

### Core Quality Control

#### `confidence_threshold`
- **Type**: `float`
- **Default**: `0.5`
- **Valid Range**: `[0.0, 1.0]`
- **Description**: Minimum confidence score for extracted entities to be kept.

**Usage**:
```python
# Permissive: keep entities with any positive confidence
config = ExtractionConfig(confidence_threshold=0.3)

# Balanced: default setting for mixed quality data
config = ExtractionConfig(confidence_threshold=0.5)

# Strict: high-confidence entities only
config = ExtractionConfig(confidence_threshold=0.75)
```

**Performance Implications**:
- Lower thresholds (0.3-0.5): More entities extracted, higher recall, lower precision
- Higher thresholds (0.7-0.9): Fewer entities, lower recall, higher precision
- Very high thresholds (> 0.9): May miss valid entities, use sparingly

**Common Patterns**:
- **Exploratory analysis**: 0.3-0.4 (maximize coverage)
- **Production systems**: 0.6-0.7 (balanced quality)
- **Critical applications**: 0.8+ (minimize false positives)

---

#### `max_confidence`
- **Type**: `float`
- **Default**: `1.0`
- **Valid Range**: `(0.0, 1.0]`
- **Description**: Upper bound for entity confidence scores. Scores are clamped to `[0.0, max_confidence]`.

**Usage**:
```python
# Cap confidence to avoid overconfidence in rule-based extraction
config = ExtractionConfig(max_confidence=0.85)

# Allow full confidence range (default)
config = ExtractionConfig(max_confidence=1.0)
```

**Performance Implications**:
- Lower max_confidence values can help calibrate hybrid systems that mix rule-based and LLM extraction
- Prevents rule-based patterns from overwhelming LLM-based confidence scores

**Constraints**:
- Must be greater than `confidence_threshold`: `confidence_threshold ≤ max_confidence`

---

#### `min_entity_length`
- **Type**: `int`
- **Default**: `2`
- **Valid Range**: `[1, ∞)`
- **Description**: Minimum character length for entity text. Entities with fewer characters are filtered out.

**Usage**:
```python
# Filter single characters only (default)
config = ExtractionConfig(min_entity_length=2)

# Filter very short entities (2-3 chars)
config = ExtractionConfig(min_entity_length=4)

# Keep all entities regardless of length
config = ExtractionConfig(min_entity_length=1)
```

**Performance Implications**:
- Shorter lengths (1-2): May include noisy single-letter entities (e.g., "a", "I")
- Medium lengths (3-4): Good balance for most text processing
- Longer lengths (5+): May filter valid short entities like names ("Sam", "IBM")

**Common Patterns**:
- **General text**: 2-3 characters
- **Technical content**: 3-4 characters (filter abbreviations)
- **Names and codes**: 1-2 characters (include short identifiers)

---

### Entity and Relationship Limits

#### `max_entities`
- **Type**: `int`
- **Default**: `0` (unlimited)
- **Valid Range**: `[0, ∞)`
- **Description**: Maximum number of entities to extract per document. `0` means no limit.

**Usage**:
```python
# No limit (extract all qualifying entities)
config = ExtractionConfig(max_entities=0)

# Limit to top 50 entities
config = ExtractionConfig(max_entities=50)

# Strict limit for large-scale processing
config = ExtractionConfig(max_entities=100)
```

**Performance Implications**:
- **Memory**: More entities → higher memory usage
- **Processing time**: Relationship inference is O(n²) in entity count
- **Quality**: Top-ranked entities are selected when limit is reached

**Common Patterns**:
- **Small documents (< 1KB)**: No limit or 20-50 entities
- **Medium documents (1-10KB)**: 50-100 entities
- **Large documents (> 10KB)**: 100-200 entities
- **Real-time systems**: Cap at 50-100 to ensure consistent latency

**Recommended Settings by Document Size**:
| Document Size | Suggested Limit | Rationale |
|--------------|----------------|-----------|
| < 1 KB | 20-50 | Small text, few entities expected |
| 1-10 KB | 50-100 | Typical documents, balanced processing |
| 10-100 KB | 100-200 | Large documents, prevent O(n²) blowup |
| > 100 KB | 200-500 | Very large documents, strict control needed |

---

#### `max_relationships`
- **Type**: `int`
- **Default**: `0` (unlimited)
- **Valid Range**: `[0, ∞)`
- **Description**: Maximum number of relationships to infer per document. `0` means no limit.

**Usage**:
```python
# No limit (infer all relationships)
config = ExtractionConfig(max_relationships=0)

# Limit to strongest 100 relationships
config = ExtractionConfig(max_relationships=100)

# Strict limit for graph size control
config = ExtractionConfig(max_relationships=500)
```

**Performance Implications**:
- **Memory**: More relationships → larger graph structures
- **Graph queries**: Smaller graphs query faster
- **Quality**: Top-ranked relationships (by confidence) are kept when limit is reached

**Common Patterns**:
- **Dense graphs**: No limit or very high limit (1000+)
- **Sparse graphs**: 50-200 relationships
- **Graph databases**: Limit to database capacity constraints

**Relationship Density Guide**:
| Entities | Expected Relationships (no limit) | Suggested Max |
|----------|----------------------------------|---------------|
| 10 | 10-45 | 50 |
| 50 | 50-1,225 | 200-500 |
| 100 | 100-4,950 | 500-1,000 |
| 200 | 200-19,900 | 1,000-2,000 |

---

#### `window_size`
- **Type**: `int`
- **Default**: `5`
- **Valid Range**: `[1, ∞)`
- **Description**: Co-occurrence window size for relationship inference (in sentences or tokens, depending on strategy).

**Usage**:
```python
# Narrow window: entities must be very close
config = ExtractionConfig(window_size=3)

# Default window: balanced co-occurrence
config = ExtractionConfig(window_size=5)

# Wide window: liberal co-occurrence
config = ExtractionConfig(window_size=10)
```

**Performance Implications**:
- Smaller windows (1-3): Fewer relationships, higher precision
- Larger windows (10+): More relationships, lower precision, higher recall
- Very large windows (20+): May infer spurious relationships

**Common Patterns**:
- **Tight semantic coupling**: 3-5 sentences (default)
- **Document-level relationships**: 10-15 sentences
- **Paragraph-level**: 20+ sentences

---

### Domain-Specific Configuration

#### `domain_vocab`
- **Type**: `Dict[str, List[str]]`
- **Default**: `{}` (empty)
- **Description**: Domain-specific vocabulary for entity type hints. Maps entity types to keyword lists.

**Usage**:
```python
# Legal domain vocabulary
legal_vocab = {
    "person": ["plaintiff", "defendant", "attorney", "judge", "witness"],
    "organization": ["court", "firm", "corporation", "agency"],
    "document": ["complaint", "motion", "brief", "order", "affidavit"],
    "date": ["filed", "dated", "effective"]
}
config = ExtractionConfig(domain_vocab=legal_vocab)

# Medical domain vocabulary
medical_vocab = {
    "patient": ["patient", "individual", "subject"],
    "provider": ["doctor", "physician", "nurse", "hospital"],
    "condition": ["diagnosis", "disease", "disorder", "syndrome"],
    "medication": ["drug", "prescription", "treatment"]
}
config = ExtractionConfig(domain_vocab=medical_vocab)
```

**Performance Implications**:
- **Precision**: Domain vocab improves entity type accuracy
- **Recall**: May miss entities not in vocabulary
- **Processing**: Minimal impact on extraction speed

**Best Practices**:
- Include common synonyms and variations
- Use lowercase terms (matching is case-insensitive)
- Group by semantic categories
- Update vocabulary based on extraction audit

---

#### `custom_rules`
- **Type**: `List[tuple]`
- **Default**: `[]` (empty)
- **Description**: Pluggable rule sets as `(regex_pattern, entity_type)` tuples for custom entity extraction.

**Usage**:
```python
# Custom patterns for email addresses and URLs
email_url_rules = [
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', 'email'),
    (r'https?://[^\s]+', 'url'),
]
config = ExtractionConfig(custom_rules=email_url_rules)

# Legal case citation patterns
legal_rules = [
    (r'\d+ U\.S\. \d+', 'case_citation'),
    (r'\d+ F\.\d+d \d+', 'case_citation'),
    (r'No\. \d+-\d+', 'docket_number'),
]
config = ExtractionConfig(custom_rules=legal_rules)

# Date and number patterns
structured_rules = [
    (r'\d{1,2}/\d{1,2}/\d{2,4}', 'date'),
    (r'\$\d+(?:,\d{3})*(?:\.\d{2})?', 'monetary_amount'),
    (r'\d+%', 'percentage'),
]
config = ExtractionConfig(custom_rules=structured_rules)
```

**Performance Implications**:
- **Speed**: Regex evaluation adds overhead (O(pattern_count × text_length))
- **Precision**: Well-tuned patterns improve accuracy
- **Maintenance**: Complex patterns may need regular updates

**Pattern Design Guidelines**:
- Use word boundaries (`\b`) to avoid partial matches
- Anchor patterns when possible (`^`, `$`)
- Test patterns on representative data
- Avoid overly greedy patterns (`.*`)
- Group similar patterns by entity type

---

### Quality Filtering

#### `stopwords`
- **Type**: `List[str]`
- **Default**: `[]` (no stopwords)
- **Description**: Entity texts matching any stopword (case-insensitive) are skipped during extraction.

**Usage**:
```python
# Common English stopwords
common_stopwords = [
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "about", "into", "through", "during"
]
config = ExtractionConfig(stopwords=common_stopwords)

# Domain-specific stopwords (legal)
legal_stopwords = [
    "case", "court", "filed", "date", "party", "see", "also", "cf", "id"
]
config = ExtractionConfig(stopwords=legal_stopwords)

# Minimal stopwords (articles only)
minimal_stopwords = ["the", "a", "an"]
config = ExtractionConfig(stopwords=minimal_stopwords)
```

**Performance Implications**:
- **Precision**: Reduces noisy entities
- **Recall**: May filter valid entity mentions
- **Speed**: Negligible impact (hash-based lookup)

**Common Patterns**:
- **General text**: 20-50 common stopwords
- **Technical documents**: Domain-specific stopwords only
- **Named entity extraction**: Minimal or no stopwords

---

#### `allowed_entity_types`
- **Type**: `List[str]`
- **Default**: `[]` (allow all types)
- **Description**: Whitelist of allowed entity types. Empty list allows all types.

**Usage**:
```python
# Allow only specific types
person_org_only = ExtractionConfig(
    allowed_entity_types=["person", "organization"]
)

# Legal document types only
legal_types = ExtractionConfig(
    allowed_entity_types=["person", "organization", "date", "document", "location"]
)

# Allow all types (default)
config = ExtractionConfig(allowed_entity_types=[])
```

**Performance Implications**:
- **Precision**: Filters out unwanted entity types
- **Speed**: Minimal overhead (post-extraction filtering)
- **Memory**: Reduces entity count if many types are excluded

**Common Patterns**:
- **Focused extraction**: Specify 2-5 critical types
- **Broad extraction**: Leave empty (allow all)
- **Type refinement**: Use after initial exploratory extraction

---

### LLM Integration

#### `llm_fallback_threshold`
- **Type**: `float`
- **Default**: `0.0` (disabled)
- **Valid Range**: `[0.0, 1.0]`
- **Description**: When rule-based confidence falls below this threshold and an `llm_backend` is configured, LLM extraction is attempted as fallback.

**Usage**:
```python
# Disabled (default, no LLM fallback)
config = ExtractionConfig(llm_fallback_threshold=0.0)

# Aggressive fallback: use LLM for low-confidence entities
config = ExtractionConfig(llm_fallback_threshold=0.6)

# Conservative fallback: only for very low confidence
config = ExtractionConfig(llm_fallback_threshold=0.3)

# Combined with LLM backend
from ipfs_datasets_py.optimizers.graphrag import OntologyGenerator

generator = OntologyGenerator(
    llm_backend=my_llm_client,
)
config = ExtractionConfig(llm_fallback_threshold=0.5)
```

**Performance Implications**:
- **Cost**: LLM calls are expensive (API costs, latency)
- **Accuracy**: LLMs can improve low-confidence extractions
- **Speed**: Significantly slower when fallback is triggered

**Cost-Performance Tradeoff**:
| Threshold | Rule Coverage | LLM Fallback Rate | Cost Impact | Quality Impact |
|-----------|--------------|-------------------|-------------|----------------|
| 0.0 | 100% | 0% | None | Baseline |
| 0.3 | ~90% | ~10% | Low | +5-10% accuracy |
| 0.5 | ~70% | ~30% | Medium | +10-20% accuracy |
| 0.7 | ~40% | ~60% | High | +20-30% accuracy |

**Best Practices**:
- Start with threshold 0.0 (disabled) for initial testing
- Enable at 0.3-0.5 for balanced hybrid extraction
- Monitor LLM API costs and adjust threshold accordingly
- Cache LLM results to avoid redundant calls
- Set `confidence_threshold` higher to reduce total entities before fallback

---

### Advanced Options

#### `include_properties`
- **Type**: `bool`
- **Default**: `True`
- **Description**: Whether to emit property predicates in the formula set (for logical inference).

**Usage**:
```python
# Include properties (default, for logical inference)
config = ExtractionConfig(include_properties=True)

# Exclude properties (simpler graphs)
config = ExtractionConfig(include_properties=False)
```

**Performance Implications**:
- **True**: Richer ontology, larger formula sets, slower inference
- **False**: Simpler graphs, faster queries, less expressiveness

**Use Cases**:
- **True**: Logical reasoning, semantic queries, knowledge bases
- **False**: Simple graph visualization, relationship mapping

---

## Configuration Patterns

### Pattern 1: Exploratory Analysis

```python
# Maximize recall, tolerate noise
exploratory_config = ExtractionConfig(
    confidence_threshold=0.3,
    max_entities=0,  # No limit
    max_relationships=0,  # No limit
    window_size=10,  # Wide co-occurrence window
    min_entity_length=2,
    llm_fallback_threshold=0.0,  # No LLM costs
)
```

**Use Cases**: Initial data exploration, corpus analysis, research

---

### Pattern 2: Production Quality

```python
# Balanced precision/recall for production systems
production_config = ExtractionConfig(
    confidence_threshold=0.65,
    max_entities=100,
    max_relationships=500,
    window_size=5,
    min_entity_length=3,
    llm_fallback_threshold=0.5,  # Hybrid extraction
    stopwords=["the", "a", "an", "and", "or"],
)
```

**Use Cases**: Production pipelines, answering systems, knowledge graphs

---

### Pattern 3: High-Precision Critical Systems

```python
# Minimize false positives, maximize precision
critical_config = ExtractionConfig(
    confidence_threshold=0.80,
    max_entities=50,
    max_relationships=200,
    window_size=3,
    min_entity_length=4,
    llm_fallback_threshold=0.7,  # LLM for difficult cases
    max_confidence=0.95,  # Conservative calibration
    stopwords=[...],  # Comprehensive stopword list
    allowed_entity_types=["person", "organization", "date"],
)
```

**Use Cases**: Legal systems, medical records, compliance applications

---

### Pattern 4: Domain-Specific Extraction

```python
# Tailored to specific domain (example: legal documents)
legal_config = ExtractionConfig(
    confidence_threshold=0.60,
    max_entities=150,
    max_relationships=750,
    window_size=7,
    domain_vocab={
        "person": ["plaintiff", "defendant", "attorney", "judge"],
        "organization": ["court", "firm", "corporation"],
        "document": ["complaint", "motion", "brief", "order"],
    },
    custom_rules=[
        (r'\d+ U\.S\. \d+', 'case_citation'),
        (r'No\. \d+-\d+', 'docket_number'),
    ],
    stopwords=["case", "court", "filed", "see", "also"],
    allowed_entity_types=["person", "organization", "document", "date", "location"],
    llm_fallback_threshold=0.55,
)
```

**Use Cases**: Legal tech, regulatory compliance, specialized knowledge extraction

---

## Configuration Methods

### Validation

Always validate configuration before use:

```python
config = ExtractionConfig(confidence_threshold=0.75)
config.validate()  # Raises ValueError if invalid
```

### Merging Configurations

Layer configurations for flexibility:

```python
# Base configuration
base = ExtractionConfig(
    confidence_threshold=0.6,
    max_entities=100,
)

# Override specific fields
override = ExtractionConfig(
    confidence_threshold=0.8,  # Override
    max_relationships=500,     # New field
)

merged = base.merge(override)
# Result: confidence_threshold=0.8, max_entities=100, max_relationships=500
```

### Environment-Based Configuration

Load from environment variables:

```bash
export EXTRACTION_CONFIDENCE_THRESHOLD=0.75
export EXTRACTION_MAX_ENTITIES=100
export EXTRACTION_LLM_FALLBACK_THRESHOLD=0.5
```

```python
config = ExtractionConfig.from_env()
# Loads all EXTRACTION_* env vars
```

### Dictionary Serialization

Save and load configurations:

```python
# Serialize to dict
config_dict = config.to_dict()

# Store in JSON, YAML, etc.
import json
with open('config.json', 'w') as f:
    json.dump(config_dict, f)

# Load from dict
loaded_config = ExtractionConfig.from_dict(config_dict)
```

### Human-Readable Description

```python
config = ExtractionConfig(
    confidence_threshold=0.75,
    max_entities=100,
)

description = config.describe()
print(description)
# Output: "confidence=0.75, max_entities=100, max_rels=0, window=5, llm_fallback=0.0"
```

---

## Performance Tuning Guide

### Extraction Speed Optimization

**Goal**: Minimize end-to-end extraction time

```python
fast_config = ExtractionConfig(
    max_entities=50,           # Limit entity count
    max_relationships=200,     # Limit relationships
    window_size=3,             # Narrow window
    llm_fallback_threshold=0.0,  # No LLM calls
    custom_rules=[],           # Minimal regex patterns
)
```

**Expected Speedup**: 2-5x faster than default for large documents

---

### Memory Optimization

**Goal**: Minimize memory footprint

```python
memory_efficient_config = ExtractionConfig(
    max_entities=30,           # Strict entity limit
    max_relationships=100,     # Strict relationship limit
    include_properties=False,  # Simpler graph
)
```

**Memory Savings**: 50-80% reduction in graph size

---

### Quality Maximization

**Goal**: Highest precision and recall

```python
quality_config = ExtractionConfig(
    confidence_threshold=0.65,  # Balanced threshold
    max_entities=0,             # No artificial limits
    max_relationships=0,
    window_size=7,              # Wider context
    llm_fallback_threshold=0.5, # Hybrid extraction
    domain_vocab={...},         # Rich vocabulary
    custom_rules=[...],         # Domain patterns
)
```

**Quality Improvement**: +20-40% F1 score vs default

---

### Cost Optimization (LLM Usage)

**Goal**: Minimize LLM API costs while maintaining quality

```python
cost_optimized_config = ExtractionConfig(
    confidence_threshold=0.70,  # Higher threshold reduces LLM calls
    llm_fallback_threshold=0.4, # Conservative fallback
    max_entities=80,            # Limit LLM scope
)
```

**Cost Savings**: 60-80% reduction in LLM API calls

---

## Troubleshooting

### Too Few Entities Extracted

**Symptoms**: Extraction returns very few entities

**Solutions**:
1. Lower `confidence_threshold` (try 0.3-0.5)
2. Reduce `min_entity_length` (try 2)
3. Remove or relax `allowed_entity_types` filter
4. Enable `llm_fallback_threshold` for hybrid extraction
5. Check `max_entities` is not too restrictive

### Too Many Low-Quality Entities

**Symptoms**: Many spurious or irrelevant entities

**Solutions**:
1. Raise `confidence_threshold` (try 0.7-0.8)
2. Increase `min_entity_length` (try 3-4)
3. Add comprehensive `stopwords` list
4. Use `allowed_entity_types` to filter unwanted types
5. Lower `max_entities` to keep only top-ranked

### Slow Extraction Performance

**Symptoms**: Extraction takes too long

**Solutions**:
1. Set `max_entities` limit (try 50-100)
2. Set `max_relationships` limit (try 200-500)
3. Reduce `window_size` (try 3-5)
4. Disable `llm_fallback_threshold` (set to 0.0)
5. Minimize `custom_rules` regex patterns

### High LLM Costs

**Symptoms**: Excessive API charges

**Solutions**:
1. Raise `llm_fallback_threshold` (reduce fallback rate)
2. Increase `confidence_threshold` (filter before LLM)
3. Set `max_entities` to limit LLM scope
4. Cache LLM results
5. Consider rule-only extraction for low-value documents

### Missing Expected Entities

**Symptoms**: Known entities not extracted

**Solutions**:
1. Check entity text length vs `min_entity_length`
2. Verify entity type in `allowed_entity_types` (if set)
3. Check if entity text is in `stopwords`
4. Add `custom_rules` for structured entity patterns
5. Lower `confidence_threshold`

---

## Migration Guide

### From Dict-Based Config

**Before**:
```python
config = {
    "confidence_threshold": 0.7,
    "max_entities": 100,
}
```

**After**:
```python
config = ExtractionConfig(
    confidence_threshold=0.7,
    max_entities=100,
)
```

### From Environment Variables

**Before**: Manual env var parsing

**After**:
```python
config = ExtractionConfig.from_env(prefix="EXTRACTION_")
```

---

## References

- [OntologyGenerator Documentation](ARCHITECTURE.md#ontologygenerator)
- [Relationship Type Confidence Guide](HACC_ANALYSIS_README.md)
- [GraphRAG Integration Architecture](HACC_INTEGRATION_ARCHITECTURE.md)
- [Extraction Pipeline Examples](EXAMPLES.md#extraction-examples)

---

## Version History

- **v1.0**: Initial comprehensive configuration guide
- Fields documented: 11 core fields + advanced options
- Patterns documented: 4 common configuration patterns
- Performance tuning: 4 optimization strategies
