"""
Tests for Search and Legal Corpus Hooks

Tests both the legal corpus RAG hooks and the adversarial harness search hooks.
"""

import sys
import os
import pytest
from unittest.mock import Mock, MagicMock, patch

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mediator.legal_corpus_hooks import LegalCorpusRAGHook
from adversarial_harness.search_hooks import (
    SearchEnrichedSeedGenerator,
    DecisionTreeEnhancer,
    MediatorSearchIntegration
)


class TestLegalCorpusRAGHook:
    """Tests for LegalCorpusRAGHook."""
    
    @pytest.fixture
    def mock_mediator(self):
        """Create a mock mediator."""
        mediator = Mock()
        mediator.log = Mock()
        return mediator
    
    @pytest.fixture
    def hook(self, mock_mediator):
        """Create a LegalCorpusRAGHook instance."""
        return LegalCorpusRAGHook(mock_mediator)
    
    def test_initialization(self, hook, mock_mediator):
        """Test hook initialization."""
        assert hook.mediator == mock_mediator
        assert hasattr(hook, 'legal_patterns')
        assert hasattr(hook, 'legal_terms')
    
    def test_search_legal_corpus(self, hook):
        """Test searching the legal corpus."""
        results = hook.search_legal_corpus("discrimination", max_results=10)
        assert isinstance(results, list)
        # Results may be empty if complaint_analysis not available
        if results:
            assert 'type' in results[0]
            assert 'content' in results[0]
            assert 'score' in results[0]
    
    def test_search_with_complaint_type(self, hook):
        """Test searching with specific complaint type."""
        results = hook.search_legal_corpus(
            "employment", 
            complaint_type="employment_discrimination",
            max_results=5
        )
        assert isinstance(results, list)
    
    def test_retrieve_relevant_laws(self, hook):
        """Test retrieving relevant laws for claims."""
        claims = ["discrimination at work", "wrongful termination"]
        laws = hook.retrieve_relevant_laws(claims)
        assert isinstance(laws, list)
        # May be empty if no matches found
        if laws:
            assert 'claim' in laws[0]
            assert 'legal_reference' in laws[0]
    
    def test_enrich_decision_tree(self, hook):
        """Test enriching a decision tree."""
        tree_data = {
            'complaint_type': 'employment_discrimination',
            'category': 'employment',
            'description': 'Employment discrimination complaint',
            'questions': {
                'q1': {
                    'question': 'When did the discrimination occur?',
                    'field_name': 'date',
                    'keywords': ['discrimination', 'date']
                }
            }
        }
        
        enriched = hook.enrich_decision_tree('employment_discrimination', tree_data)
        assert isinstance(enriched, dict)
        assert 'complaint_type' in enriched
        # May have legal_context if complaint_analysis available
    
    def test_get_legal_requirements(self, hook):
        """Test getting legal requirements."""
        requirements = hook.get_legal_requirements('employment_discrimination')
        assert isinstance(requirements, dict)
        # May be empty if complaint type not found
    
    def test_suggest_questions(self, hook):
        """Test suggesting additional questions."""
        existing = ["What is your name?", "When did this happen?"]
        suggestions = hook.suggest_questions('employment_discrimination', existing)
        assert isinstance(suggestions, list)
        # May be empty if complaint type not found
        if suggestions:
            assert 'question' in suggestions[0]
            assert 'keyword' in suggestions[0]


class TestSearchEnrichedSeedGenerator:
    """Tests for SearchEnrichedSeedGenerator."""
    
    @pytest.fixture
    def generator(self):
        """Create a SearchEnrichedSeedGenerator instance."""
        return SearchEnrichedSeedGenerator()
    
    @pytest.fixture
    def seed_template(self):
        """Create a sample seed template."""
        return {
            'complaint_type': 'employment_discrimination',
            'category': 'employment',
            'description': 'Discrimination in the workplace',
            'required_fields': ['employer', 'discrimination_type', 'date'],
            'optional_fields': ['witnesses', 'evidence']
        }
    
    def test_initialization(self, generator):
        """Test generator initialization."""
        assert hasattr(generator, 'mock_mediator')
        assert hasattr(generator, 'web_hook')
        assert hasattr(generator, 'legal_hook')
    
    def test_enrich_seed_with_search(self, generator, seed_template):
        """Test enriching seed with search (may not have real search)."""
        enriched = generator.enrich_seed_with_search(seed_template, use_brave=True)
        assert isinstance(enriched, dict)
        assert 'complaint_type' in enriched
        assert 'description' in enriched
    
    def test_enrich_seed_with_legal_corpus(self, generator, seed_template):
        """Test enriching seed with legal corpus."""
        enriched = generator.enrich_seed_with_legal_corpus(seed_template)
        assert isinstance(enriched, dict)
        assert 'complaint_type' in enriched
        # May have legal_context if available
    
    def test_enrich_seed_full(self, generator, seed_template):
        """Test full seed enrichment."""
        enriched = generator.enrich_seed_full(seed_template)
        assert isinstance(enriched, dict)
        assert 'enriched' in enriched
        assert enriched['enriched'] is True
        assert 'enriched_at' in enriched


