"""
Unit tests for Batch 216: PromptLibrary analysis methods.

Tests the 10 template library management and statistics methods added to PromptLibrary.
"""

import pytest
from complaint_analysis.prompt_templates import PromptLibrary, PromptTemplate, ReturnFormat


@pytest.fixture
def library():
    """Create a PromptLibrary instance for testing."""
    return PromptLibrary()


@pytest.fixture
def minimal_library():
    """Create a PromptLibrary without default templates."""
    lib = PromptLibrary()
    lib.templates.clear()
    lib._template_usage_count.clear()
    lib._format_history.clear()
    return lib


def create_template(name='test', format_type=ReturnFormat.JSON, warnings=None):
    """Helper to create a PromptTemplate for testing."""
    if warnings is None:
        warnings = []
    
    return PromptTemplate(
        name=name,
        system_prompt="Test system prompt",
        return_format="Test return format",
        return_format_type=format_type,
        warnings=warnings,
        payload_template="Test payload: {data}"
    )


# ============================================================================ #
# Test total_templates()
# ============================================================================ #

class TestTotalTemplates:
    def test_default_templates_exist(self, library):
        # PromptLibrary initializes with 9 default templates
        assert library.total_templates() == 9
    
    def test_empty_library(self, minimal_library):
        assert minimal_library.total_templates() == 0
    
    def test_after_registration(self, minimal_library):
        minimal_library.register_template(create_template('t1'))
        minimal_library.register_template(create_template('t2'))
        assert minimal_library.total_templates() == 2


# ============================================================================ #
# Test templates_by_format_type()
# ============================================================================ #

class TestTemplatesByFormatType:
    def test_with_default_templates(self, library):
        # Most default templates use JSON
        json_count = library.templates_by_format_type(ReturnFormat.JSON)
        assert json_count > 0
    
    def test_no_matching_type(self, minimal_library):
        minimal_library.register_template(create_template('t1', ReturnFormat.JSON))
        assert minimal_library.templates_by_format_type(ReturnFormat.MARKDOWN) == 0
    
    def test_mixed_formats(self, minimal_library):
        minimal_library.register_template(create_template('t1', ReturnFormat.JSON))
        minimal_library.register_template(create_template('t2', ReturnFormat.JSON))
        minimal_library.register_template(create_template('t3', ReturnFormat.MARKDOWN))
        
        assert minimal_library.templates_by_format_type(ReturnFormat.JSON) == 2
        assert minimal_library.templates_by_format_type(ReturnFormat.MARKDOWN) == 1


# ============================================================================ #
# Test format_type_distribution()
# ============================================================================ #

class TestFormatTypeDistribution:
    def test_empty_library(self, minimal_library):
        assert minimal_library.format_type_distribution() == {}
    
    def test_single_format(self, minimal_library):
        minimal_library.register_template(create_template('t1', ReturnFormat.JSON))
        minimal_library.register_template(create_template('t2', ReturnFormat.JSON))
        
        dist = minimal_library.format_type_distribution()
        assert dist == {'json': 2}
    
    def test_multiple_formats(self, minimal_library):
        minimal_library.register_template(create_template('t1', ReturnFormat.JSON))
        minimal_library.register_template(create_template('t2', ReturnFormat.MARKDOWN))
        minimal_library.register_template(create_template('t3', ReturnFormat.JSON))
        minimal_library.register_template(create_template('t4', ReturnFormat.PLAIN_TEXT))
        
        dist = minimal_library.format_type_distribution()
        assert dist == {'json': 2, 'markdown': 1, 'plain_text': 1}


# ============================================================================ #
# Test templates_with_warnings()
# ============================================================================ #

class TestTemplatesWithWarnings:
    def test_with_default_templates(self, library):
        # Default templates should have warnings
        assert library.templates_with_warnings() > 0
    
    def test_no_warnings(self, minimal_library):
        minimal_library.register_template(create_template('t1', warnings=[]))
        minimal_library.register_template(create_template('t2', warnings=[]))
        assert minimal_library.templates_with_warnings() == 0
    
    def test_mixed_warnings(self, minimal_library):
        minimal_library.register_template(create_template('t1', warnings=['w1']))
        minimal_library.register_template(create_template('t2', warnings=[]))
        minimal_library.register_template(create_template('t3', warnings=['w2', 'w3']))
        
        assert minimal_library.templates_with_warnings() == 2


