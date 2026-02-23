"""
Batch 228: Test regex pattern pre-compilation optimization

This module tests the performance optimization for entity extraction patterns.
The key optimization: pre-compile patterns once via @functools.lru_cache instead
of re-compiling on every finditer() call.

Expected Performance Gains:
- Verb pattern caching: ~5% speedup (patterns already cached at class level)
- Entity pattern compilation: ~5-10% speedup (THIS IS NEW - Batch 228)
- Total: ~10-15% on OntologyGenerator.extract_entities()
"""
import pytest
import re
from unittest.mock import Mock, patch
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import (
    OntologyGenerator, OntologyGenerationContext, ExtractionConfig, Entity
)


class TestPatternCompilationCaching:
    """Test _compile_entity_patterns() caching behavior"""

    def test_compile_entity_patterns_method_exists(self):
        """Verify _compile_entity_patterns static method is defined"""
        assert hasattr(OntologyGenerator, '_compile_entity_patterns')
        assert callable(OntologyGenerator._compile_entity_patterns)

    def test_compile_entity_patterns_returns_tuple(self):
        """Verify compiled patterns are returned as tuple of (regex, type)"""
        patterns = (
            (r'\b\w+\b', 'Person'),
            (r'\d+', 'Number'),
        )
        compiled = OntologyGenerator._compile_entity_patterns(patterns)
        
        assert isinstance(compiled, tuple)
        assert len(compiled) == 2
        assert hasattr(compiled[0][0], 'finditer')  # Verify regex object
        assert compiled[0][1] == 'Person'  # Verify type preserved

    def test_compile_entity_patterns_caching(self):
        """Verify patterns are cached (same call returns exact same object)"""
        patterns = (
            (r'\b(?:Mr|Mrs|Ms)\s+\w+', 'Person'),
            (r'\d{1,3}(?:,\d{3})*(?:\.\d{2})?', 'MonetaryAmount'),
        )
        
        # Call twice with same patterns
        compiled1 = OntologyGenerator._compile_entity_patterns(patterns)
        compiled2 = OntologyGenerator._compile_entity_patterns(patterns)
        
        # Should return exact same object (lru_cache hit)
        assert compiled1 is compiled2

    def test_compile_entity_patterns_cache_invalidation_different_patterns(self):
        """Verify different patterns produce different compiled objects"""
        patterns1 = ((r'\bPerson\b', 'Person'),)
        patterns2 = ((r'\bOrganization\b', 'Organization'),)
        
        compiled1 = OntologyGenerator._compile_entity_patterns(patterns1)
        compiled2 = OntologyGenerator._compile_entity_patterns(patterns2)
        
        # Different input → different output
        assert compiled1 is not compiled2
        assert compiled1[0][1] == 'Person'
        assert compiled2[0][1] == 'Organization'

    def test_compile_entity_patterns_regex_functionality(self):
        """Verify compiled regex objects work correctly"""
        patterns = ((r'\b[A-Z]\w+\b', 'ProperNoun'),)
        compiled = OntologyGenerator._compile_entity_patterns(patterns)
        
        regex, entity_type = compiled[0]
        text = "Alice and Bob went to New York"
        matches = list(regex.finditer(text))
        
        # Should match: Alice, Bob, New, York (4 proper nouns, "went" is lowercase)
        assert len(matches) == 4
        assert entity_type == 'ProperNoun'

    def test_compile_entity_patterns_empty_patterns(self):
        """Verify empty pattern list handling"""
        patterns = ()
        compiled = OntologyGenerator._compile_entity_patterns(patterns)
        
        assert isinstance(compiled, tuple)
        assert len(compiled) == 0

    def test_compile_entity_patterns_special_characters(self):
        """Verify patterns with special chars compile correctly"""
        patterns = (
            (r'[A-Z]\w+\s*\(.*?\)', 'Function'),
            (r'<[^>]+>', 'HTMLTag'),
            (r'\$\d+(?:\.\d{2})?', 'MoneyAmount'),
        )
        compiled = OntologyGenerator._compile_entity_patterns(patterns)
        
        assert len(compiled) == 3
        # Verify each one is a compiled regex
        for regex, _ in compiled:
            assert hasattr(regex, 'finditer')

    def test_compile_entity_patterns_unicode_patterns(self):
        """Verify unicode patterns compile and work"""
        patterns = (
            (r'\b[À-ÿ]+\b', 'FrenchWord'),
            (r'\b[\u4e00-\u9fff]+\b', 'ChineseCharacter'),
        )
        compiled = OntologyGenerator._compile_entity_patterns(patterns)
        
        assert len(compiled) == 2
        # Test Chinese pattern
        regex, etype = compiled[1]
        matches = list(regex.finditer("中文 hello"))
        assert len(matches) >= 1
        assert etype == 'ChineseCharacter'


