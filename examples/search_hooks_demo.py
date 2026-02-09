#!/usr/bin/env python3
"""
Demo: Search Hooks Integration

Demonstrates the integration of Brave search and legal corpus RAG hooks
with the complaint system for both adversarial testing and mediation.
"""

import sys
import os
from pathlib import Path

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import hooks directly without going through __init__.py which imports everything
import importlib.util

def import_module_from_file(module_name, file_path):
    """Import a module from a file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# Import hooks directly
base_dir = os.path.dirname(os.path.dirname(__file__))
legal_corpus_hooks = import_module_from_file(
    'legal_corpus_hooks',
    os.path.join(base_dir, 'mediator', 'legal_corpus_hooks.py')
)
search_hooks = import_module_from_file(
    'search_hooks',
    os.path.join(base_dir, 'adversarial_harness', 'search_hooks.py')
)

LegalCorpusRAGHook = legal_corpus_hooks.LegalCorpusRAGHook
SearchEnrichedSeedGenerator = search_hooks.SearchEnrichedSeedGenerator
DecisionTreeEnhancer = search_hooks.DecisionTreeEnhancer
MediatorSearchIntegration = search_hooks.MediatorSearchIntegration


class MockMediator:
    """Mock mediator for demonstration."""
    def __init__(self):
        self.logs = []
    
    def log(self, event_type, **kwargs):
        self.logs.append({'type': event_type, 'data': kwargs})
        print(f"[LOG] {event_type}: {kwargs}")


def demo_legal_corpus_rag():
    """Demonstrate legal corpus RAG hook."""
    print("\n" + "="*80)
    print("DEMO 1: Legal Corpus RAG Hook")
    print("="*80)
    
    mediator = MockMediator()
    hook = LegalCorpusRAGHook(mediator)
    
    print("\n1. Searching legal corpus for 'discrimination':")
    results = hook.search_legal_corpus("discrimination", max_results=5)
    print(f"   Found {len(results)} results")
    for i, result in enumerate(results[:3], 1):
        print(f"   {i}. [{result['type']}] {result['content'][:80]}...")
    
    print("\n2. Retrieving relevant laws for claims:")
    claims = ["age discrimination at work", "wrongful termination"]
    laws = hook.retrieve_relevant_laws(claims)
    print(f"   Found {len(laws)} relevant laws")
    for i, law in enumerate(laws[:3], 1):
        print(f"   {i}. Claim: {law.get('claim', 'N/A')[:40]}...")
        print(f"      Law: {law.get('legal_reference', 'N/A')[:60]}...")
    
    print("\n3. Getting legal requirements for employment_discrimination:")
    requirements = hook.get_legal_requirements('employment_discrimination')
    if requirements:
        print(f"   Category: {requirements.get('category', 'N/A')}")
        print(f"   Keywords: {len(requirements.get('keywords', []))} keywords")
        print(f"   Sample keywords: {requirements.get('keywords', [])[:5]}")


def demo_seed_enrichment():
    """Demonstrate seed enrichment with search."""
    print("\n" + "="*80)
    print("DEMO 2: Search-Enriched Seed Generation")
    print("="*80)
    
    generator = SearchEnrichedSeedGenerator()
    
    seed_template = {
        'complaint_type': 'employment_discrimination',
        'category': 'employment',
        'description': 'Discrimination based on age in the workplace',
        'required_fields': ['employer', 'discrimination_type', 'date'],
        'optional_fields': ['witnesses', 'evidence']
    }
    
    print("\n1. Original seed template:")
    print(f"   Type: {seed_template['complaint_type']}")
    print(f"   Description: {seed_template['description']}")
    
    print("\n2. Enriching with legal corpus...")
    enriched = generator.enrich_seed_with_legal_corpus(seed_template)
    if 'legal_context' in enriched:
        print(f"   Added legal context with {len(enriched['legal_context'].get('keywords', []))} keywords")
    if 'legal_references' in enriched:
        print(f"   Added {len(enriched['legal_references'])} legal references")
    
    print("\n3. Full enrichment (search + legal corpus)...")
    fully_enriched = generator.enrich_seed_full(seed_template)
    print(f"   Enriched: {fully_enriched.get('enriched', False)}")
    print(f"   Enriched at: {fully_enriched.get('enriched_at', 'N/A')}")


def demo_decision_tree_enhancement():
    """Demonstrate decision tree enhancement."""
    print("\n" + "="*80)
    print("DEMO 3: Decision Tree Enhancement")
    print("="*80)
    
    enhancer = DecisionTreeEnhancer()
    
    tree_data = {
        'complaint_type': 'employment_discrimination',
        'category': 'employment',
        'description': 'Employment discrimination complaint',
        'root_questions': ['q1', 'q2'],
        'questions': {
            'q1': {
                'id': 'q1',
                'question': 'What type of discrimination occurred?',
                'field_name': 'discrimination_type',
                'required': True,
                'keywords': ['discrimination', 'type']
            },
            'q2': {
                'id': 'q2',
                'question': 'When did this occur?',
                'field_name': 'date',
                'required': True,
                'keywords': ['date', 'when']
            }
        }
    }
    
    print("\n1. Original decision tree:")
    print(f"   Type: {tree_data['complaint_type']}")
    print(f"   Questions: {len(tree_data['questions'])}")
    
    print("\n2. Enhancing tree with legal corpus...")
    enhanced = enhancer.enhance_decision_tree(tree_data)
    if 'legal_context' in enhanced:
        print(f"   Added legal context!")
        legal_ctx = enhanced['legal_context']
        print(f"   - Legal patterns: {len(legal_ctx.get('legal_patterns', []))}")
        print(f"   - Relevant terms: {len(legal_ctx.get('relevant_terms', []))}")
    
    print("\n3. Suggesting additional questions...")
    suggestions = enhancer.suggest_additional_questions(tree_data)
    print(f"   Found {len(suggestions)} suggestions")
    for i, suggestion in enumerate(suggestions[:3], 1):
        print(f"   {i}. {suggestion.get('question', 'N/A')}")
        print(f"      Keyword: {suggestion.get('keyword', 'N/A')}")
        print(f"      Justification: {suggestion.get('justification', 'N/A')}")
    
    print("\n4. Validating question relevance...")
    validation = enhancer.validate_question_relevance(
        "What type of discrimination occurred?",
        "employment_discrimination"
    )
    print(f"   Valid: {validation['valid']}")
    print(f"   Relevance score: {validation['relevance_score']:.2f}")
    print(f"   Reason: {validation['reason']}")


def demo_mediator_integration():
    """Demonstrate mediator search integration."""
    print("\n" + "="*80)
    print("DEMO 4: Mediator Search Integration")
    print("="*80)
    
    mediator = MockMediator()
    integration = MediatorSearchIntegration(mediator)
    
    print("\n1. Enhancing question generation:")
    current_questions = [
        "What is your name?",
        "When did this happen?",
        "Where did it occur?"
    ]
    enhanced_questions = integration.enhance_question_generation(
        "employment_discrimination",
        current_questions
    )
    print(f"   Current questions: {len(current_questions)}")
    print(f"   Suggested questions: {len(enhanced_questions)}")
    for i, q in enumerate(enhanced_questions[:3], 1):
        print(f"   {i}. {q}")
    
    print("\n2. Enriching knowledge graph:")
    graph_data = {
        'entities': [
            {'id': 'e1', 'type': 'person', 'name': 'John Doe', 'confidence': 0.9},
            {'id': 'e2', 'type': 'organization', 'name': 'Acme Corp', 'confidence': 0.95}
        ],
        'relationships': [
            {'from': 'e1', 'to': 'e2', 'type': 'employed_by', 'confidence': 0.85}
        ]
    }
    
    enriched_graph = integration.enrich_knowledge_graph(
        graph_data,
        "employment_discrimination"
    )
    print(f"   Original entities: {len(graph_data['entities'])}")
    print(f"   Enriched graph has legal_requirements: {'legal_requirements' in enriched_graph}")


def main():
    """Run all demonstrations."""
    print("\n" + "="*80)
    print("SEARCH HOOKS INTEGRATION DEMO")
    print("Brave Search + Legal Corpus RAG for Adversarial Testing and Mediation")
    print("="*80)
    
    try:
        demo_legal_corpus_rag()
    except Exception as e:
        print(f"\nError in legal corpus RAG demo: {e}")
    
    try:
        demo_seed_enrichment()
    except Exception as e:
        print(f"\nError in seed enrichment demo: {e}")
    
    try:
        demo_decision_tree_enhancement()
    except Exception as e:
        print(f"\nError in decision tree enhancement demo: {e}")
    
    try:
        demo_mediator_integration()
    except Exception as e:
        print(f"\nError in mediator integration demo: {e}")
    
    print("\n" + "="*80)
    print("DEMO COMPLETE")
    print("="*80)
    print("\nSummary:")
    print("- Legal Corpus RAG Hook: Provides RAG over legal patterns and terms")
    print("- Search-Enriched Seeds: Automatically enriches seeds with search results")
    print("- Decision Tree Enhancer: Improves trees with legal knowledge")
    print("- Mediator Integration: Adds search capabilities during mediation")
    print("\nThese hooks integrate with:")
    print("- Adversarial testing framework for better test generation")
    print("- Mediation process for legal research during complaint processing")
    print("- Decision tree generation for more relevant questions")
    print()


if __name__ == '__main__':
    main()
