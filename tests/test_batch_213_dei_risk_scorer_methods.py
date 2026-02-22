"""
Unit tests for Batch 213: DEIRiskScorer additional analysis methods.

Tests the 10 extended risk analysis and statistics methods added to DEIRiskScorer.
"""

import pytest
from complaint_analysis.dei_risk_scoring import DEIRiskScorer


@pytest.fixture
def scorer():
    """Create a DEIRiskScorer instance for testing."""
    return DEIRiskScorer()


def create_risk_result(score=0, level='compliant', dei_count=0, proxy_count=0,
                      binding_count=0, issues=None, flagged_keywords=None):
    """Helper to create a risk analysis result."""
    if issues is None:
        issues = []
    if flagged_keywords is None:
        flagged_keywords = {'dei': [], 'proxy': [], 'binding': []}
    
    return {
        'score': score,
        'level': level,
        'dei_count': dei_count,
        'proxy_count': proxy_count,
        'binding_count': binding_count,
        'issues': issues,
        'recommendations': [],
        'flagged_keywords': flagged_keywords
    }


# ============================================================================ #
# Test maximum_risk_score()
# ============================================================================ #

class TestMaximumRiskScore:
    def test_no_analyses(self, scorer):
        assert scorer.maximum_risk_score() == 0
    
    def test_single_analysis(self, scorer):
        scorer._analysis_history.append(create_risk_result(score=2))
        assert scorer.maximum_risk_score() == 2
    
    def test_multiple_analyses(self, scorer):
        scorer._analysis_history.extend([
            create_risk_result(score=1),
            create_risk_result(score=3),
            create_risk_result(score=2),
        ])
        assert scorer.maximum_risk_score() == 3


# ============================================================================ #
# Test minimum_risk_score()
# ============================================================================ #

class TestMinimumRiskScore:
    def test_no_analyses(self, scorer):
        assert scorer.minimum_risk_score() == 0
    
    def test_single_analysis(self, scorer):
        scorer._analysis_history.append(create_risk_result(score=2))
        assert scorer.minimum_risk_score() == 2
    
    def test_multiple_analyses(self, scorer):
        scorer._analysis_history.extend([
            create_risk_result(score=1),
            create_risk_result(score=3),
            create_risk_result(score=0),
        ])
        assert scorer.minimum_risk_score() == 0


# ============================================================================ #
# Test most_common_risk_level()
# ============================================================================ #

class TestMostCommonRiskLevel:
    def test_no_analyses(self, scorer):
        assert scorer.most_common_risk_level() == 'none'
    
    def test_single_level(self, scorer):
        scorer._analysis_history.append(create_risk_result(level='medium'))
        assert scorer.most_common_risk_level() == 'medium'
    
    def test_clear_winner(self, scorer):
        scorer._analysis_history.extend([
            create_risk_result(level='low'),
            create_risk_result(level='high'),
            create_risk_result(level='high'),
            create_risk_result(level='medium'),
        ])
        # 'high' appears twice, others once
        assert scorer.most_common_risk_level() == 'high'


# ============================================================================ #
# Test average_proxy_keyword_count()
# ============================================================================ #

class TestAverageProxyKeywordCount:
    def test_no_analyses(self, scorer):
        assert scorer.average_proxy_keyword_count() == 0.0
    
    def test_single_analysis(self, scorer):
        scorer._analysis_history.append(create_risk_result(proxy_count=5))
        assert scorer.average_proxy_keyword_count() == 5.0
    
    def test_multiple_analyses(self, scorer):
        scorer._analysis_history.extend([
            create_risk_result(proxy_count=2),
            create_risk_result(proxy_count=4),
            create_risk_result(proxy_count=6),
        ])
        # (2 + 4 + 6) / 3 = 4.0
        assert abs(scorer.average_proxy_keyword_count() - 4.0) < 0.01


# ============================================================================ #
# Test documents_with_issues()
# ============================================================================ #

class TestDocumentsWithIssues:
    def test_no_analyses(self, scorer):
        assert scorer.documents_with_issues() == 0
    
    def test_no_issues(self, scorer):
        scorer._analysis_history.extend([
            create_risk_result(issues=[]),
            create_risk_result(issues=[]),
        ])
        assert scorer.documents_with_issues() == 0
    
    def test_some_with_issues(self, scorer):
        scorer._analysis_history.extend([
            create_risk_result(issues=['Issue 1']),
            create_risk_result(issues=[]),
            create_risk_result(issues=['Issue 2', 'Issue 3']),
        ])
        assert scorer.documents_with_issues() == 2


