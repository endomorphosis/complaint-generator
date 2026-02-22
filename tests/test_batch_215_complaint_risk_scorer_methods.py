"""
Unit tests for Batch 215: ComplaintRiskScorer analysis methods.

Tests the 10 risk assessment tracking and statistics methods added to ComplaintRiskScorer.
"""

import pytest
from complaint_analysis.risk_scoring import ComplaintRiskScorer


@pytest.fixture
def scorer():
    """Create a ComplaintRiskScorer instance for testing."""
    return ComplaintRiskScorer()


def create_assessment_result(score=0, level='minimal', complaint_keywords=0,
                             binding_keywords=0, legal_provisions=0, factors=None):
    """Helper to create a mock assessment result."""
    if factors is None:
        factors = []
    
    return {
        'score': score,
        'level': level,
        'factors': factors,
        'complaint_keywords': complaint_keywords,
        'binding_keywords': binding_keywords,
        'legal_provisions': legal_provisions,
        'severity_indicators': 0,
        'recommendations': []
    }


# ============================================================================ #
# Test total_assessments()
# ============================================================================ #

class TestTotalAssessments:
    def test_no_assessments(self, scorer):
        assert scorer.total_assessments() == 0
    
    def test_after_manual_assessment_add(self, scorer):
        scorer._assessment_history.append(create_assessment_result())
        assert scorer.total_assessments() == 1
    
    def test_multiple_assessments(self, scorer):
        for i in range(5):
            scorer._assessment_history.append(create_assessment_result())
        assert scorer.total_assessments() == 5


# ============================================================================ #
# Test assessments_by_risk_level()
# ============================================================================ #

class TestAssessmentsByRiskLevel:
    def test_no_assessments(self, scorer):
        assert scorer.assessments_by_risk_level('high') == 0
    
    def test_no_matching_level(self, scorer):
        scorer._assessment_history.append(create_assessment_result(level='low'))
        assert scorer.assessments_by_risk_level('high') == 0
    
    def test_single_matching_level(self, scorer):
        scorer._assessment_history.append(create_assessment_result(level='high'))
        assert scorer.assessments_by_risk_level('high') == 1
    
    def test_multiple_matching_levels(self, scorer):
        scorer._assessment_history.extend([
            create_assessment_result(level='high'),
            create_assessment_result(level='low'),
            create_assessment_result(level='high'),
        ])
        assert scorer.assessments_by_risk_level('high') == 2
        assert scorer.assessments_by_risk_level('low') == 1


# ============================================================================ #
# Test risk_level_distribution()
# ============================================================================ #

class TestRiskLevelDistribution:
    def test_no_assessments(self, scorer):
        assert scorer.risk_level_distribution() == {}
    
    def test_single_level(self, scorer):
        scorer._assessment_history.extend([
            create_assessment_result(level='low'),
            create_assessment_result(level='low'),
        ])
        assert scorer.risk_level_distribution() == {'low': 2}
    
    def test_multiple_levels(self, scorer):
        scorer._assessment_history.extend([
            create_assessment_result(level='minimal'),
            create_assessment_result(level='high'),
            create_assessment_result(level='medium'),
            create_assessment_result(level='high'),
        ])
        dist = scorer.risk_level_distribution()
        assert dist == {'minimal': 1, 'high': 2, 'medium': 1}


# ============================================================================ #
# Test average_risk_score()
# ============================================================================ #

class TestAverageRiskScore:
    def test_no_assessments(self, scorer):
        assert scorer.average_risk_score() == 0.0
    
    def test_single_assessment(self, scorer):
        scorer._assessment_history.append(create_assessment_result(score=2))
        assert scorer.average_risk_score() == 2.0
    
    def test_multiple_assessments(self, scorer):
        scorer._assessment_history.extend([
            create_assessment_result(score=0),
            create_assessment_result(score=1),
            create_assessment_result(score=2),
            create_assessment_result(score=3),
        ])
        # Average: (0 + 1 + 2 + 3) / 4 = 1.5
        assert abs(scorer.average_risk_score() - 1.5) < 0.01


# ============================================================================ #
# Test maximum_risk_score()
# ============================================================================ #

