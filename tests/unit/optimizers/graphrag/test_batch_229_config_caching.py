"""
Batch 229: Configuration Caching Optimization Tests

Tests for _resolve_rule_config() caching optimization.
Validates that config parsing results are cached by config object identity
to avoid recomputing stopwords.lower(), allowed_types, etc. on repeated calls.

OPTIMIZATION: Cache config parsing results by config object identity
Expected benefit: 3-5% speedup when same ext_config is reused multiple times
"""

import pytest
import sys
import time
from dataclasses import dataclass
from typing import Any, Optional, Set, Tuple

# Add the project root to path
sys.path.insert(0, '/home/barberb/complaint-generator')

from ipfs_datasets_py.optimizers.graphrag.ontology_generator import OntologyGenerator


@dataclass
class MockExtractionConfig:
    """Mock extraction config for testing."""
    min_entity_length: int = 2
    stopwords: list = None
    allowed_entity_types: list = None
    max_confidence: float = 1.0
    
    def __post_init__(self):
        if self.stopwords is None:
            self.stopwords = []
        if self.allowed_entity_types is None:
            self.allowed_entity_types = []


class TestResolveRuleConfigCaching:
    """Test caching behavior of _resolve_rule_config."""
    
    def setup_method(self):
        """Initialize OntologyGenerator for each test."""
        self.generator = OntologyGenerator(use_ipfs_accelerate=False)
    
    def test_cache_hit_with_same_config_object(self):
        """Test that calling with same config object reuses cached result."""
        config = MockExtractionConfig(
            min_entity_length=3,
            stopwords=['the', 'a', 'an'],
            allowed_entity_types=['Person', 'LocationTest'],
            max_confidence=0.95,
        )
        
        # First call - should compute and cache
        result1 = self.generator._resolve_rule_config(config)
        
        # Second call with same object - should return cached result
        result2 = self.generator._resolve_rule_config(config)
        
        # Results should be identical (same tuple)
        assert result1 == result2
        assert result1 is result2  # Should be the exact same object from cache
        
        # Verify cache was used
        assert id(config) in self.generator._resolve_rule_config_cache
    
    def test_cache_miss_with_different_config_objects(self):
        """Test that different config objects don't share cache."""
        config1 = MockExtractionConfig(
            stopwords=['the', 'a'],
            max_confidence=0.9,
        )
        config2 = MockExtractionConfig(
            stopwords=['this', 'that'],
            max_confidence=0.8,
        )
        
        result1 = self.generator._resolve_rule_config(config1)
        result2 = self.generator._resolve_rule_config(config2)
        
        # Results should be different
        assert result1 != result2
        
        # Both should be cached
        assert id(config1) in self.generator._resolve_rule_config_cache
        assert id(config2) in self.generator._resolve_rule_config_cache
    
    def test_none_config_caching(self):
        """Test that None config is handled and cached correctly."""
        result1 = self.generator._resolve_rule_config(None)
        result2 = self.generator._resolve_rule_config(None)
        
        # Should return consistent defaults
        assert result1 == result2
        assert result1 == (2, set(), set(), 1.0)  # defaults: min_len=2, empty sets, max_conf=1.0
        
        # None should be cached under None key
        assert None in self.generator._resolve_rule_config_cache
    
    def test_stopwords_lowercasing_only_once(self):
        """Test that stopwords are lowercased once and cached."""
        config = MockExtractionConfig(
            stopwords=['The', 'A', 'AND'],  # Mixed case
        )
        
        result1 = self.generator._resolve_rule_config(config)
        min_len1, stopwords1, allowed_types1, max_conf1 = result1
        
        # Stopwords should be lowercased
        assert 'the' in stopwords1
        assert 'a' in stopwords1
        assert 'and' in stopwords1
        assert 'The' not in stopwords1  # Original case should not be present
        
        # Call again - should return cached result with same lowercased stopwords
        result2 = self.generator._resolve_rule_config(config)
        min_len2, stopwords2, allowed_types2, max_conf2 = result2
        
        assert stopwords1 == stopwords2
        assert stopwords1 is stopwords2  # Same object from cache
    
    def test_allowed_types_caching(self):
        """Test that allowed_entity_types are cached correctly."""
        config = MockExtractionConfig(
            allowed_entity_types=['Person', 'Organization', 'Location'],
        )
        
        result1 = self.generator._resolve_rule_config(config)
        min_len1, stopwords1, allowed_types1, max_conf1 = result1
        
        assert 'Person' in allowed_types1
        assert 'Organization' in allowed_types1
        assert 'Location' in allowed_types1
        
        result2 = self.generator._resolve_rule_config(config)
        min_len2, stopwords2, allowed_types2, max_conf2 = result2
        
        # Should return exact same cached objects
        assert allowed_types1 is allowed_types2
    
    def test_cache_size_limit(self):
        """Test that cache respects maxsize limit of 32."""
        # Create 35 different config objects
        configs = [MockExtractionConfig(max_confidence=0.5 + i * 0.01) for i in range(35)]
        
        for config in configs:
            self.generator._resolve_rule_config(config)
        
        # Cache should not exceed 32 entries
        assert len(self.generator._resolve_rule_config_cache) <= 32
    
    def test_config_attribute_extraction(self):
        """Test that all config attributes are extracted correctly."""
        config = MockExtractionConfig(
            min_entity_length=5,
            stopwords=['skip', 'this'],
            allowed_entity_types=['Type1', 'Type2'],
            max_confidence=0.75,
        )
        
        min_len, stopwords, allowed_types, max_conf = self.generator._resolve_rule_config(config)
        
        assert min_len == 5
        assert stopwords == {'skip', 'this'}
        assert allowed_types == {'Type1', 'Type2'}
        assert max_conf == 0.75
    
    def test_type_conversion_errors_handled(self):
        """Test that type conversion errors are handled gracefully."""
        config = MockExtractionConfig(
            min_entity_length="invalid",  # Should become 2 (default)
            max_confidence="not_a_float",  # Should become 1.0 (default)
        )
        
        min_len, stopwords, allowed_types, max_conf = self.generator._resolve_rule_config(config)
        
        # Should use defaults when conversion fails
        assert min_len == 2
        assert max_conf == 1.0
    
    def test_empty_stopwords_list(self):
        """Test that empty stopwords list results in empty set."""
        config = MockExtractionConfig(stopwords=[])
        
        min_len, stopwords, allowed_types, max_conf = self.generator._resolve_rule_config(config)
        
        assert stopwords == set()
    
    def test_none_stopwords_attribute(self):
        """Test that None stopwords attribute is handled."""
        config = MockExtractionConfig(stopwords=None)
        
        min_len, stopwords, allowed_types, max_conf = self.generator._resolve_rule_config(config)
        
        assert stopwords == set()
    
    def test_special_characters_in_stopwords(self):
        """Test stopwords with special characters and unicode."""
        config = MockExtractionConfig(
            stopwords=['café', 'naïve', 'über', '日本語'],
        )
        
        min_len, stopwords, allowed_types, max_conf = self.generator._resolve_rule_config(config)
        
        # All should be lowercased (or unchanged if already lowercase)
        assert 'café' in stopwords
        assert 'naïve' in stopwords
        assert 'über' in stopwords
        assert '日本語' in stopwords
    
    def test_duplicate_stopwords_deduplication(self):
        """Test that duplicate stopwords are deduplicated in set."""
        config = MockExtractionConfig(
            stopwords=['the', 'the', 'a', 'a', 'The', 'A'],
        )
        
        min_len, stopwords, allowed_types, max_conf = self.generator._resolve_rule_config(config)
        
        # Set should deduplicate and lowercase
        assert len(stopwords) == 2  # Only 'the' and 'a'
        assert 'the' in stopwords
        assert 'a' in stopwords
    
    def test_cache_persistence_across_calls(self):
        """Test that cache persists and speeds up repeated calls."""
        config = MockExtractionConfig(
            stopwords=['word1', 'word2', 'word3'] * 10,  # Larger list
        )
        
        # First call - compute and cache
        start1 = time.perf_counter()
        result1 = self.generator._resolve_rule_config(config)
        time1 = time.perf_counter() - start1
        
        # Second call - should use cache (much faster)
        start2 = time.perf_counter()
        result2 = self.generator._resolve_rule_config(config)
        time2 = time.perf_counter() - start2
        
        # Results should be identical
        assert result1 == result2
        
        # Cache hit should be faster (or at least not slower)
        # Note: Can't rely on timing in tests, but verify same result at least
        assert result1 is result2
    
    def test_integration_with_extract_entities(self):
        """Test that config caching integrates properly with extract_entities."""
        config = MockExtractionConfig(
            min_entity_length=3,
            stopwords=['the'],
            allowed_entity_types=['LegalConcept'],
        )
        
        # Create a context with the config
        from ipfs_datasets_py.optimizers.graphrag.ontology_generator import OntologyGenerationContext
        
        context = OntologyGenerationContext(
            extraction_config=config,
            domain='legal',
        )
        
        # Call extract_entities which should use _resolve_rule_config internally
        result = self.generator.extract_entities(
            "This is a legal document with important clauses.",
            context
        )
        
        # Should have cached the config
        assert id(config) in self.generator._resolve_rule_config_cache
        
        # Calling again with same context should use cache
        result2 = self.generator.extract_entities(
            "Another legal document with different content.",
            context
        )
        
        # Config cache entry should still exist
        assert id(config) in self.generator._resolve_rule_config_cache


