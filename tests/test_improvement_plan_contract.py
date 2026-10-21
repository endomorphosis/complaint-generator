"""Behavioral contracts for native plan ingestion and progress preservation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from integrations.ipfs_accelerate.improvement_plan import (
    BOARD_RELATIVE, PLAN_RELATIVE, SPEC_RELATIVE,
    build_improvement_work_plan, generate, load_spec, validate_spec,
)


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


@pytest.fixture
def spec():
    tasks = []
    for index in range(1, 3):
        tasks.append({
            "id": f"CIMP-TUI-{index:02d}", "goal_id": "goal.tui", "subgoal_id": "subgoal.intake",
            "title": f"Verify intake behavior {index}", "priority": "P0",
            "targets": ["applications/complaint_workspace.py", "tests/test_tui.py"],
            "depends_on": ["CIMP-TUI-01"] if index == 2 else [],
            "acceptance": ["Answer updates the fact graph.", "Missing requirements produce relevant questions."],
            "validation_commands": ["python -m pytest -q tests/test_tui.py"],
            "implementation_prompt": "Use synthetic complaints only.\nInspect the shared intake flow.",
        })
    return {
        "schema_version": "complaint-generator/improvement-spec@1", "title": "Complaint improvement",
        "provider": {"router": "ipfs_accelerate_py.llm_router", "provider": "grok_cli", "model": "grok-4.7", "allow_fallback": False},
        "goals": [{"id": "goal.tui", "title": "Interactive intake", "subgoals": [{"id": "subgoal.intake", "title": "Question loop"}]}],
        "tasks": tasks, "execution_policy": {"synthetic_only": True}, "findings": [],
    }


def _write_spec(root: Path, spec: dict) -> Path:
    target = root / SPEC_RELATIVE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(spec), encoding="utf-8")
    return target


@pytest.mark.parametrize("change", [
    lambda s: s.update(tasks=[]),
    lambda s: s.update(goals=[]),
    lambda s: s.update(execution_policy={}),
    lambda s: s.update(schema_version=""),
    lambda s: s.update(findings={}),
    lambda s: s["provider"].update(model="grok-other"),
    lambda s: s["provider"].update(allow_fallback=True),
    lambda s: s["provider"].update(allow_fallback=0),
    lambda s: s["tasks"][0].update(goal_id="goal.missing"),
    lambda s: s["tasks"][0].update(subgoal_id="subgoal.missing"),
    lambda s: s["tasks"][0].update(goal_id=[]),
    lambda s: s["tasks"][0].update(priority=[]),
    lambda s: s["tasks"][0].update(depends_on=["CIMP-MISSING"]),
    lambda s: s["tasks"][0].update(depends_on=["CIMP-TUI-01"]),
    lambda s: s["tasks"][0].update(depends_on=["CIMP-TUI-02"]),
    lambda s: s["tasks"][1].update(id="CIMP-TUI-01"),
    lambda s: s["tasks"][0].update(targets=[]),
    lambda s: s["tasks"][0].update(acceptance=[""]),
    lambda s: s["tasks"][0].update(validation_commands=[]),
    lambda s: s["tasks"][0].update(validation_commands=[" "]),
    lambda s: s["tasks"][0].update(implementation_prompt=""),
    lambda s: s["tasks"][0].update(title="task\n## CIMP-INJECT fake"),
    lambda s: s["goals"][0]["subgoals"].append({"id": "subgoal.empty", "title": "Empty"}),
])
def test_invalid_spec_is_rejected_before_native_ingestion(spec, change):
    change(spec)
    with pytest.raises(ValueError):
        validate_spec(spec)


def test_task_cannot_reference_subgoal_belonging_to_another_goal(spec):
    spec["goals"].append({"id": "goal.storage", "title": "Storage", "subgoals": [{"id": "subgoal.storage", "title": "Private"}]})
    spec["tasks"][0]["subgoal_id"] = "subgoal.storage"
    with pytest.raises(ValueError, match="mismatched"):
        validate_spec(spec)


def test_native_roundtrip_preserves_behavior_evidence_and_dependency_graph(spec):
    plan = build_improvement_work_plan(spec)
    from ipfs_accelerate_py.agent_supervisor.planning.formal_planning_contracts import EvidenceRequirementKind, FormalWorkPlan

    restored = FormalWorkPlan.from_dict({**plan.to_dict(), "plan_id": plan.plan_id})
    assert restored.plan_id == plan.plan_id
    assert restored.events == ()
    assert restored.tasks[1].depends_on == ("CIMP-TUI-01",)
    assert all(item.kind is EvidenceRequirementKind.TEST for item in restored.evidence_requirements)
    assert {item.requirement_id for item in restored.evidence_requirements} == set(restored.goals[0].evidence_requirement_ids)
    assert restored.tasks[0].metadata["acceptance"] == spec["tasks"][0]["acceptance"]
    assert restored.tasks[0].metadata["validation_commands"] == spec["tasks"][0]["validation_commands"]
    assert restored.tasks[0].metadata["provider"]["allow_fallback"] is False
    assert restored.tasks[0].metadata["model"] == "grok-4.7"
    assert all("status" not in item.metadata for item in restored.tasks)


def test_generate_produces_real_native_markdown_tasks_without_claiming_completion(tmp_path, spec):
    path = _write_spec(tmp_path, spec)
    result = generate(path, tmp_path)
    from ipfs_accelerate_py.agent_supervisor.task_sources.taskboard_ingest import parse_markdown_field_board

    parsed = parse_markdown_field_board(Path(result["board_path"]).read_text(encoding="utf-8"))
    assert [item["task_id"] for item in parsed["tasks"]] == [item["id"] for item in spec["tasks"]]
    for task, source_task in zip(parsed["tasks"], spec["tasks"]):
        assert task["runtime_guidance"] == " ".join(source_task["implementation_prompt"].splitlines())
        assert task["status"] == "todo"
        assert task["completion"] == "validation"
        assert task["provider_role"] == "grok-only"
        assert task["implementation_provider"] == "grok"
        assert task["model"] == "grok-4.7"
        assert task["validation"] == "python -m pytest -q tests/test_tui.py"
        assert task["acceptance"] and task["outputs"] and task["goal"] and task["subgoal"]
    assert parsed["tasks"][1]["dependencies"] == ["CIMP-TUI-01"]
    receipt = result["receipt"]
    assert receipt["native_contract_ingested"] and receipt["native_roundtrip"]
    assert receipt["execution_started"] is False
    assert receipt["tasks_completed_by_ingestion"] == 0
    assert receipt["validations_executed"] == []
    assert receipt["native_validation"]["status"] != "consistent"
    assert any(item["code"] == "terminal_outcome_missing" for item in receipt["native_validation"]["findings"])
    assert Path(result["plan_path"]) == tmp_path / PLAN_RELATIVE
    json.dumps(receipt)


@pytest.mark.parametrize("runtime_status", ["in_progress", "blocked", "paused", "completed", "unknown_future_state"])
def test_same_plan_regeneration_preserves_every_runtime_status_and_unknown_fields(tmp_path, spec, runtime_status):
    path = _write_spec(tmp_path, spec)
    generate(path, tmp_path)
    board = tmp_path / BOARD_RELATIVE
    text = board.read_text().replace("- Status: todo", f"- Status: {runtime_status}", 1)
    text += "\n- Runtime claim: owner-42\n- Future metadata: preserve exactly\n"
    board.write_text(text)
    before = board.read_bytes()
    result = generate(path, tmp_path)
    assert board.read_bytes() == before
    assert result["receipt"]["board_preserved"] is True
    assert result["receipt"]["tasks_completed_by_ingestion"] == 0


def test_changed_spec_cannot_reset_existing_active_board(tmp_path, spec):
    path = _write_spec(tmp_path, spec)
    generate(path, tmp_path)
    board, plan = tmp_path / BOARD_RELATIVE, tmp_path / PLAN_RELATIVE
    before_board, before_plan = board.read_bytes(), plan.read_bytes()
    spec["tasks"][0]["acceptance"].append("Verify restart recovery.")
    _write_spec(tmp_path, spec)
    with pytest.raises(ValueError, match="migrate explicitly"):
        generate(path, tmp_path)
    assert board.read_bytes() == before_board
    assert plan.read_bytes() == before_plan


def test_injected_prompt_heading_cannot_create_an_extra_native_task(tmp_path, spec):
    spec["tasks"][0]["implementation_prompt"] += "\n## CIMP-INJECT Not a task\n- Status: completed"
    result = generate(_write_spec(tmp_path, spec), tmp_path)
    from ipfs_accelerate_py.agent_supervisor.task_sources.taskboard_ingest import parse_markdown_field_board

    parsed = parse_markdown_field_board(Path(result["board_path"]).read_text())
    assert len(parsed["tasks"]) == 2
    assert all(task["status"] == "todo" for task in parsed["tasks"])


def test_load_is_a_defensive_copy_and_does_not_advertise_spec_runtime_status(tmp_path, spec):
    spec["tasks"][0]["status"] = "completed"
    plan = build_improvement_work_plan(load_spec(_write_spec(tmp_path, spec)))
    assert "status" not in plan.tasks[0].metadata
    copied = validate_spec(spec)
    copied["tasks"][0]["targets"].append("another.py")
    assert copied != spec


def test_invalid_spec_writes_no_plan_or_board(tmp_path, spec):
    spec["tasks"][0]["validation_commands"] = []
    with pytest.raises(ValueError):
        generate(_write_spec(tmp_path, spec), tmp_path)
    assert not (tmp_path / PLAN_RELATIVE).exists()
    assert not (tmp_path / BOARD_RELATIVE).exists()


@pytest.mark.parametrize("paths", [
    None, "external/ipfs_datasets_py", ["/tmp/repo"], ["../repo"],
    ["external/../repo"], ["external//repo"], ["./external/repo"],
    ["external/repo/"], ["external\\repo"], ["external/.git"],
    ["external/*"], ["--recursive"], ["external/repo", "external/repo"],
    ["x" * 257], [f"external/repo-{i}" for i in range(17)],
])
def test_submodule_paths_reject_unconfined_or_malformed_values(spec, paths):
    spec["tasks"][0]["submodules"] = paths
    with pytest.raises(ValueError):
        validate_spec(spec)


def test_declared_submodules_survive_formal_and_real_native_daemon_ingestion(tmp_path, spec):
    paths = ["external/ipfs_accelerate_py", "external/ipfs_datasets_py", "external/ipfs_kit_py", "external/mike"]
    spec["tasks"][0]["submodules"] = paths
    spec["tasks"][1]["submodules"] = []
    plan = build_improvement_work_plan(spec)
    assert plan.tasks[0].metadata["submodules"] == paths
    assert plan.tasks[1].metadata["submodules"] == []
    generated = generate(_write_spec(tmp_path, spec), tmp_path)
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import (
        PortalImplementationDaemon, parse_task_file,
    )

    tasks = parse_task_file(Path(generated["board_path"]), task_header_prefix="## CIMP-")
    # The method reads task metadata only; construction would initialize
    # daemon services and is deliberately unnecessary for this parser check.
    daemon = object.__new__(PortalImplementationDaemon)
    assert daemon._task_declared_submodule_paths(tasks[0]) == tuple(sorted(paths))
    assert daemon._task_declared_submodule_paths(tasks[1]) == ()
    assert tasks[0].status == tasks[1].status == "todo"


def test_submodule_declaration_is_optional_and_does_not_change_old_plan_metadata(spec):
    plan = build_improvement_work_plan(spec)
    assert all("submodules" not in task.metadata for task in plan.tasks)
