"""
Unit tests for Batch 214: KeywordRegistry analysis methods.

Tests the 10 keyword registry analysis and statistics methods.
"""

import pytest
from complaint_analysis.keywords import KeywordRegistry


@pytest.fixture
def registry():
    """Create a fresh KeywordRegistry instance for testing."""
    return KeywordRegistry()


# ============================================================================ #
# Test total_categories()
# ============================================================================ #

class TestTotalCategories:
    def test_empty_registry(self, registry):
        assert registry.total_categories() == 0
    
    def test_single_category(self, registry):
        registry.register_keywords('complaint', ['keyword1'])
        assert registry.total_categories() == 1
    
    def test_multiple_categories(self, registry):
        registry.register_keywords('complaint', ['kw1'])
        registry.register_keywords('evidence', ['kw2'])
        registry.register_keywords('legal', ['kw3'])
        assert registry.total_categories() == 3


# ============================================================================ #
# Test total_keywords_in_category()
# ============================================================================ #

class TestTotalKeywordsInCategory:
    def test_nonexistent_category(self, registry):
        assert registry.total_keywords_in_category('nonexistent') == 0
    
    def test_single_keyword(self, registry):
        registry.register_keywords('complaint', ['fraud'])
        assert registry.total_keywords_in_category('complaint') == 1
    
    def test_multiple_keywords_same_type(self, registry):
        registry.register_keywords('complaint', ['fraud', 'deception', 'scam'])
        assert registry.total_keywords_in_category('complaint') == 3
    
    def test_global_and_type_specific(self, registry):
        registry.register_keywords('complaint', ['global1', 'global2'])  # Global
        registry.register_keywords('complaint', ['housing1', 'housing2'], complaint_type='housing')
        # Total unique: global1, global2, housing1, housing2 = 4
        assert registry.total_keywords_in_category('complaint') == 4
    
    def test_overlapping_keywords(self, registry):
        registry.register_keywords('complaint', ['shared', 'global'])
        registry.register_keywords('complaint', ['shared', 'specific'], complaint_type='housing')
        # Unique: shared, global, specific = 3
        assert registry.total_keywords_in_category('complaint') == 3


# ============================================================================ #
# Test category_with_most_keywords()
# ============================================================================ #

class TestCategoryWithMostKeywords:
    def test_empty_registry(self, registry):
        assert registry.category_with_most_keywords() == 'none'
    
    def test_single_category(self, registry):
        registry.register_keywords('complaint', ['kw1', 'kw2'])
        assert registry.category_with_most_keywords() == 'complaint'
    
    def test_clear_winner(self, registry):
        registry.register_keywords('complaint', ['kw1', 'kw2', 'kw3'])
        registry.register_keywords('evidence', ['kw4'])
        registry.register_keywords('legal', ['kw5', 'kw6'])
        # complaint has 3, legal has 2, evidence has 1
        assert registry.category_with_most_keywords() == 'complaint'


# ============================================================================ #
# Test keywords_by_type()
# ============================================================================ #

class TestKeywordsByType:
    def test_nonexistent_type(self, registry):
        registry.register_keywords('complaint', ['kw1'])
        assert registry.keywords_by_type('housing') == {}
    
    def test_single_category_with_type(self, registry):
        registry.register_keywords('complaint', ['housing1', 'housing2'], complaint_type='housing')
        result = registry.keywords_by_type('housing')
        assert result == {'complaint': 2}
    
    def test_multiple_categories_with_type(self, registry):
        registry.register_keywords('complaint', ['h1', 'h2'], complaint_type='housing')
        registry.register_keywords('evidence', ['e1'], complaint_type='housing')
        registry.register_keywords('legal', ['l1', 'l2', 'l3'], complaint_type='housing')
        result = registry.keywords_by_type('housing')
        assert result == {'complaint': 2, 'evidence': 1, 'legal': 3}


# ============================================================================ #
# Test global_keywords_count()
# ============================================================================ #

