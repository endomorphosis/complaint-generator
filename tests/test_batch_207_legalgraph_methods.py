"""
Unit tests for Batch 207: LegalGraph analysis methods.

Tests the 10 legal graph analysis and statistics methods added to LegalGraph.
"""

import pytest
from complaint_phases.legal_graph import LegalGraph, LegalElement, LegalRelation


@pytest.fixture
def legal_graph():
    """Create an empty LegalGraph instance for testing."""
    return LegalGraph()


def create_element(element_id, element_type='statute', name='Test Element', 
                   description='', citation='', attributes=None):
    """Helper to create a LegalElement."""
    if attributes is None:
        attributes = {}
    return LegalElement(
        id=element_id,
        element_type=element_type,
        name=name,
        description=description,
        citation=citation,
        attributes=attributes
    )


def create_relation(relation_id, source_id, target_id, relation_type='requires'):
    """Helper to create a LegalRelation."""
    return LegalRelation(
        id=relation_id,
        source_id=source_id,
        target_id=target_id,
        relation_type=relation_type,
        attributes={}
    )


# ============================================================================ #
# Test total_elements()
# ============================================================================ #

class TestTotalElements:
    def test_empty_graph(self, legal_graph):
        assert legal_graph.total_elements() == 0
    
    def test_single_element(self, legal_graph):
        elem = create_element('e1')
        legal_graph.add_element(elem)
        assert legal_graph.total_elements() == 1
    
    def test_multiple_elements(self, legal_graph):
        for i in range(5):
            elem = create_element(f'e{i}')
            legal_graph.add_element(elem)
        assert legal_graph.total_elements() == 5


# ============================================================================ #
# Test total_relations()
# ============================================================================ #

class TestTotalRelations:
    def test_empty_graph(self, legal_graph):
        assert legal_graph.total_relations() == 0
    
    def test_single_relation(self, legal_graph):
        legal_graph.add_element(create_element('e1'))
        legal_graph.add_element(create_element('e2'))
        rel = create_relation('r1', 'e1', 'e2')
        legal_graph.add_relation(rel)
        assert legal_graph.total_relations() == 1
    
    def test_multiple_relations(self, legal_graph):
        for i in range(4):
            legal_graph.add_element(create_element(f'e{i}'))
        for i in range(3):
            rel = create_relation(f'r{i}', f'e{i}', f'e{i+1}')
            legal_graph.add_relation(rel)
        assert legal_graph.total_relations() == 3


# ============================================================================ #
# Test element_type_frequency()
# ============================================================================ #

class TestElementTypeFrequency:
    def test_empty_graph(self, legal_graph):
        assert legal_graph.element_type_frequency() == {}
    
    def test_single_type(self, legal_graph):
        legal_graph.add_element(create_element('e1', element_type='statute'))
        legal_graph.add_element(create_element('e2', element_type='statute'))
        freq = legal_graph.element_type_frequency()
        assert freq == {'statute': 2}
    
    def test_multiple_types(self, legal_graph):
        legal_graph.add_element(create_element('e1', element_type='statute'))
        legal_graph.add_element(create_element('e2', element_type='requirement'))
        legal_graph.add_element(create_element('e3', element_type='statute'))
        legal_graph.add_element(create_element('e4', element_type='regulation'))
        legal_graph.add_element(create_element('e5', element_type='requirement'))
        legal_graph.add_element(create_element('e6', element_type='requirement'))
        freq = legal_graph.element_type_frequency()
        assert freq == {'statute': 2, 'requirement': 3, 'regulation': 1}


# ============================================================================ #
# Test most_common_element_type()
# ============================================================================ #

class TestMostCommonElementType:
    def test_empty_graph(self, legal_graph):
        assert legal_graph.most_common_element_type() == 'none'
    
    def test_single_element(self, legal_graph):
        legal_graph.add_element(create_element('e1', element_type='regulation'))
        assert legal_graph.most_common_element_type() == 'regulation'
    
    def test_clear_winner(self, legal_graph):
        types = ['statute', 'requirement', 'statute', 'statute', 'regulation']
        for i, etype in enumerate(types):
            legal_graph.add_element(create_element(f'e{i}', element_type=etype))
        assert legal_graph.most_common_element_type() == 'statute'


