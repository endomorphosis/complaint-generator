"""
Unit tests for Batch 212: ComplaintAnalyzer analysis methods.

Tests the 10 analysis tracking and statistics methods added to ComplaintAnalyzer.
"""

import pytest
from unittest.mock import Mock, patch
from complaint_analysis.analyzer import ComplaintAnalyzer


@pytest.fixture
def analyzer():
    """Create a ComplaintAnalyzer instance for testing."""
    return ComplaintAnalyzer()


def create_analysis_result(risk_score=1, risk_level='low', keywords=None, categories=None):
    """Helper to create a mock analysis result."""
    if keywords is None:
        keywords = []
    if categories is None:
        categories = []
    
    return {
        'legal_provisions': {},
        'citations': [],
        'categories': categories,
        'risk_score': risk_score,
        'risk_level': risk_level,
        'risk_factors': [],
        'recommendations': [],
        'keywords_found': keywords,
        'metadata': {}
    }


# ============================================================================ #
# Test total_analyses()
# ============================================================================ #

class TestTotalAnalyses:
    def test_no_analyses(self, analyzer):
        assert analyzer.total_analyses() == 0
    
    def test_after_manual_history_add(self, analyzer):
        analyzer._analysis_history.append(create_analysis_result())
        assert analyzer.total_analyses() == 1
    
    def test_multiple_analyses(self, analyzer):
        for i in range(5):
            analyzer._analysis_history.append(create_analysis_result())
        assert analyzer.total_analyses() == 5


# ============================================================================ #
# Test analyses_by_risk_level()
# ============================================================================ #

class TestAnalysesByRiskLevel:
    def test_no_analyses(self, analyzer):
        assert analyzer.analyses_by_risk_level('high') == 0
    
    def test_no_matching_level(self, analyzer):
        analyzer._analysis_history.append(create_analysis_result(risk_level='low'))
        assert analyzer.analyses_by_risk_level('high') == 0
    
    def test_single_matching_level(self, analyzer):
        analyzer._analysis_history.append(create_analysis_result(risk_level='high'))
        assert analyzer.analyses_by_risk_level('high') == 1
    
    def test_multiple_matching_levels(self, analyzer):
        analyzer._analysis_history.extend([
            create_analysis_result(risk_level='high'),
            create_analysis_result(risk_level='low'),
            create_analysis_result(risk_level='high'),
        ])
        assert analyzer.analyses_by_risk_level('high') == 2
        assert analyzer.analyses_by_risk_level('low') == 1


# ============================================================================ #
# Test risk_level_distribution()
# ============================================================================ #

class TestRiskLevelDistribution:
    def test_no_analyses(self, analyzer):
        assert analyzer.risk_level_distribution() == {}
    
    def test_single_level(self, analyzer):
        analyzer._analysis_history.extend([
            create_analysis_result(risk_level='low'),
            create_analysis_result(risk_level='low'),
        ])
        assert analyzer.risk_level_distribution() == {'low': 2}
    
    def test_multiple_levels(self, analyzer):
        analyzer._analysis_history.extend([
            create_analysis_result(risk_level='low'),
            create_analysis_result(risk_level='high'),
            create_analysis_result(risk_level='medium'),
            create_analysis_result(risk_level='high'),
        ])
        dist = analyzer.risk_level_distribution()
        assert dist == {'low': 1, 'high': 2, 'medium': 1}


# ============================================================================ #
# Test average_risk_score()
# ============================================================================ #

class TestAverageRiskScore:
    def test_no_analyses(self, analyzer):
        assert analyzer.average_risk_score() == 0.0
    
    def test_single_analysis(self, analyzer):
        analyzer._analysis_history.append(create_analysis_result(risk_score=3))
        assert analyzer.average_risk_score() == 3.0
    
    def test_multiple_analyses(self, analyzer):
        analyzer._analysis_history.extend([
            create_analysis_result(risk_score=2),
            create_analysis_result(risk_score=4),
            create_analysis_result(risk_score=6),
        ])
        # Average: (2 + 4 + 6) / 3 = 4.0
        assert abs(analyzer.average_risk_score() - 4.0) < 0.01


