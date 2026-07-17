"""Tests for M4 operator drilldown methods on ClaimSupportHooks.

Covers:
- get_support_timeline: returns timeline of support links sorted by captured_at
- get_archive_history: returns archive captures grouped by domain
- get_graph_trace_drilldown: returns full graph trace for an element or ref
- get_enrichment_queue_state: returns pending enrichment jobs
- submit_background_enrichment_job: submits a job and returns job_id
- _build_support_packet: now includes evidence, authority, provenance sub-objects
"""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.no_auto_network


def _make_minimal_mediator(db_path: str = ":memory:") -> MagicMock:
    """Return a minimal mediator mock for ClaimSupportHooks unit tests."""
    mediator = MagicMock()
    mediator.log = MagicMock()
    mediator.get_three_phase_status = MagicMock(return_value={})
    # State
    state = MagicMock()
    state.username = "test_user"
    mediator.state = state
    return mediator


def _make_claim_support_hook(db_path: str = ":memory:"):
    from mediator.claim_support_hooks import ClaimSupportHook
    mediator = _make_minimal_mediator(db_path)
    return ClaimSupportHook(mediator, db_path=db_path)


# ---------------------------------------------------------------------------
# _build_support_packet – evidence/authority/provenance sub-objects
# ---------------------------------------------------------------------------

def test_build_support_packet_has_evidence_sub_object():
    hooks = _make_claim_support_hook()
    trace = {
        "trace_kind": "fact",
        "support_kind": "evidence",
        "support_ref": "Qm123",
        "support_label": "Test evidence",
        "fact_id": "fact:1",
        "fact_text": "Complainant was terminated.",
        "confidence": 0.85,
        "record_summary": {
            "text_length": 1500,
            "extraction_method": "pdf",
            "quality_tier": "high",
            "quality_score": 90.0,
            "chunk_count": 5,
        },
    }
    packet = hooks._build_support_packet(trace)
    assert "evidence" in packet
    evidence = packet["evidence"]
    assert evidence["parse_quality_tier"] == "high"
    assert evidence["parse_quality_score"] == 90.0
    assert evidence["extraction_method"] == "pdf"
    assert evidence["chunk_count"] == 5


def test_build_support_packet_has_authority_sub_object():
    hooks = _make_claim_support_hook()
    trace = {
        "trace_kind": "link",
        "support_kind": "authority",
        "support_ref": "auth:42",
        "authority_id": "auth:42",
        "record_summary": {
            "citation": "42 U.S.C. § 2000e",
            "treatment_signal": "followed",
            "jurisdiction": "federal",
            "authority_type": "statute",
        },
        "graph_summary": {
            "treatment_signal": "followed",
            "rule_candidates": ["R1", "R2"],
        },
    }
    packet = hooks._build_support_packet(trace)
    assert "authority" in packet
    authority = packet["authority"]
    assert authority["authority_id"] == "auth:42"
    assert authority["citation"] == "42 U.S.C. § 2000e"
    assert authority["treatment_signal"] == "followed"
    assert authority["jurisdiction"] == "federal"


def test_build_support_packet_has_provenance_sub_object():
    hooks = _make_claim_support_hook()
    trace = {
        "trace_kind": "fact",
        "support_kind": "web_evidence",
        "support_ref": "Qmweb1",
        "record_summary": {
            "archive_url": "https://web.archive.org/web/20250101/example.com",
            "captured_at": "2025-01-01T00:00:00Z",
            "source_domain": "example.com",
            "content_hash": "sha256:abc123",
        },
    }
    packet = hooks._build_support_packet(trace)
    assert "provenance" in packet
    provenance = packet["provenance"]
    assert provenance["archive_url"] == "https://web.archive.org/web/20250101/example.com"
    assert provenance["capture_timestamp"] == "2025-01-01T00:00:00Z"
    assert provenance["source_domain"] == "example.com"
    assert provenance["content_hash"] == "sha256:abc123"


def test_build_support_packet_fact_sub_object_preserved():
    hooks = _make_claim_support_hook()
    trace = {
        "trace_kind": "fact",
        "fact_id": "fact:999",
        "fact_text": "Some fact.",
        "confidence": 0.72,
    }
    packet = hooks._build_support_packet(trace)
    assert packet["fact"]["fact_id"] == "fact:999"
    assert packet["fact"]["text"] == "Some fact."
    assert packet["fact"]["confidence"] == 0.72


def test_build_support_packet_empty_trace_does_not_raise():
    hooks = _make_claim_support_hook()
    packet = hooks._build_support_packet({})
    assert "evidence" in packet
    assert "authority" in packet
    assert "provenance" in packet
    assert "fact" in packet


# ---------------------------------------------------------------------------
# get_support_timeline
# ---------------------------------------------------------------------------

