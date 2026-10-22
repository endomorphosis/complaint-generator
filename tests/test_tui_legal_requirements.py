"""Jurisdiction-specific legal requirements enter intake only through sourced records."""

from complaint_phases.dependency_graph import DependencyGraphBuilder
from integrations.ipfs_datasets.legal import (
    SourcedLegalRequirement,
    adapt_sourced_legal_requirements,
    intake_legal_selection,
    unresolved_legal_requirement,
)
from mediator.legal_hooks import SummaryJudgmentHook


class _MockBackend:
    id = "mock_backend"

    def __call__(self, prompt):
        return "1. A complainant-supplied element that is not a statute."


def _mediator():
    from mediator.mediator import Mediator

    return Mediator([_MockBackend()])


def _sourced_nodes(graph):
    return [
        node for node in graph.nodes.values()
        if isinstance(node.attributes, dict)
        and node.attributes.get("dependency_class") == "legally_sourced_requirement"
    ]


def _unresolved_nodes(graph):
    return [
        node for node in graph.nodes.values()
        if isinstance(node.attributes, dict)
        and node.attributes.get("dependency_class") == "unresolved_legal_requirement"
    ]


def test_unknown_jurisdiction_is_preserved_and_blocks_rule_selection():
    context = {
        "jurisdiction": "",
        "applicable_law_date": {"raw_text": "", "role": "applicable_law_date"},
        "event_date": {"raw_text": "", "role": "event_date"},
    }
    selection = intake_legal_selection(context, [])
    assert selection["ready_to_select"] is False
    assert selection["jurisdiction"] == "unknown"
    reasons = {item["reason"] for item in selection["questions"]}
    assert {"unresolved_jurisdiction", "missing_applicable_law_date", "missing_claim_candidates"} <= reasons

    mediator = _mediator()
    result = mediator.start_three_phase_process("Something unfair happened and I want the law applied.")
    graph = mediator.phase_manager.get_phase_data(
        __import__("complaint_phases.phase_manager", fromlist=["ComplaintPhase"]).ComplaintPhase.INTAKE,
        "dependency_graph",
    )
    assert graph.metadata["legal_context_jurisdiction"] == "unknown"
    assert graph.metadata["legal_selection_status"] == "unresolved_context"
    assert not _sourced_nodes(graph)
    unresolved = _unresolved_nodes(graph)
    assert unresolved
    assert all(node.attributes.get("jurisdiction") == "unknown" for node in unresolved)
    assert all(node.attributes.get("law_derived") is False for node in unresolved)
    assert all(node.attributes.get("source_available") is False for node in unresolved)
    assert graph.metadata["heuristic_law_derived_invoked"] is False
    assert graph.metadata["unresolved_legal_requirements"]
    questions = result["initial_questions"]
    assert questions
    assert questions[0]["type"] == "legal_context"
    assert questions[0]["jurisdiction"] == "unknown"
    assert any(item.get("reason") == "unresolved_jurisdiction" for item in questions)


def test_summary_judgment_strings_are_not_builder_rules():
    hook = SummaryJudgmentHook(_mediator())
    generated = hook.generate_requirements(
        {"claim_types": ["employment_discrimination"], "jurisdiction": "federal", "legal_areas": []},
        [{"citation": "Synthetic", "title": "Fixture", "relevance": "none"}],
    )
    assert all(isinstance(item, str) for item in generated["employment_discrimination"])
    adapted = hook.adapt_requirements_for_dependency_graph(generated)
    assert adapted["employment_discrimination"]
    assert all(entry["intake_requirement_status"] == "unresolved" for entry in adapted["employment_discrimination"])
    assert all(entry["proof_status"] == "not_authoritative" for entry in adapted["employment_discrimination"])
    assert all(entry["name"] == "Unresolved legal requirement" for entry in adapted["employment_discrimination"])
    asserted = " ".join(entry["asserted_text"] for entry in adapted["employment_discrimination"])
    graph = DependencyGraphBuilder().build_from_claims(
        [{"name": "Discrimination", "type": "employment_discrimination", "description": "I was fired"}],
        legal_requirements=generated,
        require_verified_legal_sources=True,
    )
    assert not _sourced_nodes(graph)
    unresolved = _unresolved_nodes(graph)
    assert unresolved
    assert all(node.name == "Unresolved legal requirement" for node in unresolved)
    assert all(asserted.find(node.name) < 0 for node in unresolved)
    assert graph.metadata["unresolved_legal_requirements"]


