from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "merge_email_manifests.py"
    spec = importlib.util.spec_from_file_location("merge_email_manifests_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_merge_email_manifests_deduplicates_by_message_id(tmp_path: Path) -> None:
    module = _load_script_module()
    manifest_one = tmp_path / "one.json"
    manifest_two = tmp_path / "two.json"
    shared = {
        "message_id_header": "<shared@example.com>",
        "subject": "Shared thread",
        "date": "2026-03-01T10:00:00+00:00",
        "from": "a@example.com",
        "to": "b@example.com",
        "bundle_dir": "/tmp/shared",
        "attachment_paths": [],
    }
    manifest_one.write_text(
        json.dumps(
            {
                "complaint_terms": ["hcv", "orientation"],
                "min_relevance_score": 1.0,
                "emails": [
                    shared,
                    {
                        "message_id_header": "<one@example.com>",
                        "subject": "Only one",
                        "date": "2026-03-02T10:00:00+00:00",
                        "from": "a@example.com",
                        "to": "b@example.com",
                        "bundle_dir": "/tmp/one",
                        "attachment_paths": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest_two.write_text(
        json.dumps(
            {
                "complaint_terms": ["living", "room"],
                "min_relevance_score": 2.0,
                "emails": [
                    shared,
                    {
                        "message_id_header": "<two@example.com>",
                        "subject": "Only two",
                        "date": "2026-03-03T10:00:00+00:00",
                        "from": "c@example.com",
                        "to": "d@example.com",
                        "bundle_dir": "/tmp/two",
                        "attachment_paths": [],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = module.merge_email_manifests(
        manifest_paths=[manifest_one, manifest_two],
        output_dir=tmp_path / "output",
        case_slug="merged",
    )

    merged = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
    ids = [record["message_id_header"] for record in merged["emails"]]

    assert payload["email_count"] == 3
    assert payload["duplicate_email_count"] == 1
    assert merged["matched_email_count"] == 3
    assert merged["duplicate_email_count"] == 1
    assert merged["min_relevance_score"] == 2.0
    assert ids == [
        "<shared@example.com>",
        "<one@example.com>",
        "<two@example.com>",
    ]
    assert merged["complaint_terms"] == ["hcv", "orientation", "living", "room"]
