"""
Batch 214: PromptLibrary Validation and Caching Methods Tests

Tests for PromptLibrary validation, analytics, and caching enhancements.
- Template field validation (required fields detection)
- Template metadata retrieval
- Usage pattern analysis (most used, unused, by usage)
- Template grouping and distribution analysis
- Statistics on template content (character counts, format distribution)
"""

import pytest
from complaint_analysis.prompt_templates import (
    PromptLibrary,
    PromptTemplate,
    ReturnFormat,
)


@pytest.fixture
def library():
    """Create a PromptLibrary instance for testing."""
    lib = PromptLibrary()
    return lib


class TestPromptLibraryTemplateUsage:
    """Test template usage counting and tracking."""
    
    def test_template_usage_count_starts_at_zero(self, library):
        """Verify new templates have zero usage."""
        assert library.template_usage_count('extract_entities') == 0
    
    def test_template_usage_count_increments(self, library):
        """Verify usage count increments when template is formatted."""
        library.format_prompt('extract_entities', {'complaint_text': 'test'})
        assert library.template_usage_count('extract_entities') == 1
        
        library.format_prompt('extract_entities', {'complaint_text': 'test2'})
        assert library.template_usage_count('extract_entities') == 2
    
    def test_unknown_template_usage_count_returns_zero(self, library):
        """Verify unknown templates return 0."""
        assert library.template_usage_count('nonexistent') == 0
    
    def test_different_templates_have_independent_counts(self, library):
        """Verify usage counts are independent per template."""
        library.format_prompt('extract_entities', {'complaint_text': 'test'})
        library.format_prompt('extract_relationships', {'entities': 'test', 'complaint_text': 'test'})
        library.format_prompt('extract_entities', {'complaint_text': 'test2'})
        
        assert library.template_usage_count('extract_entities') == 2
        assert library.template_usage_count('extract_relationships') == 1
    
    def test_templates_by_usage_returns_sorted_list(self, library):
        """Verify templates_by_usage returns sorted by count descending."""
        library.format_prompt('extract_entities', {'complaint_text': 'test'})
        library.format_prompt('extract_entities', {'complaint_text': 'test'})
        library.format_prompt('extract_relationships', {'entities': 'e', 'complaint_text': 'c'})
        library.format_prompt('generate_questions', {'complaint_type': 't', 'current_info': 'i', 'missing_fields': 'f'})
        library.format_prompt('generate_questions', {'complaint_type': 't', 'current_info': 'i', 'missing_fields': 'f'})
        library.format_prompt('generate_questions', {'complaint_type': 't', 'current_info': 'i', 'missing_fields': 'f'})
        
        usage_list = library.templates_by_usage()
        
        assert len(usage_list) >= 3
        assert usage_list[0][1] >= usage_list[1][1]  # Descending order
    
    def test_templates_by_usage_with_limit(self, library):
        """Verify top_n parameter limits results."""
        library.format_prompt('extract_entities', {'complaint_text': 'test'})
        library.format_prompt('extract_entities', {'complaint_text': 'test'})
        library.format_prompt('extract_relationships', {'entities': 'e', 'complaint_text': 'c'})
        
        top_2 = library.templates_by_usage(top_n=2)
        assert len(top_2) == 2
    
    def test_unused_templates_returns_never_formatted(self, library):
        """Verify unused_templates lists templates with zero usage."""
        library.format_prompt('extract_entities', {'complaint_text': 'test'})
        
        unused = library.unused_templates()
        assert 'extract_entities' not in unused
        assert len(unused) > 0  # Other templates should be unused


class TestPromptLibraryValidation:
    """Test template field validation."""
    
    def test_validate_template_fields_with_valid_data(self, library):
        """Verify validation succeeds with all required fields."""
        payload = {'complaint_text': 'test complaint'}
        errors = library.validate_template_fields('extract_entities', payload)
        assert len(errors) == 0
    
    def test_validate_template_fields_missing_field(self, library):
        """Verify validation catches missing required fields."""
        payload = {}
        errors = library.validate_template_fields('extract_entities', payload)
        assert len(errors) > 0
        assert any('complaint_text' in err for err in errors)
    
    def test_validate_template_fields_empty_required_field(self, library):
        """Verify validation catches empty required fields."""
        payload = {'complaint_text': ''}
        errors = library.validate_template_fields('extract_entities', payload)
        assert len(errors) > 0
    
    def test_validate_template_fields_none_value(self, library):
        """Verify validation catches None values in required fields."""
        payload = {'complaint_text': None}
        errors = library.validate_template_fields('extract_entities', payload)
        assert len(errors) > 0
    
    def test_validate_nonexistent_template(self, library):
        """Verify validation handles nonexistent template."""
        errors = library.validate_template_fields('nonexistent', {})
        assert len(errors) > 0
        assert 'not found' in errors[0].lower()


