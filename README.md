# Complaint Generator
### by JusticeDAO

![Complaint Generator Overview](https://user-images.githubusercontent.com/13929820/159738867-25593733-fc54-4683-abc7-a0703ce7d4a7.svg)

## Overview

The Complaint Generator is an AI-powered legal automation system that assists users in preparing legal complaints by:

- **Three-Phase Processing** - Intake with denoising, evidence gathering, formal complaint generation (NEW)
- **Knowledge Graphs** - Extract entities and relationships from complaints (NEW)
- **Dependency Graphs** - Track claim requirements and satisfaction (NEW)
- **Neurosymbolic AI** - Combine symbolic and semantic reasoning for legal matching (NEW)
- **Classifying legal issues** from complaint text
- **Researching applicable laws** from multiple authoritative sources
- **Managing evidence** with immutable IPFS storage and DuckDB metadata
- **Discovering web evidence** automatically using search engines and archives
- **Generating targeted questions** for evidence gathering
- **Analyzing requirements** for legal motions

The system integrates [ipfs_datasets_py](https://github.com/endomorphosis/ipfs_datasets_py) for LLM routing, IPFS storage, legal research tools, and web archiving capabilities.

## Features

### 🔄 Three-Phase Complaint Processing (NEW)
Sophisticated multi-phase workflow inspired by denoising diffusion:
- **Phase 1: Intake & Denoising** - Build knowledge/dependency graphs, iteratively ask questions to fill gaps
- **Phase 2: Evidence Gathering** - Enhance graphs with evidence, track satisfaction of requirements  
- **Phase 3: Formalization** - Neurosymbolic matching against legal requirements, generate formal complaint
- **Convergence Detection** - Automatically detect when complaint is complete
- **Graph Persistence** - Save/load knowledge, dependency, and legal graphs as JSON
- **33 Tests** - Comprehensive test coverage for all three phases

See [docs/THREE_PHASE_SYSTEM.md](docs/THREE_PHASE_SYSTEM.md) and [examples/three_phase_example.py](examples/three_phase_example.py)

### 🤖 LLM Router Backend
- Multi-provider LLM routing (OpenRouter, HuggingFace, Codex, Copilot, Gemini, Claude)
- Automatic fallback between providers
- Unified interface for all LLM operations
- See [docs/LLM_ROUTER.md](docs/LLM_ROUTER.md)

### 📊 DEI Policy Analysis (NEW)
Comprehensive DEI (Diversity, Equity, Inclusion) policy analysis integrated from [HACC repository](https://github.com/endomorphosis/HACC):
- **Risk Scoring** - 0-3 algorithm detecting DEI mandates with binding language
- **Provision Extraction** - Context-aware extraction with binding vs aspirational detection
- **Report Generation** - Executive summaries, technical reports, CSV/JSON exports
- **100+ Keywords** - Direct DEI terms, proxy/euphemisms, procurement, training, etc.
- **9 Applicability Domains** - Housing, employment, procurement, training, community engagement, etc.

See [docs/HACC_INTEGRATION.md](docs/HACC_INTEGRATION.md) and [examples/hacc_dei_analysis_example.py](examples/hacc_dei_analysis_example.py)

### ⚖️ Legal Analysis Pipeline
Four-stage automated legal analysis:
1. **Classification** - Extract claim types, jurisdiction, and legal areas
2. **Statute Retrieval** - Identify applicable laws and regulations
3. **Summary Judgment** - Generate required elements per claim type
4. **Question Generation** - Create evidence-gathering questions

See [docs/LEGAL_HOOKS.md](docs/LEGAL_HOOKS.md)

### 📂 Evidence Management
- **IPFS Storage** - Immutable content-addressable evidence storage
- **DuckDB State** - Fast SQL queries for evidence metadata
- **CID References** - Track evidence by cryptographic content hash
- **Analysis Tools** - AI-powered evidence gap identification

See [docs/EVIDENCE_MANAGEMENT.md](docs/EVIDENCE_MANAGEMENT.md)

### 🔍 Legal Authority Research
Multi-source legal research with automated discovery:
- **US Code** - Federal statutes via legal scrapers
- **Federal Register** - Regulations and notices
- **RECAP Archive** - Court decisions and case law
- **Web Archives** - Common Crawl Search Engine
- **DuckDB Storage** - Organized citation database

See [docs/LEGAL_AUTHORITY_RESEARCH.md](docs/LEGAL_AUTHORITY_RESEARCH.md)

### 🌐 Web Evidence Discovery
Automated evidence discovery from web sources:
- **Brave Search API** - Current web content (requires API key)
- **Common Crawl** - Billions of archived web pages
- **AI Validation** - LLM-powered relevance scoring
- **Auto-Discovery** - Generate keywords from claims

See [docs/WEB_EVIDENCE_DISCOVERY.md](docs/WEB_EVIDENCE_DISCOVERY.md)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Complaint Input                             │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LLM Router Backend                            │
│   (Multi-provider LLM: OpenRouter, HuggingFace, Claude, etc.)   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Legal Analysis Hooks                          │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │ Classification   │  │ Statute Retrieval│                     │
│  └──────────────────┘  └──────────────────┘                     │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │ Requirements     │  │ Question Gen     │                     │
│  └──────────────────┘  └──────────────────┘                     │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              Legal Authority Research Hooks                      │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │  US Code   │  │ Fed Register │  │ RECAP Archive│             │
│  └────────────┘  └──────────────┘  └──────────────┘             │
│  ┌────────────┐                                                  │
│  │Web Archives│  (Common Crawl Search Engine)                    │
│  └────────────┘                                                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              Web Evidence Discovery Hooks                        │
│  ┌────────────┐  ┌──────────────┐                               │
│  │Brave Search│  │ Common Crawl │                               │
│  └────────────┘  └──────────────┘                               │
│         │                │                                       │
│         └────────┬───────┘                                       │
│                  ▼                                               │
│         ┌────────────────┐                                       │
│         │ AI Validation  │                                       │
│         └────────────────┘                                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Storage Layer                                 │
│  ┌─────────────────────┐  ┌──────────────────────┐              │
│  │  IPFS (Evidence)    │  │   DuckDB (Metadata)  │              │
│  │  - Content CIDs     │  │   - Evidence table   │              │
│  │  - Immutable        │  │   - Authorities table│              │
│  └─────────────────────┘  └──────────────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

## Installation

### Prerequisites

- Python 3.8+
- Git
- (Optional) Brave Search API key for web evidence discovery

### Quick Start

1. **Clone the repository:**
```bash
git clone https://github.com/endomorphosis/complaint-generator.git
cd complaint-generator
```

2. **Initialize the ipfs_datasets_py submodule:**
```bash
git submodule update --init --recursive
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **(Optional) Set up Brave Search API:**
```bash
export BRAVE_SEARCH_API_KEY="your_api_key_here"
```

### Running the Application

**Basic run:**
```bash
python run.py
```

**Run with specific config:**
```bash
python run.py --config config.llm_router.json
```

## Configuration

The generator's behavior is defined by configuration files (`.json` or `.toml` format).

### Configuration Structure

```json
{
  "BACKENDS": [
    {
      "id": "llm-router",
      "type": "llm_router",
      "provider": "local_hf",
      "model": "gpt2",
      "max_tokens": 128
    }
  ],
  "MEDIATOR": {
    "backends": ["llm-router"]
  },
  "APPLICATION": {
    "type": "console"
  }
}
```

### Configuration Sections

- **`BACKENDS`** - Defines backend adapters (LLM providers, models, credentials)
- **`MEDIATOR`** - Core logic configuration (which backends to use)
- **`APPLICATION`** - Frontend application settings

### Example Configurations

- `config.json` - Default OpenAI backend configuration
- `config.llm_router.json` - LLM Router with multiple provider support
- `config.toml` - TOML format configuration

## Usage Examples

### Basic Complaint Analysis

```python
from mediator import Mediator
from backends import LLMRouterBackend

# Initialize
backend = LLMRouterBackend(id='llm-router', provider='local_hf')
mediator = Mediator(backends=[backend])

# Set complaint text
mediator.state.complaint = """
    I was terminated from my job after reporting safety violations
    to OSHA. My employer claimed it was due to poor performance,
    but I had received excellent reviews for 5 years.
"""

# Run legal analysis
result = mediator.analyze_complaint_legal_issues()

print("Claim Types:", result['classification']['claim_types'])
print("Applicable Statutes:", result['statutes'])
print("Evidence Questions:", result['questions'][:3])
```

### Evidence Management

```python
# Submit evidence
result = mediator.submit_evidence(
    data=b"Performance review document...",
    evidence_type='document',
    description='5 years of excellent performance reviews',
    claim_type='wrongful termination'
)
print(f"Evidence stored with CID: {result['cid']}")

# Retrieve user's evidence
evidence_list = mediator.get_user_evidence()
print(f"Total evidence items: {len(evidence_list)}")

# Analyze evidence for specific claim
analysis = mediator.analyze_evidence(claim_type='wrongful termination')
print(f"Recommendations: {analysis['recommendation']}")
```

### Automatic Legal Research

```python
# Research applicable laws automatically
results = mediator.research_case_automatically()
print(f"Found {results['total_authorities']} legal authorities")

# Get stored authorities
authorities = mediator.get_legal_authorities(claim_type='retaliation')
for auth in authorities:
    print(f"- {auth['citation']}: {auth['title']}")
```

### Web Evidence Discovery

```python
# Automatically discover evidence
results = mediator.discover_evidence_automatically()
print(f"Discovered: {results['total_discovered']}")
```

### DEI Policy Analysis

```python
from complaint_analysis import (
    DEIRiskScorer,
    DEIProvisionExtractor,
    DEIReportGenerator
)

# Analyze policy for DEI compliance risks
policy_text = """
All contractors shall implement diversity, equity, and inclusion 
initiatives. Cultural competence training is mandatory for all staff.
"""

# Risk assessment
scorer = DEIRiskScorer()
risk = scorer.calculate_risk(policy_text)
print(f"Risk Level: {risk['level']} ({risk['score']}/3)")
print(f"Issues: {risk['issues']}")

# Extract specific provisions
extractor = DEIProvisionExtractor()
provisions = extractor.extract_provisions(policy_text, document_type='policy')
for prov in provisions:
    print(f"{prov['section']}: {prov['is_binding']}")

# Generate comprehensive report
generator = DEIReportGenerator(project_name="Policy Review")
generator.add_document_analysis(risk, provisions, {'source': 'Contract XYZ'})
reports = generator.save_reports('output/')
print(f"Reports saved: {list(reports.keys())}")
```

See [docs/HACC_INTEGRATION.md](docs/HACC_INTEGRATION.md) for complete API reference.
print(f"Stored: {results['total_stored']}")

# Manual search with specific keywords
search_results = mediator.search_web_for_evidence(
    keywords=['OSHA retaliation', 'whistleblower protection'],
    domains=['osha.gov', 'dol.gov'],
    max_results=10
)
```

## Testing

The project includes a comprehensive test suite following Test-Driven Development (TDD) principles.

### Run All Tests

```bash
pytest
```

### Run with Coverage

```bash
pytest --cov=. --cov-report=html
```

### Run Specific Test Categories

```bash
# Integration tests only
pytest -m integration

# Exclude integration tests (faster)
pytest -m "not integration"
```

### Test Structure

```
tests/
├── test_log.py                     # Logging module (6 tests)
├── test_mediator.py                # Mediator core (4 tests)
├── test_state.py                   # State management (2 tests)
├── test_integration.py             # End-to-end workflows (2 tests)
├── test_llm_router_backend.py      # LLM routing (7 tests)
├── test_legal_hooks.py             # Legal analysis (12 tests)
├── test_evidence_hooks.py          # Evidence management (12 tests)
├── test_legal_authority_hooks.py   # Legal research (11 tests)
└── test_web_evidence_hooks.py      # Web discovery (12 tests)
```

See [TESTING.md](TESTING.md) and [tests/README.md](tests/README.md) for detailed testing documentation.

## Database Schema

### Evidence Table

Stores evidence metadata with references to IPFS content.

```sql
CREATE TABLE evidence (
    id BIGINT PRIMARY KEY,
    user_id VARCHAR,
    username VARCHAR,
    evidence_cid VARCHAR NOT NULL,         -- IPFS Content ID
    evidence_type VARCHAR NOT NULL,         -- document, image, video, etc.
    evidence_size INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON,                          -- source_type, relevance_score, etc.
    complaint_id VARCHAR,
    claim_type VARCHAR,
    description TEXT
)
```

**Indexes:**
- `idx_evidence_cid` - Fast CID lookups
- `idx_evidence_user` - User-specific queries

### Legal Authorities Table

Stores researched legal authorities (statutes, regulations, case law).

```sql
CREATE TABLE legal_authorities (
    id BIGINT PRIMARY KEY,
    user_id VARCHAR,
    complaint_id VARCHAR,
    claim_type VARCHAR,
    authority_type VARCHAR NOT NULL,        -- statute, regulation, case_law
    source VARCHAR NOT NULL,                -- us_code, federal_register, recap
    citation VARCHAR,                       -- e.g., "42 U.S.C. § 1983"
    title TEXT,
    content TEXT,
    url VARCHAR,
    metadata JSON,
    relevance_score FLOAT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    search_query VARCHAR
)
```

**Indexes:**
- `idx_authorities_user` - User-specific queries
- `idx_authorities_claim` - Claim type filtering
- `idx_authorities_citation` - Citation lookups

## Documentation

### Core Documentation
- [TESTING.md](TESTING.md) - Testing guide and TDD workflow
- [tests/README.md](tests/README.md) - Detailed test documentation

### Feature Documentation
- [docs/LLM_ROUTER.md](docs/LLM_ROUTER.md) - LLM routing configuration
- [docs/LEGAL_HOOKS.md](docs/LEGAL_HOOKS.md) - Legal analysis system
- [docs/EVIDENCE_MANAGEMENT.md](docs/EVIDENCE_MANAGEMENT.md) - Evidence handling
- [docs/LEGAL_AUTHORITY_RESEARCH.md](docs/LEGAL_AUTHORITY_RESEARCH.md) - Legal research
- [docs/WEB_EVIDENCE_DISCOVERY.md](docs/WEB_EVIDENCE_DISCOVERY.md) - Web evidence discovery

### Example Scripts
- [examples/legal_analysis_demo.py](examples/legal_analysis_demo.py)
- [examples/evidence_management_demo.py](examples/evidence_management_demo.py)
- [examples/legal_authority_research_demo.py](examples/legal_authority_research_demo.py)
- [examples/web_evidence_discovery_demo.py](examples/web_evidence_discovery_demo.py)

## Development

### Project Structure

```
complaint-generator/
├── applications/          # Frontend applications
├── backends/             # Backend adapters (OpenAI, LLM Router, etc.)
├── docs/                 # Documentation
├── examples/             # Example scripts
├── ipfs_datasets_py/     # Submodule: IPFS, LLM routing, legal scrapers
├── lib/                  # Core utilities
├── mediator/             # Core business logic
│   ├── mediator.py       # Main mediator class
│   ├── state.py          # State management
│   ├── legal_hooks.py    # Legal analysis hooks
│   ├── evidence_hooks.py # Evidence management hooks
│   ├── legal_authority_hooks.py    # Legal research hooks
│   └── web_evidence_hooks.py       # Web discovery hooks
├── statefiles/           # Persistent state storage
├── templates/            # Application templates
├── tests/                # Test suite
├── config.json           # Default configuration
├── config.llm_router.json # LLM Router configuration
├── pytest.ini            # Pytest configuration
├── requirements.txt      # Python dependencies
└── run.py               # Application entry point
```

### Adding New Features (TDD Workflow)

1. **Write a failing test**
```python
def test_new_feature():
    result = new_feature()
    assert result == expected_value
```

2. **Run the test** (verify it fails)
```bash
pytest tests/test_new_feature.py -v
```

3. **Implement minimal code** to pass the test

4. **Run the test again** (verify it passes)

5. **Refactor** while keeping tests green

6. **Repeat** for next feature

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for your changes
4. Implement your changes
5. Run the test suite (`pytest`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Dependencies

### Core Dependencies
- `duckdb>=0.9.0` - Fast SQL database for state management
- `pytest>=7.0.0` - Testing framework
- `pytest-cov>=4.0.0` - Coverage reporting
- `pytest-asyncio>=0.21.0` - Async test support

### Submodule: ipfs_datasets_py
Provides:
- LLM routing (`llm_router`)
- IPFS storage (`ipfs_backend_router`)
- Legal scrapers (`legal_scrapers`)
- Web archiving tools (`web_archiving`)

## Troubleshooting

### Submodule Not Initialized
```bash
git submodule update --init --recursive
```

### Import Errors from ipfs_datasets_py
The application automatically adds `ipfs_datasets_py` to the Python path. If you encounter import errors:
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/ipfs_datasets_py"
```

### DuckDB File Locked
If you see database locking errors:
```bash
rm statefiles/*.duckdb  # Remove existing database files
```

### Missing Brave Search Results
Web evidence discovery requires a Brave Search API key:
```bash
export BRAVE_SEARCH_API_KEY="your_key"
```
Get a free API key at: https://brave.com/search/api/

## Support

- **Issues**: https://github.com/endomorphosis/complaint-generator/issues
- **Discussions**: https://github.com/endomorphosis/complaint-generator/discussions

## Acknowledgments

- Built with [ipfs_datasets_py](https://github.com/endomorphosis/ipfs_datasets_py)
- Developed by JusticeDAO
- Powered by multiple LLM providers through the LLM Router

---

**Note**: This system is designed to assist legal professionals and should not be considered a replacement for professional legal advice. Always consult with a qualified attorney for legal matters.
