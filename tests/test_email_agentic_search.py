from __future__ import annotations

import json
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")

from complaint_generator.email_agentic_search import search_email_corpus_agentic


def _write_messages_parquet(path: Path) -> None:
    conn = duckdb.connect()
    try:
        conn.execute(
            """
            CREATE TABLE email_messages AS
            SELECT * FROM (
                VALUES
                (
                    '<msg1@example.test>',
                    1,
                    '[Gmail]/All Mail',
                    'RE: Allegations of Fraud - JC Household',
                    '"Ferron, Ashley" <AFerron@clackamas.us>',
                    'benjamin barber <starworks5@gmail.com>',
                    '',
                    'Tue, 27 Jan 2026 16:49:04 +0000',
                    '<msg1@example.test>',
                    '/tmp/bundle1',
                    '/tmp/bundle1/message.eml',
                    '/tmp/bundle1/message.json',
                    1234,
                    '',
                    '',
                    0.0,
                    '[]',
                    '[]',
                    0,
                    '[]',
                    '["aferron@clackamas.us", "starworks5@gmail.com"]',
                    'Email subject: RE: Allegations of Fraud - JC Household\nClackamas County fraud review by Ashley Ferron.'
                ),
                (
                    '<msg2@example.test>',
                    2,
                    '[Gmail]/All Mail',
                    'Re: Additional Information Needed',
                    '"Tilton, Kati" <KTilton@clackamas.us>',
                    'benjamin barber <starworks5@gmail.com>',
                    '',
                    'Mon, 09 Feb 2026 10:40:29 -0800',
                    '<msg2@example.test>',
                    '/tmp/bundle2',
                    '/tmp/bundle2/message.eml',
                    '/tmp/bundle2/message.json',
                    2345,
                    '',
                    '',
                    0.0,
                    '[]',
                    '[]',
                    0,
                    '[]',
                    '["ktilton@clackamas.us", "starworks5@gmail.com"]',
                    'Email subject: Re: Additional Information Needed\nClackamas County requested additional information for the household review.'
                ),
                (
                    '<msg3@example.test>',
                    3,
                    '[Gmail]/All Mail',
                    'Promo Offer',
                    'promo@example.com',
                    'starworks5@gmail.com',
                    '',
                    'Mon, 10 Feb 2026 10:40:29 -0800',
                    '<msg3@example.test>',
                    '/tmp/bundle3',
                    '/tmp/bundle3/message.eml',
                    '/tmp/bundle3/message.json',
                    3456,
                    '',
                    '',
                    0.0,
                    '[]',
                    '[]',
                    0,
                    '[]',
                    '["promo@example.com", "starworks5@gmail.com"]',
                    'Email subject: Promo Offer\nUnrelated marketing content.'
                )
            ) AS t(
                message_key,
                manifest_index,
                folder,
                subject,
                sender,
                recipient,
                cc,
                date,
                message_id_header,
                bundle_dir,
                eml_path,
                metadata_path,
                raw_size_bytes,
                raw_sha256,
                raw_cid,
                relevance_score,
                matched_terms_json,
                matched_fields_json,
                attachment_count,
                attachment_paths_json,
                participants_json,
                corpus_text
            )
            """
        )
        conn.execute("COPY email_messages TO ? (FORMAT PARQUET)", [str(path)])
    finally:
        conn.close()


def test_search_email_corpus_agentic_groups_threads_and_builds_timeline(tmp_path: Path) -> None:
    messages_path = tmp_path / "email_messages.parquet"
    _write_messages_parquet(messages_path)

    summary = search_email_corpus_agentic(
        index_path=messages_path,
        complaint_query="clackamas county fraud review",
        seed_terms=["clackamas county", "additional information needed"],
        seed_participants=["aferron@clackamas.us", "ktilton@clackamas.us"],
        output_dir=tmp_path / "agentic-output",
        emit_graphrag=False,
    )

    assert summary["status"] == "success"
    assert summary["candidate_count"] == 2
    assert summary["result_count"] == 2
    assert summary["chain_count"] == 2
    assert Path(summary["matched_emails_path"]).exists()
    assert Path(summary["chain_summaries_path"]).exists()
    assert Path(summary["timeline_candidates_path"]).exists()

    timeline_payload = json.loads(Path(summary["timeline_candidates_path"]).read_text(encoding="utf-8"))
    assert timeline_payload[0]["thread_subject"] == "Allegations of Fraud - JC Household"
    assert timeline_payload[1]["thread_subject"] == "Additional Information Needed"

    chain_payload = json.loads(Path(summary["chain_summaries_path"]).read_text(encoding="utf-8"))
    thread_subjects = [item["thread_subject"] for item in chain_payload]
    assert "Allegations of Fraud - JC Household" in thread_subjects
    assert "Additional Information Needed" in thread_subjects


def test_search_email_corpus_agentic_can_require_domain_and_multiple_seed_hits(tmp_path: Path) -> None:
    messages_path = tmp_path / "email_messages.parquet"
    _write_messages_parquet(messages_path)

    summary = search_email_corpus_agentic(
        index_path=messages_path,
        complaint_query="review",
        seed_terms=["clackamas county", "additional information needed"],
        seed_participants=["aferron@clackamas.us", "ktilton@clackamas.us"],
        required_participant_domains=["clackamas.us"],
        min_seed_phrase_matches=2,
        output_dir=tmp_path / "filtered-output",
        emit_graphrag=False,
    )

    assert summary["status"] == "success"
    assert summary["candidate_count"] == 2
    assert summary["result_count"] == 2
    assert summary["required_participant_domains"] == ["clackamas.us"]
    assert summary["min_seed_phrase_matches"] == 2

    hit_payload = json.loads(Path(summary["matched_emails_path"]).read_text(encoding="utf-8"))
    assert len(hit_payload) == 2
    assert all("clackamas.us" in " ".join(item["participants"]).lower() for item in hit_payload)
