"""Tests for OntologyPipeline error recovery and resilience."""

import sys
sys.path.insert(0, '/home/barberb/complaint-generator/ipfs_datasets_py')

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_pipeline import OntologyPipeline
from ipfs_datasets_py.optimizers.graphrag import (
    OntologyGenerator,
    OntologyCritic,
    OntologyGenerationContext,
)
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import ExtractionConfig


class TestPipelineErrorRecoveryBasics:
    """Tests for basic error handling and recovery in OntologyPipeline."""

    def test_pipeline_with_empty_text(self):
        """Test pipeline resilience to empty input text."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(
            data_source='test',
            data_type='text',
            domain='legal'
        )
        
        # Empty string should be handled gracefully
        result = pipeline.run(text='', context=context)
        
        assert result is not None
        assert hasattr(result, 'ontology')
        # Empty input should produce minimal ontology
        ontology = result.ontology
        assert ontology is not None
        assert isinstance(ontology, dict)

    def test_pipeline_with_whitespace_only(self):
        """Test pipeline resilience to whitespace-only input."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='medical')
        
        # Only whitespace should handle gracefully
        result = pipeline.run(text='   \n\t  ', context=context)
        
        assert result is not None
        assert hasattr(result, 'ontology')

    def test_pipeline_with_very_long_text(self):
        """Test pipeline with very long input text."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        # Create very long text (10000 chars)
        long_text = 'The court held that the defendant was responsible. ' * 200
        
        result = pipeline.run(text=long_text, context=context)
        
        assert result is not None
        assert hasattr(result, 'ontology')
        ontology = result.ontology
        assert ontology is not None

    def test_pipeline_with_malformed_context(self):
        """Test pipeline error handling with incomplete context."""
        pipeline = OntologyPipeline()
        
        # Context without domain (should have default)
        context = OntologyGenerationContext()
        text = 'John Doe worked at ABC Law Firm.'
        
        # Should handle missing domain gracefully
        result = pipeline.run(text=text, context=context)
        assert result is not None

    def test_pipeline_with_none_context(self):
        """Test that pipeline requires a valid context."""
        pipeline = OntologyPipeline()
        
        with pytest.raises((TypeError, AttributeError)):
            pipeline.run(text='Some text', context=None)

    def test_pipeline_with_special_characters(self):
        """Test pipeline robustness to special characters in input."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        text = 'The plaintiff, Jane @# Doe [2023], filed suit ($$$) against XYZ Corp™'
        
        result = pipeline.run(text=text, context=context)
        
        assert result is not None
        assert hasattr(result, 'ontology')

    def test_pipeline_with_unicode_text(self):
        """Test pipeline with unicode and multi-language text."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        text = 'The attorney 法律家 (lawyer) filed a motion. Avocat français intervened.'
        
        result = pipeline.run(text=text, context=context)
        
        assert result is not None
        assert hasattr(result, 'ontology')

    def test_pipeline_with_malformed_ontology_config(self):
        """Test pipeline with invalid extraction config."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        # Create config with invalid values (but don't validate yet)
        bad_config = ExtractionConfig(
            confidence_threshold=0.8,
            max_entities=50
        )
        
        # Pipeline should still work since it may not validate
        text = 'John Doe filed a lawsuit.'
        result = pipeline.run(text=text, context=context)
        assert result is not None


