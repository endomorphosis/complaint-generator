"""
Unit tests for Batch 205: NeurosymbolicMatcher analysis methods.

Tests the 10 matching analysis and diagnostic methods added to NeurosymbolicMatcher.
"""

import pytest
from complaint_phases.neurosymbolic_matcher import NeurosymbolicMatcher


@pytest.fixture
def matcher():
    """Create a NeurosymbolicMatcher instance for testing."""
    return NeurosymbolicMatcher()


def create_matching_result(overall_satisfaction=0.5, total_claims=5, satisfied_claims=2, gaps=None):
    """Helper to create a matching result dict."""
    if gaps is None:
        gaps = []
    return {
        'overall_satisfaction': overall_satisfaction,
        'total_claims': total_claims,
        'satisfied_claims': satisfied_claims,
        'gaps': gaps
    }


# ============================================================================ #
# Test matching_history_size()
# ============================================================================ #

class TestMatchingHistorySize:
    def test_empty_history(self, matcher):
        assert matcher.matching_history_size() == 0
    
    def test_single_result(self, matcher):
        matcher.matching_results.append(create_matching_result())
        assert matcher.matching_history_size() == 1
    
    def test_multiple_results(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(),
            create_matching_result(),
            create_matching_result()
        ])
        assert matcher.matching_history_size() == 3


# ============================================================================ #
# Test average_satisfaction_score()
# ============================================================================ #

class TestAverageSatisfactionScore:
    def test_empty_results(self, matcher):
        assert matcher.average_satisfaction_score() == 0.0
    
    def test_single_result(self, matcher):
        matcher.matching_results.append(create_matching_result(overall_satisfaction=0.75))
        assert matcher.average_satisfaction_score() == 0.75
    
    def test_multiple_results(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(overall_satisfaction=0.6),
            create_matching_result(overall_satisfaction=0.8),
            create_matching_result(overall_satisfaction=0.7)
        ])
        avg = matcher.average_satisfaction_score()
        assert abs(avg - 0.7) < 0.01
    
    def test_zero_satisfaction(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(overall_satisfaction=0.0),
            create_matching_result(overall_satisfaction=0.0)
        ])
        assert matcher.average_satisfaction_score() == 0.0


# ============================================================================ #
# Test total_claims_processed()
# ============================================================================ #

class TestTotalClaimsProcessed:
    def test_empty_results(self, matcher):
        assert matcher.total_claims_processed() == 0
    
    def test_single_result(self, matcher):
        matcher.matching_results.append(create_matching_result(total_claims=10))
        assert matcher.total_claims_processed() == 10
    
    def test_multiple_results(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(total_claims=5),
            create_matching_result(total_claims=7),
            create_matching_result(total_claims=3)
        ])
        assert matcher.total_claims_processed() == 15


# ============================================================================ #
# Test total_satisfied_claims()
# ============================================================================ #

class TestTotalSatisfiedClaims:
    def test_empty_results(self, matcher):
        assert matcher.total_satisfied_claims() == 0
    
    def test_single_result(self, matcher):
        matcher.matching_results.append(create_matching_result(satisfied_claims=8))
        assert matcher.total_satisfied_claims() == 8
    
    def test_multiple_results(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(satisfied_claims=2),
            create_matching_result(satisfied_claims=4),
            create_matching_result(satisfied_claims=1)
        ])
        assert matcher.total_satisfied_claims() == 7
    
    def test_all_unsatisfied(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(satisfied_claims=0),
            create_matching_result(satisfied_claims=0)
        ])
        assert matcher.total_satisfied_claims() == 0


# ============================================================================ #
# Test satisfaction_improvement_trend()
# ============================================================================ #

