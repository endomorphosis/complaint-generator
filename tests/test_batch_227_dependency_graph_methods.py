"""
Unit tests for Batch 227: DependencyGraph analysis methods.
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
):
    return DependencyNode(
        id=node_id,
        node_type=node_type,
        name=name,
        description=description,
        satisfied=satisfied,
        confidence=confidence,
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


class TestNodeAndDependencyIds:
    def test_empty_ids(self, graph):
        assert graph.node_ids() == []
        assert graph.dependency_ids() == []

    def test_sorted_ids(self, graph):
        graph.add_node(create_node("n2"))
        graph.add_node(create_node("n1"))
        graph.add_node(create_node("n3"))
        graph.add_dependency(create_dependency("d2", "n2", "n1"))
        graph.add_dependency(create_dependency("d1", "n1", "n3"))

        assert graph.node_ids() == ["n1", "n2", "n3"]
        assert graph.dependency_ids() == ["d1", "d2"]


class TestSatisfiedNodeRatio:
    def test_empty_graph(self, graph):
        assert graph.satisfied_node_ratio() == 0.0

    def test_satisfied_ratio(self, graph):
        graph.add_node(create_node("n1", satisfied=True))
        graph.add_node(create_node("n2", satisfied=False))
        graph.add_node(create_node("n3", satisfied=True))

        assert graph.satisfied_node_ratio() == pytest.approx(2 / 3)


class TestDependencyDensity:
    def test_density_empty(self, graph):
        assert graph.dependency_density() == 0.0

    def test_density(self, graph):
        graph.add_node(create_node("n1"))
        graph.add_node(create_node("n2"))
        graph.add_node(create_node("n3"))
        graph.add_dependency(create_dependency("d1", "n1", "n2"))
        graph.add_dependency(create_dependency("d2", "n2", "n3"))

        assert graph.dependency_density() == pytest.approx(2 / 6)


class TestAverageDependenciesBySatisfaction:
    def test_average_dependencies_per_satisfied_node(self, graph):
        graph.add_node(create_node("n1", satisfied=True))
        graph.add_node(create_node("n2", satisfied=True))
        graph.add_node(create_node("n3", satisfied=False))
        graph.add_dependency(create_dependency("d1", "n1", "n2"))
        graph.add_dependency(create_dependency("d2", "n1", "n3"))

        assert graph.average_dependencies_per_satisfied_node() == pytest.approx(1.5)
        assert graph.average_dependencies_per_unsatisfied_node() == pytest.approx(1.0)

    def test_average_dependencies_per_unsatisfied_node_empty(self, graph):
        graph.add_node(create_node("n1", satisfied=True))
        assert graph.average_dependencies_per_unsatisfied_node() == 0.0


class TestDependencyStrengthExtremes:
    def test_strength_required_optional_empty(self, graph):
        assert graph.dependency_strength_min_required() == 0.0
        assert graph.dependency_strength_max_required() == 0.0
        assert graph.dependency_strength_min_optional() == 0.0
        assert graph.dependency_strength_max_optional() == 0.0

    def test_strength_required_optional(self, graph):
        graph.add_node(create_node("n1"))
        graph.add_node(create_node("n2"))
        graph.add_dependency(create_dependency("d1", "n1", "n2", required=True, strength=0.6))
        graph.add_dependency(create_dependency("d2", "n2", "n1", required=True, strength=0.9))
        graph.add_dependency(create_dependency("d3", "n1", "n2", required=False, strength=0.4))
        graph.add_dependency(create_dependency("d4", "n2", "n1", required=False, strength=0.7))

        assert graph.dependency_strength_min_required() == pytest.approx(0.6)
        assert graph.dependency_strength_max_required() == pytest.approx(0.9)
        assert graph.dependency_strength_min_optional() == pytest.approx(0.4)
        assert graph.dependency_strength_max_optional() == pytest.approx(0.7)
