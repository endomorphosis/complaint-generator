from __future__ import annotations

from integrations.ipfs_datasets.logic import run_hybrid_reasoning


def test_run_hybrid_reasoning_exposes_local_logic_snapshot_and_metadata() -> None:
    payload = {
        "predicates": [
            {
                "predicate_type": "claim_element",
                "claim_type": "retaliation",
                "predicate_id": "retaliation:1",
                "claim_element_id": "retaliation:1",
                "claim_element_text": "Protected activity",
                "coverage_status": "supported",
            },
            {
                "predicate_type": "support_trace",
                "claim_type": "retaliation",
                "predicate_id": "support:1",
                "support_ref": "QmEvidenceTemporal",
                "support_kind": "evidence",
                "text": "Email complaint chain",
                "claim_element_id": "retaliation:1",
            },
            {
                "predicate_type": "temporal_fact",
                "claim_type": "retaliation",
                "predicate_id": "temporal_fact:fact_1",
                "fact_id": "fact_1",
                "text": "Employee complained to HR.",
                "start_date": "2025-03-01",
                "end_date": "2025-03-01",
                "granularity": "day",
                "is_approximate": False,
                "is_range": False,
                "relative_markers": ["after_complaint"],
            },
        ]
    }

    result = run_hybrid_reasoning(payload)

    assert result["metadata"]["details"]["local_formal_logic_available"] is True
    assert result["metadata"]["details"]["local_formal_logic_path"] == "lib.formal_logic"
    assert result["metadata"]["details"]["local_logic_snapshot_frame_count"] == 3

    snapshot = result["result"]["local_logic_snapshot"]
    assert snapshot["frame_count"] == 3
    assert snapshot["frames"]["retaliation_1"]["slots"]["claim_type"] == [
        {"value": "retaliation", "sources": ["claim_element"]}
    ]
    assert snapshot["frames"]["support_1"]["slots"]["support_ref"] == [
        {"value": "QmEvidenceTemporal", "sources": ["support_trace"]}
    ]
    assert snapshot["frames"]["fact_1"]["slots"]["relative_marker"] == [
        {"value": "after_complaint", "sources": ["temporal_fact"]}
    ]