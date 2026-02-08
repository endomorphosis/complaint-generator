# HACC Repository Python Scripts - Reuse Analysis

**Repository:** https://github.com/endomorphosis/HACC  
**Path:** research_data/scripts  
**Analysis Date:** 2026-02-08  
**Purpose:** Identify reusable components for complaint intake, evidence gathering, and legal citation research

---

## Executive Summary

The HACC repository contains 34+ Python scripts in the `research_data/scripts` directory that implement a comprehensive legal research and document analysis pipeline. Many of these scripts can be directly reused or adapted for the complaint-generator system's needs around:

1. **Complaint Intake** - Web search and document discovery
2. **Evidence Gathering** - Document download, parsing, and management
3. **Legal Citation Research** - Statute extraction, legal keyword tagging, and analysis

### High-Priority Scripts for Immediate Reuse

| Script | Purpose | Reuse Potential |
|--------|---------|-----------------|
| `collect_brave.py` | Brave Search API integration | **CRITICAL** - Direct reuse for evidence discovery |
| `download_manager.py` | URL deduplication + PDF management | **CRITICAL** - Core infrastructure for evidence curation |
| `parse_pdfs.py` | PDF text extraction with OCR fallback | **CRITICAL** - Essential for document processing |
| `index_and_tag.py` | Document indexing + keyword tagging | **HIGH** - Adaptable for complaint-specific keywords |
| `deep_analysis.py` | Legal provision extraction | **HIGH** - Statutory context extraction |
| `report_generator.py` | Risk-scored summary reports | **HIGH** - Complaint summary generation |
| `seeded_commoncrawl_discovery.py` | CommonCrawl web archiving | **HIGH** - Policy/regulation discovery |

---

## 1. Complaint Intake & Discovery Scripts

### 1.1 `collect_brave.py` - Web Search Integration

**Purpose:** Execute searches via Brave Search API and collect results with metadata.

**Key Classes/Functions:**
- `BraveCollector` - Main search collector class
  - `search(query, count)` - Execute single search
  - `batch_search(queries)` - Execute multiple searches
  - `save_results()` - Save to JSON with timestamps

**Dependencies:**
- `requests` for HTTP calls
- `BRAVE_API_KEY` environment variable

**Reuse Strategy for Complaint Generator:**
```python
# Example integration
from hacc_scripts.collect_brave import BraveCollector

collector = BraveCollector(output_dir="evidence/search_results/")

# Search for evidence related to complaint
queries = [
    'site:gov "fair housing" "complaint" filetype:pdf',
    'site:gov "landlord" "discrimination" filetype:pdf',
    'site:.edu "tenant rights" "legal aid" filetype:pdf'
]

results = collector.batch_search(queries)
collector.save_results()
```

**Adaptation Needed:**
- Replace DEI-specific queries with complaint-type-based queries
- Add filtering for relevant legal domains (.gov, .edu, .org)
- Integrate with mediator's `WebEvidenceSearchHook`

---

### 1.2 `seeded_commoncrawl_discovery.py` - Archive-Based Discovery

**Purpose:** Query CommonCrawl web archives to find historical documents and policies.

**Key Functions:**
- `parse_query(query)` - Extract site filters and keywords from search queries
- `commoncrawl_list_urls(domain, index)` - Query CommonCrawl index for URLs
- `score_url(url, keywords)` - Rank URLs by keyword relevance
- `fetch_text(url)` - Retrieve archived page content

**Dependencies:**
- `requests` for CommonCrawl API
- `cdx_toolkit` (optional) for advanced querying

**Reuse Strategy:**
```python
# Search archived government sites for complaint-relevant policies
from hacc_scripts.seeded_commoncrawl import search_commoncrawl

results = search_commoncrawl(
    query='site:oregon.gov "fair housing" OR "tenant rights"',
    keywords=['fair housing', 'discrimination', 'complaint'],
    max_results=50
)
```

**Use Cases:**
- Finding historical housing authority policies
- Discovering removed/archived complaint procedures
- Researching regulatory history for legal citations

---

### 1.3 `enhanced_research.py` - Statute & Regulation Research

**Purpose:** Automated research for legal statutes and regulations using web scraping.

