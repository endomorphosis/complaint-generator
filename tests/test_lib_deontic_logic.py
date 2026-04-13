from lib.deontic_logic import (
    DeonticGraph,
    DeonticGraphBuilder,
    DeonticModality,
    DeonticNode,
    DeonticNodeType,
    DeonticRule,
)


def test_lib_deontic_graph_tracks_nodes_rules_and_active_modalities() -> None:
    graph = DeonticGraph()
    graph.add_node(DeonticNode(id="actor:hacc", node_type=DeonticNodeType.ACTOR, label="HACC", active=True, confidence=1.0))
    graph.add_node(
        DeonticNode(id="action:grant_review", node_type=DeonticNodeType.ACTION, label="Grant informal review", active=False, confidence=0.8)
    )
    graph.add_rule(
        DeonticRule(
            id="rule:1",
            modality=DeonticModality.OBLIGATION,
            source_ids=["actor:hacc"],
            target_id="action:grant_review",
            predicate="must_grant_review",
            active=True,
            confidence=0.92,
            authority_ids=["24-cfr-982-555"],
        )
    )

    assert graph.summary()["active_rule_count"] == 1
    assert graph.modality_distribution() == {"obligation": 1}


def test_lib_deontic_graph_builder_detects_conflict() -> None:
    graph = DeonticGraphBuilder().build_from_matrix(
        [
            {
                "rule_id": "rule:obligation",
                "modality": "obligation",
                "predicate": "grant_review",
                "active": True,
                "target_id": "action:grant_review",
                "target_label": "Grant informal review",
                "sources": [{"id": "actor:hacc", "label": "HACC", "node_type": "actor", "active": True}],
            },
            {
                "rule_id": "rule:prohibition",
                "modality": "prohibition",
                "predicate": "grant_review",
                "active": True,
                "target_id": "action:grant_review",
                "target_label": "Grant informal review",
                "sources": [{"id": "fact:deadline_missed", "label": "Deadline missed", "node_type": "fact", "active": False}],
            },
        ]
    )

    conflicts = graph.detect_conflicts()
    assert len(conflicts) == 1
    assert conflicts[0].modalities == ["obligation", "prohibition"]