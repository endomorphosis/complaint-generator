"""Append-only factual corrections, retractions, conflicts, and answer-event replay."""

import copy
import json

import pytest

from complaint_phases.dependency_graph import DependencyGraphBuilder, DependencyNode, NodeType
from complaint_phases.knowledge_graph import (
    AnswerEventConflict,
    Entity,
    KnowledgeGraph,
    Relationship,
    assertion_from_provenance,
)
from complaint_phases.phase_manager import ComplaintPhase
from integrations.ipfs_datasets.types import (
    build_user_assertion_envelope,
    source_byte_hash,
    user_assertion_from_mapping,
)
from mediator.mediator import Mediator


class MockBackend:
    id = "mock_backend"

    def __call__(self, prompt):
        return "Mock response"


def _context(text, message_id, confidence=None, subject_key="employment-date"):
    payload = {
        "source_text": text,
        "source_kind": "user_statement",
        "source_id": message_id,
        "message_id": message_id,
        "assertion_status": "asserted",
        "extractor_version": "fact03-test",
        "source_hash": source_byte_hash(text),
        "source_span": {"start": 0, "end": len(text.encode("utf-8")), "text": text},
        "subject_key": subject_key,
    }
    if confidence is not None:
        payload["confidence"] = confidence
    return payload


def _asserted_fact(entity_id, text, message_id, confidence):
    envelope = build_user_assertion_envelope(**{
        key: value for key, value in _context(text, message_id, confidence).items() if key != "confidence"
    }, confidence=confidence)
    assert envelope.is_asserted_user_fact
    return Entity(
        id=entity_id,
        type="fact",
        name=text,
        attributes={"description": text, "fact_type": "timeline"},
        confidence=confidence,
        source="complaint",
        provenance={"user_assertion": envelope.as_dict()},
    ), envelope


def _mediator_with_fact(text, message_id, confidence=0.4):
    mediator = Mediator([MockBackend()])
    graph = KnowledgeGraph()
    fact, envelope = _asserted_fact("fact_original", text, message_id, confidence)
    claim = Entity(
        id="claim_1",
        type="claim",
        name="Termination",
        attributes={
            "claim_type": "employment",
            "satisfied_requirements": [fact.id],
            "satisfied_fact_bundle": [fact.id],
        },
        confidence=0.9,
    )
    graph.add_entity(claim)
    graph.add_entity(fact)
    graph.register_assertion(fact, envelope, status="active")
    graph.add_relationship(Relationship(
        id="rel_support",
        source_id=fact.id,
        target_id=claim.id,
        relation_type="supports",
        attributes={},
        confidence=0.9,
    ))
    dependency_graph = DependencyGraphBuilder().build_from_claims(
        [{"name": "Termination", "type": "employment"}]
    )
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "knowledge_graph", graph)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "dependency_graph", dependency_graph)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "intake_case_file", {
        "canonical_facts": [],
        "candidate_claims": [],
    })
    return mediator, fact, envelope


def _question():
    return {
        "type": "clarification",
        "question": "What date were you fired?",
        "context": {"fact_type": "timeline"},
    }


def test_correction_keeps_both_sources_and_supersedes_the_prior_assertion():
    original = "I was fired on January 1, 2020."
    corrected = "I was fired on January 2, 2020."
    mediator, fact, envelope = _mediator_with_fact(original, "msg-original", confidence=0.95)
    original_proof = copy.deepcopy(fact.provenance["user_assertion"])
    result = mediator.process_denoising_answer(
        _question(),
        corrected,
        answer_event_id="answer-event-correction",
        source_context=_context(corrected, "msg-correction", confidence=0.2),
        factual_action="correct",
        supersedes_stable_id=envelope.stable_id,
    )
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    assert fact.provenance["user_assertion"] == original_proof
    assert user_assertion_from_mapping(original_proof).is_asserted_user_fact
    assert graph.assertion_state(envelope.stable_id)["status"] == "superseded"
    new_state = graph.assertion_state(result["updates"]["stable_id"])
    assert new_state["status"] == "active"
    assert user_assertion_from_mapping(new_state["envelope"]).is_asserted_user_fact
    assert new_state["envelope"]["source_identity"] == "msg-correction"
    assert graph.assertion_state(envelope.stable_id)["envelope"]["source_identity"] == "msg-original"
    identities = {
        graph.assertion_state(envelope.stable_id)["source_identity"],
        new_state["source_identity"],
    }
    assert identities == {"msg-original", "msg-correction"}
    assert fact.id not in {item.id for item in graph.effective_fact_entities()}
    case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
    assert fact.id not in {item.get("fact_id") for item in case_file["canonical_facts"]}
    historical = case_file["historical_canonical_facts"]
    assert any(item.get("fact_id") == fact.id and item.get("activity_status") == "superseded" for item in historical)
    assert any(item.get("activity_status") == "invalidated" and item.get("effective") is False for item in case_file["support_links"])
    assert "fact_original" not in claim_satisfied(graph)
    assert result["next_questions"][0]["context"]["regenerated"] is True
    assert graph.metadata["revision"] > 0


