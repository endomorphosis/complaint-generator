import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "refactor_agent_supervisor.py"
SPEC = importlib.util.spec_from_file_location("complaint_generator_refactor_agent_supervisor", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
supervisor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = supervisor
SPEC.loader.exec_module(supervisor)

ROUTER_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "llm_router_merge_resolver.py"
ROUTER_SPEC = importlib.util.spec_from_file_location("complaint_generator_llm_router_merge_resolver", ROUTER_SCRIPT_PATH)
assert ROUTER_SPEC is not None and ROUTER_SPEC.loader is not None
router_resolver = importlib.util.module_from_spec(ROUTER_SPEC)
sys.modules[ROUTER_SPEC.name] = router_resolver
ROUTER_SPEC.loader.exec_module(router_resolver)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )


def test_renderers_use_supervisor_validation_command_delimiter() -> None:
    task = supervisor.RefactorTask(
        goal_id="G9",
        subgoal_id="G9.S1",
        title="Validate command rendering",
        priority="P0",
        files=("scripts/refactor_agent_supervisor.py",),
        rationale="Keep generated validation commands independently executable.",
        acceptance=("Both commands remain distinct.",),
        validation=(
            "python -m pytest tests/test_first.py -q",
            "python -m pytest tests/test_second.py -q",
        ),
    )
    goals = [
        {
            "id": "G9",
            "title": "Supervisor throughput",
            "priority": "P0",
            "subgoals": [
                {
                    "id": "G9.S1",
                    "title": "Validation routing",
                    "tasks": [task],
                }
            ],
        }
    ]
    expected = (
        "- Validation: python -m pytest tests/test_first.py -q; "
        "python -m pytest tests/test_second.py -q"
    )

    assert expected in supervisor._render_objective_heap(goals)
    assert expected in supervisor._task_block(task, "REF-900", 900)