class TestSatisfactionImprovementTrend:
    def test_insufficient_data_empty(self, matcher):
        assert matcher.satisfaction_improvement_trend() == 'insufficient_data'
    
    def test_insufficient_data_one_result(self, matcher):
        matcher.matching_results.append(create_matching_result(overall_satisfaction=0.5))
        assert matcher.satisfaction_improvement_trend() == 'insufficient_data'
    
    def test_improving_trend_two_results(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(overall_satisfaction=0.3),
            create_matching_result(overall_satisfaction=0.8)
        ])
        assert matcher.satisfaction_improvement_trend() == 'improving'
    
    def test_declining_trend_two_results(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(overall_satisfaction=0.9),
            create_matching_result(overall_satisfaction=0.3)
        ])
        assert matcher.satisfaction_improvement_trend() == 'declining'
    
    def test_stable_trend_two_results(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(overall_satisfaction=0.5),
            create_matching_result(overall_satisfaction=0.52)
        ])
        assert matcher.satisfaction_improvement_trend() == 'stable'
    
    def test_improving_trend_many_results(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(overall_satisfaction=0.2),
            create_matching_result(overall_satisfaction=0.3),
            create_matching_result(overall_satisfaction=0.4),
            create_matching_result(overall_satisfaction=0.7),
            create_matching_result(overall_satisfaction=0.8),
            create_matching_result(overall_satisfaction=0.9)
        ])
        assert matcher.satisfaction_improvement_trend() == 'improving'
    
    def test_declining_trend_many_results(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(overall_satisfaction=0.9),
            create_matching_result(overall_satisfaction=0.8),
            create_matching_result(overall_satisfaction=0.7),
            create_matching_result(overall_satisfaction=0.3),
            create_matching_result(overall_satisfaction=0.2),
            create_matching_result(overall_satisfaction=0.1)
        ])
        assert matcher.satisfaction_improvement_trend() == 'declining'


# ============================================================================ #
# Test gap_frequency_distribution()
# ============================================================================ #

class TestGapFrequencyDistribution:
    def test_empty_results(self, matcher):
        assert matcher.gap_frequency_distribution() == {}
    
    def test_no_gaps(self, matcher):
        matcher.matching_results.append(create_matching_result(gaps=[]))
        assert matcher.gap_frequency_distribution() == {}
    
    def test_single_gap(self, matcher):
        gaps = [{'requirement_name': 'proof_of_harm'}]
        matcher.matching_results.append(create_matching_result(gaps=gaps))
        freq = matcher.gap_frequency_distribution()
        assert freq == {'proof_of_harm': 1}
    
    def test_multiple_gaps_different_types(self, matcher):
        gaps = [
            {'requirement_name': 'proof_of_harm'},
            {'requirement_name': 'causation'},
            {'requirement_name': 'standing'}
        ]
        matcher.matching_results.append(create_matching_result(gaps=gaps))
        freq = matcher.gap_frequency_distribution()
        assert freq == {'proof_of_harm': 1, 'causation': 1, 'standing': 1}
    
    def test_recurring_gaps_across_results(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(gaps=[{'requirement_name': 'proof_of_harm'}]),
            create_matching_result(gaps=[
                {'requirement_name': 'proof_of_harm'},
                {'requirement_name': 'causation'}
            ]),
            create_matching_result(gaps=[{'requirement_name': 'proof_of_harm'}])
        ])
        freq = matcher.gap_frequency_distribution()
        assert freq == {'proof_of_harm': 3, 'causation': 1}


# ============================================================================ #
# Test most_common_gap()
# ============================================================================ #

class TestMostCommonGap:
    def test_no_gaps(self, matcher):
        assert matcher.most_common_gap() == 'none'
    
    def test_single_gap_type(self, matcher):
        gaps = [{'requirement_name': 'standing'}]
        matcher.matching_results.append(create_matching_result(gaps=gaps))
        assert matcher.most_common_gap() == 'standing'
    
    def test_multiple_gap_types(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(gaps=[{'requirement_name': 'proof_of_harm'}]),
            create_matching_result(gaps=[
                {'requirement_name': 'proof_of_harm'},
                {'requirement_name': 'causation'}
            ]),
            create_matching_result(gaps=[
                {'requirement_name': 'proof_of_harm'},
                {'requirement_name': 'standing'}
            ])
        ])
        assert matcher.most_common_gap() == 'proof_of_harm'


# ============================================================================ #
# Test satisfaction_variance()
# ============================================================================ #

class TestSatisfactionVariance:
    def test_empty_results(self, matcher):
        assert matcher.satisfaction_variance() == 0.0
    
    def test_single_result(self, matcher):
        matcher.matching_results.append(create_matching_result(overall_satisfaction=0.5))
        assert matcher.satisfaction_variance() == 0.0
    
    def test_identical_scores(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(overall_satisfaction=0.7),
            create_matching_result(overall_satisfaction=0.7),
            create_matching_result(overall_satisfaction=0.7)
        ])
        assert matcher.satisfaction_variance() < 1e-10
    
    def test_varied_scores(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(overall_satisfaction=0.2),
            create_matching_result(overall_satisfaction=0.5),
            create_matching_result(overall_satisfaction=0.8)
        ])
        variance = matcher.satisfaction_variance()
        assert variance > 0.0
        # Mean = 0.5, variance = ((0.2-0.5)^2 + (0.5-0.5)^2 + (0.8-0.5)^2) / 3
        # = (0.09 + 0 + 0.09) / 3 = 0.06
        assert abs(variance - 0.06) < 0.01