def claim_satisfied(graph):
    claim = graph.get_entity("claim_1")
    return list((claim.attributes or {}).get("satisfied_requirements") or [])


def test_retraction_preserves_the_original_proof_and_drops_active_support():
    statement = "My employer fired me on March 3, 2024."
    retraction = "I retract the March 3, 2024 firing date."
    mediator, fact, envelope = _mediator_with_fact(statement, "msg-statement", confidence=0.99)
    original_proof = copy.deepcopy(fact.provenance["user_assertion"])
    mediator.process_denoising_answer(
        _question(),
        retraction,
        answer_event_id="answer-event-retract",
        source_context=_context(retraction, "msg-retract", subject_key="retraction"),
        factual_action="retract",
        retracts_stable_id=envelope.stable_id,
    )
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    assert fact.provenance["user_assertion"] == original_proof
    assert user_assertion_from_mapping(fact.provenance["user_assertion"]).is_asserted_user_fact
    assert graph.assertion_state(envelope.stable_id)["status"] == "retracted"
    assert fact.id not in {item.id for item in graph.effective_fact_entities()}
    assert graph._support_facts("claim_1", "Termination") == []
    case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
    assert all(item.get("fact_id") != fact.id for item in case_file["canonical_facts"])
    assert any(item.get("activity_status") == "retracted" for item in case_file["historical_canonical_facts"])
    assert any(not item["effective"] for item in case_file["support_links"] if item["relationship_id"] == "rel_support")
    assert case_file["reopened_questions"]


def test_contradictions_stay_unresolved_when_confidence_differs():
    low_text = "I was fired on January 1, 2020."
    high_text = "I was fired on June 1, 2020."
    low_graph = KnowledgeGraph()
    low_entity, low_envelope = _asserted_fact("entity_1", low_text, "msg-low", 0.2)
    low_graph.add_entity(low_entity)
    high_graph = KnowledgeGraph()
    high_entity, high_envelope = _asserted_fact("entity_1", high_text, "msg-high", 0.99)
    high_graph.add_entity(high_entity)
    low_graph.merge_with(high_graph)
    kept = low_graph.entities["entity_1"]
    assert kept.name == low_text
    assert kept.confidence == 0.2
    assert kept.provenance["user_assertion"]["stable_id"] == low_envelope.stable_id
    incoming = next(entity for entity in low_graph.entities.values() if entity.name == high_text)
    assert incoming.confidence == 0.99
    assert {low_graph.assertion_state(low_envelope.stable_id)["status"],
            low_graph.assertion_state(high_envelope.stable_id)["status"]} == {"conflict"}
    assert low_graph._support_facts("entity_1", low_text) == []

    reverse_low = KnowledgeGraph()
    reverse_high_entity, _ = _asserted_fact("entity_1", high_text, "msg-high", 0.99)
    reverse_low.add_entity(reverse_high_entity)
    reverse_incoming_graph = KnowledgeGraph()
    reverse_low_entity, _ = _asserted_fact("entity_1", low_text, "msg-low", 0.2)
    reverse_incoming_graph.add_entity(reverse_low_entity)
    reverse_low.merge_with(reverse_incoming_graph)
    assert reverse_low.entities["entity_1"].name == high_text
    assert reverse_low.entities["entity_1"].confidence == 0.99
    assert any(entity.name == low_text for entity in reverse_low.entities.values())


def test_explicit_contradiction_does_not_let_confidence_replace_the_original():
    original = "The meeting was on Monday."
    conflict = "The meeting was on Friday."
    mediator, fact, envelope = _mediator_with_fact(original, "msg-monday", confidence=0.15)
    original_proof = copy.deepcopy(fact.provenance["user_assertion"])
    mediator.process_denoising_answer(
        _question(),
        conflict,
        answer_event_id="answer-event-conflict",
        source_context=_context(conflict, "msg-friday", confidence=0.99, subject_key="meeting-day"),
        factual_action="contradict",
        contradicts_stable_id=envelope.stable_id,
    )
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    assert fact.name == original
    assert fact.confidence == 0.15
    assert fact.provenance["user_assertion"] == original_proof
    assert graph.assertion_state(envelope.stable_id)["status"] == "conflict"
    case_file = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file")
    statuses = {item.get("fact_id"): item.get("activity_status") for item in case_file["canonical_facts"]}
    assert statuses.get(fact.id) == "conflict"
    assert any(status == "conflict" for status in statuses.values())
    assert graph._support_facts("claim_1", "Termination") == []


