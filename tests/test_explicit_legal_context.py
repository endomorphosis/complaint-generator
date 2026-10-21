"""Explicit jurisdiction and legally relevant dates stay unresolved until stated."""

from types import SimpleNamespace

from complaint_phases import Entity, KnowledgeGraph
from complaint_phases.intake_case_file import (
    apply_explicit_legal_context,
    build_intake_case_file,
    extract_explicit_jurisdiction_from_text,
)
from integrations.ipfs_datasets.legal import (
    apply_legal_context_update,
    classify_legal_date,
    constrain_assertions_to_corpus,
    empty_legal_context,
    legal_requirement_search_plan,
    resolve_explicit_jurisdiction,
    search_legal_authority_program,
    select_requirement_applicability,
)
from mediator.mediator import Mediator


def test_unresolved_jurisdiction_is_unknown_not_oregon_or_federal():
    assert resolve_explicit_jurisdiction(None) == "unknown"
    assert resolve_explicit_jurisdiction("") == "unknown"
    assert resolve_explicit_jurisdiction("somewhere") == "unknown"
    assert resolve_explicit_jurisdiction("Oregon") == "OR"
    assert resolve_explicit_jurisdiction("federal") == "federal"
    assert legal_requirement_search_plan({"query_text": "retaliation", "authority_families": ["statute"]}) == {
        "jurisdiction": "unknown",
        "state_code": "",
        "context_status": "unknown",
        "selected_rule_applicability": "unknown",
        "search_us_code": False,
        "search_federal_register": False,
        "search_state_laws": False,
        "search_state_administrative_rules": False,
        "search_case_law": False,
        "authority_families": ["statute"],
    }


def test_authority_program_does_not_search_when_context_is_unresolved(monkeypatch):
    def _forbidden(*_args, **_kwargs):
        raise AssertionError("implicit legal search")

    monkeypatch.setattr("integrations.ipfs_datasets.legal.search_us_code", _forbidden)
    monkeypatch.setattr("integrations.ipfs_datasets.legal.search_federal_register", _forbidden)
    monkeypatch.setattr("integrations.ipfs_datasets.legal.search_state_laws", _forbidden)
    monkeypatch.setattr("integrations.ipfs_datasets.legal.search_state_administrative_rules", _forbidden)
    monkeypatch.setattr("integrations.ipfs_datasets.legal.search_recap_documents", _forbidden)

    result = search_legal_authority_program(
        {"query_text": "wage claim", "program_id": "prog-1", "authority_families": ["statute", "regulation"]}
    )
    assert result["metadata"]["jurisdiction"] == "unknown"
    assert result["metadata"]["state_code"] == ""
    assert result["metadata"]["context_status"] == "unknown"
    assert result["metadata"]["selected_rule_applicability"] == "unknown"
    assert result["result_count"] == 0


def test_corpus_constraint_leaves_unresolved_context_unknown(monkeypatch):
    monkeypatch.setattr(
        "integrations.ipfs_datasets.legal.search_us_code",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("implicit federal search")),
    )
    result = constrain_assertions_to_corpus([{"assertion_id": "a1", "text": "The employer retaliated."}])
    assert result["jurisdiction"] == "unknown"
    assert result["context_status"] == "unknown"
    assert result["selected_rule_applicability"] == "unknown"
    assert result["details"][0]["applicability"] == "unknown"
    assert result["details"][0]["reason"] == "unresolved_legal_context"
    assert result["grounded_count"] == 0


def test_date_roles_stay_distinct_and_uncertain_ranges_are_not_precise_days():
    event = classify_legal_date("early March 2024", role="event_date")
    applicable = classify_legal_date("2024-03-15", role="applicable_law_date")
    filing = classify_legal_date("March 2024 to May 2024", role="filing_reference_date")
    retrieval = classify_legal_date("2024-06-01", role="corpus_retrieval_date")

    assert event["role"] == "event_date"
    assert event["precision"] == "uncertain_range"
    assert event["precise_date"] is None
    assert event["raw_text"] == "early March 2024"
    assert applicable["role"] == "applicable_law_date"
    assert applicable["precise_date"] == "2024-03-15"
    assert filing["role"] == "filing_reference_date"
    assert filing["precision"] == "range"
    assert filing["precise_date"] is None
    assert filing["start_date"] == "2024-03-01"
    assert filing["end_date"] == "2024-05-31"
    assert retrieval["role"] == "corpus_retrieval_date"
    assert {event["role"], applicable["role"], filing["role"], retrieval["role"]} == {
        "event_date",
        "applicable_law_date",
        "filing_reference_date",
        "corpus_retrieval_date",
    }


def test_requirement_selection_requires_explicit_context_and_rejects_mismatch():
    context = empty_legal_context()
    unresolved = select_requirement_applicability({"jurisdiction": "OR", "requirement_id": "r1"}, context)
    assert unresolved["selected"] is False
    assert unresolved["applicability"] == "unknown"

    context = apply_legal_context_update(context, {
        "jurisdiction": "Oregon",
        "applicable_law_date": "March 1, 2024",
        "event_date": "sometime in spring 2024",
    })
    selected = select_requirement_applicability({"jurisdiction": "OR"}, context)
    assert selected["selected"] is True
    assert selected["event_date"]["precise_date"] is None
    assert selected["applicable_law_date"]["precise_date"] == "2024-03-01"
    federal = select_requirement_applicability({"jurisdiction": "federal"}, context)
    assert federal["selected"] is False
    assert federal["reason"] == "jurisdiction_not_selected"


