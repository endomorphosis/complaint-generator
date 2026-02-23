"""
Batch 226: ResponseParserFactory extended analytics tests.
"""

from unittest.mock import Mock

import pytest

from complaint_analysis.response_parsers import ParsedResponse, ResponseParserFactory


class TestResponseParserFactoryBatch226:
    def test_empty_history_defaults(self):
        factory = ResponseParserFactory()

        assert factory.average_response_length_by_parser_type("json") == 0.0
        assert factory.max_response_length_by_parser_type("json") == 0
        assert factory.min_response_length_by_parser_type("json") == 0
        assert factory.warning_count_by_parser_type() == {}
        assert factory.error_count_by_parser_type() == {}
        assert factory.parser_type_usage_ratio("json") == 0.0
        assert factory.operations_with_errors() == 0
        assert factory.operations_with_warnings() == 0
        assert factory.error_to_warning_ratio() == 0.0
        assert factory.most_error_prone_parser() == "none"

    def test_per_type_response_lengths(self):
        factory = ResponseParserFactory()

        factory.parse_with_tracking("{\"a\": 1}", "json")
        factory.parse_with_tracking("{\"b\": 2, \"c\": 3}", "json")
        factory.parse_with_tracking("## Section\nContent", "structured_text")

        avg_json = factory.average_response_length_by_parser_type("json")
        max_json = factory.max_response_length_by_parser_type("json")
        min_json = factory.min_response_length_by_parser_type("json")

        assert avg_json == pytest.approx((len("{\"a\": 1}") + len("{\"b\": 2, \"c\": 3}")) / 2)
        assert max_json == len("{\"b\": 2, \"c\": 3}")
        assert min_json == len("{\"a\": 1}")

    def test_warning_and_error_counts_by_type(self):
        factory = ResponseParserFactory()
        mock_parser = Mock()
        mock_parser.parse.side_effect = [
            ParsedResponse(data={}, format_type="json", success=True, errors=["e1"], warnings=["w1"]),
            ParsedResponse(data={}, format_type="json", success=True, errors=[], warnings=["w2", "w3"]),
            ParsedResponse(data={}, format_type="json", success=False, errors=["e2", "e3"], warnings=[]),
        ]
        factory._parser_instances["json"] = mock_parser

        factory.parse_with_tracking("{}", "json")
        factory.parse_with_tracking("{}", "json")
        factory.parse_with_tracking("{}", "json")

        assert factory.warning_count_by_parser_type() == {"json": 3}
        assert factory.error_count_by_parser_type() == {"json": 3}
        assert factory.operations_with_errors() == 2
        assert factory.operations_with_warnings() == 2

    def test_usage_ratio_and_error_warning_ratio(self):
        factory = ResponseParserFactory()
        mock_parser = Mock()
        mock_parser.parse.side_effect = [
            ParsedResponse(data={}, format_type="json", success=True, errors=["e1"], warnings=["w1"]),
            ParsedResponse(data={}, format_type="json", success=True, errors=[], warnings=["w2"]),
            ParsedResponse(data={}, format_type="json", success=True, errors=[], warnings=[]),
        ]
        factory._parser_instances["json"] = mock_parser

        factory.parse_with_tracking("{}", "json")
        factory.parse_with_tracking("{}", "json")
        factory.parse_with_tracking("{}", "json")

        assert factory.parser_type_usage_ratio("json") == 1.0
        assert factory.error_to_warning_ratio() == pytest.approx(1 / 2)

    def test_most_error_prone_parser(self):
        factory = ResponseParserFactory()
        mock_parser = Mock()
        mock_parser.parse.side_effect = [
            ParsedResponse(data={}, format_type="json", success=False, errors=["e1"], warnings=[]),
            ParsedResponse(data={}, format_type="json", success=False, errors=["e2", "e3"], warnings=[]),
            ParsedResponse(data={}, format_type="json", success=True, errors=[], warnings=[]),
        ]
        factory._parser_instances["json"] = mock_parser

        factory.parse_with_tracking("{}", "json")
        factory.parse_with_tracking("{}", "json")
        factory.parse_with_tracking("{}", "json")

        assert factory.most_error_prone_parser() == "json"