# ============================================================================ #
# Test relation_type_frequency()
# ============================================================================ #

class TestRelationTypeFrequency:
    def test_empty_graph(self, legal_graph):
        assert legal_graph.relation_type_frequency() == {}
    
    def test_single_type(self, legal_graph):
        for i in range(3):
            legal_graph.add_element(create_element(f'e{i}'))
        legal_graph.add_relation(create_relation('r1', 'e0', 'e1', 'requires'))
        legal_graph.add_relation(create_relation('r2', 'e1', 'e2', 'requires'))
        freq = legal_graph.relation_type_frequency()
        assert freq == {'requires': 2}
    
    def test_multiple_types(self, legal_graph):
        for i in range(4):
            legal_graph.add_element(create_element(f'e{i}'))
        legal_graph.add_relation(create_relation('r1', 'e0', 'e1', 'requires'))
        legal_graph.add_relation(create_relation('r2', 'e1', 'e2', 'supplements'))
        legal_graph.add_relation(create_relation('r3', 'e2', 'e3', 'requires'))
        freq = legal_graph.relation_type_frequency()
        assert freq == {'requires': 2, 'supplements': 1}


# ============================================================================ #
# Test most_connected_element()
# ============================================================================ #

class TestMostConnectedElement:
    def test_empty_graph(self, legal_graph):
        assert legal_graph.most_connected_element() == 'none'
    
    def test_no_relations(self, legal_graph):
        legal_graph.add_element(create_element('e1'))
        legal_graph.add_element(create_element('e2'))
        # Should return one of them (all have 0 connections)
        result = legal_graph.most_connected_element()
        assert result in ['e1', 'e2']
    
    def test_clear_hub_element(self, legal_graph):
        # e1 is connected to e2, e3, e4 (hub)
        for i in range(4):
            legal_graph.add_element(create_element(f'e{i}'))
        legal_graph.add_relation(create_relation('r1', 'e0', 'e1'))
        legal_graph.add_relation(create_relation('r2', 'e0', 'e2'))
        legal_graph.add_relation(create_relation('r3', 'e0', 'e3'))
        assert legal_graph.most_connected_element() == 'e0'


# ============================================================================ #
# Test average_relations_per_element()
# ============================================================================ #

class TestAverageRelationsPerElement:
    def test_empty_graph(self, legal_graph):
        assert legal_graph.average_relations_per_element() == 0.0
    
    def test_no_relations(self, legal_graph):
        legal_graph.add_element(create_element('e1'))
        legal_graph.add_element(create_element('e2'))
        assert legal_graph.average_relations_per_element() == 0.0
    
    def test_linear_chain(self, legal_graph):
        # e0 -> e1 -> e2 (2 relations, 3 elements)
        for i in range(3):
            legal_graph.add_element(create_element(f'e{i}'))
        legal_graph.add_relation(create_relation('r1', 'e0', 'e1'))
        legal_graph.add_relation(create_relation('r2', 'e1', 'e2'))
        avg = legal_graph.average_relations_per_element()
        # e0: 1 rel, e1: 2 rels, e2: 1 rel -> total 4 / 2 = 2, avg = 2/3
        assert abs(avg - (2/3)) < 0.01
    
    def test_fully_connected_three(self, legal_graph):
        # 3 elements with 3 relations (each pair connected)
        for i in range(3):
            legal_graph.add_element(create_element(f'e{i}'))
        legal_graph.add_relation(create_relation('r1', 'e0', 'e1'))
        legal_graph.add_relation(create_relation('r2', 'e1', 'e2'))
        legal_graph.add_relation(create_relation('r3', 'e0', 'e2'))
        avg = legal_graph.average_relations_per_element()
        # Each element has 2 connections, total 6 / 2 = 3, avg = 3/3 = 1.0
        assert abs(avg - 1.0) < 0.01


# ============================================================================ #
# Test requirements_coverage()
# ============================================================================ #

