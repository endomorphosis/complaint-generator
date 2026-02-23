"""
Batch 216: ComplaintRiskScorer analysis methods tests.

Tests assessment tracking, distribution metrics, and aggregate statistics.
"""

from complaint_analysis.risk_scoring import ComplaintRiskScorer


def text_high_risk() -> str:
    return (
        "Systemic discrimination violates the Fair Housing Act and must be addressed. "
        "This includes discrimination and retaliation."
    )


def text_medium_risk() -> str:
    return (
        "Discrimination must be investigated promptly."
    )


def text_low_risk() -> str:
    return "Possible discrimination was reported."


def text_minimal() -> str:
    return "General statement with no legal issues described."


class TestComplaintRiskScorerAnalysis:
    def test_assessment_counts_and_distribution(self):
        scorer = ComplaintRiskScorer()

        scorer.calculate_risk(text_high_risk())
        scorer.calculate_risk(text_medium_risk())
        scorer.calculate_risk(text_low_risk())
        scorer.calculate_risk(text_minimal())

        assert scorer.total_assessments() == 4
        dist = scorer.risk_level_distribution()
        assert dist
        assert dist.get('high', 0) >= 1
        assert dist.get('medium', 0) >= 1
        assert dist.get('low', 0) >= 1
        assert dist.get('minimal', 0) >= 1

    def test_average_metrics(self):
        scorer = ComplaintRiskScorer()

        scorer.calculate_risk(text_high_risk())
        scorer.calculate_risk(text_medium_risk())
        scorer.calculate_risk(text_low_risk())

        assert scorer.average_risk_score() > 0
        assert scorer.maximum_risk_score() >= scorer.average_risk_score()
        assert scorer.average_complaint_keywords() >= 1.0
        assert scorer.average_binding_keywords() >= 0.0
        assert scorer.average_legal_provisions() >= 0.0

    def test_high_risk_percentage_and_actionable_ratio(self):
        scorer = ComplaintRiskScorer()

        scorer.calculate_risk(text_high_risk())
        scorer.calculate_risk(text_medium_risk())
        scorer.calculate_risk(text_minimal())

        high_pct = scorer.high_risk_percentage()
        assert 0.0 <= high_pct <= 100.0
        assert high_pct > 0.0

        actionable_ratio = scorer.actionable_complaints_ratio(threshold=2)
        assert 0.0 <= actionable_ratio <= 1.0
        assert actionable_ratio > 0.0

    def test_assessments_by_risk_level(self):
        scorer = ComplaintRiskScorer()

        scorer.calculate_risk(text_high_risk())
        scorer.calculate_risk(text_high_risk())
        scorer.calculate_risk(text_low_risk())

        assert scorer.assessments_by_risk_level('high') >= 2
        assert scorer.assessments_by_risk_level('low') >= 1
        assert scorer.assessments_by_risk_level('minimal') == 0
