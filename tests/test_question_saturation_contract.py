"""QUEST-01: neutral questions stay bound to unresolved targets."""

from unittest.mock import Mock

from complaint_phases import (
    ComplaintDenoiser,
    Dependency,
    DependencyGraph,
    DependencyNode,
    DependencyType,
    Entity,
    KnowledgeGraph,
    NodeType,
)
from mediator import Mediator


def _graphs():
    kg = KnowledgeGraph()
    kg.add_entity(Entity("c1", "claim", "Retaliation"))
    dg = DependencyGraph()
    left = DependencyNode("fact-before", NodeType.FACT, "Termination happened before complaint")
    right = DependencyNode("fact-after", NodeType.FACT, "Complaint happened before termination")
    claim = DependencyNode("claim-retaliation", NodeType.CLAIM, "Retaliation Claim")
    requirement = DependencyNode("req-protected", NodeType.REQUIREMENT, "Protected activity")
    dg.add_node(left)
    dg.add_node(right)
    dg.add_node(claim)
    dg.add_node(requirement)
    dg.add_dependency(Dependency("edge-contradicts", "fact-before", "fact-after", DependencyType.CONTRADICTS, required=False))
    dg.add_dependency(Dependency("edge-requires", "req-protected", "claim-retaliation", DependencyType.REQUIRES))
    intake = {
        "candidate_claims": [
            {
                "claim_id": "claim-retaliation",
                "claim_type": "retaliation",
                "label": "Retaliation Claim",
                "required_elements": [
                    {
                        "element_id": "protected_activity",
                        "label": "Protected activity",
                        "blocking": True,
                        "status": "missing",
                    }
                ],
            }
        ],
        "source_capability": {"status": "unavailable", "component": "prover"},
    }
    return kg, dg, intake


def _assert_bound(question):
    target = question.get("unresolved_target") or {}
    assert target.get("target_id")
    assert target.get("target_revision")
    assert target.get("target_kind") in {"factual", "requirement", "contradiction", "proof"}
    assert isinstance(target.get("provenance"), dict)
    assert target.get("why_answer_helps")
    assert target.get("expected_information")
    assert target.get("user_answerability") == "user_observable"
    lowered = str(question.get("question") or "").lower()
    assert "which version is correct" not in lowered
    assert "illegal" not in lowered
    assert "prover" not in lowered
    assert "backend" not in lowered


def test_generate_questions_binds_neutral_targets_and_routes_source_gaps():
    denoiser = ComplaintDenoiser()
    kg, dg, intake = _graphs()
    questions = denoiser.generate_questions(kg, dg, max_questions=8, intake_case_file=intake)

    assert questions
    assert all(_assert_bound(question) or True for question in questions)
    for question in questions:
        _assert_bound(question)
    assert any(question["unresolved_target"]["target_kind"] == "contradiction" for question in questions)
    assert any(question["unresolved_target"]["target_kind"] == "requirement" for question in questions)
    assert denoiser.source_operator_diagnostics
    assert all(item.get("user_question") is None for item in denoiser.source_operator_diagnostics)
    assert all("operator" in str(item.get("message") or "").lower() for item in denoiser.source_operator_diagnostics)
    # Empty diagnostics are not a saturation claim; targeted questions can remain.
    assert questions


def test_generic_prompts_and_closed_targets_do_not_bypass_or_repeat():
    denoiser = ComplaintDenoiser()
    denoiser.actor_critic_enabled = False
    kg, dg, intake = _graphs()
    intake = dict(intake)
    intake.pop("source_capability")
    generic = {
        "type": "clarification",
        "question": "Can you provide more details about anything else?",
        "priority": "high",
        "candidate_source": "standard_intake_backstop",
        "context": {},
    }
    operator = {
        "type": "clarification",
        "question": "The prover is unavailable. Can you repair the backend and rerun the solver?",
        "priority": "high",
        "candidate_source": "source_outage",
        "context": {"source_status": "unavailable", "requirement_id": "solver-outage"},
    }
    questions = denoiser.generate_questions(
        kg,
        dg,
        max_questions=6,
        intake_case_file=intake,
        additional_candidates=[generic, operator],
    )
    texts = " ".join(question["question"].lower() for question in questions)
    assert "anything else" not in texts
    assert "repair the backend" not in texts
    assert "prover" not in texts
    assert any(item.get("audience") == "operator" for item in denoiser.source_operator_diagnostics)

    closed_id = questions[0]["unresolved_target"]["target_id"]
    denoiser.target_dispositions[closed_id] = "unknown"
    denoiser.questions_asked.append({
        "question": questions[0],
        "answer": "",
        "disposition": "declined",
    })
    again = denoiser.generate_questions(kg, dg, max_questions=6, intake_case_file=intake)
    assert all(question["unresolved_target"]["target_id"] != closed_id for question in again)


