# HACC Scripts Summary - Files Analyzed

## Repository Information
- **Repository URL:** https://github.com/endomorphosis/HACC
- **Branch:** main
- **Path:** research_data/scripts
- **Analysis Date:** 2026-02-08
- **Total Python Files:** 34

## Files Analyzed in Detail

### Core Infrastructure (6 files)
1. **collect_brave.py** - Brave Search API integration for web discovery
2. **download_manager.py** - URL deduplication and document download management
3. **parse_pdfs.py** - PDF text extraction with OCR fallback
4. **index_and_tag.py** - Document indexing and keyword tagging
5. **deep_analysis.py** - Legal provision extraction from statutes
6. **report_generator.py** - Findings summary and report generation

### Web Discovery & Search (4 files)
7. **seeded_commoncrawl_discovery.py** - CommonCrawl archive search
8. **enhanced_research.py** - Automated statute and regulation research
9. **collect_brave.py** - (already listed above)
10. **kg_followup_search.py** - Local corpus entity search

### Document Extraction (6 files)
11. **extract_external_documents_from_quantum_pages.py** - Link extraction from HTML
12. **extract_quantum_residential_documents.py** - Housing document extraction
13. **extract_clackamas_links.py** - Clackamas County document extraction
14. **extract_oregon_links.py** - Oregon state document extraction
15. **extract_p1p2_links.py** - P1/P2 document extraction
16. **extract_third_party_candidates.py** - Third-party document discovery

### Download Management (5 files)
17. **download_hacc_documents.py** - HACC-specific document downloads
18. **download_oregon_documents.py** - Oregon document downloads
19. **download_third_party_queue.py** - Third-party download queue processor
20. **download_retry_search_fallback.py** - Retry with fallback strategies
21. **playwright_redownload.py** - Browser-based re-download for JavaScript sites

### Processing & Analysis (6 files)
22. **batch_ocr_parallel.py** - Parallel OCR processing
23. **fallback_pdftotext_extract.py** - Fallback PDF extraction strategies
24. **audit_policy_kg_and_summaries.py** - Policy audit and knowledge graph
25. **deep_analysis.py** - (already listed above)
26. **topic_triage_risk_gt0.py** - Risk-based topic triage
27. **oregon_dei_research.py** - Oregon DEI research automation

### Knowledge Graph (4 files)
28. **kg_seed_pack.py** - Entity extraction and seed query generation
29. **kg_violation_seed_queries.py** - Violation-based entity pooling
30. **kg_followup_search.py** - (already listed above)
31. **kg_prioritize_queues.py** - Entity-based queue prioritization

### Orchestration & Utilities (3 files)
32. **run_collection.py** - Collection orchestration
33. **generate_third_party_download_queue.py** - Queue generation
34. **filter_third_party_download_queue.py** - Queue filtering
35. **filter_and_download_p1p2.py** - P1/P2 filtering and download
36. **ingest_third_party_into_corpus.py** - Corpus ingestion
37. **export_problematic_downloads.py** - Export failed downloads
38. **seed_from_quantum_html.py** - HTML-based seeding

## Reusability Assessment

### Critical Priority (Direct Reuse)
- ✅ **collect_brave.py** - Web search for evidence
- ✅ **download_manager.py** - Document management infrastructure
- ✅ **parse_pdfs.py** - PDF text extraction
- ✅ **index_and_tag.py** - Document indexing
- ✅ **deep_analysis.py** - Legal provision extraction
- ✅ **report_generator.py** - Summary generation

### High Priority (Minor Adaptation)
- ⭐ **seeded_commoncrawl_discovery.py** - Archive search
- ⭐ **enhanced_research.py** - Legal research automation
- ⭐ **kg_violation_seed_queries.py** - Risk-based entity search
- ⭐ **batch_ocr_parallel.py** - Bulk OCR processing
- ⭐ **download_retry_search_fallback.py** - Resilient downloads

### Medium Priority (Moderate Adaptation)
- 🔸 **extract_external_documents_from_quantum_pages.py** - Link extraction
- 🔸 **kg_seed_pack.py** - Entity extraction
- 🔸 **playwright_redownload.py** - Browser automation
- 🔸 **fallback_pdftotext_extract.py** - Extraction fallbacks

### Low Priority (Domain-Specific)
- 🔹 Domain-specific extraction scripts (Oregon, Clackamas, P1/P2)
- 🔹 Third-party queue management scripts
- 🔹 Corpus ingestion utilities

## Key Dependencies Identified

### Python Packages
- `requests` - HTTP client
- `beautifulsoup4` - HTML parsing
- `playwright` - Browser automation
- `cdx_toolkit` - CommonCrawl queries (optional)

### System Dependencies
- `pdftotext` (poppler-utils) - PDF text extraction
- `ocrmypdf` - OCR processing
- `tesseract-ocr` - OCR engine
- Playwright browsers (chromium)

### API Keys
- `BRAVE_API_KEY` - Brave Search API

## Integration Strategy

### Phase 1: Core Infrastructure
1. Integrate `download_manager.py` with IPFS storage
2. Integrate `parse_pdfs.py` with evidence hooks
3. Set up DuckDB schema extensions

### Phase 2: Search & Discovery
1. Integrate `collect_brave.py` with web evidence hooks
2. Integrate `seeded_commoncrawl_discovery.py` for archives
3. Adapt keyword sets for complaint types

### Phase 3: Analysis & Reporting
1. Integrate `index_and_tag.py` with complaint keywords
2. Integrate `deep_analysis.py` for legal citations
3. Integrate `report_generator.py` for summaries

## Files Created in This Analysis

1. **docs/HACC_SCRIPTS_REUSE_ANALYSIS.md** - Comprehensive analysis (24KB)
2. **docs/HACC_QUICK_REFERENCE.md** - Quick reference guide (5KB)
3. **examples/hacc_integration_example.py** - Integration example (11KB)
4. **docs/HACC_FILES_SUMMARY.md** - This file

## Next Steps

1. Review documentation with team
2. Prioritize scripts for integration
3. Create integration wrappers in `hacc_integration/` module
4. Adapt keyword sets for complaint use cases
5. Begin Phase 1 implementation

## Resources

- Full Analysis: [HACC_SCRIPTS_REUSE_ANALYSIS.md](HACC_SCRIPTS_REUSE_ANALYSIS.md)
- Quick Reference: [HACC_QUICK_REFERENCE.md](HACC_QUICK_REFERENCE.md)
- Example Code: [../examples/hacc_integration_example.py](../examples/hacc_integration_example.py)
- HACC Repository: https://github.com/endomorphosis/HACC
