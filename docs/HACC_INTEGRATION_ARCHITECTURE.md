# HACC Integration Architecture

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                     COMPLAINT GENERATOR SYSTEM                       │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE LAYER                          │
├─────────────────────────────────────────────────────────────────────┤
│  • Web UI (Complaint Intake Forms)                                  │
│  • API Endpoints (REST/GraphQL)                                     │
│  • CLI Tools                                                         │
└─────────────────┬───────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        MEDIATOR LAYER                                │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐       │
│  │  Evidence Management Hooks                               │       │
│  │  • EvidenceStorageHook (IPFS)                           │       │
│  │  • EvidenceStateHook (DuckDB)                           │       │
│  │  • EvidenceAnalysisHook                                 │       │
│  └─────────────────────────────────────────────────────────┘       │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │  Legal Authority Hooks                                   │       │
│  │  • LegalAuthoritySearchHook                             │       │
│  │  • LegalAuthorityStorageHook (DuckDB)                   │       │
│  │  • LegalAuthorityAnalysisHook                           │       │
│  └─────────────────────────────────────────────────────────┘       │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │  Web Evidence Hooks                                      │       │
│  │  • WebEvidenceSearchHook (Brave + CommonCrawl)          │       │
│  │  • WebEvidenceIntegrationHook                           │       │
│  └─────────────────────────────────────────────────────────┘       │
└───────────────────────┬─────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  HACC INTEGRATION LAYER                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │  hacc_integration/search.py                              │       │
│  │  ┌─────────────────────┐  ┌─────────────────────────┐   │       │
│  │  │ BraveSearchWrapper   │  │ CommonCrawlWrapper      │   │       │
│  │  │                      │  │                         │   │       │
│  │  │ • search_evidence()  │  │ • search_archives()     │   │       │
│  │  │ • batch_search()     │  │ • find_historical()     │   │       │
│  │  └──────────┬───────────┘  └──────────┬──────────────┘   │       │
│  │             │                          │                   │       │
│  │             ▼                          ▼                   │       │
│  │      collect_brave.py    seeded_commoncrawl_discovery.py  │       │
│  └─────────────────────────────────────────────────────────┘       │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │  hacc_integration/download.py                            │       │
│  │  ┌───────────────────────────────────────────────────┐   │       │
│  │  │ EvidenceDownloadManager                            │   │       │
│  │  │                                                    │   │       │
│  │  │ • download_with_dedupe()                          │   │       │
│  │  │ • bulk_download()                                 │   │       │
│  │  │ • retry_with_fallback()                           │   │       │
│  │  └──────────┬─────────────────────────────────────────   │       │
│  │             │                                             │       │
│  │             ▼                                             │       │
│  │      download_manager.py                                 │       │
│  │      download_retry_search_fallback.py                   │       │
│  │      playwright_redownload.py                            │       │
│  └─────────────────────────────────────────────────────────┘       │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │  hacc_integration/parser.py                              │       │
│  │  ┌───────────────────────────────────────────────────┐   │       │
│  │  │ DocumentParser                                     │   │       │
│  │  │                                                    │   │       │
│  │  │ • parse_pdf()                                     │   │       │
│  │  │ • parse_with_ocr()                                │   │       │
│  │  │ • batch_parse()                                   │   │       │
│  │  └──────────┬─────────────────────────────────────────   │       │
│  │             │                                             │       │
│  │             ▼                                             │       │
│  │      parse_pdfs.py                                       │       │
│  │      batch_ocr_parallel.py                               │       │
│  │      fallback_pdftotext_extract.py                       │       │
│  └─────────────────────────────────────────────────────────┘       │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │  hacc_integration/indexer.py                             │       │
│  │  ┌───────────────────────────────────────────────────┐   │       │
│  │  │ ComplaintDocumentIndexer                          │   │       │
│  │  │                                                    │   │       │
│  │  │ • index_with_keywords()                           │   │       │
│  │  │ • calculate_relevance()                           │   │       │
│  │  │ • tag_by_type()                                   │   │       │
│  │  └──────────┬─────────────────────────────────────────   │       │
│  │             │                                             │       │
│  │             ▼                                             │       │
│  │      index_and_tag.py                                    │       │
│  └─────────────────────────────────────────────────────────┘       │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │  hacc_integration/analyzer.py                            │       │
│  │  ┌───────────────────────────────────────────────────┐   │       │
│  │  │ LegalProvisionExtractor                           │   │       │
│  │  │                                                    │   │       │
│  │  │ • extract_statutes()                              │   │       │
│  │  │ • identify_citations()                            │   │       │
│  │  │ • find_legal_requirements()                       │   │       │
│  │  └──────────┬─────────────────────────────────────────   │       │
│  │             │                                             │       │
│  │             ▼                                             │       │
│  │      deep_analysis.py                                    │       │
│  │      kg_seed_pack.py                                     │       │
│  │      kg_violation_seed_queries.py                        │       │
│  └─────────────────────────────────────────────────────────┘       │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │  hacc_integration/reporter.py                            │       │
│  │  ┌───────────────────────────────────────────────────┐   │       │
│  │  │ ComplaintReportGenerator                          │   │       │
│  │  │                                                    │   │       │
│  │  │ • generate_summary()                              │   │       │
│  │  │ • create_evidence_report()                        │   │       │
│  │  │ • format_legal_analysis()                         │   │       │
│  │  └──────────┬─────────────────────────────────────────   │       │
│  │             │                                             │       │
│  │             ▼                                             │       │
│  │      report_generator.py                                 │       │
│  └─────────────────────────────────────────────────────────┘       │
└───────────────────────┬─────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      STORAGE LAYER                                   │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐   │
│  │    IPFS      │  │   DuckDB     │  │  File System           │   │
│  │              │  │              │  │                        │   │
│  │ • Evidence   │  │ • Metadata   │  │ • Parsed Text          │   │
│  │   Documents  │  │ • Index      │  │ • Temp Files           │   │
│  │ • PDFs       │  │ • Citations  │  │ • Manifests            │   │
│  └──────────────┘  └──────────────┘  └────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                    EXTERNAL SERVICES                                 │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐   │
│  │ Brave Search │  │ CommonCrawl  │  │  Government Websites   │   │
│  │     API      │  │    Index     │  │  (.gov, .edu)          │   │
│  └──────────────┘  └──────────────┘  └────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow Diagram

