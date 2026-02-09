# Three-Phase Complaint Processing System

A sophisticated multi-phase complaint processing system that combines knowledge graphs, dependency graphs, and neurosymbolic AI to create formal legal complaints through iterative refinement.

## Overview

The complaint_phases module implements a three-phase workflow inspired by denoising diffusion techniques:

1. **Phase 1: Intake & Denoising** - Build knowledge/dependency graphs, iteratively fill information gaps
2. **Phase 2: Evidence Gathering** - Enhance graphs with evidence, track requirement satisfaction
3. **Phase 3: Formalization** - Match against legal requirements, generate formal complaint

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PHASE 1: INTAKE                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Initial Complaint Text                              │   │
│  └──────────────┬───────────────────────────────────────┘   │
│                 │                                            │
│                 ▼                                            │
│  ┌──────────────────────────┐  ┌────────────────────────┐   │
│  │   Knowledge Graph        │  │  Dependency Graph      │   │
│  │  (Entities & Relations)  │  │  (Claims & Reqs)       │   │
│  └──────────────────────────┘  └────────────────────────┘   │
│                 │                          │                 │
│                 └──────────┬───────────────┘                 │
│                            ▼                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │   Denoising Questions                                │   │
│  │   (Fill gaps, reduce uncertainty)                    │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  PHASE 2: EVIDENCE                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Identify Evidence Gaps                              │   │
│  └──────────────┬───────────────────────────────────────┘   │
│                 │                                            │
│                 ▼                                            │
│  ┌──────────────────────────┐  ┌────────────────────────┐   │
│  │  User-Submitted Evidence │  │  Auto-Discovered       │   │
│  │  (Documents, Testimony)  │  │  Evidence (Web)        │   │
│  └──────────────────────────┘  └────────────────────────┘   │
│                 │                          │                 │
│                 └──────────┬───────────────┘                 │
│                            ▼                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │   Enhanced Knowledge & Dependency Graphs             │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              PHASE 3: FORMALIZATION                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Legal Graph (Statutes, Requirements, Procedures)    │   │
│  └──────────────┬───────────────────────────────────────┘   │
│                 │                                            │
│                 ▼                                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │   Neurosymbolic Matching                             │   │
│  │   (Facts ↔ Legal Requirements)                       │   │
│  └──────────────┬───────────────────────────────────────┘   │
│                 │                                            │
│                 ▼                                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │   Formal Complaint Document                          │   │
│  │   (Title, Parties, Claims, Facts, Relief)            │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Phase Manager (`phase_manager.py`)

**Purpose:** Orchestrates the three-phase workflow with automatic phase transitions.

**Key Classes:**
- `ComplaintPhase` (enum) - INTAKE, EVIDENCE, FORMALIZATION
- `PhaseManager` - Phase orchestration and transition logic

**Phase Completion Criteria:**
- **Phase 1**: Knowledge/dependency graphs built + gaps ≤ 3 + converged (gap_ratio < 0.3)
- **Phase 2**: Evidence gathered + graphs enhanced + gap_ratio < 0.3
- **Phase 3**: Legal graph built + matching complete + formal complaint generated

**Example:**
```python
from complaint_phases import PhaseManager

manager = PhaseManager(mediator)

# Start intake phase
manager.start_intake_phase(complaint_text)

# Process iteratively
while not manager.is_phase_complete():
    questions = manager.get_next_questions()
    answers = collect_answers(questions)
    manager.process_answers(answers)

# Automatic transition to next phase
manager.transition_to_next_phase()
```

### 2. Knowledge Graph (`knowledge_graph.py`)

**Purpose:** Represent facts, entities, and relationships from the complaint.

**Key Classes:**
- `Entity` - Represents people, organizations, dates, facts, claims
- `Relationship` - Represents connections (employed_by, caused_by, occurred_on, etc.)
- `KnowledgeGraph` - Container for entities and relationships
- `KnowledgeGraphBuilder` - Constructs graphs from text

**Entity Types:**
- `person` - Individuals involved
- `organization` - Companies, agencies, institutions
- `date` - Temporal information
- `location` - Places where events occurred
- `fact` - Factual statements
- `claim` - Legal claims or allegations

**Relationship Types:**
- `employed_by` - Employment relationships
- `caused_by` - Causation
- `occurred_on` - Temporal association
- `located_at` - Spatial association
- `related_to` - General association

**Features:**
- Entity extraction with confidence scores
- Relationship inference
- Gap detection (low confidence, isolated entities, unsupported claims)
- Graph merging for iterative enhancement
- JSON serialization for persistence

