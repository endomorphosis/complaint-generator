"""Unit tests for GraphRAG OntologyOptimizer pure helper methods.

These tests cover deterministic, pure functions in OntologyOptimizer that
don't require mocking or external dependencies.

Note: The _identify_patterns() method requires structured result objects with
multiple attributes. For simpler integration testing, we focus on pure
single-responsibility helpers instead.
"""

import pytest
from unittest.mock import Mock, MagicMock
from ipfs_datasets_py.optimizers.graphrag.ontology_optimizer import (
    OntologyOptimizer,
    OptimizationReport,
)


class TestOntologyOptimizerHelpers:
    """Test suite for OntologyOptimizer pure helper methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.optimizer = OntologyOptimizer()

    def test_determine_trend_baseline(self):
        """Test _determine_trend returns 'baseline' when no history."""
        trend = self.optimizer._determine_trend(0.75)
        assert trend == 'baseline'

    def test_determine_trend_improving(self):
        """Test _determine_trend detects improvement."""
        # Add initial report
        report1 = OptimizationReport(average_score=0.70, trend='baseline')
        self.optimizer._history.append(report1)
        
        # Compute trend for higher score (> 0.05 increase)
        trend = self.optimizer._determine_trend(0.76)
        assert trend == 'improving'

    def test_determine_trend_degrading(self):
        """Test _determine_trend detects degradation."""
        # Add initial report
        report1 = OptimizationReport(average_score=0.80, trend='baseline')
        self.optimizer._history.append(report1)
        
        # Compute trend for lower score (> 0.05 decrease)
        trend = self.optimizer._determine_trend(0.74)
        assert trend == 'degrading'

    def test_determine_trend_stable(self):
        """Test _determine_trend detects stable score."""
        # Add initial report
        report1 = OptimizationReport(average_score=0.75, trend='baseline')
        self.optimizer._history.append(report1)
        
        # Compute trend within 0.05 threshold
        trend = self.optimizer._determine_trend(0.76)
        assert trend == 'stable'

    def test_compute_std_single_value(self):
        """Test _compute_std returns 0 for single value."""
        std = self.optimizer._compute_std([0.75])
        assert std == 0.0

    def test_compute_std_empty_list(self):
        """Test _compute_std returns 0 for empty list."""
        std = self.optimizer._compute_std([])
        assert std == 0.0

    def test_compute_std_two_values(self):
        """Test _compute_std computes correctly for two values."""
        # std([0, 2]) = sqrt(1) = 1.0
        std = self.optimizer._compute_std([0.0, 2.0])
        assert std == pytest.approx(1.0, abs=1e-6)

    def test_compute_std_normal_distribution(self):
        """Test _compute_std for normal distribution."""
        # [1, 2, 3, 4, 5] => mean=3, var=2, std=sqrt(2)≈1.414
        std = self.optimizer._compute_std([1.0, 2.0, 3.0, 4.0, 5.0])
        assert std == pytest.approx(1.414, abs=0.01)

    def test_extract_ontology_from_mediator_state(self):
        """Test _extract_ontology extracts from MediatorState-like object."""
        # Mock result with current_ontology attribute
        result = Mock()
        result.current_ontology = {'entities': [{'type': 'PERSON'}]}
        result.critic_scores = [Mock(overall=0.85)]
        
        ontology_dict = self.optimizer._extract_ontology(result)
        
        assert ontology_dict['ontology'] == {'entities': [{'type': 'PERSON'}]}
        assert ontology_dict['score'] == 0.85

    def test_extract_ontology_from_session_result(self):
        """Test _extract_ontology extracts from SessionResult-like object."""
        # Mock result with ontology attribute
        result = Mock()
        result.ontology = {'relationships': [{'type': 'HAS_ATTRIBUTE'}]}
        result.critic_score = Mock(overall=0.72)
        # Remove current_ontology to force fallback path
        delattr(result, 'current_ontology')
        
        ontology_dict = self.optimizer._extract_ontology(result)
        
        assert ontology_dict['ontology'] == {'relationships': [{'type': 'HAS_ATTRIBUTE'}]}
        assert ontology_dict['score'] == 0.72

    def test_extract_ontology_fallback_empty(self):
        """Test _extract_ontology returns empty dict when no ontology found."""
        result = Mock(spec=[])
        ontology_dict = self.optimizer._extract_ontology(result)
        
        assert ontology_dict == {'ontology': {}, 'score': 0.0}

    def test_compute_score_distribution_single_dimension(self):
        """Test _compute_score_distribution aggregates single dimension."""
        # Create mock results with critic_scores (using spec to allow attributes)
        result1 = Mock()
        score1 = Mock()
        score1.completeness = 0.8
        score1.consistency = 0.0
        score1.clarity = 0.0
        score1.granularity = 0.0
        score1.domain_alignment = 0.0
        result1.critic_scores = [score1]
        
        result2 = Mock()
        score2 = Mock()
        score2.completeness = 0.9
        score2.consistency = 0.0
        score2.clarity = 0.0
        score2.granularity = 0.0
        score2.domain_alignment = 0.0
        result2.critic_scores = [score2]
        
        distribution = self.optimizer._compute_score_distribution([result1, result2])
        
        assert distribution['completeness'] == pytest.approx(0.85, abs=0.01)
        assert distribution['consistency'] == 0.0

    def test_compute_score_distribution_all_dimensions(self):
        """Test _compute_score_distribution aggregates all dimensions."""
        result = Mock()
        result.critic_scores = [Mock(
            completeness=0.8,
            consistency=0.75,
            clarity=0.9,
            granularity=0.7,
            domain_alignment=0.85
        )]
        
        distribution = self.optimizer._compute_score_distribution([result])
        
        assert distribution['completeness'] == 0.8
        assert distribution['consistency'] == 0.75
        assert distribution['clarity'] == 0.9
        assert distribution['granularity'] == 0.7
        assert distribution['domain_alignment'] == 0.85

    def test_compute_score_distribution_missing_dimensions(self):
        """Test _compute_score_distribution handles missing dimensions gracefully."""
        result = Mock()
        result.critic_scores = [Mock(completeness=0.8, spec=['completeness'])]
        
        distribution = self.optimizer._compute_score_distribution([result])
        
        # Missing dimensions should default to 0.0
        assert distribution['completeness'] == 0.8
        assert distribution['consistency'] == 0.0
        assert distribution['clarity'] == 0.0

    def test_compute_score_distribution_no_critic_scores(self):
        """Test _compute_score_distribution all zeros when no critic_scores."""
        result = Mock()
        result.critic_scores = []
        
        distribution = self.optimizer._compute_score_distribution([result])
        
        # All dimensions should be 0.0
        for dim in distribution.values():
            assert dim == 0.0

    def test_identify_patterns_empty_results(self):
        """Test _identify_patterns returns defaults for empty results."""
        patterns = self.optimizer._identify_patterns([])
        
        assert patterns['avg_final_score'] == 0.0
        assert patterns['avg_convergence_rounds'] == 0.0
        assert patterns['top_entity_types'] == []
        assert patterns['most_common_weakness'] is None
        assert patterns['session_count'] == 0

    def test_identify_patterns_with_scores(self):
        """Test _identify_patterns extracts scores correctly."""
        result = Mock()
        score = Mock()
        score.overall = 0.85
        score.completeness = 0.9
        score.consistency = 0.8
        score.clarity = 0.85
        score.granularity = 0.8
        score.domain_alignment = 0.85
        result.critic_scores = [score]
        result.current_round = 1
        
        patterns = self.optimizer._identify_patterns([result])
        
        assert patterns['avg_final_score'] == 0.85
        assert patterns['session_count'] == 1

    def test_identify_patterns_with_entity_types(self):
        """Test _identify_patterns identifies entity type distribution."""
        result = Mock()
        score = Mock()
        score.overall = 0.8
        score.completeness = 0.8
        score.consistency = 0.8
        score.clarity = 0.8
        score.granularity = 0.8
        score.domain_alignment = 0.8
        result.critic_scores = [score]
        result.current_ontology = {
            'entities': [
                {'type': 'PERSON'},
                {'type': 'PERSON'},
                {'type': 'ORGANIZATION'},
            ]
        }
        result.current_round = 1
        
        patterns = self.optimizer._identify_patterns([result])
        
        assert 'PERSON' in patterns['top_entity_types']
        assert 'ORGANIZATION' in patterns['top_entity_types']

    def test_identify_patterns_with_relationship_types(self):
        """Test _identify_patterns identifies relationship type distribution."""
        result = Mock()
        score = Mock()
        score.overall = 0.8
        score.completeness = 0.8
        score.consistency = 0.8
        score.clarity = 0.8
        score.granularity = 0.8
        score.domain_alignment = 0.8
        result.critic_scores = [score]
        result.current_ontology = {
            'relationships': [
                {'type': 'HAS_ATTRIBUTE'},
                {'type': 'HAS_ATTRIBUTE'},
                {'type': 'WORKS_FOR'},
            ]
        }
        result.current_round = 1
        
        patterns = self.optimizer._identify_patterns([result])
        
        assert 'HAS_ATTRIBUTE' in patterns['top_rel_types']
        assert 'WORKS_FOR' in patterns['top_rel_types']

    def test_identify_patterns_with_weaknesses(self):
        """Test _identify_patterns identifies weakest dimensions."""
        result.current_round = 1
        result.current_ontology = {}
        result = Mock()
        score = Mock()
        score.overall = 0.8
        score.completeness = 0.9
        score.consistency = 0.7
        score.clarity = 0.9
        score.granularity = 0.65
        score.domain_alignment = 0.8
        result.critic_scores = [score]
        
        patterns = self.optimizer._identify_patterns([result])
        
        # Should identify the weakest dimension in this session
        assert patterns['most_common_weakness'] in ['granularity', 'consistency']
        assert 'weakness_distribution' in patterns
        assert isinstance(patterns['weakness_distribution'], dict)

    def test_generate_recommendations_low_score(self):
        """Test _generate_recommendations for low scores."""
        patterns = {
            'session_count': 3,
            'weakness_distribution': {'completeness': 2}
        }
        
        recs = self.optimizer._generate_recommendations(0.55, [0.5, 0.55, 0.6], patterns)
        
        # Should have recommendations for low score
        assert len(recs) > 0
        assert any('hybrid' in r.lower() or 'refinement' in r.lower() for r in recs)

    def test_generate_recommendations_medium_score(self):
        """Test _generate_recommendations for medium scores."""
        patterns = {
            'session_count': 3,
            'weakness_distribution': {'clarity': 1}
        }
        
        recs = self.optimizer._generate_recommendations(0.72, [0.7, 0.72, 0.74], patterns)
        
        # Should have recommendations for medium score
        assert len(recs) > 0

    def test_generate_recommendations_high_score(self):
        """Test _generate_recommendations for high scores."""
        patterns = {
            'session_count': 3,
            'weakness_distribution': {}
        }
        
        recs = self.optimizer._generate_recommendations(0.88, [0.85, 0.88, 0.90], patterns)
        
        # Should recommend maintaining configuration
        assert any('maintain' in r.lower() for r in recs)

    def test_generate_recommendations_high_variance(self):
        """Test _generate_recommendations detects high variance."""
        patterns = {'session_count': 3, 'weakness_distribution': {}}
        
        # High variance: [0.5, 0.75, 1.0] => std ≈ 0.204 > 0.15
        recs = self.optimizer._generate_recommendations(0.75, [0.5, 0.75, 1.0], patterns)
        
        # Should notice high variance
        assert any('variance' in r.lower() or 'stabilize' in r.lower() for r in recs)

    def test_optimization_report_to_dict(self):
        """Test OptimizationReport.to_dict() conversion."""
        report = OptimizationReport(
            average_score=0.82,
            trend='improving',
            recommendations=['Fix clarity', 'Add completeness'],
            score_distribution={'completeness': 0.85}
        )
        
        report_dict = report.to_dict()
        
        assert report_dict['average_score'] == 0.82
        assert report_dict['trend'] == 'improving'
        assert len(report_dict['recommendations']) == 2
        assert report_dict['score_distribution']['completeness'] == 0.85

    def test_optimization_report_with_ontologies(self):
        """Test OptimizationReport preserves best/worst ontologies."""
        best_onto = {'score': 0.9, 'entities': []}
        worst_onto = {'score': 0.6, 'entities': []}
        
        report = OptimizationReport(
            average_score=0.75,
            trend='stable',
            best_ontology=best_onto,
            worst_ontology=worst_onto
        )
        
        report_dict = report.to_dict()
        assert report_dict['best_score'] == 0.9
        assert report_dict['worst_score'] == 0.6


class TestOntologyOptimizerIntegration:
    """Integration tests for OntologyOptimizer analyzing batches."""

    def setup_method(self):
        """Set up test fixtures."""
        self.optimizer = OntologyOptimizer()

    def test_analyze_batch_empty(self):
        """Test analyze_batch returns safe result for empty input."""
        report = self.optimizer.analyze_batch([])
        
        assert report.average_score == 0.0
        assert report.trend == 'insufficient_data'
        assert len(report.recommendations) > 0

    def test_analyze_batch_single_session(self):
        """Test analyze_batch with single session."""
        result = Mock()
        score = Mock()
        score.overall = 0.80
        score.completeness = 0.8
        score.consistency = 0.8
        score.clarity = 0.8
        score.granularity = 0.8
        result.current_round = 1
        score.domain_alignment = 0.8
        result.critic_scores = [score]
        result.current_ontology = {'entities': []}
        
        report = self.optimizer.analyze_batch([result])
        
        assert report.average_score == 0.80
        assert report.trend == 'baseline'
        assert report.metadata['num_sessions'] == 1

    def test_analyze_batch_multiple_sessions(self):
        """Test analyze_batch with multiple sessions."""
        results = []
        for score_val in [0.70, 0.75, 0.80]:
            result = Mock()
            score = Mock()
            score.overall = score_val
            score.completeness = score_val
            score.consistency = score_val
            score.clarity = score_val
            score..current_round = 1
            resultgranularity = score_val
            score.domain_alignment = score_val
            result.critic_scores = [score]
            result.current_ontology = {'entities': []}
            results.append(result)
        
        report = self.optimizer.analyze_batch(results)
        
        assert report.average_score == pytest.approx(0.75, abs=0.01)
        assert report.metadata['num_sessions'] == 3

    def test_analyze_batch_improvement_rate(self):
        """Test analyze_batch tracks improvement rate."""
        # First batch
        result1 = Mock()
        score1 = Mock()
        score1.overall = 0.70
        score1.completeness = 0.7
        score1.consistency = 0.7
        result1.current_round = 1
        self.optimizer.analyze_batch([result1])
        
        # Second batch (improved)
        result2 = Mock()
        score2 = Mock()
        score2.overall = 0.80
        score2.completeness = 0.8
        score2.consistency = 0.8
        score2.clarity = 0.8
        score2.granularity = 0.8
        score2.domain_alignment = 0.8
        result2.critic_scores = [score2]
        result2.current_ontology = {}
        result2.current_round = 1
        score2.clarity = 0.8
        score2.granularity = 0.8
        score2.domain_alignment = 0.8
        result2.critic_scores = [score2]
        result2.current_ontology = {}
        report2 = self.optimizer.analyze_batch([result2])
        
        # Should track improvement rate
        assert report2.improvement_rate == pytest.approx(0.10, abs=0.01)

    def test_analyze_batch_parallel_matches_sequential(self):
        """Test analyze_batch_parallel produces same results as analyze_batch."""
        # Create test data
        results = []
        for score_val in [0.70, 0.75, 0.80, 0.85]:
            result = Mock()
            score = Mock()
            score.overall = score_val
            score..current_round = 1
            resultcompleteness = score_val
            score.consistency = score_val
            score.clarity = score_val
            score.granularity = score_val
            score.domain_alignment = score_val
            result.critic_scores = [score]
            result.current_ontology = {'entities': []}
            results.append(result)
        
        # Sequential analysis
        optimizer1 = OntologyOptimizer()
        report_seq = optimizer1.analyze_batch(results)
        
        # Parallel analysis
        optimizer2 = OntologyOptimizer()
        report_par = optimizer2.analyze_batch_parallel(results, max_workers=2)
        
        # Should match (except improvement_rate which depends on history)
        assert report_seq.average_score == pytest.approx(report_par.average_score, abs=0.01)
        assert report_seq.trend == report_par.trend
        assert len(report_seq.recommendations) == len(report_par.recommendations)
