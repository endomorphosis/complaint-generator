import importlib.util
import json
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