class TestConfigCachingEdgeCases:
    """Test edge cases and boundary conditions for caching."""
    
    def setup_method(self):
        """Initialize OntologyGenerator for each test."""
        self.generator = OntologyGenerator(use_ipfs_accelerate=False)
    
    def test_missing_attributes_use_defaults(self):
        """Test that missing config attributes use appropriate defaults."""
        class MinimalConfig:
            pass
        
        config = MinimalConfig()
        
        min_len, stopwords, allowed_types, max_conf = self.generator._resolve_rule_config(config)
        
        # Should use all defaults
        assert min_len == 2
        assert stopwords == set()
        assert allowed_types == set()
        assert max_conf == 1.0
    
    def test_large_stopwords_list(self):
        """Test performance with large stopwords list."""
        large_stopwords = [f"word{i}" for i in range(1000)]
        config = MockExtractionConfig(stopwords=large_stopwords)
        
        start = time.perf_counter()
        result = self.generator._resolve_rule_config(config)
        elapsed = time.perf_counter() - start
        
        # Should complete quickly (under 100ms)
        assert elapsed < 0.1
        
        min_len, stopwords, allowed_types, max_conf = result
        assert len(stopwords) == 1000
    
    def test_float_max_confidence_boundaries(self):
        """Test max_confidence float conversion."""
        test_cases = [
            (0.0, 0.0),
            (0.5, 0.5),
            (1.0, 1.0),
            ("0.75", 0.75),
            ("invalid", 1.0),  # Default on error
            (1.5, 1.5),  # Allows values > 1.0
        ]
        
        for input_val, expected in test_cases:
            config = MockExtractionConfig(max_confidence=input_val)
            min_len, stopwords, allowed_types, max_conf = self.generator._resolve_rule_config(config)
            assert max_conf == expected
    
    def test_min_length_conversion_edge_cases(self):
        """Test min_entity_length integer conversion."""
        test_cases = [
            (0, 0),
            (1, 1),
            (2, 2),
            (100, 100),
            ("5", 5),
            ("invalid", 2),  # Default on error
            (-1, -1),  # Allows negative
        ]
        
        for input_val, expected in test_cases:
            config = MockExtractionConfig(min_entity_length=input_val)
            min_len, stopwords, allowed_types, max_conf = self.generator._resolve_rule_config(config)
            assert min_len == expected


class TestCacheKeyGeneration:
    """Test cache key generation by object identity."""
    
    def setup_method(self):
        """Initialize OntologyGenerator for each test."""
        self.generator = OntologyGenerator(use_ipfs_accelerate=False)
    
    def test_identical_configs_different_objects_not_cached_together(self):
        """Test that configs with identical values but different objects are cached separately."""
        config1 = MockExtractionConfig(stopwords=['the', 'a'])
        config2 = MockExtractionConfig(stopwords=['the', 'a'])  # Same values, different object
        
        result1 = self.generator._resolve_rule_config(config1)
        result2 = self.generator._resolve_rule_config(config2)
        
        # Results should have same values
        assert result1[1] == result2[1]  # Same stopwords set content
        
        # But should be different cache entries
        assert id(config1) != id(config2)
        assert id(config1) in self.generator._resolve_rule_config_cache
        assert id(config2) in self.generator._resolve_rule_config_cache
        
        # And potentially different object instances (depending on cache)
        # We should have 2 cache entries
        assert len(self.generator._resolve_rule_config_cache) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
