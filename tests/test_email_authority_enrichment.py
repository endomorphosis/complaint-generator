import json
from pathlib import Path

from complaint_generator.email_authority_enrichment import (
    build_email_authority_query_plan,
    enrich_email_timeline_authorities,
)


def test_build_email_authority_query_plan_uses_topics_and_clackamas_context():
    handoff = {
        "claim_type": "retaliation",
        "claim_element_id": "causation",
        "canonical_facts": [
            {
                "participants": ["AFerron@clackamas.us", "starworks5@gmail.com"],
            }
        ],
        "claim_support_temporal_handoff": {
            "topic_summary": {
                "fraud_household": {"count": 5},
                "hcv_orientation": {"count": 2},
            }
        },
    }

    plan = build_email_authority_query_plan(handoff, jurisdiction_label="Oregon")

    assert plan
    assert any("Clackamas County Housing Authority" in item["query"] for item in plan)
    assert any(item["topic"] == "fraud_household" for item in plan)
    assert any("reasonable accommodation" in item["query"].lower() for item in plan)


def test_enrich_email_timeline_authorities_writes_json(tmp_path, monkeypatch):
    handoff_path = tmp_path / "email_timeline_handoff.json"
    handoff_path.write_text(
        json.dumps(
            {
                "claim_type": "retaliation",
                "claim_element_id": "causation",
                "canonical_facts": [{"participants": ["AFerron@clackamas.us"]}],
                "claim_support_temporal_handoff": {
                    "topic_summary": {"fraud_household": {"count": 1}}
                },
            }
        ),
        encoding="utf-8",
    )

    class _FakeAuthoritySearch:
        def search_web_archives(self, domain, max_results=3):
            return [{"url": f"https://{domain}/example", "title": "Example"}]

    class _FakeMediator:
        def __init__(self, backends):
            self.legal_authority_search = _FakeAuthoritySearch()

        def search_legal_authorities(self, *args, **kwargs):
            return {
                "statutes": [{"citation": "24 C.F.R. § 982.555"}],
                "regulations": [],
                "case_law": [{"citation": "Smith v. Housing Auth."}],
                "web_archives": [],
            }

    monkeypatch.setattr("complaint_generator.email_authority_enrichment.Mediator", _FakeMediator)

    payload = enrich_email_timeline_authorities(
        handoff_path,
        output_dir=tmp_path / "authority_enrichment",
        max_queries=2,
    )

    output_path = Path(payload["output_path"])
    assert output_path.exists()
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["summary"]["query_count"] == 2
    assert written["summary"]["total_counts"]["statutes"] == 2
    assert written["summary"]["total_counts"]["case_law"] == 2
    assert written["summary"]["total_counts"]["state_web_archives"] > 0