class TestMaximumRiskScore:
    def test_no_assessments(self, scorer):
        assert scorer.maximum_risk_score() == 0
    
    def test_single_assessment(self, scorer):
        scorer._assessment_history.append(create_assessment_result(score=2))
        assert scorer.maximum_risk_score() == 2
    
    def test_multiple_assessments(self, scorer):
        scorer._assessment_history.extend([
            create_assessment_result(score=0),
            create_assessment_result(score=3),
            create_assessment_result(score=1),
        ])
        assert scorer.maximum_risk_score() == 3


# ============================================================================ #
# Test average_complaint_keywords()
# ============================================================================ #

class TestAverageComplaintKeywords:
    def test_no_assessments(self, scorer):
        assert scorer.average_complaint_keywords() == 0.0
    
    def test_single_assessment(self, scorer):
        scorer._assessment_history.append(create_assessment_result(complaint_keywords=5))
        assert scorer.average_complaint_keywords() == 5.0
    
    def test_multiple_assessments(self, scorer):
        scorer._assessment_history.extend([
            create_assessment_result(complaint_keywords=2),
            create_assessment_result(complaint_keywords=4),
            create_assessment_result(complaint_keywords=6),
        ])
        # Average: (2 + 4 + 6) / 3 = 4.0
        assert abs(scorer.average_complaint_keywords() - 4.0) < 0.01


# ============================================================================ #
# Test average_binding_keywords()
# ============================================================================ #

class TestAverageBindingKeywords:
    def test_no_assessments(self, scorer):
        assert scorer.average_binding_keywords() == 0.0
    
    def test_single_assessment(self, scorer):
        scorer._assessment_history.append(create_assessment_result(binding_keywords=3))
        assert scorer.average_binding_keywords() == 3.0
    
    def test_multiple_assessments(self, scorer):
        scorer._assessment_history.extend([
            create_assessment_result(binding_keywords=1),
            create_assessment_result(binding_keywords=2),
            create_assessment_result(binding_keywords=3),
        ])
        # Average: (1 + 2 + 3) / 3 = 2.0
        assert abs(scorer.average_binding_keywords() - 2.0) < 0.01


# ============================================================================ #
# Test average_legal_provisions()
# ============================================================================ #

class TestAverageLegalProvisions:
    def test_no_assessments(self, scorer):
        assert scorer.average_legal_provisions() == 0.0
    
    def test_single_assessment(self, scorer):
        scorer._assessment_history.append(create_assessment_result(legal_provisions=4))
        assert scorer.average_legal_provisions() == 4.0
    
    def test_multiple_assessments(self, scorer):
        scorer._assessment_history.extend([
            create_assessment_result(legal_provisions=2),
            create_assessment_result(legal_provisions=3),
            create_assessment_result(legal_provisions=7),
        ])
        # Average: (2 + 3 + 7) / 3 = 4.0
        assert abs(scorer.average_legal_provisions() - 4.0) < 0.01


# ============================================================================ #
# Test high_risk_percentage()
# ============================================================================ #

class TestHighRiskPercentage:
    def test_no_assessments(self, scorer):
        assert scorer.high_risk_percentage() == 0.0
    
    def test_no_high_risk(self, scorer):
        scorer._assessment_history.extend([
            create_assessment_result(level='minimal'),
            create_assessment_result(level='low'),
        ])
        assert scorer.high_risk_percentage() == 0.0
    
    def test_all_high_risk(self, scorer):
        scorer._assessment_history.extend([
            create_assessment_result(level='high'),
            create_assessment_result(level='high'),
        ])
        assert scorer.high_risk_percentage() == 100.0
    
    def test_mixed_risk_levels(self, scorer):
        scorer._assessment_history.extend([
            create_assessment_result(level='high'),
            create_assessment_result(level='low'),
            create_assessment_result(level='high'),
            create_assessment_result(level='medium'),
        ])
        # 2 high out of 4 = 50%
        assert abs(scorer.high_risk_percentage() - 50.0) < 0.01


# ============================================================================ #
# Test actionable_complaints_ratio()
# ============================================================================ #