**Key Features:**
- Async Playwright for JavaScript-heavy legal sites
- Full-text statute downloads
- Keyword-based relevance filtering

**Reuse Strategy:**
- Adapt domain filters for complaint-relevant jurisdictions
- Replace DEI keywords with complaint-type keywords (housing, employment, civil rights)
- Integrate with `LegalAuthoritySearchHook` in mediator

---

## 2. Evidence Gathering & Document Processing

### 2.1 `download_manager.py` - Core Download Infrastructure

**Purpose:** Download, deduplicate, and manage document artifacts with metadata tracking.

**Key Classes/Functions:**
- `DownloadManager` - Main download orchestrator
  - `download_pdf(url, source)` - Download with deduplication
  - `compute_hash(url)` - URL-based hashing for dedupe
  - `is_downloaded(url)` - Check if already downloaded
  - Manifest system for tracking downloads

**Features:**
- MD5-based URL deduplication
- Automatic content-type validation
- Playwright fallback for JavaScript-rendered downloads
- Brave Search API fallback for failed downloads
- Metadata manifest (JSON) for provenance tracking

**Reuse Strategy:**
```python
from hacc_scripts.download_manager import DownloadManager

manager = DownloadManager(
    raw_dir="evidence/documents/raw",
    metadata_file="evidence/documents/manifest.json"
)

# Download complaint evidence
filepath = manager.download_pdf(
    url="https://example.gov/complaint_form.pdf",
    source="complaint_intake"
)

# Check if already downloaded
if manager.is_downloaded(url):
    print(f"Already have this: {url}")
```

**Integration with Complaint Generator:**
- Replace raw directory path with `mediator` evidence storage
- Integrate with IPFS storage via `EvidenceStorageHook`
- Add DuckDB metadata tracking alongside JSON manifest

---

### 2.2 `parse_pdfs.py` - PDF Text Extraction

**Purpose:** Extract text from PDFs with automatic OCR fallback for scanned documents.

**Key Classes/Functions:**
- `PDFParser` - PDF processing orchestrator
  - `extract_text_pdftotext(pdf_path)` - Fast extraction for text-based PDFs
  - `extract_text_with_ocr(pdf_path)` - OCR for scanned PDFs
  - `parse_pdf(pdf_path)` - Unified interface with auto-fallback
  - Metadata manifest tracking

**Dependencies:**
- `pdftotext` (poppler-utils) - Fast text extraction
- `ocrmypdf` - OCR processing
- `tesseract-ocr` - OCR engine

**Reuse Strategy:**
```python
from hacc_scripts.parse_pdfs import PDFParser

parser = PDFParser(
    raw_dir="evidence/documents/raw",
    parsed_dir="evidence/documents/parsed"
)

# Parse complaint document with auto-OCR fallback
text = parser.parse_pdf("evidence/documents/raw/complaint_001.pdf")

# Batch process all downloaded evidence
parser.batch_parse()
```

**Integration Points:**
- Hook into `EvidenceAnalysisHook` for automatic processing
- Store parsed text in DuckDB evidence table
- Extract complaint-relevant keywords during parsing

---

### 2.3 `extract_*.py` Files - Link & Document Extraction

Multiple scripts handle extraction from different sources:

**`extract_external_documents_from_quantum_pages.py`**
- Extract document links from crawled HTML pages
- Score and rank candidate URLs by relevance
- Build download queues

**`extract_quantum_residential_documents.py`**
- Extract housing-specific documents
- Map evidence sources to download queues

**Reuse Strategy:**
- Adapt for complaint evidence discovery from agency websites
- Extract links to complaint forms, procedures, policies
- Build priority queues for evidence download

---

### 2.4 `batch_ocr_parallel.py` - Parallel OCR Processing

**Purpose:** High-throughput OCR processing for bulk scanned documents.

**Features:**
- Parallel processing with multiprocessing
- Progress tracking
- Error handling and retry logic

**Reuse for Complaint Generator:**
- Process bulk complaint submissions (scanned forms)
- Handle historical complaint archives
- Parallel processing of evidence batches

---

## 3. Legal Citation & Knowledge Graph Research

### 3.1 `deep_analysis.py` - Legal Provision Extraction

**Purpose:** Extract specific legal provisions with contextual information from statutes and regulations.

