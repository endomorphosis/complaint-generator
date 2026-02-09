"""
Adversarial Harness Standalone Example

This example demonstrates the adversarial harness without requiring
full mediator dependencies.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from adversarial_harness import (
    Complainant,
    ComplaintContext,
    Critic,
    SeedComplaintLibrary,
    Optimizer
)


class MockLLMBackend:
    """Mock LLM backend for demonstration."""
    def __init__(self, response_type='default'):
        self.response_type = response_type
        self.call_count = 0
    
    def __call__(self, prompt):
        self.call_count += 1
        
        if 'complaint' in prompt.lower() and 'generate' in prompt.lower():
            return """I was working as a senior engineer at TechCorp. Despite 5 years of excellent 
performance reviews, I was passed over for a promotion that went to a less qualified colleague. 
When I raised concerns about discrimination, I was told I was being "too emotional" and shortly 
after was terminated without cause."""
        
        elif 'evaluate' in prompt.lower() or 'SCORES' in prompt:
            return """SCORES:
question_quality: 0.75
information_extraction: 0.70
empathy: 0.65
efficiency: 0.72
coverage: 0.68

FEEDBACK:
The mediator asked relevant questions and gathered key information.

STRENGTHS:
- Asked clear, specific questions
- Followed up on vague responses

WEAKNESSES:
- Could show more empathy
- Missed some timeline details

