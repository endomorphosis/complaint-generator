"""
Test suite for Batch 210: DEIRiskScorer analytical methods.

Tests the 10 new methods added to DEIRiskScorer:
- add_to_history, total_analyses, risk_level_distribution
- average_risk_score, high_risk_count, medium_risk_count
- low_risk_count, compliant_count, average_dei_keyword_count
- average_binding_keyword_count, problematic_document_ratio
"""
import pytest
from complaint_analysis.dei_risk_scoring import DEIRiskScorer


@pytest.fixture
def scorer():
    """Create a fresh DEIRiskScorer instance."""
    return DEIRiskScorer()


@pytest.fixture
def sample_results():
    """Create sample risk assessment results."""
    return [
        {'score': 3, 'level': 'high', 'dei_count': 10, 'proxy_count': 5, 'binding_count': 8},
        {'score': 2, 'level': 'medium', 'dei_count': 5, 'proxy_count': 3, 'binding_count': 4},
        {'score': 1, 'level': 'low', 'dei_count': 2, 'proxy_count': 1, 'binding_count': 0},
        {'score': 0, 'level': 'compliant', 'dei_count': 0, 'proxy_count': 0, 'binding_count': 0},
        {'score': 3, 'level': 'high', 'dei_count': 12, 'proxy_count': 6, 'binding_count': 10},
        {'score': 2, 'level': 'medium', 'dei_count': 4, 'proxy_count': 2, 'binding_count': 5},
        {'score': 1, 'level': 'low', 'dei_count': 3, 'proxy_count': 0, 'binding_count': 0},
    ]


@pytest.fixture
def populated_scorer(scorer, sample_results):
    """Create a scorer with sample results in history."""
    for result in sample_results:
        scorer.add_to_history(result)
    return scorer


# -------------------------------------------------------------------------
# Test add_to_history
# -------------------------------------------------------------------------
class TestAddToHistory:
    def test_add_single_result(self, scorer):
        result = {'score': 2, 'level': 'medium', 'dei_count': 5}
        scorer.add_to_history(result)
        assert len(scorer._analysis_history) == 1
        assert scorer._analysis_history[0] == result
    
    def test_add_multiple_results(self, scorer):
        for i in range(5):
            scorer.add_to_history({'score': i % 4, 'level': 'test'})
        assert len(scorer._analysis_history) == 5
    
    def test_preserves_order(self, scorer):
        results = [
            {'score': 3, 'level': 'high'},
            {'score': 1, 'level': 'low'},
            {'score': 0, 'level': 'compliant'}
        ]
        for r in results:
            scorer.add_to_history(r)
        assert scorer._analysis_history == results


# -------------------------------------------------------------------------
# Test total_analyses
# -------------------------------------------------------------------------
class TestTotalAnalyses:
    def test_empty_scorer(self, scorer):
        assert scorer.total_analyses() == 0
    
    def test_after_adding(self, scorer):
        scorer.add_to_history({'score': 1})
        assert scorer.total_analyses() == 1
        scorer.add_to_history({'score': 2})
        assert scorer.total_analyses() == 2
    
    def test_populated_scorer(self, populated_scorer):
        assert populated_scorer.total_analyses() == 7


# -------------------------------------------------------------------------
# Test risk_level_distribution
# -------------------------------------------------------------------------
class TestRiskLevelDistribution:
    def test_empty_scorer(self, scorer):
        dist = scorer.risk_level_distribution()
        assert dist == {}
    
    def test_single_level(self, scorer):
        for _ in range(3):
            scorer.add_to_history({'level': 'high'})
        dist = scorer.risk_level_distribution()
        assert dist == {'high': 3}
    
    def test_multiple_levels(self, populated_scorer):
        dist = populated_scorer.risk_level_distribution()
        assert dist.get('high', 0) == 2
        assert dist.get('medium', 0) == 2
        assert dist.get('low', 0) == 2
        assert dist.get('compliant', 0) == 1
    
    def test_unknown_level(self, scorer):
        scorer.add_to_history({'score': 2})  # No 'level' key
        dist = scorer.risk_level_distribution()
        assert dist.get('unknown', 0) == 1


# -------------------------------------------------------------------------
# Test average_risk_score
# -------------------------------------------------------------------------
class TestAverageRiskScore:
    def test_empty_scorer(self, scorer):
        assert scorer.average_risk_score() == 0.0
    
    def test_single_score(self, scorer):
        scorer.add_to_history({'score': 2})
        assert scorer.average_risk_score() == 2.0
    
    def test_multiple_scores(self, populated_scorer):
        # Scores: 3, 2, 1, 0, 3, 2, 1 -> avg = 12/7
        avg = populated_scorer.average_risk_score()
        expected = (3 + 2 + 1 + 0 + 3 + 2 + 1) / 7
        assert abs(avg - expected) < 0.01
    
    def test_all_same_score(self, scorer):
        for _ in range(5):
            scorer.add_to_history({'score': 1})
        assert scorer.average_risk_score() == 1.0


