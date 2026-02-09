"""
Tests for adversarial harness system
"""

import pytest
from adversarial_harness import (
    Complainant,
    ComplaintGenerator,
    ComplaintContext,
    Critic,
    CriticScore,
    AdversarialSession,
    SessionResult,
    AdversarialHarness,
    Optimizer,
    OptimizationReport,
    SeedComplaintLibrary,
    ComplaintTemplate
)


class MockLLMBackend:
    """Mock LLM backend for testing."""
    def __init__(self, response_template=None):
        self.response_template = response_template or "Mock response"
        self.call_count = 0
    
    def __call__(self, prompt):
        self.call_count += 1
        if callable(self.response_template):
            return self.response_template(prompt)
        return self.response_template


class MockMediator:
    """Mock mediator for testing."""
    def __init__(self):
        self.phase_manager = MockPhaseManager()
        self.questions_asked = 0
    
    def start_three_phase_process(self, complaint_text):
        return {
            'phase': 'intake',
            'initial_questions': [
                {'question': 'Can you provide more details?', 'type': 'clarification'}
            ]
        }
    
    def process_denoising_answer(self, question, answer):
        self.questions_asked += 1
        return {
            'converged': self.questions_asked >= 3,
            'next_questions': [{'question': 'Tell me more', 'type': 'follow_up'}]
        }
    
    def get_three_phase_status(self):
        return {
            'current_phase': 'intake',
            'iteration_count': self.questions_asked
        }


class MockPhaseManager:
    """Mock phase manager."""
    def get_phase_data(self, phase, key):
        if key == 'knowledge_graph':
            return MockKnowledgeGraph()
        elif key == 'dependency_graph':
            return MockDependencyGraph()
        return None


class MockKnowledgeGraph:
    """Mock knowledge graph."""
    def summary(self):
        return {'total_entities': 5, 'total_relationships': 3}


class MockDependencyGraph:
    """Mock dependency graph."""
    def summary(self):
        return {'total_nodes': 4, 'total_dependencies': 2}


class TestComplainant:
    """Tests for Complainant class."""
    
    def test_complainant_creation(self):
        """Test complainant can be created."""
        backend = MockLLMBackend()
        complainant = Complainant(backend, personality="cooperative")
        assert complainant.personality == "cooperative"
        assert complainant.context is None
    
    def test_set_context(self):
        """Test setting context."""
        backend = MockLLMBackend()
        complainant = Complainant(backend)
        
        context = ComplaintContext(
            complaint_type="employment_discrimination",
            key_facts={'employer': 'Acme Corp'}
        )
        complainant.set_context(context)
        
        assert complainant.context == context
    
    def test_generate_initial_complaint(self):
        """Test generating initial complaint."""
        backend = MockLLMBackend("I was discriminated against at work.")
        complainant = Complainant(backend)
        
        seed = {'type': 'employment_discrimination', 'summary': 'Fired unfairly'}
        complaint = complainant.generate_initial_complaint(seed)
        
        assert len(complaint) > 0
        assert backend.call_count == 1
    
    def test_respond_to_question(self):
        """Test responding to mediator questions."""
        backend = MockLLMBackend("Yes, it happened last month.")
        complainant = Complainant(backend)
        
        context = ComplaintContext(
            complaint_type="employment_discrimination",
            key_facts={'employer': 'Acme Corp'}
        )
        complainant.set_context(context)
        
        response = complainant.respond_to_question("When did this occur?")
        
        assert len(response) > 0
        assert backend.call_count == 1


class TestCritic:
    """Tests for Critic class."""
    
    def test_critic_creation(self):
        """Test critic can be created."""
        backend = MockLLMBackend()
        critic = Critic(backend)
        assert critic.llm_backend == backend
    
    def test_evaluate_session(self):
        """Test evaluating a session."""
        response_text = """SCORES:
question_quality: 0.8
information_extraction: 0.7
empathy: 0.6
efficiency: 0.75
coverage: 0.7

FEEDBACK:
Good questioning overall.

STRENGTHS:
- Clear questions
- Good follow-ups

WEAKNESSES:
- Could be more empathetic

SUGGESTIONS:
- Add more rapport building
"""
        backend = MockLLMBackend(response_text)
        critic = Critic(backend)
        
        score = critic.evaluate_session(
            "Initial complaint",
            [{'role': 'mediator', 'content': 'Question'}],
            {'status': 'complete'}
        )
        
        assert isinstance(score, CriticScore)
        assert 0.0 <= score.overall_score <= 1.0
        assert score.question_quality == 0.8
    
    def test_fallback_score(self):
        """Test fallback when evaluation fails."""
        backend = MockLLMBackend()
        backend.__call__ = lambda x: None  # Force failure
        critic = Critic(backend)
        
        score = critic._fallback_score([])
        
        assert isinstance(score, CriticScore)
        assert score.overall_score >= 0.0