def test_sourced_requirement_keeps_authority_identity():
    requirement = SourcedLegalRequirement(
        claim_type="employment_discrimination",
        name="Notice",
        description="An employer shall provide notice to an employee.",
        authority_locator="Synthetic fixture rule notice",
        source_locator="span:1-12",
        jurisdiction="OR",
        effective_date="2024-01-01",
        authority_version="2024-edition",
        derivation_status="source_derived",
        proof_status="source_bound",
    )
    entry = requirement.as_builder_entry()
    for key in (
        "authority_locator", "source_locator", "jurisdiction", "effective_date",
        "authority_version", "derivation_status", "proof_status",
    ):
        assert entry[key]
    assert entry["jurisdiction"] == "OR"
    assert entry["derivation_status"] == "source_derived"
    assert entry["proof_status"] == "source_bound"
    assert entry["intake_requirement_status"] == "source_bound"


def test_user_assertion_cannot_create_authoritative_law():
    asserted = {
        "claim_type": "retaliation",
        "name": "The statute requires reinstatement",
        "description": "The statute requires reinstatement",
        "citation": "ORS 000.000",
        "jurisdiction": "OR",
        "effective_date": "2024-01-01",
        "authority_version": "user-typed",
        "origin": "user",
        "user_asserted": True,
    }
    adapted = adapt_sourced_legal_requirements({"retaliation": [asserted]})
    entry = adapted["retaliation"][0]
    assert entry["derivation_status"] == "user_assertion"
    assert entry["proof_status"] == "not_authoritative"
    assert entry["authority_locator"] == ""
    assert entry["unresolved_reason"] == "user_assertion_cannot_create_law"
    graph = DependencyGraphBuilder().build_from_claims(
        [{"name": "Retaliation", "type": "retaliation", "description": "I was fired"}],
        legal_requirements=adapted,
        require_verified_legal_sources=True,
    )
    assert not _sourced_nodes(graph)
    unresolved = _unresolved_nodes(graph)
    assert unresolved
    assert all(node.attributes["user_assertion_is_not_law"] is True for node in unresolved)
    assert all(node.name != asserted["name"] for node in unresolved)


def test_ambiguous_authority_is_unresolved_and_initial_graph_receives_requirements():
    ambiguous = {
        "name": "Maybe a duty",
        "description": "Some duty might exist",
        "jurisdiction": "OR",
    }
    adapted = adapt_sourced_legal_requirements({"employment_discrimination": [ambiguous]})
    assert adapted["employment_discrimination"][0]["unresolved_reason"] == "missing_authority_locator"
    graph = DependencyGraphBuilder().build_from_claims(
        [{"name": "Discrimination", "type": "employment_discrimination", "description": "I was fired"}],
        legal_requirements=adapted,
        require_verified_legal_sources=True,
    )
    assert not _sourced_nodes(graph)
    assert _unresolved_nodes(graph)
    assert graph.metadata["unresolved_legal_requirements"][0]["reason"] == "missing_authority_locator"

    mediator = _mediator()
    seen = {}
    original = mediator.dg_builder.build_from_claims

    def _capture(claims, legal_requirements=None, **kwargs):
        seen["legal_requirements"] = legal_requirements
        seen["explicit"] = "legal_requirements" in kwargs or legal_requirements is not None
        return original(claims, legal_requirements=legal_requirements, **kwargs)

    mediator.dg_builder.build_from_claims = _capture
    mediator.start_three_phase_process("I was treated unfairly.")
    assert isinstance(seen["legal_requirements"], dict)
    assert seen["explicit"] is True
    assert seen["legal_requirements"]
    assert all(
        entry.get("intake_requirement_status") == "unresolved"
        for entries in seen["legal_requirements"].values()
        for entry in entries
    )


def test_unresolved_helper_does_not_invent_a_rule():
    requirement = unresolved_legal_requirement("unknown", "unresolved_jurisdiction")
    assert requirement.jurisdiction == "unknown"
    assert requirement.authority_locator == ""
    assert requirement.proof_status == "unresolved"
    assert requirement.name == "Unresolved legal requirement"