# ============================================================================ #
# Test average_issues_per_document()
# ============================================================================ #

class TestAverageIssuesPerDocument:
    def test_no_analyses(self, scorer):
        assert scorer.average_issues_per_document() == 0.0
    
    def test_no_issues(self, scorer):
        scorer._analysis_history.extend([
            create_risk_result(issues=[]),
            create_risk_result(issues=[]),
        ])
        assert scorer.average_issues_per_document() == 0.0
    
    def test_with_issues(self, scorer):
        scorer._analysis_history.extend([
            create_risk_result(issues=['Issue 1']),
            create_risk_result(issues=['Issue 2', 'Issue 3']),
            create_risk_result(issues=[]),
        ])
        # Total: 1 + 2 + 0 = 3, avg = 3/3 = 1.0
        assert abs(scorer.average_issues_per_document() - 1.0) < 0.01


# ============================================================================ #
# Test most_flagged_dei_keyword()
# ============================================================================ #

class TestMostFlaggedDEIKeyword:
    def test_no_analyses(self, scorer):
        assert scorer.most_flagged_dei_keyword() == 'none'
    
    def test_no_keywords(self, scorer):
        scorer._analysis_history.append(
            create_risk_result(flagged_keywords={'dei': []})
        )
        assert scorer.most_flagged_dei_keyword() == 'none'
    
    def test_single_keyword(self, scorer):
        scorer._analysis_history.append(
            create_risk_result(flagged_keywords={'dei': ['diversity']})
        )
        assert scorer.most_flagged_dei_keyword() == 'diversity'
    
    def test_multiple_keywords(self, scorer):
        scorer._analysis_history.extend([
            create_risk_result(flagged_keywords={'dei': ['diversity', 'equity']}),
            create_risk_result(flagged_keywords={'dei': ['diversity']}),
            create_risk_result(flagged_keywords={'dei': ['inclusion', 'diversity']}),
        ])
        # 'diversity' appears 3 times, others once
        assert scorer.most_flagged_dei_keyword() == 'diversity'


# ============================================================================ #
# Test most_flagged_binding_keyword()
# ============================================================================ #

class TestMostFlaggedBindingKeyword:
    def test_no_analyses(self, scorer):
        assert scorer.most_flagged_binding_keyword() == 'none'
    
    def test_no_keywords(self, scorer):
        scorer._analysis_history.append(
            create_risk_result(flagged_keywords={'binding': []})
        )
        assert scorer.most_flagged_binding_keyword() == 'none'
    
    def test_single_keyword(self, scorer):
        scorer._analysis_history.append(
            create_risk_result(flagged_keywords={'binding': ['required']})
        )
        assert scorer.most_flagged_binding_keyword() == 'required'
    
    def test_multiple_keywords(self, scorer):
        scorer._analysis_history.extend([
            create_risk_result(flagged_keywords={'binding': ['required', 'mandatory']}),
            create_risk_result(flagged_keywords={'binding': ['required']}),
            create_risk_result(flagged_keywords={'binding': ['shall', 'required']}),
        ])
        # 'required' appears 3 times, others once
        assert scorer.most_flagged_binding_keyword() == 'required'


# ============================================================================ #
# Test score_variance()
# ============================================================================ #

class TestScoreVariance:
    def test_no_analyses(self, scorer):
        assert scorer.score_variance() == 0.0
    
    def test_uniform_scores(self, scorer):
        scorer._analysis_history.extend([
            create_risk_result(score=2),
            create_risk_result(score=2),
            create_risk_result(score=2),
        ])
        # All same score, variance = 0
        assert scorer.score_variance() == 0.0
    
    def test_varied_scores(self, scorer):
        scorer._analysis_history.extend([
            create_risk_result(score=0),
            create_risk_result(score=2),
            create_risk_result(score=4),
        ])
        # Mean = 2, variance = ((0-2)^2 + (2-2)^2 + (4-2)^2) / 3 = (4 + 0 + 4) / 3 = 8/3
        expected_variance = 8.0 / 3.0
        assert abs(scorer.score_variance() - expected_variance) < 0.01


