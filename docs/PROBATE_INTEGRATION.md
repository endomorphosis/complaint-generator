# Probate Complaint Type Integration

## Overview

The complaint_analysis module now includes probate and estate law as a fully integrated complaint type. This brings the total number of complaint types to 14 (13 original + probate).

## What Was Added

### 1. Probate Keywords (203 total)

Comprehensive keywords covering all major areas of probate law:

**Probate Process**
- probate, probate court, estate administration, surrogate court, orphans court

**Parties**
- decedent, executor, administrator, beneficiary, heir, trustee, guardian, conservator, ward

**Documents**
- will, testament, codicil, trust, letters testamentary, letters of administration

**Disputes**
- will contest, undue influence, breach of fiduciary duty, trust litigation

**Estate Types**
- testate, intestate, probate asset, non-probate asset

**And many more covering**: assets, taxes, debts, inheritance, guardianship, trust types, powers of attorney, estate planning

### 2. Legal Patterns (28 regex patterns)

Regex patterns for identifying probate-related legal terms in text:
- Probate court proceedings
- Executor/administrator terminology
- Will and trust language
- Estate taxes and claims
- Guardianship terminology
- Legal concepts (undue influence, testamentary capacity, fiduciary duty)

### 3. Decision Tree (10 questions)

A structured decision tree guiding complaint intake with questions about:
1. Decedent name
2. Date of death
3. Type of probate issue
4. Decedent residence
5. Will or trust existence
6. Fiduciary identification
7. Specific issues/disputes
8. Estate assets
9. Relationship to decedent
10. Probate court information

### 4. Seed Templates

Automatic generation of probate seed templates for adversarial testing with:
- 160+ keywords
- 2+ required fields
- Probate-specific scenarios

## Usage

### Get Probate Keywords

```python
from complaint_analysis.keywords import get_keywords

keywords = get_keywords('complaint', complaint_type='probate')
print(f"Found {len(keywords)} probate keywords")
# Output: Found 203 probate keywords
```

### Get Probate Legal Patterns

```python
from complaint_analysis.legal_patterns import get_legal_terms

patterns = get_legal_terms('probate')
print(f"Found {len(patterns)} probate legal patterns")
# Output: Found 28 probate legal patterns
```

### Load Probate Decision Tree

```python
import json

with open('complaint_analysis/decision_trees/probate_tree.json', 'r') as f:
    probate_tree = json.load(f)

print(f"Questions: {len(probate_tree['questions'])}")
print(f"Required fields: {len(probate_tree['required_fields'])}")
# Output: Questions: 10
# Output: Required fields: 7
```

### Generate Probate Seeds

```python
from complaint_analysis import SeedGenerator

generator = SeedGenerator()
probate_templates = [
    (tid, t) for tid, t in generator.templates.items() 
    if 'probate' in tid
]

print(f"Generated {len(probate_templates)} probate templates")
# Output: Generated 1 probate templates
```

### Search Legal Corpus for Probate

```python
from mediator import LegalCorpusRAGHook

legal_hook = LegalCorpusRAGHook(mediator)
results = legal_hook.search_legal_corpus(
    query="will contest undue influence",
    complaint_type="probate"
)

print(f"Found {len(results)} relevant legal provisions")
```

## Integration Status

✅ **Works with all existing complaint_analysis features:**
- SeedGenerator for adversarial testing
- DecisionTreeGenerator for question guidance
- LegalCorpusRAGHook for legal research
- PromptLibrary for structured prompts
- ResponseParsers for LLM response parsing
- Search hooks for evidence gathering

## Testing

Run the test suite:

```bash
python3 test_probate_integration.py
```

Expected output:
```
============================================================
PROBATE COMPLAINT TYPE INTEGRATION TEST
============================================================
Testing probate registration...
✓ Found 14 registered complaint types
✓ Probate is registered

Testing probate keywords...
✓ Found 203 probate keywords
✓ All expected keywords found: ['probate', 'executor', 'will', 'trust', 'estate', 'decedent']

Testing probate seed generation...
✓ Generated 1 probate seed template(s)

Testing probate decision tree...
✓ Probate decision tree exists

Testing probate legal patterns...
✓ Found 28 probate legal patterns

============================================================
RESULTS: 5/5 tests passed
============================================================

✓ All tests PASSED!
```

## Domain Coverage

The probate integration covers all major areas of probate and estate law:

- **Wills & Testaments**: Last will and testament, codicils, holographic wills, testamentary capacity
- **Trusts**: Living trusts, testamentary trusts, revocable/irrevocable trusts, special needs trusts, charitable trusts
- **Estate Administration**: Probate process, letters testamentary, estate accounting, asset distribution
- **Guardianship**: Guardian of the person, guardian of the estate, conservatorship, adult guardianship
- **Disputes**: Will contests, undue influence, breach of fiduciary duty, trust litigation
- **Taxation**: Estate tax, inheritance tax, gift tax
- **Powers**: Power of attorney, healthcare directives, advance directives
- **Inheritance**: Intestate succession, statutory share, per stirpes distribution

## Complete List of Complaint Types

The complaint_analysis module now supports 14 complaint types:

1. housing
2. employment
3. civil_rights
4. consumer
5. healthcare
6. free_speech
7. immigration
8. family_law
9. criminal_defense
10. tax_law
11. intellectual_property
12. environmental_law
13. dei (diversity, equity, inclusion)
14. **probate** (NEW)

## Next Steps

To further enhance probate support:
- Add more specific trust subtypes
- Expand guardianship scenarios
- Include more estate planning keywords
- Add jurisdiction-specific probate rules
- Create specialized prompts for probate documents

## References

- Code: `complaint_analysis/complaint_types.py` - `register_probate_complaint()`
- Decision Tree: `complaint_analysis/decision_trees/probate_tree.json`
- Tests: `test_probate_integration.py`
- Keywords: 203 probate-specific terms
- Legal Patterns: 28 regex patterns