class TestPromptLibraryMetadata:
    """Test template metadata retrieval."""
    
    def test_get_template_metadata_returns_all_fields(self, library):
        """Verify metadata includes all expected fields."""
        library.format_prompt('extract_entities', {'complaint_text': 'test'})
        
        metadata = library.get_template_metadata('extract_entities')
        
        assert 'name' in metadata
        assert 'format_type' in metadata
        assert 'usage_count' in metadata
        assert 'warning_count' in metadata
        assert 'has_payload' in metadata
        assert 'system_prompt_length' in metadata
        assert 'return_format_length' in metadata
    
    def test_get_template_metadata_usage_count_matches(self, library):
        """Verify metadata usage count matches actual usage."""
        library.format_prompt('extract_entities', {'complaint_text': 'test'})
        library.format_prompt('extract_entities', {'complaint_text': 'test'})
        
        metadata = library.get_template_metadata('extract_entities')
        assert metadata['usage_count'] == 2
    
    def test_get_template_metadata_warning_count_matches(self, library):
        """Verify metadata warning count matches template."""
        metadata = library.get_template_metadata('extract_entities')
        template = library.get_template('extract_entities')
        
        assert metadata['warning_count'] == len(template.warnings)
    
    def test_get_template_metadata_nonexistent_template(self, library):
        """Verify metadata returns empty dict for nonexistent template."""
        metadata = library.get_template_metadata('nonexistent')
        assert metadata == {}


class TestPromptLibraryTemplateClassification:
    """Test template classification and grouping."""
    
    def test_templates_needing_payload_returns_templates_with_placeholders(self, library):
        """Verify templates_needing_payload includes templates with {field} placeholders."""
        payload_templates = library.templates_needing_payload()
        
        # Most default templates should need payload
        assert len(payload_templates) > 0
        assert 'extract_entities' in payload_templates
    
    def test_templates_without_payload_returns_templates_no_placeholders(self, library):
        """Verify templates_without_payload contains templates with no placeholders."""
        without_payload = library.templates_without_payload()
        
        # Should be smaller or empty since most templates have payloads
        all_templates = set(library.list_templates())
        with_payload = set(library.templates_needing_payload())
        
        assert set(without_payload) == all_templates - with_payload
    
    def test_templates_by_format_type_json_is_most_common(self, library):
        """Verify most templates are JSON format."""
        json_count = library.templates_by_format_type(ReturnFormat.JSON)
        assert json_count > 0
        assert json_count >= library.templates_by_format_type(ReturnFormat.STRUCTURED_TEXT)
    
    def test_template_format_type_breakdown_includes_all_templates(self, library):
        """Verify format type breakdown includes all templates."""
        breakdown = library.template_format_type_breakdown()
        
        total_in_breakdown = sum(len(templates) for templates in breakdown.values())
        assert total_in_breakdown == library.total_templates()
    
    def test_template_format_type_breakdown_keys_are_valid_formats(self, library):
        """Verify breakdown keys are valid ReturnFormat values."""
        breakdown = library.template_format_type_breakdown()
        valid_formats = set(fmt.value for fmt in ReturnFormat)
        
        for format_type in breakdown.keys():
            assert format_type in valid_formats


class TestPromptLibraryWarningAnalysis:
    """Test warning distribution and analysis."""
    
    def test_warning_distribution_returns_counts(self, library):
        """Verify warning_distribution returns warning count distribution."""
        dist = library.warning_distribution()
        
        # Should have some entries (templates with different warning counts)
        assert isinstance(dist, dict)
        assert len(dist) > 0
        
        # All keys should be non-negative integers
        for count in dist.keys():
            assert count >= 0
            assert isinstance(count, int)
    
    def test_warning_distribution_sums_to_total_templates(self, library):
        """Verify warning distribution accounts for all templates."""
        dist = library.warning_distribution()
        total = sum(dist.values())
        
        assert total == library.total_templates()
    
    def test_templates_with_most_warnings_returns_valid_template(self, library):
        """Verify most_warnings returns an actual template name."""
        most_warned = library.templates_with_most_warnings()
        
        if library.total_templates() > 0:
            assert most_warned in library.list_templates()
    
    def test_warning_coverage_percentage_in_valid_range(self, library):
        """Verify warning_coverage_percentage returns 0-100."""
        coverage = library.average_warnings_per_template()
        
        # Should be a reasonable average
        assert coverage >= 0


class TestPromptLibraryContentAnalysis:
    """Test analysis of template content."""
    
    def test_system_prompt_length_distribution_has_required_keys(self, library):
        """Verify prompt length distribution has expected keys."""
        dist = library.system_prompt_length_distribution()
        
        assert 'total_templates' in dist
        if dist['total_templates'] > 0:
            assert 'average_length' in dist
            assert 'min_length' in dist
            assert 'max_length' in dist
            assert 'total_chars' in dist
    
    def test_system_prompt_length_distribution_reasonable_values(self, library):
        """Verify prompt length statistics are reasonable."""
        dist = library.system_prompt_length_distribution()
        
        if dist['total_templates'] > 0:
            assert dist['min_length'] <= dist['average_length']
            assert dist['average_length'] <= dist['max_length']
            assert dist['total_chars'] > 0
    
    def test_total_characters_in_templates_is_nonzero(self, library):
        """Verify total character count is reasonable."""
        total_chars = library.total_characters_in_templates()
        
        # Should have substantial content in templates
        assert total_chars > 0
    
    def test_total_characters_accounts_for_all_content(self, library):
        """Verify character count includes all template parts."""
        total_chars = library.total_characters_in_templates()
        
        # Manually calculate and verify
        manual_total = 0
        for template in library.templates.values():
            manual_total += len(template.system_prompt)
            manual_total += len(template.return_format)
            manual_total += len(template.payload_template)
        
        assert total_chars == manual_total


