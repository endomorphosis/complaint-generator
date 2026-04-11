from lib.deontic_logic import DeonticGraphBuilder
from lib.support_map import SupportMapBuilder


def test_lib_support_map_builder_links_active_rules_to_facts_and_filings() -> None:
    graph = DeonticGraphBuilder().build_from_findings(
        actor_label="Housing Authority",
        findings={
            "requested_review": True,
            "notice_sent": True,
            "hearing_denied": False,
        },
        rule_templates=[
            {
                "rule_id": "rule:review",
                "modality": "obligation",
                "predicate": "grant_review",
                "target_id": "action:grant_review",
                "target_label": "Grant informal review",
                "conditions": ["requested_review", "notice_sent"],
                "authority_ids": ["24-cfr-982-555"],
                "evidence_ids": ["exhibit:A"],
            }
        ],
    )

    support_map = SupportMapBuilder().build_from_deontic_graph(
        graph,
        fact_catalog={
            "fact:requested_review": {"predicate": "requested_informal_review", "status": "verified", "source_ids": ["email:2026-03-04"]},
            "fact:notice_sent": {"predicate": "written_notice_sent", "status": "verified", "source_ids": ["notice:termination"]},
        },
        filing_map={
            "rule:review": [
                {
                    "filing_id": "motion:show-cause",
                    "filing_type": "motion",
                    "proposition": "Respondent had a duty to provide an informal review.",
                }
            ]
        },
    )

    payload = support_map.to_dict()
    assert payload["entry_count"] == 1
    assert payload["entries"][0]["authority_ids"] == ["24-cfr-982-555"]
    assert payload["entries"][0]["filings"][0]["filing_id"] == "motion:show-cause"