# -------------------------------------------------------------------------
# Test high_risk_count
# -------------------------------------------------------------------------
class TestHighRiskCount:
    def test_empty_scorer(self, scorer):
        assert scorer.high_risk_count() == 0
    
    def test_no_high_risk(self, scorer):
        scorer.add_to_history({'score': 0})
        scorer.add_to_history({'score': 1})
        scorer.add_to_history({'score': 2})
        assert scorer.high_risk_count() == 0
    
    def test_with_high_risk(self, populated_scorer):
        assert populated_scorer.high_risk_count() == 2
    
    def test_all_high_risk(self, scorer):
        for _ in range(4):
            scorer.add_to_history({'score': 3})
        assert scorer.high_risk_count() == 4


# -------------------------------------------------------------------------
# Test medium_risk_count
# -------------------------------------------------------------------------
class TestMediumRiskCount:
    def test_empty_scorer(self, scorer):
        assert scorer.medium_risk_count() == 0
    
    def test_no_medium_risk(self, scorer):
        scorer.add_to_history({'score': 0})
        scorer.add_to_history({'score': 3})
        assert scorer.medium_risk_count() == 0
    
    def test_with_medium_risk(self, populated_scorer):
        assert populated_scorer.medium_risk_count() == 2
    
    def test_all_medium_risk(self, scorer):
        for _ in range(3):
            scorer.add_to_history({'score': 2})
        assert scorer.medium_risk_count() == 3


# -------------------------------------------------------------------------
# Test low_risk_count
# -------------------------------------------------------------------------
class TestLowRiskCount:
    def test_empty_scorer(self, scorer):
        assert scorer.low_risk_count() == 0
    
    def test_no_low_risk(self, scorer):
        scorer.add_to_history({'score': 0})
        scorer.add_to_history({'score': 2})
        assert scorer.low_risk_count() == 0
    
    def test_with_low_risk(self, populated_scorer):
        assert populated_scorer.low_risk_count() == 2
    
    def test_all_low_risk(self, scorer):
        for _ in range(5):
            scorer.add_to_history({'score': 1})
        assert scorer.low_risk_count() == 5


# -------------------------------------------------------------------------
# Test compliant_count
# -------------------------------------------------------------------------
class TestCompliantCount:
    def test_empty_scorer(self, scorer):
        assert scorer.compliant_count() == 0
    
    def test_no_compliant(self, scorer):
        scorer.add_to_history({'score': 1})
        scorer.add_to_history({'score': 2})
        assert scorer.compliant_count() == 0
    
    def test_with_compliant(self, populated_scorer):
        assert populated_scorer.compliant_count() == 1
    
    def test_all_compliant(self, scorer):
        for _ in range(6):
            scorer.add_to_history({'score': 0})
        assert scorer.compliant_count() == 6


# -------------------------------------------------------------------------
# Test average_dei_keyword_count
# -------------------------------------------------------------------------
class TestAverageDEIKeywordCount:
    def test_empty_scorer(self, scorer):
        assert scorer.average_dei_keyword_count() == 0.0
    
    def test_single_analysis(self, scorer):
        scorer.add_to_history({'dei_count': 5})
        assert scorer.average_dei_keyword_count() == 5.0
    
    def test_multiple_analyses(self, populated_scorer):
        # dei_counts: 10, 5, 2, 0, 12, 4, 3 -> avg = 36/7
        avg = populated_scorer.average_dei_keyword_count()
        expected = (10 + 5 + 2 + 0 + 12 + 4 + 3) / 7
        assert abs(avg - expected) < 0.01
    
    def test_zero_counts(self, scorer):
        for _ in range(3):
            scorer.add_to_history({'dei_count': 0})
        assert scorer.average_dei_keyword_count() == 0.0


# -------------------------------------------------------------------------
# Test average_binding_keyword_count
# -------------------------------------------------------------------------
class TestAverageBindingKeywordCount:
    def test_empty_scorer(self, scorer):
        assert scorer.average_binding_keyword_count() == 0.0
    
    def test_single_analysis(self, scorer):
        scorer.add_to_history({'binding_count': 7})
        assert scorer.average_binding_keyword_count() == 7.0
    
    def test_multiple_analyses(self, populated_scorer):
        # binding_counts: 8, 4, 0, 0, 10, 5, 0 -> avg = 27/7
        avg = populated_scorer.average_binding_keyword_count()
        expected = (8 + 4 + 0 + 0 + 10 + 5 + 0) / 7
        assert abs(avg - expected) < 0.01
    
    def test_zero_counts(self, scorer):
        for _ in range(4):
            scorer.add_to_history({'binding_count': 0})
        assert scorer.average_binding_keyword_count() == 0.0


