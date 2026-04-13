from complaint_phases import DeonticGraphBuilder, SupportMapBuilder


def test_support_map_builder_links_active_rules_to_facts_and_filings():
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
            },
            {
                "rule_id": "rule:deny",
                "modality": "prohibition",
                "predicate": "deny_review",
                "target_id": "action:deny_review",
                "target_label": "Deny informal review",
                "conditions": ["hearing_denied"],
            },
        ],
    )

    support_map = SupportMapBuilder().build_from_deontic_graph(
        graph,
        fact_catalog={
            "fact:requested_review": {
                "predicate": "requested_informal_review",
                "status": "verified",
                "source_ids": ["email:2026-03-04"],
            },
            "fact:notice_sent": {
                "predicate": "written_notice_sent",
                "status": "verified",
                "source_ids": ["notice:termination"],
            },
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
    entry = payload["entries"][0]
    assert entry["rule_id"] == "rule:review"
    assert entry["target_label"] == "Grant informal review"
    assert entry["authority_ids"] == ["24-cfr-982-555"]
    assert entry["evidence_ids"] == ["exhibit:A"]
    assert [fact["fact_id"] for fact in entry["facts"]] == ["fact:requested_review", "fact:notice_sent"]
    assert entry["filings"] == [
        {
            "filing_id": "motion:show-cause",
            "filing_type": "motion",
            "proposition": "Respondent had a duty to provide an informal review.",
        }
    ]
