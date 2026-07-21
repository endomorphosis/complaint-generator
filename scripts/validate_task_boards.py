#!/usr/bin/env python3
"""Validate supervisor task boards and backlog docs.

The checks are intentionally lightweight so they can run in local dev,
CI, or an external ipfs_accelerate_py worker before claiming implementation
tasks from the board.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BOARD_PATH = REPO_ROOT / "docs/task_boards/ipfs_supervisor_task_board.json"
PAYLOAD_CONTRACTS = REPO_ROOT / "docs/PAYLOAD_CONTRACTS.md"
DOCS_TO_LINT = [
    REPO_ROOT / "docs/CLAIM_SUPPORT_REVIEW_DASHBOARD_EXECUTION_BACKLOG.md",
    REPO_ROOT / "docs/INTAKE_EVIDENCE_EXECUTION_BACKLOG.md",
    REPO_ROOT / "docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md",
    REPO_ROOT / "docs/IPFS_DATASETS_PY_MILESTONE_CHECKLIST.md",
    PAYLOAD_CONTRACTS,
    REPO_ROOT / "docs/TEMPORAL_TIMELINE_PROOF_EXECUTION_BACKLOG.md",
]
VALID_STATUSES = {
    "complete",
    "validation_required",
    "in_progress",
    "planned",
    "deferred",
    "blocked",
}
VALID_PRIORITIES = {"P0", "P1", "P2"}
STALE_ABSOLUTE_PREFIX = "/home/barberb/complaint-generator"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: top-level JSON value must be an object")
    return payload


def _line_number(text: str, offset: int) -> int:
    return text[:offset].count("\n") + 1


def _validate_json_fences(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    for index, match in enumerate(re.finditer(r"```json\n(.*?)\n```", text, re.S), start=1):
        body = match.group(1)
        try:
            json.loads(body)
        except json.JSONDecodeError as exc:
            start_line = _line_number(text, match.start())
            errors.append(
                f"{path.relative_to(REPO_ROOT)}: json fence {index} starting at line "
                f"{start_line} is invalid: {exc}"
            )
    return errors


def _validate_no_stale_absolute_links(paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if STALE_ABSOLUTE_PREFIX in line:
                errors.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_number}: stale absolute link "
                    f"uses {STALE_ABSOLUTE_PREFIX}"
                )
    return errors


def _section_status_conflicts(path: Path) -> list[str]:
    """Find sections marked planned even though every checklist item is checked."""

    errors: list[str] = []
    current_heading = ""
    current_status = ""
    checked = 0
    unchecked = 0
    status_line = 0

    def flush() -> None:
        nonlocal checked, unchecked, current_heading, current_status, status_line
        if current_status == "Planned" and checked > 0 and unchecked == 0:
            errors.append(
                f"{path.relative_to(REPO_ROOT)}:{status_line}: section "
                f"{current_heading!r} is Planned but all checklist items are checked"
            )

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.startswith("## "):
            flush()
            current_heading = line.removeprefix("## ").strip()
            current_status = ""
            checked = 0
            unchecked = 0
            status_line = 0
        elif line.startswith("Status: "):
            current_status = line.removeprefix("Status: ").strip()
            status_line = line_number
        elif line.startswith("- [x] "):
            checked += 1
        elif line.startswith("- [ ] "):
            unchecked += 1
    flush()
    return errors


def _validate_board(board: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    tasks = board.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return ["task board must contain a non-empty tasks array"]

    task_ids: set[str] = set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"tasks[{index}] must be an object")
            continue
        task_id = task.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            errors.append(f"tasks[{index}].task_id is required")
            continue
        if task_id in task_ids:
            errors.append(f"duplicate task_id: {task_id}")
        task_ids.add(task_id)

        status = task.get("status")
        if status not in VALID_STATUSES:
            errors.append(f"{task_id}: invalid status {status!r}")
        priority = task.get("priority")
        if priority not in VALID_PRIORITIES:
            errors.append(f"{task_id}: invalid priority {priority!r}")

        for required in (
            "title",
            "source_doc",
            "target_files",
            "acceptance_criteria",
            "validation_commands",
        ):
            if required not in task:
                errors.append(f"{task_id}: missing required field {required}")

        source_doc = task.get("source_doc")
        if isinstance(source_doc, str) and not (REPO_ROOT / source_doc).exists():
            errors.append(f"{task_id}: source_doc does not exist: {source_doc}")

        for field_name in ("target_files", "acceptance_criteria", "validation_commands"):
            value = task.get(field_name)
            if not isinstance(value, list) or not value:
                errors.append(f"{task_id}: {field_name} must be a non-empty list")

        for target in task.get("target_files", []):
            if not isinstance(target, str):
                errors.append(f"{task_id}: target_files entries must be strings")
                continue
            if target.startswith("/"):
                errors.append(f"{task_id}: target file must be repo-relative: {target}")
            elif not (REPO_ROOT / target).exists():
                errors.append(f"{task_id}: target file does not exist: {target}")

    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = task.get("task_id", "<unknown>")
        for dependency in task.get("depends_on", []):
            if dependency not in task_ids:
                errors.append(f"{task_id}: unknown dependency {dependency}")
    return errors


def main() -> int:
    errors: list[str] = []
    board = _load_json(BOARD_PATH)
    errors.extend(_validate_board(board))
    errors.extend(_validate_json_fences(PAYLOAD_CONTRACTS))
    errors.extend(_validate_no_stale_absolute_links(DOCS_TO_LINT))
    for path in DOCS_TO_LINT:
        errors.extend(_section_status_conflicts(path))

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(
        f"Validated {BOARD_PATH.relative_to(REPO_ROOT)} with "
        f"{len(board.get('tasks', []))} tasks and {len(DOCS_TO_LINT)} source docs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