class TestGlobalKeywordsCount:
    def test_no_keywords(self, registry):
        assert registry.global_keywords_count() == 0
    
    def test_only_global_keywords(self, registry):
        registry.register_keywords('complaint', ['kw1', 'kw2'])
        registry.register_keywords('evidence', ['kw3'])
        # 2 + 1 = 3 global keywords
        assert registry.global_keywords_count() == 3
    
    def test_mixed_global_and_specific(self, registry):
        registry.register_keywords('complaint', ['global1', 'global2'])  # Global
        registry.register_keywords('complaint', ['specific1'], complaint_type='housing')  # Type-specific
        # Only 2 global keywords
        assert registry.global_keywords_count() == 2


# ============================================================================ #
# Test type_specific_keywords_count()
# ============================================================================ #

class TestTypeSpecificKeywordsCount:
    def test_no_keywords(self, registry):
        assert registry.type_specific_keywords_count() == 0
    
    def test_only_global_keywords(self, registry):
        registry.register_keywords('complaint', ['kw1', 'kw2'])
        assert registry.type_specific_keywords_count() == 0
    
    def test_only_type_specific(self, registry):
        registry.register_keywords('complaint', ['h1', 'h2'], complaint_type='housing')
        registry.register_keywords('evidence', ['e1'], complaint_type='employment')
        # 2 + 1 = 3 type-specific
        assert registry.type_specific_keywords_count() == 3
    
    def test_mixed_global_and_specific(self, registry):
        registry.register_keywords('complaint', ['global1'])  # Global
        registry.register_keywords('complaint', ['h1', 'h2'], complaint_type='housing')
        registry.register_keywords('evidence', ['e1'], complaint_type='employment')
        # 2 + 1 = 3 type-specific
        assert registry.type_specific_keywords_count() == 3


# ============================================================================ #
# Test has_keywords_for_type()
# ============================================================================ #

class TestHasKeywordsForType:
    def test_empty_registry(self, registry):
        assert registry.has_keywords_for_type('housing') is False
    
    def test_type_exists(self, registry):
        registry.register_keywords('complaint', ['h1'], complaint_type='housing')
        assert registry.has_keywords_for_type('housing') is True
    
    def test_type_does_not_exist(self, registry):
        registry.register_keywords('complaint', ['h1'], complaint_type='housing')
        assert registry.has_keywords_for_type('employment') is False
    
    def test_multiple_categories_with_type(self, registry):
        registry.register_keywords('complaint', ['h1'], complaint_type='housing')
        registry.register_keywords('evidence', ['h2'], complaint_type='housing')
        assert registry.has_keywords_for_type('housing') is True


# ============================================================================ #
# Test average_keywords_per_category()
# ============================================================================ #

class TestAverageKeywordsPerCategory:
    def test_empty_registry(self, registry):
        assert registry.average_keywords_per_category() == 0.0
    
    def test_single_category(self, registry):
        registry.register_keywords('complaint', ['kw1', 'kw2', 'kw3'])
        assert registry.average_keywords_per_category() == 3.0
    
    def test_multiple_categories(self, registry):
        registry.register_keywords('complaint', ['kw1', 'kw2'])  # 2
        registry.register_keywords('evidence', ['kw3', 'kw4', 'kw5', 'kw6'])  # 4
        registry.register_keywords('legal', ['kw7'])  # 1
        # Average: (2 + 4 + 1) / 3 = 7/3 ≈ 2.33
        assert abs(registry.average_keywords_per_category() - (7/3)) < 0.01


# ============================================================================ #
# Test categories_with_type_specific_keywords()
# ============================================================================ #

class TestCategoriesWithTypeSpecificKeywords:
    def test_empty_registry(self, registry):
        assert registry.categories_with_type_specific_keywords() == 0
    
    def test_only_global_keywords(self, registry):
        registry.register_keywords('complaint', ['kw1'])
        registry.register_keywords('evidence', ['kw2'])
        assert registry.categories_with_type_specific_keywords() == 0
    
    def test_some_type_specific(self, registry):
        registry.register_keywords('complaint', ['global1'])  # Global only
        registry.register_keywords('evidence', ['e1'], complaint_type='employment')  # Has type-specific
        registry.register_keywords('legal', ['l1'], complaint_type='housing')  # Has type-specific
        # 2 categories have type-specific keywords
        assert registry.categories_with_type_specific_keywords() == 2
    
    def test_all_type_specific(self, registry):
        registry.register_keywords('complaint', ['h1'], complaint_type='housing')
        registry.register_keywords('evidence', ['e1'], complaint_type='employment')
        assert registry.categories_with_type_specific_keywords() == 2


