"""
Batch 225: LegalPatternExtractor additional analytics tests.

Tests totals, averages, citation rates, and min/max helpers.
"""

from complaint_analysis.legal_patterns import LegalPatternExtractor


def sample_text_one() -> str:
    return (
        "The Fair Housing Act prohibits discrimination in Section 8 housing. "
        "This includes race and national origin discrimination. "
        "See 42 U.S.C. § 3604 for details."
    )


def sample_text_two() -> str:
    return (
        "The ADA requires reasonable accommodation. "
        "Gender identity harassment is prohibited. "
        "See 24 C.F.R. § 100.70."
    )


class TestLegalPatternExtractorBatch225:
    def test_empty_history_metrics(self):
        extractor = LegalPatternExtractor()

        assert extractor.total_provisions_found() == 0
        assert extractor.total_unique_terms_counted() == 0
        assert extractor.average_protected_classes_per_analysis() == 0.0
        assert extractor.average_complaint_types_per_analysis() == 0.0
        assert extractor.analyses_with_citations() == 0
        assert extractor.citation_rate() == 0.0
        assert extractor.max_unique_terms_found() == 0
        assert extractor.min_unique_terms_found() == 0
        assert extractor.max_citations_found() == 0
        assert extractor.min_citations_found() == 0

    def test_totals_and_averages_from_results(self):
        extractor = LegalPatternExtractor()

        result_one = extractor.analyze_text(sample_text_one())
        result_two = extractor.analyze_text(sample_text_two())

        provision_counts = [
            result_one["provisions"]["provision_count"],
            result_two["provisions"]["provision_count"],
        ]
        unique_term_counts = [
            result_one["provisions"]["unique_terms"],
            result_two["provisions"]["unique_terms"],
        ]
        citation_counts = [
            len(result_one["citations"]),
            len(result_two["citations"]),
        ]
        protected_class_counts = [
            len(result_one["protected_classes"]),
            len(result_two["protected_classes"]),
        ]
        complaint_type_counts = [
            len(result_one["categories"]),
            len(result_two["categories"]),
        ]

        assert extractor.total_provisions_found() == sum(provision_counts)
        assert extractor.total_unique_terms_counted() == sum(unique_term_counts)

        assert extractor.average_protected_classes_per_analysis() == (
            sum(protected_class_counts) / len(protected_class_counts)
        )
        assert extractor.average_complaint_types_per_analysis() == (
            sum(complaint_type_counts) / len(complaint_type_counts)
        )

        assert extractor.analyses_with_citations() == sum(1 for c in citation_counts if c > 0)
        assert extractor.citation_rate() == (
            extractor.analyses_with_citations() / extractor.total_analyses_performed()
        )

        assert extractor.max_unique_terms_found() == max(unique_term_counts)
        assert extractor.min_unique_terms_found() == min(unique_term_counts)
        assert extractor.max_citations_found() == max(citation_counts)
        assert extractor.min_citations_found() == min(citation_counts)