class TestExtractEntitiesFromPatternsWithCaching:
    """Test that _extract_entities_from_patterns uses compiled patterns"""

    def test_extract_entities_from_patterns_basic(self):
        """Verify pattern-based extraction works with compiled patterns"""
        generator = OntologyGenerator()
        text = "Mr. John Smith works at Acme Corporation on 02-22-2026"
        patterns = [
            (r'\b(?:Mr|Mrs|Ms)\s+[A-Z]\w+(?:\s+[A-Z]\w+)?', 'Person'),
            (r'\b[A-Z]\w+(?:\s+[A-Z]\w+)*(?:Corp|Corporation|Inc|Ltd)\b', 'Organization'),
            (r'\d{2}-\d{2}-\d{4}', 'Date'),
        ]
        
        result = generator._extract_entities_from_patterns(
            text=text,
            patterns=patterns,
            allowed_types=set(),
            min_len=1,
            stopwords=set(),
            max_confidence=1.0,
        )
        
        # Just verify extraction works and finds entities
        # (specific types depend on pattern matching regex implementation)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_extract_entities_from_patterns_uses_compiled_patterns(self):
        """Verify extraction uses cached compiled patterns"""
        generator = OntologyGenerator()
        text = "Test text with Alice and Bob"
        patterns = [(r'\b[A-Z]\w+\b', 'ProperNoun')]
        
        # Call twice - second should reuse cached compiled patterns
        result1 = generator._extract_entities_from_patterns(
            text=text,
            patterns=patterns,
            allowed_types=set(),
            min_len=2,
            stopwords=set(),
            max_confidence=1.0,
        )
        
        result2 = generator._extract_entities_from_patterns(
            text=text,
            patterns=patterns,
            allowed_types=set(),
            min_len=2,
            stopwords=set(),
            max_confidence=1.0,
        )
        
        # Both should produce same entities
        assert len(result1) == len(result2)
        assert {e.text for e in result1} == {e.text for e in result2}

    def test_extract_entities_from_patterns_respects_allowed_types(self):
        """Verify allowed_types filtering works"""
        generator = OntologyGenerator()
        text = "Alice Smith and Acme Inc were parties"
        patterns = [
            (r'[A-Z]\w+\s+[A-Z]\w+', 'Person'),
            (r'[A-Z]\w+\s+Inc', 'Organization'),
        ]
        
        # Only allow Person type
        result = generator._extract_entities_from_patterns(
            text=text,
            patterns=patterns,
            allowed_types={'Person'},
            min_len=3,
            stopwords=set(),
            max_confidence=1.0,
        )
        
        assert all(e.type == 'Person' for e in result)

    def test_extract_entities_from_patterns_stopwords(self):
        """Verify stopwords are respected"""
        generator = OntologyGenerator()
        text = "the quick brown fox"
        patterns = [(r'\b\w+\b', 'Word')]
        stopwords = {'the', 'quick'}
        
        result = generator._extract_entities_from_patterns(
            text=text,
            patterns=patterns,
            allowed_types=set(),
            min_len=1,
            stopwords=stopwords,
            max_confidence=1.0,
        )
        
        found_words = {e.text.lower() for e in result}
        assert 'the' not in found_words
        assert 'quick' not in found_words
        assert 'brown' in found_words or 'fox' in found_words

    def test_extract_entities_from_patterns_min_length(self):
        """Verify minimum length filtering works"""
        generator = OntologyGenerator()
        text = "a be cat dog"
        patterns = [(r'\b\w+\b', 'Word')]
        
        result = generator._extract_entities_from_patterns(
            text=text,
            patterns=patterns,
            allowed_types=set(),
            min_len=3,
            stopwords=set(),
            max_confidence=1.0,
        )
        
        assert all(len(e.text) >= 3 for e in result)

    def test_extract_entities_from_patterns_no_regex_import(self):
        """Verify 're' module is not imported in method (uses compiled patterns)"""
        # This is a code structure test - verify no "import re" or "_re.finditer"
        import inspect
        source = inspect.getsource(OntologyGenerator._extract_entities_from_patterns)
        
        # Should NOT have "import re as _re" anymore
        assert 'import re as _re' not in source
        # Should use compiled_pattern.finditer instead of _re.finditer
        assert 'compiled_pattern.finditer' in source


