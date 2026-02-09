# The Mediator

Core orchestration module of the complaint generator. Sits between the frontend application and the backend services, coordinating all complaint processing workflows.

## Overview

![Complaint Generator Mediator](https://user-images.githubusercontent.com/13929820/159747598-01bea9f8-2087-4ee2-869b-aede394cb168.svg)

The Mediator module is the external facing interface and has the function signatures as shown in the diagram. These are the only methods callable by the application modules, such as the CLI app.
Arrow directions indicate dependencies.

## Core Components

### Mediator Class (`mediator.py`)

The main orchestration class that coordinates all complaint processing activities.

**Key Methods:**
- `analyze_complaint_legal_issues()` - Run 4-stage legal analysis pipeline
- `research_case_automatically()` - Automated multi-source legal research
- `discover_evidence_automatically()` - Web evidence discovery with AI validation
- `submit_evidence()` - Store evidence in IPFS with DuckDB metadata
- `get_user_evidence()` - Retrieve stored evidence
- `analyze_evidence()` - AI-powered evidence gap analysis
- `get_legal_authorities()` - Query researched legal authorities
- `search_web_for_evidence()` - Manual web search with specific keywords
- `run_three_phase_processing()` - Execute complete three-phase workflow
- `save_phase_state()` / `load_phase_state()` - Persist processing state

### State Management (`state.py`)

DuckDB-backed persistent state management for evidence, legal authorities, and processing state.

**Features:**
- Evidence table with IPFS CID references
- Legal authorities table with multi-source citations
- Complaint metadata and processing state
- SQL indexes for fast queries
- Thread-safe operations

### Hooks Architecture

The mediator uses a hook-based architecture for extensibility. All hooks implement `.execute(state, mediator)` and `.hook_name()` methods.

#### Legal Analysis Hooks (`legal_hooks.py`)

Four-stage legal analysis pipeline:

1. **LegalClassificationHook** - Extract claim types, jurisdiction, legal areas
2. **StatuteRetrievalHook** - Identify applicable laws and regulations
3. **SummaryJudgmentHook** - Generate required elements per claim type
4. **QuestionGenerationHook** - Create evidence-gathering questions

#### Legal Research Hooks (`legal_authority_hooks.py`)

Multi-source legal research with automated discovery:

- **LegalAuthoritySearchHook** - Search US Code, Federal Register, RECAP, Common Crawl
- **LegalAuthorityStorageHook** - Store findings in DuckDB with relevance scoring
- **LegalAuthorityAnalysisHook** - AI-powered relevance analysis and recommendations

#### Evidence Management Hooks (`evidence_hooks.py`)

IPFS-based evidence storage with DuckDB metadata:

- **EvidenceStorageHook** - Store evidence with content-addressable CIDs
- **EvidenceStateHook** - Track evidence metadata (type, description, claim association)
- **EvidenceAnalysisHook** - Identify gaps and generate recommendations

#### Web Evidence Discovery Hooks (`web_evidence_hooks.py`)

Automated evidence discovery from web sources:

- **WebEvidenceSearchHook** - Search via Brave Search API and Common Crawl archives
- **WebEvidenceIntegrationHook** - AI validation and relevance scoring
- Automatic keyword generation from claims
- Domain filtering and content classification

#### Legal Corpus RAG Hooks (`legal_corpus_hooks.py`)

Retrieval-Augmented Generation over legal corpus:

- **LegalCorpusRAGHook** - RAG over 90+ legal patterns and 390+ keywords
- `search_legal_corpus()` - Semantic search across complaint types
- `retrieve_relevant_laws()` - Find applicable statutes and regulations
- `enrich_decision_tree()` - Enhance decision trees with legal knowledge
- `get_legal_requirements()` - Extract requirements for claim types
- `suggest_questions()` - Generate evidence-gathering questions

## Three-Phase Complaint Processing

The mediator coordinates a sophisticated three-phase workflow (see `docs/THREE_PHASE_SYSTEM.md`):

### Phase 1: Intake & Denoising
- Build knowledge graph (entities, relationships)
- Build dependency graph (claims, requirements)
- Iteratively ask questions to fill gaps
- Detect convergence (gap_ratio < 0.3, gaps ≤ 3)

### Phase 2: Evidence Gathering
- Identify evidence gaps from dependency graph
- Integrate user-submitted and auto-discovered evidence
- Enhance graphs with evidence
- Track requirement satisfaction

### Phase 3: Formalization
- Build legal graph (statutes, requirements, procedures)
- Neurosymbolic matching (facts ↔ legal requirements)
- Generate formal complaint document
- Validate completeness

## Integration with Other Modules

### Complaint Analysis Integration
- Uses `complaint_analysis` for classification and risk scoring
- Leverages decision trees for guided questioning
- Integrates seed generation for testing

### Adversarial Testing Integration
- Provides interface for `adversarial_harness` testing
- Supports critic evaluation via session metrics
- Enables optimizer feedback loops

### Backend Integration
- Routes LLM requests through `backends.LLMRouterBackend`
- Supports multiple providers (OpenAI, HuggingFace, Copilot, etc.)
- Automatic fallback between providers

### IPFS Integration
- Uses `ipfs_datasets_py` for evidence storage
- Content-addressable storage via IPFS
- DuckDB for metadata and queries

## Usage Examples

### Basic Legal Analysis
```python
from mediator import Mediator
from backends import LLMRouterBackend

backend = LLMRouterBackend(id='llm-router', provider='copilot_cli', model='gpt-5-mini')
mediator = Mediator(backends=[backend])

mediator.state.complaint = "I was terminated after reporting safety violations..."
result = mediator.analyze_complaint_legal_issues()

print("Claim Types:", result['classification']['claim_types'])
print("Statutes:", result['statutes'])
print("Questions:", result['questions'][:3])
```

### Three-Phase Processing
```python
# Run complete three-phase workflow
result = mediator.run_three_phase_processing(
    initial_complaint="My employer violated my rights...",
    max_iterations=5
)

print(f"Phase: {result['current_phase']}")
print(f"Formal Complaint: {result['formal_complaint']}")
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
print(f"CID: {result['cid']}")

# Analyze evidence
analysis = mediator.analyze_evidence(claim_type='wrongful termination')
print(f"Recommendations: {analysis['recommendation']}")
```

### Automated Research
```python
# Research applicable laws
results = mediator.research_case_automatically()
print(f"Found {results['total_authorities']} legal authorities")

# Get authorities for specific claim
authorities = mediator.get_legal_authorities(claim_type='retaliation')
for auth in authorities:
    print(f"- {auth['citation']}: {auth['title']}")
```

## Testing

See `tests/test_mediator.py` and `tests/test_mediator_three_phase.py` for comprehensive unit and integration tests.

## See Also

- [docs/THREE_PHASE_SYSTEM.md](../docs/THREE_PHASE_SYSTEM.md) - Three-phase workflow documentation
- [docs/LEGAL_HOOKS.md](../docs/LEGAL_HOOKS.md) - Legal analysis hooks
- [docs/EVIDENCE_MANAGEMENT.md](../docs/EVIDENCE_MANAGEMENT.md) - Evidence management
- [docs/LEGAL_AUTHORITY_RESEARCH.md](../docs/LEGAL_AUTHORITY_RESEARCH.md) - Legal research
- [docs/SEARCH_HOOKS.md](../docs/SEARCH_HOOKS.md) - Search and RAG integration
