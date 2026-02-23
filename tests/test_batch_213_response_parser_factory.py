"""
Batch 213: ResponseParserFactory Enhancement Tests

Tests for ResponseParserFactory caching, history tracking, and analysis methods.
- Parser instance caching (same instance returned for same type)
- Parse operation tracking (history, counters)
- Analytics methods (success rate, parser distribution, error ratio)
- History management (clear, limit retrieval)
"""

import pytest
from unittest.mock import Mock, patch
from complaint_analysis.response_parsers import (
    ResponseParserFactory,
    JSONResponseParser,
    EntityParser,
    RelationshipParser,
    ParsedResponse,
)


class TestResponseParserFactoryCaching:
    """Test parser instance caching behavior."""
    
    def test_get_parser_returns_instance(self):
        """Verify get_parser returns a parser instance."""
        factory = ResponseParserFactory()
        parser = factory.get_parser('json')
        
        assert parser is not None
        assert isinstance(parser, JSONResponseParser)
    
    def test_caching_same_type_returns_same_instance(self):
        """Verify that multiple calls for same type return cached instance."""
        factory = ResponseParserFactory()
        parser1 = factory.get_parser('json')
        parser2 = factory.get_parser('json')
        
        assert parser1 is parser2
    
    def test_different_types_return_different_instances(self):
        """Verify that different types return different instances."""
        factory = ResponseParserFactory()
        json_parser = factory.get_parser('json')
        entity_parser = factory.get_parser('entities')
        
        assert json_parser is not entity_parser
        assert isinstance(json_parser, JSONResponseParser)
        assert isinstance(entity_parser, EntityParser)
    
    def test_all_parser_types_cacheable(self):
        """Test that all supported parser types can be cached."""
        factory = ResponseParserFactory()
        parser_types = ['json', 'structured_text', 'entities', 'relationships', 'questions', 'claims']
        
        parsers = {}
        for parser_type in parser_types:
            parsers[parser_type] = factory.get_parser(parser_type)
        
        # Verify all were created
        assert len(parsers) == 6
        
        # Verify caching works for all
        for parser_type in parser_types:
            assert factory.get_parser(parser_type) is parsers[parser_type]
    
    def test_invalid_parser_type_raises_error(self):
        """Verify that invalid parser type raises ValueError."""
        factory = ResponseParserFactory()
        
        with pytest.raises(ValueError) as exc_info:
            factory.get_parser('invalid_type')
        
        assert 'Unknown parser type' in str(exc_info.value)


class TestResponseParserFactoryHistoryTracking:
    """Test history tracking of parse operations."""
    
    def test_parse_with_tracking_records_successful_operation(self):
        """Verify successful parse is recorded in history."""
        factory = ResponseParserFactory()
        valid_json = '{"test": "data"}'
        
        parsed = factory.parse_with_tracking(valid_json, 'json')
        
        assert parsed.success
        assert len(factory.get_history()) == 1
    
    def test_parse_with_tracking_records_failed_operation(self):
        """Verify failed parse is recorded in history."""
        factory = ResponseParserFactory()
        invalid_json = '{invalid json}'
        
        parsed = factory.parse_with_tracking(invalid_json, 'json')
        
        assert not parsed.success
        assert len(factory.get_history()) == 1
    
    def test_history_entries_contain_required_fields(self):
        """Verify history entries have correct structure."""
        factory = ResponseParserFactory()
        valid_json = '{"test": "data"}'
        
        factory.parse_with_tracking(valid_json, 'json')
        history = factory.get_history()
        
        assert len(history) == 1
        entry = history[0]
        assert 'parser_type' in entry
        assert 'response_length' in entry
        assert 'success' in entry
        assert 'errors' in entry
        assert 'warnings' in entry
    
    def test_multiple_operations_tracked_independently(self):
        """Verify multiple operations are tracked independently."""
        factory = ResponseParserFactory()
        
        factory.parse_with_tracking('{"a": 1}', 'json')
        factory.parse_with_tracking('{"b": 2}', 'json')
        factory.parse_with_tracking('{invalid}', 'json')
        
        history = factory.get_history()
        assert len(history) == 3
    
    def test_total_parsing_operations_counts_correctly(self):
        """Verify total_parsing_operations counts all operations."""
        factory = ResponseParserFactory()
        
        for i in range(5):
            factory.parse_with_tracking(f'{{"op": {i}}}', 'json')
        
        assert factory.total_parsing_operations() == 5
    
    def test_history_response_length_recorded(self):
        """Verify response length is accurately recorded."""
        factory = ResponseParserFactory()
        short_response = '{"x": 1}'
        long_response = '{"very_long_key": "' + 'x' * 100 + '"}'
        
        factory.parse_with_tracking(short_response, 'json')
        factory.parse_with_tracking(long_response, 'json')
        
        history = factory.get_history()
        assert history[0]['response_length'] == len(short_response)
        assert history[1]['response_length'] == len(long_response)


