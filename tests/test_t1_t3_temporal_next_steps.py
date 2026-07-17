"""
T1 / T3 / T5 / T6 temporal timeline proof regression suite.

Covers:
  T1 – inferred date-anchor relations in build_temporal_relation_registry
  T1 – issue category normalization (temporal_ prefix stripping) in build_temporal_issue_registry
  T3 – formula certainty annotation in proof bundle theorem_exports
  T3 – proof_bundles keyed by claim_type:element_id in claim review output
  T5 – _build_chronology_blocker_summary gates on temporal_rule_profile_failed_element_count
"""
from __future__ import annotations

import types
from typing import Any, Dict, List

from complaint_phases.intake_case_file import (
    build_temporal_issue_registry,
    build_temporal_relation_registry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _anchored_fact(fact_id: str, start_date: str, element_tags: List[str]) -> Dict[str, Any]:
    return {
        "fact_id": fact_id,
        "fact_type": "timeline",
        "text": f"Event {fact_id}",
        "element_tags": element_tags,
        "temporal_context": {"start_date": start_date, "raw_text": start_date},
        "claim_types": ["retaliation"],
    }


def _make_claim_support_hook_stub():
    """Return a minimal stub that exposes the pure utility methods needed by T3 tests.

    Uses a SimpleNamespace bound to the real implementations so tests do not
    reach the complex database and mediator initialization path.
    """
    from mediator import claim_support_hooks as _hooks_mod

    # Grab the unbound method implementation so we can bind it to a namespace.
    real_normalize = _hooks_mod.ClaimSupportHook._normalize_reasoning_key
    real_build_bundle = _hooks_mod.ClaimSupportHook._build_temporal_proof_bundle

    stub = types.SimpleNamespace()
    stub._normalize_reasoning_key = lambda value: real_normalize(stub, value)
    stub._build_temporal_proof_bundle = lambda *a, **kw: real_build_bundle(stub, *a, **kw)
    return stub


def _make_document_builder_stub():
    """Return a minimal stub exposing _build_chronology_blocker_summary."""
    from document_pipeline import FormalComplaintDocumentBuilder

    real_method = FormalComplaintDocumentBuilder._build_chronology_blocker_summary

    stub = types.SimpleNamespace()
    stub._build_chronology_blocker_summary = lambda **kw: real_method(stub, **kw)
    return stub


# ---------------------------------------------------------------------------
# T1: Inferred relation generation from date anchors
# ---------------------------------------------------------------------------

def test_t1_inferred_before_relation_generated_when_no_explicit_relation():
    """When fact A has an earlier date than fact B, a 'before' relation is inferred."""
    facts = [
        _anchored_fact("pa_001", "2023-01-15", ["protected_activity"]),
        _anchored_fact("aa_001", "2023-07-20", ["adverse_action"]),
    ]
    registry = build_temporal_relation_registry(facts, [])

    assert len(registry) == 1
    rel = registry[0]
    assert rel["source_fact_id"] == "pa_001"
    assert rel["target_fact_id"] == "aa_001"
    assert rel["relation_type"] == "before"
    assert rel["inference_mode"] == "derived_from_date_anchors"
    assert rel["registry_version"] == "temporal_relation_registry.v1"


def test_t1_inferred_same_time_relation_when_dates_equal():
    """When two facts share the same start_date, a 'same_time' relation is inferred."""
    facts = [
        _anchored_fact("aa_001", "2023-06-01", ["adverse_action"]),
        _anchored_fact("aa_002", "2023-06-01", ["adverse_action"]),
    ]
    registry = build_temporal_relation_registry(facts, [])

    assert len(registry) == 1
    rel = registry[0]
    assert rel["relation_type"] == "same_time"
    assert rel["inference_mode"] == "derived_from_date_anchors"


def test_t1_explicit_relation_suppresses_inferred_pair():
    """An explicit relation for a pair prevents generation of an inferred duplicate."""
    facts = [
        _anchored_fact("pa_001", "2023-01-01", ["protected_activity"]),
        _anchored_fact("aa_001", "2023-09-01", ["adverse_action"]),
    ]
    explicit = [
        {
            "relation_id": "explicit_rel_001",
            "source_fact_id": "pa_001",
            "target_fact_id": "aa_001",
            "relation_type": "before",
        }
    ]
    registry = build_temporal_relation_registry(facts, explicit)

    assert len(registry) == 1
    assert registry[0]["inference_mode"] == "explicit"
    assert registry[0]["relation_id"] == "explicit_rel_001"


def test_t1_explicit_relations_marked_as_explicit():
    """Relations from the timeline_relations input carry inference_mode='explicit'."""
    facts = [
        _anchored_fact("f_a", "2023-03-01", ["protected_activity"]),
        _anchored_fact("f_b", "2023-11-01", ["adverse_action"]),
    ]
    explicit = [
        {
            "relation_id": "r_001",
            "source_fact_id": "f_a",
            "target_fact_id": "f_b",
            "relation_type": "before",
        }
    ]
    registry = build_temporal_relation_registry(facts, explicit)
    assert registry[0]["inference_mode"] == "explicit"


def test_t1_three_facts_two_inferred_relations():
    """Three anchored facts with distinct dates generate the correct inferred pairs."""
    facts = [
        _anchored_fact("e1", "2023-01-01", ["protected_activity"]),
        _anchored_fact("e2", "2023-04-01", ["causal_connection"]),
        _anchored_fact("e3", "2023-09-01", ["adverse_action"]),
    ]
    registry = build_temporal_relation_registry(facts, [])
    assert len(registry) == 3
    relation_types = {r["relation_type"] for r in registry}
    assert relation_types == {"before"}
    for r in registry:
        assert r["inference_mode"] == "derived_from_date_anchors"


def test_t1_inferred_relation_carries_element_tags_from_both_facts():
    """Inferred relation merges element_tags from both source and target facts."""
    facts = [
        _anchored_fact("pa_001", "2023-01-01", ["protected_activity"]),
        _anchored_fact("aa_001", "2023-06-01", ["adverse_action"]),
    ]
    registry = build_temporal_relation_registry(facts, [])
    rel = registry[0]
    assert "protected_activity" in rel["element_tags"]
    assert "adverse_action" in rel["element_tags"]


def test_t1_no_inferred_relations_without_anchors():
    """Facts without start_date do not generate inferred relations."""
    facts = [
        {
            "fact_id": "f1",
            "fact_type": "timeline",
            "text": "Event without date",
            "element_tags": ["protected_activity"],
            "temporal_context": {"relative_markers": ["some time ago"], "raw_text": "some time ago"},
            "claim_types": ["retaliation"],
        },
        {
            "fact_id": "f2",
            "fact_type": "timeline",
            "text": "Another event without date",
            "element_tags": ["adverse_action"],
            "temporal_context": {"relative_markers": ["later"], "raw_text": "later"},
            "claim_types": ["retaliation"],
        },
    ]
    registry = build_temporal_relation_registry(facts, [])
    assert len(registry) == 0


# ---------------------------------------------------------------------------
# T1: Issue category normalization
# ---------------------------------------------------------------------------

def test_t1_temporal_contradictory_dates_prefix_stripped():
    """`temporal_contradictory_dates` is normalised to `contradictory_dates`."""
    contradiction_queue = [
        {
            "contradiction_id": "c_001",
            "category": "temporal_contradictory_dates",
            "summary": "Date conflict between records",
        }
    ]
    registry = build_temporal_issue_registry([], contradiction_queue)
    assert len(registry) == 1
    assert registry[0]["issue_type"] == "contradictory_dates"
    assert registry[0]["category"] == "contradictory_dates"


def test_t1_temporal_limitations_risk_prefix_stripped():
    """`temporal_limitations_risk` is normalised to `limitations_risk`."""
    contradiction_queue = [
        {
            "contradiction_id": "c_002",
            "category": "temporal_limitations_risk",
            "summary": "Filing deadline risk",
        }
    ]
    registry = build_temporal_issue_registry([], contradiction_queue)
    assert len(registry) == 1
    assert registry[0]["issue_type"] == "limitations_risk"


def test_t1_temporal_missing_anchor_prefix_stripped():
    """`temporal_missing_anchor` is normalised to `missing_anchor`."""
    contradiction_queue = [
        {
            "contradiction_id": "c_003",
            "category": "temporal_missing_anchor",
            "summary": "No date anchor",
        }
    ]
    registry = build_temporal_issue_registry([], contradiction_queue)
    assert len(registry) == 1
    assert registry[0]["issue_type"] == "missing_anchor"


def test_t1_non_temporal_category_excluded():
    """Contradiction entries without a `temporal` prefix are excluded."""
    contradiction_queue = [
        {"contradiction_id": "c_x", "category": "other_contradiction", "summary": "Not temporal"},
    ]
    registry = build_temporal_issue_registry([], contradiction_queue)
    assert len(registry) == 0


def test_t1_canonical_issue_type_passthrough():
    """A category that is already canonical (e.g. `temporal_reverse_before`) is preserved."""
    contradiction_queue = [
        {
            "contradiction_id": "c_004",
            "category": "temporal_reverse_before",
            "summary": "Adverse action predates protected activity",
        }
    ]
    registry = build_temporal_issue_registry([], contradiction_queue)
    assert len(registry) == 1
    assert registry[0]["issue_type"] == "temporal_reverse_before"


def test_t1_normalised_issue_type_used_in_evaluate_temporal_rule_profile():
    """Normalised `contradictory_dates` from the registry is detected by evaluate_temporal_rule_profile."""
    from complaint_analysis.temporal_rule_profiles import evaluate_temporal_rule_profile

    contradiction_queue = [
        {
            "contradiction_id": "c_100",
            "category": "temporal_contradictory_dates",
            "summary": "Conflicting dates",
        }
    ]
    issue_registry = build_temporal_issue_registry([], contradiction_queue)
    # Map registry records into the temporal_issues list shape the rule profile expects.
    temporal_issues = [{"issue_type": r["issue_type"]} for r in issue_registry]

    element = {"element_id": "causal_connection", "element_text": "causal connection"}
    # Provide enough facts to give a satisfied base status, then let contradictory_dates downgrade it.
    temporal_context = {
        "temporal_facts": [
            {
                "fact_id": "pa_001",
                "element_tags": ["protected_activity"],
                "affected_element_ids": ["protected_activity"],
                "temporal_context": {"start_date": "2023-01-01"},
            },
            {
                "fact_id": "aa_001",
                "element_tags": ["adverse_action"],
                "affected_element_ids": ["adverse_action"],
                "temporal_context": {"start_date": "2023-06-01"},
            },
        ],
        "temporal_relations": [
            {
                "relation_id": "rel_001",
                "source_fact_id": "pa_001",
                "target_fact_id": "aa_001",
                "relation_type": "before",
            }
        ],
        "temporal_issues": temporal_issues,
    }
    profile = evaluate_temporal_rule_profile("retaliation", element, temporal_context)
    assert profile["has_contradictory_dates"] is True
    # A satisfied causal_connection is downgraded to partial when contradictory dates are present.
    assert profile["status"] == "partial"


# ---------------------------------------------------------------------------
# T3: Formula certainty annotation in theorem_exports
# ---------------------------------------------------------------------------

def test_t3_certain_fact_formulas_annotated_as_certain():
    """TDFOL formulas for directly asserted facts are marked 'certain'."""
    hooks = _make_claim_support_hook_stub()

    element = {"element_id": "causal_connection", "element_text": "causal connection"}
    temporal_context: Dict[str, Any] = {
        "temporal_facts": [
            {
                "fact_id": "pa_001",
                "element_tags": ["protected_activity"],
                "temporal_context": {"start_date": "2023-01-01"},
                "timeline_anchor_ids": [],
                "source_artifact_ids": [],
                "testimony_record_ids": [],
            },
            {
                "fact_id": "aa_001",
                "element_tags": ["adverse_action"],
                "temporal_context": {"start_date": "2023-06-01"},
                "timeline_anchor_ids": [],
                "source_artifact_ids": [],
                "testimony_record_ids": [],
            },
        ],
        "temporal_relations": [
            {
                "relation_id": "rel_001",
                "source_fact_id": "pa_001",
                "target_fact_id": "aa_001",
                "relation_type": "before",
                "inference_mode": "explicit",
            }
        ],
        "temporal_issues": [],
        "consistency_summary": {},
    }
    from complaint_analysis.temporal_rule_profiles import evaluate_temporal_rule_profile
    profile = evaluate_temporal_rule_profile("retaliation", element, temporal_context)
    bundle = hooks._build_temporal_proof_bundle("retaliation", element, temporal_context, profile)

    exports = bundle.get("theorem_exports", {})
    tdfol_certainties = exports.get("tdfol_formula_certainties", {})
    # Fact-assertion formulas must be certain.
    pa_formula = "ProtectedActivity(pa_001)"
    aa_formula = "AdverseAction(aa_001)"
    assert pa_formula in tdfol_certainties
    assert tdfol_certainties[pa_formula] == "certain"
    assert aa_formula in tdfol_certainties
    assert tdfol_certainties[aa_formula] == "certain"


def test_t3_inferred_relation_formula_annotated_as_inferred():
    """TDFOL formulas for inferred ordering relations are marked 'inferred'."""
    hooks = _make_claim_support_hook_stub()

    element = {"element_id": "causal_connection", "element_text": "causal connection"}
    temporal_context: Dict[str, Any] = {
        "temporal_facts": [
            {
                "fact_id": "pa_001",
                "element_tags": ["protected_activity"],
                "temporal_context": {"start_date": "2023-01-01"},
                "timeline_anchor_ids": [],
                "source_artifact_ids": [],
                "testimony_record_ids": [],
            },
            {
                "fact_id": "aa_001",
                "element_tags": ["adverse_action"],
                "temporal_context": {"start_date": "2023-06-01"},
                "timeline_anchor_ids": [],
                "source_artifact_ids": [],
                "testimony_record_ids": [],
            },
        ],
        "temporal_relations": [
            {
                "relation_id": "inferred_rel_001",
                "source_fact_id": "pa_001",
                "target_fact_id": "aa_001",
                "relation_type": "before",
                "inference_mode": "derived_from_date_anchors",
            }
        ],
        "temporal_issues": [],
        "consistency_summary": {},
    }
    from complaint_analysis.temporal_rule_profiles import evaluate_temporal_rule_profile
    profile = evaluate_temporal_rule_profile("retaliation", element, temporal_context)
    bundle = hooks._build_temporal_proof_bundle("retaliation", element, temporal_context, profile)

    exports = bundle.get("theorem_exports", {})
    tdfol_certainties = exports.get("tdfol_formula_certainties", {})
    before_formula = "Before(pa_001,aa_001)"
    assert before_formula in tdfol_certainties
    assert tdfol_certainties[before_formula] == "inferred"


def test_t3_dcec_formula_certainties_present():
    """DCEC Happens() formulas are included in dcec_formula_certainties."""
    hooks = _make_claim_support_hook_stub()

    element = {"element_id": "adverse_action", "element_text": "adverse action"}
    temporal_context: Dict[str, Any] = {
        "temporal_facts": [
            {
                "fact_id": "aa_001",
                "element_tags": ["adverse_action"],
                "temporal_context": {"start_date": "2023-06-01"},
                "timeline_anchor_ids": [],
                "source_artifact_ids": [],
                "testimony_record_ids": [],
            },
        ],
        "temporal_relations": [],
        "temporal_issues": [],
        "consistency_summary": {},
    }
    from complaint_analysis.temporal_rule_profiles import evaluate_temporal_rule_profile
    profile = evaluate_temporal_rule_profile("retaliation", element, temporal_context)
    bundle = hooks._build_temporal_proof_bundle("retaliation", element, temporal_context, profile)

    exports = bundle.get("theorem_exports", {})
    dcec_certainties = exports.get("dcec_formula_certainties", {})
    assert len(dcec_certainties) >= 1
    for cert in dcec_certainties.values():
        assert cert == "certain"


# ---------------------------------------------------------------------------
# T3: proof_bundles keyed by claim_type:element_id in claim review
# ---------------------------------------------------------------------------

def test_t3_proof_bundles_keyed_by_claim_element():
    """summarize_claim_reasoning_validation includes proof_bundles dict."""
    from claim_support_review import summarize_claim_reasoning_review

    element = {
        "element_id": "causal_connection",
        "element_text": "causal connection",
        "validation_status": "accepted",
        "reasoning_diagnostics": {
            "temporal_summary": {},
            "temporal_rule_profile": {
                "available": True,
                "evaluated": True,
                "profile_id": "retaliation_temporal_profile_v1",
                "rule_frame_id": "retaliation_temporal_frame",
                "status": "partial",
                "blocking_reasons": ["Missing ordering."],
                "warnings": [],
                "recommended_follow_ups": [],
                "matched_fact_ids": [],
                "matched_relation_ids": [],
            },
            "temporal_proof_bundle": {
                "proof_bundle_id": "retaliation:causal_connection:retaliation_temporal_profile_v1",
                "status": "partial",
                "rule_frame_id": "retaliation_temporal_frame",
                "temporal_fact_ids": [],
                "temporal_relation_ids": [],
                "temporal_issue_ids": [],
                "theorem_exports": {
                    "tdfol_formulas": ["ProtectedActivity(pa_001)"],
                    "dcec_formulas": [],
                    "tdfol_formula_certainties": {"ProtectedActivity(pa_001)": "certain"},
                    "dcec_formula_certainties": {},
                    "theorem_export_metadata": {
                        "proof_bundle_id": "retaliation:causal_connection:retaliation_temporal_profile_v1",
                        "rule_frame_id": "retaliation_temporal_frame",
                        "chronology_blocked": True,
                        "chronology_task_count": 1,
                        "unresolved_temporal_issue_ids": [],
                        "event_ids": [],
                        "temporal_fact_ids": [],
                        "temporal_relation_ids": [],
                        "timeline_anchor_ids": [],
                        "timeline_issue_ids": [],
                        "temporal_issue_ids": [],
                        "missing_temporal_predicates": [],
                        "required_provenance_kinds": [],
                        "temporal_proof_bundle_ids": [
                            "retaliation:causal_connection:retaliation_temporal_profile_v1"
                        ],
                        "temporal_proof_objectives": ["retaliation_temporal_frame"],
                        "claim_type": "retaliation",
                        "claim_element_id": "causal_connection",
                        "contract_version": "claim_support_temporal_handoff_v1",
                    },
                },
            },
            "adapter_statuses": {},
        },
    }

    claim_validation = {
        "claim_type": "retaliation",
        "elements": [element],
        "temporal_issue_registry": [],
    }
    result = summarize_claim_reasoning_review(claim_validation)

    assert "proof_bundles" in result
    pb = result["proof_bundles"]
    assert isinstance(pb, dict)
    assert len(pb) == 1
    bundle_key = "retaliation:causal_connection"
    assert bundle_key in pb
    stored = pb[bundle_key]
    assert stored["proof_bundle_id"] == "retaliation:causal_connection:retaliation_temporal_profile_v1"
    assert stored["rule_frame_id"] == "retaliation_temporal_frame"
    assert stored["status"] == "partial"
    assert "ProtectedActivity(pa_001)" in stored["tdfol_preview"]


# ---------------------------------------------------------------------------
# T5: _build_chronology_blocker_summary gates on temporal rule profile failures
# ---------------------------------------------------------------------------

def test_t5_chronology_blocked_when_rule_profile_fails():
    """chronology_blocked is True when temporal_rule_profile_failed_element_count > 0."""
    pipeline = _make_document_builder_stub()

    claim_reasoning_review = {
        "retaliation": {
            "temporal_rule_profile_failed_element_count": 1,
            "temporal_rule_profile_partial_element_count": 0,
            "proof_bundles": {
                "retaliation:causal_connection": {
                    "proof_bundle_id": "retaliation:causal_connection:retaliation_temporal_profile_v1",
                    "status": "failed",
                    "rule_frame_id": "retaliation_temporal_frame",
                }
            },
        }
    }
    intake_case_summary = {
        "claim_support_packet_summary": {
            "proof_readiness_score": 0.5,
            "claim_support_unresolved_temporal_issue_count": 0,
            "claim_support_unresolved_temporal_issue_ids": [],
            "temporal_gap_task_count": 0,
        },
        "alignment_task_summary": {},
        "claim_reasoning_review": claim_reasoning_review,
    }
    result = pipeline._build_chronology_blocker_summary(
        intake_case_summary=intake_case_summary,
        claim_support_temporal_handoff={},
    )

    assert result["chronology_blocked"] is True
    assert result["temporal_rule_profile_failed_element_count"] == 1
    assert "failed temporal rule profile" in result["summary"]
    assert "retaliation_temporal_frame" in result.get("failed_rule_frame_ids", [])


def test_t5_chronology_not_blocked_when_all_profiles_satisfied():
    """chronology_blocked is False when no temporal rule profile failures or issues."""
    pipeline = _make_document_builder_stub()

    intake_case_summary = {
        "claim_support_packet_summary": {
            "proof_readiness_score": 0.9,
            "claim_support_unresolved_temporal_issue_count": 0,
            "claim_support_unresolved_temporal_issue_ids": [],
            "temporal_gap_task_count": 0,
        },
        "alignment_task_summary": {},
        "claim_reasoning_review": {
            "retaliation": {
                "temporal_rule_profile_failed_element_count": 0,
                "temporal_rule_profile_partial_element_count": 0,
                "proof_bundles": {},
            }
        },
    }
    result = pipeline._build_chronology_blocker_summary(
        intake_case_summary=intake_case_summary,
        claim_support_temporal_handoff={},
    )
    # No failures → empty summary (or not blocked)
    assert not result or result.get("chronology_blocked") is False


def test_t5_failed_rule_frame_ids_present_in_summary():
    """failed_rule_frame_ids lists all rule frame IDs from failed/partial proof bundles."""
    pipeline = _make_document_builder_stub()

    claim_reasoning_review = {
        "retaliation": {
            "temporal_rule_profile_failed_element_count": 2,
            "temporal_rule_profile_partial_element_count": 0,
            "proof_bundles": {
                "retaliation:causal_connection": {
                    "proof_bundle_id": "retaliation:causal_connection:p",
                    "status": "failed",
                    "rule_frame_id": "retaliation_temporal_frame",
                },
                "retaliation:protected_activity": {
                    "proof_bundle_id": "retaliation:protected_activity:p",
                    "status": "partial",
                    "rule_frame_id": "retaliation_temporal_frame",
                },
            },
        }
    }
    intake_case_summary = {
        "claim_support_packet_summary": {
            "proof_readiness_score": 0.4,
            "claim_support_unresolved_temporal_issue_count": 0,
            "claim_support_unresolved_temporal_issue_ids": [],
            "temporal_gap_task_count": 0,
        },
        "alignment_task_summary": {},
        "claim_reasoning_review": claim_reasoning_review,
    }
    result = pipeline._build_chronology_blocker_summary(
        intake_case_summary=intake_case_summary,
        claim_support_temporal_handoff={},
    )
    assert result["chronology_blocked"] is True
    frame_ids = result.get("failed_rule_frame_ids", [])
    assert "retaliation_temporal_frame" in frame_ids
    # Each unique rule_frame_id appears once even if multiple bundles share it.
    assert frame_ids.count("retaliation_temporal_frame") == 1