# ============================================================================ #
# Test keyword_coverage_ratio()
# ============================================================================ #

class TestKeywordCoverageRatio:
    def test_empty_registry(self, registry):
        assert registry.keyword_coverage_ratio() == 0.0
    
    def test_only_global(self, registry):
        registry.register_keywords('complaint', ['kw1', 'kw2'])
        # 0 type-specific / 2 total = 0.0
        assert registry.keyword_coverage_ratio() == 0.0
    
    def test_only_type_specific(self, registry):
        registry.register_keywords('complaint', ['h1', 'h2'], complaint_type='housing')
        # 2 type-specific / 2 total = 1.0
        assert registry.keyword_coverage_ratio() == 1.0
    
    def test_mixed(self, registry):
        registry.register_keywords('complaint', ['global1', 'global2'])  # 2 global
        registry.register_keywords('complaint', ['h1', 'h2'], complaint_type='housing')  # 2 type-specific
        # 2 type-specific / 4 total = 0.5
        assert abs(registry.keyword_coverage_ratio() - 0.5) < 0.01


# ============================================================================ #
# Integration test
# ============================================================================ #

class TestBatch214Integration:
    def test_comprehensive_keyword_registry_analysis(self, registry):
        """Test that all Batch 214 methods work together correctly."""
        # Populate registry with realistic data
        # Global keywords
        registry.register_keywords('complaint', ['fraud', 'deception'])
        registry.register_keywords('evidence', ['document', 'witness'])
        
        # Housing-specific
        registry.register_keywords('complaint', ['landlord', 'tenant', 'lease'], complaint_type='housing')
        registry.register_keywords('evidence', ['inspection_report'], complaint_type='housing')
        
        # Employment-specific
        registry.register_keywords('complaint', ['employer', 'harassment'], complaint_type='employment')
        registry.register_keywords('legal', ['title_vii', 'ada'], complaint_type='employment')
        
        # Consumer-specific
        registry.register_keywords('complaint', ['warranty', 'refund'], complaint_type='consumer')
        
        # Test all methods
        assert registry.total_categories() == 3  # complaint, evidence, legal
        
        # Complaint: fraud, deception, landlord, tenant, lease, employer, harassment, warranty, refund = 9 unique
        assert registry.total_keywords_in_category('complaint') == 9
        # Evidence: document, witness, inspection_report = 3
        assert registry.total_keywords_in_category('evidence') == 3
        # Legal: title_vii, ada = 2
        assert registry.total_keywords_in_category('legal') == 2
        
        assert registry.category_with_most_keywords() == 'complaint'
        
        housing_kws = registry.keywords_by_type('housing')
        assert housing_kws == {'complaint': 3, 'evidence': 1}
        
        employment_kws = registry.keywords_by_type('employment')
        assert employment_kws == {'complaint': 2, 'legal': 2}
        
        # Global: fraud, deception, document, witness = 4
        assert registry.global_keywords_count() == 4
        
        # Type-specific: 3 (housing complaint) + 1 (housing evidence) + 2 (employment complaint) 
        #                + 2 (employment legal) + 2 (consumer complaint) = 10
        assert registry.type_specific_keywords_count() == 10
        
        assert registry.has_keywords_for_type('housing') is True
        assert registry.has_keywords_for_type('employment') is True
        assert registry.has_keywords_for_type('consumer') is True
        assert registry.has_keywords_for_type('civil_rights') is False
        
        # Average: (9 + 3 + 2) / 3 = 14/3 ≈ 4.67
        assert abs(registry.average_keywords_per_category() - (14/3)) < 0.01
        
        # All 3 categories have type-specific keywords
        assert registry.categories_with_type_specific_keywords() == 3
        
        # Coverage: 10 type-specific / 14 total ≈ 0.714
        assert abs(registry.keyword_coverage_ratio() - (10/14)) < 0.01
