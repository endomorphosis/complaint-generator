"""Bounded native recovery for stalled complaint-improvement workers.

These tests use temporary Git roots, synthetic process births and a fake
container inventory. They do not dispatch a provider or invent interview answers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import sys

import pytest

import integrations.ipfs_accelerate.improvement_runner as runner


ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.fixture(autouse=True)
def restore_cwd(monkeypatch):
    monkeypatch.chdir(ROOT)


def _forbid_dispatch(monkeypatch):
    original = runner.subprocess.Popen

    def guarded(*args, **kwargs):
        command = args[0] if args else kwargs.get("args")
        rendered = " ".join(map(str, command)) if isinstance(command, (list, tuple)) else str(command)
        executable = command[0] if isinstance(command, (list, tuple)) and command else rendered
        name = Path(str(executable)).name
        if name in {"grok", "grok-cli"} or "--owner-token" in rendered or name.startswith("provider"):
            pytest.fail(f"provider or child dispatch: {rendered}")
        return original(*args, **kwargs)

    monkeypatch.setattr(runner.subprocess, "Popen", guarded)
    monkeypatch.setattr(runner, "start", lambda *a, **k: pytest.fail("task selection"))


def _stamp(seconds_ago=0):
    return datetime.fromtimestamp(runner.time.time() - seconds_ago, timezone.utc).isoformat()


def _identity(pid=991119):
    return {"pid": pid, "start_ticks": 123456, "boot_id": "test-boot", "ppid": 1,
            "session": pid, "process_group": pid, "argv": [sys.executable, "_run"]}


def _spec_text():
    return json.dumps({
        "schema_version": "complaint-intake-improvement@1", "title": "Synthetic recovery campaign",
        "provider": {"router": "ipfs_accelerate_py.llm_router", "provider": "grok_cli",
                     "model": "grok-4.7", "allow_fallback": False},
        "execution_policy": {"one_lane": True},
        "goals": [{"id": "goal.ops", "title": "Ops", "subgoals": [{"id": "sub.ops", "title": "Recovery"}]}],
        "tasks": [{"id": "CIMP-OPS-03", "title": "Recover", "goal_id": "goal.ops", "subgoal_id": "sub.ops",
                   "priority": "P0", "targets": ["integrations/ipfs_accelerate/improvement_runner.py"],
                   "depends_on": [], "acceptance": ["Dead ordinary attempts reconcile without a refund"],
                   "validation_commands": ["python -m pytest -q tests/test_improvement_recovery.py"],
                   "implementation_prompt": "Repair eligible dead claims through native recovery."}],
    })


def _write_campaign(tmp_path, monkeypatch, native_state, *, owned=True, heartbeat=True, started_ago=30):
    state = tmp_path / "state"
    state.mkdir(parents=True)
    spec = tmp_path / "spec.json"
    spec.write_text(_spec_text())
    argv = [sys.executable, "_run", "--state-dir", str(state), "--owner-token", "test-owner"]
    record = {"identity": {**_identity(), "argv": argv}, "argv": argv,
              "owner_token": "test-owner", "started_at": runner.time.time() - started_ago, "status": "starting",
              "native_daemon": {"todo_path": str(tmp_path / "board.md"), "state_path": str(state / f"{runner.STATE_PREFIX}_task_state.json"),
                                "strategy_path": str(state / f"{runner.STATE_PREFIX}_strategy.json"),
                                "events_path": str(state / f"{runner.STATE_PREFIX}_events.jsonl"),
                                "worktree_root": str(tmp_path / "worktrees")}}
    (tmp_path / "board.md").write_text("# Tasks\n\n## CIMP-OPS-03 Example\n\n- Status: ready\n")
    runner._atomic_json(state / "launcher.json", record)
    if native_state is not None:
        runner._atomic_json(state / f"{runner.STATE_PREFIX}_task_state.json", native_state)
    if heartbeat:
        runner._atomic_json(state / f"{runner.STATE_PREFIX}_supervisor_status.json", {
            "status": "running", "supervisor_pid": record["identity"]["pid"],
            "daemon_pid": 991120, "daemon_pid_alive": True,
        })
    identities = {record["identity"]["pid"]: record["identity"]}
    if owned:
        identities[991120] = {**_identity(991120), "ppid": record["identity"]["pid"]}

    def identify(pid):
        return identities.get(pid)

    monkeypatch.setattr(runner, "process_identity", identify)
    monkeypatch.setattr(runner, "_validate_board", lambda *a: {
        "count": 1, "completed": 0, "ready_task_ids": ["CIMP-OPS-03"], "manual_hold_task_ids": [],
    })
    return tmp_path, tmp_path / "spec.json", state, record


def _dead_attempt(**extra):
    birth = {"pid": 424242, "start_ticks": 9, "boot_id": "dead-owner"}
    payload = {"active_task_id": "CIMP-OPS-03", "active_task_cid": "bafyattemptcid",
               "active_attempt": 3, "implementation_in_progress": True, "active_phase": "implementing",
               "active_task_started_at": _stamp(30), "owner_process_birth": birth,
               "implementation_attempts": {"CIMP-OPS-03": 3},
               "implementation_attempts_by_cid": {"bafyattemptcid": 3},
               "active_worktree_path": "/tmp/not-used", "active_log_path": "/tmp/not-used/attempt.log"}
    payload.update(extra)
    return payload


def test_live_pid_without_heartbeat_is_not_healthy(tmp_path, monkeypatch):
    root, spec, state, _ = _write_campaign(tmp_path, monkeypatch, {"active_task_id": "CIMP-OPS-03"}, heartbeat=False)
    result = runner.status(root, spec, state)
    assert result["owned_process_alive"] and result["healthy"] is False
    assert result["worker_liveness"] == "unknown"


def test_grok_frames_bind_to_the_current_attempt_only(tmp_path, monkeypatch):
    started = _stamp(20)
    root, spec, state, _ = _write_campaign(tmp_path, monkeypatch, {
        "active_task_id": "CIMP-OPS-03", "active_task_cid": "bafycurrentcid", "active_attempt": 1,
        "implementation_in_progress": True, "active_phase": "implementing", "active_task_started_at": started,
        "active_worktree_path": str(tmp_path / "work"), "active_log_path": str(state_log(tmp_path)),
    })
    events = state / f"{runner.STATE_PREFIX}_events.jsonl"
    old = {"type": "grok_usage", "provider": "grok_cli", "model": "grok-4.7", "usage": {"input_tokens": 15},
           "tool_frames": 32, "task_id": "CIMP-OPS-03", "task_cid": "bafyoldcid", "attempt": 1,
           "timestamp": _stamp(5), "worktree_path": str(tmp_path / "work"), "log_path": str(state_log(tmp_path))}
    events.write_text(json.dumps(old) + "\n")
    assert runner.status(root, spec, state)["provider_execution_verified"] is False
    task_only = dict(old)
    task_only.pop("task_cid")
    task_only.pop("attempt")
    events.write_text(json.dumps(task_only) + "\n")
    assert runner.status(root, spec, state)["provider_execution_verified"] is False
    current = dict(old, task_cid="bafycurrentcid", timestamp=_stamp(1))
    events.write_text(json.dumps(current) + "\n")
    result = runner.status(root, spec, state)
    assert result["provider_execution_verified"] and result["provider_progress_verified"]
    assert result["progress_verified"] and result["completion_authority"] is False
    assert not result["validation_activity_verified"]


def state_log(tmp_path):
    return tmp_path / "state" / "attempt.log"


def test_validation_activity_is_not_provider_progress(tmp_path, monkeypatch):
    started = _stamp(10)
    log = state_log(tmp_path)
    root, spec, state, _ = _write_campaign(tmp_path, monkeypatch, {
        "active_task_id": "CIMP-OPS-03", "active_task_cid": "bafycurrentcid", "active_attempt": 2,
        "implementation_in_progress": True, "active_phase": "validation", "active_task_started_at": started,
        "active_worktree_path": str(tmp_path / "work"), "active_log_path": str(log),
    })
    event = {"type": "validation_started", "task_id": "CIMP-OPS-03", "task_cid": "bafycurrentcid", "attempt": 2,
             "timestamp": _stamp(1), "worktree_path": str(tmp_path / "work"), "log_path": str(log)}
    (state / f"{runner.STATE_PREFIX}_events.jsonl").write_text(json.dumps(event) + "\n")
    result = runner.status(root, spec, state)
    assert result["validation_activity_verified"] and not result["provider_execution_verified"]
    assert result["application_interview_state"] is None


def test_awaiting_user_is_not_a_stalled_worker(tmp_path, monkeypatch):
    _forbid_dispatch(monkeypatch)
    monkeypatch.setattr(runner, "_open_recovery_daemon", lambda *a, **k: pytest.fail("reconciled interview"))
    root, spec, state, _ = _write_campaign(tmp_path, monkeypatch, _dead_attempt(active_phase="awaiting_user"))
    before = (state / f"{runner.STATE_PREFIX}_task_state.json").read_bytes()
    result = runner.recover_stalled_worker(root, spec, state)
    assert result["recovery"] == "blocked" and result["application_interview_state"] == "awaiting_user"
    assert result["selection_performed"] is False and result["attempt_refunded"] is False
    assert (state / f"{runner.STATE_PREFIX}_task_state.json").read_bytes() == before


@pytest.mark.parametrize("phase,flag", [
    ("manual_hold", None), ("paused", None), ("cancelled", None),
    ("implementing", "manual_hold"), ("implementing", "manual_cancellation"),
    ("implementing", "capacity_quarantine"), ("protected_incident", "protected_incident"),
])
def test_manual_and_protected_states_are_not_recovered(tmp_path, monkeypatch, phase, flag):
    _forbid_dispatch(monkeypatch)
    monkeypatch.setattr(runner, "_open_recovery_daemon", lambda *a, **k: pytest.fail("reconciled held claim"))
    extra = {"active_phase": phase}
    if flag:
        extra[flag] = True
    root, spec, state, _ = _write_campaign(tmp_path, monkeypatch, _dead_attempt(**extra))
    before = (state / f"{runner.STATE_PREFIX}_task_state.json").read_bytes()
    result = runner.recover_stalled_worker(root, spec, state)
    assert result["reconciled"] is False and result["paid_dispatch"] is False
    assert result["counters_preserved"] and result["observed_attempts"]["CIMP-OPS-03"] == 3
    assert (state / f"{runner.STATE_PREFIX}_task_state.json").read_bytes() == before


@pytest.mark.parametrize("kind", ["pid_reuse", "alive", "unknown"])
def test_live_reused_and_unknown_owners_block_recovery(tmp_path, monkeypatch, kind):
    _forbid_dispatch(monkeypatch)
    monkeypatch.setattr(runner, "_open_recovery_daemon", lambda *a, **k: pytest.fail("reconciled unsafe owner"))
    payload = _dead_attempt()
    birth = payload["owner_process_birth"]
    root, spec, state, _ = _write_campaign(tmp_path, monkeypatch, payload, heartbeat=True)
    current = dict(birth)
    if kind == "pid_reuse":
        current["start_ticks"] = 999
    elif kind == "unknown":
        current = {"pid": birth["pid"], "unknown": True}
    elif kind == "alive":
        current = dict(birth)
    original = runner.process_identity

    def identify(pid):
        if pid == birth["pid"]:
            return None if kind == "dead" else current
        return original(pid)

    monkeypatch.setattr(runner, "process_identity", identify)
    result = runner.recover_stalled_worker(root, spec, state)
    assert result["recovery"] == "blocked"
    assert result["reason"] == ("worker_alive" if kind == "alive" else kind)
    assert result["attempt_refunded"] is False and result["selection_performed"] is False


def test_stale_cid_and_proof_are_not_reconciled(tmp_path, monkeypatch):
    _forbid_dispatch(monkeypatch)
    monkeypatch.setattr(runner, "_open_recovery_daemon", lambda *a, **k: pytest.fail("reconciled stale proof"))
    root, spec, state, _ = _write_campaign(tmp_path, monkeypatch, _dead_attempt(claim_task_cid="bafyothercid"))
    result = runner.recover_stalled_worker(root, spec, state)
    assert result["reason"] == "stale_cid" and result["reconciled"] is False
    root, spec, state, _ = _write_campaign(tmp_path / "proof", monkeypatch, _dead_attempt(stale_proof=True))
    assert runner.recover_stalled_worker(root, spec, state)["reason"] == "stale_proof"


def test_observation_error_blocks_without_selection(tmp_path, monkeypatch):
    _forbid_dispatch(monkeypatch)
    monkeypatch.setattr(runner, "_open_recovery_daemon", lambda *a, **k: pytest.fail("reconciled unread state"))
    root, spec, state, _ = _write_campaign(tmp_path, monkeypatch, None)
    (state / f"{runner.STATE_PREFIX}_task_state.json").write_text("{")
    result = runner.recover_stalled_worker(root, spec, state)
    assert result["reason"] == "observation_error" and result["diagnostics"]
    assert result["selection_performed"] is False


def test_lock_contention_and_dependency_use_capped_cooldown(tmp_path, monkeypatch):
    _forbid_dispatch(monkeypatch)
    monkeypatch.setattr(runner, "_open_recovery_daemon", lambda *a, **k: pytest.fail("reconciled during cooldown"))
    root, spec, state, _ = _write_campaign(tmp_path, monkeypatch, _dead_attempt(dependency_status="unavailable"))
    before = (state / f"{runner.STATE_PREFIX}_task_state.json").read_bytes()
    first = runner.recover_stalled_worker(root, spec, state)
    assert first["recovery"] == "cooldown" and first["reason"] == "dependency_unavailable"
    assert 0 < first["cooldown_seconds"] <= 600 and first["progress_preserved"]
    second = runner.recover_stalled_worker(root, spec, state)
    assert second["spinning_prevented"] and second["cooldown_until"] == first["cooldown_until"]
    assert (state / f"{runner.STATE_PREFIX}_task_state.json").read_bytes() == before
    root, spec, state, _ = _write_campaign(tmp_path / "lock", monkeypatch, _dead_attempt())
    held = (state / "recovery.lock").open("a+", encoding="utf-8")
    fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        lock = runner.recover_stalled_worker(root, spec, state)
    finally:
        fcntl.flock(held.fileno(), fcntl.LOCK_UN)
        held.close()
    assert lock["recovery"] == "cooldown" and lock["reason"] == "lock_contention"
    assert lock["cooldown_seconds"] <= 600 and lock["counters_preserved"]


def test_silent_provider_and_validation_do_not_spin_or_drop_progress(tmp_path, monkeypatch):
    _forbid_dispatch(monkeypatch)
    monkeypatch.setattr(runner, "_open_recovery_daemon", lambda *a, **k: pytest.fail("reconciled a live silent worker"))
    provider_state = _dead_attempt(active_task_started_at=_stamp(runner.STALL_SECONDS + 30),
                                   owner_process_birth={"pid": 991120, "start_ticks": 123456, "boot_id": "test-boot"})
    root, spec, state, _ = _write_campaign(tmp_path, monkeypatch, provider_state, started_ago=runner.STALL_SECONDS + 40)
    log = state / "attempt.log"
    log.write_text("generic churn\n")
    payload = json.loads((state / f"{runner.STATE_PREFIX}_task_state.json").read_text())
    payload["active_log_path"] = str(log)
    runner._atomic_json(state / f"{runner.STATE_PREFIX}_task_state.json", payload)
    (state / f"{runner.STATE_PREFIX}_events.jsonl").write_text(json.dumps({
        "type": "watchdog_heartbeat", "task_id": "CIMP-OPS-03", "timestamp": _stamp(1)}) + "\n")
    before = (state / f"{runner.STATE_PREFIX}_task_state.json").read_bytes()
    silent = runner.recover_stalled_worker(root, spec, state)
    assert (silent["recovery"], silent["reason"], silent.get("status"), silent.get("worker_liveness")) == ("cooldown", "silent_provider", "stalled", "alive")
    assert silent["cooldown_scope"] == "provider" and silent["attempt_refunded"] is False
    assert (state / f"{runner.STATE_PREFIX}_task_state.json").read_bytes() == before
    validation_state = dict(provider_state, active_phase="validation")
    root, spec, state, _ = _write_campaign(tmp_path / "validation", monkeypatch, validation_state,
                                          started_ago=runner.STALL_SECONDS + 40)
    stalled = runner.recover_stalled_worker(root, spec, state)
    assert stalled["reason"] == "validation_stall" and stalled["cooldown_scope"] == "validation"
    assert stalled["cooldown_seconds"] <= 600


def test_missing_heartbeat_on_a_live_worker_cools_down_without_refund(tmp_path, monkeypatch):
    _forbid_dispatch(monkeypatch)
    monkeypatch.setattr(runner, "_open_recovery_daemon", lambda *a, **k: pytest.fail("reconciled missing heartbeat"))
    payload = _dead_attempt(owner_process_birth={"pid": 991120, "start_ticks": 123456, "boot_id": "test-boot"},
                            active_task_started_at=_stamp(10))
    root, spec, state, _ = _write_campaign(tmp_path, monkeypatch, payload, heartbeat=False, started_ago=runner.STARTUP_SECONDS + 5)
    result = runner.recover_stalled_worker(root, spec, state)
    assert result["recovery"] == "cooldown" and result["attempt_refunded"] is False
    assert result["observed_attempts"]["CIMP-OPS-03"] == 3


def test_eligible_dead_attempt_reconciles_twice_without_resetting_the_cap(tmp_path, monkeypatch):
    _forbid_dispatch(monkeypatch)
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from test.api.test_agent_supervisor_implementation_protected_paths import (
        POLICY_PATH, _persist_live_shaped_interrupted_attempt, _protected_git_worktree_daemon,
    )
    monkeypatch.setenv(native.AUTOMATIC_RETRY_REARM_ENV, "0")
    reconciler = native.CrashFenceReconciler
    monkeypatch.setattr(native, "CrashFenceReconciler", lambda daemon: reconciler(daemon, max_hold_seconds=10.0))
    daemon, repo, workspace, _protected = _protected_git_worktree_daemon(tmp_path)
    task, _lock, claim_path = _persist_live_shaped_interrupted_attempt(daemon, workspace=workspace, attempt=3)
    state = native.PortalTaskState.load(daemon.state_path)
    assert state.implementation_attempts[task.task_id] == 3
    assert state.implementation_attempts_by_cid[state.active_task_cid] == 3
    birth = json.loads(claim_path.read_text())["owner_process_birth"]
    state_dir = daemon.state_path.parent
    record = {"identity": {"pid": birth["pid"], "start_ticks": birth["start_time_ticks"], "boot_id": birth["boot_id"]},
              "argv": [sys.executable, "_run"], "owner_token": "synthetic-owner", "started_at": runner.time.time() - 50,
              "status": "starting", "native_daemon": {
                  "todo_path": str(daemon.todo_path), "state_path": str(daemon.state_path),
                  "strategy_path": str(daemon.strategy_path), "events_path": str(daemon.events_path),
                  "worktree_root": str(daemon.worktree_root), "implementation_command": "fake-agent",
                  "implementation_protected_paths": [POLICY_PATH]}}
    runner._atomic_json(state_dir / "launcher.json", record)
    monkeypatch.setattr(runner, "process_identity", lambda _pid: None)
    monkeypatch.setattr(runner, "_validate_board", lambda *a: {
        "count": 1, "completed": 0, "ready_task_ids": [task.task_id], "manual_hold_task_ids": [],
    })
    containers = []

    def inventory(state_dir, launcher, *, parent_quiesced=False, **kwargs):
        containers.append({"parent_quiesced": parent_quiesced, "launcher": launcher.get("owner_token")})
        return {"applicable": True, "quiesced": True, "status": "stopped", "containers": [
            {"container_id": "a" * 64, "synthetic": True}], "attempt_refunded": False, "completion_authority": False}

    monkeypatch.setattr("integrations.ipfs_accelerate.improvement_shutdown.close_campaign_containers", inventory)
    spec = tmp_path / "spec.json"
    spec.write_text(_spec_text())
    first = runner.recover_stalled_worker(repo, spec, state_dir)
    # The ready task is not terminal, so native claim release stays fail-closed.
    # The dead attempt is still fenced and the spent cap is not refunded.
    assert first["paid_dispatch"] is False and first["attempt_refunded"] is False
    assert first["reason"] == "task_claim_reconciliation_blocked"
    assert containers and containers[0]["parent_quiesced"] is True
    assert first["fence"]["fenced"] is True
    assert claim_path.is_file()
    after = native.PortalTaskState.load(daemon.state_path)
    cid = state.active_task_cid
    assert after.implementation_attempts[task.task_id] == 3
    assert after.implementation_attempts_by_cid[cid] == 3
    assert not after.completed_task_ids
    second = runner.recover_stalled_worker(repo, spec, state_dir)
    assert second["paid_dispatch"] is False and second["attempt_refunded"] is False
    assert second["selection_performed"] is False
    again = native.PortalTaskState.load(daemon.state_path)
    assert again.implementation_attempts[task.task_id] == 3
    assert again.implementation_attempts_by_cid[cid] == 3
    assert claim_path.is_file()
    assert not again.completed_task_ids


def test_native_protected_mutation_does_not_release_the_attempt(tmp_path, monkeypatch):
    _forbid_dispatch(monkeypatch)
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from test.api.test_agent_supervisor_implementation_protected_paths import (
        POLICY_PATH, _persist_live_shaped_interrupted_attempt, _protected_git_worktree_daemon,
    )
    monkeypatch.setenv(native.AUTOMATIC_RETRY_REARM_ENV, "0")
    reconciler = native.CrashFenceReconciler
    monkeypatch.setattr(native, "CrashFenceReconciler", lambda daemon: reconciler(daemon, max_hold_seconds=10.0))
    daemon, repo, workspace, protected = _protected_git_worktree_daemon(tmp_path)
    task, _lock, claim_path = _persist_live_shaped_interrupted_attempt(daemon, workspace=workspace, attempt=3)
    protected.write_text("mutated-without-authority\n", encoding="utf-8")
    birth = json.loads(claim_path.read_text())["owner_process_birth"]
    state_dir = daemon.state_path.parent
    runner._atomic_json(state_dir / "launcher.json", {
        "identity": {"pid": birth["pid"], "start_ticks": birth["start_time_ticks"], "boot_id": birth["boot_id"]},
        "argv": [sys.executable], "owner_token": "synthetic-owner", "started_at": runner.time.time() - 20,
        "native_daemon": {"todo_path": str(daemon.todo_path), "state_path": str(daemon.state_path),
                          "strategy_path": str(daemon.strategy_path), "events_path": str(daemon.events_path),
                          "worktree_root": str(daemon.worktree_root), "implementation_command": "fake-agent",
                          "implementation_protected_paths": [POLICY_PATH]}})
    monkeypatch.setattr(runner, "process_identity", lambda _pid: None)
    monkeypatch.setattr(runner, "_validate_board", lambda *a: {
        "count": 1, "completed": 0, "ready_task_ids": [task.task_id], "manual_hold_task_ids": [],
    })
    monkeypatch.setattr("integrations.ipfs_accelerate.improvement_shutdown.close_campaign_containers",
                        lambda *a, **k: {"applicable": True, "quiesced": True, "containers": [], "attempt_refunded": False})
    before = native.PortalTaskState.load(daemon.state_path)
    result = runner.recover_stalled_worker(repo, tmp_path / "spec.json", state_dir)
    after = native.PortalTaskState.load(daemon.state_path)
    assert result["reconciled"] is False and result["attempt_refunded"] is False
    assert after.implementation_attempts[task.task_id] == before.implementation_attempts[task.task_id] == 3
    assert after.implementation_attempts_by_cid == before.implementation_attempts_by_cid
    assert not after.completed_task_ids