**Key Features:**
- Regex-based term extraction (currently DEI-focused)
- Statutory section identification
- Context preservation (surrounding text)
- Multi-term matching

**Current Keywords (DEI-focused):**
```python
DEI_TERMS = [
    r"\b(diversity|diverse)\b",
    r"\b(equity|equitable)\b",
    r"\b(fair housing)\b",
    r"\b(discrimination)\b",
    # ... many more
]
```

**Adaptation for Complaint Generator:**
```python
# Replace DEI terms with complaint-relevant legal terms
COMPLAINT_LEGAL_TERMS = [
    r"\b(fair housing)\b",
    r"\b(discrimination)\b",
    r"\b(retaliation)\b",
    r"\b(reasonable accommodation)\b",
    r"\b(familial status)\b",
    r"\b(protected class)\b",
    r"\b(disparate (impact|treatment))\b",
    r"\b(harassment)\b",
    r"\b(hostile environment)\b",
    r"\b(damages)\b",
    r"\b(injunctive relief)\b",
    r"\b(civil rights)\b",
    r"\b(Section 8)\b",
    r"\b(42 U\.S\.C\.)\\b",  # Federal housing law citations
]

class ComplaintProvisionExtractor(ProvisionExtractor):
    def __init__(self):
        super().__init__()
        self.terms = COMPLAINT_LEGAL_TERMS
    
    def extract_housing_statutes(self, filepath):
        # Extract Fair Housing Act provisions, state housing laws, etc.
        pass
```

**Use Cases:**
- Extract relevant statutes for complaint type
- Identify applicable legal requirements
- Build legal authority citations

---

### 3.2 `index_and_tag.py` - Document Indexing & Keyword Tagging

**Purpose:** Build searchable index of documents with keyword-based tagging and risk scoring.

**Key Classes/Functions:**
- `DocumentIndexer` - Main indexing class
  - `index_document(text_path, metadata)` - Index single document
  - `batch_index(parsed_dir)` - Index all documents in directory
  - `_extract_keywords(text, keyword_list)` - Keyword extraction
  - `_tag_applicability(text)` - Categorize by application area
  - `_calculate_risk_score(dei, proxy, binding)` - Risk assessment

**Keyword Categories (Currently DEI-focused):**
- DEI Keywords - Primary terms
- Proxy Keywords - Related/euphemistic terms
- Binding Keywords - Indicates enforceable policy
- Applicability Keywords - Domain tagging (hiring, procurement, housing, etc.)

**Adaptation for Complaint Generator:**
```python
COMPLAINT_KEYWORDS = [
    'discrimination', 'harassment', 'retaliation', 'fair housing',
    'protected class', 'disability', 'familial status', 'reasonable accommodation',
    'hostile environment', 'disparate impact', 'disparate treatment'
]

EVIDENCE_KEYWORDS = [
    'witness', 'testimony', 'document', 'record', 'proof', 'exhibit',
    'correspondence', 'notice', 'communication', 'photograph'
]

LEGAL_AUTHORITY_KEYWORDS = [
    'statute', 'regulation', 'ordinance', 'code', 'law', 'act',
    'U.S.C.', 'C.F.R.', 'O.R.S.', 'precedent', 'case law', 'holding'
]

APPLICABILITY_KEYWORDS = {
    'housing': ['housing', 'lease', 'tenant', 'landlord', 'rental', 'eviction'],
    'employment': ['employment', 'workplace', 'hire', 'fire', 'promote', 'demote'],
    'public accommodation': ['public accommodation', 'service', 'access', 'facility'],
    'lending': ['lending', 'mortgage', 'credit', 'loan', 'financing'],
    'education': ['education', 'school', 'university', 'admission', 'enrollment']
}

class ComplaintDocumentIndexer(DocumentIndexer):
    def __init__(self):
        self.complaint_keywords = COMPLAINT_KEYWORDS
        self.evidence_keywords = EVIDENCE_KEYWORDS
        self.legal_keywords = LEGAL_AUTHORITY_KEYWORDS
        self.applicability_keywords = APPLICABILITY_KEYWORDS
    
    def calculate_relevance_score(self, complaint_count, evidence_count, legal_count):
        """Score document relevance to complaint (0-3)."""
        if complaint_count > 0 and legal_count > 0:
            return 3  # Highly relevant
        elif complaint_count > 0 or evidence_count > 0:
            return 2  # Relevant
        elif legal_count > 0:
            return 1  # Potentially relevant
        return 0
```

