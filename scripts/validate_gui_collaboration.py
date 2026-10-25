#!/usr/bin/env python3
"""Bounded current-source GUI acceptance groups.

Local synthetic acceptance, historical Native completions, and optional future
live model, corpus, prover, and replica qualification are separate lanes.
A group that was not executed is never passing. Historical completion and an
unexecuted live lane do not satisfy local synthetic acceptance.

This runner uses the shared ASGI application through the Task 02 same-origin
pipe bridge, the private-artifact seal, and the synthetic graph provenance
check. It does not install packages, read private campaigns, or call a live
model, corpus, prover, or replica.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from integrations.ipfs_accelerate.supervisor_terminal_acceptance import default_graph_acceptance
from integrations.ipfs_datasets.capabilities import DECLARED_OWNER_PINS
from integrations.private_storage import (
    ENVELOPE_MAGIC,
    PrivateArtifactBinding,
    PrivateArtifactBindingError,
    PrivateArtifactIntegrityError,
    assert_access_matches_binding,
    open_private_artifact,
    seal_private_artifact,
)
from tests.gui_native_browser import (
    SAME_ORIGIN,
    BrowserCapabilityError,
    BrowserHttpRequest,
    SameOriginAsgiBridge,
    build_qualification_app,
    qualify_native_browser,
)


SOURCE_BASELINE = "2c1439a7029eb9035338133210d8b43319add8a4"
SCHEMA = "complaint-gui-acceptance-groups/v1"
TASK_ID = "CIMP-GUI-59"
PLAINTEXT = b"synthetic-cimp-gui-59-note"
KEY = bytes(range(32))
KEY_ID = "synthetic-cimp-gui-59-key"
LANE_LOCAL = "local_synthetic_gui"
LANE_HISTORICAL = "historical_native"
LANE_OPTIONAL = "optional_future_live"
OPTIONAL_GROUPS = ("live_model", "live_corpus", "live_prover", "live_replica")
LOCAL_GROUPS = ("runtime_identity", "dom_asgi", "encryption", "provenance", "negative_access")
HISTORICAL_GROUP = "historical_native_completions"
DECLARED_GROUPS = LOCAL_GROUPS + (HISTORICAL_GROUP,) + OPTIONAL_GROUPS
_IDENTITY_FILES = (
    "applications/server.py",
    "integrations/private_storage.py",
    "tests/gui_native_browser.py",
    "scripts/validate_gui_collaboration.py",
)
_HISTORICAL_PROGRAMS = frozenset({
    "completed44",
    "completed58",
    "old44",
    "old58",
    "mediator-44",
    "intake-58",
})


class AcceptanceSeparationError(ValueError):
    """A lane was counted as a pass without its own executed evidence."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def current_runtime_identity() -> dict[str, Any]:
    """Bind this run to the source baseline, declared SDK pins, and this interpreter."""

    root = _repo_root()
    files: dict[str, str] = {}
    for relative in _IDENTITY_FILES:
        path = root / relative
        files[relative] = _sha256(path) if path.is_file() else ""
    return {
        "source_baseline": SOURCE_BASELINE,
        "source_file_sha256": files,
        "sdk_pins": {name: DECLARED_OWNER_PINS[name] for name in ("ipfs_accelerate_py", "ipfs_datasets_py", "ipfs_kit_py")},
        "python": platform.python_version(),
        "executable": sys.executable,
        "implementation": platform.python_implementation(),
        "packages_installed": False,
        "live_egress": False,
    }


def _case(case_id: str, *, executed: bool, passed: bool, detail: Mapping[str, Any]) -> dict[str, Any]:
    if passed and not executed:
        raise AcceptanceSeparationError(f"{case_id} cannot pass without execution")
    return {
        "case_id": case_id,
        "executed": executed,
        "passed": passed,
        "counts_as_passing": executed and passed,
        "detail": dict(detail),
    }


def _group(name: str, lane: str, cases: Sequence[Mapping[str, Any]], *, mandatory: bool) -> dict[str, Any]:
    if not cases:
        raise AcceptanceSeparationError(f"{name} has no cases")
    executed = [row for row in cases if row["executed"]]
    if mandatory and not executed:
        raise AcceptanceSeparationError(f"mandatory group {name} did not execute")
    passed = bool(executed) and all(row["passed"] for row in executed) and len(executed) == len(cases)
    return {
        "group": name,
        "lane": lane,
        "mandatory": mandatory,
        "cases": list(cases),
        "executed": len(executed) == len(cases) and bool(executed),
        "passed": passed,
        "counts_as_passing": passed,
        "counts_as_local_synthetic_acceptance": lane == LANE_LOCAL and passed,
    }


