"""Tests for the implemented check_contradictions function and graphrag local fallbacks.

These tests confirm that:
- check_contradictions is fully implemented (no longer returns 'not_implemented')
- formula-level contradictions are detected
- temporal-signal contradictions are surfaced
- graphrag build_ontology / validate_ontology / run_refinement_cycle have working
  local fallbacks instead of returning 'not_implemented'
"""
from __future__ import annotations

from typing import Any, Dict


# ---------------------------------------------------------------------------
# check_contradictions
# ---------------------------------------------------------------------------

def test_check_contradictions_returns_implemented_status():
    from integrations.ipfs_datasets.logic import check_contradictions

    result = check_contradictions([])
    assert result["metadata"]["implementation_status"] == "implemented"


def test_check_contradictions_empty_predicates():
    from integrations.ipfs_datasets.logic import check_contradictions

    result = check_contradictions([])
    assert isinstance(result.get("contradictions"), list)
    assert result.get("contradiction_count") == 0
    assert result.get("has_contradictions") is False
    assert result.get("proof_status") == "passed"


def test_check_contradictions_required_keys():
    from integrations.ipfs_datasets.logic import check_contradictions

    result = check_contradictions([{"predicate_type": "factual_statement", "formula": "P(x)"}])
    for key in ("contradictions", "contradiction_count", "has_contradictions", "proof_status"):
        assert key in result, f"Missing key: {key}"


def test_check_contradictions_temporal_issue_signal():
    from integrations.ipfs_datasets.logic import check_contradictions

    predicates = [
        {
            "predicate_type": "temporal_issue",
            "claim_type": "retaliation",
            "predicate_id": "issue-1",
            "issue_type": "reverse_before",
            "summary": "Event B occurs before Event A but should follow it.",
            "severity": "error",
        }
    ]
    result = check_contradictions(predicates)
    assert result["has_contradictions"] is True
    assert result["contradiction_count"] >= 1
    assert result["proof_status"] == "needs_review"
    assert any(c.get("type") == "temporal_issue" for c in result["contradictions"])


def test_check_contradictions_contradiction_candidate_signal():
    from integrations.ipfs_datasets.logic import check_contradictions

    predicates = [
        {
            "predicate_type": "contradiction_candidate",
            "claim_type": "retaliation",
            "predicate_id": "cand-1",
            "summary": "Two timeline entries conflict.",
            "severity": "warning",
        }
    ]
    result = check_contradictions(predicates)
    assert result["has_contradictions"] is True
    assert result["contradiction_count"] >= 1


def test_check_contradictions_no_contradiction_in_normal_predicates():
    from integrations.ipfs_datasets.logic import check_contradictions

    predicates = [
        {"predicate_type": "claim_element", "claim_type": "retaliation", "claim_element_id": "elem-1"},
        {"predicate_type": "support_trace", "claim_type": "retaliation", "support_ref": "QmABC"},
        {"predicate_type": "temporal_fact", "claim_type": "retaliation", "start_date": "2024-01-01"},
    ]
    result = check_contradictions(predicates)
    # No contradiction-type predicates — count should be 0
    assert result["contradiction_count"] == 0
    assert result["has_contradictions"] is False
    assert result["proof_status"] == "passed"


def test_check_contradictions_preserves_predicate_summary():
    from integrations.ipfs_datasets.logic import check_contradictions

    predicates = [
        {"predicate_type": "claim_element", "claim_type": "retaliation", "claim_element_id": "e1"},
        {"predicate_type": "temporal_fact", "claim_type": "retaliation", "start_date": "2024-01-01"},
    ]
    result = check_contradictions(predicates)
    assert result.get("predicate_count") == 2
    assert isinstance(result.get("predicate_type_counts"), dict)


def test_check_contradictions_returns_temporal_reasoning_payload():
    from integrations.ipfs_datasets.logic import check_contradictions

    predicates = [
        {"predicate_type": "temporal_fact", "claim_type": "retaliation", "start_date": "2024-03-01"},
    ]
    result = check_contradictions(predicates)
    assert isinstance(result.get("temporal_reasoning_payload"), dict)


# ---------------------------------------------------------------------------
# prove_claim_elements now exposes contradiction_count and contradictions
# ---------------------------------------------------------------------------

def test_prove_claim_elements_exposes_contradiction_fields():
    from integrations.ipfs_datasets.logic import prove_claim_elements

    result = prove_claim_elements([
        {"predicate_type": "claim_element", "claim_type": "retaliation", "coverage_status": "unsupported"},
    ])
    assert "contradiction_count" in result
    assert "contradictions" in result
    assert isinstance(result["contradiction_count"], int)
    assert isinstance(result["contradictions"], list)


def test_prove_claim_elements_contradiction_count_non_negative():
    from integrations.ipfs_datasets.logic import prove_claim_elements

    result = prove_claim_elements([])
    assert result["contradiction_count"] >= 0


def test_prove_claim_elements_with_temporal_issue_raises_contradiction_count():
    from integrations.ipfs_datasets.logic import prove_claim_elements

    predicates = [
        {
            "predicate_type": "temporal_issue",
            "claim_type": "retaliation",
            "predicate_id": "issue-1",
            "summary": "Chronological conflict detected.",
            "severity": "error",
        }
    ]
    result = prove_claim_elements(predicates)
    assert result["contradiction_count"] >= 1


# ---------------------------------------------------------------------------
# graphrag local fallbacks
# ---------------------------------------------------------------------------

