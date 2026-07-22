import importlib.util
import json
import os
import re
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


def test_queue_refill_maintains_work_item_floor_without_duplicate_active_bundles(
    tmp_path, monkeypatch
) -> None:
    bundle_dir = tmp_path / "bundles"
    bundle_dir.mkdir()
    (bundle_dir / "index.json").write_text("{}\n", encoding="utf-8")
    todo_path = tmp_path / "todo.md"
    todo_path.write_text(
        "\n".join(
            [
                "- [ ] Task checkbox-1: REF-001 First task",
                "- [ ] Task checkbox-2: REF-002 Second task",
                "- [ ] Task checkbox-3: REF-003 Third task",
                "- [x] Task checkbox-4: REF-004 Completed task",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", bundle_dir)
    monkeypatch.setattr(supervisor, "TODO_PATH", todo_path)
    monkeypatch.setattr(supervisor, "QUEUE_PATH", tmp_path / "queue.duckdb")

    def task(task_id: str, priority: str = "P0") -> dict[str, object]:
        return {
            "task_id": task_id,
            "title": f"Title {task_id}",
            "priority": priority,
            "goal_id": "G1",
            "subgoal_id": "G1.S1",
            "acceptance": [f"Accept {task_id}"],
            "validation": [f"validate {task_id}"],
            "paths": [f"{task_id}.py"],
        }

    payloads = [
        {"bundle_key": "refactor/g1/g1-s1", "tasks": [task("REF-001"), task("REF-002")]},
        {"bundle_key": "refactor/g1/g1-s2", "tasks": [task("REF-003", "P1"), task("REF-004")]},
    ]
    monkeypatch.setattr(supervisor, "_upstream_bundle_payload_builder", lambda: lambda _path: payloads)

    class FakeQueue:
        items: list[dict[str, object]] = []

        def __init__(self, _path: str):
            pass

        def list(self, *, status, limit, task_types):
            return [item for item in self.items if item["status"] == status][:limit]

        def submit(self, *, task_type, model_name, payload):
            task_id = f"queue-{len(self.items) + 1}"
            self.items.append(
                {
                    "task_id": task_id,
                    "task_type": task_type,
                    "model_name": model_name,
                    "payload": payload,
                    "status": "queued",
                }
            )
            return task_id

        def close(self):
            pass

    monkeypatch.setattr(supervisor, "_task_queue_class", lambda: FakeQueue)

    first = supervisor.refill_bundle_queue(refill_floor=3)
    second = supervisor.refill_bundle_queue(refill_floor=3)

    assert first["floor_satisfied"] is True
    assert first["queued_work_items_after"] == 3
    assert first["submitted_bundle_count"] == 2
    assert second["submitted_bundle_count"] == 0
    assert second["queued_work_items_before"] == 3
    assert len(FakeQueue.items) == 2
    queued_payload = FakeQueue.items[0]["payload"]
    assert queued_payload["schema"] == "complaint_generator.refactor_supervisor.bundle_task.v1"
    assert queued_payload["goal_id"] == "G1"
    assert queued_payload["subgoal_id"] == "G1.S1"
    assert queued_payload["priority"] == "P0"
    assert queued_payload["acceptance"]
    assert queued_payload["validation"]


def test_goal_json_projects_header_statuses_and_resolves_seed_task_ids(tmp_path, monkeypatch) -> None:
    todo_path = tmp_path / "todo.md"
    todo_path.write_text(
        "\n".join(
            [
                "## REF-001 Seed task",
                "",
                "- Status: completed",
                "",
                "## REF-027 Generated task",
                "",
                "- Status: todo",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(supervisor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "TODO_PATH", todo_path)
    monkeypatch.setattr(supervisor, "OBJECTIVE_PATH", tmp_path / "objective.md")
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", tmp_path / "bundles")
    monkeypatch.setattr(supervisor, "QUEUE_PATH", tmp_path / "queue.duckdb")
    seed_task = supervisor.RefactorTask(
        goal_id="G1",
        subgoal_id="G1.S1",
        title="Seed task",
        priority="P0",
        files=("seed.py",),
        rationale="Keep projections synchronized.",
        acceptance=("Status is visible.",),
        validation=("python -m py_compile seed.py",),
    )
    goals = [
        {
            "id": "G1",
            "title": "Goal",
            "priority": "P0",
            "subgoals": [{"id": "G1.S1", "title": "Subgoal", "tasks": [seed_task]}],
        }
    ]

    taskboard = supervisor._taskboard_snapshot()
    payload = supervisor._json_goal_tree(goals, {}, taskboard=taskboard)
    projected = payload["goals"][0]["subgoals"][0]["tasks"][0]

    assert taskboard["task_count"] == 2
    assert taskboard["tasks"][1]["task_id"] == "REF-027"
    assert projected["task_id"] == "REF-001"
    assert projected["status"] == "complete"


def test_seed_goal_tree_preserves_follow_on_planning_extensions() -> None:
    generated = {
        "generated_at": "new",
        "goals": [{"id": "G1"}],
        "scan": {"python_file_count": 1},
    }
    existing = {
        "generated_at": "old",
        "goals": [{"id": "stale"}],
        "implementation_claims": [{"id": "CLAIM-001"}],
    }

    merged = supervisor._merge_goal_tree_extensions(generated, existing)

    assert merged["generated_at"] == "new"
    assert merged["goals"] == [{"id": "G1"}]
    assert merged["implementation_claims"] == [{"id": "CLAIM-001"}]


def test_taskboard_projects_canonical_ipfs_p0_cross_links(tmp_path, monkeypatch) -> None:
    backlog = tmp_path / "ipfs-backlog.md"
    taskboard = tmp_path / "taskboard.md"
    backlog.write_text(
        "# Backlog\n\n"
        "| ID | Workstream | Status | Priority | Outcome |\n"
        "|---|---|---|---|---|\n"
        "| W1 | Adapter | In Progress | P0 | Stable contracts |\n\n"
        f"{supervisor.IPFS_P0_CROSS_LINKS_START}\n"
        "## P0 Refactor Supervisor Cross-Links\n\n"
        "| IPFS workstream | Refactor goal(s) | Package coverage | Merge and scope rule |\n"
        "|---|---|---|---|\n"
        "| W1 | G3.S1 | W1.1 | Merge matching claims. |\n"
        f"{supervisor.IPFS_P0_CROSS_LINKS_END}\n\n"
        "## Workstream details\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(supervisor, "IPFS_EXECUTION_BACKLOG_PATH", backlog)
    monkeypatch.setattr(supervisor, "TASKBOARD_DOC_PATH", taskboard)
    scan = {
        "python_file_count": 1,
        "python_total_lines": 2,
        "test_file_count": 3,
        "signals": {
            "direct_ipfs_import_count": 0,
            "sys_path_mutation_count": 0,
            "broad_exception_count": 0,
        },
    }

    goals = [
        {
            "id": "G3",
            "subgoals": [{"id": "G3.S1", "title": "Contracts", "tasks": []}],
            "title": "Adapters",
            "priority": "P0",
        }
    ]
    supervisor._write_taskboard_doc(
        goals,
        scan,
        {},
        {},
        {},
        queue_refill={},
        taskboard={},
    )

    rendered = taskboard.read_text(encoding="utf-8")
    assert rendered.count("## P0 Refactor Supervisor Cross-Links") == 1
    assert "| W1 | G3.S1 | W1.1 | Merge matching claims. |" in rendered
    assert rendered.index("## P0 Refactor Supervisor Cross-Links") < rendered.index("## Goals")


def test_ipfs_p0_cross_link_markers_must_be_unique(tmp_path) -> None:
    backlog = tmp_path / "ipfs-backlog.md"
    backlog.write_text(
        "# Backlog\n\n"
        f"{supervisor.IPFS_P0_CROSS_LINKS_START}\n"
        "mapping\n",
        encoding="utf-8",
    )

    try:
        supervisor._read_ipfs_p0_cross_links(backlog)
    except ValueError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("malformed mapping markers should fail taskboard generation")


def test_repository_ipfs_p0_cross_links_cover_the_overview_and_known_goals() -> None:
    section = supervisor._read_ipfs_p0_cross_links()
    goals = supervisor.build_goals({"signals": {}})

    supervisor._validate_ipfs_p0_cross_link_goals(section, goals)

    rows = [line for line in section if re.match(r"^\| W\d+\b", line)]
    assert [re.match(r"^\| (W\d+)\b", line).group(1) for line in rows] == [
        "W1",
        "W2",
        "W3",
        "W4",
        "W9",
        "W10",
    ]
    assert all("Merge and scope rule" not in row and row.count("|") >= 5 for row in rows)


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
    monkeypatch.setattr(supervisor, "TASK_STATE_PATH", tmp_path / "task-state.json")
    monkeypatch.setattr(supervisor, "MANAGED_DAEMON_PID_PATH", tmp_path / "managed-daemon.pid")
    monkeypatch.setattr(supervisor, "GOALS_PATH", tmp_path / "goals.json")
    monkeypatch.setattr(supervisor, "TODO_PATH", tmp_path / "todo.md")
    monkeypatch.setattr(supervisor, "QUEUE_PATH", tmp_path / "queue.duckdb")
    monkeypatch.setattr(supervisor, "BUNDLE_LANE_MANIFEST", tmp_path / "lanes.json")
    monkeypatch.setattr(supervisor, "BUNDLE_SCHEDULER_PID_PATH", tmp_path / "bundle-scheduler.pid")
    monkeypatch.setattr(supervisor, "BUNDLE_SCHEDULER_LOG_PATH", tmp_path / "bundle-scheduler.log")
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


def test_durable_status_projection_repairs_primary_counts_and_bundle_shards(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", tmp_path / "bundles")
    supervisor.BUNDLE_DIR.mkdir()
    supervisor.TODO_PATH.write_text(
        """- [ ] Task checkbox-1: REF-001 First task

## REF-001 First task

- Status: todo

## REF-002 Second task

- Status: completed
""",
        encoding="utf-8",
    )
    shard = supervisor.BUNDLE_DIR / "objective.todo.md"
    shard.write_text(
        """- [ ] Task checkbox-1: REF-001 First task

## REF-001 First task

- Status: todo

- [ ] Task checkbox-2: REF-002 Second task

## REF-002 Second task

- Status: todo
""",
        encoding="utf-8",
    )
    colliding_shard = supervisor.BUNDLE_DIR / "repair.todo.md"
    colliding_shard.write_text(
        """- [ ] Task checkbox-1: REF-001 Different repair task

## REF-001 Different repair task

- Status: todo
- Dedupe key: reconciliation_guardrail:different_repair
""",
        encoding="utf-8",
    )
    supervisor.TASK_STATE_PATH.write_text(
        json.dumps({"completed_task_ids": ["REF-001"], "blocked_task_ids": []}),
        encoding="utf-8",
    )

    projected = supervisor.synchronize_taskboard_statuses()

    assert projected["completed_count"] == 2
    assert supervisor._todo_counts() == {
        "needed": 0,
        "in_progress": 0,
        "complete": 2,
        "blocked": 0,
    }
    assert "- [x] Task checkbox-1: REF-001" in supervisor.TODO_PATH.read_text(encoding="utf-8")
    shard_text = shard.read_text(encoding="utf-8")
    assert "- [x] Task checkbox-1: REF-001" in shard_text
    assert "- [x] Task checkbox-2: REF-002" in shard_text
    assert shard_text.count("- Status: completed") == 2
    colliding_text = colliding_shard.read_text(encoding="utf-8")
    assert "- [ ] Task checkbox-1: REF-001 Different repair task" in colliding_text
    assert "- Status: todo" in colliding_text


def test_seed_bundle_index_carries_durable_member_status(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(supervisor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", tmp_path / "bundles")
    monkeypatch.setattr(supervisor, "TASKBOARD_DOC_PATH", tmp_path / "taskboard.md")
    task = supervisor.RefactorTask(
        goal_id="G1",
        subgoal_id="G1.S1",
        title="Completed member",
        priority="P0",
        files=(),
        rationale="Already merged.",
        acceptance=("Receipt exists.",),
        validation=("true",),
        task_id="REF-001",
    )
    goals = [
        {
            "id": "G1",
            "title": "Goal",
            "priority": "P0",
            "subgoals": [{"id": "G1.S1", "title": "Subgoal", "tasks": [task]}],
        }
    ]

    supervisor.write_seed_bundle_index(goals, task_statuses={"REF-001": "completed"})

    index = json.loads((supervisor.BUNDLE_DIR / "index.json").read_text(encoding="utf-8"))
    member = index["bundles"]["refactor/g1/g1-s1"]["tasks"][0]
    assert member["status"] == "completed"


def test_start_parallel_detaches_scheduler_and_uses_requested_poll_interval(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(supervisor, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(supervisor, "ACCELERATE_REPO", tmp_path / "ipfs_accelerate_py")
    monkeypatch.setattr(supervisor, "BUNDLE_DIR", tmp_path / "bundles")
    monkeypatch.setattr(supervisor, "BUNDLE_LANE_ROOT", tmp_path / "bundle-lanes")
    monkeypatch.setattr(supervisor, "BUNDLE_COORDINATION_PATH", tmp_path / "coordination.sqlite3")
    monkeypatch.setattr(supervisor, "active_bundle_keys", lambda: set())
    monkeypatch.setattr(
        supervisor,
        "seed_taskboard",
        lambda **_kwargs: {"counts": {"todo": {}}, "bundle_seed": {"generated": 2}},
    )
    monkeypatch.setattr(supervisor, "_pid_alive", lambda pid: pid == 4242)
    monkeypatch.setattr(supervisor.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        supervisor,
        "_collect_counts",
        lambda: ({"todo": {}, "queue": {}}, {}),
    )
    captured: dict[str, object] = {}

    class Process:
        pid = 4242

        @staticmethod
        def poll():
            return None

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Process()

    monkeypatch.setattr(supervisor.subprocess, "Popen", fake_popen)
    args = supervisor.build_parser().parse_args(["start-parallel", "--interval-s", "37"])

    payload = supervisor.run_parallel_bundle_supervisor(args, start=True)

    command = captured["command"]
    assert isinstance(command, list)
    assert command[:3] == [sys.executable, "-m", "ipfs_accelerate_py.agent_supervisor.bundle_supervisor"]
    assert command[command.index("--poll-interval") + 1] == "37.0"
    assert command[-1] == "--start"
    assert captured["kwargs"]["start_new_session"] is True
    assert captured["kwargs"]["stdin"] is subprocess.DEVNULL
    assert payload["status"] == "started"
    assert supervisor.BUNDLE_SCHEDULER_PID_PATH.read_text(encoding="utf-8") == "4242\n"


def test_status_projects_dynamic_parallel_scheduler_manifest(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(
        supervisor,
        "_collect_counts",
        lambda: ({"todo": {}, "queue": {}}, {}),
    )
    supervisor.BUNDLE_SCHEDULER_PID_PATH.write_text(f"{os.getpid()}\n", encoding="utf-8")
    supervisor.BUNDLE_LANE_MANIFEST.write_text(
        json.dumps(
            {
                "schema": "ipfs_accelerate_py.agent_supervisor.dynamic_bundle_scheduler@1",
                "scheduler_state": "running",
                "cycle": 3,
                "planned_count": 8,
                "started_count": 2,
                "running_count": 2,
                "ready_count": 5,
                "blocked_count": 1,
                "completed_count": 4,
                "lanes": [
                    {
                        "bundle_key": "objective/a",
                        "state": "running",
                        "pid": 123,
                        "task_ids": ["T-1"],
                        "conflict_color": 2,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = supervisor.status_payload()

    assert payload["parallel_scheduler"]["pid_alive"] is True
    assert payload["parallel_lanes"]["running_count"] == 2
    assert payload["parallel_lanes"]["ready_count"] == 5
    assert payload["parallel_lanes"]["lanes"][0]["task_ids"] == ["T-1"]


def test_parallel_scheduler_has_explicit_stop_command() -> None:
    assert supervisor.build_parser().parse_args(["stop-parallel"]).command == "stop-parallel"


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
    managed = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import signal,sys,time; "
                "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); "
                "print('managed-ready', flush=True); time.sleep(60)"
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "ready"
        assert managed.stdout is not None
        assert managed.stdout.readline().strip() == "managed-ready"
        supervisor.PID_PATH.write_text(f"{child.pid}\n", encoding="utf-8")
        supervisor.MANAGED_DAEMON_PID_PATH.write_text(f"{managed.pid}\n", encoding="utf-8")

        result = supervisor.stop_daemon()

        child.wait(timeout=2)
        managed.wait(timeout=2)
        assert result["status"] == "stopped"
        assert result["pid"] == child.pid
        assert result["pid_alive"] is False
        assert result["signal_scope"] == "process_group"
        assert result["managed_daemon_pid"] == managed.pid
        assert result["managed_daemon_pid_alive"] is False
        assert result["managed_daemon_signal_scope"] == "process_group"
        assert not supervisor.PID_PATH.exists()
        assert not supervisor.MANAGED_DAEMON_PID_PATH.exists()
        persisted = json.loads(supervisor.STATUS_PATH.read_text(encoding="utf-8"))
        assert persisted["status"] == "stopped"
        assert persisted["pid"] == child.pid
        assert persisted["pid_alive"] is False
        assert persisted["counts"] == counts
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=2)
        if managed.poll() is None:
            managed.terminate()
            managed.wait(timeout=2)


def test_stop_daemon_stops_orphaned_managed_worker(tmp_path, monkeypatch) -> None:
    _isolate_status_paths(tmp_path, monkeypatch)
    monkeypatch.setattr(supervisor, "STOP_TIMEOUT_SECONDS", 5.0)
    monkeypatch.setattr(
        supervisor,
        "_collect_counts",
        lambda: ({"todo": {}, "queue": {}}, {}),
    )
    managed = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import signal,sys,time; signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); time.sleep(60)",
        ],
        start_new_session=True,
    )
    try:
        supervisor.MANAGED_DAEMON_PID_PATH.write_text(f"{managed.pid}\n", encoding="utf-8")

        result = supervisor.stop_daemon()

        managed.wait(timeout=2)
        assert result["status"] == "stopped"
        assert result["pid"] == 0
        assert result["managed_daemon_pid"] == managed.pid
        assert result["managed_daemon_pid_alive"] is False
    finally:
        if managed.poll() is None:
            managed.terminate()
            managed.wait(timeout=2)
