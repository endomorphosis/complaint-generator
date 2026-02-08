# HACC Integration Module

This module extracts and adapts the legal domain knowledge from the [HACC repository](https://github.com/endomorphosis/HACC) for use with [ipfs_datasets_py](https://github.com/endomorphosis/ipfs_datasets_py) infrastructure.

## Overview

The HACC Integration module provides the **unique value** of HACC (legal expertise) integrated with ipfs_datasets_py's **superior infrastructure** (search, PDF processing, storage, knowledge graphs).

### What's Included from HACC

1. **Legal Pattern Extraction** (`legal_patterns.py`)
   - Regex patterns for complaint-relevant legal terms
   - Statutory citation extraction
   - Protected class identification
   - Complaint categorization

2. **Complaint Keywords** (`keywords.py`)
   - Domain-specific terminology taxonomies
   - Evidence keywords
   - Legal authority keywords
   - Applicability tags (housing, employment, etc.)
   - Severity indicators

3. **Risk Scoring** (`risk_scoring.py`)
   - Risk calculation algorithms (0-3 scale)
   - Factor identification
   - Actionable recommendations
   - Severity categorization

4. **Hybrid Indexer** (`indexer.py`)
   - Combines vector embeddings (ipfs_datasets_py)
   - With keyword matching (HACC)
   - Provides comprehensive document analysis

### What's Used from ipfs_datasets_py

- **Web Search**: `BraveSearchClient`, `CommonCrawlSearchEngine`
- **PDF Processing**: `PDFProcessor` with GPU OCR
- **Vector Embeddings**: `EmbeddingsRouter`
- **Knowledge Graphs**: GraphRAG integration
- **Storage**: IPFS-native with automatic deduplication

## Usage

### Basic Legal Pattern Extraction

```python
from hacc_integration import ComplaintLegalPatternExtractor

extractor = ComplaintLegalPatternExtractor()
result = extractor.extract_provisions(document_text)

for provision in result['provisions']:
    print(f"{provision['term']}: {provision['context'][:100]}")

# Categorize complaint
categories = extractor.categorize_complaint_type(document_text)
print(f"Complaint categories: {categories}")

# Find protected classes
protected_classes = extractor.find_protected_classes(document_text)
print(f"Protected classes: {protected_classes}")
```

### Risk Scoring

```python
from hacc_integration import ComplaintRiskScorer

scorer = ComplaintRiskScorer()
risk = scorer.calculate_risk(document_text)

print(f"Risk Level: {risk['level']} (score: {risk['score']})")
print(f"Factors: {risk['factors']}")
print(f"Recommendations: {risk['recommendations']}")

# Check if actionable
if scorer.is_actionable(document_text):
    print("This complaint requires action!")
```

### Hybrid Document Indexing

```python
from hacc_integration import HybridDocumentIndexer

indexer = HybridDocumentIndexer()
result = await indexer.index_document(text, metadata={'source': 'complaint_form'})

print(f"Risk: {result['risk_level']}")
print(f"Keywords: {result['keywords']}")
print(f"Legal provisions: {result['legal_provisions']['provision_count']}")
print(f"Applicability: {result['applicability']}")
print(f"Relevance score: {result['relevance_score']}")
```

### Integration with ipfs_datasets_py

```python
from ipfs_datasets_py.web_archiving import BraveSearchClient
from ipfs_datasets_py.pdf_processing import PDFProcessor
from hacc_integration import ComplaintLegalPatternExtractor, ComplaintRiskScorer

# Use ipfs_datasets_py for infrastructure
search = BraveSearchClient(cache_ipfs=True)
results = search.search('site:gov "fair housing" filetype:pdf', count=50)

processor = PDFProcessor(enable_ocr=True, hardware_acceleration=True)
pdf_result = await processor.process_document(pdf_path)

# Use HACC for legal expertise
extractor = ComplaintLegalPatternExtractor()
provisions = extractor.extract_provisions(pdf_result.text)

scorer = ComplaintRiskScorer()
risk = scorer.calculate_risk(pdf_result.text, provisions)

print(f"Found {len(provisions)} legal provisions with risk level: {risk['level']}")
```

## Module Structure

```
hacc_integration/
├── __init__.py              # Module exports
├── legal_patterns.py        # Legal term patterns and extraction
├── keywords.py              # Complaint-specific keyword taxonomies
├── risk_scoring.py          # Risk assessment algorithms
├── indexer.py               # Hybrid document indexer
└── README.md                # This file
```

## Keywords

### Complaint Keywords
Discrimination, harassment, retaliation, fair housing, protected classes, etc.

### Evidence Keywords
Witness, testimony, documentation, exhibits, correspondence, etc.

### Legal Authority Keywords
Statutes, regulations, case law, precedent, constitutional provisions, etc.

### Applicability Areas
- Housing
- Employment
- Public accommodation
- Lending
- Education
- Government services

## Risk Levels

- **0 (Minimal)**: No significant legal issues identified
- **1 (Low)**: Potential legal issues, needs review
- **2 (Medium)**: Probable legal issues, requires action
- **3 (High)**: Clear legal issues, immediate action needed

## Legal Terms Covered

- Fair Housing Act (FHA)
- Title VII (employment discrimination)
- Americans with Disabilities Act (ADA)
- Age Discrimination in Employment Act (ADEA)
- Family and Medical Leave Act (FMLA)
- Section 8 Housing
- Protected classes (race, color, religion, sex, disability, etc.)
- Reasonable accommodations
- Disparate impact/treatment
- Remedies and relief

## Integration Points

This module is designed to integrate seamlessly with the complaint-generator mediator:

1. **Evidence Hooks**: Use with `EvidenceAnalysisHook` for automatic legal analysis
2. **Legal Authority Hooks**: Extract citations for `LegalAuthorityStorageHook`
3. **Web Evidence Hooks**: Combine with search results for relevance scoring
4. **Mediator Workflows**: Integrate into complaint intake and analysis pipelines

## Performance

- Legal pattern extraction: ~100ms for typical document (1000 words)
- Risk scoring: ~50ms (uses cached patterns)
- Hybrid indexing: ~2-3s with embeddings, ~200ms without

## Dependencies

### Required
- Python 3.8+
- No external dependencies (uses only standard library)

### Optional (for full functionality)
- `ipfs_datasets_py` - For vector embeddings and advanced features

## Testing

```bash
# Run tests for hacc_integration module
pytest tests/test_hacc_integration.py -v

# Test with specific categories
pytest tests/test_hacc_integration.py::test_legal_extraction -v
pytest tests/test_hacc_integration.py::test_risk_scoring -v
```

## License

This module adapts patterns and approaches from the HACC repository while providing original implementations. See the main repository LICENSE for details.

## Credits

- Legal patterns adapted from [HACC repository](https://github.com/endomorphosis/HACC)
- Infrastructure provided by [ipfs_datasets_py](https://github.com/endomorphosis/ipfs_datasets_py)
- Integration developed for complaint-generator project