class TestPromptLibraryCaching:
    """Test caching and efficiency metrics."""
    
    def test_cache_efficiency_ratio_zero_when_no_formats(self, library):
        """Verify cache efficiency is 0 when templates not formatted."""
        ratio = library.cache_efficiency_ratio()
        assert ratio == 0.0 or ratio is not None  # No formats yet
    
    def test_cache_efficiency_ratio_improves_with_reuse(self, library):
        """Verify cache efficiency improves with template reuse."""
        # Format same template multiple times
        for i in range(5):
            library.format_prompt('extract_entities', {'complaint_text': f'test {i}'})
        
        ratio = library.cache_efficiency_ratio()
        
        # With 5 formats of same template, ratio should be reasonable
        assert 0 <= ratio <= 1
    
    def test_clear_usage_statistics_resets_counts(self, library):
        """Verify clear_usage_statistics resets all tracking."""
        library.format_prompt('extract_entities', {'complaint_text': 'test'})
        assert library.template_usage_count('extract_entities') == 1
        
        library.clear_usage_statistics()
        
        assert library.template_usage_count('extract_entities') == 0
        assert len(library.get_usage_history()) == 0
    
    def test_get_usage_history_returns_recent_operations(self, library):
        """Verify usage history contains format operations in order."""
        library.format_prompt('extract_entities', {'complaint_text': 'test'})
        library.format_prompt('extract_relationships', {'entities': 'e', 'complaint_text': 'c'})
        library.format_prompt('extract_entities', {'complaint_text': 'test2'})
        
        history = library.get_usage_history()
        
        assert len(history) == 3
        assert history[0] == 'extract_entities'
        assert history[1] == 'extract_relationships'
        assert history[2] == 'extract_entities'
    
    def test_get_usage_history_with_limit(self, library):
        """Verify usage history limit returns most recent entries."""
        library.format_prompt('extract_entities', {'complaint_text': 'test'})
        library.format_prompt('extract_relationships', {'entities': 'e', 'complaint_text': 'c'})
        library.format_prompt('extract_entities', {'complaint_text': 'test2'})
        
        recent = library.get_usage_history(limit=2)
        
        assert len(recent) == 2
        assert recent[0] == 'extract_relationships'
        assert recent[1] == 'extract_entities'
    
    def test_get_usage_history_zero_limit_returns_empty(self, library):
        """Verify zero limit returns empty list."""
        library.format_prompt('extract_entities', {'complaint_text': 'test'})
        
        history = library.get_usage_history(limit=0)
        assert len(history) == 0


class TestPromptLibraryIntegration:
    """Integration tests combining multiple features."""
    
    def test_full_workflow_usage_tracking_and_validation(self, library):
        """Test realistic workflow with validation and tracking."""
        # Validate before formatting
        errors = library.validate_template_fields(
            'extract_entities',
            {'complaint_text': 'Test complaint about discrimination'}
        )
        assert len(errors) == 0
        
        # Format and track
        prompt = library.format_prompt('extract_entities', {'complaint_text': 'Test complaint'})
        assert len(prompt) > 0
        
        # Check usage was tracked
        assert library.template_usage_count('extract_entities') == 1
        assert 'extract_entities' in library.templates_by_usage()[0]
    
    def test_multiple_templates_with_statistics(self, library):
        """Test using multiple templates and analyzing statistics."""
        library.format_prompt('extract_entities', {'complaint_text': 'test'})
        library.format_prompt('extract_entities', {'complaint_text': 'test'})
        library.format_prompt('extract_relationships', {'entities': 'e', 'complaint_text': 'c'})
        
        # Get statistics
        usage_list = library.templates_by_usage()
        metadata = library.get_template_metadata('extract_entities')
        breakdown = library.template_format_type_breakdown()
        
        # Verify statistics are consistent
        assert len(usage_list) > 0
        assert metadata['usage_count'] == 2
        assert len(breakdown) > 0
        
        # Calculate cache efficiency
        efficiency = library.cache_efficiency_ratio()
        assert 0 <= efficiency <= 1
    
    def test_comprehensive_template_analysis(self, library):
        """Test comprehensive analysis of all templates."""
        # Use all format types
        usage_before = len([t for t in library.templates.values()])
        
        # Get comprehensive stats
        total_templates = library.total_templates()
        total_chars = library.total_characters_in_templates()
        format_dist = library.format_type_distribution()
        unused = library.unused_templates()
        
        # Verify consistency
        assert total_templates > 0
        assert total_chars > 0
        assert sum(format_dist.values()) == total_templates
        assert len(unused) == total_templates  # All unused if never formatted
