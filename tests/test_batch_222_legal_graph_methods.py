"""
Unit tests for Batch 222: LegalGraph analysis methods.

Tests 10 analytics methods added to LegalGraph.
"""

import pytest

from complaint_phases.legal_graph import LegalGraph, LegalElement, LegalRelation


@pytest.fixture
def legal_graph():
    return LegalGraph()


def create_element(
    element_id,
    element_type="statute",
    name="Test Element",
    description="",
    citation="",
    jurisdiction="",
    required=True,
    attributes=None,
):
    if attributes is None:
        attributes = {}
    return LegalElement(
        id=element_id,
        element_type=element_type,
        name=name,
        description=description,
        citation=citation,
        jurisdiction=jurisdiction,
        required=required,
        attributes=attributes,
    )


def create_relation(relation_id, source_id, target_id, relation_type="requires"):
    return LegalRelation(
        id=relation_id,
        source_id=source_id,
        target_id=target_id,
        relation_type=relation_type,
        attributes={},
    )


class TestElementJurisdictionFrequency:
    def test_empty_graph(self, legal_graph):
        assert legal_graph.element_jurisdiction_frequency() == {}

    def test_multiple_jurisdictions(self, legal_graph):
        legal_graph.add_element(create_element("e1", jurisdiction="US"))
        legal_graph.add_element(create_element("e2", jurisdiction="US"))
        legal_graph.add_element(create_element("e3", jurisdiction="CA"))
        legal_graph.add_element(create_element("e4", jurisdiction=""))

        freq = legal_graph.element_jurisdiction_frequency()
        assert freq == {"US": 2, "CA": 1, "": 1}


class TestRequiredOptionalCounts:
    def test_required_elements_count(self, legal_graph):
        legal_graph.add_element(create_element("e1", required=True))
        legal_graph.add_element(create_element("e2", required=False))
        legal_graph.add_element(create_element("e3", required=True))

        assert legal_graph.required_elements_count() == 2

    def test_optional_elements_count(self, legal_graph):
        legal_graph.add_element(create_element("e1", required=False))
        legal_graph.add_element(create_element("e2", required=False))
        legal_graph.add_element(create_element("e3", required=True))

        assert legal_graph.optional_elements_count() == 2


class TestElementsWithAttributesCount:
    def test_elements_with_attributes_count(self, legal_graph):
        legal_graph.add_element(create_element("e1", attributes={"a": 1}))
        legal_graph.add_element(create_element("e2", attributes={}))
        legal_graph.add_element(create_element("e3", attributes={"b": "x"}))

        assert legal_graph.elements_with_attributes_count() == 2


class TestElementsMissingCitationCount:
    def test_elements_missing_citation_count(self, legal_graph):
        legal_graph.add_element(create_element("e1", citation=""))
        legal_graph.add_element(create_element("e2", citation="42 U.S.C."))
        legal_graph.add_element(create_element("e3", citation=""))

        assert legal_graph.elements_missing_citation_count() == 2


class TestRelationTypeSet:
    def test_relation_type_set_empty(self, legal_graph):
        assert legal_graph.relation_type_set() == []

    def test_relation_type_set_sorted(self, legal_graph):
        for i in range(3):
            legal_graph.add_element(create_element(f"e{i}"))
        legal_graph.add_relation(create_relation("r1", "e0", "e1", "provides"))
        legal_graph.add_relation(create_relation("r2", "e1", "e2", "requires"))
        legal_graph.add_relation(create_relation("r3", "e2", "e0", "contradicts"))

        assert legal_graph.relation_type_set() == ["contradicts", "provides", "requires"]


class TestAverageElementsPerType:
    def test_average_elements_per_type_empty(self, legal_graph):
        assert legal_graph.average_elements_per_type() == 0.0

    def test_average_elements_per_type(self, legal_graph):
        legal_graph.add_element(create_element("e1", element_type="statute"))
        legal_graph.add_element(create_element("e2", element_type="statute"))
        legal_graph.add_element(create_element("e3", element_type="requirement"))

        assert legal_graph.average_elements_per_type() == pytest.approx(1.5)


class TestElementsByJurisdiction:
    def test_elements_by_jurisdiction(self, legal_graph):
        legal_graph.add_element(create_element("e1", jurisdiction="US"))
        legal_graph.add_element(create_element("e2", jurisdiction="CA"))
        legal_graph.add_element(create_element("e3", jurisdiction="US"))

        elements = legal_graph.elements_by_jurisdiction("US")
        assert {e.id for e in elements} == {"e1", "e3"}


class TestRelationCountForElement:
    def test_relation_count_for_element(self, legal_graph):
        for i in range(3):
            legal_graph.add_element(create_element(f"e{i}"))
        legal_graph.add_relation(create_relation("r1", "e0", "e1"))
        legal_graph.add_relation(create_relation("r2", "e1", "e2"))
        legal_graph.add_relation(create_relation("r3", "e0", "e2"))

        assert legal_graph.relation_count_for_element("e0") == 2
        assert legal_graph.relation_count_for_element("e1") == 2
        assert legal_graph.relation_count_for_element("e2") == 2


class TestClaimTypeRequirementCounts:
    def test_claim_type_requirement_counts(self, legal_graph):
        legal_graph.add_element(
            create_element(
                "r1",
                element_type="requirement",
                attributes={"applicable_claim_types": ["discrimination", "retaliation"]},
            )
        )
        legal_graph.add_element(
            create_element(
                "r2",
                element_type="procedural_requirement",
                attributes={"applicable_claim_types": ["discrimination"]},
            )
        )
        legal_graph.add_element(create_element("s1", element_type="statute"))

        counts = legal_graph.claim_type_requirement_counts()
        assert counts == {"discrimination": 2, "retaliation": 1}
