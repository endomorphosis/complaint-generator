"""
Example: Complete Integration of complaint_analysis with Adversarial Harness

This example demonstrates how complaint_analysis modules integrate with
the adversarial testing framework:

1. SeedGenerator creates seeds from complaint types
2. Decision trees guide question generation
3. Prompt templates structure LLM calls
4. Response parsers ingest into statefiles
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from complaint_analysis import (
    SeedGenerator,
    DecisionTreeGenerator,
    PromptLibrary,
    ResponseParserFactory
)
from adversarial_harness import SeedComplaintLibrary


def demo_seed_generation():
    """Demonstrate seed generation from complaint_analysis."""
    print("=" * 60)
    print("1. SEED GENERATION FROM COMPLAINT_ANALYSIS")
    print("=" * 60)
    
    # Create seed generator
    generator = SeedGenerator()
    
    # List available templates
    print(f"\nTotal templates: {len(generator.templates)}")
    
    # Show templates by category
    for category in ['housing', 'employment', 'consumer']:
        templates = generator.list_templates(category=category)
        print(f"\n{category.upper()} templates: {len(templates)}")
        for t in templates[:2]:
            print(f"  - {t.id}: {t.description}")
    
    # Generate a seed complaint
    print("\n" + "-" * 60)
    print("Generating a housing discrimination seed:")
    print("-" * 60)
    
    housing_templates = generator.list_templates(category='housing')
    if housing_templates:
        template = housing_templates[0]
        values = {
            'landlord_name': 'Test Landlord LLC',
            'property_address': '123 Main St',
            'protected_class': 'familial status',
            'discriminatory_action': 'refused rental'
        }
        seed = template.instantiate(values)
        print(f"Type: {seed['type']}")
        print(f"Category: {seed['category']}")
        print(f"Key facts: {seed['key_facts']}")
        print(f"Keywords: {len(seed['keywords'])} keywords")
        print(f"Legal patterns: {len(seed['legal_patterns'])} patterns")


def demo_decision_trees():
    """Demonstrate decision tree generation and usage."""
    print("\n" + "=" * 60)
    print("2. DECISION TREES FOR QUESTION GENERATION")
    print("=" * 60)
    
    # Generate decision tree
    generator = DecisionTreeGenerator()
    tree = generator.generate_tree('housing')
    
    print(f"\nHousing decision tree:")
    print(f"  - Total questions: {len(tree.questions)}")
    print(f"  - Required fields: {len(tree.required_fields)}")
    print(f"  - Optional fields: {len(tree.optional_fields)}")
    print(f"  - Root questions: {len(tree.root_questions)}")
    
    # Simulate question flow
    print("\n" + "-" * 60)
    print("Simulating question flow:")
    print("-" * 60)
    
    answered = set()
    iteration = 1
    
    while True:
        next_questions = tree.get_next_questions(answered)
        if not next_questions:
            break
        
        print(f"\nIteration {iteration}:")
        for q in next_questions[:2]:  # Show first 2 questions
            print(f"  Q: {q.question}")
            print(f"     Field: {q.field_name}, Required: {q.required}")
            answered.add(q.field_name)
        
        iteration += 1
        if iteration > 3:  # Limit for demo
            break


def demo_prompt_templates():
    """Demonstrate prompt template usage."""
    print("\n" + "=" * 60)
    print("3. PROMPT TEMPLATES FOR LLM CALLS")
    print("=" * 60)
    
    library = PromptLibrary()
    
    print(f"\nAvailable templates: {len(library.list_templates())}")
    print("Templates:", ", ".join(library.list_templates()))
    
    # Format a prompt
    print("\n" + "-" * 60)
    print("Example: Extract entities prompt")
    print("-" * 60)
    
    prompt = library.format_prompt('extract_entities', {
        'complaint_text': 'John Doe was discriminated against by Acme Corp on January 15, 2024.'
    })
    
    print(prompt[:500])  # Show first 500 chars
    print("...")


def demo_response_parsing():
    """Demonstrate response parsing and ingestion."""
    print("\n" + "=" * 60)
    print("4. RESPONSE PARSING AND STATEFILE INGESTION")
    print("=" * 60)
    
    # Parse entity response
    parser = ResponseParserFactory.get_parser('entities')
    
    response = '''```json
{
  "entities": [
    {"text": "John Doe", "type": "person", "role": "complainant", "confidence": 0.95},
    {"text": "Acme Corp", "type": "organization", "role": "defendant", "confidence": 0.98},
    {"text": "January 15, 2024", "type": "date", "confidence": 0.99}
  ]
}
```'''
    
    parsed = parser.parse(response)
    
    print(f"\nParsing result:")
    print(f"  Success: {parsed.success}")
    print(f"  Format: {parsed.format_type}")
    print(f"  Entities extracted: {len(parsed.data.get('entities', []))}")
    
    if parsed.success:
        print("\nExtracted entities:")
        for entity in parsed.data['entities']:
            print(f"  - {entity['text']} ({entity['type']}) - confidence: {entity['confidence']}")
    
    # Show ingestion (without actually writing files)
    print("\n" + "-" * 60)
    print("Statefile ingestion:")
    print("-" * 60)
    print("  Would write to: statefiles/session_id_knowledge_graph.json")
    print("  Would append entities to graph structure")


def demo_adversarial_integration():
    """Demonstrate adversarial harness integration."""
    print("\n" + "=" * 60)
    print("5. ADVERSARIAL HARNESS INTEGRATION")
    print("=" * 60)
    
    # Show that adversarial harness now uses complaint_analysis
    library = SeedComplaintLibrary()
    
    print(f"\nSeedComplaintLibrary now uses complaint_analysis")
    print(f"  Total templates available: {len(library.templates)}")
    
    # Get seed complaints
    seeds = library.get_seed_complaints(count=5)
    
    print(f"\nGenerated {len(seeds)} seed complaints:")
    for i, seed in enumerate(seeds, 1):
        print(f"\n  Seed {i}:")
        print(f"    Type: {seed['type']}")
        print(f"    Category: {seed['category']}")
        if 'keywords' in seed:
            print(f"    Keywords: {len(seed['keywords'])} available")
        if 'legal_patterns' in seed:
            print(f"    Legal patterns: {len(seed['legal_patterns'])} available")


def main():
    """Run all demos."""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 58 + "║")
    print("║" + "  complaint_analysis + Adversarial Harness Integration".center(58) + "║")
    print("║" + " " * 58 + "║")
    print("╚" + "=" * 58 + "╝")
    
    try:
        demo_seed_generation()
        demo_decision_trees()
        demo_prompt_templates()
        demo_response_parsing()
        demo_adversarial_integration()
        
        print("\n" + "=" * 60)
        print("INTEGRATION SUMMARY")
        print("=" * 60)
        print("""
The integration provides:

1. DATA-DRIVEN SEEDS: Seeds automatically generated from 12 complaint types
   with keywords and legal patterns built-in.

2. GUIDED QUESTIONS: Decision trees provide structured question sequences
   with dependencies and priorities.

3. STRUCTURED PROMPTS: LLM calls use consistent format with:
   - System prompt (role/context)
   - Return format (expected structure)
   - Warnings (constraints)
   - Payload (actual query)

4. RELIABLE PARSING: Responses validated and ingested into statefiles
   with error handling and schema validation.

5. SEAMLESS INTEGRATION: Adversarial harness now uses complaint_analysis
   data automatically, no manual seed creation needed.

This enables the adversarial testing framework to leverage domain knowledge
from complaint_analysis while testing the mediator's performance.
        """)
        
    except Exception as e:
        print(f"\nError during demo: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