# ============================================================================ #
# Test highest_risk_score()
# ============================================================================ #

class TestHighestRiskScore:
    def test_no_analyses(self, analyzer):
        assert analyzer.highest_risk_score() == 0
    
    def test_single_analysis(self, analyzer):
        analyzer._analysis_history.append(create_analysis_result(risk_score=5))
        assert analyzer.highest_risk_score() == 5
    
    def test_multiple_analyses(self, analyzer):
        analyzer._analysis_history.extend([
            create_analysis_result(risk_score=2),
            create_analysis_result(risk_score=7),
            create_analysis_result(risk_score=4),
        ])
        assert analyzer.highest_risk_score() == 7


# ============================================================================ #
# Test most_common_keyword()
# ============================================================================ #

class TestMostCommonKeyword:
    def test_no_keywords(self, analyzer):
        assert analyzer.most_common_keyword() == 'none'
    
    def test_single_keyword(self, analyzer):
        analyzer._keyword_frequency = {'discrimination': 5}
        assert analyzer.most_common_keyword() == 'discrimination'
    
    def test_multiple_keywords(self, analyzer):
        analyzer._keyword_frequency = {
            'harassment': 3,
            'discrimination': 8,
            'retaliation': 2
        }
        assert analyzer.most_common_keyword() == 'discrimination'


# ============================================================================ #
# Test keyword_frequency()
# ============================================================================ #

class TestKeywordFrequency:
    def test_keyword_not_found(self, analyzer):
        assert analyzer.keyword_frequency('unknown') == 0
    
    def test_keyword_found(self, analyzer):
        analyzer._keyword_frequency = {'discrimination': 5}
        assert analyzer.keyword_frequency('discrimination') == 5
    
    def test_multiple_keywords(self, analyzer):
        analyzer._keyword_frequency = {
            'harassment': 3,
            'discrimination': 8
        }
        assert analyzer.keyword_frequency('harassment') == 3
        assert analyzer.keyword_frequency('discrimination') == 8


# ============================================================================ #
# Test total_unique_keywords()
# ============================================================================ #

class TestTotalUniqueKeywords:
    def test_no_keywords(self, analyzer):
        assert analyzer.total_unique_keywords() == 0
    
    def test_single_keyword(self, analyzer):
        analyzer._keyword_frequency = {'discrimination': 5}
        assert analyzer.total_unique_keywords() == 1
    
    def test_multiple_keywords(self, analyzer):
        analyzer._keyword_frequency = {
            'harassment': 3,
            'discrimination': 8,
            'retaliation': 2
        }
        assert analyzer.total_unique_keywords() == 3


# ============================================================================ #
# Test high_risk_percentage()
# ============================================================================ #

class TestHighRiskPercentage:
    def test_no_analyses(self, analyzer):
        assert analyzer.high_risk_percentage() == 0.0
    
    def test_no_high_risk(self, analyzer):
        analyzer._analysis_history.extend([
            create_analysis_result(risk_level='low'),
            create_analysis_result(risk_level='medium'),
        ])
        assert analyzer.high_risk_percentage() == 0.0
    
    def test_all_high_risk(self, analyzer):
        analyzer._analysis_history.extend([
            create_analysis_result(risk_level='high'),
            create_analysis_result(risk_level='high'),
        ])
        assert analyzer.high_risk_percentage() == 100.0
    
    def test_mixed_risk_levels(self, analyzer):
        analyzer._analysis_history.extend([
            create_analysis_result(risk_level='high'),
            create_analysis_result(risk_level='low'),
            create_analysis_result(risk_level='high'),
            create_analysis_result(risk_level='medium'),
        ])
        # 2 high out of 4 total = 50%
        assert abs(analyzer.high_risk_percentage() - 50.0) < 0.01


