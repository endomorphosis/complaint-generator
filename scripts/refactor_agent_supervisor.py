#!/usr/bin/env python3
"""Complaint-generator refactor supervisor wrapper.

This script keeps the repo-specific scan and initial refactor objectives here,
but delegates objective scanning, backlog refill, bundle queue submission, and
implementation supervision to ``ipfs_accelerate_py.agent_supervisor``.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACCELERATE_REPO = PROJECT_ROOT / "ipfs_datasets_py" / "ipfs_accelerate_py"
STATE_ROOT = PROJECT_ROOT / "data" / "refactor_supervisor"
QUEUE_PATH = STATE_ROOT / "refactor_taskboard.duckdb"
GOALS_PATH = STATE_ROOT / "refactor_goals.json"
OBJECTIVE_PATH = STATE_ROOT / "refactor_objective_heap.md"
TODO_PATH = STATE_ROOT / "refactor_todo.md"
BUNDLE_DIR = STATE_ROOT / "objective_bundles"
DATASET_DIR = STATE_ROOT / "objective_datasets"
DISCOVERY_DIR = STATE_ROOT / "discovery"
GRAPH_PATH = STATE_ROOT / "objective_graph.json"
STRATEGY_PATH = STATE_ROOT / "strategy.json"
EVENTS_PATH = STATE_ROOT / "events.jsonl"
REFILL_STATE_PATH = STATE_ROOT / "refill_state.json"
SUPERVISOR_STATE_DIR = STATE_ROOT / "supervisor_state"
WORKTREE_ROOT = STATE_ROOT / "worktrees"
STATUS_PATH = STATE_ROOT / "refactor_supervisor_status.json"
PID_PATH = STATE_ROOT / "refactor_supervisor.pid"
LOG_PATH = STATE_ROOT / "refactor_supervisor.log"
TASKBOARD_DOC_PATH = PROJECT_ROOT / "docs" / "REFACTOR_SUPERVISOR_TASKBOARD.md"

TASK_PREFIX = "REF-"
TASK_HEADER_PREFIX = "## REF-"
TASK_TYPES = ("codex.todo_bundle",)
MODEL_NAME = "complaint-generator-refactor-supervisor"


def _ensure_accelerate_import_path() -> None:
    path = str(ACCELERATE_REPO)
    if path not in sys.path:
        sys.path.insert(0, path)


def _task_queue_class():
    _ensure_accelerate_import_path()
    from ipfs_accelerate_py.p2p_tasks import TaskQueue

    return TaskQueue


def _upstream_objective_runner():
    _ensure_accelerate_import_path()
    from ipfs_accelerate_py.agent_supervisor.objective_daemon import (
        build_arg_parser,
        run_objective_daemon,
    )

    return build_arg_parser, run_objective_daemon


def _upstream_backlog_runner():
    _ensure_accelerate_import_path()
    from ipfs_accelerate_py.agent_supervisor.backlog_refinery import (
        build_arg_parser,
        run_backlog_refinery,
    )

    return build_arg_parser, run_backlog_refinery


def _upstream_task_board_helpers():
    _ensure_accelerate_import_path()
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.engine import parse_markdown_tasks
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.task_board import task_status_counts

    return parse_markdown_tasks, task_status_counts


@dataclass(frozen=True)
class RefactorTask:
    goal_id: str
    subgoal_id: str
    title: str
    priority: str
    files: tuple[str, ...]
    rationale: str
    acceptance: tuple[str, ...]
    validation: tuple[str, ...]

    @property
    def stable_key(self) -> str:
        return f"{self.goal_id}:{self.subgoal_id}:{self.title}".lower()

    def payload(self) -> dict[str, Any]:
        return {
            "supervisor": "refactor_agent_supervisor",
            "objective": "Refactor complaint-generator safely and incrementally.",
            "goal_id": self.goal_id,
            "subgoal_id": self.subgoal_id,
            "title": self.title,
            "priority": self.priority,
            "files": list(self.files),
            "rationale": self.rationale,
            "acceptance": list(self.acceptance),
            "validation": list(self.validation),
            "stable_key": self.stable_key,
            "created_by": "ipfs_accelerate_py.p2p_tasks.TaskQueue",
        }


def _iter_py_files() -> list[Path]:
    roots = [
        "applications",
        "backends",
        "complaint_analysis",
        "complaint_generator",
        "complaint_phases",
        "integrations",
        "lib",
        "mediator",
        "scripts",
        "tests",
    ]
    files: list[Path] = []
    for root_name in roots:
        root = PROJECT_ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in {".venv", "__pycache__"} for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def scan_codebase() -> dict[str, Any]:
    py_files = _iter_py_files()
    line_counts: list[tuple[int, str]] = []
    direct_ipfs_imports: list[str] = []
    sys_path_mutations: list[str] = []
    broad_exceptions: list[str] = []
    wildcard_imports: list[str] = []
    silent_passes: list[str] = []

    for path in py_files:
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        if rel == "scripts/refactor_agent_supervisor.py":
            continue
        text = _read_text(path)
        lines = text.splitlines()
        line_counts.append((len(lines), rel))
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if "from ipfs_datasets_py" in stripped or "import ipfs_datasets_py" in stripped:
                direct_ipfs_imports.append(f"{rel}:{idx}")
            if "sys.path.insert" in stripped or "sys.path.append" in stripped:
                sys_path_mutations.append(f"{rel}:{idx}")
            if stripped.startswith("except Exception"):
                broad_exceptions.append(f"{rel}:{idx}")
            if stripped.endswith("import *"):
                wildcard_imports.append(f"{rel}:{idx}")
            if stripped == "pass":
                silent_passes.append(f"{rel}:{idx}")

    return {
        "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python_file_count": len(py_files),
        "python_total_lines": sum(n for n, _ in line_counts),
        "largest_python_files": [
            {"path": rel, "lines": count} for count, rel in sorted(line_counts, reverse=True)[:25]
        ],
        "signals": {
            "direct_ipfs_imports": direct_ipfs_imports[:200],
            "direct_ipfs_import_count": len(direct_ipfs_imports),
            "sys_path_mutations": sys_path_mutations[:200],
            "sys_path_mutation_count": len(sys_path_mutations),
            "broad_exception_count": len(broad_exceptions),
            "wildcard_imports": wildcard_imports[:100],
            "wildcard_import_count": len(wildcard_imports),
            "silent_pass_count": len(silent_passes),
        },
        "test_file_count": len([p for p in py_files if p.relative_to(PROJECT_ROOT).parts[0] == "tests"]),
        "packaging": {
            "pyproject": (PROJECT_ROOT / "pyproject.toml").exists(),
            "pytest_ini": (PROJECT_ROOT / "pytest.ini").exists(),
            "package_json": (PROJECT_ROOT / "package.json").exists(),
        },
    }


def build_goals(scan: dict[str, Any]) -> list[dict[str, Any]]:
    largest = [item["path"] for item in scan.get("largest_python_files", [])[:8]]
    direct_imports = scan.get("signals", {}).get("direct_ipfs_imports", [])
    sys_path = scan.get("signals", {}).get("sys_path_mutations", [])

    return [
        {
            "id": "G1",
            "title": "Stabilize repository boundaries",
            "priority": "P0",
            "subgoals": [
                {
                    "id": "G1.S1",
                    "title": "Map package ownership and runtime entrypoints",
                    "tasks": [
                        _task(
                            "G1",
                            "G1.S1",
                            "Create an entrypoint and ownership map for the largest runtime modules",
                            "P0",
                            tuple(largest[:6]),
                            "Large modules dominate change risk and need explicit boundaries before extraction.",
                            ("A short module ownership map exists.", "Entrypoints are grouped by CLI, web, mediator, and workflow role."),
                            ("python -m pytest tests/test_package_imports.py -q",),
                        ),
                        _task(
                            "G1",
                            "G1.S1",
                            "Document allowed dependency direction between applications, mediator, phases, integrations, and lib",
                            "P0",
                            ("docs/ARCHITECTURE.md", "pyproject.toml"),
                            "Refactors need a clear import direction to avoid moving complexity around.",
                            ("Architecture docs identify allowed imports.", "New work has a simple rule for where shared code belongs."),
                            ("python -m pytest tests/test_package_imports.py -q",),
                        ),
                    ],
                },
                {
                    "id": "G1.S2",
                    "title": "Remove ad hoc import path behavior from production surfaces",
                    "tasks": [
                        _task(
                            "G1",
                            "G1.S2",
                            "Replace production sys.path mutation with package-level imports or adapter loader calls",
                            "P0",
                            tuple(_paths_from_locations(sys_path[:12])),
                            "The scan found production-style sys.path mutation that makes runtime behavior environment-sensitive.",
                            ("No production entrypoint mutates sys.path for normal imports.", "Explicit exceptions are isolated to scripts/tests."),
                            ("python -m pytest tests/test_package_imports.py -q",),
                        ),
                        _task(
                            "G1",
                            "G1.S2",
                            "Route direct ipfs_datasets_py imports through integrations/ipfs_datasets adapters where production-facing",
                            "P0",
                            tuple(_paths_from_locations(direct_imports[:16])),
                            "Optional dependency behavior should stay behind the adapter boundary.",
                            ("Production direct imports are replaced or documented.", "Degraded mode still imports cleanly."),
                            ("python -m pytest tests/test_ipfs_adapter_layer.py -q",),
                        ),
                    ],
                },
            ],
        },
        {
            "id": "G2",
            "title": "Decompose oversized orchestration modules",
            "priority": "P0",
            "subgoals": [
                {
                    "id": "G2.S1",
                    "title": "Extract mediator service seams",
                    "tasks": [
                        _task(
                            "G2",
                            "G2.S1",
                            "Split mediator/mediator.py by workflow service while preserving public API compatibility",
                            "P0",
                            ("mediator/mediator.py", "mediator/__init__.py"),
                            "The mediator is the largest runtime file and carries high regression risk.",
                            ("One cohesive service is extracted.", "Existing imports continue to resolve."),
                            ("python -m pytest tests/test_mediator.py tests/test_mediator_three_phase.py -q",),
                        ),
                        _task(
                            "G2",
                            "G2.S1",
                            "Move claim support orchestration helpers into focused private modules",
                            "P0",
                            ("mediator/claim_support_hooks.py",),
                            "Claim support hooks are large enough to hide unrelated concerns.",
                            ("At least one cohesive helper group moves behind a stable import.", "No payload contract changes without tests."),
                            ("python -m pytest tests/test_claim_support_hooks.py tests/test_claim_support_review_dashboard_flow.py -q",),
                        ),
                    ],
                },
                {
                    "id": "G2.S2",
                    "title": "Reduce application surface coupling",
                    "tasks": [
                        _task(
                            "G2",
                            "G2.S2",
                            "Extract complaint workspace request handlers from UI state helpers",
                            "P1",
                            ("applications/complaint_workspace.py",),
                            "The workspace module mixes UI routing, state shaping, and workflow calls.",
                            ("One handler group is isolated.", "Routes keep the same response shape."),
                            ("python -m pytest tests/test_review_api.py -q",),
                        ),
                        _task(
                            "G2",
                            "G2.S2",
                            "Separate dashboard fixture data from live route logic",
                            "P1",
                            ("applications/dashboard_ui.py", "playwright/server.js"),
                            "Dashboard behavior is harder to test when fixtures and live assembly are interleaved.",
                            ("Fixture builders are named and reusable.", "Playwright smoke tests remain stable."),
                            ("python -m pytest tests/test_claim_support_review_playwright_smoke.py -q",),
                        ),
                    ],
                },
            ],
        },
        {
            "id": "G3",
            "title": "Harden adapter contracts and degraded mode",
            "priority": "P0",
            "subgoals": [
                {
                    "id": "G3.S1",
                    "title": "Normalize IPFS datasets adapter payloads",
                    "tasks": [
                        _task(
                            "G3",
                            "G3.S1",
                            "Standardize capability status and degraded-reason payloads across adapters",
                            "P0",
                            ("integrations/ipfs_datasets/capabilities.py", "integrations/ipfs_datasets/loader.py"),
                            "The existing backlog identifies adapter capability reporting as incomplete.",
                            ("All adapter groups report stable keys.", "Missing optional extras produce actionable reasons."),
                            ("python -m pytest tests/test_ipfs_adapter_layer.py -q",),
                        ),
                        _task(
                            "G3",
                            "G3.S1",
                            "Promote document parsing into a shared ingestion contract",
                            "P0",
                            ("integrations/ipfs_datasets/documents.py", "mediator/evidence_hooks.py"),
                            "Document parsing is still fallback-oriented and should be reusable across ingestion paths.",
                            ("Evidence, authority, and web ingestion can call one parse contract.", "Fallback mode preserves current behavior."),
                            ("python -m pytest tests/test_document_pipeline.py tests/test_document_pipeline_fallbacks.py -q",),
                        ),
                    ],
                },
                {
                    "id": "G3.S2",
                    "title": "Clarify graph, GraphRAG, and logic adapter boundaries",
                    "tasks": [
                        _task(
                            "G3",
                            "G3.S2",
                            "Define graph persistence and query interfaces before moving support scoring",
                            "P1",
                            ("integrations/ipfs_datasets/graphs.py", "complaint_phases/knowledge_graph.py"),
                            "Graph support currently lacks a durable query plane.",
                            ("Interfaces specify persistence, query, and provenance fields.", "Fallback graph behavior remains covered."),
                            ("python -m pytest tests/test_complaint_phases.py tests/test_ipfs_adapter_layer.py -q",),
                        ),
                        _task(
                            "G3",
                            "G3.S2",
                            "Turn not_implemented logic paths into explicit capability-gated contracts",
                            "P1",
                            ("integrations/ipfs_datasets/logic.py", "lib/formal_logic"),
                            "Formal validation should fail predictably when unavailable.",
                            ("Logic status distinguishes unavailable, degraded, and implemented.", "Callers do not branch on fragile strings."),
                            ("python -m pytest tests/test_symbolicai_logic_dependency.py tests/test_ipld_logic_storage_dependency.py -q",),
                        ),
                    ],
                },
            ],
        },
        {
            "id": "G4",
            "title": "Improve validation speed and confidence",
            "priority": "P1",
            "subgoals": [
                {
                    "id": "G4.S1",
                    "title": "Create focused test lanes for refactor work",
                    "tasks": [
                        _task(
                            "G4",
                            "G4.S1",
                            "Define smoke, adapter, mediator, document, and UI test lanes",
                            "P1",
                            ("pytest.ini", "Makefile", "docs/VERIFICATION_SUMMARY.md"),
                            "The repo has many tests; refactor agents need fast confidence lanes.",
                            ("A documented test lane map exists.", "Each P0 workstream has a named validation command."),
                            ("python -m pytest --collect-only -q",),
                        ),
                        _task(
                            "G4",
                            "G4.S1",
                            "Add import and dependency-boundary tests for production modules",
                            "P1",
                            ("tests", "pyproject.toml"),
                            "Dependency drift is a recurring refactor risk.",
                            ("Tests catch direct production imports where adapters are required.", "Tests avoid blocking intentional test-only imports."),
                            ("python -m pytest tests/test_package_imports.py -q",),
                        ),
                    ],
                }
            ],
        },
        {
            "id": "G5",
            "title": "Make automation observable and refillable",
            "priority": "P0",
            "subgoals": [
                {
                    "id": "G5.S1",
                    "title": "Operate a durable refactor taskboard",
                    "tasks": [
                        _task(
                            "G5",
                            "G5.S1",
                            "Keep the refactor taskboard synchronized with generated goals and subgoals",
                            "P0",
                            ("scripts/refactor_agent_supervisor.py", "docs/REFACTOR_SUPERVISOR_TASKBOARD.md"),
                            "The requested supervisor needs a refill loop and visible board state.",
                            ("Queued task count is maintained above the configured floor.", "Docs and JSON state are regenerated each cycle."),
                            ("python scripts/refactor_agent_supervisor.py seed --once",),
                        ),
                        _task(
                            "G5",
                            "G5.S1",
                            "Record supervisor status, scan metrics, and queue counts for handoff",
                            "P0",
                            ("data/refactor_supervisor",),
                            "Long-running automation needs inspectable state and a clean stop path.",
                            ("Status JSON includes pid, heartbeat, scan summary, and counts.", "Stop command terminates the daemon cleanly."),
                            ("python scripts/refactor_agent_supervisor.py status",),
                        ),
                    ],
                }
            ],
        },
        {
            "id": "G6",
            "title": "Pay down error-handling and observability debt",
            "priority": "P1",
            "subgoals": [
                {
                    "id": "G6.S1",
                    "title": "Replace silent failures with typed outcomes",
                    "tasks": [
                        _task(
                            "G6",
                            "G6.S1",
                            "Audit broad exception handlers in mediator and adapter paths",
                            "P1",
                            ("mediator/mediator.py", "mediator/evidence_hooks.py", "integrations/ipfs_datasets/search.py"),
                            "The scan found many broad exception handlers; refactors need predictable failure semantics.",
                            ("Top production broad-exception clusters are documented.", "At least one cluster returns a typed degraded result."),
                            ("python -m pytest tests/test_mediator.py tests/test_ipfs_adapter_layer.py -q",),
                        ),
                        _task(
                            "G6",
                            "G6.S1",
                            "Convert silent pass blocks in user-facing workflows into debug logs or explicit fallbacks",
                            "P1",
                            ("applications/ui_review.py", "complaint_generator/ui_optimizer_daemon.py", "mediator/state.py"),
                            "Silent failures hide regressions during long-running automation.",
                            ("Intentional ignores are named.", "Unexpected failures leave diagnostic breadcrumbs."),
                            ("python -m pytest tests/test_ui_optimizer_daemon_cli.py tests/test_review_api.py -q",),
                        ),
                    ],
                },
                {
                    "id": "G6.S2",
                    "title": "Unify runtime status payloads",
                    "tasks": [
                        _task(
                            "G6",
                            "G6.S2",
                            "Standardize daemon status payload shape across UI, scraper, Gmail, and refactor supervisors",
                            "P1",
                            ("complaint_generator/ui_optimizer_daemon.py", "integrations/ipfs_datasets/scraper_daemon.py", "scripts/gmail_duckdb_daemon.py"),
                            "Multiple daemon surfaces should be inspectable with the same status fields.",
                            ("Status payloads include status, pid, updated_at, artifacts, and last_error where applicable.", "Existing CLI tests remain compatible."),
                            ("python -m pytest tests/test_ui_optimizer_daemon_cli.py tests/test_gmail_duckdb_daemon_cli.py -q",),
                        ),
                        _task(
                            "G6",
                            "G6.S2",
                            "Add queue count and last-cycle metrics to long-running automation docs",
                            "P2",
                            ("docs/OBSERVABILITY_INDEX.md", "docs/observability/TROUBLESHOOTING.md"),
                            "Operators need consistent guidance for stalled background workflows.",
                            ("Docs explain where to find pid, log, status, and queue files.", "Troubleshooting includes stale running task recovery."),
                            ("python scripts/refactor_agent_supervisor.py status",),
                        ),
                    ],
                },
            ],
        },
        {
            "id": "G7",
            "title": "Rationalize frontend and review surfaces",
            "priority": "P1",
            "subgoals": [
                {
                    "id": "G7.S1",
                    "title": "Separate review API contracts from display assembly",
                    "tasks": [
                        _task(
                            "G7",
                            "G7.S1",
                            "Move review payload normalization behind explicit DTO helpers",
                            "P1",
                            ("applications/review_api.py", "applications/ui_review.py", "mediator/claim_support_hooks.py"),
                            "Review screens depend on stable payloads that should not be assembled ad hoc in route handlers.",
                            ("DTO helpers cover coverage, follow-up, and support-path summaries.", "Route response snapshots stay stable."),
                            ("python -m pytest tests/test_review_api.py tests/test_claim_support_review_dashboard_flow.py -q",),
                        ),
                        _task(
                            "G7",
                            "G7.S1",
                            "Create fixture builders for Playwright review and dashboard smoke tests",
                            "P1",
                            ("tests/test_claim_support_review_playwright_smoke.py", "tests/test_review_surface_site_playwright.py"),
                            "Large Playwright tests should share fixture setup before UI refactors.",
                            ("Shared builders remove repeated setup.", "Screenshots still render with representative support states."),
                            ("python -m pytest tests/test_claim_support_review_playwright_smoke.py tests/test_review_surface_site_playwright.py -q",),
                        ),
                    ],
                },
            ],
        },
        {
            "id": "G8",
            "title": "Prepare incremental implementation slices",
            "priority": "P0",
            "subgoals": [
                {
                    "id": "G8.S1",
                    "title": "Convert existing roadmaps into executable slices",
                    "tasks": [
                        _task(
                            "G8",
                            "G8.S1",
                            "Cross-link IPFS datasets execution backlog tasks to refactor supervisor goals",
                            "P0",
                            ("docs/IPFS_DATASETS_PY_EXECUTION_BACKLOG.md", "docs/REFACTOR_SUPERVISOR_TASKBOARD.md"),
                            "Existing roadmap work should feed the automated taskboard rather than drift separately.",
                            ("Each P0 backlog workstream maps to at least one refactor goal.", "Duplicated tasks are merged or explicitly scoped."),
                            ("python scripts/refactor_agent_supervisor.py seed --once",),
                        ),
                        _task(
                            "G8",
                            "G8.S1",
                            "Define first three implementation claims from the queued taskboard",
                            "P0",
                            ("data/refactor_supervisor/refactor_goals.json",),
                            "A robust board still needs a practical starting order.",
                            ("The first three claims are small, testable, and dependency-ordered.", "Each claim names exact validation commands."),
                            ("python scripts/refactor_agent_supervisor.py status",),
                        ),
                    ],
                },
                {
                    "id": "G8.S2",
                    "title": "Keep generated artifacts reviewable",
                    "tasks": [
                        _task(
                            "G8",
                            "G8.S2",
                            "Add a taskboard inspection command that prints queued refactor tasks compactly",
                            "P1",
                            ("scripts/refactor_agent_supervisor.py",),
                            "Agents need a simple way to see the next work without opening DuckDB manually.",
                            ("Status output or a new command lists next tasks by priority.", "Output is stable enough for automation."),
                            ("python scripts/refactor_agent_supervisor.py status",),
                        ),
                        _task(
                            "G8",
                            "G8.S2",
                            "Create tests for refactor supervisor seed idempotence and task payload schema",
                            "P1",
                            ("tests/test_refactor_agent_supervisor.py", "scripts/refactor_agent_supervisor.py"),
                            "The supervisor itself should not duplicate tasks or emit malformed payloads.",
                            ("Running seed twice does not duplicate active tasks.", "Payloads include goal, subgoal, priority, acceptance, and validation."),
                            ("python -m pytest tests/test_refactor_agent_supervisor.py -q",),
                        ),
                    ],
                },
            ],
        },
    ]


def _task(
    goal_id: str,
    subgoal_id: str,
    title: str,
    priority: str,
    files: tuple[str, ...],
    rationale: str,
    acceptance: tuple[str, ...],
    validation: tuple[str, ...],
) -> RefactorTask:
    clean_files = tuple(dict.fromkeys(f for f in files if f))
    return RefactorTask(goal_id, subgoal_id, title, priority, clean_files, rationale, acceptance, validation)


def _paths_from_locations(locations: list[str]) -> list[str]:
    paths: list[str] = []
    for item in locations:
        path = str(item).split(":", 1)[0].strip()
        if path and path not in paths:
            paths.append(path)
    return paths


def flatten_tasks(goals: list[dict[str, Any]]) -> list[RefactorTask]:
    tasks: list[RefactorTask] = []
    for goal in goals:
        for subgoal in goal.get("subgoals", []):
            for task in subgoal.get("tasks", []):
                if isinstance(task, RefactorTask):
                    tasks.append(task)
    return tasks


def _json_goal_tree(goals: list[dict[str, Any]], scan: dict[str, Any]) -> dict[str, Any]:
    out_goals: list[dict[str, Any]] = []
    for goal in goals:
        goal_out = {k: v for k, v in goal.items() if k != "subgoals"}
        goal_out["subgoals"] = []
        for subgoal in goal.get("subgoals", []):
            subgoal_out = {k: v for k, v in subgoal.items() if k != "tasks"}
            subgoal_out["tasks"] = [task.payload() for task in subgoal.get("tasks", [])]
            goal_out["subgoals"].append(subgoal_out)
        out_goals.append(goal_out)
    return {
        "objective": "Refactor complaint-generator safely and incrementally.",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_supervisor_module": "ipfs_accelerate_py.agent_supervisor",
        "objective_path": str(OBJECTIVE_PATH.relative_to(PROJECT_ROOT)),
        "todo_path": str(TODO_PATH.relative_to(PROJECT_ROOT)),
        "bundle_dir": str(BUNDLE_DIR.relative_to(PROJECT_ROOT)),
        "queue_path": str(QUEUE_PATH.relative_to(PROJECT_ROOT)),
        "scan": scan,
        "goals": out_goals,
    }


def _goal_evidence(task: RefactorTask) -> str:
    evidence = [*task.files, *task.acceptance, *task.validation]
    return ", ".join(dict.fromkeys(item for item in evidence if item)) or task.title


def _render_objective_heap(goals: list[dict[str, Any]]) -> str:
    lines = [
        "# Complaint Generator Refactor Objective Heap",
        "",
        "Ultimate objective: Refactor complaint-generator safely and incrementally while preserving behavior.",
        "",
    ]
    for goal in goals:
        tasks = flatten_tasks([goal])
        lines.extend(
            [
                f"## {goal['id']} {goal['title']}",
                "",
                "- Status: active",
                f"- Priority: {goal['priority']}",
                f"- Bundle: refactor/{goal['id'].lower()}",
                "- Goal: " + goal["title"],
                "- Evidence: docs/ARCHITECTURE.md, docs/REFACTOR_SUPERVISOR_TASKBOARD.md, "
                + ", ".join(dict.fromkeys(path for task in tasks for path in task.files[:3])),
                "- Validation: python -m pytest --collect-only -q",
                "",
            ]
        )
        for subgoal in goal.get("subgoals", []):
            subgoal_tasks = [task for task in subgoal.get("tasks", []) if isinstance(task, RefactorTask)]
            lines.extend(
                [
                    f"## {subgoal['id']} {subgoal['title']}",
                    "",
                    "- Status: active",
                    f"- Parent: {goal['id']}",
                    f"- Priority: {goal['priority']}",
                    f"- Bundle: refactor/{goal['id'].lower()}/{subgoal['id'].replace('.', '-').lower()}",
                    "- Goal: " + subgoal["title"],
                    "- Evidence: " + ", ".join(_goal_evidence(task) for task in subgoal_tasks),
                    "- Validation: " + ", ".join(
                        dict.fromkeys(command for task in subgoal_tasks for command in task.validation)
                    ),
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _render_seed_todo(goals: list[dict[str, Any]]) -> str:
    lines = [
        "# Complaint Generator Refactor Todo Board",
        "",
        "Generated by `scripts/refactor_agent_supervisor.py` from a codebase scan.",
        "This board is consumed by `ipfs_accelerate_py.agent_supervisor`.",
        "",
    ]
    index = 1
    for task in flatten_tasks(goals):
        outputs = ", ".join(task.files) or str(TASKBOARD_DOC_PATH.relative_to(PROJECT_ROOT))
        validation = ", ".join(task.validation) or "python -m pytest --collect-only -q"
        lines.extend(
            [
                f"- [ ] Task checkbox-{index}: {TASK_PREFIX}{index:03d} {task.title}",
                "",
                f"## {TASK_PREFIX}{index:03d} {task.title}",
                "",
                "- Status: todo",
                "- Completion: manual",
                f"- Priority: {task.priority}",
                f"- Track: {task.goal_id}",
                "- Depends on: ",
                f"- Outputs: {outputs}",
                f"- Validation: {validation}",
                f"- Bundle: refactor/{task.goal_id.lower()}/{task.subgoal_id.replace('.', '-').lower()}",
                "- Bundle strategy: keep related refactor edits in the same lane and validate before merge",
                f"- Goal id: {task.subgoal_id}",
                f"- Missing evidence: {task.rationale}",
                "- Acceptance: " + "; ".join(task.acceptance),
                "",
            ]
        )
        index += 1
    return "\n".join(lines).rstrip() + "\n"


def _ensure_text(path: Path, text: str, *, overwrite: bool = True) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return False
    existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else None
    if existing == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def _todo_counts() -> dict[str, int]:
    if not TODO_PATH.exists():
        return {"needed": 0, "in_progress": 0, "complete": 0, "blocked": 0}
    parse_markdown_tasks, task_status_counts = _upstream_task_board_helpers()
    return task_status_counts(parse_markdown_tasks(TODO_PATH.read_text(encoding="utf-8", errors="replace")))


def seed_taskboard(
    *,
    refill_floor: int = 20,
    submit_bundles: bool = True,
    force: bool = False,
    full_scan: bool = False,
) -> dict[str, Any]:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    scan = scan_codebase()
    goals = build_goals(scan)

    goal_tree = _json_goal_tree(goals, scan)
    GOALS_PATH.write_text(json.dumps(goal_tree, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    objective_changed = _ensure_text(OBJECTIVE_PATH, _render_objective_heap(goals), overwrite=True)
    existing_todo_total = sum(_todo_counts().values()) if TODO_PATH.exists() else 0
    todo_changed = _ensure_text(TODO_PATH, _render_seed_todo(goals), overwrite=existing_todo_total == 0)

    objective_result: dict[str, Any] = {"skipped": True, "reason": "fast_seed"}
    backlog_result: dict[str, Any] = {"skipped": True, "reason": "fast_seed"}
    if full_scan:
        objective_parser, run_objective_daemon = _upstream_objective_runner()
        objective_args = objective_parser().parse_args(
            [
                "--repo-root",
                str(PROJECT_ROOT),
                "--objective-path",
                str(OBJECTIVE_PATH),
                "--todo-path",
                str(TODO_PATH),
                "--discovery-dir",
                str(DISCOVERY_DIR),
                "--bundle-dir",
                str(BUNDLE_DIR),
                "--dataset-dir",
                str(DATASET_DIR),
                "--graph-path",
                str(GRAPH_PATH),
                "--task-prefix",
                TASK_PREFIX,
                "--objective-summary-prefix",
                "Refactor objective gap",
                "--max-findings",
                str(max(8, int(refill_floor))),
                "--surplus-findings-per-goal",
                "2",
                "--refine-objective-heap",
                "--no-reconcile-goal-completion",
                "--no-persist-ast-dataset",
                "--max-refinement-children",
                "2",
                "--max-refinement-depth",
                "3",
                "--submit-bundles" if submit_bundles else "--no-todo-vector-index",
                "--queue-path",
                str(QUEUE_PATH),
                "--queue-task-type",
                "codex.todo_bundle",
                "--queue-model-name",
                MODEL_NAME,
            ]
        )
        objective_result = run_objective_daemon(objective_args)

        backlog_parser, run_backlog_refinery = _upstream_backlog_runner()
        backlog_argv = [
            "--repo-root",
            str(PROJECT_ROOT),
            "--todo-path",
            str(TODO_PATH),
            "--state-path",
            str(REFILL_STATE_PATH),
            "--strategy-path",
            str(STRATEGY_PATH),
            "--events-path",
            str(EVENTS_PATH),
            "--discovery-dir",
            str(DISCOVERY_DIR),
            "--objective-path",
            str(OBJECTIVE_PATH),
            "--bundle-dir",
            str(BUNDLE_DIR),
            "--dataset-dir",
            str(DATASET_DIR),
            "--task-prefix",
            TASK_PREFIX,
            "--task-header-prefix",
            TASK_HEADER_PREFIX,
            "--min-open-tasks",
            str(int(refill_floor)),
            "--max-findings",
            "8",
            "--objective-surplus-findings-per-goal",
            "2",
        ]
        if force:
            backlog_argv.append("--force")
        backlog_args = backlog_parser().parse_args(backlog_argv)
        backlog_result = run_backlog_refinery(backlog_args)

    queue_counts: dict[str, int] = {}
    if QUEUE_PATH.exists():
        TaskQueue = _task_queue_class()
        queue = TaskQueue(str(QUEUE_PATH))
        queue_counts = {
            "queued": queue.count(status="queued", task_types=TASK_TYPES),
            "running": queue.count(status="running", task_types=TASK_TYPES),
            "completed": queue.count(status="completed", task_types=TASK_TYPES),
            "failed": queue.count(status="failed", task_types=TASK_TYPES),
        }

    counts = {"todo": _todo_counts(), "queue": queue_counts}
    _write_taskboard_doc(goals, scan, counts, objective_result, backlog_result)
    _write_status(
        {
            "status": "seeded",
            "pid": 0,
            "pid_alive": False,
            "objective_path": str(OBJECTIVE_PATH),
            "todo_path": str(TODO_PATH),
            "bundle_dir": str(BUNDLE_DIR),
            "graph_path": str(GRAPH_PATH),
            "queue_path": str(QUEUE_PATH),
            "last_seed": {
                "counts": counts,
                "scan_summary": {
                    "python_file_count": scan["python_file_count"],
                    "python_total_lines": scan["python_total_lines"],
                    "test_file_count": scan["test_file_count"],
                    "direct_ipfs_import_count": scan["signals"]["direct_ipfs_import_count"],
                    "sys_path_mutation_count": scan["signals"]["sys_path_mutation_count"],
                    "broad_exception_count": scan["signals"]["broad_exception_count"],
                },
                "objective_result": objective_result,
                "backlog_result": backlog_result,
            },
        }
    )
    return {
        "objective_changed": objective_changed,
        "todo_changed": todo_changed,
        "counts": counts,
        "objective_result": objective_result,
        "backlog_result": backlog_result,
        "scan": scan,
    }


def _write_taskboard_doc(
    goals: list[dict[str, Any]],
    scan: dict[str, Any],
    counts: dict[str, Any],
    objective_result: dict[str, Any],
    backlog_result: dict[str, Any],
) -> None:
    todo_counts = counts.get("todo") or {}
    queue_counts = counts.get("queue") or {}
    lines = [
        "# Refactor Supervisor Taskboard",
        "",
        f"Generated: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        "",
        "This taskboard is generated by `scripts/refactor_agent_supervisor.py` and backed by",
        "`ipfs_accelerate_py.agent_supervisor` objective/refill/implementation supervisor modules.",
        "",
        "## Artifacts",
        "",
        f"- Objective heap: `{OBJECTIVE_PATH.relative_to(PROJECT_ROOT)}`",
        f"- Markdown todo board: `{TODO_PATH.relative_to(PROJECT_ROOT)}`",
        f"- Bundle dir: `{BUNDLE_DIR.relative_to(PROJECT_ROOT)}`",
        f"- Objective graph: `{GRAPH_PATH.relative_to(PROJECT_ROOT)}`",
        f"- Queue path: `{QUEUE_PATH.relative_to(PROJECT_ROOT)}`",
        "",
        "## Counts",
        "",
        f"- Todo needed: {todo_counts.get('needed', 0)}",
        f"- Todo in progress: {todo_counts.get('in_progress', 0)}",
        f"- Todo complete: {todo_counts.get('complete', 0)}",
        f"- Todo blocked: {todo_counts.get('blocked', 0)}",
        f"- Bundle queue queued: {queue_counts.get('queued', 0)}",
        f"- Bundle queue running: {queue_counts.get('running', 0)}",
        f"- Bundle queue completed: {queue_counts.get('completed', 0)}",
        f"- Objective tasks generated this cycle: {objective_result.get('generated_count', 0)}",
        f"- Backlog codebase tasks generated this cycle: {backlog_result.get('codebase_generated_count', 0)}",
        "",
        "## Scan Summary",
        "",
        f"- Python files scanned: {scan['python_file_count']}",
        f"- Python lines scanned: {scan['python_total_lines']}",
        f"- Test files scanned: {scan['test_file_count']}",
        f"- Direct `ipfs_datasets_py` import hits: {scan['signals']['direct_ipfs_import_count']}",
        f"- `sys.path` mutation hits: {scan['signals']['sys_path_mutation_count']}",
        f"- Broad `except Exception` hits: {scan['signals']['broad_exception_count']}",
        "",
        "## Goals",
        "",
    ]
    for goal in goals:
        lines.append(f"### {goal['id']}: {goal['title']} ({goal['priority']})")
        lines.append("")
        for subgoal in goal.get("subgoals", []):
            lines.append(f"#### {subgoal['id']}: {subgoal['title']}")
            lines.append("")
            for task in subgoal.get("tasks", []):
                lines.append(f"- [{task.priority}] {task.title}")
                if task.files:
                    lines.append(f"  - Files: {', '.join(f'`{f}`' for f in task.files)}")
                lines.append(f"  - Acceptance: {'; '.join(task.acceptance)}")
                lines.append(f"  - Validation: {'; '.join(f'`{v}`' for v in task.validation)}")
            lines.append("")
    TASKBOARD_DOC_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write_status(payload: dict[str, Any]) -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    STATUS_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def run_daemon(*, interval_s: float, refill_floor: int, once: bool = False) -> dict[str, Any]:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    host = socket.gethostname()
    cycle = 0
    last_result: dict[str, Any] = {}

    def _stop(signum: int, frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    try:
        while True:
            cycle += 1
            result = seed_taskboard(refill_floor=refill_floor)
            last_result = result
            _write_status(
                {
                    "status": "running",
                    "pid": os.getpid(),
                    "host": host,
                    "cycle": cycle,
                    "queue_path": str(QUEUE_PATH),
                    "goals_path": str(GOALS_PATH),
                    "taskboard_doc_path": str(TASKBOARD_DOC_PATH),
                    "last_seed": result,
                }
            )
            if once:
                break
            time.sleep(max(5.0, float(interval_s)))
    except KeyboardInterrupt:
        _write_status({"status": "stopped", "pid": os.getpid(), "host": host, "cycle": cycle, "last_seed": last_result})
    finally:
        try:
            if PID_PATH.exists() and PID_PATH.read_text(encoding="utf-8").strip() == str(os.getpid()):
                PID_PATH.unlink()
        except Exception:
            pass
    return last_result


def start_daemon(args: argparse.Namespace) -> dict[str, Any]:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    if PID_PATH.exists():
        try:
            pid = int(PID_PATH.read_text(encoding="utf-8").strip())
        except Exception:
            pid = 0
        if _pid_alive(pid):
            return {"status": "already_running", "pid": pid, "status_path": str(STATUS_PATH)}

    seed_result = seed_taskboard(refill_floor=args.refill_floor, full_scan=False)
    SUPERVISOR_STATE_DIR.mkdir(parents=True, exist_ok=True)
    WORKTREE_ROOT.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_supervisor",
        "--todo-path",
        str(TODO_PATH),
        "--state-dir",
        str(SUPERVISOR_STATE_DIR),
        "--task-prefix",
        TASK_PREFIX,
        "--state-prefix",
        "complaint_generator_refactor",
        "--implement",
        "--implementation-timeout",
        str(float(args.implementation_timeout)),
        "--check-interval",
        str(float(args.interval_s)),
        "--daemon-interval",
        str(float(args.daemon_interval_s)),
        "--max-restarts",
        str(int(args.max_restarts)),
        "--worktree-root",
        str(WORKTREE_ROOT),
        "--worktree-submodule-path",
        "ipfs_datasets_py/ipfs_accelerate_py",
        "--objective-refill-scan",
        "--objective-path",
        str(OBJECTIVE_PATH),
        "--objective-graph-path",
        str(GRAPH_PATH),
        "--objective-bundle-dir",
        str(BUNDLE_DIR),
        "--objective-dataset-dir",
        str(DATASET_DIR),
        "--objective-discovery-dir",
        str(DISCOVERY_DIR),
        "--objective-scan-min-open-tasks",
        str(int(args.refill_floor)),
        "--objective-scan-max-findings",
        "6",
        "--objective-surplus-findings-per-goal",
        "2",
        "--objective-max-refinement-children",
        "2",
        "--objective-max-refinement-depth",
        "3",
        "--codebase-refill-scan",
        "--codebase-scan-min-open-tasks",
        str(int(args.refill_floor)),
        "--codebase-scan-max-findings",
        "6",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ACCELERATE_REPO) + os.pathsep + env.get("PYTHONPATH", "")
    log_handle = LOG_PATH.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    time.sleep(1.0)
    PID_PATH.write_text(str(proc.pid) + "\n", encoding="utf-8")
    payload = {
        "status": "started",
        "pid": proc.pid,
        "status_path": str(STATUS_PATH),
        "log_path": str(LOG_PATH),
        "upstream_supervisor": True,
        "seed": seed_result,
        "command": cmd,
    }
    _write_status(payload)
    return payload


def stop_daemon() -> dict[str, Any]:
    if not PID_PATH.exists():
        return {"status": "not_running"}
    try:
        pid = int(PID_PATH.read_text(encoding="utf-8").strip())
    except Exception:
        pid = 0
    if not _pid_alive(pid):
        try:
            PID_PATH.unlink()
        except Exception:
            pass
        return {"status": "not_running"}
    os.kill(pid, signal.SIGTERM)
    for _ in range(20):
        if not _pid_alive(pid):
            break
        time.sleep(0.2)
    return {"status": "stopped" if not _pid_alive(pid) else "stopping", "pid": pid}


def status_payload() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "unknown",
        "pid_alive": False,
        "objective_path": str(OBJECTIVE_PATH),
        "todo_path": str(TODO_PATH),
        "bundle_dir": str(BUNDLE_DIR),
        "graph_path": str(GRAPH_PATH),
        "queue_path": str(QUEUE_PATH),
        "log_path": str(LOG_PATH),
    }
    if STATUS_PATH.exists():
        try:
            payload.update(json.loads(STATUS_PATH.read_text(encoding="utf-8")))
        except Exception as exc:
            payload["status_read_error"] = str(exc)
    if PID_PATH.exists():
        try:
            pid = int(PID_PATH.read_text(encoding="utf-8").strip())
        except Exception:
            pid = 0
        payload["pid"] = pid
        payload["pid_alive"] = _pid_alive(pid)
    payload["todo_counts"] = _todo_counts()
    if QUEUE_PATH.exists():
        try:
            TaskQueue = _task_queue_class()
            queue = TaskQueue(str(QUEUE_PATH))
            payload["queue_counts"] = {
                "queued": queue.count(status="queued", task_types=TASK_TYPES),
                "running": queue.count(status="running", task_types=TASK_TYPES),
                "completed": queue.count(status="completed", task_types=TASK_TYPES),
                "failed": queue.count(status="failed", task_types=TASK_TYPES),
            }
            payload["next_tasks"] = [
                {
                    "task_id": item.get("task_id"),
                    "priority": (item.get("payload") or {}).get("priority"),
                    "goal_id": (item.get("payload") or {}).get("goal_id"),
                    "subgoal_id": (item.get("payload") or {}).get("subgoal_id"),
                    "title": (item.get("payload") or {}).get("title"),
                    "files": (item.get("payload") or {}).get("files", []),
                }
                for item in queue.list(status="queued", limit=10, task_types=TASK_TYPES)
            ]
        except Exception as exc:
            payload["queue_error"] = str(exc)
    if TODO_PATH.exists():
        parse_markdown_tasks, _task_status_counts = _upstream_task_board_helpers()
        tasks = parse_markdown_tasks(TODO_PATH.read_text(encoding="utf-8", errors="replace"))
        payload["next_todo_tasks"] = [
            {"checkbox_id": task.checkbox_id, "status": task.status, "title": task.title}
            for task in tasks
            if task.status in {"needed", "in-progress"}
        ][:10]
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refactor planning supervisor backed by ipfs_accelerate_py TaskQueue.")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed", help="Scan the repo and seed/refill the taskboard once.")
    seed.add_argument("--refill-floor", type=int, default=20)
    seed.add_argument("--full-scan", action="store_true", help="Also run upstream objective/refill scans now.")
    seed.add_argument("--once", action="store_true", help="Accepted for command symmetry; seed always runs once.")

    run = sub.add_parser("run", help="Run the refill supervisor in the foreground.")
    run.add_argument("--interval-s", type=float, default=300.0)
    run.add_argument("--refill-floor", type=int, default=20)
    run.add_argument("--once", action="store_true")

    start = sub.add_parser("start", help="Start the refill supervisor as a background daemon.")
    start.add_argument("--interval-s", type=float, default=300.0)
    start.add_argument("--daemon-interval-s", type=float, default=300.0)
    start.add_argument("--refill-floor", type=int, default=20)
    start.add_argument("--implementation-timeout", type=float, default=1800.0)
    start.add_argument("--max-restarts", type=int, default=10)

    sub.add_parser("status", help="Show supervisor status.")
    sub.add_parser("stop", help="Stop the background supervisor.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "seed":
        payload = seed_taskboard(refill_floor=args.refill_floor, full_scan=args.full_scan)
    elif args.command == "run":
        payload = run_daemon(interval_s=args.interval_s, refill_floor=args.refill_floor, once=args.once)
    elif args.command == "start":
        payload = start_daemon(args)
    elif args.command == "status":
        payload = status_payload()
    elif args.command == "stop":
        payload = stop_daemon()
    else:
        raise AssertionError(args.command)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