**Example:**
```python
from complaint_phases import KnowledgeGraphBuilder

builder = KnowledgeGraphBuilder(mediator=mediator)
graph = builder.build_from_text(complaint_text)

# Inspect entities
for entity in graph.entities.values():
    print(f"{entity.type}: {entity.value} (confidence: {entity.confidence})")

# Inspect relationships
for rel in graph.relationships.values():
    print(f"{rel.source} --[{rel.type}]--> {rel.target}")

# Detect gaps
gaps = graph.find_gaps()
print(f"Low confidence entities: {len(gaps.get('low_confidence_entities', []))}")
print(f"Isolated entities: {len(gaps.get('isolated_entities', []))}")

# Save/load
graph.to_json('knowledge_graph.json')
loaded_graph = KnowledgeGraph.from_json('knowledge_graph.json')
```

### 3. Dependency Graph (`dependency_graph.py`)

**Purpose:** Track what each claim requires and whether requirements are satisfied.

**Key Classes:**
- `DependencyNode` - Represents claims, requirements, facts, evidence, legal elements
- `Dependency` - Represents dependencies (requires, supports, contradicts, enables)
- `DependencyGraph` - Container tracking satisfaction of requirements
- `DependencyGraphBuilder` - Constructs dependency structures from claims

**Node Types:**
- `claim` - Legal claims (discrimination, retaliation, etc.)
- `requirement` - Elements required to prove claim
- `fact` - Facts that support requirements
- `evidence` - Evidence items
- `legal_element` - Specific legal requirements

**Dependency Types:**
- `requires` - Hard requirement (claim requires element)
- `supports` - Supportive relationship (evidence supports fact)
- `contradicts` - Contradictory information
- `enables` - Enabling relationship

**Features:**
- Requirement tracking per claim
- Satisfaction checking (is requirement met?)
- Gap identification (unsatisfied requirements)
- Evidence mapping (which evidence supports which requirements)
- Propagation logic (satisfaction flows through graph)

**Example:**
```python
from complaint_phases import DependencyGraphBuilder

builder = DependencyGraphBuilder(mediator=mediator)
graph = builder.build_from_claims(claims)

# Check satisfaction
for claim_id, node in graph.nodes.items():
    if node.node_type == NodeType.CLAIM:
        satisfaction = graph.calculate_satisfaction(claim_id)
        print(f"Claim: {node.name}")
        print(f"  Satisfaction: {satisfaction['satisfied']}/{satisfaction['total']}")

# Get gaps
gaps = graph.identify_gaps()
print(f"Unsatisfied requirements: {len(gaps.get('unsatisfied_requirements', []))}")

# Save/load
graph.to_json('dependency_graph.json')
loaded_graph = DependencyGraph.from_json('dependency_graph.json')
```

### 4. Complaint Denoiser (`denoiser.py`)

**Purpose:** Iteratively reduce information gaps through targeted questioning.

**Key Classes:**
- `ComplaintDenoiser` - Gap reduction through iterative questioning

**Denoising Metrics:**
- **Noise Calculation**: `noise = (1 - entity_confidence) * 0.4 + (1 - dependency_satisfaction) * 0.4 + gap_ratio * 0.2`
- **Gap Ratio**: `unsatisfied_requirements / total_requirements`
- **Convergence**: Detected when gap_ratio < 0.3 and gaps ≤ 3

**Features:**
- Automatic question generation from gaps
- Priority-based questioning (address most critical gaps first)
- Convergence detection
- Iterative refinement
- Progress tracking

**Example:**
```python
from complaint_phases import ComplaintDenoiser

denoiser = ComplaintDenoiser(mediator=mediator)

# Generate questions from graphs
questions = denoiser.generate_questions(knowledge_graph, dependency_graph, max_questions=5)

# Calculate noise level
noise_level = denoiser.calculate_noise_level(knowledge_graph, dependency_graph)

print(f"Noise Level: {noise_level}")
```

### 5. Legal Graph (`legal_graph.py`)

**Purpose:** Represent legal requirements, statutes, and procedures for claims.

**Key Classes:**
- `LegalElement` - Represents statutes, regulations, case law, procedural requirements
- `LegalRelation` - Represents relationships (applies_to, requires, supersedes)
- `LegalGraph` - Container for legal knowledge
- `LegalGraphBuilder` - Constructs legal graphs for complaint types

**Legal Element Types:**
- `statute` - Federal/state statutes
- `regulation` - Administrative regulations
- `case_law` - Precedential court decisions
- `procedural_requirement` - Filing procedures, deadlines, jurisdiction
- `element` - Elements of a claim

**Legal Relation Types:**
- `applies_to` - Legal element applies to claim
- `requires` - Element requires another element
- `supersedes` - One law supersedes another
- `interpreted_by` - Statute interpreted by case law

**Features:**
- Multi-source legal authority integration
- Procedural requirement tracking
- Jurisdiction-aware matching
- Citation management
- JSON serialization

