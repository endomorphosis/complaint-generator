"""
Batch 231: Feature test for entity_type_diversity_index.

Tests for:
- OntologyGenerator.entity_type_diversity_index()
"""

import pytest
from ipfs_datasets_py.optimizers.graphrag.ontology_generator import OntologyGenerator


class TestEntityTypeDiversity:
    """Test OntologyGenerator.entity_type_diversity_index() method."""

    def test_diversity_empty_result(self):
        """Empty result returns 0.0."""
        gen = OntologyGenerator()
        result = type('obj', (object,), {'entities': []})()
        assert gen.entity_type_diversity_index(result) == 0.0

    def test_diversity_single_type(self):
        """All same type returns 0.0 (no diversity)."""
        gen = OntologyGenerator()
        entities = [
            type('obj', (object,), {'type': 'Person'})(),
            type('obj', (object,), {'type': 'Person'})(),
            type('obj', (object,), {'type': 'Person'})(),
        ]
        result = type('obj', (object,), {'entities': entities})()
        assert gen.entity_type_diversity_index(result) == 0.0

    def test_diversity_two_types_equal(self):
        """Two types with equal counts."""
        gen = OntologyGenerator()
        entities = [
            type('obj', (object,), {'type': 'Person'})(),
            type('obj', (object,), {'type': 'Person'})(),
            type('obj', (object,), {'type': 'Organization'})(),
            type('obj', (object,), {'type': 'Organization'})(),
        ]
        result = type('obj', (object,), {'entities': entities})()
        diversity = gen.entity_type_diversity_index(result)
        # D = 1 - (2/4)² - (2/4)² = 1 - 0.25 - 0.25 = 0.5
        assert diversity == pytest.approx(0.5, abs=0.001)

    def test_diversity_two_types_unequal(self):
        """Two types with unequal counts."""
        gen = OntologyGenerator()
        entities = [
            type('obj', (object,), {'type': 'Person'})(),
            type('obj', (object,), {'type': 'Person'})(),
            type('obj', (object,), {'type': 'Organization'})(),
        ]
        result = type('obj', (object,), {'entities': entities})()
        diversity = gen.entity_type_diversity_index(result)
        # D = 1 - (2/3)² - (1/3)² = 1 - 4/9 - 1/9 = 4/9 ≈ 0.4444
        assert diversity == pytest.approx(4/9, abs=0.001)

    def test_diversity_three_types(self):
        """Three types with varying counts."""
        gen = OntologyGenerator()
        entities = [
            type('obj', (object,), {'type': 'Person'})(),
            type('obj', (object,), {'type': 'Person'})(),
            type('obj', (object,), {'type': 'Person'})(),
            type('obj', (object,), {'type': 'Organization'})(),
            type('obj', (object,), {'type': 'Organization'})(),
            type('obj', (object,), {'type': 'Location'})(),
        ]
        result = type('obj', (object,), {'entities': entities})()
        diversity = gen.entity_type_diversity_index(result)
        # D = 1 - (3/6)² - (2/6)² - (1/6)²
        expected = 1 - (3/6)**2 - (2/6)**2 - (1/6)**2
        assert diversity == pytest.approx(expected, abs=0.001)

    def test_diversity_all_unique_types(self):
        """All unique types gives maximum diversity."""
        gen = OntologyGenerator()
        entities = [
            type('obj', (object,), {'type': 'Person'})(),
            type('obj', (object,), {'type': 'Organization'})(),
            type('obj', (object,), {'type': 'Location'})(),
            type('obj', (object,), {'type': 'Event'})(),
        ]
        result = type('obj', (object,), {'entities': entities})()
        diversity = gen.entity_type_diversity_index(result)
        # D = 1 - 4*(1/4)² = 1 - 0.25 = 0.75
        assert diversity == pytest.approx(0.75, abs=0.001)

    def test_diversity_bounds(self):
        """Diversity always in [0, 1]."""
        gen = OntologyGenerator()
        test_cases = [
            [],  # empty
            [type('obj', (object,), {'type': 'A'})()],  # single entity
            [type('obj', (object,), {'type': 'A'})() for _ in range(10)],  # all same
            [type('obj', (object,), {'type': f'T{i}'})() for i in range(10)],  # all unique
        ]
        for entities in test_cases:
            result = type('obj', (object,), {'entities': entities})()
            diversity = gen.entity_type_diversity_index(result)
            assert 0.0 <= diversity <= 1.0, f"Diversity {diversity} out of bounds"


# Property-based test
class TestBatch231Properties:
    """Property-based tests for batch 231 features."""

    def test_diversity_bounded(self):
        """Diversity index always in [0, 1] for valid inputs."""
        gen = OntologyGenerator()
        import random
        for _ in range(20):
            n_entities = random.randint(0, 50)
            if n_entities == 0:
                continue
            n_types = random.randint(1, min(10, n_entities))
            type_names = [f"Type{i}" for i in range(n_types)]
            entities = [
                type('obj', (object,), {'type': random.choice(type_names)})()
                for _ in range(n_entities)
            ]
            result = type('obj', (object,), {'entities': entities})()
            diversity = gen.entity_type_diversity_index(result)
            assert 0.0 <= diversity <= 1.0, f"Diversity {diversity} out of bounds"

    def test_diversity_extremes(self):
        """Diversity is 0 for uniform, maximal for all unique."""
        gen = OntologyGenerator()
        # All same type -> D = 0
        uniform_entities = [type('obj', (object,), {'type': 'A'})() for _ in range(10)]
        uniform_result = type('obj', (object,), {'entities': uniform_entities})()
        assert gen.entity_type_diversity_index(uniform_result) == 0.0

        # All unique types -> D approaches 1
        unique_entities = [type('obj', (object,), {'type': f'T{i}'})() for i in range(10)]
        unique_result = type('obj', (object,), {'entities': unique_entities})()
        diversity_unique = gen.entity_type_diversity_index(unique_result)
        # D = 1 - 10*(1/10)² = 1 - 0.1 = 0.9
        assert diversity_unique == pytest.approx(0.9, abs=0.001)