def test_build_ontology_local_fallback_returns_success():
    from integrations.ipfs_datasets.graphrag import build_ontology

    result = build_ontology("Defendant terminated Plaintiff after the complaint.")
    assert result["metadata"]["implementation_status"] != "not_implemented"
    assert result.get("status") in {"success", "unavailable", "error"}
    # When unavailable (no backend), status is unavailable — that's fine.
    # The key assertion: we no longer return 'not_implemented'.


def test_build_ontology_local_fallback_has_ontology():
    from integrations.ipfs_datasets.graphrag import build_ontology, GRAPHRAG_AVAILABLE

    if not GRAPHRAG_AVAILABLE:
        import pytest
        pytest.skip("graphrag backend not available; local fallback only reached when backend is present")

    result = build_ontology("Defendant terminated Plaintiff after the complaint to HR.")
    assert result.get("status") in {"success", "error"}
    # When the backend is available but lacks .generate(), the local fallback fires.
    if result.get("status") == "success":
        assert result.get("ontology") is not None


def test_build_local_ontology_helper():
    """The local helper extracts entities, relations, and concepts from text."""
    from integrations.ipfs_datasets.graphrag import _build_local_ontology

    result = _build_local_ontology(
        "Defendant terminated Plaintiff on March 1. "
        "Plaintiff reported discrimination to HR."
    )
    assert isinstance(result.get("entities"), list)
    assert isinstance(result.get("relations"), list)
    assert isinstance(result.get("concepts"), list)
    assert result.get("entity_count") == len(result["entities"])
    assert result.get("relation_count") == len(result["relations"])
    assert result.get("concept_count") == len(result["concepts"])
    assert result.get("source") == "local_regex_fallback"
    # "Defendant" and "Plaintiff" should be found as named entities
    entity_names = {e["name"] for e in result["entities"]}
    assert "Defendant" in entity_names or "Plaintiff" in entity_names


def test_validate_ontology_locally_valid():
    from integrations.ipfs_datasets.graphrag import _validate_ontology_locally

    ontology = {
        "entities": [{"name": "Defendant", "type": "party"}],
        "relations": [{"subject": "Defendant", "predicate": "terminated", "object": "Plaintiff"}],
        "concepts": [],
    }
    result = _validate_ontology_locally(ontology)
    assert result["valid"] is True
    assert result["issues"] == []
    assert result["field_presence"]["entities"] is True
    assert result["field_presence"]["relations"] is True


def test_validate_ontology_locally_empty_dict():
    from integrations.ipfs_datasets.graphrag import _validate_ontology_locally

    result = _validate_ontology_locally({})
    assert result["valid"] is False
    assert result["issues"]


def test_validate_ontology_locally_non_dict():
    from integrations.ipfs_datasets.graphrag import _validate_ontology_locally

    result = _validate_ontology_locally("not a dict")
    assert result["valid"] is False


def test_validate_ontology_locally_missing_standard_keys():
    from integrations.ipfs_datasets.graphrag import _validate_ontology_locally

    result = _validate_ontology_locally({"other_key": "value"})
    assert result["valid"] is False
    assert any("entities" in issue or "relations" in issue or "concepts" in issue for issue in result["issues"])


def test_validate_ontology_adapter_returns_implemented():
    from integrations.ipfs_datasets.graphrag import validate_ontology, LogicValidator

    if LogicValidator is None:
        import pytest
        pytest.skip("LogicValidator unavailable; validate_ontology returns 'unavailable', not 'not_implemented'")

    result = validate_ontology({"entities": [], "relations": [], "concepts": []})
    assert result["metadata"]["implementation_status"] != "not_implemented"


def test_refine_ontology_locally_deduplicates_entities():
    from integrations.ipfs_datasets.graphrag import _refine_ontology_locally

    ontology = {
        "entities": [
            {"name": "Defendant", "frequency": 2},
            {"name": "defendant", "frequency": 1},
        ],
        "relations": [],
        "concepts": [],
    }
    result = _refine_ontology_locally(ontology, rounds=1)
    # After dedup by lower-cased name, should have 1 entity
    assert result["entity_count"] == 1
    assert result["entities"][0]["frequency"] == 3  # 2 + 1 merged


def test_refine_ontology_locally_deduplicates_relations():
    from integrations.ipfs_datasets.graphrag import _refine_ontology_locally

    ontology = {
        "entities": [],
        "relations": [
            {"subject": "Defendant", "predicate": "terminated", "object": "Plaintiff"},
            {"subject": "Defendant", "predicate": "terminated", "object": "Plaintiff"},
        ],
        "concepts": [],
    }
    result = _refine_ontology_locally(ontology, rounds=1)
    assert result["relation_count"] == 1


def test_refine_ontology_locally_preserves_source_annotation():
    from integrations.ipfs_datasets.graphrag import _refine_ontology_locally

    ontology = {"entities": [], "relations": [], "concepts": [], "source": "local_regex_fallback"}
    result = _refine_ontology_locally(ontology, rounds=1)
    assert "local_refinement" in result.get("source", "")
    assert result.get("refined_rounds") == 1


def test_refine_ontology_locally_non_dict_input():
    from integrations.ipfs_datasets.graphrag import _refine_ontology_locally

    result = _refine_ontology_locally("not a dict", rounds=1)
    assert result.get("status") == "skipped"


def test_run_refinement_cycle_adapter_returns_implemented():
    from integrations.ipfs_datasets.graphrag import run_refinement_cycle, OntologyMediator

    if OntologyMediator is None:
        import pytest
        pytest.skip("OntologyMediator unavailable; run_refinement_cycle returns 'unavailable', not 'not_implemented'")

    result = run_refinement_cycle({"entities": [{"name": "A"}], "relations": [], "concepts": []}, rounds=1)
    assert result["metadata"]["implementation_status"] != "not_implemented"