class TestResponseParserFactoryCounters:
    """Test success and failure counters."""
    
    def test_successful_parse_count_increments(self):
        """Verify success counter increments on successful parse."""
        factory = ResponseParserFactory()
        
        factory.parse_with_tracking('{"valid": true}', 'json')
        assert factory.successful_parse_count() == 1
        
        factory.parse_with_tracking('{"another": true}', 'json')
        assert factory.successful_parse_count() == 2
    
    def test_failed_parse_count_increments(self):
        """Verify failure counter increments on failed parse."""
        factory = ResponseParserFactory()
        
        factory.parse_with_tracking('{invalid}', 'json')
        assert factory.failed_parse_count() == 1
        
        factory.parse_with_tracking('{also invalid}', 'json')
        assert factory.failed_parse_count() == 2
    
    def test_success_and_failure_count_separately(self):
        """Verify success and failure counters track independently."""
        factory = ResponseParserFactory()
        
        factory.parse_with_tracking('{"valid": 1}', 'json')
        factory.parse_with_tracking('{invalid}', 'json')
        factory.parse_with_tracking('{"valid": 2}', 'json')
        factory.parse_with_tracking('{also invalid}', 'json')
        
        assert factory.successful_parse_count() == 2
        assert factory.failed_parse_count() == 2
    
    def test_success_rate_calculation(self):
        """Verify success_rate is calculated correctly."""
        factory = ResponseParserFactory()
        
        # No operations yet
        assert factory.success_rate() == 0.0
        
        # 2 successes out of 4 = 50%
        factory.parse_with_tracking('{"valid": 1}', 'json')
        factory.parse_with_tracking('{invalid}', 'json')
        factory.parse_with_tracking('{"valid": 2}', 'json')
        factory.parse_with_tracking('{also invalid}', 'json')
        
        assert factory.success_rate() == pytest.approx(0.5)
    
    def test_success_rate_with_only_successes(self):
        """Verify success_rate is 1.0 when all operations succeed."""
        factory = ResponseParserFactory()
        
        for i in range(3):
            factory.parse_with_tracking(f'{{"x": {i}}}', 'json')
        
        assert factory.success_rate() == 1.0
    
    def test_success_rate_with_only_failures(self):
        """Verify success_rate is 0.0 when all operations fail."""
        factory = ResponseParserFactory()
        
        for i in range(3):
            factory.parse_with_tracking('{invalid}', 'json')
        
        assert factory.success_rate() == 0.0