def test_answer_event_replay_is_idempotent_after_reload_and_rejects_a_changed_payload():
    original = "I complained on May 1, 2024."
    corrected = "I complained on May 2, 2024."
    mediator, _fact, envelope = _mediator_with_fact(original, "msg-may-1", confidence=0.5)
    kwargs = dict(
        answer_event_id="answer-event-replay",
        source_context=_context(corrected, "msg-may-2", confidence=0.1),
        factual_action="correct",
        supersedes_stable_id=envelope.stable_id,
    )
    first = mediator.process_denoising_answer(_question(), corrected, **kwargs)
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    revision = graph.metadata["revision"]
    iterations = mediator.phase_manager.iteration_count
    asked = len(mediator.denoiser.questions_asked)
    questions = copy.deepcopy(first["next_questions"])
    reloaded = KnowledgeGraph.from_dict(graph.to_dict())
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "knowledge_graph", reloaded)
    second = mediator.process_denoising_answer(_question(), corrected, **kwargs)
    assert second["iteration"] == first["iteration"]
    assert second["updates"]["stable_id"] == first["updates"]["stable_id"]
    assert second["next_questions"] == questions
    assert mediator.phase_manager.iteration_count == iterations
    assert len(mediator.denoiser.questions_asked) == asked
    assert reloaded.metadata["revision"] == revision
    assert len(reloaded.factual_ledger()["revisions"]) == len(graph.factual_ledger()["revisions"])
    with pytest.raises(AnswerEventConflict):
        mediator.process_denoising_answer(
            _question(),
            "I complained on May 3, 2024.",
            answer_event_id="answer-event-replay",
            source_context=_context("I complained on May 3, 2024.", "msg-may-3"),
            factual_action="correct",
            supersedes_stable_id=envelope.stable_id,
        )
    assert reloaded.metadata["revision"] == revision
    assert len(mediator.denoiser.questions_asked) == asked


def test_builder_local_ids_and_rewired_relationships_do_not_overwrite_history():
    current = KnowledgeGraph()
    current.add_entity(Entity(id="entity_1", type="person", name="Alice", attributes={"description": "Alice"}))
    current.add_entity(Entity(id="entity_2", type="organization", name="Acme", attributes={"description": "Acme"}))
    incoming = KnowledgeGraph()
    incoming.add_entity(Entity(id="entity_1", type="person", name="Bob", attributes={"description": "Bob"}))
    incoming.add_entity(Entity(id="entity_2", type="organization", name="Acme", attributes={"description": "Acme"}))
    statement = "Bob worked for Acme."
    envelope = build_user_assertion_envelope(
        source_text=statement,
        source_kind="user_statement",
        source_id="msg-rel",
        message_id="msg-rel",
        assertion_status="asserted",
        extractor_version="fact03-test",
        source_hash=source_byte_hash(statement),
        source_span={"start": 0, "end": len(statement.encode("utf-8")), "text": statement},
        role="worked_for",
        subject_key="employment",
        graph_source_id="entity_1",
        graph_target_id="entity_2",
    )
    assert envelope.is_asserted_user_fact
    relationship = Relationship(
        id="rel_1",
        source_id="entity_1",
        target_id="entity_2",
        relation_type="worked_for",
        attributes={},
        confidence=0.4,
        provenance={"user_assertion": envelope.as_dict()},
    )
    incoming.add_relationship(relationship)
    original_proof = copy.deepcopy(relationship.provenance["user_assertion"])
    current.merge_with(incoming)
    assert current.entities["entity_1"].name == "Alice"
    assert any(entity.name == "Bob" for entity in current.entities.values())
    assert relationship.provenance["user_assertion"] == original_proof
    rewired = [item for item in current.relationships.values() if item.relation_type == "worked_for"]
    assert rewired
    assert all("user_assertion" not in (item.provenance or {}) for item in rewired)
    for entity in current.entities.values():
        restored = assertion_from_provenance(entity.provenance)
        assert restored is None or not restored.is_asserted_user_fact


def test_prior_graph_snapshot_is_immutable_after_correction():
    old = "I was fired on January 1, 2020."
    new = "I was fired on January 2, 2020."
    mediator, fact, proof = _mediator_with_fact(old, "audit-snapshot-original")
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    snapshot = graph.to_dict()
    before = json.dumps(snapshot, sort_keys=True)
    mediator.process_denoising_answer(_question(), new,
        answer_event_id="audit-snapshot-correction",
        source_context=_context(new, "audit-snapshot-new"),
        factual_action="correct", supersedes_stable_id=proof.stable_id)
    assert json.dumps(snapshot, sort_keys=True) == before