def test_merge_watchdog_skips_aborted_historical_merge(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "checkout", "-b", "main")
    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        json.dumps(
            {
                "type": "merge_reconciled",
                "task_id": "REF-901",
                "resolved": False,
                "merge_result": {
                    "attempted": True,
                    "merged": False,
                    "branch": "implementation/ref-901",
                    "target_branch": "main",
                    "reason": "content_conflict",
                    "main_worktree_path": str(repo),
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(supervisor, "PROJECT_ROOT", repo)
    monkeypatch.setattr(supervisor, "MERGE_RESOLVER_STATUS_PATH", tmp_path / "status.json")
    monkeypatch.setattr(supervisor, "MERGE_RESOLVER_REGISTRY_DIR", tmp_path / "registry")
    monkeypatch.setattr(supervisor, "merge_event_paths", lambda: [events_path])

    result = supervisor.resolve_merge_conflicts_once(timeout_seconds=1)

    assert result["attempted_count"] == 0
    assert result["applied_count"] == 0
    assert result["results"][0]["skip_reason"] == "merge_not_active"


def test_router_commit_preserves_unrelated_dirty_paths(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "checkout", "-b", "main")
    _git(repo, "config", "user.email", "agent@example.com")
    _git(repo, "config", "user.name", "Agent")
    intended = repo / "intended.txt"
    unrelated = repo / "unrelated.txt"
    intended.write_text("before\n", encoding="utf-8")
    unrelated.write_text("before\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")
    intended.write_text("after\n", encoding="utf-8")
    unrelated.write_text("user change\n", encoding="utf-8")

    assert router_resolver._stage_and_commit_if_resolved(
        repo,
        paths_to_stage=["intended.txt"],
    )

    assert _git(repo, "show", "HEAD:intended.txt").stdout == "after\n"
    assert _git(repo, "show", "HEAD:unrelated.txt").stdout == "before\n"
    assert _git(repo, "status", "--short").stdout == " M unrelated.txt\n"
    assert not router_resolver._stage_and_commit_if_resolved(repo, paths_to_stage=[])


def test_merge_watchdog_has_explicit_stop_command() -> None:
    assert supervisor.build_parser().parse_args(["stop-merge-watchdog"]).command == "stop-merge-watchdog"


def _isolate_status_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(supervisor, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "STATUS_PATH", tmp_path / "status.json")
    monkeypatch.setattr(supervisor, "PID_PATH", tmp_path / "supervisor.pid")
    monkeypatch.setattr(supervisor, "GOALS_PATH", tmp_path / "goals.json")
    monkeypatch.setattr(supervisor, "TODO_PATH", tmp_path / "todo.md")
    monkeypatch.setattr(supervisor, "QUEUE_PATH", tmp_path / "queue.duckdb")
    monkeypatch.setattr(supervisor, "BUNDLE_LANE_MANIFEST", tmp_path / "lanes.json")
    monkeypatch.setattr(supervisor, "MERGE_RESOLVER_STATUS_PATH", tmp_path / "merge-status.json")
    monkeypatch.setattr(supervisor, "MERGE_RESOLVER_PID_PATH", tmp_path / "merge.pid")
    monkeypatch.setattr(supervisor, "UPSTREAM_SUPERVISOR_STATUS_PATH", tmp_path / "upstream-status.json")


def test_status_snapshot_has_stable_handoff_metrics(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    counts = {
        "todo": {"needed": 7, "in_progress": 2, "complete": 11, "blocked": 1},
        "queue": {"queued": 5, "running": 1, "completed": 9, "failed": 2},
    }
    monkeypatch.setattr(supervisor, "_collect_counts", lambda: (counts, {}))
    scan_summary = {
        "scanned_at": "2026-07-21T12:00:00Z",
        "python_file_count": 42,
        "python_total_lines": 9001,
        "test_file_count": 13,
        "direct_ipfs_import_count": 3,
        "sys_path_mutation_count": 2,
        "broad_exception_count": 8,
    }

    supervisor._write_status(
        {
            "status": "seeded",
            "pid": 0,
            "pid_alive": False,
            "scan_summary": scan_summary,
            "counts": counts,
        }
    )

    persisted = json.loads(supervisor.STATUS_PATH.read_text(encoding="utf-8"))
    assert persisted["schema"] == supervisor.STATUS_SCHEMA
    assert persisted["pid"] == 0
    assert persisted["pid_alive"] is False
    assert persisted["heartbeat"] == persisted["heartbeat_at"] == persisted["updated_at"]
    assert persisted["scan_summary"] == scan_summary
    assert persisted["counts"] == counts
    assert persisted["todo_counts"] == counts["todo"]
    assert persisted["queue_counts"] == counts["queue"]

    inspected = supervisor.status_payload()
    assert inspected["pid"] == 0
    assert inspected["heartbeat"] == persisted["heartbeat"]
    assert inspected["heartbeat_age_seconds"] is not None
    assert inspected["scan_summary"] == scan_summary
    assert inspected["counts"] == counts


def test_status_uses_live_upstream_heartbeat(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    counts = {
        "todo": {"needed": 0, "in_progress": 0, "complete": 0, "blocked": 0},
        "queue": {"queued": 0, "running": 0, "completed": 0, "failed": 0},
    }
    monkeypatch.setattr(supervisor, "_collect_counts", lambda: (counts, {}))
    supervisor.STATUS_PATH.write_text(
        json.dumps({"status": "started", "pid": os.getpid(), "heartbeat": "2026-01-01T00:00:00Z"}),
        encoding="utf-8",
    )
    supervisor.PID_PATH.write_text(f"{os.getpid()}\n", encoding="utf-8")
    supervisor.UPSTREAM_SUPERVISOR_STATUS_PATH.write_text(
        json.dumps({"status": "running", "heartbeat_at": "2026-07-21T12:34:56Z"}),
        encoding="utf-8",
    )

    payload = supervisor.status_payload()

    assert payload["pid"] == os.getpid()
    assert payload["pid_alive"] is True
    assert payload["heartbeat"] == "2026-07-21T12:34:56Z"
    assert payload["heartbeat_at"] == payload["heartbeat"]
    assert payload["upstream_supervisor_status"]["status"] == "running"


def test_stop_daemon_terminates_process_group_and_cleans_pid(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    counts = {
        "todo": {"needed": 0, "in_progress": 0, "complete": 0, "blocked": 0},
        "queue": {"queued": 0, "running": 0, "completed": 0, "failed": 0},
    }
    monkeypatch.setattr(supervisor, "_collect_counts", lambda: (counts, {}))
    monkeypatch.setattr(supervisor, "STOP_TIMEOUT_SECONDS", 5.0)
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import signal,sys,time; "
                "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); "
                "print('ready', flush=True); time.sleep(60)"
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "ready"
        supervisor.PID_PATH.write_text(f"{child.pid}\n", encoding="utf-8")

        result = supervisor.stop_daemon()

        child.wait(timeout=2)
        assert result["status"] == "stopped"
        assert result["pid"] == child.pid
        assert result["pid_alive"] is False
        assert result["signal_scope"] == "process_group"
        assert not supervisor.PID_PATH.exists()
        persisted = json.loads(supervisor.STATUS_PATH.read_text(encoding="utf-8"))
        assert persisted["status"] == "stopped"
        assert persisted["pid"] == child.pid
        assert persisted["pid_alive"] is False
        assert persisted["counts"] == counts
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=2)