class TestDecisionTreeEnhancer:
    """Tests for DecisionTreeEnhancer."""
    
    @pytest.fixture
    def enhancer(self):
        """Create a DecisionTreeEnhancer instance."""
        return DecisionTreeEnhancer()
    
    @pytest.fixture
    def tree_data(self):
        """Create sample tree data."""
        return {
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
    
    def test_initialization(self, enhancer):
        """Test enhancer initialization."""
        assert hasattr(enhancer, 'mock_mediator')
        assert hasattr(enhancer, 'legal_hook')
    
    def test_enhance_decision_tree(self, enhancer, tree_data):
        """Test enhancing a decision tree."""
        enhanced = enhancer.enhance_decision_tree(tree_data)
        assert isinstance(enhanced, dict)
        assert 'complaint_type' in enhanced
        assert 'questions' in enhanced
    
    def test_suggest_additional_questions(self, enhancer, tree_data):
        """Test suggesting additional questions."""
        suggestions = enhancer.suggest_additional_questions(tree_data)
        assert isinstance(suggestions, list)
        # May be empty if no suggestions
    
    def test_validate_question_relevance(self, enhancer):
        """Test validating question relevance."""
        result = enhancer.validate_question_relevance(
            "What type of discrimination occurred?",
            "employment_discrimination"
        )
        assert isinstance(result, dict)
        assert 'valid' in result
        assert 'relevance_score' in result
        assert isinstance(result['valid'], bool)
        assert isinstance(result['relevance_score'], float)


class TestMediatorSearchIntegration:
    """Tests for MediatorSearchIntegration."""
    
    @pytest.fixture
    def mock_mediator(self):
        """Create a mock mediator."""
        mediator = Mock()
        mediator.log = Mock()
        return mediator
    
    @pytest.fixture
    def integration(self, mock_mediator):
        """Create a MediatorSearchIntegration instance."""
        return MediatorSearchIntegration(mock_mediator)
    
    def test_initialization(self, integration, mock_mediator):
        """Test integration initialization."""
        assert integration.mediator == mock_mediator
        assert hasattr(integration, 'web_hook')
        assert hasattr(integration, 'legal_hook')
    
    def test_enhance_question_generation(self, integration):
        """Test enhancing question generation."""
        current_questions = ["What is your name?", "Where did this happen?"]
        suggestions = integration.enhance_question_generation(
            "employment_discrimination",
            current_questions
        )
        assert isinstance(suggestions, list)
    
    def test_search_for_precedents(self, integration):
        """Test searching for precedents."""
        precedents = integration.search_for_precedents("age discrimination")
        assert isinstance(precedents, list)
        # May be empty if Brave search not available
    
    def test_enrich_knowledge_graph(self, integration):
        """Test enriching knowledge graph."""
        graph_data = {
            'entities': [
                {'id': 'e1', 'type': 'person', 'name': 'John Doe'}
            ],
            'relationships': []
        }
        
        enriched = integration.enrich_knowledge_graph(
            graph_data,
            "employment_discrimination"
        )
        assert isinstance(enriched, dict)
        assert 'entities' in enriched


class TestIntegration:
    """Integration tests for all search hooks working together."""
    
    def test_full_workflow(self):
        """Test a complete workflow using all hooks."""
        # Create mock mediator
        mediator = Mock()
        mediator.log = Mock()
        
        # Initialize hooks
        legal_hook = LegalCorpusRAGHook(mediator)
        seed_gen = SearchEnrichedSeedGenerator()
        tree_enhancer = DecisionTreeEnhancer()
        med_integration = MediatorSearchIntegration(mediator)
        
        # Test workflow
        assert legal_hook is not None
        assert seed_gen is not None
        assert tree_enhancer is not None
        assert med_integration is not None
        
        # Basic operations should not raise errors
        legal_hook.search_legal_corpus("discrimination")
        
        seed_template = {
            'complaint_type': 'employment_discrimination',
            'description': 'Test complaint'
        }
        enriched_seed = seed_gen.enrich_seed_full(seed_template)
        assert isinstance(enriched_seed, dict)
        
        tree_data = {
            'complaint_type': 'employment_discrimination',
            'questions': {}
        }
        enhanced_tree = tree_enhancer.enhance_decision_tree(tree_data)
        assert isinstance(enhanced_tree, dict)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
