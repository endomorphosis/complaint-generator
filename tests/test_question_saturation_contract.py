"""QUEST-01 through QUEST-03: targeted questions, dispositions, and stop states."""

import pytest
from unittest.mock import Mock

from complaint_phases import (
    ComplaintDenoiser,
    ComplaintPhase,
    Dependency,
    DependencyGraph,
    DependencyNode,
    DependencyType,
    Entity,
    KnowledgeGraph,
    NodeType,
    PhaseManager,
    build_intake_case_file,
    refresh_intake_case_file,
)
from intake_status import build_intake_status_summary
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


def _bound_question(denoiser, target_id, text="What date do you recall?"):
    return denoiser._bind_unresolved_target(denoiser._question_candidate(
        source="dependency_graph_requirement",
        question_type="requirement",
        question_text=text,
        context={"requirement_id": target_id, "target_revision": "scope-a"},
        priority="high",
    ))


def test_empty_pool_question_cap_and_loss_plateau_are_not_saturation():
    denoiser = ComplaintDenoiser()
    denoiser.questions_pool.clear()
    denoiser.questions_asked.extend({"question": {"question": "q"}} for _ in range(51))
    assert denoiser.is_exhausted() is False
    capped = denoiser.evaluate_interview_stop(open_questions=[], loss_converged=True, pool_empty=True)
    assert capped["state"] == "limit_reached"
    assert capped["filing_ready"] is False
    assert capped["intake_complete"] is False
    assert capped["legal_sufficiency"] is False
    assert "question_count_limit" in capped["unresolved_issue_summary"]["rejected_shortcuts"]
    assert "loss_convergence" in capped["unresolved_issue_summary"]["rejected_shortcuts"]
    assert "complete" in capped["message"]
    assert "not ready to file" in capped["message"]

    fresh = ComplaintDenoiser()
    plateau = fresh.evaluate_interview_stop(open_questions=[], loss_converged=True, pool_empty=True)
    assert plateau["state"] == "needs_answer"
    assert plateau["intake_complete"] is False
    assert plateau["filing_ready"] is False
    assert fresh.is_exhausted() is False


def test_saturated_stop_requires_disposed_targets_and_lists_unresolved_issues():
    denoiser = ComplaintDenoiser()
    kg, dg, _ = _graphs()
    answered = _bound_question(denoiser, "req-protected")
    refused = _bound_question(denoiser, "req-notice", "What document shows the notice date?")
    denoiser.record_question_disposition(answered, "March 1, 2024", disposition="answered")
    denoiser.record_question_disposition(refused, "I decline", disposition="refused")
    stop = denoiser.evaluate_interview_stop(
        open_questions=[answered, refused],
        loss_converged=True,
        pool_empty=True,
        iteration_count=3,
        iteration_cap=20,
    )
    assert stop["state"] == "saturated"
    assert stop["targets_accounted_for"] is True
    assert stop["filing_ready"] is False
    assert stop["legal_sufficiency"] is False
    assert stop["intake_complete"] is False
    summary = stop["unresolved_issue_summary"]
    assert summary["core_facts_complete"] is False
    assert any(item.get("disposition") == "refused" for item in summary["items"])
    assert denoiser.is_exhausted() is True


def test_unknown_only_stop_is_deferred_unknown_not_completion():
    denoiser = ComplaintDenoiser()
    question = _bound_question(denoiser, "req-protected")
    denoiser.record_question_disposition(question, "I don't know", disposition="unknown")
    stop = denoiser.evaluate_interview_stop(open_questions=[question], pool_empty=True)
    assert stop["state"] == "deferred_unknown"
    assert stop["intake_complete"] is False
    assert stop["filing_ready"] is False
    assert stop["unresolved_issue_summary"]["core_facts_complete"] is False
    assert stop["unresolved_issue_summary"]["items"]


def test_provider_failure_and_cancellation_do_not_advertise_readiness():
    denoiser = ComplaintDenoiser()
    question = _bound_question(denoiser, "req-protected")
    failed = denoiser.evaluate_interview_stop(
        open_questions=[question],
        provider_status="provider_unavailable",
        iteration_count=20,
        iteration_cap=20,
    )
    assert failed["state"] == "provider_unavailable"
    assert failed["intake_complete"] is False
    assert failed["filing_ready"] is False
    assert failed["ready_for_evidence_phase"] is False
    cancelled = denoiser.evaluate_interview_stop(open_questions=[question], cancelled=True)
    assert cancelled["state"] == "cancelled"
    assert cancelled["intake_complete"] is False
    assert cancelled["filing_ready"] is False


