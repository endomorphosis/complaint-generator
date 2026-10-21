"""Compile reviewed improvement specifications into native supervisor plans.

Compilation checks intended work. It executes no validation commands, produces
no implementation evidence, and never changes an existing task board's status.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping


SPEC_RELATIVE = "docs/task_boards/complaint_intake_improvement_spec.json"
PLAN_RELATIVE = "docs/task_boards/complaint_intake_formal_work_plan.json"
BOARD_RELATIVE = "docs/task_boards/complaint_intake_task_board.md"
_ACTOR_ID = "actor.complaint_improvement"
_PROVIDER = {
    "router": "ipfs_accelerate_py.llm_router",
    "provider": "grok_cli",
    "model": "grok-4.7",
    "allow_fallback": False,
}


def _text(value: Any, context: str, *, multiline: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be a nonempty string")
    if not multiline and ("\n" in value or "\r" in value):
        raise ValueError(f"{context} must be one line")
    return value.strip()


def _strings(value: Any, context: str, *, empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not empty):
        raise ValueError(f"{context} must be a {'possibly empty ' if empty else 'nonempty '}list")
    result = [_text(item, context) for item in value]
    if len(set(result)) != len(result):
        raise ValueError(f"{context} contains duplicates")
    return result


def validate_spec(spec: Any) -> dict[str, Any]:
    """Validate metadata and the complete task DAG before loading native code."""

    if not isinstance(spec, dict):
        raise ValueError("spec must be an object")
    _text(spec.get("schema_version"), "schema_version")
    _text(spec.get("title"), "title")
    if spec.get("provider") != _PROVIDER or spec["provider"].get("allow_fallback") is not False:
        raise ValueError("provider must use grok-4.7 through llm_router with fallback disabled")
    if not isinstance(spec.get("execution_policy"), dict) or not spec["execution_policy"]:
        raise ValueError("execution_policy must be a nonempty object")
    if not isinstance(spec.get("findings", []), list):
        raise ValueError("findings must be a list")
    goals = spec.get("goals")
    tasks = spec.get("tasks")
    if not isinstance(goals, list) or not goals or not isinstance(tasks, list) or not tasks:
        raise ValueError("goals and tasks must be nonempty lists")
    identifiers: set[str] = set()
    subgoal_parents: dict[str, str] = {}
    goal_ids: set[str] = set()

    def identify(record: Any, context: str) -> str:
        if not isinstance(record, dict):
            raise ValueError(f"{context} must be an object")
        identifier = _text(record.get("id"), f"{context}.id")
        if identifier != record["id"] or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", identifier):
            raise ValueError(f"{context}.id is not a stable identifier")
        if identifier in identifiers:
            raise ValueError(f"duplicate identifier: {identifier}")
        identifiers.add(identifier)
        _text(record.get("title"), f"{identifier}.title")
        return identifier

    for goal in goals:
        goal_id = identify(goal, "goal")
        goal_ids.add(goal_id)
        children = goal.get("subgoals")
        if not isinstance(children, list) or not children:
            raise ValueError(f"{goal_id}.subgoals must be nonempty")
        for subgoal in children:
            subgoal_parents[identify(subgoal, "subgoal")] = goal_id
    task_ids: set[str] = set()
    dependencies: dict[str, list[str]] = {}
    populated_subgoals: set[str] = set()
    for task in tasks:
        task_id = identify(task, "task")
        if not task_id.startswith("CIMP-"):
            raise ValueError("task identifiers must begin CIMP-")
        task_ids.add(task_id)
        goal_id = _text(task.get("goal_id"), f"{task_id}.goal_id")
        subgoal_id = _text(task.get("subgoal_id"), f"{task_id}.subgoal_id")
        if goal_id not in goal_ids or subgoal_parents.get(subgoal_id) != goal_id:
            raise ValueError(f"{task_id} has an unknown or mismatched goal/subgoal")
        populated_subgoals.add(subgoal_id)
        if _text(task.get("priority"), f"{task_id}.priority") not in {"P0", "P1", "P2", "P3"}:
            raise ValueError(f"{task_id}.priority must be P0, P1, P2 or P3")
        for field in ("targets", "acceptance", "validation_commands"):
            _strings(task.get(field), f"{task_id}.{field}")
        submodules = _strings(task.get("submodules", []), f"{task_id}.submodules", empty=True)
        if len(submodules) > 16:
            raise ValueError(f"{task_id}.submodules exceeds the sixteen-path bound")
        for path in submodules:
            if (len(path) > 256 or path != path.strip() or path.startswith("-")
                    or re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", path) is None
                    or any(part in {".", "..", ".git"} for part in path.split("/"))):
                raise ValueError(f"{task_id}.submodules must contain safe repository-relative paths")
        dependencies[task_id] = _strings(task.get("depends_on"), f"{task_id}.depends_on", empty=True)
        _text(task.get("implementation_prompt"), f"{task_id}.implementation_prompt", multiline=True)
    if populated_subgoals != set(subgoal_parents):
        raise ValueError("every subgoal must contain at least one implementation task")
    for task_id, upstream in dependencies.items():
        if task_id in upstream or not set(upstream) <= task_ids:
            raise ValueError(f"{task_id} has an unknown or self dependency")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ValueError(f"task dependency cycle at {task_id}")
        if task_id not in visited:
            visiting.add(task_id)
            for upstream in dependencies[task_id]:
                visit(upstream)
            visiting.remove(task_id)
            visited.add(task_id)

    for task_id in dependencies:
        visit(task_id)
    # A JSON round trip also rejects unexpected nonserializable metadata.
    return json.loads(json.dumps(spec, allow_nan=False))


def load_spec(path: Path | str) -> dict[str, Any]:
    return validate_spec(json.loads(Path(path).read_text(encoding="utf-8")))


def build_improvement_work_plan(spec: Mapping[str, Any]) -> Any:
    """Build canonical contracts with behavior-test evidence, without executing it."""

    spec = validate_spec(dict(spec))
    from integrations.ipfs_datasets.loader import ensure_import_paths

    ensure_import_paths("ipfs_accelerate_py.agent_supervisor")
    from ipfs_accelerate_py.agent_supervisor.planning.formal_planning_contracts import (
        Actor, ActorKind, EvidenceRequirement, EvidenceRequirementKind,
        FormalWorkPlan, Goal, PlanTask, RefinementMode, Subgoal,
    )
    from ipfs_accelerate_py.agent_supervisor.proof.formal_logic_vocabulary import (
        LOGIC_VOCABULARY_VERSION, ReviewedPredicate, TermSort,
        atom, constant, subgoal_satisfied,
    )

    requirements = tuple(
        EvidenceRequirement(
            requirement_id=f"test.{task['id']}",
            kind=EvidenceRequirementKind.TEST,
            subject_ids=(task["id"], task["subgoal_id"], task["goal_id"]),
            fallback_check_ids=tuple(task["validation_commands"]),
            metadata={
                "acceptance": task["acceptance"],
                "validation_commands": task["validation_commands"],
                "required_evidence": "Behavioral assertions at the tested source revision; skipped or unexecuted checks do not satisfy this requirement.",
            },
        ) for task in spec["tasks"]
    )
    formulas = []
    goals = []
    subgoals = []
    for goal in spec["goals"]:
        formula = atom(ReviewedPredicate.GOAL_SATISFIED, constant(TermSort.GOAL, goal["id"]))
        formulas.append(formula)
        goals.append(Goal(
            goal_id=goal["id"], owner_actor_id=_ACTOR_ID,
            satisfaction_formula_id=formula.formula_id,
            evidence_requirement_ids=tuple(f"test.{task['id']}" for task in spec["tasks"] if task["goal_id"] == goal["id"]),
            source_ids=(SPEC_RELATIVE,), metadata={"title": goal["title"]},
        ))
        for subgoal in goal["subgoals"]:
            formula = subgoal_satisfied(subgoal["id"])
            formulas.append(formula)
            subgoals.append(Subgoal(
                subgoal_id=subgoal["id"], goal_id=goal["id"], parent_id=goal["id"],
                refinement_mode=RefinementMode.SUFFICIENT,
                satisfaction_formula_id=formula.formula_id,
                evidence_requirement_ids=tuple(f"test.{task['id']}" for task in spec["tasks"] if task["subgoal_id"] == subgoal["id"]),
                metadata={"title": subgoal["title"]},
            ))
    tasks = tuple(PlanTask(
        task_id=task["id"], goal_id=task["goal_id"], subgoal_id=task["subgoal_id"],
        actor_ids=(_ACTOR_ID,), depends_on=tuple(task["depends_on"]),
        evidence_requirement_ids=(f"test.{task['id']}",),
        metadata={
            **{key: task[key] for key in ("title", "priority", "targets", "acceptance", "validation_commands", "implementation_prompt")},
            **({"submodules": task["submodules"]} if "submodules" in task else {}),
            "outputs": task["targets"], "provider": dict(_PROVIDER),
            "implementation_provider": "grok", "provider_role": "grok-only", "model": _PROVIDER["model"],
            "completion": "validation",
        },
    ) for task in spec["tasks"])
    return FormalWorkPlan(
        vocabulary_profile_id="supervisor-reviewed", vocabulary_version=LOGIC_VOCABULARY_VERSION,
        source_ids=("complaint-generator", SPEC_RELATIVE), repository_tree_id="",
        trace_bound=1,
        actors=(Actor(actor_id=_ACTOR_ID, kind=ActorKind.AGENT, principal_id="complaint-generator",
                      capabilities=("implementation", "behavioral_validation"), metadata={"provider": dict(_PROVIDER)}),),
        goals=tuple(goals), subgoals=tuple(subgoals), tasks=tasks,
        events=(), fluents=(), preconditions=(), effects=(), norms=(), temporal_constraints=(),
        evidence_requirements=requirements, formulas=tuple(formulas),
        metadata={"title": spec["title"], "provider": dict(_PROVIDER),
                  "execution_policy": spec["execution_policy"],
                  "spec_sha256": hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                  "evidence_policy": "Ingestion and bounded consistency are not execution or task completion."},
    )


def _render_board(spec: Mapping[str, Any], plan_id: str) -> str:
    lines = [f"# {spec['title']}", "", f"<!-- plan_id: {plan_id} -->", "",
             "Implementation tasks begin pending. Completion requires behavioral validation evidence.", ""]
    for task in spec["tasks"]:
        lines.extend([
            f"## {task['id']} {task['title']}", "",
            "- Status: todo", "- Completion: validation", f"- Priority: {task['priority']}",
            f"- Goal: {task['goal_id']}", f"- Subgoal: {task['subgoal_id']}",
            f"- Depends on: {', '.join(task['depends_on'])}",
            f"- Outputs: {', '.join(task['targets'])}",
            f"- Submodules: {', '.join(task.get('submodules', []))}",
            f"- Validation: {'; '.join(task['validation_commands'])}",
            f"- Acceptance: {' '.join(task['acceptance'])}",
            "- Implementation provider: grok", "- Provider role: grok-only", "- Model: grok-4.7",
            "- Router: ipfs_accelerate_py.llm_router", "- Provider fallback: disabled",
            "- Runtime guidance: " + " ".join(task["implementation_prompt"].splitlines()), "",
            "Implementation instructions:", "",
            *("> " + line for line in task["implementation_prompt"].splitlines()), "",
        ])
    return "\n".join(lines)


_TASK_HEADER_PREFIX = "## CIMP-"
_CONTRACT_METADATA = (
    "goal", "subgoal", "submodules", "implementation provider", "provider role",
    "model", "router", "provider fallback",
)


def _parsed_projection(text: str, root: Path) -> dict[str, Any]:
    """Parse with the production board path so semantic identities stay path-bound."""

    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import parse_task_text

    parsed = parse_task_text(text, path=root / BOARD_RELATIVE, task_header_prefix=_TASK_HEADER_PREFIX)
    tasks: dict[str, Any] = {}
    for task in parsed:
        if task.task_id in tasks:
            raise ValueError("existing task board differs from this plan; preserve it and migrate explicitly")
        tasks[task.task_id] = task
    return tasks


def _projection_drift(existing: Any, expected: Any) -> list[str]:
    """Return contract fields that differ. Runtime status and notes are not contract."""

    drifted = []
    if (existing.canonical_task_cid != expected.canonical_task_cid
            or existing.canonical_task_key != expected.canonical_task_key):
        drifted.append("semantic identity")
    if tuple(existing.outputs) != tuple(expected.outputs):
        drifted.append("outputs")
    if existing.acceptance != expected.acceptance:
        drifted.append("acceptance")
    if tuple(existing.depends_on) != tuple(expected.depends_on):
        drifted.append("dependencies")
    if tuple(existing.validation) != tuple(expected.validation):
        drifted.append("validation")
    if existing.completion != expected.completion or existing.completion != "validation":
        drifted.append("completion")
    for key in _CONTRACT_METADATA:
        if existing.metadata.get(key, "") != expected.metadata.get(key, ""):
            drifted.append(key)
    return drifted


def _require_matching_projection(existing_text: str, spec: Mapping[str, Any], plan_id: str, root: Path) -> None:
    expected_text = _render_board(spec, plan_id)
    existing, expected = _parsed_projection(existing_text, root), _parsed_projection(expected_text, root)
    planned = {task["id"] for task in spec["tasks"]}
    if set(existing) != planned or set(expected) != planned:
        raise ValueError("existing task board differs from this plan; preserve it and migrate explicitly")
    drifted = {task_id: _projection_drift(existing[task_id], expected[task_id]) for task_id in sorted(planned)}
    drifted = {task_id: fields for task_id, fields in drifted.items() if fields}
    if drifted:
        detail = "; ".join(f"{task_id}: {', '.join(fields)}" for task_id, fields in drifted.items())
        raise ValueError(
            "existing task board contract differs from this plan "
            f"({detail}); preserve it and migrate explicitly"
        )



def _require_emitted_projection(text: str, spec: Mapping[str, Any], root: Path) -> None:
    """Validate the actual native projection before publishing a new board."""
    tasks = _parsed_projection(text, root)
    if set(tasks) != {item["id"] for item in spec["tasks"]}:
        raise ValueError("rendered native projection differs from the specification")
    for item in spec["tasks"]:
        task = tasks[item["id"]]
        metadata = {
            "goal": item["goal_id"], "subgoal": item["subgoal_id"],
            "submodules": ", ".join(item.get("submodules", [])),
            "implementation provider": "grok", "provider role": "grok-only",
            "model": _PROVIDER["model"], "router": _PROVIDER["router"],
            "provider fallback": "disabled",
        }
        if (task.title != item["title"] or task.priority != item["priority"]
                or task.outputs != item["targets"] or task.depends_on != item["depends_on"]
                or task.validation != item["validation_commands"]
                or task.acceptance != " ".join(item["acceptance"])
                or task.completion != "validation"
                or any(task.metadata.get(key, "") != value for key, value in metadata.items())):
            raise ValueError(f"rendered native projection differs for {item['id']}")


def _atomic_create(path: Path, content: str) -> bool:
    """Publish complete bytes only if another creator has not won the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return False
        return True
    finally:
        Path(temporary).unlink(missing_ok=True)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def generate(spec_path: Path | str, repo_root: Path | str) -> dict[str, Any]:
    """Write native artifacts and return an honest, non-execution ingestion receipt.

    Existing matching Markdown is left byte-for-byte intact, including unknown
    runtime fields and states. A changed specification requires explicit board
    migration rather than resetting potentially active tasks to todo.
    """

    spec_path = Path(spec_path).resolve()
    root = Path(repo_root).resolve()
    spec = load_spec(spec_path)
    plan = build_improvement_work_plan(spec)
    from ipfs_accelerate_py.agent_supervisor.planning.formal_planning_contracts import FormalWorkPlan
    from ipfs_accelerate_py.agent_supervisor.planning.formal_plan_validator import FormalPlanValidator

    document = {**plan.to_dict(), "plan_id": plan.plan_id}
    restored = FormalWorkPlan.from_dict(document)
    if restored.plan_id != plan.plan_id:
        raise ValueError("native plan round trip changed identity")
    validation = FormalPlanValidator().validate(restored)
    rendered = _render_board(spec, plan.plan_id)
    _require_emitted_projection(rendered, spec, root)
    plan_path, board_path = root / PLAN_RELATIVE, root / BOARD_RELATIVE
    marker = f"<!-- plan_id: {plan.plan_id} -->"
    board_preserved = board_path.exists()
    if not board_preserved:
        # Hard-link publication is atomic and cannot replace a concurrent
        # creator's held/owned board. Validate that winner before writing plan.
        board_preserved = not _atomic_create(board_path, rendered)
    if board_preserved:
        existing = board_path.read_text(encoding="utf-8")
        headings = re.findall(r"^## (CIMP-[A-Za-z0-9_.:-]+)(?:\s|$)", existing, re.MULTILINE)
        if marker not in existing or len(headings) != len(set(headings)) or set(headings) != {task["id"] for task in spec["tasks"]}:
            raise ValueError("existing task board differs from this plan; preserve it and migrate explicitly")
        # Same plan marker and headings are not a contract. Compare the native
        # parse before any artifact write so a drifted active board is neither
        # rewritten nor given an ingestion receipt.
        _require_matching_projection(existing, spec, plan.plan_id, root)
    # The board is not touched at all when it already exists, so a concurrent
    # daemon can keep changing its statuses without a compiler overwrite race.
    _atomic_write(plan_path, json.dumps(document, indent=2, sort_keys=True) + "\n")
    receipt = {
        "schema_version": "complaint-generator/improvement-plan-ingestion@1",
        "plan_id": plan.plan_id, "native_roundtrip": True, "native_contract_ingested": True,
        "admission_status": "native_contract_ingested_open_plan", "consistency_claimed": False,
        "task_count": len(plan.tasks), "goal_count": len(plan.goals), "subgoal_count": len(plan.subgoals),
        "provider": dict(_PROVIDER), "board_preserved": board_preserved,
        "execution_started": False, "tasks_completed_by_ingestion": 0,
        "validations_executed": [], "native_validation": validation.to_record(),
        "trace_scope": "Open, unexecuted implementation plan; no terminal runtime events or test evidence are asserted.",
        "scope": "Native contract ingestion and bounded consistency only; no task implementation, test execution, provider invocation or completion evidence.",
    }
    return {"spec_path": str(spec_path), "plan_path": str(plan_path), "board_path": str(board_path), "receipt": receipt}