# ============================================================================ #
# Test high_score_percentage()
# ============================================================================ #

class TestHighScorePercentage:
    def test_no_analyses(self, scorer):
        assert scorer.high_score_percentage() == 0.0
    
    def test_no_high_scores(self, scorer):
        scorer._analysis_history.extend([
            create_risk_result(score=0),
            create_risk_result(score=1),
        ])
        assert scorer.high_score_percentage() == 0.0
    
    def test_all_high_scores(self, scorer):
        scorer._analysis_history.extend([
            create_risk_result(score=2),
            create_risk_result(score=3),
        ])
        assert scorer.high_score_percentage() == 100.0
    
    def test_mixed_scores(self, scorer):
        scorer._analysis_history.extend([
            create_risk_result(score=0),
            create_risk_result(score=1),
            create_risk_result(score=2),
            create_risk_result(score=3),
        ])
        # 2 out of 4 are >= 2, so 50%
        assert abs(scorer.high_score_percentage() - 50.0) < 0.01


# ============================================================================ #
# Integration test
# ============================================================================ #

class TestBatch213Integration:
    def test_comprehensive_dei_risk_analysis(self, scorer):
        """Test that all Batch 213 methods work together correctly."""
        # Populate with realistic risk analysis results
        scorer._analysis_history.extend([
            create_risk_result(
                score=0,
                level='compliant',
                dei_count=0,
                proxy_count=0,
                binding_count=0,
                issues=[],
                flagged_keywords={'dei': [], 'proxy': [], 'binding': []}
            ),
            create_risk_result(
                score=1,
                level='low',
                dei_count=2,
                proxy_count=1,
                binding_count=0,
                issues=['Possible DEI reference'],
                flagged_keywords={'dei': ['diversity'], 'proxy': ['cultural competence'], 'binding': []}
            ),
            create_risk_result(
                score=2,
                level='medium',
                dei_count=3,
                proxy_count=2,
                binding_count=2,
                issues=['DEI requirement', 'Binding language present'],
                flagged_keywords={'dei': ['diversity', 'equity'], 'proxy': ['lived experience'], 'binding': ['required', 'shall']}
            ),
            create_risk_result(
                score=3,
                level='high',
                dei_count=5,
                proxy_count=3,
                binding_count=4,
                issues=['Clear DEI mandate', 'Enforcement language', 'Compliance required'],
                flagged_keywords={'dei': ['diversity', 'equity', 'inclusion'], 'proxy': ['cultural fit'], 'binding': ['required', 'mandatory']}
            ),
            create_risk_result(
                score=2,
                level='medium',
                dei_count=2,
                proxy_count=1,
                binding_count=3,
                issues=['DEI language', 'Policy requirement'],
                flagged_keywords={'dei': ['diversity'], 'proxy': [], 'binding': ['required', 'must']}
            ),
        ])
        
        # Test all Batch 213 methods
        assert scorer.maximum_risk_score() == 3
        assert scorer.minimum_risk_score() == 0
        
        # 'medium' appears twice, others once
        assert scorer.most_common_risk_level() == 'medium'
        
        # Average proxy count: (0 + 1 + 2 + 3 + 1) / 5 = 1.4
        assert abs(scorer.average_proxy_keyword_count() - 1.4) < 0.01
        
        # 4 out of 5 have issues
        assert scorer.documents_with_issues() == 4
        
        # Total issues: 0 + 1 + 2 + 3 + 2 = 8, avg = 8/5 = 1.6
        assert abs(scorer.average_issues_per_document() - 1.6) < 0.01
        
        # 'diversity' appears 4 times
        assert scorer.most_flagged_dei_keyword() == 'diversity'
        
        # 'required' appears 3 times
        assert scorer.most_flagged_binding_keyword() == 'required'
        
        # Score variance
        # Scores: 0, 1, 2, 3, 2
        # Mean: 1.6
        # Variance: ((0-1.6)^2 + (1-1.6)^2 + (2-1.6)^2 + (3-1.6)^2 + (2-1.6)^2) / 5
        #         = (2.56 + 0.36 + 0.16 + 1.96 + 0.16) / 5
        #         = 5.2 / 5 = 1.04
        assert abs(scorer.score_variance() - 1.04) < 0.01
        
        # High score percentage: 3 out of 5 are >= 2, so 60%
        assert abs(scorer.high_score_percentage() - 60.0) < 0.01