def test_ranking_uses_dependency_impact_uncertainty_and_answerability():
    denoiser = ComplaintDenoiser()
    denoiser.actor_critic_enabled = False
    low = denoiser._question_candidate(
        source="dependency_graph_requirement",
        question_type="requirement",
        question_text="What dates or documents can you share about the later notice?",
        context={"requirement_id": "req-low", "dependency_impact": 0, "uncertainty": 0, "target_revision": "r1"},
        priority="low",
    )
    high = denoiser._question_candidate(
        source="dependency_graph_requirement",
        question_type="requirement",
        question_text="What dates or documents can you share about the termination decision?",
        context={"requirement_id": "req-high", "dependency_impact": 5, "uncertainty": 4, "target_revision": "r1"},
        priority="low",
    )
    selected = denoiser.select_question_candidates([low, high], max_questions=2)
    assert [item["unresolved_target"]["target_id"] for item in selected] == [
        "requirement:req-high",
        "requirement:req-low",
    ]
    again = denoiser.select_question_candidates([high, low], max_questions=2)
    assert [item["target_id"] for item in again] == [item["target_id"] for item in selected]


def test_inquiry_registration_preserves_target_disposition_and_payload():
    mediator = Mediator(backends=[Mock(id="test-backend")])
    denoiser = ComplaintDenoiser(mediator=mediator)
    mediator.denoiser = denoiser
    kg, dg, intake = _graphs()
    intake = dict(intake)
    intake.pop("source_capability")
    questions = denoiser.generate_questions(kg, dg, max_questions=4, intake_case_file=intake)
    registered = []
    for question in questions:
        target = question["unresolved_target"]
        registered.append({
            "question": question["question"],
            "priority": question.get("priority") or "high",
            "unresolved_target": target,
            "why_answer_helps": target["why_answer_helps"],
            "expected_information": target["expected_information"],
            "user_answerability": target["user_answerability"],
            "provenance": target["provenance"],
            "answer": None,
        })
    merged = mediator.inquiries.merge_legal_questions(registered)
    assert merged == len(registered)
    pending = mediator.inquiries.get_next()
    assert pending["unresolved_target"]["target_id"]
    explanation = mediator.inquiries.explain_inquiry(pending)
    mediator.state.current_inquiry = pending
    mediator.state.current_inquiry_explanation = explanation
    mediator.process = Mock(return_value=pending["question"])
    payload = mediator.io_payload("yes")
    assert payload["inquiry"]["unresolved_target"]["target_id"] == pending["unresolved_target"]["target_id"]
    assert payload["explanation"]["unresolved_target"]["target_revision"] == pending["unresolved_target"]["target_revision"]
    assert payload["explanation"]["expected_information"]
    assert payload["explanation"]["why_answer_helps"]

    closed = dict(mediator.state.inquiries[0])
    closed["answer"] = None
    closed["disposition"] = "unknown"
    mediator.state.inquiries[0] = closed
    mediator.inquiries.merge_legal_questions([{
        "question": closed["question"],
        "answer": None,
        "disposition": None,
        "unresolved_target": {"target_id": "replacement-target", "target_revision": "other", "target_kind": "factual"},
    }])
    assert mediator.state.inquiries[0]["disposition"] == "unknown"
    assert mediator.state.inquiries[0]["unresolved_target"]["target_id"] == closed["unresolved_target"]["target_id"]
    nxt = mediator.inquiries.get_next()
    if nxt is not None:
        assert nxt["unresolved_target"]["target_id"] != closed["unresolved_target"]["target_id"]


def test_selector_keeps_impact_order_for_equal_selector_scores():
    mediator = Mediator(backends=[Mock(id="test-backend")])
    denoiser = ComplaintDenoiser()
    mediator.denoiser = denoiser
    mediator.phase_manager.get_phase_data = Mock(return_value=None)
    mediator.build_inquiry_gap_context = Mock(return_value={})
    mediator._build_intake_claim_pressure_map = Mock(return_value={})
    mediator._build_intake_matching_pressure_map = Mock(return_value={})
    low = denoiser._question_candidate(
        source="dependency_graph_requirement",
        question_type="requirement",
        question_text="What documents show the first notice date?",
        context={"requirement_id": "a-low", "dependency_impact": 1, "uncertainty": 1, "target_revision": "rev-a"},
        priority="medium",
    )
    high = denoiser._question_candidate(
        source="dependency_graph_requirement",
        question_type="requirement",
        question_text="What documents show the decision date?",
        context={"requirement_id": "b-high", "dependency_impact": 4, "uncertainty": 3, "target_revision": "rev-b"},
        priority="medium",
    )
    for candidate in (low, high):
        candidate["selector_score"] = 1.0
        candidate["actor_critic_score"] = 1.0
    selected = mediator.select_intake_question_candidates([low, high], max_questions=2)
    assert selected[0]["unresolved_target"]["dependency_impact"] >= selected[-1]["unresolved_target"]["dependency_impact"]
    assert selected[0]["unresolved_target"]["target_id"] == "requirement:b-high"
