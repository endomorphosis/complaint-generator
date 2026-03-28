from __future__ import annotations

import json
from pathlib import Path

from complaint_generator.email_timeline_handoff import (
    build_email_timeline_handoff,
    build_email_timeline_handoff_from_file,
)


def test_build_email_timeline_handoff_builds_anchored_temporal_artifacts() -> None:
    payload = build_email_timeline_handoff(
        [
            {
                "thread_subject": "Allegations of Fraud - JC Household",
                "subject": "Re: Allegations of Fraud - JC Household",
                "email_date": "Tue, 02 Dec 2025 16:54:52 +0000",
                "email_date_iso": "2025-12-02T16:54:52+00:00",
                "sender": "benjamin barber <starworks5@gmail.com>",
                "recipient": "\"Ferron, Ashley\" <AFerron@clackamas.us>",
                "participants": ["starworks5@gmail.com", "aferron@clackamas.us"],
                "summary": "Ben sent allegations email.",
                "eml_path": "/tmp/a.eml",
            },
            {
                "thread_subject": "HCV Orientation",
                "subject": "RE: HCV Orientation",
                "email_date": "Thu, 26 Mar 2026 16:36:46 +0000",
                "email_date_iso": "2026-03-26T16:36:46+00:00",
                "sender": "\"Tilton, Kati\" <KTilton@clackamas.us>",
                "recipient": "benjamin barber <starworks5@gmail.com>",
                "participants": ["starworks5@gmail.com", "ktilton@clackamas.us"],
                "summary": "Kati sent orientation response.",
                "eml_path": "/tmp/b.eml",
            },
        ],
        claim_type="retaliation",
        claim_element_id="causation",
    )

    assert payload["status"] == "success"
    assert payload["source_event_count"] == 2
    assert payload["canonical_facts"][0]["fact_id"] == "email_fact_001"
    assert payload["timeline_anchors"][0]["anchor_id"] == "timeline_anchor_001"
    assert payload["temporal_fact_registry"][0]["timeline_anchor_ids"] == ["timeline_anchor_001"]
    assert payload["timeline_relations"] == [
        {
            "relation_id": "timeline_relation_001",
            "source_fact_id": "email_fact_001",
            "target_fact_id": "email_fact_002",
            "relation_type": "before",
            "source_start_date": "2025-12-02",
            "source_end_date": "2025-12-02",
            "target_start_date": "2026-03-26",
            "target_end_date": "2026-03-26",
            "confidence": "high",
        }
    ]
    assert payload["claim_support_temporal_handoff"]["timeline_anchor_count"] == 2
    assert payload["claim_support_temporal_handoff"]["temporal_proof_objectives"] == [
        "establish_clackamas_email_sequence"
    ]


def test_build_email_timeline_handoff_from_file_writes_json(tmp_path: Path) -> None:
    timeline_path = tmp_path / "combined_timeline_candidates.json"
    timeline_path.write_text(
        json.dumps(
            [
                {
                    "thread_subject": "Additional Information Needed",
                    "subject": "Additional Information Needed",
                    "email_date": "Mon, 09 Feb 2026 17:57:35 +0000",
                    "email_date_iso": "2026-02-09T17:57:35+00:00",
                    "sender": "\"Tilton, Kati\" <KTilton@clackamas.us>",
                    "recipient": "benjamin barber <starworks5@gmail.com>",
                    "participants": ["ktilton@clackamas.us", "starworks5@gmail.com"],
                    "summary": "Kati requested additional information.",
                    "eml_path": "/tmp/c.eml",
                }
            ]
        ),
        encoding="utf-8",
    )

    payload = build_email_timeline_handoff_from_file(timeline_path)

    assert Path(payload["output_path"]).is_file()
    written = json.loads(Path(payload["output_path"]).read_text(encoding="utf-8"))
    assert written["source_timeline_path"] == str(timeline_path.resolve())
    assert written["canonical_facts"][0]["predicate_family"] == "additional_information"