```
COMPLAINT INTAKE WORKFLOW
═════════════════════════

┌─────────────┐
│   User      │
│  Submits    │
│ Complaint   │
└──────┬──────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│  1. KEYWORD EXTRACTION                       │
│  Extract: complaint type, keywords, entities │
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│  2. EVIDENCE SEARCH                          │
│  ┌────────────────┐    ┌──────────────────┐ │
│  │ Brave Search   │    │ CommonCrawl      │ │
│  │ collect_brave  │───▶│ seeded_cc_disc   │ │
│  └────────┬───────┘    └──────┬───────────┘ │
└───────────┼───────────────────┼──────────────┘
            │                   │
            └─────────┬─────────┘
                      ▼
┌──────────────────────────────────────────────┐
│  3. DOCUMENT DOWNLOAD                        │
│  ┌────────────────────────────────────────┐  │
│  │ Download Manager                        │  │
│  │ • Dedupe by URL hash                   │  │
│  │ • Retry with fallbacks                 │  │
│  │ • Store in IPFS                        │  │
│  └────────┬───────────────────────────────┘  │
└───────────┼──────────────────────────────────┘
            ▼
┌──────────────────────────────────────────────┐
│  4. DOCUMENT PARSING                         │
│  ┌────────────────────────────────────────┐  │
│  │ PDF Parser                             │  │
│  │ • Extract text (pdftotext)             │  │
│  │ • OCR fallback (ocrmypdf)              │  │
│  │ • Store parsed text in DuckDB          │  │
│  └────────┬───────────────────────────────┘  │
└───────────┼──────────────────────────────────┘
            ▼
┌──────────────────────────────────────────────┐
│  5. INDEXING & TAGGING                       │
│  ┌────────────────────────────────────────┐  │
│  │ Document Indexer                       │  │
│  │ • Extract complaint keywords           │  │
│  │ • Tag evidence type                    │  │
│  │ • Calculate relevance score            │  │
│  │ • Store in DuckDB index                │  │
│  └────────┬───────────────────────────────┘  │
└───────────┼──────────────────────────────────┘
            ▼
┌──────────────────────────────────────────────┐
│  6. LEGAL ANALYSIS                           │
│  ┌────────────────────────────────────────┐  │
│  │ Provision Extractor                    │  │
│  │ • Extract statutes                     │  │
│  │ • Find legal citations                 │  │
│  │ • Identify requirements                │  │
│  │ • Store in legal_authorities table     │  │
│  └────────┬───────────────────────────────┘  │
└───────────┼──────────────────────────────────┘
            ▼
┌──────────────────────────────────────────────┐
│  7. REPORT GENERATION                        │
│  ┌────────────────────────────────────────┐  │
│  │ Report Generator                       │  │
│  │ • Complaint summary                    │  │
│  │ • Evidence list (scored)               │  │
│  │ • Legal authorities found              │  │
│  │ • Recommended next steps               │  │
│  └────────┬───────────────────────────────┘  │
└───────────┼──────────────────────────────────┘
            ▼
┌──────────────────┐
│   Output to      │
│   User/Attorney  │
└──────────────────┘
```

## Component Interaction Matrix

| Component | Uses | Produces | Stores In |
|-----------|------|----------|-----------|
| **collect_brave.py** | Brave API | Search results JSON | File system |
| **seeded_commoncrawl_discovery.py** | CommonCrawl API | URL lists, archived pages | File system |
| **download_manager.py** | HTTP requests, Playwright | PDFs, metadata | IPFS + manifest |
| **parse_pdfs.py** | pdftotext, ocrmypdf | Parsed text | DuckDB + filesystem |
| **index_and_tag.py** | Parsed text | Document index, tags | DuckDB + JSON |
| **deep_analysis.py** | HTML, parsed text | Legal provisions | JSON + DuckDB |
| **report_generator.py** | Document index | Reports, summaries | File system |

