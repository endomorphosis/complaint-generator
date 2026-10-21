"""Hermetic launcher ownership and actual native ingestion/config contracts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
import os
from pathlib import Path
import signal
import sys
import time
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner


ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.fixture(autouse=True)
def restore_cwd(monkeypatch):
    monkeypatch.chdir(ROOT)


def _spec():
    return {
        "schema_version": "complaint-intake-improvement@1", "title": "Synthetic interview campaign",
        "provider": {"router": "ipfs_accelerate_py.llm_router", "provider": "grok_cli",
                     "model": "grok-4.7", "allow_fallback": False},
        "execution_policy": {"one_lane": True},
        "goals": [{"id": "goal.intake", "title": "Intake", "subgoals": [{"id": "sub.intake", "title": "Questions"}]}],
        "tasks": [
            {"id": "CIMP-TUI-01", "title": "Inspect terminal", "goal_id": "goal.intake", "subgoal_id": "sub.intake",
             "priority": "P0", "targets": ["tests/test_terminal_contract.py"], "depends_on": [],
             "acceptance": ["Synthetic terminal interview is characterized"],
             "validation_commands": ["python -m pytest -q tests/test_terminal_contract.py"],
             "implementation_prompt": "Create a bounded synthetic terminal behavior test."},
            {"id": "CIMP-TUI-02", "title": "Refine interview", "goal_id": "goal.intake", "subgoal_id": "sub.intake",
             "priority": "P1", "targets": ["tests/test_question_contract.py"], "depends_on": ["CIMP-TUI-01"],
             "acceptance": ["Questions update facts without inventing facts"],
             "validation_commands": ["python -m pytest -q tests/test_question_contract.py"],
             "implementation_prompt": "Verify questions against user-provided facts."},
        ],
    }


@pytest.fixture
def campaign(tmp_path):
    from integrations.ipfs_accelerate.improvement_plan import generate
    spec = tmp_path / runner.SPEC_RELATIVE
    spec.parent.mkdir(parents=True)
    spec.write_text(json.dumps(_spec()))
    # Import the native package under the real repository before isolating
    # artifact paths; no provider/daemon is instantiated by these operations.
    runner._native_modules(ROOT)
    generated = generate(spec, tmp_path)
    return tmp_path, spec, tmp_path / "state", generated


def _identity(pid=991119, argv=None):
    return {"pid": pid, "start_ticks": 123456, "boot_id": "test-boot", "ppid": 1,
            "session": pid, "process_group": pid, "argv": argv or []}


def _owner(state, identity=None):
    argv = [sys.executable, str(ROOT / "scripts/run_complaint_improvement_supervisor.py"),
            "_run", "--state-dir", str(state), "--owner-token", "test-owner"]
    identity = identity or _identity(argv=argv)
    return {"identity": identity, "argv": argv, "owner_token": "test-owner",
            "started_at": runner.time.time() - 10, "status": "starting"}


def test_explicit_environment_removes_ambient_routes_and_pins_model():
    environment = runner.campaign_environment(ROOT, {
        "PATH": "/bin", "HOME": "/preserved/user", "XAI_API_KEY": "fixture-secret",
        "IPFS_ACCELERATE_AGENT_IMPLEMENTATION_PROVIDER": "codex",
        "IPFS_ACCELERATE_AGENT_IMPLEMENTATION_FALLBACK_PROVIDER": "codex",
        "IPFS_ACCELERATE_AGENT_PROVIDER_FALLBACK_POLICY": "grok_quota_only",
        "IPFS_ACCELERATE_AGENT_IMPLEMENTATION_ROUTE_ID": "other-campaign",
        "IPFS_ACCELERATE_AGENT_PRODUCTION_PROVIDER_POLICY": "independent-review",
        "IMPLEMENTATION_DAEMON_COMMAND": "unexpected-provider", "GROK_MODEL": "old-model",
        "TODO_DAEMON_LLM_ALLOW_CROSS_PROVIDER_FALLBACK": "1",
        "IPFS_ACCELERATE_AGENT_GROK_REASONING_EFFORT": "high",
        "IPFS_ACCELERATE_AGENT_GROK_MAX_TURNS": "1000",
        runner.AUTOMATIC_RETRY_REARM_ENV: "1",
        "IPFS_ACCELERATE_AGENT_WORKTREE_SUBMODULE_PATHS": "external/ambient-unrelated",
        "IPFS_ACCELERATE_AGENT_WORKTREE_POOL_MAX_ENTRIES": "1000",
    })
    assert environment["IPFS_ACCELERATE_AGENT_IMPLEMENTATION_PROVIDER"] == "grok"
    assert environment["GROK_MODEL"] == environment["TODO_DAEMON_LLM_MODEL"] == "grok-4.7"
    assert environment["TODO_DAEMON_LLM_ALLOW_CROSS_PROVIDER_FALLBACK"] == "0"
    assert environment["TODO_DAEMON_LLM_ALLOW_LOCAL_FALLBACK"] == "0"
    assert environment["IPFS_ACCELERATE_AGENT_GROK_MAX_TURNS"] == "64"
    assert environment["IPFS_ACCELERATE_AGENT_GROK_REASONING_EFFORT"] == "low"
    assert environment[runner.AUTOMATIC_RETRY_REARM_ENV] == "0"
    assert environment["IPFS_ACCELERATE_AGENT_WORKTREE_SUBMODULE_PATHS"] == "external/ipfs_datasets_py"
    assert environment["IPFS_ACCELERATE_AGENT_WORKTREE_POOL_MAX_ENTRIES"] == "1"
    assert environment["HOME"] == "/preserved/user"
    assert environment["XAI_API_KEY"] == "fixture-secret"
    assert json.loads(environment[runner.PRIVATE_PATHS_ENV]) == list(runner._PRIVATE_PATHS)
    assert environment["PATH"].split(os.pathsep)[0] == str(Path(sys.executable).parent)
    for key in ("IMPLEMENTATION_DAEMON_COMMAND", "IPFS_ACCELERATE_AGENT_IMPLEMENTATION_ROUTE_ID",
                "IPFS_ACCELERATE_AGENT_IMPLEMENTATION_FALLBACK_PROVIDER",
                "IPFS_ACCELERATE_AGENT_PROVIDER_FALLBACK_POLICY",
                "IPFS_ACCELERATE_AGENT_PRODUCTION_PROVIDER_POLICY"):
        assert key not in environment


def test_private_exclusions_use_trusted_spec_and_coalesce_mandatory_directories():
    result = runner.campaign_environment(ROOT, {runner.PRIVATE_PATHS_ENV: '["untrusted"]'},
                                         context_exclude=["data/**", ".complaint_workspace/sessions/**", "private-audit/**"])
    paths = json.loads(result[runner.PRIVATE_PATHS_ENV])
    assert "data" in paths and ".complaint_workspace" in paths and "private-audit/**" in paths
    assert "data/**" not in paths and "untrusted" not in paths


def test_campaign_has_its_own_native_control_plane_root(tmp_path):
    result = runner.campaign_environment(ROOT, {
        runner.ORCHESTRATION_DIR_ENV: "/other/campaign",
        "IPFS_ACCELERATE_AGENT_CONTROL_DUCKDB": "/other/lane.duckdb",
        "IPFS_ACCELERATE_AGENT_QUACK_ENDPOINT": "quack://other-campaign",
    }, state_dir=tmp_path)
    assert result[runner.ORCHESTRATION_DIR_ENV] == str(tmp_path / "control-plane")
    assert "IPFS_ACCELERATE_AGENT_CONTROL_DUCKDB" not in result
    assert "IPFS_ACCELERATE_AGENT_QUACK_ENDPOINT" not in result


@pytest.mark.parametrize("value", [["/home/user/secrets"], ["../secrets"], ["**"], ["*"], "data/**"])
def test_private_exclusions_reject_unbounded_or_unconfined_values(value):
    with pytest.raises(ValueError, match="bounded"):
        runner.campaign_environment(ROOT, {}, context_exclude=value)


def test_private_policy_survives_actual_native_daemon_and_provider_environment(campaign, monkeypatch):
    supervisor, daemon = runner._native_modules(ROOT)
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_runtime
    policy = runner.campaign_environment(ROOT, {"PATH": os.defpath})
    monkeypatch.setattr(runner.os, "environ", dict(policy))
    observations = []
    monkeypatch.setattr(supervisor_runtime.subprocess, "Popen", lambda command, **kwargs:
                        observations.append(kwargs["env"]) or SimpleNamespace(pid=991119))
    supervisor_runtime.launch_process_child(
        ["synthetic-native-daemon"], cwd=ROOT,
        env=supervisor._managed_daemon_child_environment(),
    )
    child_environment = observations[0]
    assert child_environment[runner.PRIVATE_PATHS_ENV] == policy[runner.PRIVATE_PATHS_ENV]
    assert child_environment["IPFS_ACCELERATE_AGENT_GROK_REASONING_EFFORT"] == "low"
    assert child_environment["IPFS_ACCELERATE_AGENT_GROK_MAX_TURNS"] == "64"
    assert child_environment["IPFS_ACCELERATE_AGENT_WORKTREE_POOL_MAX_ENTRIES"] == "1"
    monkeypatch.setattr(runner.os, "environ", child_environment)
    provider_environment = daemon.PortalImplementationDaemon._implementation_untrusted_process_environment()
    assert provider_environment[runner.PRIVATE_PATHS_ENV] == policy[runner.PRIVATE_PATHS_ENV]
    assert provider_environment["IPFS_ACCELERATE_AGENT_GROK_REASONING_EFFORT"] == "low"
    assert provider_environment["IPFS_ACCELERATE_AGENT_GROK_MAX_TURNS"] == "64"
    assert provider_environment["IPFS_ACCELERATE_AGENT_IMPLEMENTATION_PROVIDER"] == "grok"


def test_campaign_pool_limit_preserves_leased_worktrees_and_prunes_only_idle(tmp_path, monkeypatch):
    import subprocess

    _, native = runner._native_modules(ROOT)
    repo = tmp_path / "synthetic-repo"
    repo.mkdir()

    def git(*args):
        return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True)

    git("init", "-b", "main")
    (repo / "app.py").write_text("VALUE = 1\n")
    git("add", "app.py")
    git("-c", "user.name=Pool fixture", "-c", "user.email=pool@example.invalid",
        "commit", "-m", "Synthetic pool baseline")
    state_dir = repo / "state"
    policy = runner.campaign_environment(repo, {"PATH": os.defpath,
        "IPFS_ACCELERATE_AGENT_WORKTREE_POOL_MAX_ENTRIES": "1000"}, state_dir=state_dir)
    monkeypatch.setattr(runner.os, "environ", dict(policy))
    todo = repo / "todo.md"
    todo.write_text("# Synthetic pool fixture\n")
    daemon = native.PortalImplementationDaemon(
        todo_path=todo, state_path=state_dir / "task_state.json",
        strategy_path=state_dir / "strategy.json", events_path=state_dir / "events.jsonl",
        repo_root=repo, implement=False, use_ephemeral_worktree=True,
        worktree_root=repo / "worktrees", merge_queue_dir=state_dir / "merge-queue",
        llm_merge_resolver_command="",
    )
    pool = daemon.worktree_pool
    assert pool is not None and pool.max_entries == 1
    held = pool.acquire(cache_key="synthetic-held", base_ref="main")
    try:
        first = pool.acquire(cache_key="synthetic-first", base_ref="main")
        assert first.release()["pooled"] is True
        first_state = pool.state_root / f"{first.entry_id}.json"
        held_state = pool.state_root / f"{held.entry_id}.json"
        held_before = held_state.read_bytes()
        second = pool.acquire(cache_key="synthetic-second", base_ref="main")
        assert second.release()["pooled"] is True
        assert not first.path.exists() and not first_state.exists()
        assert second.path.is_dir()
        assert held.path.is_dir() and held_state.read_bytes() == held_before
        assert held_state.with_suffix(".lock").is_file()
        states = [json.loads(path.read_text()) for path in pool.state_root.glob("*.json")]
        assert [item["lease_token"] for item in states if item["state"] == "idle"] == [second.entry_id]
        assert [item["lease_token"] for item in states if item["state"] == "leased"] == [held.entry_id]
        state = native.PortalTaskState.load(daemon.state_path)
        assert not state.implementation_attempts and not state.implementation_attempts_by_cid
        assert not state.completed_task_ids
    finally:
        held.release(reusable=False)


def test_real_native_parser_and_config_accept_explicit_bounded_campaign(campaign):
    root, _, state, generated = campaign
    native, _ = runner._native_modules(ROOT)
    args = native.parse_args(runner.native_argv(Path(generated["board_path"]), state, "local-campaign"))
    config = native.supervisor_config_from_args(args, repo_root=root)
    assert args.implement is True
    assert args.task_prefix == "## CIMP-"
    assert args.task_source_kind == "legacy-markdown"
    assert args.authority_mode == "legacy_markdown" and args.explicit_legacy_task_source
    assert args.implementation_timeout == args.implementation_max_timeout == 900
    assert args.max_task_attempts == 3 and args.max_restarts == 5
    assert args.task_shard_count == 1 and args.task_shard_index == 0
    assert config.use_ephemeral_worktree
    assert config.merge_target_branch == "local-campaign"
    assert not config.worktree_reconciliation_enabled
    assert config.worktree_root == state / "worktrees"
    assert tuple(config.worktree_submodule_paths) == ("external/ipfs_datasets_py",)


def test_native_task_parser_sees_entire_dag_and_grok_route(campaign):
    root, spec, _, generated = campaign
    from integrations.ipfs_accelerate.improvement_plan import load_spec
    result = runner._validate_board(root, Path(generated["board_path"]), load_spec(spec))
    assert result["count"] == 2 and result["completed"] == 0
    assert result["ready_task_ids"] == ["CIMP-TUI-01"]


def test_board_validation_rejects_changed_dependency(campaign):
    root, spec, _, generated = campaign
    from integrations.ipfs_accelerate.improvement_plan import load_spec
    path = Path(generated["board_path"])
    path.write_text(path.read_text().replace("- Depends on: CIMP-TUI-01", "- Depends on: forged-task"))
    with pytest.raises(ValueError, match="references/validation differ"):
        runner._validate_board(root, path, load_spec(spec))


def test_doctor_checks_presence_without_running_auth_or_provider(campaign, monkeypatch):
    root, spec, state, _ = campaign
    monkeypatch.setenv("XAI_API_KEY", "fixture-secret")
    monkeypatch.setattr(runner.shutil, "which", lambda *a, **k: "/bin/grok")
    monkeypatch.setattr(runner, "_private_runtime_checks", lambda *a: {"ready": True})
    # The local Git size observation is tested with real synthetic repositories
    # below; this presence-only contract keeps all process dispatch forbidden.
    capacity_observations = []
    monkeypatch.setattr(runner, "_worktree_capacity", lambda *a: capacity_observations.append(a) or {"sufficient": None})
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: pytest.fail("doctor spawned a provider/process"))
    result = runner.doctor(root, spec, state, merge_target="local-campaign")
    assert result["status"] == "ready" and result["paid_calls"] == 0
    assert result["auth_validated"] is False
    assert result["native_config_validated"]
    assert capacity_observations == [(root, state / "worktrees")]
    assert not state.exists()


def test_doctor_rejects_auth_provider_command_without_forwardable_credentials(campaign, monkeypatch):
    root, spec, state, _ = campaign
    for key in ("XAI_API_KEY", "ipfs_accelerate_py_XAI_API_KEY", "IPFS_ACCELERATE_PY_XAI_API_KEY", "IPFS_DATASETS_PY_XAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GROK_HOME", str(root / "empty-auth-home"))
    monkeypatch.setenv("GROK_AUTH_PROVIDER_COMMAND", "do-not-execute-this")
    monkeypatch.setattr(runner.shutil, "which", lambda *a, **k: "/bin/grok")
    monkeypatch.setattr(runner, "_private_runtime_checks", lambda *a: {"ready": True})
    result = runner.doctor(root, spec, state, merge_target="local-campaign")
    assert result["status"] == "not_ready" and not result["auth_material_present"]
    assert result["auth_provider_command_supported"] is False


def test_privacy_preflight_rejects_native_without_enforcement(campaign, monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.runtime import grok_cli_runner
    monkeypatch.setattr(grok_cli_runner, "GROK_PRIVATE_PATHS_VERSION", 0, raising=False)
    result = runner._private_runtime_checks(ROOT, runner.campaign_environment(ROOT))
    assert not result["ready"] and not result["native_enforcement_available"]


def test_preflight_rejects_ignored_reasoning_configuration(campaign, monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.runtime import grok_cli_runner
    monkeypatch.delattr(grok_cli_runner, "GROK_REASONING_EFFORT_ENV", raising=False)
    result = runner._private_runtime_checks(ROOT, runner.campaign_environment(ROOT))
    assert not result["ready"]
    assert result["reason"] == "native_reasoning_effort_control_unavailable"



def test_preflight_rejects_native_that_ignores_automatic_budget_reset_policy(campaign, monkeypatch):
    _, native = runner._native_modules(ROOT)
    monkeypatch.delattr(native, "AUTOMATIC_RETRY_REARM_ENV", raising=False)
    result = runner._private_runtime_checks(ROOT, runner.campaign_environment(ROOT))
    assert not result["ready"]
    assert result["reason"] == "native_retry_budget_control_unavailable"

def test_privacy_preflight_validates_policy_and_bounded_docker_readiness(campaign, monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.runtime import grok_cli_runner
    monkeypatch.setattr(grok_cli_runner, "GROK_PRIVATE_PATHS_VERSION", 1, raising=False)
    monkeypatch.setattr(grok_cli_runner, "validate_grok_private_path_patterns", lambda raw: tuple(json.loads(raw)), raising=False)
    resolved = []
    monkeypatch.setattr(grok_cli_runner, "_grok_private_workspace_paths",
                        lambda **kwargs: resolved.append(kwargs) or (), raising=False)
    monkeypatch.setattr(grok_cli_runner, "_docker_isolation_binary", lambda: "/usr/bin/docker")
    monkeypatch.setattr(grok_cli_runner, "_ordinary_task_toolchain_image_profile", lambda: ("sha256:qualified", "amd64", "label"), raising=False)
    monkeypatch.setattr(runner.platform, "machine", lambda: "x86_64")
    calls = []
    monkeypatch.setattr(grok_cli_runner, "_docker_isolation_image_id", lambda binary, **kwargs:
                        calls.append((binary, kwargs)) or "sha256:base")
    monkeypatch.setattr(grok_cli_runner, "_docker_ordinary_task_toolchain_image_id", lambda binary, **kwargs:
                        calls.append((binary, kwargs)) or "sha256:qualified")
    result = runner._private_runtime_checks(ROOT, runner.campaign_environment(ROOT))
    assert result["ready"] and result["docker_ready"]
    assert resolved[0]["workspace"] == ROOT
    assert result["ordinary_task_image_id"] == "sha256:qualified"
    assert len(calls) == 2 and calls[0][0] == "/usr/bin/docker"
    assert calls[0][1]["docker_config"] == calls[1][1]["docker_config"]


@pytest.mark.parametrize("ordinary,architecture,reason", [
    ("", "amd64", "qualified_ordinary_task_image_unavailable"),
    ("sha256:qualified", "arm64", "ordinary_task_image_architecture_mismatch"),
])
def test_privacy_preflight_rejects_missing_or_wrong_architecture_image(campaign, monkeypatch, ordinary, architecture, reason):
    from ipfs_accelerate_py.agent_supervisor.runtime import grok_cli_runner
    monkeypatch.setattr(grok_cli_runner, "GROK_PRIVATE_PATHS_VERSION", 1, raising=False)
    monkeypatch.setattr(grok_cli_runner, "validate_grok_private_path_patterns", lambda raw: tuple(json.loads(raw)), raising=False)
    monkeypatch.setattr(grok_cli_runner, "_grok_private_workspace_paths", lambda **kwargs: (), raising=False)
    monkeypatch.setattr(grok_cli_runner, "_docker_isolation_binary", lambda: "/usr/bin/docker")
    monkeypatch.setattr(grok_cli_runner, "_docker_isolation_image_id", lambda *a, **k: "sha256:base")
    monkeypatch.setattr(grok_cli_runner, "_docker_ordinary_task_toolchain_image_id", lambda *a, **k: ordinary)
    monkeypatch.setattr(grok_cli_runner, "_ordinary_task_toolchain_image_profile", lambda: ("sha256:qualified", architecture, "label"), raising=False)
    monkeypatch.setattr(runner.platform, "machine", lambda: "x86_64")
    result = runner._private_runtime_checks(ROOT, runner.campaign_environment(ROOT))
    assert not result["ready"] and result["reason"] == reason


@pytest.mark.parametrize("changed", ["start_ticks", "boot_id", "argv", "session"])
def test_ownership_rejects_reused_pid_or_changed_command(tmp_path, monkeypatch, changed):
    record = _owner(tmp_path)
    current = dict(record["identity"])
    current[changed] = ["unrelated-process"] if changed == "argv" else "different"
    monkeypatch.setattr(runner, "process_identity", lambda pid: current)
    assert runner.owns_process(record) is False


def test_real_proc_identity_reads_own_process():
    identity = runner.process_identity(os.getpid())
    assert identity and identity["pid"] == os.getpid()
    assert identity["start_ticks"] > 0 and identity["boot_id"] and identity["argv"]


def test_duplicate_start_returns_existing_owned_process(tmp_path, monkeypatch):
    record = _owner(tmp_path)
    runner._atomic_json(tmp_path / "launcher.json", record)
    child = {**_identity(pid=991120), "ppid": record["identity"]["pid"]}
    monkeypatch.setattr(runner, "process_identity", lambda pid: record["identity"] if pid == record["identity"]["pid"] else child if pid == 991120 else None)
    monkeypatch.setattr(runner, "prepare", lambda *a: pytest.fail("duplicate recompiled campaign"))
    assert runner.start(ROOT, ROOT / runner.SPEC_RELATIVE, tmp_path)["status"] == "already_running"


def test_start_spawns_detached_but_reports_starting_not_running(tmp_path, monkeypatch):
    observations = {}
    current = {}
    monkeypatch.setattr(runner, "process_identity", lambda pid: current.get(pid))
    monkeypatch.setattr(runner, "prepare", lambda *a: {"board_path": "/board.md"})
    monkeypatch.setattr(runner, "doctor", lambda *a: {"status": "ready", "merge_target": "campaign", "native_plan_id": "plan-1"})
    def spawn(argv, **kwargs):
        observations.update(kwargs)
        current[991119] = _identity(argv=argv)
        return SimpleNamespace(pid=991119, poll=lambda: None)
    monkeypatch.setattr(runner.subprocess, "Popen", spawn)
    result = runner.start(ROOT, ROOT / runner.SPEC_RELATIVE, tmp_path)
    assert result["status"] == "starting" and result["progress_verified"] is False
    assert observations["start_new_session"] is True
    assert observations["stdin"] == runner.subprocess.DEVNULL
    assert observations["cwd"] == ROOT and observations["close_fds"] is True
    assert runner.owns_process(runner._read_json(tmp_path / "launcher.json"))


def test_unready_start_never_launches(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "prepare", lambda *a: {})
    monkeypatch.setattr(runner, "doctor", lambda *a: {"status": "not_ready"})
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: pytest.fail("unready launch"))
    assert runner.start(ROOT, ROOT / runner.SPEC_RELATIVE, tmp_path)["status"] == "not_ready"


def test_stop_does_not_signal_recycled_pid_or_modify_manual_board(tmp_path, monkeypatch):
    record = _owner(tmp_path)
    runner._atomic_json(tmp_path / "launcher.json", record)
    changed = {**record["identity"], "start_ticks": 123457}
    monkeypatch.setattr(runner, "process_identity", lambda pid: changed)
    monkeypatch.setattr(runner, "_signal_birth", lambda *a: pytest.fail("signalled unrelated PID"))
    original = (tmp_path / "launcher.json").read_bytes()
    result = runner.stop(tmp_path)
    assert result["status"] == "not_owned_or_stopped" and not result["signalled"]
    assert (tmp_path / "launcher.json").read_bytes() == original


def test_stop_signals_only_owned_root_and_captured_births(tmp_path, monkeypatch):
    record = _owner(tmp_path)
    runner._atomic_json(tmp_path / "launcher.json", record)
    child = _identity(pid=991120)
    current = {record["identity"]["pid"]: record["identity"], child["pid"]: child}
    monkeypatch.setattr(runner, "process_identity", lambda pid: current.get(pid))
    monkeypatch.setattr(runner, "_descendants", lambda root: [child])
    signals = []
    def send(identity, signum):
        signals.append((identity["pid"], signum))
        current.pop(identity["pid"], None)
        return True
    monkeypatch.setattr(runner, "_signal_birth", send)
    result = runner.stop(tmp_path, timeout=0)
    assert result["status"] == "stopped" and result["manual_holds_preserved"]
    assert signals[0] == (991119, signal.SIGTERM)
    assert all(pid in {991119, 991120} for pid, _ in signals)


def _status_fixture(campaign, monkeypatch, *, native_state=None, board=None, heartbeat=True):
    root, spec, state, _ = campaign
    state.mkdir()
    record = _owner(state)
    runner._atomic_json(state / "launcher.json", record)
    child = {**_identity(pid=991120), "ppid": record["identity"]["pid"]}
    monkeypatch.setattr(runner, "process_identity", lambda pid: record["identity"] if pid == record["identity"]["pid"] else child if pid == 991120 else None)
    if native_state is not None:
        runner._atomic_json(state / f"{runner.STATE_PREFIX}_task_state.json", native_state)
    if heartbeat:
        runner._atomic_json(state / f"{runner.STATE_PREFIX}_supervisor_status.json", {
            "status": "running", "supervisor_pid": record["identity"]["pid"],
            "daemon_pid": 991120, "daemon_pid_alive": True,
        })
    if board is not None:
        monkeypatch.setattr(runner, "_validate_board", lambda *a: board)
    return root, spec, state, record


def test_status_does_not_promote_popen_to_progress(campaign, monkeypatch):
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, heartbeat=False)
    result = runner.status(root, spec, state)
    assert result["status"] == "starting" and not result["progress_verified"]


def test_status_observes_current_native_task_claim(campaign, monkeypatch):
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, native_state={
        "active_task_id": "CIMP-TUI-01", "implementation_in_progress": True,
        "active_phase": "implementation", "active_attempt": 1,
    })
    result = runner.status(root, spec, state)
    assert result["status"] == "active" and result["claim_progress_verified"]
    assert result["provider_execution_verified"] is False and result["progress_verified"] is False
    assert result["native_state"]["active_task_id"] == "CIMP-TUI-01"
    assert result["completion_authority"] is False


@pytest.mark.parametrize("executing,expected", [(False, "selected"), (True, "active")])
def test_status_never_uses_previous_attempt_log_for_new_claim(campaign, monkeypatch, executing, expected):
    stamp = datetime.now(timezone.utc).isoformat()
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, native_state={
        "active_task_id": "CIMP-TUI-01", "active_attempt": 0,
        "active_phase": "", "active_task_started_at": stamp,
        "implementation_in_progress": executing,
    })
    old_log = state / "attempt-1.log"
    old_log.write_text("previous timed-out attempt\n")
    old = runner.time.time() - runner.STALL_SECONDS - 120
    os.utime(old_log, (old, old))
    path = state / f"{runner.STATE_PREFIX}_task_state.json"
    payload = json.loads(path.read_text())
    payload["last_implementation_log_path"] = str(old_log)
    runner._atomic_json(path, payload)
    result = runner.status(root, spec, state)
    assert result["status"] == expected
    assert result["claim_progress_verified"] and not result["provider_execution_verified"]


def test_status_bounds_selected_claim_without_worker(campaign, monkeypatch):
    stamp = datetime.fromtimestamp(runner.time.time() - runner.STALL_SECONDS - 10, timezone.utc).isoformat()
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, native_state={
        "active_task_id": "CIMP-TUI-01", "active_attempt": 0,
        "active_phase": "", "active_task_started_at": stamp,
        "implementation_in_progress": False,
    })
    assert runner.status(root, spec, state)["status"] == "no_progress"


def test_status_still_detects_stale_current_execution_log(campaign, monkeypatch):
    stamp = datetime.fromtimestamp(runner.time.time() - runner.STALL_SECONDS - 20, timezone.utc).isoformat()
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, native_state={
        "active_task_id": "CIMP-TUI-01", "active_attempt": 2,
        "active_phase": "implementing", "active_task_started_at": stamp,
        "implementation_in_progress": True,
    })
    log = state / "attempt-2.log"
    log.write_text("current stalled attempt\n")
    old = runner.time.time() - runner.STALL_SECONDS - 10
    os.utime(log, (old, old))
    path = state / f"{runner.STATE_PREFIX}_task_state.json"
    payload = json.loads(path.read_text())
    payload["active_log_path"] = str(log)
    runner._atomic_json(path, payload)
    assert runner.status(root, spec, state)["status"] == "stalled"


def test_status_reads_real_native_duckdb_row_without_json_mirror(campaign, monkeypatch):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import portal_task_state_control_plane as plane
    root, spec, state, _ = _status_fixture(campaign, monkeypatch)
    path = state / f"{runner.STATE_PREFIX}_task_state.json"
    monkeypatch.setenv(runner.ORCHESTRATION_DIR_ENV, str(state / "control-plane"))
    stamp = datetime.now(timezone.utc).isoformat()
    plane.save_portal_task_state(path.stem, {
        "active_task_id": "CIMP-TUI-01", "heartbeat_at": stamp,
        "active_task_started_at": stamp, "implementation_in_progress": True,
    }, state_path=path)
    database = plane.task_state_authority_file(path)
    assert not path.exists()
    result = runner.status(root, spec, state)
    assert result["status"] == "active" and result["claim_progress_verified"]
    assert result["native_state_source"]["source"] == "native_control_plane"
    assert result["native_state_source"]["authority_path"] == str(database)
    assert not result["provider_execution_verified"]


def test_native_observer_creates_no_catalog_or_legacy_migration(campaign, monkeypatch):
    root, _, state, _ = campaign
    state.mkdir()
    account = root / "isolated-account"
    legacy = account / ".local/state/ipfs_accelerate_py/legacy.duckdb"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"synthetic-unmigrated-catalog")
    monkeypatch.setenv("HOME", str(account))
    payload, source = runner._read_native_state(root, state / f"{runner.STATE_PREFIX}_task_state.json")
    assert not payload and not list(state.iterdir())
    assert source["authority_path"] is None
    assert legacy.read_bytes() == b"synthetic-unmigrated-catalog"


def test_native_observer_deadline_is_bounded(campaign, monkeypatch):
    root, _, state, _ = campaign
    started = time.monotonic()
    payload, _ = runner._read_native_state(root, state / "state.json", timeout_seconds=0.0001)
    assert payload["read_error"] == "native_state_read_timeout"
    assert time.monotonic() - started < 2


@pytest.mark.parametrize("native_status,child_alive,expected", [
    ("failed", True, "daemon_failed"), ("running", False, "daemon_failed"),
    ("recycling", False, "recycling"),
])
def test_status_honors_actual_native_heartbeat_and_child_liveness(campaign, monkeypatch, native_status, child_alive, expected):
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, native_state={"active_task_id": "CIMP-TUI-01"})
    heartbeat_path = state / f"{runner.STATE_PREFIX}_supervisor_status.json"
    heartbeat = json.loads(heartbeat_path.read_text())
    heartbeat.update(status=native_status, daemon_pid_alive=child_alive)
    runner._atomic_json(heartbeat_path, heartbeat)
    assert runner.status(root, spec, state)["status"] == expected


@pytest.mark.parametrize("native_status,age,expected", [
    ("agentic_maintenance_started", 10, "starting"),
    ("agentic_maintenance_completed", 10, "starting"),
    ("agentic_maintenance_failed", 10, "daemon_failed"),
    ("agentic_maintenance_started", 100, "daemon_failed"),
])
def test_status_bounds_native_startup_maintenance_without_child(campaign, monkeypatch, native_status, age, expected):
    root, spec, state, record = _status_fixture(campaign, monkeypatch)
    record["started_at"] = runner.time.time() - age
    runner._atomic_json(state / "launcher.json", record)
    heartbeat_path = state / f"{runner.STATE_PREFIX}_supervisor_status.json"
    heartbeat = json.loads(heartbeat_path.read_text())
    heartbeat.update(status=native_status, daemon_pid=None, daemon_pid_alive=False)
    runner._atomic_json(heartbeat_path, heartbeat)
    assert runner.status(root, spec, state)["status"] == expected


def test_only_native_provider_start_event_verifies_provider_execution(campaign, monkeypatch):
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, native_state={"active_task_id": "CIMP-TUI-01"})
    events = state / f"{runner.STATE_PREFIX}_events.jsonl"
    event = {"type": "task_selected", "task_id": "CIMP-TUI-01", "timestamp": datetime.now(timezone.utc).isoformat()}
    events.write_text(json.dumps(event) + "\n")
    assert not runner.status(root, spec, state)["provider_execution_verified"]
    event["type"] = "implementation_provider_started"
    events.write_text(json.dumps(event) + "\n")
    result = runner.status(root, spec, state)
    assert result["provider_execution_verified"] and result["progress_verified"]


def test_status_preserves_intentional_user_wait(campaign, monkeypatch):
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, native_state={
        "active_task_id": "CIMP-TUI-01", "active_phase": "waiting_for_user"})
    assert runner.status(root, spec, state)["status"] == "waiting_for_user"


def test_status_reports_blocked_not_idle_success(campaign, monkeypatch):
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, board={
        "count": 2, "completed": 0, "ready_task_ids": [], "manual_hold_task_ids": []})
    assert runner.status(root, spec, state)["status"] == "blocked"


def test_status_reports_native_attempt_limit_block_despite_ready_dependencies(campaign, monkeypatch):
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, native_state={
        "blocked_task_ids": ["CIMP-TUI-01"], "selectable_ready_task_ids": [],
    })
    assert runner.status(root, spec, state)["status"] == "blocked"


def test_status_detects_expired_attempt_without_log(campaign, monkeypatch):
    started = datetime.fromtimestamp(runner.time.time() - 1000, timezone.utc).isoformat()
    root, spec, state, _ = _status_fixture(campaign, monkeypatch, native_state={
        "active_task_id": "CIMP-TUI-01", "active_task_started_at": started,
        "implementation_in_progress": True,
    })
    assert runner.status(root, spec, state)["status"] == "stalled"


def test_status_rejects_prior_run_claim_as_progress(campaign, monkeypatch):
    root, spec, state, record = _status_fixture(campaign, monkeypatch,
        native_state={"active_task_id": "CIMP-TUI-01"})
    old = record["started_at"] - 100
    os.utime(state / f"{runner.STATE_PREFIX}_task_state.json", (old, old))
    assert not runner.status(root, spec, state)["progress_verified"]



@pytest.mark.parametrize("has_old_claim", [False, True])
def test_fresh_supervisor_events_cannot_hide_missing_current_task_progress(campaign, monkeypatch, has_old_claim):
    root, spec, state, record = _status_fixture(campaign, monkeypatch,
        native_state={"active_task_id": "CIMP-TUI-01"} if has_old_claim else None)
    record["started_at"] = runner.time.time() - runner.STARTUP_SECONDS - 10
    runner._atomic_json(state / "launcher.json", record)
    if has_old_claim:
        old = record["started_at"] - 100
        os.utime(state / f"{runner.STATE_PREFIX}_task_state.json", (old, old))
    (state / f"{runner.STATE_PREFIX}_supervisor_events.jsonl").write_text(
        json.dumps({"type": "watchdog_heartbeat"}) + "\n")
    result = runner.status(root, spec, state)
    assert result["status"] == "no_progress"
    assert not result["claim_progress_verified"]


def test_selected_claim_without_attempt_clock_has_bounded_wait(campaign, monkeypatch):
    root, spec, state, record = _status_fixture(campaign, monkeypatch,
        native_state={"active_task_id": "CIMP-TUI-01", "implementation_in_progress": False})
    record["started_at"] = runner.time.time() - runner.STALL_SECONDS - 10
    runner._atomic_json(state / "launcher.json", record)
    result = runner.status(root, spec, state)
    assert result["status"] == "no_progress"


@pytest.mark.parametrize("proof", ["missing", "wrong_owner", "wrong_plan", "unquiesced", "verified"])
def test_dead_full_launcher_requires_bound_container_shutdown_proof(campaign, monkeypatch, proof):
    root, spec, state, record = _status_fixture(campaign, monkeypatch)
    record.update(schema_version="complaint-improvement-launcher@1", repo_root=str(root),
                  state_dir=str(state), plan_id=campaign[3]["receipt"]["plan_id"])
    runner._atomic_json(state / "launcher.json", record)
    monkeypatch.setattr(runner, "process_identity", lambda _pid: None)
    if proof != "missing":
        receipt = {"schema": "complaint-improvement-container-shutdown@1", "repo_root": str(root),
                   "state_dir": str(state), "plan_id": record["plan_id"], "started_at": record["started_at"],
                   "owner_token_sha256": runner.hashlib.sha256(record["owner_token"].encode()).hexdigest(),
                   "quiesced": proof != "unquiesced", "status": "stopped", "completion_authority": False,
                   "provider_callback_settled": False, "attempt_refunded": False}
        if proof == "wrong_owner":
            receipt["owner_token_sha256"] = "0" * 64
        if proof == "wrong_plan":
            receipt["plan_id"] = "another-plan"
        runner._atomic_json(state / "container_shutdown.json", receipt)
    result = runner.status(root, spec, state)
    assert result["status"] == ("stopped" if proof == "verified" else "stop_incomplete")
    assert result["container_shutdown_verified"] is (proof == "verified")
    assert not result["owned_process_alive"]

def test_status_handles_malformed_owner_and_native_receipts(campaign):
    root, spec, state, _ = campaign
    state.mkdir()
    runner._atomic_json(state / "launcher.json", {"identity": "malformed", "started_at": None})
    (state / f"{runner.STATE_PREFIX}_task_state.json").write_text("not-json")
    result = runner.status(root, spec, state)
    assert result["status"] == "stopped" and result["pid"] is None
    assert result["native_read_errors"]["state"] == "JSONDecodeError"


def test_tail_is_bounded_and_preserves_latest_lines(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("old\n" * 10000 + "last\n")
    result = runner._tail(path, lines=3, maximum=100)
    assert len(result) == 3 and result[-1] == "last"


def test_cli_has_no_implicit_provider_model_override(monkeypatch, capsys, tmp_path):
    seen = []
    monkeypatch.setattr(runner, "doctor", lambda *a: seen.append(a) or {"status": "ready"})
    assert runner.main(["doctor", "--repo-root", str(ROOT), "--state-dir", str(tmp_path)]) == 0
    assert seen[0][0] == ROOT
    assert json.loads(capsys.readouterr().out)["status"] == "ready"
    with pytest.raises(SystemExit):
        runner.main(["start", "--model", "old-model"])


def test_internal_entry_requires_exact_parent_ownership(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "owns_process", lambda record: False)
    with pytest.raises(RuntimeError, match="exact owned launch receipt"):
        runner.run_internal(ROOT, ROOT / runner.SPEC_RELATIVE, tmp_path, "wrong", "campaign")


@pytest.mark.parametrize("changed_spec", [False, True])
def test_internal_entry_calls_actual_native_runner_contract_without_once(campaign, monkeypatch, changed_spec):
    root, spec, state, generated = campaign
    state.mkdir()
    record = _owner(state)
    record["plan_id"] = generated["receipt"]["plan_id"]
    record["identity"]["pid"] = os.getpid()
    runner._atomic_json(state / "launcher.json", record)
    monkeypatch.setattr(runner, "owns_process", lambda item: True)
    monkeypatch.setattr(runner, "_validate_board", lambda *a: {})
    monkeypatch.setattr(runner, "_private_runtime_checks", lambda *a: {"ready": True})
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor_runner as native_runner
    calls = []
    monkeypatch.setattr(native_runner, "run_configured_portal_implementation_supervisor",
                        lambda argv, **kwargs: calls.append((argv, kwargs)))
    # Scope the environment mutation to this test; the child normally owns it.
    monkeypatch.setattr(runner.os, "environ", dict(os.environ))
    if changed_spec:
        document = json.loads(spec.read_text())
        document["tasks"][0]["implementation_prompt"] += " Changed after launch."
        spec.write_text(json.dumps(document))
        with pytest.raises(RuntimeError, match="specification changed"):
            runner.run_internal(root, spec, state, "test-owner", "campaign")
        assert not calls
        return
    assert runner.run_internal(root, spec, state, "test-owner", "campaign") == 0
    assert len(calls) == 1 and "--once" not in calls[0][0]
    assert calls[0][1]["repo_root"] == root
    assert "--implement" in calls[0][0]


def _configured_owner(repo, state, workspace_root):
    binding = runner._validate_worktree_root(repo, state, workspace_root, claim=True)
    record = _owner(state)
    record.update(repo_root=str(repo), state_dir=str(state), worktree_root=str(workspace_root),
                  worktree_root_binding=binding)
    record['argv'].extend(['--worktree-root', str(workspace_root)])
    record['identity']['argv'] = record['argv'][:]
    return record


@pytest.mark.parametrize('mutation', ['symlink', 'public_mode', 'nonempty', 'foreign_marker', 'foreign_uid', 'inside_repo', 'inside_state'])
def test_configured_worktree_root_rejects_unowned_or_non_dedicated_directory(tmp_path, monkeypatch, mutation):
    repo, state = tmp_path / 'repo', tmp_path / 'state'
    repo.mkdir(); state.mkdir(mode=0o700)
    target = tmp_path / 'external-root'
    target.mkdir(mode=0o700)
    if mutation == 'symlink':
        alias = tmp_path / 'alias'; alias.symlink_to(target, target_is_directory=True); target = alias
    elif mutation == 'public_mode':
        target.chmod(0o755)
    elif mutation == 'nonempty':
        (target / 'unrelated.txt').write_text('preserve')
    elif mutation == 'foreign_marker':
        runner._validate_worktree_root(repo, tmp_path / 'foreign-epoch', target, claim=True)
    elif mutation == 'foreign_uid':
        uid = os.getuid(); monkeypatch.setattr(runner.os, 'getuid', lambda: uid + 1)
    elif mutation == 'inside_repo':
        target = repo / 'private'; target.mkdir(mode=0o700)
    elif mutation == 'inside_state':
        target = state / 'private'; target.mkdir(mode=0o700)
    with pytest.raises((ValueError, OSError)):
        runner._validate_worktree_root(repo, state, target, claim=True)


def test_bound_worktree_root_persists_identity_without_touching_epoch_or_task_history(tmp_path, monkeypatch):
    repo, state, target = tmp_path / 'repo', tmp_path / 'epoch', tmp_path / 'storage-root'
    repo.mkdir(); state.mkdir(mode=0o700); target.mkdir(mode=0o700)
    history = state / 'spent-counts-and-quarantine.json'
    history.write_text('{"spent":4,"quarantine":"retained"}')
    before = history.read_bytes()
    record = _configured_owner(repo, state, target)
    assert (target / runner.WORKTREE_MARKER).stat().st_mode & 0o777 == 0o600
    (target / 'workspace_native_01').mkdir()
    monkeypatch.setenv('IPFS_ACCELERATE_AGENT_WORKTREE_ROOT', '/untrusted/ambient')
    selected, binding = runner._select_worktree_root(repo, state, record, None)
    assert selected == target and binding == record['worktree_root_binding']
    assert binding['device'] == target.stat().st_dev and binding['inode'] == target.stat().st_ino
    assert history.read_bytes() == before
    assert not (state / 'worktrees').exists()


@pytest.mark.parametrize('mutation', ['directory_replaced', 'marker_replaced', 'flag_missing', 'flag_duplicate', 'record_path_changed'])
def test_recorded_root_rejects_identity_or_argv_changes_before_stop_effects(tmp_path, monkeypatch, mutation):
    repo, state, target = tmp_path / 'repo', tmp_path / 'epoch', tmp_path / 'storage-root'
    repo.mkdir(); state.mkdir(mode=0o700); target.mkdir(mode=0o700)
    record = _configured_owner(repo, state, target)
    if mutation == 'directory_replaced':
        target.rename(tmp_path / 'preserved-old-root'); target.mkdir(mode=0o700)
        (target / runner.WORKTREE_MARKER).write_bytes((tmp_path / 'preserved-old-root' / runner.WORKTREE_MARKER).read_bytes())
        (target / runner.WORKTREE_MARKER).chmod(0o600)
    elif mutation == 'marker_replaced':
        (target / runner.WORKTREE_MARKER).write_text('{}')
    elif mutation == 'flag_missing':
        record['argv'] = record['argv'][:-2]
    elif mutation == 'flag_duplicate':
        record['argv'] += ['--worktree-root', str(target)]
    else:
        record['worktree_root'] = str(tmp_path / 'other-root')
    runner._atomic_json(state / 'launcher.json', record)
    monkeypatch.setattr(runner, '_signal_birth', lambda *a: pytest.fail('invalid binding signalled process'))
    from integrations.ipfs_accelerate import improvement_shutdown
    monkeypatch.setattr(improvement_shutdown, 'close_campaign_containers', lambda *a, **k: pytest.fail('invalid binding inspected Docker'))
    assert runner.stop(state)['status'] == 'stop_incomplete'


def test_actual_native_parser_uses_external_root_without_moving_state_or_queue(campaign):
    root, spec, state, generated = campaign
    target = root / 'external-storage'
    target.mkdir(mode=0o700)
    # This config parser is pure; storage validation is separately exercised on
    # a directory outside the synthetic repository boundary.
    native, _ = runner._native_modules(ROOT)
    parsed = native.parse_args(runner.native_argv(Path(generated['board_path']), state, 'campaign', worktree_root=target))
    config = native.supervisor_config_from_args(parsed, repo_root=root)
    assert config.worktree_root == target
    assert config.state_path == state / 'complaint_intake_task_state.json'
    assert config.merge_queue_dir == state / 'merge-queue'


def test_cli_accepts_explicit_root_only_for_start_doctor_and_owned_internal(monkeypatch, capsys, tmp_path):
    observed = []
    target = tmp_path / 'private-root'
    monkeypatch.setattr(runner, 'doctor', lambda *a, **k: observed.append(k) or {'status': 'ready'})
    assert runner.main(['doctor', '--repo-root', str(ROOT), '--state-dir', str(tmp_path), '--worktree-root', str(target)]) == 0
    assert observed == [{'worktree_root': target}]
    capsys.readouterr()
    for command in ['status', 'stop']:
        with pytest.raises(SystemExit):
            runner.main([command, '--worktree-root', str(target)])


def test_capacity_preflight_uses_real_pinned_blob_sizes_without_fetch(tmp_path, monkeypatch):
    repo = tmp_path / 'source'
    datasets = repo / 'external/ipfs_datasets_py'
    datasets.mkdir(parents=True)
    def git(path, *args):
        return runner.subprocess.run(['git', '-c', 'user.name=Synthetic Fixture', '-c', 'user.email=fixture@example.invalid', *args],
            cwd=path, check=True, capture_output=True, text=True).stdout.strip()
    git(datasets, 'init', '-q')
    (datasets / 'payload').write_bytes(b'd' * 8192)
    git(datasets, 'add', 'payload'); git(datasets, 'commit', '-qm', 'synthetic datasets')
    pinned = git(datasets, 'rev-parse', 'HEAD')
    git(repo, 'init', '-q')
    (repo / 'payload').write_bytes(b'r' * 4096)
    git(repo, 'add', 'payload')
    git(repo, 'update-index', '--add', '--cacheinfo', '160000,' + pinned + ',external/ipfs_datasets_py')
    git(repo, 'commit', '-qm', 'synthetic source with pinned datasets')
    target = tmp_path / 'target'; target.mkdir(mode=0o700)
    monkeypatch.setattr(runner.shutil, 'disk_usage', lambda path: SimpleNamespace(free=12287))
    capacity = runner._worktree_capacity(repo, target)
    assert capacity['minimum_cold_checkout_bytes'] == 12288
    assert capacity['sufficient'] is False and capacity['free_bytes'] == 12287
    assert list(target.iterdir()) == []


def test_doctor_refuses_known_insufficient_checkout_space_without_provider(campaign, monkeypatch):
    root, spec, state, generated = campaign
    monkeypatch.setattr(runner, '_branch', lambda path: 'campaign')
    monkeypatch.setattr(runner.shutil, 'which', lambda *a, **k: '/synthetic/grok')
    monkeypatch.setenv('XAI_API_KEY', 'synthetic-not-used')
    monkeypatch.setattr(runner, '_private_runtime_checks', lambda *a: {'ready': True})
    monkeypatch.setattr(runner, '_worktree_capacity', lambda *a: {'sufficient': False, 'free_bytes': 1, 'minimum_cold_checkout_bytes': 2})
    result = runner.doctor(root, spec, state)
    assert result['status'] == 'not_ready' and result['paid_calls'] == 0
    assert result['worktree_capacity']['sufficient'] is False


def test_configured_start_and_owned_reentry_preserve_root_epoch_and_native_contract(campaign, monkeypatch):
    root, spec, state, generated = campaign
    state.mkdir(mode=0o700)
    target = root.parent / (root.name + '-dedicated-storage')
    target.mkdir(mode=0o700)
    history = state / 'original-accounting-and-quarantine.json'
    history.write_text('{"spent":4,"quarantine":"preserved"}')
    original = history.read_bytes()
    current = {}
    monkeypatch.setattr(runner, 'process_identity', lambda pid: current.get(pid))
    monkeypatch.setattr(runner, 'prepare', lambda *a: generated)
    monkeypatch.setattr(runner, 'doctor', lambda *a, **k: {'status': 'ready', 'merge_target': 'campaign',
                                                       'native_plan_id': generated['receipt']['plan_id']})
    def spawn(argv, **kwargs):
        current[991119] = _identity(argv=argv)
        return SimpleNamespace(pid=991119, poll=lambda: None)
    monkeypatch.setattr(runner.subprocess, 'Popen', spawn)
    assert runner.start(root, spec, state, worktree_root=target)['status'] == 'starting'
    record = runner._read_json(state / 'launcher.json')
    assert record['argv'].count('--worktree-root') == 1
    assert record['argv'][-2:] == ['--worktree-root', str(target)]
    assert record['worktree_root_binding']['marker_sha256'] == runner.hashlib.sha256((target / runner.WORKTREE_MARKER).read_bytes()).hexdigest()
    assert runner._select_worktree_root(root, state, record, None)[0] == target
    record['identity']['pid'] = os.getpid()
    runner._atomic_json(state / 'launcher.json', record)
    monkeypatch.setattr(runner, 'owns_process', lambda item: True)
    monkeypatch.setattr(runner, '_validate_board', lambda *a: {})
    monkeypatch.setattr(runner, '_private_runtime_checks', lambda *a: {'ready': True})
    monkeypatch.setattr(runner.os, 'environ', dict(os.environ))
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor_runner as native_runner
    calls = []
    monkeypatch.setattr(native_runner, 'run_configured_portal_implementation_supervisor', lambda argv, **kwargs: calls.append(argv))
    assert runner.run_internal(root, spec, state, record['owner_token'], 'campaign', worktree_root=target) == 0
    assert len(calls) == 1 and calls[0].count('--worktree-root') == 1
    assert calls[0][calls[0].index('--worktree-root') + 1] == str(target)
    assert calls[0][calls[0].index('--state-dir') + 1] == str(state)
    assert calls[0][calls[0].index('--merge-queue-dir') + 1] == str(state / 'merge-queue')
    assert history.read_bytes() == original
    assert not (state / 'worktrees').exists()
