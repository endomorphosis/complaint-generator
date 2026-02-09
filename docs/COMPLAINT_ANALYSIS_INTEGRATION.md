# complaint_analysis Integration with Adversarial Harness

## Overview

This document describes the integration between the `complaint_analysis` module and the `adversarial_harness` testing framework, implementing all requirements from the problem statement.

## Problem Statement Requirements

The goal was to:

1. **Use complaint_analysis data to create seeds** for adversarial testing framework
2. **Generate decision trees** from complaint_analysis to guide question pool generation
3. **Create prompt engineering programs** with format: `| system prompt | return format | warnings | payload |`
4. **Create parsers** to parse LLM responses and ingest into statefiles

## Implementation

### 1. Seed Generation (`complaint_analysis/seed_generator.py`)

**Purpose**: Automatically generate complaint seeds from registered complaint types.

**Features**:
- Converts 12+ complaint types into reusable templates
- Includes type-specific keywords and legal patterns
- Supports all registered types: housing, employment, civil_rights, consumer, healthcare, free_speech, immigration, family_law, criminal_defense, tax_law, intellectual_property, environmental_law, dei

**Usage**:
```python
from complaint_analysis import SeedGenerator

generator = SeedGenerator()
templates = generator.list_templates(category='housing')
seed = generator.generate_seed('housing_discrimination_1', {
    'landlord_name': 'Test LLC',
    'protected_class': 'race',
    'discriminatory_action': 'refused rental'
})
```

**Integration**: `adversarial_harness/seed_complaints.py` now uses `SeedGenerator` instead of hardcoded templates.

### 2. Decision Trees (`complaint_analysis/decision_trees.py`)

**Purpose**: Provide structured question sequences for guiding complaint intake.

**Features**:
- 13 pre-generated decision tree JSON files (76 total questions)
- Questions have dependencies (ask B after A is answered)
- Prioritizes required vs optional information
- Tracks field names for state management
- Method: `get_next_questions(answered_fields)` returns what to ask next

**Decision Tree Structure**:
```json
{
  "complaint_type": "housing",
  "category": "housing",
  "root_questions": ["q1", "q2", "q3"],
  "questions": {
    "q1": {
      "id": "q1",
      "question": "Who is the landlord?",
      "field_name": "landlord_name",
      "required": true,
      "depends_on": [],
      "keywords": ["landlord", "owner"]
    }
  },
  "required_fields": ["landlord_name", "property_address"],
  "optional_fields": ["witnesses"]
}
```

**Usage**:
```python
from complaint_analysis import DecisionTreeGenerator

generator = DecisionTreeGenerator(output_dir='complaint_analysis/decision_trees')
tree = generator.generate_tree('housing')

# Get next questions based on what's answered
answered = {'landlord_name', 'property_address'}
next_questions = tree.get_next_questions(answered)
```

**Pre-generated Files**:
- `complaint_analysis/decision_trees/housing_tree.json`
- `complaint_analysis/decision_trees/employment_tree.json`
- ... (13 total files)

**Generation Script**: `scripts/generate_decision_trees.py` regenerates all trees.

### 3. Prompt Templates (`complaint_analysis/prompt_templates.py`)

**Purpose**: Structure LLM prompts with consistent 4-section format.

**Format**:
```
## SYSTEM PROMPT
<role and context>

## RETURN FORMAT
<expected output structure>

## WARNINGS
- <constraint 1>
- <constraint 2>

## PAYLOAD
<actual query with data>
```

**Pre-built Templates** (9 total):
1. `extract_entities` - Extract parties, dates, locations
2. `extract_relationships` - Find entity relationships
3. `generate_questions` - Create denoising questions
4. `extract_claims` - Identify legal claims
5. `extract_requirements` - Determine proof requirements
6. `synthesize_summary` - Create human-readable summaries
7. `evaluate_evidence` - Assess evidence quality
8. `generate_formal_complaint` - Draft formal documents
9. `assess_viability` - Evaluate claim strength

