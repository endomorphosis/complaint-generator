"""
Unit tests for Batch 223: DependencyGraph analysis methods.

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


class TestNodeTypeSet:
    def test_empty_graph(self, graph):
        assert graph.node_type_set() == []

    def test_node_type_set_sorted(self, graph):
        graph.add_node(create_node("n1", node_type=NodeType.EVIDENCE))
        graph.add_node(create_node("n2", node_type=NodeType.CLAIM))
        graph.add_node(create_node("n3", node_type=NodeType.REQUIREMENT))
        assert graph.node_type_set() == ["claim", "evidence", "requirement"]


class TestDependencyTypeSet:
    def test_empty_graph(self, graph):
        assert graph.dependency_type_set() == []

    def test_dependency_type_set_sorted(self, graph):
        graph.add_node(create_node("n1"))
        graph.add_node(create_node("n2"))
        graph.add_node(create_node("n3"))
        graph.add_dependency(create_dependency("d1", "n1", "n2", DependencyType.SUPPORTS))
        graph.add_dependency(create_dependency("d2", "n2", "n3", DependencyType.CONTRADICTS))
        graph.add_dependency(create_dependency("d3", "n3", "n1", DependencyType.DEPENDS_ON))
        assert graph.dependency_type_set() == ["contradicts", "depends_on", "supports"]


class TestNodesWithAttributesCount:
    def test_nodes_with_attributes_count(self, graph):
        graph.add_node(create_node("n1", attributes={"key": "value"}))
        graph.add_node(create_node("n2", attributes={}))
        graph.add_node(create_node("n3", attributes={"x": 1}))
        assert graph.nodes_with_attributes_count() == 2


class TestDescriptionCounts:
    def test_nodes_with_description_count(self, graph):
        graph.add_node(create_node("n1", description="desc"))
        graph.add_node(create_node("n2", description=""))
        graph.add_node(create_node("n3", description="more"))
        assert graph.nodes_with_description_count() == 2

    def test_nodes_missing_description_count(self, graph):
        graph.add_node(create_node("n1", description="desc"))
        graph.add_node(create_node("n2", description=""))
        graph.add_node(create_node("n3", description=""))
        assert graph.nodes_missing_description_count() == 2


class TestNodesBySatisfaction:
    def test_nodes_by_satisfaction(self, graph):
        graph.add_node(create_node("n1", satisfied=True))
        graph.add_node(create_node("n2", satisfied=False))
        graph.add_node(create_node("n3", satisfied=True))

        satisfied_nodes = graph.nodes_by_satisfaction(True)
        unsatisfied_nodes = graph.nodes_by_satisfaction(False)

        assert {n.id for n in satisfied_nodes} == {"n1", "n3"}
        assert {n.id for n in unsatisfied_nodes} == {"n2"}


class TestDependencyCountForNode:
    def test_dependency_count_for_node(self, graph):
        graph.add_node(create_node("n1"))
        graph.add_node(create_node("n2"))
        graph.add_node(create_node("n3"))
        graph.add_dependency(create_dependency("d1", "n1", "n2"))
        graph.add_dependency(create_dependency("d2", "n2", "n3"))
        graph.add_dependency(create_dependency("d3", "n1", "n3"))

        assert graph.dependency_count_for_node("n1") == 2
        assert graph.dependency_count_for_node("n2") == 2
        assert graph.dependency_count_for_node("n3") == 2


class TestDependenciesRequiredRatio:
    def test_dependencies_required_ratio_empty(self, graph):
        assert graph.dependencies_required_ratio() == 0.0

    def test_dependencies_required_ratio(self, graph):
        graph.add_node(create_node("n1"))
        graph.add_node(create_node("n2"))
        graph.add_dependency(create_dependency("d1", "n1", "n2", required=True))
        graph.add_dependency(create_dependency("d2", "n2", "n1", required=False))
        graph.add_dependency(create_dependency("d3", "n1", "n2", required=True))

        assert graph.dependencies_required_ratio() == pytest.approx(2 / 3)


class TestDependencyStrengthStats:
    def test_dependency_strength_stats_empty(self, graph):
        assert graph.dependency_strength_stats() == {"avg": 0.0, "min": 0.0, "max": 0.0}

    def test_dependency_strength_stats(self, graph):
        graph.add_node(create_node("n1"))
        graph.add_node(create_node("n2"))
        graph.add_dependency(create_dependency("d1", "n1", "n2", strength=0.5))
        graph.add_dependency(create_dependency("d2", "n2", "n1", strength=0.8))
        graph.add_dependency(create_dependency("d3", "n1", "n2", strength=0.2))

        stats = graph.dependency_strength_stats()
        assert stats["avg"] == pytest.approx((0.5 + 0.8 + 0.2) / 3)
        assert stats["min"] == pytest.approx(0.2)
        assert stats["max"] == pytest.approx(0.8)


class TestAverageRequiredDependenciesPerNode:
    def test_average_required_dependencies_per_node_empty(self, graph):
        assert graph.average_required_dependencies_per_node() == 0.0

    def test_average_required_dependencies_per_node(self, graph):
        graph.add_node(create_node("n1"))
        graph.add_node(create_node("n2"))
        graph.add_node(create_node("n3"))
        graph.add_dependency(create_dependency("d1", "n1", "n2", required=True))
        graph.add_dependency(create_dependency("d2", "n2", "n3", required=False))
        graph.add_dependency(create_dependency("d3", "n1", "n3", required=True))

        # Required connections counted twice (n1-n2, n1-n3) -> 4 total / 2 = 2
        assert graph.average_required_dependencies_per_node() == pytest.approx(2 / 3)