SUGGESTIONS:
- Begin with acknowledgment of complainant's experience
- Ask more specific date-related questions
"""
        
        elif 'respond' in prompt.lower() or 'response' in prompt.lower():
            if 'when' in prompt.lower() or 'date' in prompt.lower():
                return "This happened about 6 months ago, in September 2023."
            elif 'who' in prompt.lower() or 'witness' in prompt.lower():
                return "My colleague Sarah witnessed some incidents."
            else:
                return "Yes, I can provide more details about that."
        
        return "Mock response"


def main():
    print("=" * 80)
    print("ADVERSARIAL HARNESS STANDALONE EXAMPLE")
    print("=" * 80)
    print()
    
    # Create backends
    complainant_backend = MockLLMBackend('complainant')
    critic_backend = MockLLMBackend('critic')
    
    print("1. COMPLAINANT DEMONSTRATION")
    print("-" * 80)
    
    # Create complainant
    complainant = Complainant(complainant_backend, personality="cooperative")
    
    # Set context
    context = ComplaintContext(
        complaint_type="employment_discrimination",
        key_facts={
            'employer': 'TechCorp',
            'position': 'Senior Engineer',
            'action': 'wrongful termination'
        },
        cooperation_level=0.8
    )
    complainant.set_context(context)
    
    # Generate complaint
    seed = {
        'type': 'employment_discrimination',
        'summary': 'Discrimination and wrongful termination'
    }
    
    complaint = complainant.generate_initial_complaint(seed)
    print(f"Initial Complaint:\n{complaint}\n")
    
    # Respond to questions
    questions = [
        "When did this termination occur?",
        "Were there any witnesses to the discrimination?",
        "Can you describe the discriminatory actions?"
    ]
    
    print("Q&A Session:")
    for i, question in enumerate(questions, 1):
        response = complainant.respond_to_question(question)
        print(f"  Q{i}: {question}")
        print(f"  A{i}: {response}\n")
    
    print()
    
    # 2. CRITIC DEMONSTRATION
    print("2. CRITIC DEMONSTRATION")
    print("-" * 80)
    
    critic = Critic(critic_backend)
    
    # Simulate conversation history
    conversation = [
        {'role': 'complainant', 'type': 'initial_complaint', 'content': complaint},
        {'role': 'mediator', 'type': 'question', 'content': questions[0]},
        {'role': 'complainant', 'type': 'response', 'content': 'About 6 months ago'},
        {'role': 'mediator', 'type': 'question', 'content': questions[1]},
        {'role': 'complainant', 'type': 'response', 'content': 'Yes, Sarah witnessed it'},
    ]
    
    # Evaluate
    score = critic.evaluate_session(
        initial_complaint=complaint,
        conversation_history=conversation,
        final_state={'questions_asked': 3, 'converged': False}
    )
    
    print(f"Overall Score: {score.overall_score:.3f}\n")
    print("Component Scores:")
    print(f"  Question Quality:       {score.question_quality:.3f}")
    print(f"  Information Extraction: {score.information_extraction:.3f}")
    print(f"  Empathy:               {score.empathy:.3f}")
    print(f"  Efficiency:            {score.efficiency:.3f}")
    print(f"  Coverage:              {score.coverage:.3f}\n")
    
    if score.strengths:
        print("Strengths:")
        for strength in score.strengths:
            print(f"  ✓ {strength}")
        print()
    
    if score.weaknesses:
        print("Weaknesses:")
        for weakness in score.weaknesses:
            print(f"  ✗ {weakness}")
        print()
    
    if score.suggestions:
        print("Suggestions:")
        for suggestion in score.suggestions:
            print(f"  → {suggestion}")
        print()
    
    print()
    
    # 3. SEED LIBRARY DEMONSTRATION
    print("3. SEED COMPLAINT LIBRARY")
    print("-" * 80)
    
    library = SeedComplaintLibrary()
    
    print(f"Total templates: {len(library.templates)}")
    print("\nAvailable templates:")
    for template in library.list_templates():
        print(f"  - {template.id} ({template.category})")
    
    print("\nPre-defined seeds:")
    seeds = library.get_seed_complaints(count=3)
    for i, seed in enumerate(seeds, 1):
        print(f"\n  Seed {i}:")
        print(f"    Type: {seed['type']}")
        print(f"    Summary: {seed.get('summary', 'N/A')}")
    
    print()
    
    # 4. OPTIMIZER DEMONSTRATION
    print("4. OPTIMIZER DEMONSTRATION")
    print("-" * 80)
    
    # Create mock session results
    from adversarial_harness import SessionResult, CriticScore
    
    mock_results = []
    for i in range(5):
        mock_score = CriticScore(
            overall_score=0.65 + i * 0.05,
            question_quality=0.7 + i * 0.03,
            information_extraction=0.6 + i * 0.04,
            empathy=0.65,
            efficiency=0.7,
            coverage=0.68,
            feedback="Test feedback",
            strengths=["Clear questions", "Good follow-up"],
            weaknesses=["Could improve empathy"],
            suggestions=["Add more rapport building"]
        )
        
        result = SessionResult(
            session_id=f"session_{i}",
            timestamp="2024-01-01T00:00:00",
            seed_complaint=seeds[0] if seeds else {},
            initial_complaint_text="Test complaint",
            conversation_history=[],
            num_questions=5 + i,
            num_turns=3,
            final_state={},
            critic_score=mock_score,
            duration_seconds=30.0 + i * 5,
            success=True
        )
        mock_results.append(result)
    
    optimizer = Optimizer()
    report = optimizer.analyze(mock_results)
    
    print(f"Sessions Analyzed: {report.num_sessions_analyzed}")
    print(f"Average Score: {report.average_score:.3f}")
    print(f"Trend: {report.score_trend}\n")
    
    print("Component Averages:")
    print(f"  Question Quality:       {report.question_quality_avg:.3f}")
    print(f"  Information Extraction: {report.information_extraction_avg:.3f}")
    print(f"  Empathy:               {report.empathy_avg:.3f}")
    print(f"  Efficiency:            {report.efficiency_avg:.3f}")
    print(f"  Coverage:              {report.coverage_avg:.3f}\n")
    
    if report.priority_improvements:
        print("Priority Improvements:")
        for improvement in report.priority_improvements:
            print(f"  {improvement}")
        print()
    
    if report.recommendations:
        print("Recommendations:")
        for i, rec in enumerate(report.recommendations[:3], 1):
            print(f"  {i}. {rec}")
        print()
    
    print("=" * 80)
    print("EXAMPLE COMPLETE")
    print("=" * 80)
    print()
    print("This example demonstrated:")
    print("  ✓ Complainant generating complaints and responding to questions")
    print("  ✓ Critic evaluating mediator-complainant interactions")
    print("  ✓ Seed library providing diverse complaint scenarios")
    print("  ✓ Optimizer analyzing results and providing recommendations")
    print()
    print("To run full adversarial sessions with real mediator:")
    print("  1. Configure LLM backends with API keys")
    print("  2. Use AdversarialHarness.run_batch()")
    print("  3. Analyze results with Optimizer")
    print("  4. Iterate based on recommendations")
    print()


if __name__ == '__main__':
    main()