**Usage**:
```python
from complaint_analysis import PromptLibrary

library = PromptLibrary()
prompt = library.format_prompt('extract_entities', {
    'complaint_text': 'John was fired by Acme Corp on Jan 15, 2024'
})

# Send prompt to LLM
response = llm.generate(prompt)
```

**Benefits**:
- Consistent prompt structure across all LLM calls
- Built-in warnings and constraints
- Specified return formats
- Reusable templates

### 4. Response Parsers (`complaint_analysis/response_parsers.py`)

**Purpose**: Parse LLM responses and ingest into statefiles.

**Parser Types**:
- `JSONResponseParser` - Parse JSON with schema validation
- `StructuredTextParser` - Parse section-based text
- `EntityParser` - Parse entity extraction responses
- `RelationshipParser` - Parse relationship extraction
- `QuestionParser` - Parse generated questions
- `ClaimParser` - Parse legal claims

**Statefile Ingestion**:
```python
from complaint_analysis import StateFileIngester, ResponseParserFactory

# Parse response
parser = ResponseParserFactory.get_parser('entities')
parsed = parser.parse(llm_response)

# Ingest to statefile
ingester = StateFileIngester('statefiles/')
if parsed.success:
    ingester.ingest_entities(parsed, 'session_123')
```

**Statefile Outputs**:
- `statefiles/{session}_knowledge_graph.json` - Entities and relationships
- `statefiles/{session}_dependency_graph.json` - Claims and requirements
- `statefiles/{session}_summary.json` - Human-readable summaries

**Features**:
- Validates responses against schemas
- Handles errors gracefully
- Extracts JSON from markdown code blocks
- Appends to existing statefiles

## Integration Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  complaint_analysis                      │
│                                                          │
│  ┌─────────────┐  ┌───────────────┐  ┌──────────────┐ │
│  │    Seed     │  │   Decision    │  │   Prompt     │ │
│  │  Generator  │  │     Trees     │  │  Templates   │ │
│  └──────┬──────┘  └───────┬───────┘  └──────┬───────┘ │
│         │                 │                  │          │
└─────────┼─────────────────┼──────────────────┼──────────┘
          │                 │                  │
          ▼                 ▼                  ▼
┌─────────────┐   ┌────────────────┐   ┌─────────────┐
│ adversarial │   │  complaint_    │   │  mediator/  │
│   harness   │   │   phases/      │   │  mediator   │
│             │   │   denoiser     │   │             │
└─────────────┘   └────────────────┘   └──────┬──────┘
                                               │
                                               ▼
                                        ┌──────────────┐
                                        │   Response   │
                                        │   Parsers    │
                                        └──────┬───────┘
                                               │
                                               ▼
                                        ┌──────────────┐
                                        │  statefiles/ │
                                        │     *.json   │
                                        └──────────────┘
```

## Usage Examples

### Complete Workflow

```python
from complaint_analysis import (
    SeedGenerator,
    DecisionTreeGenerator,
    PromptLibrary,
    ResponseParserFactory,
    StateFileIngester
)

# 1. Generate seed from complaint type
seed_gen = SeedGenerator()
seed = seed_gen.generate_seed('housing_discrimination_1', values)

# 2. Load decision tree for guided questions
tree_gen = DecisionTreeGenerator()
tree = tree_gen.generate_tree('housing')

# 3. Generate questions based on decision tree
answered_fields = set()
next_questions = tree.get_next_questions(answered_fields)

# 4. Format prompt for LLM
prompt_lib = PromptLibrary()
prompt = prompt_lib.format_prompt('generate_questions', {
    'complaint_type': 'housing',
    'current_info': current_data,
    'missing_fields': list(tree.required_fields - answered_fields)
})

# 5. Send to LLM and parse response
llm_response = llm.generate(prompt)
parser = ResponseParserFactory.get_parser('questions')
parsed = parser.parse(llm_response)

