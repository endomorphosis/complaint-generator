# Performance Tuning Guide

## Overview

This guide summarizes the most impactful performance levers for the GraphRAG
pipeline, focusing on the rule-based extractor and relationship inference. It
pulls from profiling reports in:

- [INFER_RELATIONSHIPS_PERFORMANCE_ANALYSIS.md](ipfs_datasets_py/docs/profiling/INFER_RELATIONSHIPS_PERFORMANCE_ANALYSIS.md)
- [PROFILING_EXTRACT_RULE_BASED.md](ipfs_datasets_py/docs/PROFILING_EXTRACT_RULE_BASED.md)

The two largest costs are:
1. Relationship inference (O(n^2) entity pair checks).
2. Regex-based entity extraction (multiple full-text scans).

## Quick Wins (Most Impact, Low Risk)

### 1) Cache lowercased strings

**Why:** String lowering and substring searching account for a large share of
runtime in relationship inference.

**Where:** `OntologyGenerator.infer_relationships()`.

**Approach:**
- Compute `text_lower` once.
- Cache `entity.text.lower()` once per entity.
- Reuse cached values for find/compare operations.

**Expected gain:** 30-40% in relationship inference on mid-size workloads.

### 2) Pre-compute entity positions

**Why:** Repeated `text.find()` calls are expensive and scale with entity count.

**Approach:**
- Build a dict of `entity_id -> position` once.
- Skip pairs when either position is missing.

**Expected gain:** 20-30% on co-occurrence-heavy corpora.

### 3) Pre-compile regex patterns

**Why:** Rule-based extraction scans the text with many regex patterns. Compile
once and reuse.

**Where:** `_extract_entities_from_patterns()`.

**Expected gain:** 10-15% for repeated extractions.

## Configuration Tuning

### ExtractionConfig settings

- `confidence_threshold`: Higher reduces entity count (and pair checks). Use a
  higher threshold for performance-sensitive workloads.
- `max_entities`: Cap entity growth early to keep O(n^2) relationship inference
  bounded.
- `max_relationships`: Prevent runaway relationship growth.
- `min_entity_length`: Reduces noisy entities and downstream pair checks.
- `stopwords`: Expands stopword list to reduce trivial entities.

See [EXTRACTION_CONFIG_GUIDE.md](ipfs_datasets_py/docs/EXTRACTION_CONFIG_GUIDE.md)
for details.

### Relationship window size

Co-occurrence checks are distance-based. Lowering the effective window (or
skipping pairs beyond a threshold) reduces pair evaluations.

## Profiling Playbook

### Profile relationship inference

Use the existing benchmark harness:

```bash
python ipfs_datasets_py/scripts/profile_infer_relationships.py
```

Focus on:
- `.lower()` and `.find()` hot spots
- Pair loop counts (`n(n-1)/2`)

### Profile rule-based extraction

```bash
python -m cProfile -o /tmp/extract.prof \
  -m ipfs_datasets_py.optimizers.graphrag.ontology_generator
```

Then review with:

```bash
python -m pstats /tmp/extract.prof
```

## Scaling Guidance

### Relationship inference is O(n^2)

- 100 entities => 4,950 pairs
- 500 entities => 124,750 pairs
- 1000 entities => 499,500 pairs

Keep entity counts bounded or reduce pair checks using position-based filters.

### Rule-based extraction is O(n)

The extractor scales linearly with input length, but the constant factor is
influenced by:
- Number of regex patterns
- Stopword filtering
- Lowercasing and dedup logic

## Optimization Roadmap

### Phase 1 (low effort, high impact)
- Cache lowercased text and entity strings.
- Pre-compute entity positions.
- Pre-compile regex patterns.

### Phase 2 (moderate effort)
- Filter pairs by distance using a sorted position list.
- Introduce early exit conditions for low-quality entities.

### Phase 3 (high impact, higher effort)
- Use spatial indexing (interval trees) for proximity filtering.
- Parallelize relationship inference for large entity sets.

## Validation Checklist

- Benchmark before and after changes using the same text corpus.
- Track entity/relationship counts to confirm no regressions in quality.
- Validate that confidence scores remain within expected ranges.

## References

- [INFER_RELATIONSHIPS_PERFORMANCE_ANALYSIS.md](ipfs_datasets_py/docs/profiling/INFER_RELATIONSHIPS_PERFORMANCE_ANALYSIS.md)
- [PROFILING_EXTRACT_RULE_BASED.md](ipfs_datasets_py/docs/PROFILING_EXTRACT_RULE_BASED.md)
- [EXTRACTION_CONFIG_GUIDE.md](ipfs_datasets_py/docs/EXTRACTION_CONFIG_GUIDE.md)