def test_iteration_cap_action_is_limit_reached_and_blocks_intake_completion():
    pm = PhaseManager()
    pm.update_phase_data(ComplaintPhase.INTAKE, "knowledge_graph", {})
    pm.update_phase_data(ComplaintPhase.INTAKE, "dependency_graph", {})
    pm.update_phase_data(ComplaintPhase.INTAKE, "remaining_gaps", 5)
    pm.update_phase_data(ComplaintPhase.INTAKE, "denoising_converged", False)
    pm.update_phase_data(ComplaintPhase.INTAKE, "current_gaps", [])
    pm.iteration_count = 20
    action = pm.get_next_action()
    assert action["action"] == "limit_reached"
    assert action["filing_ready"] is False
    assert action["intake_complete"] is False
    assert pm.is_phase_complete(ComplaintPhase.INTAKE) is False
    assert "not ready to file" in action["message"]

    pm.update_phase_data(ComplaintPhase.INTAKE, "interview_stop", {
        "state": "provider_unavailable",
        "intake_complete": False,
        "filing_ready": False,
        "message": "backend down",
        "unresolved_issue_summary": {"items": [{"reason": "backend"}], "legal_sufficiency": False},
    })
    blocked = pm.get_next_action()
    assert blocked["action"] == "provider_unavailable"
    assert blocked["filing_ready"] is False
    assert pm.is_phase_complete(ComplaintPhase.INTAKE) is False
    assert pm.get_intake_readiness()["ready"] is False


def test_pause_and_resume_preserve_assertion_truth_without_supervisory_restart():
    mediator = Mediator(backends=[Mock(id="test-backend")])
    kg, dg, _ = _graphs()
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "knowledge_graph", kg)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "dependency_graph", dg)
    mediator.phase_manager.iteration_count = 4
    before_entities = [(entity.id, entity.name, entity.confidence) for entity in kg.entities.values()]
    before_nodes = [(node.id, node.satisfied, node.name) for node in dg.nodes.values()]
    paused = mediator.pause_intentional_user_wait("user_pause")
    assert paused["status"] == "awaiting_user"
    assert paused["paused"] is True
    assert paused["worker_stalled"] is False
    assert paused["supervisory_restart"] is False
    assert paused["iteration_count"] == 4
    assert [(entity.id, entity.name, entity.confidence) for entity in kg.entities.values()] == before_entities
    assert [(node.id, node.satisfied, node.name) for node in dg.nodes.values()] == before_nodes
    assert mediator.phase_manager.get_next_action()["action"] == "awaiting_user"
    assert mediator.phase_manager.get_next_action()["supervisory_restart"] is False
    resumed = mediator.resume_intentional_user_wait()
    assert resumed["resumed"] is True
    assert resumed["supervisory_restart"] is False
    assert resumed["worker_stalled"] is False
    assert resumed["assertion_rule_unchanged"] is True
    assert resumed["iteration_count"] == 4
    assert mediator.phase_manager.iteration_count == 4
    assert [(entity.id, entity.name, entity.confidence) for entity in kg.entities.values()] == before_entities
    assert [(node.id, node.satisfied, node.name) for node in dg.nodes.values()] == before_nodes


def test_intake_status_hides_filing_readiness_for_incomplete_stops():
    class _Mediator:
        def get_three_phase_status(self):
            return {
                "current_phase": "intake",
                "intake_readiness": {
                    "ready_to_advance": True,
                    "score": 1,
                    "remaining_gap_count": 0,
                    "contradiction_count": 0,
                    "blockers": [],
                    "criteria": {},
                },
                "interview_stop": {
                    "state": "limit_reached",
                    "intake_complete": False,
                    "filing_ready": False,
                    "legal_sufficiency": False,
                    "unresolved_issue_summary": {
                        "items": [{"reason": "iteration_cap"}],
                        "legal_sufficiency": False,
                        "core_facts_complete": False,
                    },
                },
                "intentional_user_wait": {
                    "status": "awaiting_user",
                    "awaiting_user": True,
                    "paused": True,
                    "worker_stalled": False,
                    "supervisory_restart": False,
                },
            }

    summary = build_intake_status_summary(_Mediator())
    assert summary["interview_stop"]["state"] == "limit_reached"
    assert summary["ready_to_advance"] is False
    assert summary["filing_ready"] is False
    assert summary["intake_complete"] is False
    assert summary["unresolved_issue_summary"]["items"]
    assert summary["awaiting_user"] is True
    assert summary["worker_stalled"] is False
    assert summary["supervisory_restart"] is False