class TestRequirementsCoverage:
    def test_empty_graph(self, legal_graph):
        coverage = legal_graph.requirements_coverage()
        assert coverage == {
            'total_requirements': 0,
            'claim_types_covered': 0,
            'avg_requirements_per_claim': 0.0
        }
    
    def test_no_requirements(self, legal_graph):
        legal_graph.add_element(create_element('e1', element_type='statute'))
        coverage = legal_graph.requirements_coverage()
        assert coverage['total_requirements'] == 0
        assert coverage['claim_types_covered'] == 0
    
    def test_single_requirement_single_claim(self, legal_graph):
        req = create_element(
            'r1', 
            element_type='requirement',
            attributes={'applicable_claim_types': ['discrimination']}
        )
        legal_graph.add_element(req)
        coverage = legal_graph.requirements_coverage()
        assert coverage['total_requirements'] == 1
        assert coverage['claim_types_covered'] == 1
        assert coverage['avg_requirements_per_claim'] == 1.0
    
    def test_multiple_requirements_multiple_claims(self, legal_graph):
        req1 = create_element(
            'r1',
            element_type='requirement',
            attributes={'applicable_claim_types': ['discrimination', 'retaliation']}
        )
        req2 = create_element(
            'r2',
            element_type='procedural_requirement',
            attributes={'applicable_claim_types': ['discrimination']}
        )
        req3 = create_element(
            'r3',
            element_type='requirement',
            attributes={'applicable_claim_types': ['wrongful_termination']}
        )
        legal_graph.add_element(req1)
        legal_graph.add_element(req2)
        legal_graph.add_element(req3)
        
        coverage = legal_graph.requirements_coverage()
        assert coverage['total_requirements'] == 3
        assert coverage['claim_types_covered'] == 3  # discrimination, retaliation, wrongful_termination
        # Total mappings: 2 + 1 + 1 = 4, avg = 4/3
        assert abs(coverage['avg_requirements_per_claim'] - (4/3)) < 0.01


# ============================================================================ #
# Test elements_with_citations()
# ============================================================================ #

class TestElementsWithCitations:
    def test_empty_graph(self, legal_graph):
        assert legal_graph.elements_with_citations() == 0
    
    def test_no_citations(self, legal_graph):
        legal_graph.add_element(create_element('e1', citation=''))
        legal_graph.add_element(create_element('e2', citation=''))
        assert legal_graph.elements_with_citations() == 0
    
    def test_all_cited(self, legal_graph):
        legal_graph.add_element(create_element('e1', citation='42 U.S.C. § 1983'))
        legal_graph.add_element(create_element('e2', citation='18 U.S.C. § 242'))
        assert legal_graph.elements_with_citations() == 2
    
    def test_mixed_citations(self, legal_graph):
        legal_graph.add_element(create_element('e1', citation='42 U.S.C. § 1983'))
        legal_graph.add_element(create_element('e2', citation=''))
        legal_graph.add_element(create_element('e3', citation='Title VII'))
        legal_graph.add_element(create_element('e4', citation=''))
        assert legal_graph.elements_with_citations() == 2


# ============================================================================ #
# Test graph_density()
# ============================================================================ #