# ============================================================================ #
# Test average_warnings_per_template()
# ============================================================================ #

class TestAverageWarningsPerTemplate:
    def test_empty_library(self, minimal_library):
        assert minimal_library.average_warnings_per_template() == 0.0
    
    def test_no_warnings(self, minimal_library):
        minimal_library.register_template(create_template('t1', warnings=[]))
        minimal_library.register_template(create_template('t2', warnings=[]))
        assert minimal_library.average_warnings_per_template() == 0.0
    
    def test_mixed_warnings(self, minimal_library):
        minimal_library.register_template(create_template('t1', warnings=['w1', 'w2']))
        minimal_library.register_template(create_template('t2', warnings=[]))
        minimal_library.register_template(create_template('t3', warnings=['w3']))
        
        # Total warnings: 2 + 0 + 1 = 3, Average: 3 / 3 = 1.0
        assert abs(minimal_library.average_warnings_per_template() - 1.0) < 0.01


# ============================================================================ #
# Test maximum_warnings_count()
# ============================================================================ #

class TestMaximumWarningsCount:
    def test_empty_library(self, minimal_library):
        assert minimal_library.maximum_warnings_count() == 0
    
    def test_single_template(self, minimal_library):
        minimal_library.register_template(create_template('t1', warnings=['w1', 'w2', 'w3']))
        assert minimal_library.maximum_warnings_count() == 3
    
    def test_multiple_templates(self, minimal_library):
        minimal_library.register_template(create_template('t1', warnings=['w1']))
        minimal_library.register_template(create_template('t2', warnings=['w1', 'w2', 'w3', 'w4']))
        minimal_library.register_template(create_template('t3', warnings=['w1', 'w2']))
        
        assert minimal_library.maximum_warnings_count() == 4


# ============================================================================ #
# Test warning_coverage_percentage()
# ============================================================================ #

class TestWarningCoveragePercentage:
    def test_empty_library(self, minimal_library):
        assert minimal_library.warning_coverage_percentage() == 0.0
    
    def test_no_warnings(self, minimal_library):
        minimal_library.register_template(create_template('t1', warnings=[]))
        minimal_library.register_template(create_template('t2', warnings=[]))
        assert minimal_library.warning_coverage_percentage() == 0.0
    
    def test_all_have_warnings(self, minimal_library):
        minimal_library.register_template(create_template('t1', warnings=['w1']))
        minimal_library.register_template(create_template('t2', warnings=['w2']))
        assert minimal_library.warning_coverage_percentage() == 100.0
    
    def test_partial_coverage(self, minimal_library):
        minimal_library.register_template(create_template('t1', warnings=['w1']))
        minimal_library.register_template(create_template('t2', warnings=[]))
        minimal_library.register_template(create_template('t3', warnings=['w2']))
        minimal_library.register_template(create_template('t4', warnings=[]))
        
        # 2 out of 4 have warnings = 50%
        assert abs(minimal_library.warning_coverage_percentage() - 50.0) < 0.01


# ============================================================================ #
# Test most_common_format_type()
# ============================================================================ #

class TestMostCommonFormatType:
    def test_empty_library(self, minimal_library):
        assert minimal_library.most_common_format_type() is None
    
    def test_single_format(self, minimal_library):
        minimal_library.register_template(create_template('t1', ReturnFormat.JSON))
        assert minimal_library.most_common_format_type() == 'json'
    
    def test_multiple_formats(self, minimal_library):
        minimal_library.register_template(create_template('t1', ReturnFormat.JSON))
        minimal_library.register_template(create_template('t2', ReturnFormat.MARKDOWN))
        minimal_library.register_template(create_template('t3', ReturnFormat.JSON))
        minimal_library.register_template(create_template('t4', ReturnFormat.JSON))
        
        assert minimal_library.most_common_format_type() == 'json'


# ============================================================================ #
# Test total_format_operations()
# ============================================================================ #