**Example:**
```python
from complaint_phases import LegalGraphBuilder

builder = LegalGraphBuilder(mediator=mediator)
graph = builder.build_for_claims(claims)

# Inspect legal elements
for element in graph.elements.values():
    print(f"{element.element_type}: {element.citation}")
    print(f"  Text: {element.text[:100]}...")
    print(f"  Applies to: {element.applies_to}")

# Check procedural requirements
procedural = graph.get_procedural_requirements()
for req in procedural:
    print(f"Requirement: {req.text}")
    print(f"  Deadline: {req.metadata.get('deadline')}")

# Save/load
graph.to_json('legal_graph.json')
loaded_graph = LegalGraph.from_json('legal_graph.json')
```

### 6. Neurosymbolic Matcher (`neurosymbolic_matcher.py`)

**Purpose:** Combine symbolic and semantic reasoning for legal requirement matching.

**Key Classes:**
- `NeurosymbolicMatcher` - Hybrid symbolic + semantic matching engine

**Matching Strategies:**
1. **Symbolic Matching** - Graph pattern matching, dependency checking, logical inference
2. **Semantic Matching** - LLM-based similarity, contextual understanding, intent recognition
3. **Hybrid Scoring** - Weighted combination of symbolic (0.6) and semantic (0.4) scores

**Features:**
- Fact-to-requirement matching
- Satisfaction scoring (0.0-1.0)
- Explanation generation
- Confidence scoring
- Missing element identification

**Example:**
```python
from complaint_phases import NeurosymbolicMatcher

matcher = NeurosymbolicMatcher(mediator=mediator)

# Match facts to legal requirements
matches = matcher.match_requirements(
    knowledge_graph=knowledge_graph,
    dependency_graph=dependency_graph,
    legal_graph=legal_graph
)

# Review matches
for req_id, match in matches.items():
    print(f"Requirement: {match['requirement']}")
    print(f"  Satisfaction: {match['satisfaction_score']}")
    print(f"  Matched Facts: {match.get('matched_facts', [])}")

# Check overall satisfaction
overall = matcher.calculate_satisfaction_score(matches)
print(f"Overall Satisfaction: {overall}")
```

## Phase Workflows

### Phase 1: Intake & Denoising

```python
from complaint_phases import (
    PhaseManager,
    KnowledgeGraphBuilder,
    DependencyGraphBuilder,
    ComplaintDenoiser
)

# Initialize
manager = PhaseManager(mediator)
kg_builder = KnowledgeGraphBuilder(llm_backend)
dg_builder = DependencyGraphBuilder(llm_backend)
denoiser = ComplaintDenoiser(llm_backend)

# Start intake
manager.start_intake_phase(complaint_text)

# Build initial graphs
knowledge_graph = kg_builder.build_from_text(complaint_text)
dependency_graph = dg_builder.build_from_claims(
    extract_claims(complaint_text),
    knowledge_graph
)

# Iterative denoising
denoiser.set_graphs(knowledge_graph, dependency_graph)

max_iterations = 5
for i in range(max_iterations):
    # Generate questions
    questions = denoiser.generate_denoising_questions(max_questions=3)
    
    # Collect answers (from user or LLM)
    answers = collect_answers(questions)
    
    # Process answers and update graphs
    for q, a in zip(questions, answers):
        denoiser.process_answer(q, a)
    
    # Check convergence
    if denoiser.has_converged():
        print(f"Converged after {i+1} iterations")
        break

# Save state
knowledge_graph.to_json_file('statefiles/knowledge_graph.json')
dependency_graph.to_json_file('statefiles/dependency_graph.json')

# Transition to Phase 2
manager.transition_to_next_phase()
```

### Phase 2: Evidence Gathering

```python
# Continue from Phase 1
manager.start_evidence_phase()

# Identify evidence gaps
gaps = dependency_graph.get_gaps()
evidence_requirements = gaps['unsatisfied_requirements']

# Gather evidence (user submission + auto-discovery)
for requirement in evidence_requirements:
    # User-submitted evidence
    user_evidence = collect_user_evidence(requirement)
    
    # Auto-discovered web evidence
    web_evidence = mediator.discover_evidence_automatically(
        keywords=generate_keywords(requirement)
    )
    
    # Add to graphs
    for evidence in user_evidence + web_evidence:
        dependency_graph.add_evidence_node(evidence, supports=requirement)

# Re-check satisfaction
updated_gaps = dependency_graph.get_gaps()
gap_ratio = len(updated_gaps['unsatisfied_requirements']) / dependency_graph.total_requirements

# Transition to Phase 3 if ready
if gap_ratio < 0.3:
    manager.transition_to_next_phase()
```

### Phase 3: Formalization