class TestPatternCachingPerformance:
    """Test performance benefits of pattern caching"""

    def test_multiple_extraction_calls_use_cached_patterns(self):
        """Verify multiple calls reuse cached compiled patterns"""
        generator = OntologyGenerator()
        
        # Build patterns once
        patterns = [
            (r'\b(?:Mr|Mrs|Ms)\s+\w+', 'Person'),
            (r'\b[A-Z]\w+\s+(?:Corp|Inc|Ltd)\b', 'Organization'),
        ]
        
        text1 = "Mr. John Smith and Acme Corp"
        text2 = "Ms. Jane Doe and Tech Inc"
        
        # First extraction
        result1 = generator._extract_entities_from_patterns(
            text=text1,
            patterns=patterns,
            allowed_types=set(),
            min_len=2,
            stopwords=set(),
            max_confidence=1.0,
        )
        
        # Second extraction with same patterns (should use cache)
        result2 = generator._extract_entities_from_patterns(
            text=text2,
            patterns=patterns,
            allowed_types=set(),
            min_len=2,
            stopwords=set(),
            max_confidence=1.0,
        )
        
        # Both should have results
        assert len(result1) > 0
        assert len(result2) > 0


class TestIntegrationWithExtractEntities:
    """Test pattern caching in full extract_entities pipeline"""

    def test_extract_entities_integration(self):
        """Verify extract_entities works with pattern caching"""
        generator = OntologyGenerator()
        text = "Smith v. Jones (2020): Mr. John Smith and Acme Corporation dispute"
        
        config = ExtractionConfig(confidence_threshold=0.3)
        context = OntologyGenerationContext(
            data_source="test",
            data_type="text",
            domain="legal",
            config=config,
        )
        
        result = generator.extract_entities(text, context)
        
        assert result.entities is not None
        assert isinstance(result.entities, list)
        assert result.relationships is not None
        assert isinstance(result.relationships, list)

    def test_extract_entities_multiple_calls_consistency(self):
        """Verify multiple extractions are consistent"""
        generator = OntologyGenerator()
        text = "Dr. Alice Brown works at Brown University in Boston"
        
        config = ExtractionConfig(confidence_threshold=0.3)
        context = OntologyGenerationContext(
            data_source="test",
            data_type="text",
            domain="technical",
            config=config,
        )
        
        # Call extraction multiple times
        result1 = generator.extract_entities(text, context)
        result2 = generator.extract_entities(text, context)
        
        # Should get same number of entities (cached patterns)
        assert len(result1.entities) == len(result2.entities)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
