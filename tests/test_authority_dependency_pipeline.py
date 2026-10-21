"""Verified legal requirements drive intake dependency construction and scoped refresh."""

from complaint_phases.dependency_graph import DependencyGraphBuilder, NodeType
from complaint_phases.phase_manager import ComplaintPhase


class _MockBackend:
    id = "mock_backend"

    def __call__(self, prompt):
        return "Mock response"


def _verified_requirement(rule_id, name, *, fact_ids=None, jurisdiction="federal"):
    return {
        "name": name,
        "description": f"Source-bound requirement {name}",
        "rule_id": rule_id,
        "authority_id": rule_id,
        "jurisdiction": jurisdiction,
        "promoted": True,
        "source_bound": True,
        "verification_status": "verified",
        "applicable": True,
        "support_eligible": True,
        "fact_ids": list(fact_ids or []),
        "provenance": {"source_id": rule_id, "authority_id": rule_id},
    }


def _mediator():
    from mediator.mediator import Mediator

    return Mediator([_MockBackend()])


def _sourced_nodes(graph):
    return [
        node for node in graph.nodes.values()
        if isinstance(node.attributes, dict)
        and node.attributes.get("dependency_class") == "legally_sourced_requirement"
    ]


def _gap_nodes(graph):
    return [
        node for node in graph.nodes.values()
        if isinstance(node.attributes, dict)
        and node.attributes.get("dependency_class") == "legal_source_gap"
    ]


def _factual_nodes(graph):
    return [
        node for node in graph.nodes.values()
        if isinstance(node.attributes, dict)
        and node.attributes.get("dependency_class") == "factual_clarification"
    ]


def test_start_binds_verified_requirements_before_element_questions():
    mediator = _mediator()
    mediator.state.verified_legal_requirements = {
        "employment_discrimination": [
            _verified_requirement("rule-protected", "Protected class"),
        ],
    }

    result = mediator.start_three_phase_process(
        "I faced discrimination at work and I have emails."
    )

    sequence = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_construction_sequence")
    assert sequence.index("verified_legal_requirements") < sequence.index("dependency_graph")
    assert sequence.index("dependency_graph") < sequence.index("element_questions")
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
    sourced = _sourced_nodes(graph)
    factual = _factual_nodes(graph)
    assert sourced
    assert factual
    assert {node.attributes.get("dependency_class") for node in sourced} == {"legally_sourced_requirement"}
    assert all(node.attributes.get("law_derived") is False for node in sourced)
    assert all(node.attributes.get("dependency_class") == "factual_clarification" for node in factual)
    assert all(node.attributes.get("about_complainant") is True for node in factual)
    assert not _gap_nodes(graph)
    assert graph.metadata["heuristic_law_derived_invoked"] is False
    assert result["initial_questions"] is not None


def test_missing_retrieved_requirements_record_a_source_gap_without_heuristic_law():
    mediator = _mediator()
    mediator.state.verified_legal_requirements = {
        "employment_discrimination": [{
            "name": "Heuristic protected class",
            "origin": "heuristic",
            "law_derived": True,
            "verification_status": "heuristic",
            "description": "Invented element",
        }],
    }

    mediator.start_three_phase_process("My employer discriminated against me.")

    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
    assert graph.metadata["heuristic_law_derived_invoked"] is False
    assert not any(node.name == "Heuristic protected class" for node in graph.nodes.values())
    assert not _sourced_nodes(graph)
    gaps = _gap_nodes(graph)
    assert gaps
    assert all(gap.attributes.get("gap_kind") == "legal_context_source_gap" for gap in gaps)
    assert all(gap.attributes.get("reason") == "no_retrieved_requirements" for gap in gaps)
    assert all(gap.attributes.get("heuristic_law_derived") is False for gap in gaps)
    stored = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "legal_context_source_gaps")
    assert stored
    assert "legal_context_source_gap" in mediator.phase_manager.get_phase_data(
        ComplaintPhase.INTAKE, "intake_gap_types"
    )


