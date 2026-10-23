"""Supervisor terminal completion requires executed synthetic evidence.

Source text that contains an acceptance phrase is not a receipt. Interview
waits stay distinct from stalled development workers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.ipfs_accelerate.supervisor_terminal_acceptance import (
    MAX_EXTERNAL_RETRIES,
    TerminalAcceptanceError,
    apply_receipt_to_product_session,
    continue_development,
    distinguish_wait,
    execute_bounded_acceptance,
    mark_terminal_complete,
    refuse_unstick_action,
    source_identity,
)


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _source(tmp_path: Path) -> Path:
    path = tmp_path / "gate.py"
    path.write_text("def gate():\n    return 'executed'\n", encoding="utf-8")
    return path


def _session() -> dict:
    return {
        "session_id": "synthetic-session",
        "legal_status": "unresolved",
        "unresolved_issues": [
            {"id": "issue-legal-1", "kind": "legal", "summary": "Authority is still unidentified."},
            {"id": "issue-user-1", "kind": "user", "summary": "The user has not named the defendant."},
        ],
    }


def _receipt(tmp_path: Path, **kwargs):
    return execute_bounded_acceptance(task_id="CIMP-TUI-12", source_paths=[_source(tmp_path)], product_session=_session(), **kwargs)


def test_source_substring_alone_cannot_complete(tmp_path: Path) -> None:
    source = _source(tmp_path)
    text = source.read_text(encoding="utf-8") + "\nStatus: completed\n"
    decision = mark_terminal_complete({"method": "source_substring", "source_text": text, "needle": "Status: completed", "matched": True})
    assert decision["completion"] is False
    assert decision["reason"] == "source_substring_not_authoritative"
    assert decision["substring_check"]["authoritative"] is False
    assert decision["passed"] == []
    assert decision["skipped"] == []
    assert decision["live_canary"]["status"] == "not_requested"


def test_executed_lanes_attach_receipts_and_source_identity(tmp_path: Path) -> None:
    calls = []

    def runner(lane):
        def _run(fixture):
            calls.append((lane, dict(fixture)))
            return {"status": "passed", "executed": True, "reason": "injected", "detail": {"lane": lane}}
        return _run

    source = _source(tmp_path)
    receipt = execute_bounded_acceptance(
        task_id="CIMP-TUI-12",
        source_paths=[source],
        runners={name: runner(name) for name in ("pty", "graph", "privacy")},
        fixtures={
            "pty": {"script": [{"role": "user", "text": "synthetic"}]},
            "graph": {"nodes": []},
            "privacy": {"denied_paths": []},
        },
        product_session=_session(),
        substring_check={"source_text": "Status: completed", "needle": "Status: completed"},
    )
    assert calls and [item[0] for item in calls] == ["pty", "graph", "privacy"]
    assert receipt["completion"] is True
    assert receipt["passed"] == ["pty", "graph", "privacy"]
    assert receipt["skipped"] == []
    assert receipt["live_canary"] == {"requested": False, "executed": False, "status": "not_requested"}
    assert receipt["source_identity"]["digest"] == source_identity([source])["digest"]
    assert receipt["substring_check"]["matched"] is True
    assert receipt["substring_check"]["authoritative"] is False
    assert [row["lane"] for row in receipt["output_receipts"]] == ["pty", "graph", "privacy"]
    assert all(row["executed"] is True and row["digest"] for row in receipt["output_receipts"])
    decision = mark_terminal_complete({"receipt": receipt, "source_identity_digest": receipt["source_identity"]["digest"]})
    assert decision["completion"] is True


def test_skipped_lane_is_not_passed_and_blocks_completion(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path, fixtures={"privacy": {}})
    assert "privacy" in receipt["skipped"]
    assert "privacy" not in receipt["passed"]
    assert receipt["completion"] is False
    assert receipt["reason"].startswith("skipped_required_lane")


def test_live_canary_is_reported_separately_from_passed_lanes(tmp_path: Path) -> None:
    not_run = _receipt(tmp_path, live_canary={"requested": True, "executed": False, "status": "passed"})
    assert not_run["completion"] is True
    assert not_run["passed"] == ["pty", "graph", "privacy"]
    assert not_run["live_canary"] == {"requested": True, "executed": False, "status": "not_executed"}

    failed = _receipt(tmp_path, live_canary={"requested": True, "executed": True, "status": "failed"})
    assert failed["completion"] is True
    assert "live_canary" not in failed["passed"]
    assert failed["live_canary"]["status"] == "failed"
    assert failed["skipped"] == []


def test_stale_source_identity_rejects_an_otherwise_valid_receipt(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path)
    decision = mark_terminal_complete({"receipt": receipt, "source_identity_digest": "0" * 64})
    assert decision["completion"] is False
    assert decision["reason"] == "stale_source_identity"


def test_default_pty_bounds_and_refuses_fabricated_answers(tmp_path: Path) -> None:
    too_long = [{"role": "user", "text": f"line-{index}"} for index in range(9)]
    receipt = _receipt(tmp_path, fixtures={"pty": {"script": too_long, "max_turns": 8}})
    assert receipt["completion"] is False
    pty = next(row for row in receipt["output_receipts"] if row["lane"] == "pty")
    assert pty["reason"] == "pty_turn_bound_exceeded"
    with pytest.raises(TerminalAcceptanceError, match="fabricate"):
        _receipt(tmp_path, fixtures={"pty": {"fabricate_missing_answer": True, "script": too_long[:1]}})


def test_graph_without_provenance_fails_and_privacy_denied_read_fails(tmp_path: Path) -> None:
    receipt = _receipt(
        tmp_path,
        fixtures={
            "graph": {"nodes": [{"id": "n1", "provenance": {}}]},
            "privacy": {"denied_paths": ["sessions/real"], "attempted_reads": ["sessions/real"]},
        },
    )
    reasons = {row["lane"]: row["reason"] for row in receipt["output_receipts"]}
    assert reasons["graph"] == "graph_provenance_missing"
    assert reasons["privacy"] == "denied_path_read"
    assert receipt["failed"] == ["graph", "privacy"]
    assert receipt["passed"] == ["pty"]


def test_interview_awaiting_user_is_not_a_stalled_development_worker() -> None:
    waiting = distinguish_wait({"role": "end_user_interview", "phase": "awaiting_user", "heartbeat_age_seconds": None})
    assert waiting["classification"] == "legitimate_awaiting_user"
    assert waiting["stalled_development_worker"] is False
    assert waiting["fabricated_user_answer"] is None
    assert waiting["legal_completion_forced"] is False
    assert waiting["recovery_action"] == "wait"

    stalled = distinguish_wait({"role": "development_worker", "phase": "awaiting_user", "heartbeat_age_seconds": 500})
    assert stalled["classification"] == "stalled_development_worker"
    assert stalled["stalled_development_worker"] is True
    assert stalled["recovery_action"] == "bounded_retry"
    assert stalled["fabricated_user_answer"] is None

    active = distinguish_wait({"role": "development_worker", "heartbeat_age_seconds": 5, "stall_after_seconds": 120})
    assert active["classification"] == "development_worker_active"


def test_unstick_actions_are_refused() -> None:
    with pytest.raises(TerminalAcceptanceError, match="fabricate"):
        refuse_unstick_action("fabricate_user_answer")
    with pytest.raises(TerminalAcceptanceError, match="legal completion"):
        refuse_unstick_action("force_legal_completion")
    with pytest.raises(TerminalAcceptanceError, match="fabricate"):
        continue_development({"id": "CIMP-DEV", "fabricate_user_answer": True}, synthetic_fixture={"fixture_id": "fix-1"})
    with pytest.raises(TerminalAcceptanceError, match="legal completion"):
        continue_development({"id": "CIMP-DEV", "force_legal_completion": True}, synthetic_fixture={"fixture_id": "fix-1"})


def test_development_uses_synthetic_fixture_or_bounded_resumable_diagnostic() -> None:
    continued = continue_development(
        {"id": "CIMP-DEV", "cursor": "lane-2"},
        synthetic_fixture={"fixture_id": "synthetic-graph"},
        state={"attempt": 1, "checkpoint": {"task_id": "CIMP-DEV", "cursor": "lane-2"}},
    )
    assert continued["status"] == "continued"
    assert continued["fixture_id"] == "synthetic-graph"
    assert continued["attempt"] == 1
    assert continued["checkpoint"]["cursor"] == "lane-2"
    assert continued["legal_completion_forced"] is False

    state = {"attempt": 0, "checkpoint": {"task_id": "CIMP-DEV", "cursor": "external"}}
    dependency = {
        "name": "sealed-prover",
        "irreducible": True,
        "available": False,
        "code": "external_dependency_unavailable",
        "detail": "sealed prover is absent from the validation PATH",
    }
    first = continue_development({"id": "CIMP-DEV"}, external_dependency=dependency, state=state)
    assert first["status"] == "retry_scheduled"
    assert first["attempt"] == 1
    assert first["retries_remaining"] == MAX_EXTERNAL_RETRIES - 1
    assert first["diagnostic"]["code"] == "external_dependency_unavailable"
    assert first["diagnostic"]["detail"] == dependency["detail"]
    assert first["checkpoint"] == state["checkpoint"]
    assert first["fabricated_user_answer"] is None

    exhausted_state = {"attempt": MAX_EXTERNAL_RETRIES, "checkpoint": dict(state["checkpoint"])}
    stopped = continue_development({"id": "CIMP-DEV"}, external_dependency=dependency, state=exhausted_state)
    assert stopped["status"] == "blocked_external_dependency"
    assert stopped["attempt"] == MAX_EXTERNAL_RETRIES
    assert stopped["retries_remaining"] == 0
    assert stopped["checkpoint"] == exhausted_state["checkpoint"]
    assert stopped["legal_completion_forced"] is False


def test_completion_preserves_actionable_product_issues(tmp_path: Path) -> None:
    session = _session()
    receipt = _receipt(tmp_path)
    preserved = apply_receipt_to_product_session(session, receipt)
    assert preserved["legal_status"] == "unresolved"
    assert preserved["unresolved_issues"] == session["unresolved_issues"]
    assert receipt["unresolved_legal_user_issues"] == session["unresolved_issues"]
    assert session["legal_status"] == "unresolved"
    with pytest.raises(TerminalAcceptanceError, match="legally complete"):
        apply_receipt_to_product_session({**session, "legal_status": "complete"}, receipt)


def test_missing_source_identity_blocks_completion(tmp_path: Path) -> None:
    receipt = execute_bounded_acceptance(
        task_id="CIMP-TUI-12",
        source_paths=[tmp_path / "absent.py"],
        product_session=_session(),
    )
    assert receipt["completion"] is False
    assert receipt["reason"] == "missing_source_identity"
    assert receipt["source_identity"]["digest"] == ""
    assert receipt["passed"] == ["pty", "graph", "privacy"]
