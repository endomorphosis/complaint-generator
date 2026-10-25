"""Progress checks and verified recovery for one complaint supervisor campaign.

Native remains the authority for process fencing, task attempts, validation,
merge and completion. This adapter never edits those records or calls a model.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import time


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _watchdog_executable_path(interpreter, environment=None):
    """Bind public executable locations without inheriting shell/cwd authority.

    A user service does not inherit the interactive shell's PATH. Keep the
    selected command's directory (including a Grok symlink's directory), not
    the resolved script's directory. This does not change validation's
    separately sealed executable search path or copy any credentials.
    """
    source = os.environ if environment is None else environment
    executable = Path(interpreter)
    if not executable.is_absolute():
        raise ValueError("watchdog_interpreter_not_absolute")
    provider = shutil.which(source.get("IPFS_ACCELERATE_AGENT_GROK_BIN") or "grok",
                          path=source.get("PATH", os.defpath))
    if not provider:
        raise ValueError("watchdog_grok_executable_unavailable")
    selected = [executable, Path(provider)]
    for command in ("node", "docker", "git"):
        found = shutil.which(command, path=source.get("PATH", os.defpath))
        if found:
            selected.append(Path(found))
    if any(not item.is_absolute() for item in selected):
        raise ValueError("watchdog_executable_path_invalid")
    directories = []
    for path in [*(item.absolute().parent for item in selected),
                 *(Path(part) for part in os.defpath.split(os.pathsep) if part)]:
        if not path.is_absolute() or any(c in str(path) for c in "\n\r\0"):
            raise ValueError("watchdog_executable_path_invalid")
        directory = str(path.resolve(strict=True))
        if not path.is_dir() or os.pathsep in directory:
            raise ValueError("watchdog_executable_path_invalid")
        if directory not in directories:
            directories.append(directory)
    return os.pathsep.join(directories)


def _preflight_summary(check):
    """Return closed diagnostic metadata; never serialize auth/config bodies."""
    if not isinstance(check, dict):
        check = {}
    def observed_boolean(value):
        return value if type(value) is bool else None
    def nested(key, member):
        value = check.get(key)
        return observed_boolean(value.get(member)) if isinstance(value, dict) else None
    flags = {
        "grok_binary_present": observed_boolean(check.get("grok_binary_present")),
        "auth_material_present": observed_boolean(check.get("auth_material_present")),
        "private_runtime_ready": nested("privacy", "ready"),
        "worktree_capacity_sufficient": nested("worktree_capacity", "sufficient"),
        "resource_capacity_ready": nested("resource_capacity", "ready"),
    }
    codes = {
        "grok_binary_present": "grok_executable_missing",
        "auth_material_present": "provider_auth_material_missing",
        "private_runtime_ready": "private_runtime_unavailable",
        "worktree_capacity_sufficient": "worktree_capacity_insufficient",
        "resource_capacity_ready": "resource_capacity_unavailable",
    }
    raw_status = check.get("status")
    status = raw_status if type(raw_status) is str and raw_status in {"ready", "not_ready"} else "unknown"
    reasons = [codes[key] for key, value in flags.items() if value is False]
    if status != "ready" and not reasons:
        reasons = ["preflight_not_ready" if status == "not_ready" else "preflight_status_unknown"]
    return {"status": status, "reasons": reasons, **flags}


class ComplaintCampaignWatchdog:
    def __init__(self, repo_root, spec_path, state_dir, *, expected_spec_sha256=None,
                 expected_plan_id=None, clock=None):
        from . import improvement_runner as runner
        self.runner = runner
        self.root, self.spec_path, self.state = (Path(p).resolve(strict=True)
            for p in (repo_root, spec_path, state_dir))
        self.spec, self.artifacts = runner._campaign_spec(self.root, self.spec_path)
        self.spec_sha = hashlib.sha256(self.spec_path.read_bytes()).hexdigest()
        runner._native_modules(self.root)
        from .improvement_plan import build_improvement_work_plan
        self.plan_id = build_improvement_work_plan(self.spec).plan_id
        if ((expected_spec_sha256 and expected_spec_sha256 != self.spec_sha)
                or (expected_plan_id and expected_plan_id != self.plan_id)):
            raise ValueError("watchdog_campaign_contract_changed")
        self.clock = clock or time.time
        from ipfs_accelerate_py.agent_supervisor.prompt.prompt_workflow import prompt_workflow_cid
        self.scope = {
            "repository_root_cid": prompt_workflow_cid({"repo_root": str(self.root)}),
            "policy_root": prompt_workflow_cid({"schema": "complaint-campaign-watchdog-policy@1",
                "plan_id": self.plan_id, "spec_sha256": self.spec_sha,
                "implementation_attempts_unchanged": True, "confirmations": 2,
                "max_recoveries_per_incident": 2}),
            "run_cid": prompt_workflow_cid({"state_dir": str(self.state), "plan_id": self.plan_id}),
        }
        self.directory = self.state / "watchdog"
        self.latest_status = {}
        self.latest_completion = {}
        self.latest_observation = {}
        self.last_action = {}
        self.latest_preflight = {}

    def _contract_current(self):
        if hashlib.sha256(self.spec_path.read_bytes()).hexdigest() != self.spec_sha:
            raise ValueError("watchdog_campaign_contract_changed")

    def _launch(self):
        from .improvement_shutdown import _context
        value = self.runner._read_json(self.state / "launcher.json")
        bound = bool(not value.get("read_error") and self.runner._full_launch_record(value)
            and self.runner._campaign_tuple_matches(value, self.root, self.spec_path, self.state)
            and _context(self.state, value) is not None)
        token = _digest({key: value.get(key) for key in
            ("identity", "started_at", "repo_root", "state_dir", "plan_id", "worktree_root_binding")})
        return value, bound, token

    def _automatic_stop_matches(self, launch, token):
        from .improvement_recovery import _owned_bytes
        try:
            value = json.loads(_owned_bytes(self.directory / "automatic-stop.json", 8192))
            shutdown = self.runner._read_json(self.state / "container_shutdown.json")
            return bool(value == {"schema": "complaint-watchdog-owned-stop@1", "scope": self.scope,
                    "owner_token": token, "launcher_sha256": _digest(launch)}
                and self.runner._shutdown_verified(launch, shutdown, self.root, self.state))
        except (OSError, ValueError, TypeError, KeyError):
            return False

    def _mark_automatic_stop(self, token):
        launch, bound, current = self._launch()
        shutdown = self.runner._read_json(self.state / "container_shutdown.json")
        if (not bound or current != token or launch.get("status") != "stopped"
                or not self.runner._shutdown_verified(launch, shutdown, self.root, self.state)):
            raise RuntimeError("watchdog_automatic_stop_unverified")
        self.runner._atomic_json(self.directory / "automatic-stop.json", {
            "schema": "complaint-watchdog-owned-stop@1", "scope": self.scope,
            "owner_token": token, "launcher_sha256": _digest(launch)})

    def observe(self):
        self._contract_current()
        self.latest_preflight = {}
        status = self.runner.status(self.root, self.spec_path, self.state)
        self.latest_status = status
        launch, bound, owner = self._launch()
        self.latest_launcher = launch
        native = status.get("native_state") or {}
        tasks = self.runner._native_modules(self.root)[1].parse_task_file(
            self.root / self.artifacts.board_relative, task_header_prefix=self.runner.TASK_PREFIX)
        pending = sorted(t.task_id for t in tasks if t.status != "completed")
        completed = False
        self.latest_completion = {}
        if not pending:
            from .campaign_completion import verify_campaign_completion
            self.latest_completion = verify_campaign_completion(self.root, self.spec_path, self.state)
            completed = self.latest_completion.get("verified") is True
        phase = str(native.get("active_phase") or "").lower()
        waiting = status.get("application_interview_state")
        automatic_stop = bool(launch.get("status") == "stopped"
            and self._automatic_stop_matches(launch, owner))
        hold = ""
        if os.path.lexists(self.directory / "HOLD") or os.path.lexists(self.directory / "OPERATOR_STOP"):
            hold = "manual_hold"
        elif native.get("manual_hold") or status.get("board", {}).get("manual_hold_task_ids"):
            hold = "manual_hold"
        elif native.get("manual_cancellation") or waiting == "cancelled":
            hold = "cancelled"
        elif waiting in {"awaiting_user", "waiting_for_user", "paused", "manual_hold"}:
            hold = "awaiting_user" if waiting in {"awaiting_user", "waiting_for_user"} else "manual_hold"
        elif native.get("capacity_quarantine") or phase == "capacity_quarantine":
            hold = "capacity_quarantine"
        elif native.get("protected_incident") or phase == "protected_incident":
            hold = "protected_incident"
        elif str(native.get("dependency_status") or "").lower() in {"unavailable", "temporary_unavailable", "degraded"}:
            hold = "dependency_unavailable"
        elif launch.get("status") == "stopped" and pending and not automatic_stop:
            # An operator's deliberate stop is not an unexpected owner death.
            hold = "manual_hold"
        elif automatic_stop and pending:
            check = self.runner.doctor(self.root, self.spec_path, self.state)
            self.latest_preflight = _preflight_summary(check)
            if check.get("status") != "ready":
                hold = "dependency_unavailable"
        active = str(native.get("active_task_id") or "")
        cid = str(native.get("active_task_cid") or "")
        if not active or not cid:
            active = cid = ""
        provider = status.get("provider_execution_evidence") or {}
        validation = status.get("validation_activity_evidence") or {}
        progress = _digest({"pending": pending, "task": active, "cid": cid,
            "attempt": native.get("active_attempt", 0), "phase": phase,
            "provider": {k: provider.get(k) for k in ("frame_counts", "log_bytes", "provider_terminal_observed")},
            "validation": {k: validation.get(k) for k in ("activity_id", "binding_sha256", "type")}})
        state = str(status.get("status") or "unknown")
        if state not in {"waiting_for_user", "manual_hold", "paused", "cancelled", "capacity_quarantine",
                "protected_incident", "budget_exhausted", "blocked", "active", "post_provider", "running",
                "maintenance", "selected", "starting", "stalled", "no_progress", "daemon_failed", "stopped",
                "complete", "identity_mismatch", "state_error", "board_error", "stop_incomplete", "unknown"}:
            state = "unknown"
        permitted = bool(bound and pending and not hold and not status.get("native_read_errors")
            and not self.runner._claim_proof_conflict(native)
            and status.get("worker_liveness") not in {"unknown", "pid_reuse"}
            and (state in {"stalled", "no_progress", "daemon_failed"}
                 or (state == "stopped" and automatic_stop)))
        selected_at = self.runner._event_timestamp({"timestamp": native.get("active_task_started_at")}) or 0
        grace_started = max(float(launch.get("started_at") or 0), selected_at)
        # A live heartbeat can coexist with an orphaned claim or an idle
        # selector. Logical ready work distinguishes that mechanical block
        # from a task genuinely waiting for dependencies or user input.
        if (state in {"blocked", "running"} and not hold and pending
                and status.get("board", {}).get("ready_task_ids")
                and not active and not native.get("implementation_in_progress")
                and not status.get("provider_progress_verified")
                and not status.get("validation_activity_verified")
                and self.clock() >= grace_started + self.runner.STALL_SECONDS):
            state = "no_progress"
            permitted = bool(bound and not status.get("native_read_errors")
                and not self.runner._claim_proof_conflict(native)
                and status.get("worker_liveness") not in {"unknown", "pid_reuse"})
        result = {"schema": "campaign-progress-observation@1", "scope": dict(self.scope),
            "status": "complete" if completed else state, "healthy": completed or status.get("healthy") is True,
            "completion_verified": completed, "manual_hold": bool(hold), "hold_reason": hold,
            "progress_verified": False if completed else bool(status.get("provider_progress_verified")
                or status.get("validation_activity_verified")),
            "owner_binding_verified": bound, "recovery_permitted": permitted,
            "pending_task_ids": pending, "active_task_id": "" if completed else active,
            "active_task_cid": "" if completed else cid,
            "attempt": 0 if completed else int(native.get("active_attempt") or 0),
            "progress_token": progress, "owner_token": owner,
            "grace_until_ms": int((grace_started + self.runner.STARTUP_SECONDS) * 1000)}
        self.latest_observation = result
        return result

    def _accounting(self):
        value, _ = self.runner._read_native_state(self.root,
            self.state / f"{self.runner.STATE_PREFIX}_task_state.json")
        if value.get("read_error"):
            raise RuntimeError("watchdog_native_accounting_unavailable")
        keys = ("implementation_attempts", "implementation_attempts_by_cid", "protected_implementation_attempts",
            "retry_budget_repair_receipts", "retry_budget_repair_rearm_receipts",
            "stale_proposal_replay_rearm_receipts", "validation_obsolescence_rearm_receipts")
        return {k: value.get(k, {}) for k in keys}

    def recover(self, context):
        from ipfs_accelerate_py.agent_supervisor.rescue.supervisor_recovery import RecoveryActionObservation
        effects = []
        action = self.last_action = {"stage": "before_stop", "provider_dispatched_by_watchdog": False}
        expected = self.latest_observation
        current = self.observe()
        if current != expected or not current["recovery_permitted"]:
            return RecoveryActionObservation(False, reason="campaign_changed_before_stop")
        before = self._accounting()
        deadline = context.deadline_at_ms / 1000
        def remaining():
            if self.clock() >= deadline:
                raise TimeoutError("watchdog_action_deadline")
        remaining()
        if self.observe() != expected:
            return RecoveryActionObservation(False, reason="campaign_changed_during_accounting")
        stopped = self.runner.stop(self.state, expected_launcher_sha256=_digest(self.latest_launcher))
        action.update(stage="stopped", stop_status=stopped.get("status"))
        if stopped.get("status") != "stopped":
            return RecoveryActionObservation(False, reason="owned_stop_incomplete")
        effects.append("old_lane_fenced")
        self._mark_automatic_stop(expected["owner_token"])
        remaining()
        action["stage"] = "reconcile"
        recovered = self.runner.recover_stalled_worker(self.root, self.spec_path, self.state)
        action.update(recovery_status=recovered.get("recovery"), recovery_reason=recovered.get("reason"))
        if self._accounting() != before:
            raise RuntimeError("watchdog_native_accounting_changed_before_restart")
        remaining()
        after = self.observe()
        if after["completion_verified"]:
            action["stage"] = "completed_during_reconciliation"
            return RecoveryActionObservation(True, tuple(effects), {"healthy": True}, reason="verified_completion")
        if after["manual_hold"]:
            return RecoveryActionObservation(False, tuple(effects), reason="hold_introduced_during_recovery")
        # Only verified reconciliation or an ordinary closed empty execution
        # may resume. All refusal reasons retain their holds and evidence.
        if recovered.get("recovery") != "reconciled":
            return RecoveryActionObservation(False, tuple(effects), reason="native_reconciliation_refused")
        action["stage"] = "doctor"
        check = self.runner.doctor(self.root, self.spec_path, self.state)
        self.latest_preflight = _preflight_summary(check)
        action["preflight"] = self.latest_preflight
        if check.get("status") != "ready":
            return RecoveryActionObservation(False, tuple(effects), reason="native_preflight_not_ready")
        remaining()
        restart_view = self.observe()
        if restart_view["completion_verified"]:
            return RecoveryActionObservation(True, tuple(effects), {"healthy": True}, reason="verified_completion")
        if (restart_view["owner_token"] != expected["owner_token"] or restart_view["manual_hold"]
                or not restart_view["owner_binding_verified"] or not restart_view["recovery_permitted"]):
            return RecoveryActionObservation(False, tuple(effects), reason="campaign_changed_before_restart")
        if self._accounting() != before:
            raise RuntimeError("watchdog_native_accounting_changed_before_restart")
        remaining()
        action["stage"] = "start"
        started = self.runner.start(self.root, self.spec_path, self.state,
            expected_launcher_sha256=_digest(self.latest_launcher))
        action["start_status"] = started.get("status")
        if started.get("status") not in {"starting", "already_running"}:
            return RecoveryActionObservation(False, tuple(effects), reason="native_restart_refused")
        effects.append("lane_restarted")
        # A PID is not recovery. Observe genuine work, or a bounded start that
        # remains visible to subsequent timer checks without spending a retry.
        action["stage"] = "observe_restart"
        until = min(deadline, self.clock() + self.runner.STARTUP_SECONDS)
        while self.clock() < until:
            view = self.observe()
            if view["completion_verified"] or (view["healthy"] and view["progress_verified"]):
                action["stage"] = "verified_progress"
                return RecoveryActionObservation(True, tuple(effects), {"healthy": True})
            if view["manual_hold"] or view["status"] in {"daemon_failed", "state_error", "identity_mismatch", "stop_incomplete"}:
                break
            time.sleep(min(2, max(0, until - self.clock())))
        return RecoveryActionObservation(False, tuple(effects), reason="restart_waiting_for_verified_progress", partial=True)

    def run_once(self, *, stop_completed=False):
        from ipfs_accelerate_py.agent_supervisor.rescue.campaign_watchdog import (
            CampaignProgressWatchdog, CampaignProgressWatchdogPolicy)
        policy = CampaignProgressWatchdogPolicy(deadline_ms=1_200_000)
        result = CampaignProgressWatchdog(self.directory, repository_root=self.root, scope=self.scope, observe=self.observe,
            recover=self.recover, policy=policy).run_once()
        if result.get("status") == "complete" and stop_completed and not self.latest_observation.get("manual_hold"):
            expected = self.latest_observation
            if self.observe() != expected or not self.latest_observation["completion_verified"]:
                result = {**result, "status": "refused", "reason": "completion_changed_before_cleanup"}
            else:
                launch = self.latest_launcher
                bound = self.latest_observation["owner_binding_verified"]
                if bound and self.runner.owns_process(launch):
                    stopped = self.runner.stop(self.state, expected_launcher_sha256=_digest(launch))
                    result = {**result, "completion_cleanup": {"status": stopped.get("status"),
                        "quiesced": (stopped.get("container_shutdown") or {}).get("quiesced")}}
                    if stopped.get("status") != "stopped":
                        result.update(status="refused", reason="completed_supervisor_cleanup_incomplete")
        report = {**result, "checked_at": self.clock(), "plan_id": self.plan_id,
            "repo_root": str(self.root), "state_dir": str(self.state),
            "completed": (self.latest_status.get("board") or {}).get("completed"),
            "task_count": (self.latest_status.get("board") or {}).get("count"),
            "active_task_id": self.latest_observation.get("active_task_id"),
            "last_action": self.last_action, "completion": self.latest_completion,
            "preflight": getattr(self, "latest_preflight", {})}
        import stat
        self.directory.mkdir(mode=0o700, exist_ok=True)
        info = self.directory.lstat()
        if (self.directory.resolve(strict=True) != self.directory or info.st_uid != os.getuid()
                or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700):
            raise ValueError("watchdog_directory_custody_invalid")
        self.runner._atomic_json(self.directory / "latest.json", report)
        return report


def watch_campaign(repo_root, spec_path, state_dir, *, once=False, interval_seconds=60,
                   stop_completed=False, expected_spec_sha256=None, expected_plan_id=None):
    if type(interval_seconds) not in (int, float) or not 5 <= interval_seconds <= 3600:
        raise ValueError("watchdog_interval_invalid")
    watcher = ComplaintCampaignWatchdog(repo_root, spec_path, state_dir,
        expected_spec_sha256=expected_spec_sha256, expected_plan_id=expected_plan_id)
    while True:
        result = watcher.run_once(stop_completed=stop_completed)
        if once or result.get("status") == "complete":
            return result
        time.sleep(interval_seconds)


def systemd_units(repo_root, spec_path, state_dir, *, interpreter, plan_id, spec_sha256,
                  executable_path=None):
    """Render dedicated user units; installation and enabling are explicit."""
    root, spec, state = (Path(p).resolve(strict=True) for p in (repo_root, spec_path, state_dir))
    name = "complaint-agent-watchdog-" + _digest(str(state))[:12]
    def quoted(value):
        value = str(value)
        if any(c in value for c in "\n\r\0"):
            raise ValueError("watchdog_unit_argument_invalid")
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$") + '"'
    command = [interpreter, "-I", "-B", root / "scripts/run_complaint_improvement_supervisor.py",
        "watchdog", "--once", "--stop-completed", "--repo-root", root, "--spec", spec,
        "--state-dir", state, "--expected-plan-id", plan_id, "--expected-spec-sha256", spec_sha256]
    working_directory = str(root).replace("%", "%%")
    if any(c in working_directory for c in "\n\r\0"):
        raise ValueError("watchdog_unit_argument_invalid")
    runtime_path = executable_path if executable_path is not None else os.defpath
    if (not isinstance(runtime_path, str) or not runtime_path
            or any(c in runtime_path for c in "\n\r\0")
            or any(not Path(part).is_absolute() for part in runtime_path.split(os.pathsep))):
        raise ValueError("watchdog_executable_path_invalid")
    # Environment= expands unit specifiers but does not expand '$'. ExecStart
    # has a different expansion contract, so do not reuse its dollar escaping.
    path_assignment = '"PATH=' + runtime_path.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'
    service = "\n".join(["[Unit]", "Description=Verify and recover the complaint agent campaign", "",
        "[Service]", "Type=oneshot", "WorkingDirectory=" + working_directory,
        "ExecStart=" + " ".join(quoted(v) for v in command), "TimeoutStartSec=1800",
        # Public start detaches a Native owner. Session detachment does not
        # escape this cgroup; only Native's public stop may reap its children.
        "KillMode=process", "UMask=0077", "Environment=HF_HUB_OFFLINE=1",
        "Environment=HF_DATASETS_OFFLINE=1", "Environment=TRANSFORMERS_OFFLINE=1",
        "Environment=IPFS_DATASETS_PY_MINIMAL_IMPORTS=1", "Environment=IPFS_DATASETS_PY_AUTO_NLTK_DOWNLOAD=0",
        "Environment=" + path_assignment,
        "SyslogIdentifier=" + name, ""])
    timer = "\n".join(["[Unit]", "Description=Check complaint agent campaign progress every minute", "",
        "[Timer]", "OnCalendar=*-*-* *:*:00", "Persistent=true", "AccuracySec=1s",
        "Unit=" + name + ".service", "", "[Install]", "WantedBy=timers.target", ""])
    return {"name": name, "service": service, "timer": timer}


def install_user_timer(repo_root, spec_path, state_dir, *, interpreter=None, unit_directory=None, command_runner=None):
    """Install this campaign's dedicated user timer without replacing other units."""
    import stat
    import subprocess
    import sys
    import tempfile
    watcher = ComplaintCampaignWatchdog(repo_root, spec_path, state_dir)
    units = systemd_units(watcher.root, watcher.spec_path, watcher.state,
        interpreter=interpreter or sys.executable, plan_id=watcher.plan_id, spec_sha256=watcher.spec_sha,
        executable_path=_watchdog_executable_path(interpreter or sys.executable))
    folder = (Path(unit_directory) if unit_directory else
        Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "systemd/user")
    folder.mkdir(parents=True, exist_ok=True)
    if folder.resolve(strict=True) != folder.absolute() or folder.stat().st_uid != os.getuid():
        raise ValueError("watchdog_unit_directory_unowned")
    files = {folder / (units["name"] + "." + kind): units[kind] for kind in ("service", "timer")}
    # The previous renderer omitted PATH. Upgrade only its exact, same-campaign
    # managed bytes; any operator customization or foreign binding still fails.
    legacy_service = "\n".join(line for line in units["service"].splitlines()
                               if not line.startswith('Environment="PATH=')) + "\n"
    upgrades = {}
    for path, content in files.items():
        if os.path.lexists(path):
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                raise ValueError("watchdog_existing_unit_conflict")
            existing = path.read_text()
            if existing == content:
                continue
            if path.suffix != ".service" or existing != legacy_service:
                raise ValueError("watchdog_existing_unit_conflict")
            upgrades[path] = (existing, info)
    for path, content in files.items():
        if not path.exists() or path in upgrades:
            descriptor, temporary = tempfile.mkstemp(prefix=".watchdog-unit-", dir=folder)
            try:
                with os.fdopen(descriptor, "w") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                if path in upgrades:
                    expected, previous = upgrades[path]
                    current = path.lstat()
                    if (any(getattr(current, key) != getattr(previous, key) for key in
                            ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns"))
                            or path.read_text() != expected):
                        raise ValueError("watchdog_existing_unit_conflict")
                    os.replace(temporary, path)
                else:
                    # Do not replace a different unit created after preflight.
                    os.link(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
    run = command_runner or subprocess.run
    commands = [["systemd-analyze", "--user", "verify", *(str(p) for p in files)],
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", units["name"] + ".timer"],
        ["systemctl", "--user", "start", units["name"] + ".service"]]
    for command in commands:
        run(command, check=True, capture_output=True, text=True, timeout=1800)
    return {"status": "installed", "unit": units["name"], "timer_enabled": True,
        "state_dir": str(watcher.state), "report_path": str(watcher.directory / "latest.json"),
        "updated_units": [path.name for path in upgrades]}
