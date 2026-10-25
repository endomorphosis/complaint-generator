"""Bounded current-source GUI acceptance groups.

Local synthetic acceptance runs nonempty cases for identity, DOM, ASGI,
encryption, provenance, and negative access. Historical Native completions
and optional live model, corpus, prover, and replica qualification stay on
separate lanes. An unexecuted group is not a pass.

Known limits: WebSocket, SSE, and streaming stay unqualified. This module
does not execute live model, corpus, prover, or replica qualification and
does not complete the campaign.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from integrations.private_storage import ENVELOPE_MAGIC


pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

_ROOT = Path(__file__).resolve().parents[1]
_SOURCE = _ROOT / "scripts" / "validate_gui_collaboration.py"
_SPEC = importlib.util.spec_from_file_location("validate_gui_collaboration", _SOURCE)
assert _SPEC is not None and _SPEC.loader is not None
acceptance = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(acceptance)


def _group(report, name):
    found = [row for row in report["groups"] if row["group"] == name]
    assert len(found) == 1
    return found[0]


def test_declared_groups_are_nonempty_and_lanes_stay_separate(tmp_path: Path) -> None:
    report = acceptance.run_bounded_acceptance(tmp_path / "lanes", include_browser=False)
    assert report["schema"] == acceptance.SCHEMA
    assert report["task_id"] == "CIMP-GUI-59"
    assert report["identity"]["source_baseline"] == acceptance.SOURCE_BASELINE
    assert set(report["identity"]["sdk_pins"]) == {"ipfs_accelerate_py", "ipfs_datasets_py", "ipfs_kit_py"}
    names = [row["group"] for row in report["groups"]]
    assert names == list(acceptance.DECLARED_GROUPS)
    for row in report["groups"]:
        assert row["cases"]
        acceptance.reject_unexecuted_pass(row)
    assert _group(report, "encryption")["lane"] == acceptance.LANE_LOCAL
    assert _group(report, "historical_native_completions")["lane"] == acceptance.LANE_HISTORICAL
    assert _group(report, "live_model")["lane"] == acceptance.LANE_OPTIONAL
    assert report["historical_counts_as_local_acceptance"] is False
    assert report["unexecuted_groups_count_as_passing"] is False
    assert "dom_asgi" in report["unexecuted_groups"]
    assert report["local_synthetic_acceptance_passed"] is False
    assert report["bounded_acceptance_ok"] is False
    assert report["campaign_completion"] is False


def test_unexecuted_optional_and_historical_completion_do_not_pass_as_local() -> None:
    for name in acceptance.OPTIONAL_GROUPS:
        case = acceptance.optional_live_case(name, None)
        assert case["executed"] is False
        assert case["passed"] is False
        assert case["counts_as_passing"] is False
    with pytest.raises(acceptance.AcceptanceSeparationError):
        acceptance.optional_live_case("live_prover", {"passed": True, "executed": False})
    old44 = {"program": "completed44", "status": "completed", "settled_merge_queue": True, "historical_native": True}
    old58 = {"program": "completed58", "status": "completed", "historical_native": True}
    assert acceptance.historical_completion_counts_as_local(old44) is False
    assert acceptance.historical_completion_counts_as_local(old58) is False
    with pytest.raises(acceptance.AcceptanceSeparationError):
        acceptance.historical_completion_counts_as_local({"program": "local_synthetic_gui", "status": "completed"})
    with pytest.raises(acceptance.AcceptanceSeparationError):
        acceptance.reject_unexecuted_pass({"group": "live_corpus", "executed": False, "passed": True, "cases": []})


def test_encryption_provenance_and_negative_access_execute(tmp_path: Path) -> None:
    report = acceptance.run_bounded_acceptance(tmp_path / "handlers", include_browser=False)
    encryption = _group(report, "encryption")
    provenance = _group(report, "provenance")
    negative = _group(report, "negative_access")
    identity = _group(report, "runtime_identity")
    for group in (encryption, provenance, negative, identity):
        assert group["executed"] is True
        assert group["passed"] is True
        assert all(case["executed"] and case["passed"] for case in group["cases"])
    assert encryption["cases"][1]["detail"]["magic"] == ENVELOPE_MAGIC.decode("ascii")
    assert provenance["cases"][1]["detail"]["reason"] == "graph_provenance_missing"
    assert negative["cases"][0]["detail"]["status"] == 401
    assert {row["group"] for row in report["groups"] if row["lane"] == acceptance.LANE_OPTIONAL} == set(acceptance.OPTIONAL_GROUPS)
    assert report["optional_future_live_passed"] is False
    assert report["all_declared_groups_passing"] is False
    assert report["historical_native_separated"] is True


def test_current_source_acceptance_runs_dom_asgi_and_keeps_optional_unexecuted(tmp_path: Path) -> None:
    report = acceptance.run_bounded_acceptance(tmp_path / "acceptance")
    dom = _group(report, "dom_asgi")
    assert dom["executed"] is True
    assert dom["passed"] is True, dom["cases"][0]["detail"]
    assert dom["counts_as_local_synthetic_acceptance"] is True
    case_ids = [case["case_id"] for case in dom["cases"]]
    assert case_ids == [
        "chromium_dom_pipe",
        "same_origin_asgi_health",
        "external_origin_aborted",
        "unsupported_transports_not_qualified",
    ]
    assert report["identity"]["python"].startswith("3.12.")
    assert all(len(digest) == 64 for digest in report["identity"]["source_file_sha256"].values())
    assert report["local_synthetic_acceptance_passed"] is True
    assert report["historical_native_separated"] is True
    assert report["optional_future_live_executed"] is False
    assert report["optional_future_live_passed"] is False
    assert set(report["unexecuted_groups"]) == set(acceptance.OPTIONAL_GROUPS)
    assert report["all_declared_groups_passing"] is False
    assert report["bounded_acceptance_ok"] is True
    assert "websocket_sse_and_streaming_are_not_qualified" in report["known_limitations"]
    forged = dict(report)
    forged["groups"] = [dict(row) for row in report["groups"]]
    forged["groups"][-1] = dict(forged["groups"][-1])
    forged["groups"][-1]["executed"] = False
    forged["groups"][-1]["passed"] = True
    with pytest.raises(acceptance.AcceptanceSeparationError):
        acceptance._rollup(report["identity"], forged["groups"])


def test_cli_report_matches_public_runner(tmp_path: Path) -> None:
    state = tmp_path / "cli-state"
    report_path = tmp_path / "report.json"
    code = acceptance.main(["--state-dir", str(state), "--report", str(report_path), "--skip-browser"])
    written = json.loads(report_path.read_text(encoding="utf-8"))
    assert code == 1
    assert written["bounded_acceptance_ok"] is False
    assert written["optional_future_live_passed"] is False
    assert _group(written, "negative_access")["passed"] is True
    full = tmp_path / "cli-full"
    full_report = tmp_path / "full.json"
    full_code = acceptance.main(["--state-dir", str(full), "--report", str(full_report)])
    body = json.loads(full_report.read_text(encoding="utf-8"))
    assert full_code == 0
    assert body["bounded_acceptance_ok"] is True
    assert body["local_synthetic_acceptance_passed"] is True
    assert body["optional_future_live_passed"] is False