class TestGraphDensity:
    def test_empty_graph(self, legal_graph):
        assert legal_graph.graph_density() == 0.0
    
    def test_single_element(self, legal_graph):
        legal_graph.add_element(create_element('e1'))
        assert legal_graph.graph_density() == 0.0
    
    def test_two_elements_no_relation(self, legal_graph):
        legal_graph.add_element(create_element('e1'))
        legal_graph.add_element(create_element('e2'))
        # Max possible: 1, actual: 0
        assert legal_graph.graph_density() == 0.0
    
    def test_two_elements_one_relation(self, legal_graph):
        legal_graph.add_element(create_element('e1'))
        legal_graph.add_element(create_element('e2'))
        legal_graph.add_relation(create_relation('r1', 'e1', 'e2'))
        # Max possible: 1, actual: 1
        assert legal_graph.graph_density() == 1.0
    
    def test_three_elements_partial(self, legal_graph):
        for i in range(3):
            legal_graph.add_element(create_element(f'e{i}'))
        legal_graph.add_relation(create_relation('r1', 'e0', 'e1'))
        # Max possible: 3, actual: 1
        assert abs(legal_graph.graph_density() - (1/3)) < 0.01
    
    def test_fully_connected(self, legal_graph):
        for i in range(4):
            legal_graph.add_element(create_element(f'e{i}'))
        # Connect all pairs
        legal_graph.add_relation(create_relation('r1', 'e0', 'e1'))
        legal_graph.add_relation(create_relation('r2', 'e0', 'e2'))
        legal_graph.add_relation(create_relation('r3', 'e0', 'e3'))
        legal_graph.add_relation(create_relation('r4', 'e1', 'e2'))
        legal_graph.add_relation(create_relation('r5', 'e1', 'e3'))
        legal_graph.add_relation(create_relation('r6', 'e2', 'e3'))
        # Max possible: 4*3/2 = 6, actual: 6
        assert legal_graph.graph_density() == 1.0


# ============================================================================ #
# Integration test
# ============================================================================ #

class TestBatch207Integration:
    def test_comprehensive_legal_graph_analysis(self, legal_graph):
        """Test that all Batch 207 methods work together correctly."""
        # Build a realistic legal graph
        # Add statutes
        legal_graph.add_element(create_element(
            's1', element_type='statute', name='Title VII',
            citation='42 U.S.C. § 2000e'
        ))
        legal_graph.add_element(create_element(
            's2', element_type='statute', name='Section 1983',
            citation='42 U.S.C. § 1983'
        ))
        
        # Add requirements
        legal_graph.add_element(create_element(
            'r1', element_type='requirement', name='Protected class membership',
            citation='', attributes={'applicable_claim_types': ['discrimination']}
        ))
        legal_graph.add_element(create_element(
            'r2', element_type='requirement', name='Adverse employment action',
            attributes={'applicable_claim_types': ['discrimination', 'retaliation']}
        ))
        legal_graph.add_element(create_element(
            'r3', element_type='procedural_requirement', name='EEOC filing',
            citation='29 C.F.R. § 1601',
            attributes={'applicable_claim_types': ['discrimination']}
        ))
        
        # Add regulation
        legal_graph.add_element(create_element(
            'reg1', element_type='regulation', name='EEOC procedures',
            citation='29 C.F.R. Part 1601'
        ))
        
        # Add relations
        legal_graph.add_relation(create_relation('rel1', 's1', 'r1', 'requires'))
        legal_graph.add_relation(create_relation('rel2', 's1', 'r2', 'requires'))
        legal_graph.add_relation(create_relation('rel3', 's1', 'r3', 'requires'))
        legal_graph.add_relation(create_relation('rel4', 'reg1', 'r3', 'defines'))
        
        # Test all methods
        assert legal_graph.total_elements() == 6
        assert legal_graph.total_relations() == 4
        
        elem_freq = legal_graph.element_type_frequency()
        assert elem_freq == {'statute': 2, 'requirement': 2, 'procedural_requirement': 1, 'regulation': 1}
        assert legal_graph.most_common_element_type() in ['statute', 'requirement']
        
        rel_freq = legal_graph.relation_type_frequency()
        assert rel_freq == {'requires': 3, 'defines': 1}
        
        # s1 has 3 relations, should be most connected
        assert legal_graph.most_connected_element() == 's1'
        
        avg_rel = legal_graph.average_relations_per_element()
        # Total connection counts: s1=3, s2=0, r1=1, r2=1, r3=2, reg1=1 = 8
        # Divided by 2 = 4, avg = 4/6 = 0.667
        assert abs(avg_rel - (2/3)) < 0.01
        
        coverage = legal_graph.requirements_coverage()
        assert coverage['total_requirements'] == 3
        assert coverage['claim_types_covered'] == 2  # discrimination, retaliation
        
        assert legal_graph.elements_with_citations() == 4  # s1, s2, r3, reg1
        
        density = legal_graph.graph_density()
        # 6 elements: max = 6*5/2 = 15, actual = 4
        assert abs(density - (4/15)) < 0.01