def test_changing_context_invalidates_selected_rules_and_dependent_proof():
    context = apply_legal_context_update(empty_legal_context(), {
        "jurisdiction": "OR",
        "applicable_law_date": "2024-01-01",
        "event_date": "2024-02-02",
    })
    context["selected_rule_applicability"] = "selected"
    context["proof_state"] = "supported"
    context["dependent_proof"] = [{"lead_id": "lead-1", "proof_state": "supported"}]
    updated = apply_legal_context_update(
        context,
        {"jurisdiction": "WA", "event_date": "early 2024"},
        dependent_proof=context["dependent_proof"],
    )
    assert updated["jurisdiction"] == "WA"
    assert updated["context_revision"] == context["context_revision"] + 1
    assert updated["selected_rule_applicability"] == "invalidated"
    assert updated["proof_state"] == "invalidated"
    assert updated["dependent_proof"][0]["proof_state"] == "invalidated"
    assert updated["event_date"]["precision"] == "uncertain_range"
    assert updated["event_date"]["precise_date"] is None
    stale = select_requirement_applicability(
        {"jurisdiction": "WA", "context_revision": context["context_revision"]},
        updated,
    )
    assert stale["applicability"] == "invalidated"


def test_intake_asks_for_missing_jurisdiction_and_keeps_location_from_becoming_law():
    graph = KnowledgeGraph()
    graph.add_entity(Entity(
        id="fact:1",
        type="fact",
        name="Office event",
        attributes={
            "description": "The meeting happened at the Dallas office.",
            "fact_type": "timeline",
            "event_date_or_range": "sometime in spring 2024",
        },
    ))
    case_file = build_intake_case_file(graph, "The meeting happened at the Dallas office.")
    assert extract_explicit_jurisdiction_from_text(case_file["source_complaint_text"]) == "unknown"
    assert case_file["legal_context"]["jurisdiction"] == "unknown"
    assert case_file["legal_context"]["status"] == "unknown"
    event = case_file["legal_context"]["event_date"]
    assert event["raw_text"] == "sometime in spring 2024"
    assert event["precise_date"] is None
    question_ids = {item["open_item_id"] for item in case_file["open_items"]}
    assert "legal_context:legal_context.jurisdiction" in question_ids
    prompts = " ".join(item["reason"] for item in case_file["open_items"])
    assert "Oregon" in prompts
    assert "federal" in prompts.lower() or "Federal" in prompts


def test_intake_context_change_invalidates_proof_and_records_separate_dates():
    graph = KnowledgeGraph()
    graph.add_entity(Entity(
        id="fact:1",
        type="fact",
        name="Termination",
        attributes={
            "description": "Employer terminated Plaintiff on January 20, 2026.",
            "fact_type": "timeline",
            "event_date_or_range": "January 20, 2026",
        },
    ))
    case_file = build_intake_case_file(
        graph,
        "Under Oregon law. Applicable law date: January 1, 2024. Filed on March 1, 2024.",
    )
    assert case_file["legal_context"]["jurisdiction"] == "OR"
    assert case_file["legal_context"]["event_date"]["precise_date"] == "2026-01-20"
    assert case_file["legal_context"]["applicable_law_date"]["precise_date"] == "2024-01-01"
    assert case_file["legal_context"]["filing_reference_date"]["precise_date"] == "2024-03-01"
    assert case_file["legal_context"]["event_date"]["role"] != case_file["legal_context"]["filing_reference_date"]["role"]
    case_file["legal_context"]["selected_rule_applicability"] = "selected"
    case_file["legal_context"]["proof_state"] = "supported"
    case_file["proof_leads"] = [{"lead_id": "lead-9", "proof_state": "supported", "text": "letter"}]
    updated = apply_explicit_legal_context(
        case_file,
        jurisdiction="Washington",
        corpus_retrieval_date="2026-04-04",
    )
    assert updated["legal_context"]["jurisdiction"] == "WA"
    assert updated["legal_context"]["selected_rule_applicability"] == "invalidated"
    assert updated["legal_context"]["proof_state"] == "invalidated"
    assert updated["proof_leads"][0]["proof_state"] == "invalidated"
    assert updated["legal_context"]["corpus_retrieval_date"]["role"] == "corpus_retrieval_date"
    assert updated["legal_context"]["corpus_retrieval_date"]["precise_date"] == "2026-04-04"
    assert updated["legal_context"]["event_date"]["precise_date"] == "2026-01-20"


def test_mediator_does_not_default_jurisdiction_to_federal():
    mediator = Mediator.__new__(Mediator)
    empty = SimpleNamespace(elements={})
    assert mediator._determine_jurisdiction(empty) == "unknown"
    labeled = SimpleNamespace(elements={
        "e1": SimpleNamespace(jurisdiction=""),
        "e2": SimpleNamespace(jurisdiction="federal"),
        "e3": SimpleNamespace(jurisdiction="federal"),
    })
    assert mediator._determine_jurisdiction(labeled) == "federal"
    mixed = SimpleNamespace(elements={
        "e1": SimpleNamespace(jurisdiction="OR"),
        "e2": SimpleNamespace(jurisdiction="WA"),
    })
    assert mediator._determine_jurisdiction(mixed) == "unknown"
    questions = mediator.legal_context_questions({"canonical_facts": [], "source_complaint_text": ""})
    assert any(item["field"] == "jurisdiction" for item in questions)
    assert any(item["field"] == "event_date" for item in questions)
