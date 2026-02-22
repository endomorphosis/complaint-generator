"""
Batch 215: LegalPatternExtractor analysis methods tests.

Tests analysis tracking, frequency distribution, and statistical helpers.
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


class TestLegalPatternExtractorAnalysis:
    def test_analysis_tracking_counts(self):
        extractor = LegalPatternExtractor()

        result_one = extractor.analyze_text(sample_text_one())
        result_two = extractor.analyze_text(sample_text_two())

        assert extractor.total_analyses_performed() == 2

        provision_counts = [
            result_one['provisions']['provision_count'],
            result_two['provisions']['provision_count'],
        ]
        unique_counts = [
            result_one['provisions']['unique_terms'],
            result_two['provisions']['unique_terms'],
        ]

        assert extractor.average_provisions_per_analysis() == (
            sum(provision_counts) / len(provision_counts)
        )
        assert extractor.average_unique_terms_per_analysis() == (
            sum(unique_counts) / len(unique_counts)
        )

        assert extractor.maximum_provisions_found() == max(provision_counts)
        assert extractor.minimum_provisions_found() == min(provision_counts)

    def test_citation_statistics(self):
        extractor = LegalPatternExtractor()

        extractor.analyze_text(sample_text_one())
        extractor.analyze_text(sample_text_two())

        assert extractor.total_citations_found() == 2
        assert extractor.average_citations_per_analysis() == 1.0

    def test_protected_class_distribution(self):
        extractor = LegalPatternExtractor()

        extractor.analyze_text(sample_text_one())
        extractor.analyze_text(sample_text_two())

        distribution = extractor.protected_class_frequency_distribution()
        assert distribution
        assert extractor.most_common_protected_class() in distribution

        assert extractor.analyses_with_protected_classes() == 2
        assert extractor.unique_protected_classes_found() >= 2

    def test_complaint_type_distribution(self):
        extractor = LegalPatternExtractor()

        extractor.analyze_text(sample_text_one())
        extractor.analyze_text(sample_text_two())

        distribution = extractor.complaint_type_frequency_distribution()
        assert distribution
        assert 'housing' in distribution
        assert 'disability' in distribution

        assert extractor.most_common_complaint_type() in distribution
        assert extractor.unique_complaint_types_identified() == len(distribution)

    def test_clear_analysis_history(self):
        extractor = LegalPatternExtractor()

        extractor.analyze_text(sample_text_one())
        extractor.analyze_text(sample_text_two())

        assert extractor.total_analyses_performed() == 2

        extractor.clear_analysis_history()

        assert extractor.total_analyses_performed() == 0
        assert extractor.total_citations_found() == 0
        assert extractor.protected_class_frequency_distribution() == {}
        assert extractor.complaint_type_frequency_distribution() == {}