# -------------------------------------------------------------------------
# Test problematic_document_ratio
# -------------------------------------------------------------------------
class TestProblematicDocumentRatio:
    def test_empty_scorer(self, scorer):
        assert scorer.problematic_document_ratio() == 0.0
    
    def test_no_problematic(self, scorer):
        scorer.add_to_history({'score': 0})
        scorer.add_to_history({'score': 1})
        ratio = scorer.problematic_document_ratio(threshold=2)
        assert ratio == 0.0
    
    def test_all_problematic(self, scorer):
        for _ in range(3):
            scorer.add_to_history({'score': 3})
        ratio = scorer.problematic_document_ratio(threshold=2)
        assert ratio == 1.0
    
    def test_mixed_with_default_threshold(self, populated_scorer):
        # Scores: 3, 2, 1, 0, 3, 2, 1
        # threshold=2: scores >= 2 are 3, 2, 3, 2 = 4 out of 7
        ratio = populated_scorer.problematic_document_ratio()
        expected = 4 / 7
        assert abs(ratio - expected) < 0.01
    
    def test_custom_threshold(self, populated_scorer):
        # threshold=3: only scores == 3 are 2 out of 7
        ratio = populated_scorer.problematic_document_ratio(threshold=3)
        expected = 2 / 7
        assert abs(ratio - expected) < 0.01
    
    def test_threshold_zero(self, populated_scorer):
        # All 7 documents have score >= 0
        ratio = populated_scorer.problematic_document_ratio(threshold=0)
        assert ratio == 1.0


# -------------------------------------------------------------------------
# Integration test
# -------------------------------------------------------------------------
class TestBatch210Integration:
    def test_all_methods_callable(self, populated_scorer):
        """Verify all Batch 210 methods are callable."""
        populated_scorer.add_to_history({'score': 1, 'level': 'low'})
        assert populated_scorer.total_analyses() > 0
        assert isinstance(populated_scorer.risk_level_distribution(), dict)
        assert isinstance(populated_scorer.average_risk_score(), float)
        assert populated_scorer.high_risk_count() >= 0
        assert populated_scorer.medium_risk_count() >= 0
        assert populated_scorer.low_risk_count() >= 0
        assert populated_scorer.compliant_count() >= 0
        assert isinstance(populated_scorer.average_dei_keyword_count(), float)
        assert isinstance(populated_scorer.average_binding_keyword_count(), float)
        assert 0.0 <= populated_scorer.problematic_document_ratio() <= 1.0
    
    def test_consistency_checks(self, populated_scorer):
        """Verify internal consistency of metrics."""
        total = populated_scorer.total_analyses()
        high = populated_scorer.high_risk_count()
        medium = populated_scorer.medium_risk_count()
        low = populated_scorer.low_risk_count()
        compliant = populated_scorer.compliant_count()
        
        # All risk levels should sum to total
        assert high + medium + low + compliant == total
        
        # Distribution should match individual counts
        dist = populated_scorer.risk_level_distribution()
        assert dist.get('high', 0) == high
        assert dist.get('medium', 0) == medium
        assert dist.get('low', 0) == low
        assert dist.get('compliant', 0) == compliant
        
        # Problematic ratio should be consistent
        ratio = populated_scorer.problematic_document_ratio(threshold=2)
        expected_problematic = high + medium
        expected_ratio = expected_problematic / total if total > 0 else 0.0
        assert abs(ratio - expected_ratio) < 0.01
    
    def test_real_world_workflow(self, scorer):
        """Test a realistic analysis workflow."""
        # Simulate analyzing several documents
        docs = [
            "This policy shall require diversity training for all employees.",
            "Standard operating procedures for the department.",
            "Hiring practices must include cultural competence assessment.",
            "General administrative guidelines.",
        ]
        
        for doc in docs:
            result = scorer.calculate_risk(doc)
            scorer.add_to_history(result)
        
        # Verify history was populated
        assert scorer.total_analyses() == 4
        
        # Verify we can get meaningful statistics
        avg_score = scorer.average_risk_score()
        assert 0.0 <= avg_score <= 3.0
        
        # Verify distribution makes sense
        dist = scorer.risk_level_distribution()
        assert sum(dist.values()) == 4