def test_fact_jurisdiction_date_and_rule_changes_refresh_only_affected_dependencies():
    builder = DependencyGraphBuilder()
    requirements = {
        "employment_discrimination": [
            _verified_requirement("rule-a", "Element A", fact_ids=["fact-a"]),
            _verified_requirement("rule-b", "Element B", fact_ids=["fact-b"]),
        ],
    }
    graph = builder.build_from_claims(
        [{"name": "Discrimination", "type": "employment_discrimination", "description": "I was fired"}],
        requirements,
        require_verified_legal_sources=True,
    )
    sourced = {node.attributes["rule_id"]: node for node in _sourced_nodes(graph)}
    factual = next(node for node in _factual_nodes(graph) if "timeline" in node.attributes["clarification_keys"])
    unrelated = next(
        node for node in _factual_nodes(graph)
        if node.id != factual.id and "timeline" not in set(node.attributes.get("clarification_keys") or [])
    )
    for node in (sourced["rule-a"], sourced["rule-b"], factual, unrelated):
        node.satisfied = True
        node.attributes["satisfaction_state"] = "satisfied"
    preserved_rule_dependency = next(
        dependency.id for dependency in graph.dependencies.values()
        if dependency.source_id == sourced["rule-b"].id
    )
    preserved_factual_dependency = next(
        dependency.id for dependency in graph.dependencies.values()
        if dependency.source_id == unrelated.id
    )

    fact_report = builder.refresh_affected_dependencies(graph, {
        "fact_change": True,
        "fact_ids": ["fact-a"],
        "clarification_keys": ["timeline"],
    })
    assert sourced["rule-a"].id in fact_report["affected_node_ids"]
    assert factual.id in fact_report["affected_node_ids"]
    assert sourced["rule-b"].id in fact_report["preserved_node_ids"]
    assert unrelated.id in fact_report["preserved_node_ids"]
    assert sourced["rule-a"].satisfied is False
    assert sourced["rule-a"].attributes["satisfaction_state"] == "invalidated"
    assert sourced["rule-a"].attributes["stale_satisfaction"] is True
    assert factual.satisfied is False
    assert sourced["rule-b"].satisfied is True
    assert unrelated.satisfied is True
    assert preserved_rule_dependency in fact_report["preserved_dependency_ids"]
    assert preserved_factual_dependency in fact_report["preserved_dependency_ids"]
    assert any(item["source_id"] == sourced["rule-a"].id for item in fact_report["recomputed_dependencies"])

    sourced["rule-a"].satisfied = True
    sourced["rule-a"].attributes["satisfaction_state"] = "satisfied"
    factual.satisfied = True
    jurisdiction_report = builder.refresh_affected_dependencies(graph, {"jurisdiction_changed": True})
    assert sourced["rule-a"].satisfied is False
    assert sourced["rule-b"].satisfied is False
    assert factual.satisfied is True
    assert unrelated.satisfied is True
    assert factual.id in jurisdiction_report["preserved_node_ids"]

    sourced["rule-b"].satisfied = True
    sourced["rule-b"].attributes["satisfaction_state"] = "satisfied"
    date_report = builder.refresh_affected_dependencies(graph, {
        "date_changed": True,
        "date_roles": ["applicable_law_date"],
    })
    assert sourced["rule-b"].attributes["stale_satisfaction"] is True
    assert unrelated.id in date_report["preserved_node_ids"]
    assert unrelated.satisfied is True

    sourced["rule-a"].satisfied = True
    sourced["rule-b"].satisfied = True
    sourced["rule-a"].attributes["satisfaction_state"] = "satisfied"
    sourced["rule-b"].attributes["satisfaction_state"] = "satisfied"
    revised = _verified_requirement("rule-a", "Element A revised", fact_ids=["fact-a"])
    revised["description"] = "Revised source text"
    rule_report = builder.refresh_affected_dependencies(graph, {
        "rule_ids": ["rule-a"],
        "updated_requirements": {"employment_discrimination": [revised]},
    })
    refreshed = {node.attributes.get("rule_id"): node for node in _sourced_nodes(graph)}
    assert "rule-a" in refreshed and "rule-b" in refreshed
    assert refreshed["rule-a"].description == "Revised source text"
    assert refreshed["rule-a"].satisfied is False
    assert refreshed["rule-a"].attributes["satisfaction_state"] == "invalidated"
    assert refreshed["rule-b"].satisfied is True
    assert refreshed["rule-b"].id == sourced["rule-b"].id
    assert "rule-a" in rule_report["replaced_rule_ids"]
    assert "rule-b" not in rule_report["replaced_rule_ids"]


def test_phase_manager_records_scoped_refresh_from_context_and_answers():
    mediator = _mediator()
    mediator.state.verified_legal_requirements = {
        "employment_discrimination": [
            _verified_requirement("rule-protected", "Protected class", fact_ids=["fact-protected"]),
        ],
    }
    mediator.start_three_phase_process("My employer discriminated against me.")
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
    legal = _sourced_nodes(graph)[0]
    factual = _factual_nodes(graph)[0]
    factual_keys = set(factual.attributes.get("clarification_keys") or [])
    question_type = "timeline" if "timeline" in factual_keys else "responsible_party"
    legal.satisfied = True
    legal.attributes["satisfaction_state"] = "satisfied"
    factual.satisfied = True
    factual.attributes["satisfaction_state"] = "satisfied"

    case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
    mediator.apply_explicit_legal_context(case_file, jurisdiction="WA")
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
    legal = _sourced_nodes(graph)[0]
    factual = next(node for node in graph.nodes.values() if node.id == factual.id)
    assert legal.satisfied is False
    assert legal.attributes["satisfaction_state"] == "invalidated"
    assert factual.satisfied is True
    recorded = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "verified_dependency_refresh")
    assert legal.id in recorded["affected_node_ids"]
    assert factual.id in recorded["preserved_node_ids"]

    legal.satisfied = True
    legal.attributes["satisfaction_state"] = "satisfied"
    mediator.process_denoising_answer(
        {"type": question_type, "question": "What additional fact is needed?"},
        "My supervisor did it on January 20, 2026.",
    )
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
    legal = next(node for node in graph.nodes.values() if node.id == legal.id)
    factual = next(node for node in graph.nodes.values() if node.id == factual.id)
    assert factual.satisfied is False
    assert factual.attributes["stale_satisfaction"] is True
    assert legal.satisfied is True
    assert legal.attributes.get("satisfaction_state") != "invalidated"