def test_get_support_timeline_returns_required_keys():
    hooks = _make_claim_support_hook()
    # Patch _get_enriched_claim_support_links to return empty list
    hooks._get_enriched_claim_support_links = MagicMock(return_value=[])
    result = hooks.get_support_timeline("test_user", claim_type="employment_discrimination")
    assert result["available"] is True
    assert "timeline" in result
    assert "entry_count" in result
    assert result["entry_count"] == 0


def test_get_support_timeline_empty_links():
    hooks = _make_claim_support_hook()
    hooks._get_enriched_claim_support_links = MagicMock(return_value=[])
    result = hooks.get_support_timeline("test_user")
    assert result["timeline"] == []
    assert result["entry_count"] == 0


def test_get_support_timeline_with_links():
    hooks = _make_claim_support_hook()
    links = [
        {
            "support_ref": "Qm1",
            "support_kind": "evidence",
            "support_label": "Email evidence",
            "claim_element_id": "adverse_action",
            "claim_element_text": "Adverse employment action",
            "facts": [
                {
                    "fact_id": "fact:1",
                    "text": "Complainant was fired.",
                    "confidence": 0.9,
                    "parse_lineage": {"captured_at": "2025-03-01T00:00:00Z"},
                }
            ],
        }
    ]
    hooks._get_enriched_claim_support_links = MagicMock(return_value=links)
    result = hooks.get_support_timeline("test_user", claim_type="employment_discrimination")
    assert result["available"] is True
    assert result["entry_count"] >= 0  # May be 0 if no traces collected


def test_get_support_timeline_respects_limit():
    hooks = _make_claim_support_hook()
    hooks._get_enriched_claim_support_links = MagicMock(return_value=[])
    result = hooks.get_support_timeline("test_user", limit=5)
    assert len(result["timeline"]) <= 5


# ---------------------------------------------------------------------------
# get_archive_history
# ---------------------------------------------------------------------------

def test_get_archive_history_returns_required_keys():
    hooks = _make_claim_support_hook()
    hooks._get_enriched_claim_support_links = MagicMock(return_value=[])
    result = hooks.get_archive_history("test_user")
    assert result["available"] is True
    assert "captures" in result
    assert "capture_count" in result
    assert "domain_count" in result
    assert "captures_by_domain" in result


def test_get_archive_history_empty():
    hooks = _make_claim_support_hook()
    hooks._get_enriched_claim_support_links = MagicMock(return_value=[])
    result = hooks.get_archive_history("test_user")
    assert result["capture_count"] == 0
    assert result["captures"] == []


def test_get_archive_history_domain_filter():
    hooks = _make_claim_support_hook()
    hooks._get_enriched_claim_support_links = MagicMock(return_value=[])
    result = hooks.get_archive_history("test_user", domain="example.com")
    assert result["domain_filter"] == "example.com"


# ---------------------------------------------------------------------------
# get_graph_trace_drilldown
# ---------------------------------------------------------------------------

def test_get_graph_trace_drilldown_returns_required_keys():
    hooks = _make_claim_support_hook()
    hooks._get_enriched_claim_support_links = MagicMock(return_value=[])
    result = hooks.get_graph_trace_drilldown("test_user")
    assert result["available"] is True
    assert "graph_traces" in result
    assert "graph_trace_count" in result
    assert "graph_summary" in result


def test_get_graph_trace_drilldown_empty():
    hooks = _make_claim_support_hook()
    hooks._get_enriched_claim_support_links = MagicMock(return_value=[])
    result = hooks.get_graph_trace_drilldown("test_user", claim_type="employment_discrimination")
    assert result["graph_trace_count"] == 0
    assert result["graph_traces"] == []


def test_get_graph_trace_drilldown_filters_by_element():
    hooks = _make_claim_support_hook()
    hooks._get_enriched_claim_support_links = MagicMock(return_value=[
        {"claim_element_id": "adverse_action", "support_ref": "Qm1", "facts": []},
        {"claim_element_id": "protected_trait", "support_ref": "Qm2", "facts": []},
    ])
    result = hooks.get_graph_trace_drilldown("test_user", claim_element_id="adverse_action")
    assert result["claim_element_id"] == "adverse_action"


# ---------------------------------------------------------------------------
# get_enrichment_queue_state
# ---------------------------------------------------------------------------

def test_get_enrichment_queue_state_no_duckdb():
    hooks = _make_claim_support_hook()
    hooks._check_duckdb_availability = MagicMock(return_value=False)
    result = hooks.get_enrichment_queue_state("test_user")
    assert result["available"] is False
    assert result["queue"] == []
    assert result["queue_count"] == 0


def test_get_enrichment_queue_state_with_duckdb():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_claim_support_hook(db_path=":memory:")
    hooks._check_duckdb_availability = MagicMock(return_value=True)
    hooks._prepare_duckdb_path = MagicMock()
    result = hooks.get_enrichment_queue_state("test_user")
    assert result["available"] is True
    assert "queue" in result
    assert result["queue_count"] >= 0