## Configuration Flow

```
┌───────────────────────────────────────┐
│  config/hacc_keywords.json            │
│  {                                    │
│    "complaint_types": {               │
│      "housing": [...],                │
│      "employment": [...],             │
│      "civil_rights": [...]            │
│    },                                 │
│    "evidence_keywords": [...],        │
│    "legal_keywords": [...]            │
│  }                                    │
└────────────┬──────────────────────────┘
             │
             ▼
┌───────────────────────────────────────┐
│  hacc_integration/__init__.py         │
│  Load and apply configurations        │
└────────────┬──────────────────────────┘
             │
             ├──────┬──────┬──────┬─────┐
             ▼      ▼      ▼      ▼     ▼
          search download parse index analyze
```

## Deployment Architecture

```
┌─────────────────────────────────────────────────────┐
│                 PRODUCTION DEPLOYMENT                │
└─────────────────────────────────────────────────────┘

┌──────────────────┐         ┌──────────────────┐
│   Web Server     │◀───────▶│   Mediator       │
│   (Flask/FastAPI)│         │   (Core Logic)   │
└──────────────────┘         └────────┬─────────┘
                                      │
                                      ▼
                             ┌──────────────────┐
                             │  HACC Integration │
                             │  Layer            │
                             └────────┬─────────┘
                                      │
        ┌─────────────┬──────────────┼───────────────┬──────────────┐
        ▼             ▼              ▼               ▼              ▼
   ┌────────┐   ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │ Worker │   │ Worker  │   │ Worker   │   │ Worker   │   │ Worker   │
   │ Search │   │Download │   │  Parse   │   │  Index   │   │ Analyze  │
   └────────┘   └─────────┘   └──────────┘   └──────────┘   └──────────┘
        │             │              │               │              │
        └─────────────┴──────────────┴───────────────┴──────────────┘
                                      │
                                      ▼
                             ┌──────────────────┐
                             │  Storage Cluster  │
                             │  • IPFS          │
                             │  • DuckDB        │
                             │  • Redis (cache) │
                             └──────────────────┘
```

## Security Architecture

```
┌─────────────────────────────────────────────────────┐
│                 SECURITY LAYERS                      │
└─────────────────────────────────────────────────────┘

INPUT VALIDATION
├─ URL sanitization (download_manager)
├─ File type validation (parse_pdfs)
└─ Query parameter escaping (search)

CONTENT SECURITY
├─ PDF malware scanning (before parsing)
├─ Text sanitization (before LLM)
└─ Extracted text validation

ACCESS CONTROL
├─ API key management (environment variables)
├─ IPFS access control
└─ DuckDB query permissions

AUDIT TRAIL
├─ All evidence downloads logged
├─ Search queries tracked
└─ Document access monitored
```

## Scaling Strategy

```
HORIZONTAL SCALING

┌────────────────────────────────────────┐
│  Load Balancer                         │
└────────┬───────────────────────────────┘
         │
         ├─────────┬─────────┬─────────┐
         ▼         ▼         ▼         ▼
    ┌─────────┐ ┌─────────┐ ┌─────────┐
    │Instance1│ │Instance2│ │Instance3│
    └────┬────┘ └────┬────┘ └────┬────┘
         │           │           │
         └───────────┴───────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │  Shared Storage       │
         │  • IPFS Cluster       │
         │  • DuckDB Replicas    │
         └───────────────────────┘

WORKER SCALING

┌────────────────────────────────────────┐
│  Task Queue (Celery/RQ)                │
└────────┬───────────────────────────────┘
         │
         ├────┬────┬────┬────┬────┐
         ▼    ▼    ▼    ▼    ▼    ▼
      Worker Pool (Auto-scaling)
      • Search workers
      • Download workers
      • Parse workers (GPU-enabled for OCR)
      • Index workers
      • Analyze workers
```

## Monitoring & Observability

```
MONITORING STACK

┌────────────────────────────────────────┐
│  Metrics Collection                    │
│  • Evidence download rate              │
│  • PDF parsing success rate            │
│  • Search API usage                    │
│  • Storage capacity                    │
└────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│  Alerting                              │
│  • API rate limits approaching         │
│  • Storage threshold exceeded          │
│  • Parse failures increasing           │
│  • DuckDB query performance            │
└────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────┐
│  Dashboards                            │
│  • Evidence pipeline health            │
│  • Search effectiveness metrics        │
│  • Document processing throughput      │
│  • Legal authority coverage            │
└────────────────────────────────────────┘
```

---

**Legend:**
- `│`, `┌`, `└`, `├`, `─`, `┐`, `┘`, `┤`, `┬`, `┴`, `┼` - Box drawing
- `▶`, `▼`, `◀`, `▲` - Flow direction
- `◀──▶` - Bidirectional communication

**Document Version:** 1.0  
**Last Updated:** 2026-02-08
