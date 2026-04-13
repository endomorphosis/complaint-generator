from complaint_phases import (
    DeonticGraph,
    DeonticGraphBuilder,
    DeonticModality,
    DeonticNode,
    DeonticNodeType,
    DeonticRule,
)


def test_deontic_graph_tracks_nodes_rules_and_active_modalities():
    graph = DeonticGraph()
    graph.add_node(
        DeonticNode(
            id="actor:hacc",
            node_type=DeonticNodeType.ACTOR,
            label="HACC",
            active=True,
            confidence=1.0,
        )
    )
    graph.add_node(
        DeonticNode(
            id="action:grant_review",
            node_type=DeonticNodeType.ACTION,
            label="Grant informal review",
            active=False,
            confidence=0.8,
        )
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

    summary = graph.summary()

    assert summary["total_nodes"] == 2
    assert summary["total_rules"] == 1
    assert summary["active_rule_count"] == 1
    assert summary["modalities"] == {"obligation": 1}
    assert summary["active_modalities"] == {"obligation": 1}
    assert graph.governed_targets() == ["action:grant_review"]


def test_deontic_graph_builder_from_findings_activates_rules_when_conditions_hold():
    builder = DeonticGraphBuilder()
    graph = builder.build_from_findings(
        actor_label="Housing Authority",
        findings={
            "requested_hearing": True,
            "notice_sent": True,
            "deadline_met": False,
        },
        rule_templates=[
            {
                "rule_id": "rule:grant-review",
                "modality": "obligation",
                "predicate": "grant_informal_review",
                "target_id": "action:grant_review",
                "target_label": "Grant informal review",
                "conditions": ["requested_hearing", "notice_sent"],
                "authority_ids": ["24-cfr-982-555"],
            },
            {
                "rule_id": "rule:timely-response",
                "modality": "prohibition",
                "predicate": "deny_for_untimeliness",
                "target_id": "action:deny_untimely",
                "target_label": "Deny request as untimely",
                "conditions": ["deadline_met"],
            },
        ],
    )

    assert graph.rules["rule:grant-review"].active is True
    assert graph.rules["rule:timely-response"].active is False
    assert graph.modality_distribution() == {"obligation": 1, "prohibition": 1}
    assert graph.active_modality_distribution() == {"obligation": 1}


def test_deontic_graph_builder_from_matrix_round_trips():
    builder = DeonticGraphBuilder()
    graph = builder.build_from_matrix(
        [
            {
                "rule_id": "rule:1",
                "modality": "entitlement",
                "predicate": "receive_notice",
                "active": True,
                "target_id": "outcome:notice",
                "target_label": "Receive written notice",
                "target_type": "outcome",
                "sources": [
                    {"id": "actor:tenant", "label": "Tenant", "node_type": "actor", "active": True},
                    {"id": "fact:denial", "label": "Denial issued", "node_type": "fact", "active": True},
                ],
            }
        ]
    )

    payload = graph.to_dict()
    restored = DeonticGraph.from_dict(payload)

    assert restored.summary()["total_rules"] == 1
    assert restored.rules["rule:1"].modality == DeonticModality.ENTITLEMENT
    assert restored.get_node("actor:tenant").node_type == DeonticNodeType.ACTOR


def test_deontic_graph_detects_conflicting_modalities_and_reports_source_gaps():
    builder = DeonticGraphBuilder()
    graph = builder.build_from_matrix(
        [
            {
                "rule_id": "rule:obligation",
                "modality": "obligation",
                "predicate": "grant_review",
                "active": True,
                "target_id": "action:grant_review",
                "target_label": "Grant informal review",
                "sources": [
                    {"id": "actor:hacc", "label": "HACC", "node_type": "actor", "active": True},
                    {"id": "fact:requested", "label": "Review requested", "node_type": "fact", "active": True},
                ],
                "authority_ids": ["24-cfr-982-555"],
            },
            {
                "rule_id": "rule:prohibition",
                "modality": "prohibition",
                "predicate": "grant_review",
                "active": True,
                "target_id": "action:grant_review",
                "target_label": "Grant informal review",
                "sources": [
                    {"id": "actor:hacc", "label": "HACC", "node_type": "actor", "active": True},
                    {"id": "fact:deadline_missed", "label": "Deadline missed", "node_type": "fact", "active": False},
                ],
            },
        ]
    )

    conflicts = graph.detect_conflicts()
    gap_summary = graph.source_gap_summary()
    rows = graph.export_reasoning_rows()

    assert conflicts[0].modalities == ["obligation", "prohibition"]
    assert conflicts[0].target_id == "action:grant_review"
    assert gap_summary["rule_count"] == 2
    assert gap_summary["fully_supported_rule_count"] == 1
    assert gap_summary["rules_with_gaps"][0]["rule_id"] == "rule:prohibition"
    assert rows[0]["target_label"] == "Grant informal review"