**Integration Strategy:**
- Index all collected evidence documents
- Tag by complaint type and legal domain
- Calculate relevance scores for prioritization
- Store in DuckDB evidence table

---

### 3.3 `report_generator.py` - Findings & Summary Reports

**Purpose:** Generate executive summaries and detailed reports from indexed documents.

**Key Classes/Functions:**
- `ReportGenerator` - Report generation class
  - `generate_one_page_summary()` - Executive summary
  - `_summarize_high_risk()` - High-priority items
  - `_summarize_medium_risk()` - Medium-priority items
  - `_summarize_applicability()` - Domain breakdown

**Output Formats:**
- Plain text executive summaries
- JSON detailed findings
- CSV data exports

**Adaptation for Complaint Generator:**
```python
class ComplaintReportGenerator(ReportGenerator):
    def generate_complaint_summary(self, complaint_data, evidence_index):
        """Generate complaint summary with evidence and legal analysis."""
        summary = f"""
================================================================================
COMPLAINT SUMMARY - {complaint_data['complaint_type']}
Generated: {datetime.now().isoformat()}
================================================================================

COMPLAINANT INFORMATION
- Name: {complaint_data['complainant_name']}
- Contact: {complaint_data['contact_info']}
- Complaint Date: {complaint_data['complaint_date']}

ALLEGED VIOLATIONS
{self._format_violations(complaint_data['violations'])}

EVIDENCE COLLECTED ({len(evidence_index)} items)
- High Relevance: {self._count_by_score(evidence_index, 3)}
- Medium Relevance: {self._count_by_score(evidence_index, 2)}

LEGAL AUTHORITIES IDENTIFIED
{self._format_legal_authorities(evidence_index)}

RECOMMENDED NEXT STEPS
{self._generate_recommendations(complaint_data, evidence_index)}

================================================================================
"""
        return summary
```

**Use Cases:**
- Generate complaint intake summaries
- Create evidence collection reports
- Produce legal research summaries
- Generate complainant communications

---

### 3.4 Knowledge Graph Scripts

**`kg_seed_pack.py` - Entity Extraction & Query Generation**
- Extract entities from documents (agencies, statutes, violation types)
- Generate seed queries for follow-up research
- Build entity co-occurrence graphs

**`kg_violation_seed_queries.py` - Risk-Based Entity Pooling**
- Pool entities by risk scores
- Identify high-risk patterns
- Generate targeted search queries

**`kg_followup_search.py` - Local Corpus Mining**
- Analyze entity co-occurrence in local corpus
- Compute entity centrality/importance
- Discover entity relationships

**Reuse Strategy for Complaint Generator:**
- Build complaint entity graphs (complainant, respondent, witnesses, locations)
- Identify patterns in similar complaints
- Generate follow-up investigation queries
- Track legal precedent relationships

---

## 4. Supporting Utilities

### 4.1 `download_retry_search_fallback.py` - Resilient Downloads

**Purpose:** Retry failed downloads with multiple fallback strategies.

**Features:**
- Exponential backoff retry logic
- Brave Search fallback for alternate sources
- Error logging and recovery

### 4.2 `playwright_redownload.py` - JavaScript-Heavy Sites

**Purpose:** Use Playwright browser automation for sites requiring JavaScript.

**Use Cases:**
- Download complaint forms from interactive government sites
- Handle authentication-protected resources
- Navigate multi-page evidence collection flows

### 4.3 `fallback_pdftotext_extract.py` - Extraction Fallbacks

**Purpose:** Multiple fallback strategies for PDF text extraction.

**Features:**
- Try multiple extraction libraries
- Handle corrupted PDFs
- Extract metadata when text fails

---

## 5. Integration Architecture

### 5.1 Recommended Integration with Complaint Generator Mediator

