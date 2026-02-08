# HACC Scripts - Quick Reference Guide

## Top 7 Scripts for Complaint Generator

### 1. **collect_brave.py** - Web Search
```python
from collect_brave import BraveCollector

collector = BraveCollector(api_key="YOUR_KEY")
results = collector.search('site:gov "fair housing" filetype:pdf', count=20)
collector.save_results()
```
**Use for:** Finding evidence, legal documents, government policies

---

### 2. **download_manager.py** - Download & Dedupe
```python
from download_manager import DownloadManager

manager = DownloadManager(raw_dir="evidence/raw")
filepath = manager.download_pdf(
    url="https://example.gov/policy.pdf",
    source="complaint_evidence"
)
```
**Use for:** Downloading evidence, preventing duplicates, tracking provenance

---

### 3. **parse_pdfs.py** - PDF Text Extraction
```python
from parse_pdfs import PDFParser

parser = PDFParser(raw_dir="evidence/raw", parsed_dir="evidence/parsed")
text = parser.parse_pdf("evidence/raw/document.pdf")  # Auto OCR fallback
parser.batch_parse()  # Process all PDFs
```
**Use for:** Extracting text from scanned complaints, evidence documents

---

### 4. **index_and_tag.py** - Document Indexing
```python
from index_and_tag import DocumentIndexer

indexer = DocumentIndexer(parsed_dir="evidence/parsed")
indexer.DEI_KEYWORDS = ['discrimination', 'harassment', 'retaliation']  # Customize
indexer.batch_index()
indexer.save_index("evidence/index.json")
```
**Use for:** Tagging documents, calculating relevance scores, building search index

---

### 5. **deep_analysis.py** - Legal Provision Extraction
```python
from deep_analysis import ProvisionExtractor

extractor = ProvisionExtractor()
provisions = extractor.extract_ors_provisions("statute.html", chapter="456")
# Returns: [{'statute': '456.055', 'text': '...', 'found_terms': [...]}]
```
**Use for:** Extracting relevant statutes, identifying legal requirements

---

### 6. **report_generator.py** - Summary Reports
```python
from report_generator import ReportGenerator

generator = ReportGenerator(output_dir="reports/")
generator.load_index("evidence/index.json")
summary = generator.generate_one_page_summary()
print(summary)
```
**Use for:** Creating complaint summaries, evidence reports

---

### 7. **seeded_commoncrawl_discovery.py** - Archive Search
```python
from seeded_commoncrawl_discovery import search_commoncrawl

results = search_commoncrawl(
    query='site:oregon.gov "housing authority"',
    keywords=['policy', 'regulation', 'procedure'],
    max_results=50
)
```
**Use for:** Finding historical policies, archived documents

---

## Integration Pattern

```python
# 1. Search for evidence
from collect_brave import BraveCollector
collector = BraveCollector()
results = collector.search('site:gov "fair housing complaint"')

# 2. Download evidence
from download_manager import DownloadManager
manager = DownloadManager()
for result in results:
    manager.download_pdf(result['url'], source='brave_search')

# 3. Parse documents
from parse_pdfs import PDFParser
parser = PDFParser()
parser.batch_parse()

# 4. Index and tag
from index_and_tag import DocumentIndexer
indexer = DocumentIndexer()
indexer.batch_index()

# 5. Generate report
from report_generator import ReportGenerator
generator = ReportGenerator()
generator.load_index("evidence/index.json")
print(generator.generate_one_page_summary())
```

---

## Keyword Customization

### Replace DEI Keywords with Complaint Keywords

```python
# Original (DEI-focused)
DEI_KEYWORDS = ['diversity', 'equity', 'inclusion', ...]

# Complaint Generator (Housing/Civil Rights)
COMPLAINT_KEYWORDS = [
    'discrimination', 'harassment', 'retaliation',
    'fair housing', 'reasonable accommodation',
    'protected class', 'familial status', 'disability',
    'disparate impact', 'hostile environment',
    'civil rights', 'Section 8', 'HUD'
]

# Apply to indexer
indexer.DEI_KEYWORDS = COMPLAINT_KEYWORDS
```

---

## Quick Start

```bash
# 1. Install dependencies
pip install requests beautifulsoup4 playwright
sudo apt-get install poppler-utils tesseract-ocr ocrmypdf
playwright install chromium

# 2. Set API key
export BRAVE_API_KEY="your_key_here"

# 3. Run search and download
python collect_brave.py
python download_manager.py

# 4. Parse and index
python parse_pdfs.py
python index_and_tag.py

# 5. Generate report
python report_generator.py
```

---

## Common Issues & Solutions

### Issue: PDF parsing fails
**Solution:** Use OCR fallback in `parse_pdfs.py`
```python
parser.extract_text_with_ocr(pdf_path)
```

### Issue: Download blocked by JavaScript
**Solution:** Use playwright fallback in `download_manager.py`
```python
manager.download_pdf(url, source='complaint', use_playwright=True)
```

### Issue: No results from Brave Search
**Solution:** Check API key, try simpler queries
```python
collector.search('site:gov housing')  # Simpler query
```

---

## File Structure

```
evidence/
├── documents/
│   ├── raw/                 # Downloaded PDFs
│   ├── parsed/              # Extracted text
│   └── manifest.json        # Download metadata
├── search_results/
│   └── brave_results_*.json # Search results
├── index.json               # Document index
└── reports/
    └── summary_*.txt        # Generated reports
```

---

## Next Steps

1. Review [Full Analysis](HACC_SCRIPTS_REUSE_ANALYSIS.md)
2. Check [Integration Examples](../examples/hacc_integration_example.py)
3. See [Implementation Roadmap](HACC_SCRIPTS_REUSE_ANALYSIS.md#6-implementation-roadmap)