class TestTotalFormatOperations:
    def test_no_operations(self, minimal_library):
        assert minimal_library.total_format_operations() == 0
    
    def test_after_formatting(self, minimal_library):
        minimal_library.register_template(create_template('t1'))
        minimal_library.format_prompt('t1', {'data': 'test'})
        assert minimal_library.total_format_operations() == 1
    
    def test_multiple_operations(self, minimal_library):
        minimal_library.register_template(create_template('t1'))
        minimal_library.register_template(create_template('t2'))
        
        minimal_library.format_prompt('t1', {'data': 'test1'})
        minimal_library.format_prompt('t2', {'data': 'test2'})
        minimal_library.format_prompt('t1', {'data': 'test3'})
        
        assert minimal_library.total_format_operations() == 3


# ============================================================================ #
# Test most_used_template()
# ============================================================================ #

class TestMostUsedTemplate:
    def test_no_usage(self, minimal_library):
        minimal_library.register_template(create_template('t1'))
        assert minimal_library.most_used_template() is None
    
    def test_single_template_used(self, minimal_library):
        minimal_library.register_template(create_template('t1'))
        minimal_library.format_prompt('t1', {'data': 'test'})
        assert minimal_library.most_used_template() == 't1'
    
    def test_multiple_templates_used(self, minimal_library):
        minimal_library.register_template(create_template('t1'))
        minimal_library.register_template(create_template('t2'))
        minimal_library.register_template(create_template('t3'))
        
        minimal_library.format_prompt('t1', {'data': 'test'})
        minimal_library.format_prompt('t2', {'data': 'test'})
        minimal_library.format_prompt('t1', {'data': 'test'})
        minimal_library.format_prompt('t3', {'data': 'test'})
        minimal_library.format_prompt('t1', {'data': 'test'})
        
        # t1 used 3 times, t2 1 time, t3 1 time
        assert minimal_library.most_used_template() == 't1'


# ============================================================================ #
# Integration test
# ============================================================================ #

class TestBatch216Integration:
    def test_comprehensive_template_library_analysis(self, minimal_library):
        """Test that all Batch 216 methods work together correctly."""
        # Populate library with templates
        minimal_library.register_template(create_template(
            'extract_entities',
            ReturnFormat.JSON,
            warnings=['warn1', 'warn2', 'warn3']
        ))
        minimal_library.register_template(create_template(
            'extract_relationships',
            ReturnFormat.JSON,
            warnings=['warn1', 'warn2']
        ))
        minimal_library.register_template(create_template(
            'generate_summary',
            ReturnFormat.STRUCTURED_TEXT,
            warnings=[]
        ))
        minimal_library.register_template(create_template(
            'assess_viability',
            ReturnFormat.JSON,
            warnings=['warn1', 'warn2', 'warn3', 'warn4']
        ))
        
        # Use some templates
        minimal_library.format_prompt('extract_entities', {'data': 'test1'})
        minimal_library.format_prompt('extract_entities', {'data': 'test2'})
        minimal_library.format_prompt('extract_relationships', {'data': 'test3'})
        
        # Test all Batch 216 methods
        assert minimal_library.total_templates() == 4
        
        assert minimal_library.templates_by_format_type(ReturnFormat.JSON) == 3
        assert minimal_library.templates_by_format_type(ReturnFormat.STRUCTURED_TEXT) == 1
        
        dist = minimal_library.format_type_distribution()
        assert dist == {'json': 3, 'structured_text': 1}
        
        # 3 out of 4 have warnings
        assert minimal_library.templates_with_warnings() == 3
        
        # Average warnings: (3 + 2 + 0 + 4) / 4 = 2.25
        assert abs(minimal_library.average_warnings_per_template() - 2.25) < 0.01
        
        assert minimal_library.maximum_warnings_count() == 4
        
        # 3 out of 4 have warnings = 75%
        assert abs(minimal_library.warning_coverage_percentage() - 75.0) < 0.01
        
        assert minimal_library.most_common_format_type() == 'json'
        
        assert minimal_library.total_format_operations() == 3
        
        assert minimal_library.most_used_template() == 'extract_entities'
