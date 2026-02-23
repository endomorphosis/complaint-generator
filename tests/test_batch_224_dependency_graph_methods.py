"""
Unit tests for Batch 224: DependencyGraph analysis methods.

Tests 10 analytics methods added to DependencyGraph.
"""

import pytest

from complaint_phases.dependency_graph import (
    DependencyGraph,
    DependencyNode,
    Dependency,
    NodeType,
    DependencyType,
)


@pytest.fixture
def graph():
    return DependencyGraph()


def create_node(
    node_id,
    node_type=NodeType.CLAIM,
    name="Node",
    description="",
    satisfied=False,
    confidence=0.0,
    attributes=None,
):
    if attributes is None:
        attributes = {}
    return DependencyNode(
        id=node_id,
        node_type=node_type,
        name=name,
        description=description,
        satisfied=satisfied,
        confidence=confidence,
        attributes=attributes,
    )


def create_dependency(
    dep_id,
    source_id,
    target_id,
    dep_type=DependencyType.REQUIRES,
    required=True,
    strength=1.0,
):
    return Dependency(
        id=dep_id,
        source_id=source_id,
        target_id=target_id,
        dependency_type=dep_type,
        required=required,
        strength=strength,
    )


class TestNodeConfidenceStats:
    def test_confidence_min_max_range_empty(self, graph):
        assert graph.node_confidence_min() == 0.0
        assert graph.node_confidence_max() == 0.0
        assert graph.node_confidence_range() == 0.0

    def test_confidence_min_max_range(self, graph):
        graph.add_node(create_node("n1", confidence=0.2))
        graph.add_node(create_node("n2", confidence=0.8))
        graph.add_node(create_node("n3", confidence=0.5))

        assert graph.node_confidence_min() == pytest.approx(0.2)
        assert graph.node_confidence_max() == pytest.approx(0.8)
        assert graph.node_confidence_range() == pytest.approx(0.6)


class TestAverageConfidenceBySatisfaction:
    def test_average_satisfied_confidence_empty(self, graph):
        assert graph.average_satisfied_confidence() == 0.0
        assert graph.average_unsatisfied_confidence() == 0.0

    def test_average_satisfied_confidence(self, graph):
        graph.add_node(create_node("n1", satisfied=True, confidence=0.9))
        graph.add_node(create_node("n2", satisfied=True, confidence=0.7))
        graph.add_node(create_node("n3", satisfied=False, confidence=0.2))

        assert graph.average_satisfied_confidence() == pytest.approx(0.8)
        assert graph.average_unsatisfied_confidence() == pytest.approx(0.2)


class TestOptionalDependencyCount:
    def test_optional_dependency_count(self, graph):
        graph.add_node(create_node("n1"))
        graph.add_node(create_node("n2"))
        graph.add_dependency(create_dependency("d1", "n1", "n2", required=True))
        graph.add_dependency(create_dependency("d2", "n2", "n1", required=False))
        graph.add_dependency(create_dependency("d3", "n1", "n2", required=False))

        assert graph.optional_dependency_count() == 2


class TestRequiredDependencyCountForNode:
    def test_required_dependency_count_for_node(self, graph):
        graph.add_node(create_node("n1"))
        graph.add_node(create_node("n2"))
        graph.add_node(create_node("n3"))
        graph.add_dependency(create_dependency("d1", "n1", "n2", required=True))
        graph.add_dependency(create_dependency("d2", "n2", "n3", required=False))
        graph.add_dependency(create_dependency("d3", "n1", "n3", required=True))

        assert graph.required_dependency_count_for_node("n1") == 2
        assert graph.required_dependency_count_for_node("n2") == 1
        assert graph.required_dependency_count_for_node("n3") == 1


class TestNodesWithoutDependenciesCount:
    def test_nodes_without_dependencies_count(self, graph):
        graph.add_node(create_node("n1"))
        graph.add_node(create_node("n2"))
        graph.add_node(create_node("n3"))
        graph.add_dependency(create_dependency("d1", "n1", "n2"))

        assert graph.nodes_without_dependencies_count() == 1


class TestDependencyStrengthAverages:
    def test_dependency_strength_average_required_empty(self, graph):
        assert graph.dependency_strength_average_required() == 0.0
        assert graph.dependency_strength_average_optional() == 0.0

    def test_dependency_strength_average_required_optional(self, graph):
        graph.add_node(create_node("n1"))
        graph.add_node(create_node("n2"))
        graph.add_dependency(create_dependency("d1", "n1", "n2", required=True, strength=0.6))
        graph.add_dependency(create_dependency("d2", "n2", "n1", required=True, strength=0.8))
        graph.add_dependency(create_dependency("d3", "n1", "n2", required=False, strength=0.4))

        assert graph.dependency_strength_average_required() == pytest.approx(0.7)
        assert graph.dependency_strength_average_optional() == pytest.approx(0.4)