```
complaint-generator/
├── hacc_integration/              # HACC scripts integration layer
│   ├── __init__.py
│   ├── search.py                 # Wraps collect_brave.py, seeded_commoncrawl_discovery.py
│   ├── download.py               # Wraps download_manager.py
│   ├── parser.py                 # Wraps parse_pdfs.py
│   ├── indexer.py                # Wraps index_and_tag.py
│   ├── analyzer.py               # Wraps deep_analysis.py
│   └── reporter.py               # Wraps report_generator.py
│
├── mediator/
│   ├── evidence_hooks.py         # Connect to hacc_integration.download/parser
│   ├── legal_authority_hooks.py  # Connect to hacc_integration.search/analyzer
│   └── web_evidence_hooks.py     # Connect to hacc_integration.search
│
└── config/
    └── hacc_keywords.json        # Complaint-specific keyword configurations
```

### 5.2 Integration Workflow

```
1. Complaint Intake
   └─→ hacc_integration.search.search_evidence(complaint_keywords)
       └─→ collect_brave.BraveCollector.batch_search()
       └─→ seeded_commoncrawl.search_archives()

2. Evidence Download
   └─→ hacc_integration.download.download_evidence(urls)
       └─→ download_manager.DownloadManager.download_pdf()
       └─→ Stores in mediator evidence storage (IPFS + DuckDB)

3. Document Parsing
   └─→ hacc_integration.parser.parse_documents()
       └─→ parse_pdfs.PDFParser.batch_parse()
       └─→ Extracts text, stores in DuckDB evidence table

4. Indexing & Tagging
   └─→ hacc_integration.indexer.index_evidence()
       └─→ index_and_tag.DocumentIndexer.batch_index()
       └─→ Tags with complaint keywords, calculates relevance

5. Legal Analysis
   └─→ hacc_integration.analyzer.extract_legal_provisions()
       └─→ deep_analysis.ProvisionExtractor.analyze_documents()
       └─→ Extracts statutes, regulations, case citations

6. Report Generation
   └─→ hacc_integration.reporter.generate_complaint_report()
       └─→ report_generator.ReportGenerator.generate_summary()
       └─→ Produces complaint summary with evidence and legal analysis
```

---

## 6. Implementation Roadmap

### Phase 1: Core Infrastructure (Week 1-2)
- [ ] Integrate `download_manager.py` with mediator evidence storage
- [ ] Integrate `parse_pdfs.py` with evidence analysis hooks
- [ ] Set up IPFS storage for downloaded evidence
- [ ] Create DuckDB schema extensions for HACC metadata

### Phase 2: Search & Discovery (Week 3-4)
- [ ] Integrate `collect_brave.py` with web evidence hooks
- [ ] Integrate `seeded_commoncrawl_discovery.py` for archive search
- [ ] Adapt search queries for complaint types
- [ ] Build complaint-specific keyword sets

### Phase 3: Indexing & Analysis (Week 5-6)
- [ ] Integrate `index_and_tag.py` with complaint keywords
- [ ] Integrate `deep_analysis.py` for legal provision extraction
- [ ] Build complaint relevance scoring system
- [ ] Create legal authority extraction pipeline

### Phase 4: Reporting & Testing (Week 7-8)
- [ ] Integrate `report_generator.py` for complaint summaries
- [ ] Build knowledge graph entity extraction
- [ ] End-to-end testing with sample complaints
- [ ] Documentation and deployment

---

## 7. Dependencies & Requirements

### Python Packages
```
requests>=2.31.0
beautifulsoup4>=4.12.0
playwright>=1.40.0
cdx-toolkit>=0.9.0  # Optional, for advanced CommonCrawl queries
```

### System Dependencies
```bash
# PDF processing
apt-get install poppler-utils tesseract-ocr ocrmypdf

# Playwright browsers
playwright install chromium
```

### API Keys Required
- `BRAVE_API_KEY` - For Brave Search API access
- Consider rate limits and quotas for production use

---

## 8. Testing Strategy

### Unit Tests
- Test each HACC script wrapper independently
- Mock external API calls (Brave, CommonCrawl)
- Validate PDF parsing with sample documents

### Integration Tests
- End-to-end complaint intake workflow
- Evidence collection and parsing pipeline
- Legal analysis and report generation

### Test Data
- Sample complaint documents (anonymized)
- Sample PDF evidence (various formats)
- Sample legal documents (statutes, regulations)

---

## 9. Security Considerations

