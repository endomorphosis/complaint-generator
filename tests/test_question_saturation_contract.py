"""QUEST-01 and QUEST-02: targeted questions and stable dispositions."""

import pytest
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
    build_intake_case_file,
    refresh_intake_case_file,
)
from complaint_phases.intake_case_file import (
    QUESTION_DISPOSITIONS,
    question_target_is_closed,
    record_question_disposition,
    reopen_question_disposition,
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


def _timeline_prompt(revision="scope-a"):
    return {
        "type": "timeline",
        "question": (
            "What is the timeline of key events, including dates, who made each decision, "
            "what notice or communication you received, and when you requested help or accommodation?"
        ),
        "priority": "high",
        "candidate_source": "standard_intake_backstop",
        "context": {"standard_intake_slot": "timeline", "target_revision": revision},
    }


def test_case_file_persists_target_revision_and_dispositions():
    kg, _, _ = _graphs()
    case_file = build_intake_case_file(kg, "Synthetic intake.")
    assert case_file["question_dispositions"] == []
    records = []
    for index, disposition in enumerate(QUESTION_DISPOSITIONS):
        records.append(record_question_disposition(
            case_file,
            target_id=f"factual:standard-intake:slot-{index}",
            target_revision="scope-a",
            disposition=disposition,
            target_kind="factual",
            question=f"Synthetic question {index}",
            answer="I do not know" if disposition != "answered" else "The meeting was on 2 March.",
            creates_fact=True,
            satisfies_requirement=True,
            contradictory_conclusion=True,
        ))
    refreshed = refresh_intake_case_file(case_file, kg)
    stored = refreshed["question_dispositions"]
    assert [item["disposition"] for item in stored] == list(QUESTION_DISPOSITIONS)
    assert {item["target_revision"] for item in stored} == {"scope-a"}
    for item in stored:
        if item["disposition"] != "answered":
            assert item["creates_fact"] is False
            assert item["satisfies_requirement"] is False
            assert item["contradictory_conclusion"] is False
        assert question_target_is_closed(refreshed, item["target_id"], "scope-a")
        assert question_target_is_closed(refreshed, item["target_id"], "scope-b")
    again = record_question_disposition(
        refreshed,
        target_id=records[0]["target_id"],
        target_revision="scope-a",
        disposition="unknown",
        target_kind="factual",
    )
    assert sum(item["target_id"] == again["target_id"] and not item["reopened"] for item in refreshed["question_dispositions"]) == 1


def test_equivalent_standard_intake_prompts_are_not_reinserted_until_reopened():
    denoiser = ComplaintDenoiser()
    denoiser.actor_critic_enabled = False
    kg, dg, intake = _graphs()
    intake = dict(intake)
    intake.pop("source_capability")
    intake["question_scope_revision"] = "scope-a"
    case_file = build_intake_case_file(kg, "")
    case_file["question_scope_revision"] = "scope-a"
    denoiser.record_question_disposition(
        _timeline_prompt(),
        "I don't know",
        intake_case_file=case_file,
    )
    stored = case_file["question_dispositions"][0]
    assert stored["target_id"] == "factual:standard-intake:timeline"
    assert stored["target_revision"] == "scope-a"
    assert stored["disposition"] == "unknown"
    assert stored["creates_fact"] is False
    equivalent = {
        "type": "timeline",
        "question": "Please share the timeline of key events and who made each decision.",
        "priority": "high",
        "candidate_source": "standard_intake_backstop",
        "context": {"target_revision": "scope-a"},
    }
    for _ in range(4):
        generated = denoiser.generate_questions(
            kg,
            dg,
            max_questions=8,
            intake_case_file=intake,
            additional_candidates=[equivalent, dict(equivalent, question="What is the timeline of key events again?")],
        )
        assert all(
            question["unresolved_target"]["target_id"] != "factual:standard-intake:timeline"
            for question in generated
        )
    with pytest.raises(ValueError):
        denoiser.reopen_disposed_question("factual:standard-intake:timeline", "", evidence_change="new letter")
    with pytest.raises(ValueError):
        denoiser.reopen_disposed_question("factual:standard-intake:timeline", "scope changed")
    denoiser.reopen_disposed_question(
        "factual:standard-intake:timeline",
        "A newly provided letter changes the timeline scope.",
        target_revision="scope-b",
        intake_case_file=case_file,
        evidence_change="letter dated 2 May",
        scope_change="scope-b",
    )
    assert case_file["question_dispositions"][-1]["reopened"] is True
    assert case_file["question_dispositions"][-1]["reopen_reason"]
    intake["question_scope_revision"] = "scope-b"
    reopened_prompt = dict(equivalent)
    reopened_prompt["context"] = {"standard_intake_slot": "timeline", "target_revision": "scope-b"}
    reopened = denoiser.generate_questions(
        kg,
        dg,
        max_questions=8,
        intake_case_file=intake,
        additional_candidates=[reopened_prompt],
    )
    assert any(
        question["unresolved_target"]["target_id"] == "factual:standard-intake:timeline"
        for question in reopened
    )


def test_unknown_and_refusal_do_not_create_facts_or_conclusions():
    denoiser = ComplaintDenoiser()
    kg, dg, _ = _graphs()
    question = denoiser._bind_unresolved_target(denoiser._question_candidate(
        source="dependency_graph_requirement",
        question_type="requirement",
        question_text="What dates or documents can you share about the protected activity?",
        context={"requirement_id": "req-protected", "target_revision": "scope-a"},
        priority="high",
    ))
    before_entities = set(kg.entities)
    before_relationships = set(kg.relationships)
    before_dependencies = set(dg.dependencies)
    satisfied = {node_id: node.satisfied for node_id, node in dg.nodes.items()}
    for answer in ("I don't know", "I decline to answer", "skip", "ask me later", "invalidated"):
        updates = denoiser.process_answer(question, answer, kg, dg)
        assert updates["entities_updated"] == 0
        assert updates["relationships_added"] == 0
        assert updates["requirements_satisfied"] == 0
        assert updates["creates_fact"] is False
        assert updates["satisfies_requirement"] is False
        assert updates["contradictory_conclusion"] is False
        assert updates["disposition"] in {"unknown", "refused", "skipped", "deferred", "invalidated"}
    assert set(kg.entities) == before_entities
    assert set(kg.relationships) == before_relationships
    assert set(dg.dependencies) == before_dependencies
    assert {node_id: node.satisfied for node_id, node in dg.nodes.items()} == satisfied


def test_mediator_records_disposition_and_reopens_with_reason():
    mediator = Mediator(backends=[Mock(id="test-backend")])
    denoiser = ComplaintDenoiser(mediator=mediator)
    mediator.denoiser = denoiser
    kg, _, _ = _graphs()
    case_file = build_intake_case_file(kg, "")
    question = _timeline_prompt("scope-a")
    question["unresolved_target"] = {
        "target_id": "factual:standard-intake:timeline",
        "target_revision": "scope-a",
        "target_kind": "factual",
    }
    mediator.state.inquiries = [{
        "question": question["question"],
        "answer": None,
        "unresolved_target": dict(question["unresolved_target"]),
    }]
    record = mediator.record_intake_question_disposition(
        question,
        "I refuse",
        intake_case_file=case_file,
    )
    assert record["disposition"] == "refused"
    assert record["creates_fact"] is False
    assert case_file["question_dispositions"][0]["target_revision"] == "scope-a"
    assert mediator.state.inquiries[0]["disposition"] == "refused"
    assert mediator.inquiries.get_next() is None
    selected = mediator.select_intake_question_candidates([question], max_questions=2)
    assert selected == []
    mediator.reopen_intake_question(
        "factual:standard-intake:timeline",
        "The complainant supplied a new notice.",
        target_revision="scope-b",
        intake_case_file=case_file,
        evidence_change="notice dated 2 May",
    )
    assert question_target_is_closed(case_file, "factual:standard-intake:timeline", "scope-b") is False
    refreshed = refresh_intake_case_file(case_file, kg)
    assert refreshed["question_dispositions"][-1]["status"] == "reopened"