class TestActionableComplaintsRatio:
    def test_no_assessments(self, scorer):
        assert scorer.actionable_complaints_ratio() == 0.0
    
    def test_no_actionable(self, scorer):
        scorer._assessment_history.extend([
            create_assessment_result(score=0),
            create_assessment_result(score=1),
        ])
        # threshold=2 by default, so scores 0,1 are not actionable
        assert scorer.actionable_complaints_ratio() == 0.0
    
    def test_all_actionable(self, scorer):
        scorer._assessment_history.extend([
            create_assessment_result(score=2),
            create_assessment_result(score=3),
        ])
        assert scorer.actionable_complaints_ratio() == 1.0
    
    def test_mixed_actionability(self, scorer):
        scorer._assessment_history.extend([
            create_assessment_result(score=0),
            create_assessment_result(score=2),
            create_assessment_result(score=1),
            create_assessment_result(score=3),
        ])
        # 2 out of 4 are >= 2, so ratio = 0.5
        assert abs(scorer.actionable_complaints_ratio() - 0.5) < 0.01
    
    def test_custom_threshold(self, scorer):
        scorer._assessment_history.extend([
            create_assessment_result(score=0),
            create_assessment_result(score=1),
            create_assessment_result(score=2),
            create_assessment_result(score=3),
        ])
        # With threshold=3, only 1 out of 4 is actionable
        assert abs(scorer.actionable_complaints_ratio(threshold=3) - 0.25) < 0.01


# ============================================================================ #
# Integration test
# ============================================================================ #

class TestBatch215Integration:
    def test_comprehensive_risk_scoring_analysis(self, scorer):
        """Test that all Batch 215 methods work together correctly."""
        # Populate with realistic assessment results
        scorer._assessment_history.extend([
            create_assessment_result(
                score=0,
                level='minimal',
                complaint_keywords=0,
                binding_keywords=0,
                legal_provisions=0,
                factors=[]
            ),
            create_assessment_result(
                score=1,
                level='low',
                complaint_keywords=2,
                binding_keywords=0,
                legal_provisions=1,
                factors=['Potential legal issues identified']
            ),
            create_assessment_result(
                score=2,
                level='medium',
                complaint_keywords=4,
                binding_keywords=2,
                legal_provisions=3,
                factors=['Complaint terms with binding language']
            ),
            create_assessment_result(
                score=3,
                level='high',
                complaint_keywords=8,
                binding_keywords=4,
                legal_provisions=6,
                factors=['Severe legal violations with binding authority']
            ),
            create_assessment_result(
                score=2,
                level='medium',
                complaint_keywords=3,
                binding_keywords=1,
                legal_provisions=4,
                factors=['Multiple legal provisions identified']
            ),
        ])
        
        # Test all Batch 215 methods
        assert scorer.total_assessments() == 5
        
        assert scorer.assessments_by_risk_level('minimal') == 1
        assert scorer.assessments_by_risk_level('low') == 1
        assert scorer.assessments_by_risk_level('medium') == 2
        assert scorer.assessments_by_risk_level('high') == 1
        
        dist = scorer.risk_level_distribution()
        assert dist == {'minimal': 1, 'low': 1, 'medium': 2, 'high': 1}
        
        # Average score: (0 + 1 + 2 + 3 + 2) / 5 = 1.6
        assert abs(scorer.average_risk_score() - 1.6) < 0.01
        
        assert scorer.maximum_risk_score() == 3
        
        # Average complaint keywords: (0 + 2 + 4 + 8 + 3) / 5 = 3.4
        assert abs(scorer.average_complaint_keywords() - 3.4) < 0.01
        
        # Average binding keywords: (0 + 0 + 2 + 4 + 1) / 5 = 1.4
        assert abs(scorer.average_binding_keywords() - 1.4) < 0.01
        
        # Average legal provisions: (0 + 1 + 3 + 6 + 4) / 5 = 2.8
        assert abs(scorer.average_legal_provisions() - 2.8) < 0.01
        
        # High risk percentage: 1 out of 5 = 20%
        assert abs(scorer.high_risk_percentage() - 20.0) < 0.01
        
        # Actionable (score >= 2): 3 out of 5 = 0.6
        assert abs(scorer.actionable_complaints_ratio() - 0.6) < 0.01