### HACC Scripts Review
- ✅ No hardcoded credentials found
- ✅ Environment variables for API keys
- ✅ Input validation on file paths
- ⚠️ Review URL parsing for injection risks
- ⚠️ Validate PDF content before processing
- ⚠️ Sanitize extracted text before storage

### Integration Security
- Store downloaded evidence in isolated directory
- Validate all URLs before downloading
- Scan uploaded PDFs for malware
- Sanitize extracted text before LLM processing
- Implement rate limiting on search APIs
- Log all evidence access for audit trail

---

## 10. Performance Considerations

### Scalability
- **Parallel Processing:** Use `batch_ocr_parallel.py` patterns for bulk operations
- **Caching:** Leverage `download_manager` deduplication
- **Indexing:** Build indexes on DuckDB tables for fast queries
- **Rate Limiting:** Respect API rate limits (Brave: 1 req/sec)

### Storage
- **IPFS:** Store large PDFs in IPFS, metadata in DuckDB
- **Parsed Text:** Store in DuckDB for fast full-text search
- **Manifest Files:** Keep JSON manifests for human readability + debugging

---

## 11. Maintenance & Updates

### Keeping HACC Scripts Updated
```bash
# Option 1: Git submodule
cd complaint-generator
git submodule add https://github.com/endomorphosis/HACC.git hacc_source
git submodule update --remote

# Option 2: Periodic sync
cd /tmp
git clone https://github.com/endomorphosis/HACC.git
rsync -av HACC/research_data/scripts/ complaint-generator/hacc_integration/scripts/
```

### Customization Strategy
- Keep original HACC scripts unmodified in `hacc_integration/scripts/`
- Create wrapper classes in `hacc_integration/*.py` for customization
- Override keyword sets and configurations via config files
- Contribute improvements back to HACC repository when applicable

---

## 12. Conclusion

The HACC repository provides a mature, well-tested foundation for legal research and document analysis. The scripts are modular, well-documented, and directly applicable to complaint-generator needs with minimal adaptation.

**Most Critical Scripts for Immediate Reuse:**
1. `download_manager.py` - Evidence collection infrastructure
2. `parse_pdfs.py` - Document text extraction
3. `collect_brave.py` - Web search for evidence
4. `index_and_tag.py` - Document indexing and tagging
5. `deep_analysis.py` - Legal provision extraction
6. `report_generator.py` - Summary report generation

**Next Steps:**
1. Review this analysis with the team
2. Prioritize integration based on immediate needs
3. Create integration wrappers in `hacc_integration/` directory
4. Adapt keyword sets for complaint-specific use cases
5. Begin with Phase 1 implementation (core infrastructure)

---

## Appendices

### Appendix A: Full Script List

All 34 Python files in `/tmp/HACC/research_data/scripts`:
```
audit_policy_kg_and_summaries.py
batch_ocr_parallel.py
collect_brave.py
deep_analysis.py
download_hacc_documents.py
download_manager.py
download_oregon_documents.py
download_retry_search_fallback.py
download_third_party_queue.py
enhanced_research.py
export_problematic_downloads.py
extract_clackamas_links.py
extract_external_documents_from_quantum_pages.py
extract_oregon_links.py
extract_p1p2_links.py
extract_quantum_residential_documents.py
extract_third_party_candidates.py
fallback_pdftotext_extract.py
filter_and_download_p1p2.py
filter_third_party_download_queue.py
generate_third_party_download_queue.py
index_and_tag.py
ingest_third_party_into_corpus.py
kg_followup_search.py
kg_prioritize_queues.py
kg_seed_pack.py
kg_violation_seed_queries.py
oregon_dei_research.py
parse_pdfs.py
playwright_redownload.py
report_generator.py
run_collection.py
seed_from_quantum_html.py
seeded_commoncrawl_discovery.py
topic_triage_risk_gt0.py
```

### Appendix B: Sample Integration Code

See `/examples/hacc_integration_example.py` for complete working example.

### Appendix C: Keyword Mapping Reference

See `/config/hacc_keywords.json` for complaint-specific keyword configurations.

---

**Document Version:** 1.0  
**Last Updated:** 2026-02-08  
**Author:** GitHub Copilot Agent  
**Status:** Draft for Review
