from __future__ import annotations

from lib.formal_logic import FrameKnowledgeBase


def test_frame_knowledge_base_merges_duplicate_values_and_sources() -> None:
    kb = FrameKnowledgeBase()
    kb.add_fact("claim:1", "Protected activity", "claim_type", "retaliation", "claim_element")
    kb.add_fact("claim:1", "Protected activity", "claim_type", "retaliation", "review_pass")
    kb.add_fact("claim:1", "Protected activity", "support_ref", "QmEvidence123", "support_trace")

    payload = kb.to_dict()

    assert kb.frame_count() == 1
    assert payload["claim:1"]["name"] == "Protected activity"
    claim_type_entries = payload["claim:1"]["slots"]["claim_type"]
    assert claim_type_entries == [
        {"value": "retaliation", "sources": ["claim_element", "review_pass"]}
    ]
    assert payload["claim:1"]["slots"]["support_ref"] == [
        {"value": "QmEvidence123", "sources": ["support_trace"]}
    ]