# ============================================================================ #
# Test categories_coverage()
# ============================================================================ #

class TestCategoriesCoverage:
    def test_no_analyses(self, analyzer):
        assert analyzer.categories_coverage() == 0
    
    def test_empty_categories(self, analyzer):
        analyzer._analysis_history.append(create_analysis_result(categories=[]))
        assert analyzer.categories_coverage() == 0
    
    def test_single_category(self, analyzer):
        analyzer._analysis_history.append(
            create_analysis_result(categories=['housing'])
        )
        assert analyzer.categories_coverage() == 1
    
    def test_duplicate_categories(self, analyzer):
        analyzer._analysis_history.extend([
            create_analysis_result(categories=['housing']),
            create_analysis_result(categories=['housing', 'discrimination']),
        ])
        # Unique categories: housing, discrimination = 2
        assert analyzer.categories_coverage() == 2
    
    def test_multiple_unique_categories(self, analyzer):
        analyzer._analysis_history.extend([
            create_analysis_result(categories=['housing', 'employment']),
            create_analysis_result(categories=['employment', 'consumer']),
            create_analysis_result(categories=['civil_rights']),
        ])
        # Unique: housing, employment, consumer, civil_rights = 4
        assert analyzer.categories_coverage() == 4


# ============================================================================ #
# Integration test
# ============================================================================ #

class TestBatch212Integration:
    def test_comprehensive_analyzer_tracking(self, analyzer):
        """Test that all Batch 212 methods work together correctly."""
        # Populate with realistic analysis results
        analyzer._analysis_history.extend([
            create_analysis_result(
                risk_score=2,
                risk_level='low',
                keywords=['tenant', 'lease'],
                categories=['housing']
            ),
            create_analysis_result(
                risk_score=5,
                risk_level='medium',
                keywords=['discrimination', 'protected_class'],
                categories=['housing', 'civil_rights']
            ),
            create_analysis_result(
                risk_score=8,
                risk_level='high',
                keywords=['discrimination', 'retaliation', 'harassment'],
                categories=['employment']
            ),
            create_analysis_result(
                risk_score=7,
                risk_level='high',
                keywords=['harassment', 'hostile_environment'],
                categories=['employment', 'civil_rights']
            ),
        ])
        
        # Populate keyword frequency
        analyzer._keyword_frequency = {
            'tenant': 1,
            'lease': 1,
            'discrimination': 2,
            'protected_class': 1,
            'retaliation': 1,
            'harassment': 2,
            'hostile_environment': 1
        }
        
        # Test all methods
        assert analyzer.total_analyses() == 4
        assert analyzer.analyses_by_risk_level('low') == 1
        assert analyzer.analyses_by_risk_level('medium') == 1
        assert analyzer.analyses_by_risk_level('high') == 2
        
        dist = analyzer.risk_level_distribution()
        assert dist == {'low': 1, 'medium': 1, 'high': 2}
        
        avg = analyzer.average_risk_score()
        # (2 + 5 + 8 + 7) / 4 = 5.5
        assert abs(avg - 5.5) < 0.01
        
        assert analyzer.highest_risk_score() == 8
        
        # Most common keywords: discrimination and harassment both have 2
        assert analyzer.most_common_keyword() in ['discrimination', 'harassment']
        
        assert analyzer.keyword_frequency('discrimination') == 2
        assert analyzer.keyword_frequency('harassment') == 2
        assert analyzer.keyword_frequency('tenant') == 1
        
        assert analyzer.total_unique_keywords() == 7
        
        high_pct = analyzer.high_risk_percentage()
        # 2 high out of 4 = 50%
        assert abs(high_pct - 50.0) < 0.01
        
        coverage = analyzer.categories_coverage()
        # Unique categories: housing, civil_rights, employment = 3
        assert coverage == 3
