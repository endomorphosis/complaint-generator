"""Unit tests for GraphRAG OntologyOptimizer pure helper methods.

These tests cover deterministic, pure functions in OntologyOptimizer.
"""

import pytest
from unittest.mock import Mock
from ipfs_datasets_py.optimizers.graphrag.ontology_optimizer import (
    OntologyOptimizer,
    OptimizationReport,
)


class TestOntologyOptimizerTrendDetection:
    """Test suite for OntologyOptimizer trend detection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.optimizer = OntologyOptimizer()

    def test_determine_trend_baseline(self):
        """Test _determine_trend returns 'baseline' when no history."""
        trend = self.optimizer._determine_trend(0.75)
        assert trend == 'baseline'

    def test_determine_trend_improving(self):
        """Test _determine_trend detects improvement."""
        report1 = OptimizationReport(average_score=0.70, trend='baseline')
        self.optimizer._history.append(report1)
        trend = self.optimizer._determine_trend(0.76)
        assert trend == 'improving'

    def test_determine_trend_degrading(self):
        """Test _determine_trend detects degradation."""
        report1 = OptimizationReport(average_score=0.80, trend='baseline')
        self.optimizer._history.append(report1)
        trend = self.optimizer._determine_trend(0.74)
        assert trend == 'degrading'

    def test_determine_trend_stable(self):
        """Test _determine_trend detects stable score."""
        report1 = OptimizationReport(average_score=0.75, trend='baseline')
        self.optimizer._history.append(report1)
        trend = self.optimizer._determine_trend(0.76)
        assert trend == 'stable'


class TestOntologyOptimizerStatistics:
    """Test suite for OntologyOptimizer statistical helpers."""

    def setup_method(self):
        """Set up test fixtures."""
        self.optimizer = OntologyOptimizer()

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
        std = self.optimizer._compute_std([0.0, 2.0])
        assert std == pytest.approx(1.0, abs=1e-6)

    def test_compute_std_normal_distribution(self):
        """Test _compute_std for normal distribution."""
        std = self.optimizer._compute_std([1.0, 2.0, 3.0, 4.0, 5.0])
        assert std == pytest.approx(1.414, abs=0.01)


class TestOntologyOptimizerOntologyExtraction:
    """Test suite for OntologyOptimizer ontology extraction."""

    def setup_method(self):
        """Set up test fixtures."""
        self.optimizer = OntologyOptimizer()

    def test_extract_ontology_from_mediator_state(self):
        """Test _extract_ontology extracts from MediatorState-like object."""
        result = Mock()
        result.current_ontology = {'entities': [{'type': 'PERSON'}]}
        result.critic_scores = [Mock(overall=0.85)]
        
        ontology_dict = self.optimizer._extract_ontology(result)
        
        assert ontology_dict['ontology'] == {'entities': [{'type': 'PERSON'}]}
        assert ontology_dict['score'] == 0.85

    def test_extract_ontology_from_session_result(self):
        """Test _extract_ontology extracts from SessionResult-like object."""
        result = Mock(spec=['ontology', 'critic_score'])
        result.ontology = {'relationships': [{'type': 'HAS_ATTR'}]}
        result.critic_score = Mock(overall=0.72)
        
        ontology_dict = self.optimizer._extract_ontology(result)
        
        assert ontology_dict['ontology'] == {'relationships': [{'type': 'HAS_ATTR'}]}
        assert ontology_dict['score'] == 0.72

    def test_extract_ontology_fallback_empty(self):
        """Test _extract_ontology returns empty dict when no ontology found."""
        result = Mock(spec=[])
        ontology_dict = self.optimizer._extract_ontology(result)
        
        assert ontology_dict == {'ontology': {}, 'score': 0.0}


class TestOntologyOptimizerScoreDistribution:
    """Test suite for OntologyOptimizer score distribution aggregation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.optimizer = OntologyOptimizer()

    def test_compute_score_distribution_single_dimension(self):
        """Test _compute_score_distribution aggregates dimensions."""
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

    def test_compute_score_distribution_all_dimensions(self):
        """Test _compute_score_distribution aggregates all dimensions."""
        result = Mock()
        score = Mock()
        score.completeness = 0.8
        score.consistency = 0.75
        score.clarity = 0.9
        score.granularity = 0.7
        score.domain_alignment = 0.85
        result.critic_scores = [score]
        
        distribution = self.optimizer._compute_score_distribution([result])
        
        assert distribution['completeness'] == 0.8
        assert distribution['consistency'] == 0.75
        assert distribution['clarity'] == 0.9
        assert distribution['granularity'] == 0.7
        assert distribution['domain_alignment'] == 0.85

    def test_compute_score_distribution_no_critic_scores(self):
        """Test _compute_score_distribution all zeros when no critic_scores."""
        result = Mock()
        result.critic_scores = []
        
        distribution = self.optimizer._compute_score_distribution([result])
        
        for dim in distribution.values():
            assert dim == 0.0


class TestOntologyOptimizerRecommendations:
    """Test suite for OntologyOptimizer recommendation generation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.optimizer = OntologyOptimizer()

    def test_generate_recommendations_low_score(self):
        """Test _generate_recommendations for low scores."""
        patterns = {'session_count': 3, 'weakness_distribution': {}}
        recs = self.optimizer._generate_recommendations(0.55, [0.5, 0.55, 0.6], patterns)
        assert len(recs) > 0

    def test_generate_recommendations_medium_score(self):
        """Test _generate_recommendations for medium scores."""
        patterns = {'session_count': 3, 'weakness_distribution': {}}
        recs = self.optimizer._generate_recommendations(0.72, [0.7, 0.72, 0.74], patterns)
        assert len(recs) > 0

    def test_generate_recommendations_high_score(self):
        """Test _generate_recommendations for high scores."""
        patterns = {'session_count': 3, 'weakness_distribution': {}}
        recs = self.optimizer._generate_recommendations(0.88, [0.85, 0.88, 0.90], patterns)
        assert any('maintain' in r.lower() for r in recs)

    def test_generate_recommendations_high_variance(self):
        """Test _generate_recommendations detects high variance."""
        patterns = {'session_count': 3, 'weakness_distribution': {}}
        recs = self.optimizer._generate_recommendations(0.75, [0.5, 0.75, 1.0], patterns)
        assert any('variance' in r.lower() or 'stabilize' in r.lower() for r in recs)


class TestOptimizationReportDataclass:
    """Test suite for OptimizationReport dataclass."""

    def test_optimization_report_to_dict(self):
        """Test OptimizationReport.to_dict() conversion."""
        report = OptimizationReport(
            average_score=0.82,
            trend='improving',
            recommendations=['Fix clarity'],
            score_distribution={'completeness': 0.85}
        )
        
        report_dict = report.to_dict()
        
        assert report_dict['average_score'] == 0.82
        assert report_dict['trend'] == 'improving'

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

