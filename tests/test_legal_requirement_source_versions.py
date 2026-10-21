"""Source-bound legal rule candidates and verified requirement promotion."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

from complaint_phases.legal_graph import LegalGraphBuilder
from integrations.ipfs_datasets.logic import (
    extract_source_bound_rule_candidates,
    is_applicable_legal_requirement,
    legacy_unverified_requirement_templates,
    sha256_utf8,
)


def _authority(text: str, **overrides):
    payload = {
        "source_text": text,
        "jurisdiction": "US-OR",
        "authority_id": "ors:659A.030",
        "citation": "ORS 659A.030",
        "authority_version": "2024-edition",
        "source_hash": sha256_utf8(text),
        "effective_date": "2024-01-01",
        "as_of_date": "2024-06-01",
    }
    payload.update(overrides)
    return payload


def _promoted(text: str, **overrides):
    result = extract_source_bound_rule_candidates(_authority(text, **overrides))
    promoted = result["promoted_requirements"]
    assert len(promoted) == 1
    return promoted[0], result


def test_claim_keyword_templates_stay_unverified_and_inapplicable():
    templates = legacy_unverified_requirement_templates(["employment_discrimination"])
    assert [item["name"] for item in templates] == [
        "Protected Class Membership",
        "Adverse Action",
        "Causal Connection",
    ]
    assert all(item["verification_status"] == "unverified_template" for item in templates)
    assert all(item["applicable"] is False for item in templates)
    assert all(not is_applicable_legal_requirement(item) for item in templates)

    graph = LegalGraphBuilder().build_from_statutes(
        [{"name": "Title VII", "citation": "42 USC 2000e", "description": "discrimination"}],
        ["discrimination"],
    )
    requirements = graph.get_elements_by_type("legal_requirement")
    assert requirements
    assert all(element.attributes["verification_status"] == "unverified_template" for element in requirements)
    assert graph.get_requirements_for_claim_type("discrimination") == []

    procedural = LegalGraphBuilder().build_rules_of_procedure()
    nodes = procedural.get_elements_by_type("procedural_requirement")
    assert nodes
    assert all(node.attributes["template_kind"] == "procedural_template" for node in nodes)
    assert all(not is_applicable_legal_requirement(node.attributes) for node in nodes)


def test_complete_coordinates_promote_exact_span_and_ignore_caller_flags():
    text = "An employer shall not retaliate against an employee for opposing an unlawful practice."
    promoted, result = _promoted(text, promoted=True, applicable=True, verification_status="promoted")
    span = promoted["source_span"]
    raw = text.encode("utf-8")
    assert raw[span["start"]:span["end"]].decode("utf-8") == text
    assert promoted["span_sha256"] == sha256_utf8(text)
    assert promoted["source_hash"] == sha256_utf8(text)
    assert promoted["jurisdiction"] == "US-OR"
    assert promoted["authority_identity"] == "ors:659A.030"
    assert promoted["authority_version"] == "2024-edition"
    assert promoted["applicable_date"]["effective_date"] == "2024-01-01"
    assert promoted["applicable_date"]["as_of_date"] == "2024-06-01"
    assert promoted["structure"]["deontic_operator"] == "prohibition"
    assert promoted["structure"]["rule_character"] == "substantive"
    assert promoted["deontic_operator_is_proof"] is False
    assert result["candidate_count"] == 1


def test_missing_version_date_hash_or_jurisdiction_stays_candidate():
    text = "An employer shall not retaliate against an employee."
    cases = [
        {"authority_version": ""},
        {"effective_date": "", "as_of_date": ""},
        {"source_hash": ""},
        {"jurisdiction": "unknown"},
        {"authority_id": "", "citation": ""},
        {"source_hash": sha256_utf8("different text")},
    ]
    expected = [
        "missing_authority_version",
        "missing_applicable_date",
        "missing_source_hash",
        "missing_jurisdiction",
        "missing_authority_identity",
        "source_hash_mismatch",
    ]
    for overrides, reason in zip(cases, expected):
        result = extract_source_bound_rule_candidates(_authority(text, **overrides))
        assert result["promoted_count"] == 0
        assert reason in result["candidates"][0]["review_reasons"]
        assert result["candidates"][0]["applicable"] is False


def test_unicode_span_is_utf8_bytes_and_repeated_text_is_ambiguous():
    text = "An employer shall not retaliate against José."
    promoted, _ = _promoted(text)
    span = promoted["source_span"]
    assert span["end"] - span["start"] == len(text.encode("utf-8"))
    assert span["end"] - span["start"] != len(text)

    repeated = text + " " + text
    result = extract_source_bound_rule_candidates(_authority(repeated))
    assert result["promoted_count"] == 0
    assert result["candidates"][0]["review_reason"].find("ambiguous_source_span") >= 0
    assert len(result["candidates"]) == 1


def test_conditions_exceptions_and_connectives_are_preserved():
    conditional = (
        "If an employee opposes an unlawful practice, an employer shall not retaliate, "
        "except when the opposition is unlawful."
    )
    promoted, _ = _promoted(conditional)
    structure = promoted["structure"]
    assert structure["conditions"][0]["text"] == "an employee opposes an unlawful practice"
    assert structure["conditions"][0]["span_status"] == "exact"
    assert structure["exceptions"][0]["text"].startswith("except when")
    assert structure["rule_character"] == "substantive"
    assert structure["connective"] == "none"

    conjunction = "A charge shall be filed within 180 days and a notice shall be filed within 10 days."
    joined, _ = _promoted(conjunction)
    assert joined["structure"]["connective"] == "conjunction"
    assert joined["structure"]["rule_character"] == "procedural"
    assert len(joined["structure"]["conjuncts"]) == 2

    disjunction = "A party shall file a notice or a party shall file a statement of the delay."
    either, _ = _promoted(disjunction)
    assert either["structure"]["connective"] == "disjunction"
    assert either["rule_character"] == "procedural"
    assert len(either["structure"]["disjuncts"]) == 2

    mixed = (
        "An employer shall not retaliate against an employee, "
        "except that a charge shall be filed within 180 days."
    )
    mixed_rule, _ = _promoted(mixed)
    assert mixed_rule["structure"]["rule_character"] == "mixed"
    assert mixed_rule["structure"]["exceptions"]

    ambiguous = "A party shall file a notice and serve it or shall state the reason."
    result = extract_source_bound_rule_candidates(_authority(ambiguous))
    assert result["promoted_count"] == 0
    assert "ambiguous_connective" in result["candidates"][0]["review_reasons"]
    assert result["candidates"][0]["structure"]["conjunction_count"] == 1
    assert result["candidates"][0]["structure"]["disjunction_count"] == 1


def test_unsupported_sentence_and_span_mismatch_remain_candidates():
    narrative = "This chapter discusses employment."
    result = extract_source_bound_rule_candidates(_authority(narrative))
    assert result["promoted_count"] == 0
    assert "unsupported_deontic_extraction" in result["candidates"][0]["review_reasons"]

    text = "An employer shall not retaliate against an employee."
    mismatched = _authority(text, rule_text=text, source_span={"start": 1, "end": 4, "text": text})
    result = extract_source_bound_rule_candidates(mismatched)
    assert "source_span_mismatch" in result["candidates"][0]["review_reasons"]

    legacy = _authority(text, legacy_template=True, template_kind="claim_keyword_template")
    result = extract_source_bound_rule_candidates(legacy)
    assert result["promoted_count"] == 0
    assert "legacy_unverified_template" in result["candidates"][0]["review_reasons"]


def test_passage_hash_scope_promotes_when_span_bytes_match():
    text = "Intro. An employer shall not retaliate against an employee."
    rule = "An employer shall not retaliate against an employee."
    result = extract_source_bound_rule_candidates(_authority(
        text,
        rule_text=rule,
        source_hash=sha256_utf8(rule),
        content_hash_scope="source_passage",
    ))
    assert result["promoted_count"] == 1
    promoted = result["promoted_requirements"][0]
    assert promoted["source_hash_scope"] == "source_passage"
    assert promoted["span_sha256"] == sha256_utf8(rule)
    raw = text.encode("utf-8")
    span = promoted["source_span"]
    assert raw[span["start"]:span["end"]].decode("utf-8") == rule


def test_graph_promotion_keeps_candidate_distinct_from_requirement():
    text = "An employer shall not retaliate against an employee for opposing an unlawful practice."
    graph = LegalGraphBuilder().build_from_statutes(
        [{
            "name": "ORS 659A.030",
            "citation": "ORS 659A.030",
            "jurisdiction": "US-OR",
            "text": text,
            "authority_id": "ors:659A.030",
            "authority_version": "2024-edition",
            "source_hash": sha256_utf8(text),
            "effective_date": "2024-01-01",
        }],
        ["retaliation"],
    )
    promoted = [
        element for element in graph.get_elements_by_type("legal_requirement")
        if element.attributes.get("promotion_status") == "promoted"
    ]
    assert len(promoted) == 1
    assert is_applicable_legal_requirement(promoted[0].attributes)
    span = promoted[0].attributes["source_span"]
    assert text.encode("utf-8")[span["start"]:span["end"]].decode("utf-8") == text
    assert graph.get_requirements_for_claim_type("discrimination") == []
    assert graph.get_requirements_for_claim_type("retaliation") == promoted

    authority_graph = LegalGraphBuilder().build_from_authorities([{
        "authority_id": "ors:659A.030",
        "name": "ORS 659A.030",
        "citation": "ORS 659A.030",
        "jurisdiction": "US-OR",
        "authority_version": "2024-edition",
        "source_text": text,
        "source_hash": sha256_utf8(text),
        "effective_date": "2024-01-01",
        "claim_type": "retaliation",
        "rule_candidates": [{"rule_text": text, "rule_type": "prohibition", "claim_element_id": "element-1"}],
    }], claim_elements=[{"element_id": "element-1", "element_text": "retaliation"}])
    rule = next(element for element in authority_graph.elements.values() if element.element_type == "rule_candidate")
    requirement = next(
        element for element in authority_graph.elements.values()
        if element.element_type == "legal_requirement" and element.attributes.get("promoted") is True
    )
    assert rule.attributes["applicable"] is False
    assert requirement.attributes["authority_version"] == "2024-edition"
    assert requirement.attributes["source_hash"] == sha256_utf8(text)
    assert any(rel.relation_type == "promoted_from" for rel in authority_graph.relations.values())
    assert authority_graph.get_requirements_for_claim_type("retaliation") == [requirement]