class TestSeedComplaintLibrary:
    """Tests for SeedComplaintLibrary."""
    
    def test_library_creation(self):
        """Test library can be created with default templates."""
        library = SeedComplaintLibrary()
        assert len(library.templates) > 0
    
    def test_get_template(self):
        """Test getting a template by ID."""
        library = SeedComplaintLibrary()
        template = library.get_template('employment_discrimination_1')
        
        assert isinstance(template, ComplaintTemplate)
        assert template.type == 'employment_discrimination'
    
    def test_list_templates(self):
        """Test listing templates."""
        library = SeedComplaintLibrary()
        all_templates = library.list_templates()
        
        assert len(all_templates) > 0
        
        employment_templates = library.list_templates(category='employment')
        assert all(t.category == 'employment' for t in employment_templates)
    
    def test_get_seed_complaints(self):
        """Test getting seed complaints."""
        library = SeedComplaintLibrary()
        seeds = library.get_seed_complaints(count=5)
        
        assert len(seeds) == 5
        assert all('type' in s for s in seeds)
        assert all('key_facts' in s for s in seeds)


class TestAdversarialSession:
    """Tests for AdversarialSession."""
    
    def test_session_creation(self):
        """Test session can be created."""
        complainant = Complainant(MockLLMBackend())
        mediator = MockMediator()
        critic = Critic(MockLLMBackend())
        
        session = AdversarialSession(
            "test_session",
            complainant,
            mediator,
            critic,
            max_turns=3
        )
        
        assert session.session_id == "test_session"
        assert session.max_turns == 3
    
    def test_session_run(self):
        """Test running a session."""
        complainant_backend = MockLLMBackend("I was discriminated against.")
        complainant = Complainant(complainant_backend)
        
        context = ComplaintContext(
            complaint_type="employment_discrimination",
            key_facts={'employer': 'Test Corp'}
        )
        complainant.set_context(context)
        
        mediator = MockMediator()
        
        critic_backend = MockLLMBackend("""SCORES:
question_quality: 0.8
information_extraction: 0.7
empathy: 0.6
efficiency: 0.75
coverage: 0.7

FEEDBACK: Good session
STRENGTHS:
- Good questions
WEAKNESSES:
- None
SUGGESTIONS:
- None
""")
        critic = Critic(critic_backend)
        
        session = AdversarialSession(
            "test_run",
            complainant,
            mediator,
            critic,
            max_turns=2
        )
        
        seed = {
            'type': 'employment_discrimination',
            'key_facts': {'employer': 'Test Corp'}
        }
        
        result = session.run(seed)
        
        assert isinstance(result, SessionResult)
        assert result.session_id == "test_run"
        assert result.num_questions >= 0


class TestAdversarialHarness:
    """Tests for AdversarialHarness."""
    
    def test_harness_creation(self):
        """Test harness can be created."""
        complainant_backend = MockLLMBackend()
        critic_backend = MockLLMBackend()
        
        def mediator_factory():
            return MockMediator()
        
        harness = AdversarialHarness(
            complainant_backend,
            critic_backend,
            mediator_factory,
            max_parallel=2
        )
        
        assert harness.max_parallel == 2
        assert hasattr(harness, 'seed_library')
    
    def test_get_statistics_empty(self):
        """Test statistics with no results."""
        harness = AdversarialHarness(
            MockLLMBackend(),
            MockLLMBackend(),
            lambda: MockMediator()
        )
        
        stats = harness.get_statistics()
        assert stats['total_sessions'] == 0


class TestOptimizer:
    """Tests for Optimizer."""
    
    def test_optimizer_creation(self):
        """Test optimizer can be created."""
        optimizer = Optimizer()
        assert len(optimizer.history) == 0
    
    def test_analyze_empty_results(self):
        """Test analyzing empty results."""
        optimizer = Optimizer()
        report = optimizer.analyze([])
        
        assert isinstance(report, OptimizationReport)
        assert report.num_sessions_analyzed == 0
    
    def test_analyze_with_results(self):
        """Test analyzing real results."""
        optimizer = Optimizer()
        
        # Create mock results
        mock_results = []
        for i in range(3):
            score = CriticScore(
                overall_score=0.7 + i * 0.05,
                question_quality=0.7,
                information_extraction=0.6,
                empathy=0.8,
                efficiency=0.7,
                coverage=0.65,
                feedback="Test feedback",
                strengths=["Good questions"],
                weaknesses=["Could improve efficiency"],
                suggestions=["Add more follow-ups"]
            )
            
            result = SessionResult(
                session_id=f"session_{i}",
                timestamp="2024-01-01",
                seed_complaint={},
                initial_complaint_text="Test",
                conversation_history=[],
                num_questions=5,
                num_turns=3,
                final_state={},
                critic_score=score,
                success=True
            )
            mock_results.append(result)
        
        report = optimizer.analyze(mock_results)
        
        assert isinstance(report, OptimizationReport)
        assert report.num_sessions_analyzed == 3
        assert 0.0 <= report.average_score <= 1.0
        assert len(report.recommendations) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