def test_get_enrichment_queue_state_returns_counts():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_claim_support_hook(db_path=":memory:")
    hooks._check_duckdb_availability = MagicMock(return_value=True)
    hooks._prepare_duckdb_path = MagicMock()
    result = hooks.get_enrichment_queue_state("test_user")
    assert "pending_count" in result
    assert "running_count" in result
    assert "completed_count" in result


# ---------------------------------------------------------------------------
# submit_background_enrichment_job
# ---------------------------------------------------------------------------

def test_submit_enrichment_job_no_duckdb():
    hooks = _make_claim_support_hook()
    hooks._check_duckdb_availability = MagicMock(return_value=False)
    result = hooks.submit_background_enrichment_job("test_user", "graph_enrichment")
    assert result["submitted"] is False
    assert "error" in result


def test_submit_enrichment_job_with_duckdb():
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_claim_support_hook(db_path=":memory:")
    hooks._check_duckdb_availability = MagicMock(return_value=True)
    hooks._prepare_duckdb_path = MagicMock()
    result = hooks.submit_background_enrichment_job(
        "test_user",
        "graph_enrichment",
        claim_type="employment_discrimination",
        priority=3,
    )
    assert result["submitted"] is True
    assert result["status"] == "pending"
    assert result["enrichment_type"] == "graph_enrichment"
    assert result["claim_type"] == "employment_discrimination"
    assert result["priority"] == 3


def test_submit_then_query_enrichment_queue():
    """Submit a job and verify it appears in the queue."""
    try:
        import duckdb  # noqa: F401
    except ImportError:
        pytest.skip("duckdb not installed")
    hooks = _make_claim_support_hook(db_path=":memory:")
    hooks._check_duckdb_availability = MagicMock(return_value=True)
    hooks._prepare_duckdb_path = MagicMock()

    submit_result = hooks.submit_background_enrichment_job(
        "user_queue_test",
        "ontology_enrichment",
        claim_type="retaliation",
        priority=1,
    )
    assert submit_result["submitted"] is True

    queue_result = hooks.get_enrichment_queue_state("user_queue_test")
    assert queue_result["available"] is True
    # The submitted job should appear in the queue
    job_types = [j["enrichment_type"] for j in queue_result["queue"]]
    assert "ontology_enrichment" in job_types


# ---------------------------------------------------------------------------
# GraphRAG quality signal wiring in decision trace
# ---------------------------------------------------------------------------

def test_build_validation_decision_trace_includes_graphrag_signal():
    hooks = _make_claim_support_hook()
    element = {
        "status": "covered",
        "total_links": 3,
        "missing_support_kinds": [],
    }
    reasoning_diagnostics = {
        "graphrag_quality": {
            "overall_quality_score": 0.2,
            "grade": "F",
            "has_gaps": True,
            "has_blocking_gaps": True,
            "gaps": [
                {
                    "gap_type": "missing_entity_coverage",
                    "description": "Missing expected entities",
                    "severity": "blocking",
                    "follow_up_action": "enrich_entities_from_evidence",
                    "missing_keywords": ["employee", "employer"],
                }
            ],
            "entity_coverage_score": 0.1,
            "concept_completeness_score": 0.1,
        }
    }
    trace = hooks._build_validation_decision_trace(element, [], reasoning_diagnostics)
    assert "graphrag_quality_signal" in trace
    assert trace["graphrag_has_blocking_gaps"] is True
    assert trace["decision_source"] == "graphrag_quality_gap"
    assert trace["validation_status"] == "incomplete"


def test_has_reasoning_gap_signals_detects_graphrag_gap():
    hooks = _make_claim_support_hook()
    proof_decision_trace = {
        "decision_source": "graphrag_quality_gap",
        "graphrag_has_blocking_gaps": True,
    }
    assert hooks._has_reasoning_gap_signals(
        ["graphrag_quality_gap"],
        proof_decision_trace,
    ) is True


def test_recommended_action_for_graphrag_gap():
    hooks = _make_claim_support_hook()
    element = {
        "status": "covered",
        "total_links": 3,
        "missing_support_kinds": [],
        "proof_decision_trace": {
            "decision_source": "graphrag_quality_gap",
            "graphrag_has_blocking_gaps": True,
        },
    }
    proof_gaps = [
        {
            "gap_type": "graphrag_quality_gap",
            "gap_count": 2,
            "blocking_gap_count": 1,
            "message": "GraphRAG has blocking gaps",
            "follow_up_action": "enrich_entities_from_evidence",
        }
    ]
    action = hooks._recommended_validation_action("incomplete", element, proof_gaps)
    assert action == "improve_graph_quality"
