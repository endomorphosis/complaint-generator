"""
Batch 221: ResponseParserFactory Additional Analytics Tests

Tests for newly added analytics methods covering warnings, response length
statistics, error averages, type-specific counts, and recent success rates.
"""

from unittest.mock import Mock

import pytest

from complaint_analysis.response_parsers import ParsedResponse, ResponseParserFactory


class TestResponseParserFactoryWarningAnalytics:
    def test_warning_ratio_no_operations(self):
        factory = ResponseParserFactory()
        assert factory.warning_ratio() == 0.0

    def test_warning_ratio_with_warnings(self):
        factory = ResponseParserFactory()
        mock_parser = Mock()
        mock_parser.parse.side_effect = [
            ParsedResponse(data={}, format_type="json", success=True, errors=[], warnings=["warn"]),
            ParsedResponse(data={}, format_type="json", success=True, errors=[], warnings=[]),
        ]
        factory._parser_instances["json"] = mock_parser

        factory.parse_with_tracking("{}", "json")
        factory.parse_with_tracking("{}", "json")

        assert factory.warning_ratio() == pytest.approx(0.5)

    def test_average_warnings_per_operation_no_operations(self):
        factory = ResponseParserFactory()
        assert factory.average_warnings_per_operation() == 0.0

    def test_average_warnings_per_operation(self):
        factory = ResponseParserFactory()
        mock_parser = Mock()
        mock_parser.parse.side_effect = [
            ParsedResponse(
                data={}, format_type="json", success=True, errors=[], warnings=["w1", "w2"]
            ),
            ParsedResponse(data={}, format_type="json", success=True, errors=[], warnings=[]),
        ]
        factory._parser_instances["json"] = mock_parser

        factory.parse_with_tracking("{}", "json")
        factory.parse_with_tracking("{}", "json")

        assert factory.average_warnings_per_operation() == pytest.approx(1.0)


class TestResponseParserFactoryResponseLength:
    def test_total_response_length_no_operations(self):
        factory = ResponseParserFactory()
        assert factory.total_response_length() == 0

    def test_total_response_length_sum(self):
        factory = ResponseParserFactory()
        response_one = "{\"a\": 1}"
        response_two = "{\"b\": 2, \"c\": 3}"

        factory.parse_with_tracking(response_one, "json")
        factory.parse_with_tracking(response_two, "json")

        assert factory.total_response_length() == len(response_one) + len(response_two)

    def test_min_response_length_no_operations(self):
        factory = ResponseParserFactory()
        assert factory.min_response_length() == 0

    def test_min_response_length(self):
        factory = ResponseParserFactory()
        short_response = "{\"x\": 1}"
        long_response = "{\"long\": 12345}"

        factory.parse_with_tracking(long_response, "json")
        factory.parse_with_tracking(short_response, "json")

        assert factory.min_response_length() == len(short_response)

    def test_max_response_length_no_operations(self):
        factory = ResponseParserFactory()
        assert factory.max_response_length() == 0

    def test_max_response_length(self):
        factory = ResponseParserFactory()
        short_response = "{\"x\": 1}"
        long_response = "{\"long\": 12345}"

        factory.parse_with_tracking(short_response, "json")
        factory.parse_with_tracking(long_response, "json")

        assert factory.max_response_length() == len(long_response)


class TestResponseParserFactoryErrorAnalytics:
    def test_average_errors_per_operation_no_operations(self):
        factory = ResponseParserFactory()
        assert factory.average_errors_per_operation() == 0.0

    def test_average_errors_per_operation(self):
        factory = ResponseParserFactory()
        mock_parser = Mock()
        mock_parser.parse.side_effect = [
            ParsedResponse(
                data={}, format_type="json", success=False, errors=["e1", "e2"], warnings=[]
            ),
            ParsedResponse(data={}, format_type="json", success=True, errors=[], warnings=[]),
        ]
        factory._parser_instances["json"] = mock_parser

        factory.parse_with_tracking("{}", "json")
        factory.parse_with_tracking("{}", "json")

        assert factory.average_errors_per_operation() == pytest.approx(1.0)


class TestResponseParserFactoryTypeCounts:
    def test_success_count_by_parser_type(self):
        factory = ResponseParserFactory()

        factory.parse_with_tracking("{\"ok\": true}", "json")
        factory.parse_with_tracking("{bad}", "json")
        factory.parse_with_tracking("{\"entities\": []}", "entities")

        success_counts = factory.success_count_by_parser_type()
        assert success_counts["json"] == 1
        assert success_counts["entities"] == 1
        assert len(success_counts) == 2

    def test_failure_count_by_parser_type(self):
        factory = ResponseParserFactory()

        factory.parse_with_tracking("{bad}", "json")
        factory.parse_with_tracking("{also bad}", "json")
        factory.parse_with_tracking("{bad}", "entities")
        factory.parse_with_tracking("{\"entities\": []}", "entities")

        failure_counts = factory.failure_count_by_parser_type()
        assert failure_counts["json"] == 2
        assert failure_counts["entities"] == 1

    def test_parser_success_rate_mixed(self):
        factory = ResponseParserFactory()

        factory.parse_with_tracking("{\"ok\": true}", "json")
        factory.parse_with_tracking("{bad}", "json")
        factory.parse_with_tracking("{\"ok\": true}", "json")

        assert factory.parser_success_rate("json") == pytest.approx(2 / 3)

    def test_parser_success_rate_missing(self):
        factory = ResponseParserFactory()
        assert factory.parser_success_rate("json") == 0.0


class TestResponseParserFactoryRecentSuccessRate:
    def test_recent_success_rate_window(self):
        factory = ResponseParserFactory()

        factory.parse_with_tracking("{\"x\": 1}", "json")
        factory.parse_with_tracking("{bad}", "json")
        factory.parse_with_tracking("{\"y\": 2}", "json")
        factory.parse_with_tracking("{\"z\": 3}", "json")

        assert factory.recent_success_rate(3) == pytest.approx(2 / 3)

    def test_recent_success_rate_window_larger_than_total(self):
        factory = ResponseParserFactory()

        factory.parse_with_tracking("{\"x\": 1}", "json")
        factory.parse_with_tracking("{bad}", "json")

        assert factory.recent_success_rate(10) == pytest.approx(0.5)

    def test_recent_success_rate_invalid_window(self):
        factory = ResponseParserFactory()

        factory.parse_with_tracking("{\"x\": 1}", "json")

        assert factory.recent_success_rate(0) == 0.0
        assert factory.recent_success_rate(-1) == 0.0