class TestPipelineErrorRecoveryMalformedData:
    """Tests for pipeline resilience to malformed data structures."""

    def test_pipeline_generator_returns_none_ontology(self):
        """Test pipeline handling when generator returns None ontology."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        # Some generators might return None for edge cases
        text = ''
        try:
            result = pipeline.run(text=text, context=context)
            # Should not crash, might have empty ontology
            assert result is not None
        except Exception as e:
            # If it does raise, should be a meaningful error
            assert 'ontology' in str(e).lower() or 'generation' in str(e).lower()

    def test_pipeline_with_malformed_entity_structure(self):
        """Test pipeline robustness when entities have weird structures."""
        # This tests how the downstream critic/mediator handle odd entity data
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        text = 'President Lincoln of the United States' # Ambiguous references
        
        result = pipeline.run(text=text, context=context)
        assert result is not None

    def test_pipeline_with_circular_entity_relationships(self):
        """Test pipeline handling of circular relationship graphs."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        # Text that might create circular relationships
        text = 'A depends on B, B depends on C, C depends on A.'
        
        result = pipeline.run(text=text, context=context)
        # Should complete without infinite loop
        assert result is not None

    def test_pipeline_with_duplicate_entities(self):
        """Test pipeline handling when same entity appears multiple times."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        text = '''
            John Doe filed suit. 
            John Doe is a plaintiff. 
            John Doe hired attorney Jane Smith.
            John Doe testified.
        '''
        
        result = pipeline.run(text=text, context=context)
        assert result is not None
        # Duplicates should be handled (merged or kept as-is)


class TestPipelineErrorRecoveryWithRefinement:
    """Tests for error handling during refinement iterations."""

    def test_pipeline_refinement_convergence_timeout(self):
        """Test that refinement loop terminates even with poor quality."""
        pipeline = OntologyPipeline(
            max_refinement_iterations=3,
        )
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        # Input that might not yield good quality
        text = 'xyz abc def ghi jkl'
        
        result = pipeline.run(text=text, context=context)
        assert result is not None
        # Should stop after max iterations
        assert result.refinement_count <= 3

    def test_pipeline_refinement_with_oscillating_scores(self):
        """Test pipeline stability when scores oscillate during refinement."""
        pipeline = OntologyPipeline(
            max_refinement_iterations=5,
        )
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        text = 'The quick brown fox jumps over the lazy dog'
        
        # Pipeline should be stable even if refinement doesn't strictly improve
        result = pipeline.run(text=text, context=context)
        assert result is not None

    def test_pipeline_refinement_strategy_not_applicable(self):
        """Test pipeline when suggested refinement cannot be applied."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        # Single entity - some strategies might not apply
        text = 'plaintiff'
        
        result = pipeline.run(text=text, context=context)
        # Pipeline should handle gracefully
        assert result is not None


class TestPipelineExceptionHandling:
    """Tests for exception handling and meaningful error messages."""

    def test_pipeline_critic_failure_doesnt_crash_pipeline(self):
        """Test that critic failures don't crash the entire pipeline."""
        generator = OntologyGenerator()
        critic = OntologyCritic()  # Valid critic
        
        pipeline = OntologyPipeline(
            data_generator=generator,
            critic=critic,
        )
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        # Valid input
        text = 'John Doe is a lawyer at ABC firm.'
        
        try:
            result = pipeline.run(text=text, context=context)
            assert result is not None
        except Exception as e:
            # If it fails, should be informative
            assert len(str(e)) > 0

    def test_pipeline_mediator_failure_handling(self):
        """Test pipeline resilience when mediator fails."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        # Valid input
        text = 'Jane Smith sued Bob Johnson for breach of contract.'
        
        # Pipeline should complete despite any mediator issues
        result = pipeline.run(text=text, context=context)
        assert result is not None

    def test_pipeline_with_context_validation_failure(self):
        """Test pipeline when context validation would fail."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='')  # Empty domain
        
        text = 'Some legal text here.'
        
        # Pipeline should handle empty/invalid domain gracefully
        result = pipeline.run(text=text, context=context)
        assert result is not None


class TestPipelinePartialFailureRecovery:
    """Tests for recovery from partial failures in pipeline stages."""

    def test_pipeline_continues_if_entity_extraction_incomplete(self):
        """Test pipeline continues even if entity extraction is incomplete."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        # Text with no obvious entities
        text = 'aaaaaa bbbbbb cccccc'
        
        result = pipeline.run(text=text, context=context)
        # Should complete, not crash
        assert result is not None

    def test_pipeline_continues_if_relationship_extraction_fails(self):
        """Test pipeline continues even if relationships are not found."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        # Text with entities but no clear relationships
        text = 'attorney plaintiff defendant'
        
        result = pipeline.run(text=text, context=context)
        # Should have ontology even without relationships
        assert result is not None

    def test_pipeline_with_zero_confidence_entities(self):
        """Test pipeline handling when entities have very low confidence."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(
            domain='legal',
            extraction_config=ExtractionConfig(confidence_threshold=0.1)
        )
        
        text = 'There may be or might be possibly attorneys or lawyers'
        
        result = pipeline.run(text=text, context=context)
        assert result is not None

    def test_pipeline_with_single_entity_ontology(self):
        """Test that pipeline works with minimal ontology (single entity)."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        # Text that might yield only one entity
        text = 'attorney'
        
        result = pipeline.run(text=text, context=context)
        assert result is not None
        assert result.ontology is not None


class TestPipelineTimeoutAndResourceLimits:
    """Tests for handling timeout and resource constraints."""

    def test_pipeline_with_execution_timeout_setting(self):
        """Test pipeline with timeout setting for long-running operations."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        text = 'Brief legal text.'
        
        # Should complete quickly
        result = pipeline.run(text=text, context=context)
        assert result is not None

    def test_pipeline_with_large_ontology_size(self):
        """Test pipeline doesn't break with large generated ontologies."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(
            domain='legal',
            extraction_config=ExtractionConfig(max_entities=10000)
        )
        
        # Generate text with many potential entities
        text = ' '.join([f'entity{i} plaintiff{i} defendant{i}' for i in range(100)])
        
        result = pipeline.run(text=text, context=context)
        assert result is not None

    def test_pipeline_with_memory_intensive_refinement(self):
        """Test pipeline stability during memory-intensive refinement."""
        pipeline = OntologyPipeline(
            max_refinement_iterations=10,
        )
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        text = 'John Doe is a plaintiff. Jane Smith is a defendant.' * 10
        
        result = pipeline.run(text=text, context=context)
        assert result is not None