def _binding(principal: str = "synthetic-owner") -> PrivateArtifactBinding:
    return PrivateArtifactBinding(
        tenant_id="synthetic-tenant-59",
        case_id="synthetic-case-59",
        artifact_kind="gui-acceptance-note",
        revision="1",
        principal_id=principal,
    )


class _Access:
    def __init__(self, principal_id: str, case_id: str, trust: str = "authenticated") -> None:
        self.principal_id = principal_id
        self.case_id = case_id
        self.trust = trust


def _identity_cases(identity: Mapping[str, Any]) -> list[dict[str, Any]]:
    pins = identity["sdk_pins"]
    files = identity["source_file_sha256"]
    pin_ok = all(isinstance(pins.get(name), str) and len(pins[name]) == 40 for name in DECLARED_OWNER_PINS)
    files_ok = all(isinstance(files.get(name), str) and len(files[name]) == 64 for name in _IDENTITY_FILES)
    python_ok = str(identity["python"]).startswith("3.12.")
    return [
        _case("source_baseline_bound", executed=True, passed=identity["source_baseline"] == SOURCE_BASELINE and files_ok, detail={"baseline": identity["source_baseline"]}),
        _case("sdk_pins_bound", executed=True, passed=pin_ok, detail={"owners": sorted(pins)}),
        _case("python_runtime_recorded", executed=True, passed=python_ok and bool(identity["executable"]), detail={"python": identity["python"], "executable": identity["executable"]}),
    ]


def _encryption_cases() -> list[dict[str, Any]]:
    binding = _binding()
    envelope = seal_private_artifact(PLAINTEXT, binding=binding, key=KEY, key_id=KEY_ID)
    opened = open_private_artifact(envelope, binding=binding, key=KEY, expected_key_id=KEY_ID)
    hidden = PLAINTEXT not in envelope and envelope.startswith(ENVELOPE_MAGIC)
    wrong = _binding("synthetic-stranger")
    denied = False
    try:
        open_private_artifact(envelope, binding=wrong, key=KEY, expected_key_id=KEY_ID)
    except PrivateArtifactIntegrityError:
        denied = True
    return [
        _case("seal_open_roundtrip", executed=True, passed=opened == PLAINTEXT, detail={"bytes": len(envelope)}),
        _case("ciphertext_hides_plaintext", executed=True, passed=hidden, detail={"magic": ENVELOPE_MAGIC.decode("ascii")}),
        _case("wrong_binding_denied", executed=True, passed=denied, detail={"principal": wrong.principal_id}),
    ]


def _provenance_cases() -> list[dict[str, Any]]:
    present = default_graph_acceptance({
        "nodes": [{
            "id": "synthetic-event-59",
            "provenance": {"source_kind": "user_statement", "source_id": "msg-synthetic-59"},
        }],
    })
    missing = default_graph_acceptance({"nodes": [{"id": "synthetic-event-59"}]})
    return [
        _case("synthetic_node_with_provenance_passes", executed=True, passed=present["status"] == "passed" and present["executed"] is True, detail={"reason": present["reason"]}),
        _case("missing_provenance_fails", executed=True, passed=missing["status"] == "failed" and missing["executed"] is True, detail={"reason": missing["reason"]}),
    ]


def _negative_access_cases(state_dir: Path) -> list[dict[str, Any]]:
    application, _fixture = build_qualification_app(state_dir)
    bridge = SameOriginAsgiBridge(application)
    download = bridge.handle(BrowserHttpRequest("GET", f"{SAME_ORIGIN}/__cimp_gui_02__/download", []))
    external = bridge.handle(BrowserHttpRequest("GET", "https://example.invalid/health", []))
    health = bridge.handle(BrowserHttpRequest("GET", f"{SAME_ORIGIN}/health", [("accept", "application/json")]))
    websocket = bridge.handle(BrowserHttpRequest("GET", f"{SAME_ORIGIN}/socket", [("upgrade", "websocket")]))
    stranger_denied = False
    try:
        assert_access_matches_binding(_Access("synthetic-stranger", "synthetic-case-59"), _binding())
    except PrivateArtifactBindingError:
        stranger_denied = True
    asgi_ok = bridge.asgi_calls >= 2 and health.status == 200 and health.action == "fulfill"
    return [
        _case("anonymous_download_denied", executed=True, passed=download.status == 401 and download.action == "fulfill", detail={"status": download.status}),
        _case("external_origin_not_fulfilled", executed=True, passed=external.action == "abort" and external.reason == "external-origin" and asgi_ok, detail={"asgi_calls": bridge.asgi_calls, "health": health.status}),
        _case("stranger_principal_binding_denied", executed=True, passed=stranger_denied and websocket.action == "abort", detail={"websocket": websocket.reason}),
    ]