```python
from complaint_phases import LegalGraphBuilder, NeurosymbolicMatcher

# Start formalization
manager.start_formalization_phase()

# Build legal graph
lg_builder = LegalGraphBuilder(llm_backend, legal_hooks)
legal_graph = lg_builder.build_for_claims(
    claims=dependency_graph.get_claims(),
    jurisdiction='federal'
)

# Neurosymbolic matching
matcher = NeurosymbolicMatcher(llm_backend)
matches = matcher.match_facts_to_requirements(
    knowledge_graph=knowledge_graph,
    dependency_graph=dependency_graph,
    legal_graph=legal_graph
)

# Generate formal complaint
formal_complaint = generate_formal_complaint(
    knowledge_graph=knowledge_graph,
    dependency_graph=dependency_graph,
    legal_graph=legal_graph,
    matches=matches
)

print(f"Formal Complaint Generated:")
print(formal_complaint)

# Save final state
legal_graph.to_json_file('statefiles/legal_graph.json')
save_formal_complaint(formal_complaint, 'statefiles/formal_complaint.txt')
```

## Testing

Comprehensive test coverage in `tests/test_complaint_phases.py` (7 test classes, 27 tests):

- `TestKnowledgeGraph` - Entity and relationship extraction
- `TestDependencyGraph` - Requirement tracking and satisfaction
- `TestComplaintDenoiser` - Gap reduction and convergence
- `TestPhaseManager` - Phase orchestration
- `TestLegalGraph` - Legal knowledge representation
- `TestNeurosymbolicMatcher` - Hybrid matching logic
- `TestIntegration` - End-to-end three-phase workflow

Additional tests in `tests/test_mediator_three_phase.py` and `tests/test_enhanced_denoising.py`.

Run tests:
```bash
pytest tests/test_complaint_phases.py -v
pytest tests/test_mediator_three_phase.py -v
pytest tests/test_enhanced_denoising.py -v
```

## Examples

See `examples/three_phase_example.py` for a complete demonstration of the three-phase workflow.

## Graph Persistence

All graphs support JSON serialization for state persistence:

```python
# Save graphs
knowledge_graph.to_json_file('statefiles/knowledge_graph.json')
dependency_graph.to_json_file('statefiles/dependency_graph.json')
legal_graph.to_json_file('statefiles/legal_graph.json')

# Load graphs
from complaint_phases import KnowledgeGraph, DependencyGraph, LegalGraph

kg = KnowledgeGraph.from_json_file('statefiles/knowledge_graph.json')
dg = DependencyGraph.from_json_file('statefiles/dependency_graph.json')
lg = LegalGraph.from_json_file('statefiles/legal_graph.json')
```

## Configuration

Key configuration parameters:

- `max_denoising_iterations` - Maximum denoising rounds (default: 5)
- `convergence_threshold` - Gap ratio threshold for convergence (default: 0.3)
- `max_gaps_for_completion` - Maximum gaps allowed for phase completion (default: 3)
- `entity_confidence_threshold` - Minimum confidence for entities (default: 0.6)
- `symbolic_weight` - Weight for symbolic matching (default: 0.6)
- `semantic_weight` - Weight for semantic matching (default: 0.4)

## Best Practices

1. **Start with Quality Input** - Better initial complaints lead to faster convergence
2. **Monitor Gap Ratios** - Track progress through gap ratio reduction
3. **Persist State** - Save graphs after each phase for resumability
4. **Use Appropriate Iteration Limits** - Balance completeness with efficiency
5. **Validate Matches** - Review neurosymbolic matches for accuracy
6. **Integrate Evidence Early** - Phase 2 evidence improves Phase 3 matching
7. **Check Procedural Requirements** - Ensure legal graph includes all procedures

## Integration with Other Modules

### Mediator Integration
The mediator coordinates three-phase processing via `run_three_phase_processing()`:
```python
result = mediator.run_three_phase_processing(
    initial_complaint=complaint_text,
    max_iterations=5
)
```

### Complaint Analysis Integration
- Uses complaint_analysis for claim type identification
- Leverages decision trees for guided questioning
- Integrates legal patterns for requirement extraction

### Evidence Management Integration
- Connects to evidence_hooks for storage
- Uses web_evidence_hooks for auto-discovery
- Integrates legal_authority_hooks for legal research

## See Also

- [docs/THREE_PHASE_SYSTEM.md](../docs/THREE_PHASE_SYSTEM.md) - Detailed system documentation
- [examples/three_phase_example.py](../examples/three_phase_example.py) - Complete workflow example
- [tests/test_complaint_phases.py](../tests/test_complaint_phases.py) - Test suite
- [mediator/readme.md](../mediator/readme.md) - Mediator integration
- [docs/LEGAL_HOOKS.md](../docs/LEGAL_HOOKS.md) - Legal analysis integration