class TestResponseParserFactoryAnalytics:
    """Test analytics methods."""
    
    def test_parser_type_distribution_counts_usage(self):
        """Verify parser_type_distribution counts correct usage."""
        factory = ResponseParserFactory()
        
        factory.parse_with_tracking('{"x": 1}', 'json')
        factory.parse_with_tracking('{"y": 2}', 'json')
        factory.parse_with_tracking('Section 1\nContent', 'structured_text')
        factory.parse_with_tracking('{"z": 3}', 'json')
        
        dist = factory.parser_type_distribution()
        
        assert dist['json'] == 3
        assert dist['structured_text'] == 1
        assert len(dist) == 2
    
    def test_most_used_parser(self):
        """Verify most_used_parser returns correct type."""
        factory = ResponseParserFactory()
        
        # JSON used 3 times, entities used 1 time
        factory.parse_with_tracking('{"x": 1}', 'json')
        factory.parse_with_tracking('{"y": 2}', 'json')
        factory.parse_with_tracking('{"z": 3}', 'json')
        factory.parse_with_tracking('{}', 'entities')
        
        assert factory.most_used_parser() == 'json'
    
    def test_most_used_parser_with_no_operations(self):
        """Verify most_used_parser returns 'none' when no operations."""
        factory = ResponseParserFactory()
        assert factory.most_used_parser() == 'none'
    
    def test_average_response_length(self):
        """Verify average_response_length is calculated correctly."""
        factory = ResponseParserFactory()
        
        # Lengths: 5, 10, 15 -> average = 10
        factory.parse_with_tracking('{"a":1}', 'json')  # 7 chars
        factory.parse_with_tracking('{"ab":12}', 'json')  # 9 chars
        factory.parse_with_tracking('{"abc":123}', 'json')  # 11 chars
        
        avg = factory.average_response_length()
        assert avg == pytest.approx(9.0)
    
    def test_average_response_length_with_no_operations(self):
        """Verify average_response_length is 0.0 when no operations."""
        factory = ResponseParserFactory()
        assert factory.average_response_length() == 0.0
    
    def test_error_ratio_calculation(self):
        """Verify error_ratio is calculated correctly."""
        factory = ResponseParserFactory()
        
        # Create successful parse (no errors)
        factory.parse_with_tracking('{"valid": 1}', 'json')
        
        # Create failed parse (has errors)
        factory.parse_with_tracking('{invalid}', 'json')
        
        # 1 out of 2 has errors = 50%
        assert factory.error_ratio() == pytest.approx(0.5)
    
    def test_error_ratio_with_no_errors(self):
        """Verify error_ratio is 0.0 when all operations succeed."""
        factory = ResponseParserFactory()
        
        factory.parse_with_tracking('{"x": 1}', 'json')
        factory.parse_with_tracking('{"y": 2}', 'json')
        
        assert factory.error_ratio() == 0.0
    
    def test_error_ratio_with_all_errors(self):
        """Verify error_ratio is 1.0 when all operations fail."""
        factory = ResponseParserFactory()
        
        factory.parse_with_tracking('{invalid}', 'json')
        factory.parse_with_tracking('{also invalid}', 'json')
        
        assert factory.error_ratio() == 1.0