def test_retracted_fact_does_not_reenter_effective_factual_allegations():
    old = "My employer fired me on March 3, 2024."
    withdrawal = "I retract the March 3, 2024 firing date."
    mediator, fact, proof = _mediator_with_fact(old, "audit-allegation-original")
    mediator.process_denoising_answer(_question(), withdrawal,
        answer_event_id="audit-allegation-retract",
        source_context=_context(withdrawal, "audit-allegation-retraction"),
        factual_action="retract", retracts_stable_id=proof.stable_id)
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    assert graph.assertion_state(proof.stable_id)["status"] == "retracted"
    assert old not in "\n".join(mediator._generate_factual_allegations(graph))


def test_unknown_correction_target_does_not_partially_insert_an_active_fact():
    old = "I was fired on January 1, 2020."
    new = "I was fired on January 2, 2020."
    mediator, fact, proof = _mediator_with_fact(old, "audit-atomic-original")
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    graph.factual_ledger()
    before = copy.deepcopy(graph.to_dict())
    with pytest.raises((KeyError, ValueError)):
        mediator.process_denoising_answer(_question(), new,
            answer_event_id="audit-unknown-target",
            source_context=_context(new, "audit-atomic-new"),
            factual_action="correct", supersedes_stable_id="missing-source-assertion")
    assert graph.to_dict() == before


def test_retraction_reopens_a_real_denoiser_satisfied_dependency():
    old = "My employer fired me on March 3, 2024."
    withdrawal = "I retract the March 3, 2024 firing date."
    mediator, fact, proof = _mediator_with_fact(old, "audit-dependency-original")
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    dg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
    requirement = DependencyNode(id="audit-timeline-requirement", node_type=NodeType.REQUIREMENT,
        name="Date of adverse action", satisfied=False)
    dg.add_node(requirement)
    question = {"type": "requirement", "question": "When did the firing occur?",
        "context": {"requirement_id": requirement.id, "fact_type": "timeline"}}
    mediator.denoiser.process_answer(question, old, graph, dg)
    assert requirement.satisfied is True
    assert requirement.attributes["satisfied_via_denoiser"] is True
    assert requirement.attributes["satisfied_answer_text"] == old
    mediator.process_denoising_answer(question, withdrawal,
        answer_event_id="audit-dependency-retraction",
        source_context=_context(withdrawal, "audit-dependency-retract"),
        factual_action="retract", retracts_stable_id=proof.stable_id)
    assert requirement.satisfied is False


def test_loaded_graph_revision_does_not_mutate_its_input_or_original_graph():
    old = "I was fired on January 1, 2020."
    new = "I was fired on January 2, 2020."
    mediator, _fact, proof = _mediator_with_fact(old, "roundtrip-original")
    original = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    payload = original.to_dict()
    before = copy.deepcopy(payload)
    loaded = KnowledgeGraph.from_dict(payload)
    mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "knowledge_graph", loaded)
    mediator.process_denoising_answer(_question(), new,
        answer_event_id="roundtrip-correction",
        source_context=_context(new, "roundtrip-new"),
        factual_action="correct", supersedes_stable_id=proof.stable_id)
    assert payload == before
    assert original.to_dict() == before
    assert loaded.assertion_state(proof.stable_id)["status"] == "superseded"


def test_targeted_retraction_preserves_unrelated_dependency_satisfaction():
    old = "My employer fired me on March 3, 2024."
    withdrawal = "I retract the March 3, 2024 firing date."
    unrelated = "I paid the filing fee on April 4, 2024."
    mediator, _fact, proof = _mediator_with_fact(old, "targeted-original")
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    dg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
    requirements = [DependencyNode(id=name, node_type=NodeType.REQUIREMENT,
        name=name, satisfied=False) for name in ("targeted-date", "independent-filing-fee")]
    for node, answer in zip(requirements, (old, unrelated)):
        dg.add_node(node)
        question = {"type": "requirement", "question": node.name,
            "context": {"requirement_id": node.id, "fact_type": "timeline"}}
        mediator.denoiser.process_answer(question, answer, graph, dg)
        assert node.satisfied is True
    preserved = copy.deepcopy(requirements[1].to_dict())
    mediator.process_denoising_answer(
        {"type": "requirement", "question": "Correct the firing date",
         "context": {"requirement_id": requirements[0].id, "fact_type": "timeline"}},
        withdrawal, answer_event_id="targeted-retraction",
        source_context=_context(withdrawal, "targeted-retraction-source"),
        factual_action="retract", retracts_stable_id=proof.stable_id)
    assert requirements[0].satisfied is False
    assert requirements[1].to_dict() == preserved


def test_invalidated_support_link_cannot_support_an_otherwise_current_fact():
    text = "My employer fired me on March 3, 2024."
    mediator, _fact, _proof = _mediator_with_fact(text, "invalidated-link-source")
    graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
    assert graph._support_facts("claim_1", "Termination")
    graph.relationships["rel_support"].attributes.update(
        activity_status="invalidated", effective=False)
    assert graph._support_facts("claim_1", "Termination") == []