# ============================================================================ #
# Test high_viability_percentage()
# ============================================================================ #

class TestHighViabilityPercentage:
    def test_empty_results(self, matcher):
        assert matcher.high_viability_percentage() == 0.0
    
    def test_all_high_viability(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(overall_satisfaction=0.9),
            create_matching_result(overall_satisfaction=0.85),
            create_matching_result(overall_satisfaction=1.0)
        ])
        assert matcher.high_viability_percentage() == 1.0
    
    def test_no_high_viability(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(overall_satisfaction=0.3),
            create_matching_result(overall_satisfaction=0.5),
            create_matching_result(overall_satisfaction=0.7)
        ])
        assert matcher.high_viability_percentage() == 0.0
    
    def test_mixed_viability(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(overall_satisfaction=0.9),
            create_matching_result(overall_satisfaction=0.5),
            create_matching_result(overall_satisfaction=0.85),
            create_matching_result(overall_satisfaction=0.3)
        ])
        percentage = matcher.high_viability_percentage()
        assert abs(percentage - 0.5) < 0.01
    
    def test_custom_threshold(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(overall_satisfaction=0.95),
            create_matching_result(overall_satisfaction=0.85),
            create_matching_result(overall_satisfaction=0.75)
        ])
        # With threshold=0.9, only first result qualifies
        percentage = matcher.high_viability_percentage(threshold=0.9)
        assert abs(percentage - (1/3)) < 0.01


# ============================================================================ #
# Test average_gaps_per_result()
# ============================================================================ #

class TestAverageGapsPerResult:
    def test_empty_results(self, matcher):
        assert matcher.average_gaps_per_result() == 0.0
    
    def test_no_gaps(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(gaps=[]),
            create_matching_result(gaps=[])
        ])
        assert matcher.average_gaps_per_result() == 0.0
    
    def test_uniform_gaps(self, matcher):
        gaps = [{'requirement_name': 'test'}] * 3
        matcher.matching_results.extend([
            create_matching_result(gaps=gaps),
            create_matching_result(gaps=gaps)
        ])
        assert matcher.average_gaps_per_result() == 3.0
    
    def test_varied_gaps(self, matcher):
        matcher.matching_results.extend([
            create_matching_result(gaps=[{'requirement_name': 'a'}]),
            create_matching_result(gaps=[
                {'requirement_name': 'b'},
                {'requirement_name': 'c'},
                {'requirement_name': 'd'}
            ]),
            create_matching_result(gaps=[
                {'requirement_name': 'e'},
                {'requirement_name': 'f'}
            ])
        ])
        avg = matcher.average_gaps_per_result()
        # Total: 1 + 3 + 2 = 6 gaps across 3 results
        assert abs(avg - 2.0) < 0.01


# ============================================================================ #
# Integration test
# ============================================================================ #

class TestBatch205Integration:
    def test_comprehensive_analysis_workflow(self, matcher):
        """Test that all Batch 205 methods work together correctly."""
        # Populate with realistic data
        matcher.matching_results.extend([
            create_matching_result(
                overall_satisfaction=0.4,
                total_claims=10,
                satisfied_claims=4,
                gaps=[
                    {'requirement_name': 'proof_of_harm'},
                    {'requirement_name': 'causation'}
                ]
            ),
            create_matching_result(
                overall_satisfaction=0.6,
                total_claims=8,
                satisfied_claims=5,
                gaps=[
                    {'requirement_name': 'proof_of_harm'},
                    {'requirement_name': 'standing'}
                ]
            ),
            create_matching_result(
                overall_satisfaction=0.9,
                total_claims=5,
                satisfied_claims=5,
                gaps=[]
            )
        ])
        
        # Verify all methods work
        assert matcher.matching_history_size() == 3
        assert 0.6 < matcher.average_satisfaction_score() < 0.7
        assert matcher.total_claims_processed() == 23
        assert matcher.total_satisfied_claims() == 14
        
        trend = matcher.satisfaction_improvement_trend()
        assert trend == 'improving'
        
        freq = matcher.gap_frequency_distribution()
        assert freq['proof_of_harm'] == 2
        assert matcher.most_common_gap() == 'proof_of_harm'
        
        variance = matcher.satisfaction_variance()
        assert variance > 0.0
        
        high_pct = matcher.high_viability_percentage()
        assert abs(high_pct - (1/3)) < 0.01
        
        avg_gaps = matcher.average_gaps_per_result()
        assert abs(avg_gaps - (4/3)) < 0.01