class TestResponseParserFactoryHistoryManagement:
    """Test history retrieval and management."""
    
    def test_get_history_returns_all_entries(self):
        """Verify get_history returns all history entries."""
        factory = ResponseParserFactory()
        
        for i in range(5):
            factory.parse_with_tracking(f'{{"op": {i}}}', 'json')
        
        history = factory.get_history()
        assert len(history) == 5
    
    def test_get_history_with_limit_returns_latest_entries(self):
        """Verify get_history with limit returns most recent entries."""
        factory = ResponseParserFactory()
        
        factory.parse_with_tracking('{"op": 1}', 'json')
        factory.parse_with_tracking('{"op": 2}', 'json')
        factory.parse_with_tracking('{"op": 3}', 'json')
        
        history = factory.get_history(limit=2)
        assert len(history) == 2
    
    def test_get_history_with_zero_limit_returns_empty(self):
        """Verify get_history with limit=0 returns empty list."""
        factory = ResponseParserFactory()
        factory.parse_with_tracking('{"x": 1}', 'json')
        
        history = factory.get_history(limit=0)
        assert len(history) == 0
    
    def test_get_history_with_negative_limit_returns_empty(self):
        """Verify get_history with negative limit returns empty list."""
        factory = ResponseParserFactory()
        factory.parse_with_tracking('{"x": 1}', 'json')
        
        history = factory.get_history(limit=-1)
        assert len(history) == 0
    
    def test_clear_history_removes_all_entries(self):
        """Verify clear_history removes all recorded history."""
        factory = ResponseParserFactory()
        
        factory.parse_with_tracking('{"x": 1}', 'json')
        factory.parse_with_tracking('{"y": 2}', 'json')
        
        assert len(factory.get_history()) == 2
        
        factory.clear_history()
        assert len(factory.get_history()) == 0
    
    def test_clear_history_resets_counters(self):
        """Verify clear_history resets success/failure counters."""
        factory = ResponseParserFactory()
        
        factory.parse_with_tracking('{"valid": 1}', 'json')
        factory.parse_with_tracking('{invalid}', 'json')
        
        assert factory.successful_parse_count() == 1
        assert factory.failed_parse_count() == 1
        
        factory.clear_history()
        
        assert factory.successful_parse_count() == 0
        assert factory.failed_parse_count() == 0
    
    def test_clear_history_resets_analytics(self):
        """Verify clear_history resets all analytics."""
        factory = ResponseParserFactory()
        
        factory.parse_with_tracking('{"x": 1}', 'json')
        factory.parse_with_tracking('{"y": 2}', 'json')
        
        factory.clear_history()
        
        assert factory.total_parsing_operations() == 0
        assert factory.success_rate() == 0.0
        assert factory.parser_type_distribution() == {}
        assert factory.average_response_length() == 0.0


class TestResponseParserFactoryAdditionalAnalytics:
    """Test additional analytics methods added to the factory."""

    def test_warning_ratio_and_average_warnings(self):
        """Verify warning ratio and average warnings per operation."""
        factory = ResponseParserFactory()

        factory.parse_with_tracking('{"x": 1}', 'json')
        factory.parse_with_tracking('{bad}', 'json')

        assert factory.warning_ratio() == 0.0
        assert factory.average_warnings_per_operation() == 0.0

    def test_response_length_stats(self):
        """Verify total/min/max response length calculations."""
        factory = ResponseParserFactory()
        response_one = '{"x": 1}'
        response_two = '{"longer": "value"}'

        factory.parse_with_tracking(response_one, 'json')
        factory.parse_with_tracking(response_two, 'json')

        expected_total = len(response_one) + len(response_two)
        assert factory.total_response_length() == expected_total
        assert factory.min_response_length() == min(len(response_one), len(response_two))
        assert factory.max_response_length() == max(len(response_one), len(response_two))

    def test_average_errors_per_operation(self):
        """Verify average error count per operation."""
        factory = ResponseParserFactory()

        factory.parse_with_tracking('{"x": 1}', 'json')
        factory.parse_with_tracking('{bad}', 'json')

        assert factory.average_errors_per_operation() == pytest.approx(0.5)

    def test_success_failure_counts_by_parser_type(self):
        """Verify per-parser success and failure counts."""
        factory = ResponseParserFactory()

        factory.parse_with_tracking('{"x": 1}', 'json')
        factory.parse_with_tracking('{bad}', 'json')
        factory.parse_with_tracking('{"entities": []}', 'entities')

        assert factory.success_count_by_parser_type() == {
            'json': 1,
            'entities': 1,
        }
        assert factory.failure_count_by_parser_type() == {
            'json': 1,
        }

    def test_parser_success_rate(self):
        """Verify success rate per parser type."""
        factory = ResponseParserFactory()

        factory.parse_with_tracking('{"x": 1}', 'json')
        factory.parse_with_tracking('{bad}', 'json')
        factory.parse_with_tracking('{"entities": []}', 'entities')

        assert factory.parser_success_rate('json') == pytest.approx(0.5)
        assert factory.parser_success_rate('entities') == 1.0
        assert factory.parser_success_rate('structured_text') == 0.0

    def test_recent_success_rate(self):
        """Verify recent success rate uses window size."""
        factory = ResponseParserFactory()

        factory.parse_with_tracking('{"x": 1}', 'json')
        factory.parse_with_tracking('{bad}', 'json')
        factory.parse_with_tracking('{"y": 2}', 'json')

        assert factory.recent_success_rate(2) == pytest.approx(0.5)
        assert factory.recent_success_rate(5) == pytest.approx(2 / 3)
        assert factory.recent_success_rate(0) == 0.0