def _dom_cases(state_dir: Path) -> list[dict[str, Any]]:
    try:
        report = qualify_native_browser(state_dir / "browser-profiles")
    except BrowserCapabilityError as exc:
        detail = {"error": str(exc), "capability": "missing"}
        return [
            _case("chromium_dom_pipe", executed=True, passed=False, detail=detail),
            _case("same_origin_asgi_health", executed=True, passed=False, detail=detail),
            _case("external_origin_aborted", executed=True, passed=False, detail=detail),
            _case("unsupported_transports_not_qualified", executed=True, passed=False, detail=detail),
        ]
    transports = report.qualified_transports
    unsupported = all(transports.get(name) is False for name in ("websocket", "sse", "streaming"))
    return [
        _case("chromium_dom_pipe", executed=True, passed=report.pipe_transport is True and bool(report.chromium.sha256), detail={"pipe_transport": report.pipe_transport, "chromium_sha256": report.chromium.sha256}),
        _case("same_origin_asgi_health", executed=True, passed=report.health_status == 200 and "/health" in report.same_origin_paths and report.persisted_note == "synthetic-note-02", detail={"health": report.health_status, "note": report.persisted_note}),
        _case("external_origin_aborted", executed=True, passed=bool(report.aborted_external) and report.cookie_replayed_by_bridge is False, detail={"aborted": len(report.aborted_external)}),
        _case("unsupported_transports_not_qualified", executed=True, passed=unsupported, detail={"qualified_transports": dict(transports)}),
    ]


def historical_completion_counts_as_local(record: Mapping[str, Any]) -> bool:
    """Historical Native completions stay on their own lane.

    A completed old 44 or old 58 record is recognized and still does not
    count as local synthetic acceptance. Other records are not this lane.
    """

    program = str(record.get("program") or record.get("kind") or "")
    historical = program in _HISTORICAL_PROGRAMS or record.get("historical_native") is True or record.get("lane") == LANE_HISTORICAL
    if not historical:
        raise AcceptanceSeparationError("record is not a historical native completion")
    return False


def _historical_cases() -> list[dict[str, Any]]:
    old44 = {"program": "completed44", "status": "completed", "settled_merge_queue": True, "historical_native": True}
    old58 = {"program": "completed58", "status": "completed", "canonical_callback": True, "historical_native": True}
    return [
        _case("old44_completion_is_not_local_acceptance", executed=True, passed=historical_completion_counts_as_local(old44) is False, detail={"program": "completed44"}),
        _case("old58_completion_is_not_local_acceptance", executed=True, passed=historical_completion_counts_as_local(old58) is False and old58["status"] == "completed", detail={"program": "completed58"}),
    ]


