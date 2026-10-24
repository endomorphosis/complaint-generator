"""Observe real watchdog policy while keeping campaign effects in a fixture."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from integrations.ipfs_accelerate import campaign_watchdog as module


def _adapter(tmp_path, monkeypatch, *, state="stalled", hold=False, completed=False):
    from ipfs_accelerate_py.agent_supervisor.prompt.prompt_workflow import prompt_workflow_cid
    watcher = object.__new__(module.ComplaintCampaignWatchdog)
    watcher.root = tmp_path
    watcher.state = tmp_path
    watcher.directory = tmp_path / "watchdog"
    watcher.spec_path = tmp_path / "spec.json"
    watcher.spec_path.write_text('{}')
    watcher.spec_sha = module.hashlib.sha256(b'{}').hexdigest()
    watcher.plan_id = "test-plan"
    watcher.artifacts = SimpleNamespace(board_relative="board.md")
    watcher.scope = {k: prompt_workflow_cid({"kind": k}) for k in
        ("repository_root_cid", "policy_root", "run_cid")}
    watcher.clock = lambda: 1000.0
    watcher.latest_status = watcher.latest_observation = watcher.latest_completion = {}
    watcher.last_action = {}
    monkeypatch.setattr(watcher, "_mark_automatic_stop", lambda _: None)
    task = SimpleNamespace(task_id="TASK-1", status="completed" if completed else "todo")
    view = {"status": "complete" if completed else state, "healthy": completed,
        "worker_liveness": "dead", "native_read_errors": {}, "board": {"completed": int(completed), "count": 1},
        "native_state": {"active_task_id": "", "active_task_cid": "", "active_attempt": 0,
            "manual_hold": hold, "implementation_in_progress": False}}
    runner = SimpleNamespace(status=lambda *_: deepcopy(view),
        _native_modules=lambda *_: (None, SimpleNamespace(parse_task_file=lambda *a, **k: [task])),
        TASK_PREFIX="## TASK-", STARTUP_SECONDS=90,
        _event_timestamp=lambda _: None,
        _claim_proof_conflict=lambda _: None,
        _atomic_json=lambda p, x: p.write_text(json.dumps(x)), owns_process=lambda _: True)
    watcher.runner = runner
    monkeypatch.setattr(watcher, "_launch", lambda: ({"started_at": 0, "status": "running"}, True, "owner-1"))
    return watcher, runner, view


def test_native_board_complete_needs_authenticated_completion(tmp_path, monkeypatch):
    from integrations.ipfs_accelerate import campaign_completion
    watcher, runner, view = _adapter(tmp_path, monkeypatch, completed=True)
    monkeypatch.setattr(campaign_completion, "verify_campaign_completion", lambda *a: {"verified": False})
    observed = watcher.observe()
    assert not observed["completion_verified"]
    assert not observed["recovery_permitted"]
    result = watcher.run_once()
    assert result["status"] == "refused"
    assert result["reason"] == "campaign_completion_unverified"


def test_complete_tick_uses_proof_and_owned_cleanup_without_recovery(tmp_path, monkeypatch):
    from integrations.ipfs_accelerate import campaign_completion
    watcher, runner, _ = _adapter(tmp_path, monkeypatch, completed=True)
    monkeypatch.setattr(campaign_completion, "verify_campaign_completion", lambda *a: {"verified": True})
    calls = []
    runner.stop = lambda state, **kw: calls.append(state) or {"status": "stopped", "container_shutdown": {"quiesced": True}}
    monkeypatch.setattr(watcher, "recover", lambda *_: pytest.fail("completed campaign dispatched recovery"))
    result = watcher.run_once(stop_completed=True)
    assert result["status"] == "complete" and result["completion_cleanup"]["quiesced"] is True
    assert calls == [tmp_path]
    assert not (watcher.directory / "campaign-progress-watchdog.json").exists()


@pytest.mark.parametrize("reason", ["manual_hold", "capacity_quarantine", "protected_incident", "awaiting_user"])
def test_intentional_wait_never_stops_or_restarts(tmp_path, monkeypatch, reason):
    watcher, runner, view = _adapter(tmp_path, monkeypatch)
    if reason == "awaiting_user":
        view["application_interview_state"] = "awaiting_user"
    else:
        view["native_state"][reason] = True
    monkeypatch.setattr(watcher, "recover", lambda *_: pytest.fail("hold dispatched recovery"))
    result = watcher.run_once()
    assert result["status"] == "held" and result["reason"] == reason


def test_observation_token_excludes_polling_heartbeat_and_age(tmp_path, monkeypatch):
    watcher, _, view = _adapter(tmp_path, monkeypatch)
    first = watcher.observe()
    view.update(native_heartbeat_age_seconds=0.002, observed_activity_age_seconds=1000)
    view["native_state"].update(heartbeat_at="new-poll", last_progress_at="new-poll")
    assert watcher.observe() == first
    view["provider_execution_evidence"] = {"frame_counts": {"usage": 1}, "log_bytes": 80}
    assert watcher.observe()["progress_token"] != first["progress_token"]


@pytest.mark.parametrize("damage", ["owner", "hold", "progress"])
def test_changed_observation_refuses_effects(tmp_path, monkeypatch, damage):
    watcher, runner, view = _adapter(tmp_path, monkeypatch)
    watcher.observe()
    runner.stop = lambda *_: pytest.fail("changed observation signalled owner")
    if damage == "owner":
        monkeypatch.setattr(watcher, "_launch", lambda: ({"started_at": 0}, True, "replacement"))
    elif damage == "hold":
        view["native_state"]["manual_hold"] = True
    else:
        view["provider_execution_evidence"] = {"frame_counts": {"usage": 1}}
    result = watcher.recover(SimpleNamespace(deadline_at_ms=2_000_000))
    assert not result.succeeded and result.reason == "campaign_changed_before_stop"


@pytest.mark.parametrize("blocked_stage", ["stop", "recover", "doctor"])
def test_recovery_stages_require_native_acceptance_and_preserve_accounting(tmp_path, monkeypatch, blocked_stage):
    watcher, runner, _ = _adapter(tmp_path, monkeypatch)
    watcher.spec = {}
    watcher.observe()
    calls = []
    monkeypatch.setattr(watcher, "_accounting", lambda: {"implementation_attempts": {"TASK-1": 2}})
    runner.stop = lambda *_, **kw: calls.append("stop") or {"status": "stop_incomplete" if blocked_stage == "stop" else "stopped"}
    runner.recover_stalled_worker = lambda *_: calls.append("recover") or {"recovery": "blocked" if blocked_stage == "recover" else "reconciled"}
    runner.doctor = lambda *_: calls.append("doctor") or {"status": "not_ready" if blocked_stage == "doctor" else "ready"}
    runner.start = lambda *_: pytest.fail("Native refusal authorized restart")
    result = watcher.recover(SimpleNamespace(deadline_at_ms=2_000_000))
    assert not result.succeeded
    assert calls == ["stop", "recover", "doctor"][:{"stop": 1, "recover": 2, "doctor": 3}[blocked_stage]]


def test_accounting_change_never_restarts(tmp_path, monkeypatch):
    watcher, runner, _ = _adapter(tmp_path, monkeypatch)
    watcher.observe()
    values = iter([{"paid": 2}, {"paid": 0}])
    monkeypatch.setattr(watcher, "_accounting", lambda: next(values))
    runner.stop = lambda *_, **kw: {"status": "stopped"}
    runner.recover_stalled_worker = lambda *_: {"recovery": "reconciled"}
    runner.start = lambda *_: pytest.fail("changed accounting authorized restart")
    with pytest.raises(RuntimeError, match="accounting_changed"):
        watcher.recover(SimpleNamespace(deadline_at_ms=2_000_000))


def test_restart_requires_native_reconciliation_and_real_followup_progress(tmp_path, monkeypatch):
    watcher, runner, view = _adapter(tmp_path, monkeypatch)
    watcher.observe()
    calls = []
    monkeypatch.setattr(watcher, "_accounting", lambda: {"attempts": 2})
    runner.stop = lambda *_, **kw: calls.append("stop") or {"status": "stopped"}
    runner.recover_stalled_worker = lambda *_: calls.append("recover") or {"recovery": "reconciled"}
    runner.doctor = lambda *_: calls.append("doctor") or {"status": "ready"}
    def start(*_, **kw):
        calls.append("start")
        view.update(status="active", healthy=True, provider_progress_verified=True)
        view["native_state"].update(active_task_id="TASK-1", active_task_cid="current-task-cid", active_attempt=2)
        return {"status": "starting"}
    runner.start = start
    result = watcher.recover(SimpleNamespace(deadline_at_ms=2_000_000))
    assert result.succeeded and result.healthy
    assert result.observed_effects == ("old_lane_fenced", "lane_restarted")
    assert calls == ["stop", "recover", "doctor", "start"]


def test_recovery_deadline_prevents_even_owned_stop(tmp_path, monkeypatch):
    watcher, runner, _ = _adapter(tmp_path, monkeypatch)
    watcher.observe()
    monkeypatch.setattr(watcher, "_accounting", lambda: {})
    runner.stop = lambda *_: pytest.fail("expired action signalled owner")
    with pytest.raises(TimeoutError):
        watcher.recover(SimpleNamespace(deadline_at_ms=999_999))


def test_manual_stop_is_held_but_verified_automatic_stop_can_resume(tmp_path, monkeypatch):
    watcher, runner, view = _adapter(tmp_path, monkeypatch, state="stopped")
    monkeypatch.setattr(watcher, "_launch", lambda: ({"started_at": 0, "status": "stopped"}, True, "owner-1"))
    monkeypatch.setattr(watcher, "_automatic_stop_matches", lambda *_: False)
    assert watcher.observe()["hold_reason"] == "manual_hold"
    monkeypatch.setattr(watcher, "_automatic_stop_matches", lambda *_: True)
    runner.doctor = lambda *_: {"status": "ready"}
    result = watcher.observe()
    assert result["recovery_permitted"] and not result["manual_hold"]
    runner.doctor = lambda *_: {"status": "not_ready"}
    assert watcher.observe()["hold_reason"] == "dependency_unavailable"


@pytest.mark.parametrize("change", ["hold", "owner"])
def test_doctor_cannot_override_new_hold_or_replacement_owner(tmp_path, monkeypatch, change):
    watcher, runner, view = _adapter(tmp_path, monkeypatch)
    watcher.observe()
    monkeypatch.setattr(watcher, "_accounting", lambda: {"attempts": 2})
    runner.stop = lambda *a, **kw: {"status": "stopped"}
    runner.recover_stalled_worker = lambda *_: {"recovery": "reconciled"}
    def doctor(*_):
        if change == "hold":
            view["native_state"]["manual_hold"] = True
        else:
            monkeypatch.setattr(watcher, "_launch", lambda: ({"started_at": 0}, True, "new-owner"))
        return {"status": "ready"}
    runner.doctor = doctor
    runner.start = lambda *a, **kw: pytest.fail("doctor overrode current campaign control")
    result = watcher.recover(SimpleNamespace(deadline_at_ms=2_000_000))
    assert not result.succeeded and result.reason == "campaign_changed_before_restart"


@pytest.mark.parametrize("operation", ["start", "stop"])
def test_native_effect_cas_runs_under_launcher_lock(tmp_path, monkeypatch, operation):
    from contextlib import contextmanager
    from integrations.ipfs_accelerate import improvement_runner as runner
    state = tmp_path / "campaign"
    state.mkdir()
    original = {"owner": "first"}
    (state / "launcher.json").write_text(json.dumps(original))
    @contextmanager
    def raced_lock(*a, **kw):
        (state / "launcher.json").write_text(json.dumps({"owner": "replacement"}))
        yield
    monkeypatch.setattr(runner, "_lock", raced_lock)
    monkeypatch.setattr(runner, "_signal_birth", lambda *a: pytest.fail("replacement owner signalled"))
    if operation == "start":
        monkeypatch.setattr(runner, "_select_worktree_root", lambda *a: (tmp_path, None))
        monkeypatch.setattr(runner, "_resource_capacity", lambda *a: {"ready": True})
        result = runner.start(tmp_path, tmp_path / "spec", state,
            expected_launcher_sha256=module._digest(original))
    else:
        result = runner.stop(state, expected_launcher_sha256=module._digest(original))
    assert result["status"] == "stop_incomplete"
    assert result["reason"] == "launcher_changed_before_" + operation


def test_hold_created_during_native_preflight_prevents_spawn(tmp_path, monkeypatch):
    from integrations.ipfs_accelerate import improvement_runner as runner, improvement_plan
    state = tmp_path / "campaign"
    state.mkdir()
    (state / "launcher.json").write_text('{}')
    monkeypatch.setattr(runner, "_select_worktree_root", lambda *a: (tmp_path, None))
    monkeypatch.setattr(runner, "_resource_capacity", lambda *a: {"ready": True})
    monkeypatch.setattr(runner, "owns_process", lambda *_: False)
    monkeypatch.setattr(runner, "_observe_campaign_containers", lambda *a: True)
    monkeypatch.setattr(runner, "process_identity", lambda *_: None)
    monkeypatch.setattr(runner, "prepare", lambda *a: {"board_path": str(tmp_path / "board")})
    def doctor(*a, **kw):
        (state / "watchdog").mkdir()
        (state / "watchdog/HOLD").write_text('operator hold')
        return {"status": "ready", "merge_target": "test", "native_plan_id": "plan"}
    monkeypatch.setattr(runner, "doctor", doctor)
    monkeypatch.setattr(improvement_plan, "load_spec", lambda *_: {"execution_policy": {}})
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **kw: pytest.fail("held campaign spawned"))
    result = runner.start(tmp_path, tmp_path / "spec", state, expected_launcher_sha256=module._digest({}))
    assert result["status"] == "not_ready" and result["reason"] == "watchdog_manual_hold"
    assert result["execution_started"] is False


def test_units_bind_campaign_and_do_not_kill_detached_native_owner(tmp_path):
    root = tmp_path / "repo with spaces"
    root.mkdir()
    spec = root / "spec.json"
    spec.write_text('{}')
    state = tmp_path / "campaign"
    state.mkdir()
    units = module.systemd_units(root, spec, state, interpreter="/usr/bin/python3", plan_id="plan", spec_sha256="ab" * 32)
    assert "KillMode=process\n" in units["service"]
    assert '"watchdog" "--once" "--stop-completed"' in units["service"]
    assert '"--expected-plan-id" "plan"' in units["service"]
    assert '"--expected-spec-sha256"' in units["service"]
    assert "TimeoutStartSec=1800" in units["service"]
    assert "WorkingDirectory=" + str(root) + "\n" in units["service"]
    assert "Persistent=true" in units["timer"] and "OnCalendar=*-*-* *:*:00" in units["timer"]


def _install_fixture(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    spec = root / "spec.json"
    spec.write_text('{}')
    state = tmp_path / "campaign"
    state.mkdir()
    watcher = SimpleNamespace(root=root, spec_path=spec, state=state, directory=state / "watchdog",
        plan_id="plan", spec_sha="ab" * 32)
    monkeypatch.setattr(module, "ComplaintCampaignWatchdog", lambda *a, **kw: watcher)
    return watcher, tmp_path / "units"


def test_installer_verifies_enables_and_runs_only_its_dedicated_unit(tmp_path, monkeypatch):
    watcher, folder = _install_fixture(tmp_path, monkeypatch)
    commands = []
    result = module.install_user_timer(watcher.root, watcher.spec_path, watcher.state,
        interpreter="/usr/bin/python3", unit_directory=folder,
        command_runner=lambda args, **kw: commands.append(args))
    name = result["unit"]
    assert [c[:3] for c in commands] == [["systemd-analyze", "--user", "verify"],
        ["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable"],
        ["systemctl", "--user", "start"]]
    assert commands[2][-1] == name + ".timer" and commands[3][-1] == name + ".service"
    assert set(p.name for p in folder.iterdir()) == {name + ".service", name + ".timer"}
    commands.clear()
    assert module.install_user_timer(watcher.root, watcher.spec_path, watcher.state,
        interpreter="/usr/bin/python3", unit_directory=folder,
        command_runner=lambda args, **kw: commands.append(args))["unit"] == name


def test_installer_preserves_conflicting_existing_units(tmp_path, monkeypatch):
    watcher, folder = _install_fixture(tmp_path, monkeypatch)
    units = module.systemd_units(watcher.root, watcher.spec_path, watcher.state,
        interpreter="/usr/bin/python3", plan_id="plan", spec_sha256="ab" * 32)
    folder.mkdir()
    timer = folder / (units["name"] + ".timer")
    timer.write_text('an existing user unit')
    with pytest.raises(ValueError, match="existing_unit_conflict"):
        module.install_user_timer(watcher.root, watcher.spec_path, watcher.state,
            interpreter="/usr/bin/python3", unit_directory=folder,
            command_runner=lambda *a, **kw: pytest.fail("conflicting unit enabled"))
    assert timer.read_text() == 'an existing user unit'
    assert not (folder / (units["name"] + ".service")).exists()


def test_rendered_units_pass_installed_systemd_parser_with_spaced_paths(tmp_path):
    import shutil
    import subprocess
    assert shutil.which("systemd-analyze"), "systemd parser required for installer validation"
    root = tmp_path / "repo with spaces"
    root.mkdir()
    spec = root / "spec.json"
    spec.write_text('{}')
    state = tmp_path / "campaign with spaces"
    state.mkdir()
    units = module.systemd_units(root, spec, state, interpreter="/usr/bin/python3", plan_id="plan", spec_sha256="ab" * 32)
    paths = []
    for kind in ("service", "timer"):
        path = tmp_path / (units["name"] + "." + kind)
        path.write_text(units[kind])
        paths.append(str(path))
    result = subprocess.run(["systemd-analyze", "--user", "verify", *paths], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
