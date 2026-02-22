"""
Test suite for Batch 209: DependencyGraph analytical methods.

Tests the 10 new methods added to DependencyGraph:
- total_nodes, total_dependencies, node_type_distribution
- dependency_type_distribution, satisfied_node_count, unsatisfied_node_count
- average_confidence, required_dependency_count, average_dependencies_per_node
- most_dependent_node
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
def empty_graph():
    """Create an empty dependency graph."""
    return DependencyGraph()


@pytest.fixture
def simple_graph():
    """Create a simple dependency graph with a few nodes."""
    graph = DependencyGraph()
    node1 = DependencyNode(id="node1", node_type=NodeType.CLAIM, name="Claim 1", confidence=0.8)
    node2 = DependencyNode(id="node2", node_type=NodeType.EVIDENCE, name="Evidence 1", confidence=0.9)
    node3 = DependencyNode(id="node3", node_type=NodeType.REQUIREMENT, name="Req 1", confidence=0.7)
    graph.add_node(node1)
    graph.add_node(node2)
    graph.add_node(node3)
    dep1 = Dependency(id="dep1", source_id="node1", target_id="node2", dependency_type=DependencyType.SUPPORTS, required=True)
    dep2 = Dependency(id="dep2", source_id="node2", target_id="node3", dependency_type=DependencyType.DEPENDS_ON, required=False)
    graph.add_dependency(dep1)
    graph.add_dependency(dep2)
    return graph


@pytest.fixture
def complex_graph():
    """Create a more complex graph with various types."""
    graph = DependencyGraph()
    # Add nodes of different types
    nodes = [
        DependencyNode(id="claim1", node_type=NodeType.CLAIM, name="Claim 1", confidence=0.85),
        DependencyNode(id="claim2", node_type=NodeType.CLAIM, name="Claim 2", confidence=0.75),
        DependencyNode(id="ev1", node_type=NodeType.EVIDENCE, name="Evidence 1", confidence=0.95),
        DependencyNode(id="ev2", node_type=NodeType.EVIDENCE, name="Evidence 2", confidence=0.88),
        DependencyNode(id="req1", node_type=NodeType.REQUIREMENT, name="Req 1", confidence=0.65),
        DependencyNode(id="req2", node_type=NodeType.REQUIREMENT, name="Req 2", confidence=0.70),
    ]
    for node in nodes:
        graph.add_node(node)
    
    # Add various dependencies
    deps = [
        Dependency(id="d1", source_id="claim1", target_id="ev1", dependency_type=DependencyType.SUPPORTS, required=True),
        Dependency(id="d2", source_id="claim1", target_id="req1", dependency_type=DependencyType.DEPENDS_ON, required=True),
        Dependency(id="d3", source_id="claim2", target_id="ev2", dependency_type=DependencyType.SUPPORTS, required=True),
        Dependency(id="d4", source_id="ev1", target_id="ev2", dependency_type=DependencyType.CONTRADICTS, required=False),
        Dependency(id="d5", source_id="req1", target_id="req2", dependency_type=DependencyType.DEPENDS_ON, required=False),
    ]
    for dep in deps:
        graph.add_dependency(dep)
    
    # Mark some nodes as satisfied
    graph.nodes["claim1"].satisfied = True
    graph.nodes["ev1"].satisfied = True
    graph.nodes["ev2"].satisfied = True
    
    return graph


# -------------------------------------------------------------------------
# Test total_nodes
# -------------------------------------------------------------------------
class TestTotalNodes:
    def test_empty_graph(self, empty_graph):
        assert empty_graph.total_nodes() == 0
    
    def test_simple_graph(self, simple_graph):
        assert simple_graph.total_nodes() == 3
    
    def test_complex_graph(self, complex_graph):
        assert complex_graph.total_nodes() == 6
    
    def test_after_adding_nodes(self, empty_graph):
        assert empty_graph.total_nodes() == 0
        empty_graph.add_node(DependencyNode(id="n1", node_type=NodeType.CLAIM, name="Node 1"))
        assert empty_graph.total_nodes() == 1
        empty_graph.add_node(DependencyNode(id="n2", node_type=NodeType.EVIDENCE, name="Node 2"))
        assert empty_graph.total_nodes() == 2


# -------------------------------------------------------------------------
# Test total_dependencies
# -------------------------------------------------------------------------
class TestTotalDependencies:
    def test_empty_graph(self, empty_graph):
        assert empty_graph.total_dependencies() == 0
    
    def test_simple_graph(self, simple_graph):
        assert simple_graph.total_dependencies() == 2
    
    def test_complex_graph(self, complex_graph):
        assert complex_graph.total_dependencies() == 5
    
    def test_after_adding_dependencies(self, simple_graph):
        initial = simple_graph.total_dependencies()
        new_dep = Dependency(id="new_dep", source_id="node1", target_id="node3", dependency_type=DependencyType.SUPPORTS)
        simple_graph.add_dependency(new_dep)
        assert simple_graph.total_dependencies() == initial + 1


# -------------------------------------------------------------------------
# Test node_type_distribution
# -------------------------------------------------------------------------
class TestNodeTypeDistribution:
    def test_empty_graph(self, empty_graph):
        dist = empty_graph.node_type_distribution()
        assert dist == {}
    
    def test_simple_graph(self, simple_graph):
        dist = simple_graph.node_type_distribution()
        assert dist.get("claim", 0) == 1
        assert dist.get("evidence", 0) == 1
        assert dist.get("requirement", 0) == 1
    
    def test_complex_graph(self, complex_graph):
        dist = complex_graph.node_type_distribution()
        assert dist.get("claim", 0) == 2
        assert dist.get("evidence", 0) == 2
        assert dist.get("requirement", 0) == 2
    
    def test_single_type(self):
        graph = DependencyGraph()
        graph.add_node(DependencyNode(id="c1", node_type=NodeType.CLAIM, name="Claim 1"))
        graph.add_node(DependencyNode(id="c2", node_type=NodeType.CLAIM, name="Claim 2"))
        graph.add_node(DependencyNode(id="c3", node_type=NodeType.CLAIM, name="Claim 3"))
        dist = graph.node_type_distribution()
        assert dist.get("claim", 0) == 3
        assert len(dist) == 1


# -------------------------------------------------------------------------
# Test dependency_type_distribution
# -------------------------------------------------------------------------
class TestDependencyTypeDistribution:
    def test_empty_graph(self, empty_graph):
        dist = empty_graph.dependency_type_distribution()
        assert dist == {}
    
    def test_simple_graph(self, simple_graph):
        dist = simple_graph.dependency_type_distribution()
        assert dist.get("supports", 0) == 1
        assert dist.get("depends_on", 0) == 1
    
    def test_complex_graph(self, complex_graph):
        dist = complex_graph.dependency_type_distribution()
        assert dist.get("supports", 0) == 2
        assert dist.get("depends_on", 0) == 2
        assert dist.get("contradicts", 0) == 1
    
    def test_single_dependency_type(self):
        graph = DependencyGraph()
        graph.add_node(DependencyNode(id="n1", node_type=NodeType.CLAIM, name="Node 1"))
        graph.add_node(DependencyNode(id="n2", node_type=NodeType.EVIDENCE, name="Node 2"))
        graph.add_node(DependencyNode(id="n3", node_type=NodeType.EVIDENCE, name="Node 3"))
        graph.add_dependency(Dependency(id="d1", source_id="n1", target_id="n2", dependency_type=DependencyType.SUPPORTS))
        graph.add_dependency(Dependency(id="d2", source_id="n1", target_id="n3", dependency_type=DependencyType.SUPPORTS))
        dist = graph.dependency_type_distribution()
        assert dist.get("supports", 0) == 2
        assert len(dist) == 1


# -------------------------------------------------------------------------
# Test satisfied_node_count
# -------------------------------------------------------------------------
class TestSatisfiedNodeCount:
    def test_empty_graph(self, empty_graph):
        assert empty_graph.satisfied_node_count() == 0
    
    def test_no_satisfied(self, simple_graph):
        # Default satisfied=False
        assert simple_graph.satisfied_node_count() == 0
    
    def test_complex_graph(self, complex_graph):
        # complex_graph has 3 nodes marked as satisfied
        assert complex_graph.satisfied_node_count() == 3
    
    def test_all_satisfied(self, simple_graph):
        for node in simple_graph.nodes.values():
            node.satisfied = True
        assert simple_graph.satisfied_node_count() == 3


# -------------------------------------------------------------------------
# Test unsatisfied_node_count
# -------------------------------------------------------------------------
class TestUnsatisfiedNodeCount:
    def test_empty_graph(self, empty_graph):
        assert empty_graph.unsatisfied_node_count() == 0
    
    def test_all_unsatisfied(self, simple_graph):
        assert simple_graph.unsatisfied_node_count() == 3
    
    def test_complex_graph(self, complex_graph):
        # 6 total nodes, 3 satisfied = 3 unsatisfied
        assert complex_graph.unsatisfied_node_count() == 3
    
    def test_none_unsatisfied(self, simple_graph):
        for node in simple_graph.nodes.values():
            node.satisfied = True
        assert simple_graph.unsatisfied_node_count() == 0


# -------------------------------------------------------------------------
# Test average_confidence
# -------------------------------------------------------------------------
class TestAverageConfidence:
    def test_empty_graph(self, empty_graph):
        assert empty_graph.average_confidence() == 0.0
    
    def test_simple_graph(self, simple_graph):
        # Confidences: 0.8, 0.9, 0.7
        avg = simple_graph.average_confidence()
        expected = (0.8 + 0.9 + 0.7) / 3
        assert abs(avg - expected) < 0.01
    
    def test_complex_graph(self, complex_graph):
        # Confidences: 0.85, 0.75, 0.95, 0.88, 0.65, 0.70
        avg = complex_graph.average_confidence()
        expected = (0.85 + 0.75 + 0.95 + 0.88 + 0.65 + 0.70) / 6
        assert abs(avg - expected) < 0.01
    
    def test_uniform_confidence(self):
        graph = DependencyGraph()
        graph.add_node(DependencyNode(id="n1", node_type=NodeType.CLAIM, name="Node 1", confidence=0.5))
        graph.add_node(DependencyNode(id="n2", node_type=NodeType.CLAIM, name="Node 2", confidence=0.5))
        graph.add_node(DependencyNode(id="n3", node_type=NodeType.CLAIM, name="Node 3", confidence=0.5))
        assert graph.average_confidence() == 0.5


# -------------------------------------------------------------------------
# Test required_dependency_count
# -------------------------------------------------------------------------
class TestRequiredDependencyCount:
    def test_empty_graph(self, empty_graph):
        assert empty_graph.required_dependency_count() == 0
    
    def test_simple_graph(self, simple_graph):
        # d1 is required=True, d2 is required=False
        assert simple_graph.required_dependency_count() == 1
    
    def test_complex_graph(self, complex_graph):
        # d1, d2, d3 are required=True; d4, d5 are required=False
        assert complex_graph.required_dependency_count() == 3
    
    def test_all_required(self, simple_graph):
        for dep in simple_graph.dependencies.values():
            dep.required = True
        assert simple_graph.required_dependency_count() == 2


# -------------------------------------------------------------------------
# Test average_dependencies_per_node
# -------------------------------------------------------------------------
class TestAverageDependenciesPerNode:
    def test_empty_graph(self, empty_graph):
        assert empty_graph.average_dependencies_per_node() == 0.0
    
    def test_simple_graph(self, simple_graph):
        # 2 dependencies, 3 nodes
        # node1->node2, node2->node3
        # node1: 1 dep (node1->node2), node2: 2 deps (node1->node2, node2->node3), node3: 1 dep (node2->node3)
        # Total connections = 1+2+1 = 4, divide by 2 = 2, then 2/3 = 0.666...
        avg = simple_graph.average_dependencies_per_node()
        assert abs(avg - 0.667) < 0.01
    
    def test_complex_graph(self, complex_graph):
        # 5 dependencies, 6 nodes
        avg = complex_graph.average_dependencies_per_node()
        # Each dependency connects 2 nodes, so total_connections_counted/2 gives actual dependency count
        # Then divide by node count
        assert avg > 0
        assert avg <= 5  # Can't exceed total dependencies
    
    def test_single_node_no_deps(self):
        graph = DependencyGraph()
        graph.add_node(DependencyNode(id="lonely", node_type=NodeType.CLAIM, name="Lonely"))
        assert graph.average_dependencies_per_node() == 0.0


# -------------------------------------------------------------------------
# Test most_dependent_node
# -------------------------------------------------------------------------
class TestMostDependentNode:
    def test_empty_graph(self, empty_graph):
        assert empty_graph.most_dependent_node() == 'none'
    
    def test_simple_graph(self, simple_graph):
        # node1: 1 dep (to node2)
        # node2: 2 deps (from node1, to node3)
        # node3: 1 dep (from node2)
        most = simple_graph.most_dependent_node()
        assert most == "node2"
    
    def test_complex_graph(self, complex_graph):
        # Count dependencies for each node
        most = complex_graph.most_dependent_node()
        assert most in complex_graph.nodes
        # Verify it has dependencies
        dep_count = len(complex_graph.get_dependencies_for_node(most))
        assert dep_count > 0
    
    def test_tie_returns_one(self):
        graph = DependencyGraph()
        graph.add_node("n1", NodeType.CLAIM)
        graph.add_node("n2", NodeType.CLAIM)
        graph.add_node("n3", NodeType.EVIDENCE)
        graph.add_dependency("d1", "n1", "n3", DependencyType.SUPPORTS)
        graph.add_dependency("d2", "n2", "n3", DependencyType.SUPPORTS)
        # n1 and n2 each have 1 dependency, n3 has 2
        most = graph.most_dependent_node()
        assert most == "n3"


# -------------------------------------------------------------------------
# Integration test
# -------------------------------------------------------------------------
class TestBatch209Integration:
    def test_all_methods_callable(self, complex_graph):
        """Verify all Batch 209 methods are callable."""
        assert complex_graph.total_nodes() == 6
        assert complex_graph.total_dependencies() == 5
        assert isinstance(complex_graph.node_type_distribution(), dict)
        assert isinstance(complex_graph.dependency_type_distribution(), dict)
        assert complex_graph.satisfied_node_count() >= 0
        assert complex_graph.unsatisfied_node_count() >= 0
        assert complex_graph.average_confidence() >= 0.0
        assert complex_graph.required_dependency_count() >= 0
        assert complex_graph.average_dependencies_per_node() >= 0.0
        assert isinstance(complex_graph.most_dependent_node(), str)
    
    def test_consistency_checks(self, complex_graph):
        """Verify internal consistency of metrics."""
        total = complex_graph.total_nodes()
        satisfied = complex_graph.satisfied_node_count()
        unsatisfied = complex_graph.unsatisfied_node_count()
        assert satisfied + unsatisfied == total
        
        total_deps = complex_graph.total_dependencies()
        required = complex_graph.required_dependency_count()
        assert required <= total_deps
        
        avg_conf = complex_graph.average_confidence()
        assert 0.0 <= avg_conf <= 1.0