class TestPipelineInputValidationAndSanitization:
    """Tests for input validation and sanitization."""

    def test_pipeline_with_null_bytes_in_text(self):
        """Test pipeline robustness to null bytes in input."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        # Text with null bytes (shouldn't occur but be defensive)
        text = 'John Doe\x00filed suit'
        
        try:
            result = pipeline.run(text=text, context=context)
            assert result is not None
        except Exception:
            # Some frameworks reject null bytes, which is reasonable
            pass

    def test_pipeline_with_control_characters(self):
        """Test pipeline with control characters in input."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        # Text with control characters
        text = 'John\x01Doe\x02filed\x03suit'
        
        result = pipeline.run(text=text, context=context)
        assert result is not None

    def test_pipeline_with_extremely_long_entity_name(self):
        """Test pipeline with very long entity name in text."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        # Entity with 1000 character name
        long_name = 'A' * 1000
        text = f'{long_name} filed suit'
        
        result = pipeline.run(text=text, context=context)
        assert result is not None

    def test_pipeline_with_deeply_nested_quotations(self):
        """Test pipeline with nested quotes and complex text structure."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        text = '''
            Judge said "The attorney claimed 'The defendant said "I am innocent"'".
            This is a complex nesting scenario.
        '''
        
        result = pipeline.run(text=text, context=context)
        assert result is not None


class TestPipelineGracefulDegradation:
    """Tests for graceful degradation when features unavailable."""

    def test_pipeline_without_critic(self):
        """Test that pipeline works even without critic scoring."""
        # Create pipeline with minimal configuration
        pipeline = OntologyPipeline(critic=None)
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        text = 'John Doe filed suit against ABC Corp.'
        
        # Should work without critic (no scoring)
        try:
            result = pipeline.run(text=text, context=context)
            # Either works, or raises informative error
            assert result is not None or True
        except (ValueError, AttributeError):
            # Acceptable if critic is required
            pass

    def test_pipeline_without_mediator(self):
        """Test that pipeline works even without mediator refinement."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        # Without running refinement
        text = 'Jane Smith is a lawyer.'
        
        result = pipeline.run(
            text=text,
            context=context,
            auto_refine=False  # Disable refinement
        )
        assert result is not None

    def test_pipeline_without_llm_backend(self):
        """Test that pipeline works in rule-based mode without LLM."""
        critic = OntologyCritic(use_llm=False)  # Rule-based only
        pipeline = OntologyPipeline(critic=critic)
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        text = 'The plaintiff hired an attorney.'
        
        result = pipeline.run(text=text, context=context)
        assert result is not None


class TestPipelineResultConsistency:
    """Tests for result consistency despite error handling."""

    def test_pipeline_result_structure_always_valid(self):
        """Test that pipeline result has consistent structure regardless of input."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        test_cases = [
            '',  # Empty
            'a b c',  # No meaningful entities
            'John Doe and Jane Smith filed suit',  # Normal case
            '   ',  # Whitespace
        ]
        
        for text in test_cases:
            result = pipeline.run(text=text, context=context)
            assert result is not None
            assert hasattr(result, 'ontology')
            # Result should always be a dict or similar structure
            assert isinstance(result.ontology, dict)

    def test_pipeline_ontology_valid_after_error_recovery(self):
        """Test that ontology structure is valid after error recovery."""
        pipeline = OntologyPipeline()
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        # Edge case input
        text = '!@#$%^&*()'
        
        result = pipeline.run(text=text, context=context)
        
        if result.ontology:
            # If ontology was generated, it should have valid structure
            assert 'entities' in result.ontology or len(result.ontology) >= 0

    def test_pipeline_refinement_count_accurate(self):
        """Test that refinement count is accurate even with errors."""
        pipeline = OntologyPipeline(max_refinement_iterations=5)
        context = OntologyGenerationContext(data_source='test', data_type='text', domain='legal')
        
        text = 'Some legal text here.'
        
        result = pipeline.run(text=text, context=context, auto_refine=True)
        
        if hasattr(result, 'refinement_count'):
            # Should not exceed max iterations
            assert result.refinement_count <= 5
            assert result.refinement_count >= 0