class TestResponseParserFactoryCreation:
    """Test factory creation methods."""
    
    def test_create_produces_new_instance(self):
        """Verify create() produces a new factory instance."""
        factory1 = ResponseParserFactory.create()
        factory2 = ResponseParserFactory.create()
        
        assert factory1 is not factory2
        assert isinstance(factory1, ResponseParserFactory)
        assert isinstance(factory2, ResponseParserFactory)
    
    def test_created_instances_have_separate_state(self):
        """Verify separate instances maintain separate state."""
        factory1 = ResponseParserFactory.create()
        factory2 = ResponseParserFactory.create()
        
        factory1.parse_with_tracking('{"x": 1}', 'json')
        
        assert factory1.successful_parse_count() == 1
        assert factory2.successful_parse_count() == 0


class TestResponseParserFactoryIntegration:
    """Integration tests for the factory."""
    
    def test_complex_workflow_with_multiple_parser_types(self):
        """Test realistic workflow using multiple parser types."""
        factory = ResponseParserFactory()
        
        # Parse JSON entities
        factory.parse_with_tracking('{"entities": []}', 'entities')
        
        # Parse structured text
        factory.parse_with_tracking('## Section\nContent', 'structured_text')
        
        # Parse relationships
        factory.parse_with_tracking('{"relationships": []}', 'relationships')
        
        # Parse claims
        factory.parse_with_tracking('{"claims": []}', 'claims')
        
        # Verify tracking
        assert factory.total_parsing_operations() == 4
        assert factory.successful_parse_count() == 4
        assert factory.failed_parse_count() == 0
        
        # Verify distribution
        dist = factory.parser_type_distribution()
        assert len(dist) == 4
        assert all(count == 1 for count in dist.values())
    
    def test_mixed_success_and_failure_workflow(self):
        """Test workflow with both successful and failed parses."""
        factory = ResponseParserFactory()
        
        # Good JSON
        factory.parse_with_tracking('{"valid": 1}', 'json')
        
        # Bad JSON
        factory.parse_with_tracking('{bad}', 'json')
        
        # Good entities
        factory.parse_with_tracking('{"entities": []}', 'entities')
        
        # Bad entities
        factory.parse_with_tracking('{not entities}', 'entities')
        
        # Verify counts
        assert factory.total_parsing_operations() == 4
        assert factory.successful_parse_count() == 2
        assert factory.failed_parse_count() == 2
        assert factory.success_rate() == 0.5
    
    def test_statistics_across_full_workflow(self):
        """Test statistics collection across complete workflow."""
        factory = ResponseParserFactory()
        
        # Perform various operations
        for i in range(10):
            if i % 3 == 0:
                factory.parse_with_tracking('{invalid}', 'json')
            else:
                factory.parse_with_tracking(f'{{"x": {i}}}', 'json')
        
        # Verify statistics
        assert factory.total_parsing_operations() == 10
        # 4 successes, 4 failures (indices 0, 3, 6, 9 are invalid)
        # Indices 0, 3, 6, 9 fail (4 failures)
        # Indices 1, 2, 4, 5, 7, 8 succeed (6 successes)
        assert factory.successful_parse_count() == 6
        assert factory.failed_parse_count() == 4
        assert factory.success_rate() == pytest.approx(0.6)
        assert factory.error_ratio() == pytest.approx(0.4)
        assert factory.most_used_parser() == 'json'