# 6. Ingest to statefiles
if parsed.success:
    ingester = StateFileIngester('statefiles/')
    ingester.ingest_questions(parsed, session_id)
```

### Adversarial Testing

```python
from adversarial_harness import SeedComplaintLibrary

# Now automatically uses complaint_analysis
library = SeedComplaintLibrary()

# Get seeds with keywords and legal patterns
seeds = library.get_seed_complaints(count=10)

# Each seed includes:
# - template_id
# - type (e.g., 'housing_discrimination')
# - category (e.g., 'housing')
# - key_facts
# - keywords (from complaint_analysis)
# - legal_patterns (from complaint_analysis)
```

## Testing

### Test Coverage

**New Tests**: `tests/test_complaint_analysis_integration.py`
- 34 tests covering all new modules
- 100% passing

**Test Breakdown**:
- `TestSeedGenerator`: 7 tests
- `TestDecisionTreeGenerator`: 7 tests
- `TestPromptTemplates`: 6 tests
- `TestResponseParsers`: 9 tests
- `TestStateFileIngester`: 5 tests

**Existing Tests**:
- `tests/test_adversarial_harness.py`: 18 tests (all passing with integration)

**Total**: 52 tests, 100% passing

### Running Tests

```bash
# Test new modules
pytest tests/test_complaint_analysis_integration.py -v

# Test adversarial harness integration
pytest tests/test_adversarial_harness.py -v

# Run all tests
pytest tests/ -v
```

## Demos

### Integration Demo

Run the comprehensive demo:
```bash
python examples/complaint_analysis_integration_demo.py
```

Shows:
1. Seed generation from complaint types
2. Decision tree question flow
3. Prompt template formatting
4. Response parsing and validation
5. Adversarial harness integration

## Files Added/Modified

### New Files

**Modules**:
- `complaint_analysis/seed_generator.py` (580 lines)
- `complaint_analysis/decision_trees.py` (820 lines)
- `complaint_analysis/prompt_templates.py` (420 lines)
- `complaint_analysis/response_parsers.py` (625 lines)

**Decision Trees**:
- `complaint_analysis/decision_trees/*.json` (13 files)

**Scripts**:
- `scripts/generate_decision_trees.py`

**Tests**:
- `tests/test_complaint_analysis_integration.py` (480 lines, 34 tests)

**Examples**:
- `examples/complaint_analysis_integration_demo.py`

### Modified Files

- `complaint_analysis/__init__.py` - Added exports for new modules
- `adversarial_harness/seed_complaints.py` - Now uses SeedGenerator

## Benefits

### 1. Data-Driven

Seeds automatically generated from structured complaint type definitions rather than hardcoded templates.

### 2. Scalable

New complaint types registered in complaint_analysis automatically become available as seeds and decision trees.

### 3. Consistent

All LLM interactions use structured prompt templates ensuring reliable results.

### 4. Validated

Response parsing with schema validation catches errors early and ensures data integrity.

### 5. Maintainable

Single source of truth for complaint knowledge reduces duplication and inconsistencies.

### 6. Extensible

Easy to add new templates, decision trees, parsers, and prompt formats.

## Future Enhancements

### Potential Improvements

1. **Machine Learning**: Use ML to optimize decision tree question ordering
2. **Adaptive Trees**: Dynamically adjust trees based on user responses
3. **Prompt Evolution**: A/B test different prompt formats
4. **Parser Learning**: Train parsers on actual LLM responses
5. **Graph Integration**: Direct integration with knowledge/dependency graphs
6. **Multilingual**: Support for non-English complaints
7. **Domain Expansion**: Add more specialized complaint types

## Conclusion

The integration successfully implements all requirements from the problem statement:

✅ Seeds generated from complaint_analysis data  
✅ Decision trees guide question pools  
✅ Prompt templates provide structured LLM interactions  
✅ Response parsers ingest into statefiles  

The system is now ready for production use with comprehensive testing, documentation, and examples demonstrating the complete workflow from seed generation through statefile ingestion.