def optional_live_case(group: str, evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Record one future live qualification. Absent evidence stays unexecuted."""

    case_id = f"{group}_qualification"
    if evidence is None:
        return _case(case_id, executed=False, passed=False, detail={"status": "unexecuted", "reason": "not_run"})
    executed = evidence.get("executed") is True
    capability = evidence.get("capability_present") is True
    observed = evidence.get("observed") is True
    passed = executed and capability and observed and evidence.get("passed") is True
    if evidence.get("passed") is True and not executed:
        raise AcceptanceSeparationError(f"{group} cannot pass without execution")
    status = "passed" if passed else ("failed" if executed else "unexecuted")
    return _case(case_id, executed=executed, passed=passed, detail={"status": status, "capability_present": capability})


def run_bounded_acceptance(state_dir: Path, *, include_browser: bool = True, optional_evidence: Mapping[str, Mapping[str, Any] | None] | None = None) -> dict[str, Any]:
    """Run every mandatory local and historical case and record optional live groups."""

    state_dir.mkdir(parents=True, exist_ok=True)
    identity = current_runtime_identity()
    if include_browser:
        dom = _group("dom_asgi", LANE_LOCAL, _dom_cases(state_dir), mandatory=True)
    else:
        dom = _group("dom_asgi", LANE_LOCAL, [_case("chromium_dom_pipe", executed=False, passed=False, detail={"status": "unexecuted"})], mandatory=False)
    groups = [
        _group("runtime_identity", LANE_LOCAL, _identity_cases(identity), mandatory=True),
        dom,
        _group("encryption", LANE_LOCAL, _encryption_cases(), mandatory=True),
        _group("provenance", LANE_LOCAL, _provenance_cases(), mandatory=True),
        _group("negative_access", LANE_LOCAL, _negative_access_cases(state_dir / "asgi"), mandatory=True),
        _group(HISTORICAL_GROUP, LANE_HISTORICAL, _historical_cases(), mandatory=True),
    ]
    supplied = optional_evidence or {}
    for name in OPTIONAL_GROUPS:
        groups.append(_group(name, LANE_OPTIONAL, [optional_live_case(name, supplied.get(name))], mandatory=False))
    return _rollup(identity, groups)


def _rollup(identity: Mapping[str, Any], groups: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_name = {str(row["group"]): row for row in groups}
    missing = [name for name in DECLARED_GROUPS if name not in by_name]
    if missing:
        raise AcceptanceSeparationError("undeclared or missing groups: " + ",".join(missing))
    local = [by_name[name] for name in LOCAL_GROUPS]
    historical = by_name[HISTORICAL_GROUP]
    optional = [by_name[name] for name in OPTIONAL_GROUPS]
    if any(row["passed"] and not row["executed"] for row in groups):
        raise AcceptanceSeparationError("unexecuted group counted as passing")
    if historical["counts_as_local_synthetic_acceptance"]:
        raise AcceptanceSeparationError("historical native completion counted as local acceptance")
    if any(row["counts_as_local_synthetic_acceptance"] for row in optional):
        raise AcceptanceSeparationError("optional live qualification counted as local acceptance")
    local_passed = all(row["mandatory"] and row["executed"] and row["passed"] for row in local)
    historical_separated = bool(historical["executed"] and historical["passed"] and not historical["counts_as_local_synthetic_acceptance"])
    optional_executed = all(row["executed"] for row in optional)
    optional_passed = optional_executed and all(row["passed"] for row in optional)
    unexecuted = [str(row["group"]) for row in groups if not row["executed"]]
    return {
        "schema": SCHEMA,
        "task_id": TASK_ID,
        "identity": dict(identity),
        "groups": [dict(row) for row in groups],
        "local_synthetic_acceptance_passed": local_passed,
        "historical_native_separated": historical_separated,
        "historical_counts_as_local_acceptance": False,
        "optional_future_live_executed": optional_executed,
        "optional_future_live_passed": optional_passed,
        "unexecuted_groups": unexecuted,
        "unexecuted_groups_count_as_passing": False,
        "all_declared_groups_passing": local_passed and historical_separated and optional_passed,
        "bounded_acceptance_ok": local_passed and historical_separated and not any(row["passed"] for row in optional if not row["executed"]),
        "campaign_completion": False,
        "known_limitations": [
            "websocket_sse_and_streaming_are_not_qualified",
            "historical_native_completions_are_a_separate_lane",
            "unexecuted_live_model_corpus_prover_and_replica_groups_are_not_passing",
            "this_report_does_not_complete_the_campaign",
        ],
    }


def reject_unexecuted_pass(group: Mapping[str, Any]) -> None:
    """Public guard used by tests. An unexecuted group is not a pass."""

    if group.get("passed") is True and group.get("executed") is not True:
        raise AcceptanceSeparationError("unexecuted group counted as passing")
    for case in group.get("cases") or []:
        if isinstance(case, Mapping) and case.get("passed") is True and case.get("executed") is not True:
            raise AcceptanceSeparationError("unexecuted case counted as passing")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run bounded current-source GUI acceptance groups")
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--skip-browser", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = run_bounded_acceptance(args.state_dir, include_browser=not args.skip_browser)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report is not None:
        args.report.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0 if report["bounded_acceptance_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
