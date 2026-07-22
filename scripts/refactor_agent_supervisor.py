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
import re
import shlex
import signal
import socket
import subprocess
import sys
import time
import ast
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
BUNDLE_LANE_ROOT = STATE_ROOT / "bundle_lanes"
BUNDLE_LANE_MANIFEST = BUNDLE_LANE_ROOT / "bundle_lanes.json"
BUNDLE_COORDINATION_PATH = BUNDLE_LANE_ROOT / "coordination.sqlite3"
MERGE_RESOLVER_PID_PATH = STATE_ROOT / "merge_resolver_watchdog.pid"
MERGE_RESOLVER_STATUS_PATH = STATE_ROOT / "merge_resolver_watchdog_status.json"
MERGE_RESOLVER_LOG_PATH = STATE_ROOT / "merge_resolver_watchdog.log"
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


def _upstream_bundle_runner():
    _ensure_accelerate_import_path()
    from ipfs_accelerate_py.agent_supervisor.bundle_supervisor import build_arg_parser, run_bundle_supervisor

    return build_arg_parser, run_bundle_supervisor


def merge_resolver_command() -> str:
    return shlex.join(
        (
            "env",
            f"PYTHONPATH={ACCELERATE_REPO}{os.pathsep}{PROJECT_ROOT}",
            "AGENT_MERGE_LLM_ROUTER_CONFIG=config.llm_router.json",
            "AGENT_MERGE_LLM_ROUTER_BACKEND_ID=llm-router-codex",
            "AGENT_MERGE_LLM_ROUTER_MAX_TOKENS=4096",
            "CODEX_MERGE_RESOLVER_TIMEOUT_SECONDS=300",
            "COPILOT_MERGE_RESOLVER_TIMEOUT_SECONDS=300",
            "AGENT_RESOLVER_LOCK_TIMEOUT_SECONDS=60",
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "llm_router_merge_resolver.py"),
        )
    )


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
    task_id: str = ""
    depends_on: tuple[str, ...] = ()

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
            "task_id": self.task_id,
            "depends_on": list(self.depends_on),
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
        {
            "id": "G9",
            "title": "Increase agent-supervisor planning quality and throughput",
            "priority": "P0",
            "subgoals": [
                {
                    "id": "G9.S1",
                    "title": "Establish canonical coordination and merge flow",
                    "tasks": [
                        _task(
                            "G9",
                            "G9.S1",
                            "Introduce canonical task identity and a durable supervisor task ledger",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_identity.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/persistent_task_queue.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py",
                            ),
                            "Bundle-local numeric task ids currently collide across boards and make global reconciliation ambiguous.",
                            (
                                "Every task has a stable canonical key or CID independent of board path and display id.",
                                "Legacy markdown tasks migrate idempotently with board namespace provenance.",
                                "Branches, events, retries, cooldowns, leases, and receipts carry canonical identity.",
                                "Refill cannot create a second active task for the same canonical work item.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q",
                            ),
                            task_id="REF-036",
                        ),
                        _task(
                            "G9",
                            "G9.S1",
                            "Replace static bundle launch with a dynamic leased worker pool",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/multi_supervisor_runner.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py",
                            ),
                            "The current bundle supervisor starts the first N lexical bundles once and cannot reclaim idle lanes or discover refilled work.",
                            (
                                "A persistent scheduler discovers new and refilled tasks without restart.",
                                "Workers claim ready tasks, release drained or blocked leases, and steal conflict-safe work.",
                                "Lane count remains within configured capacity and no task executes under two accepted leases.",
                                "The manifest is an authoritative live projection rather than a launch-time snapshot.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_lease_coordination.py -q",
                            ),
                            task_id="REF-037",
                            depends_on=("REF-036",),
                        ),
                        _task(
                            "G9",
                            "G9.S1",
                            "Integrate a deduplicating single-consumer merge train",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_queue.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_train.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/merge_resolver.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_merge_train.py",
                            ),
                            "Independent lanes currently race to merge and repeatedly retry the same failed branches.",
                            (
                                "All implementation lanes enqueue merge candidates instead of racing the target checkout.",
                                "The train deduplicates by canonical task and commit, rebases on the latest target, and preserves priority plus age fairness.",
                                "One conflict fingerprint invokes at most one active resolver attempt.",
                                "Bounded failures enter quarantine with a durable receipt instead of a polling retry loop.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_merge_train.py -q",
                            ),
                            task_id="REF-038",
                            depends_on=("REF-037",),
                        ),
                    ],
                },
                {
                    "id": "G9.S2",
                    "title": "Plan from dependencies, conflicts, and objective value",
                    "tasks": [
                        _task(
                            "G9",
                            "G9.S2",
                            "Materialize a task dependency DAG and schedule its critical path",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py",
                            ),
                            "Goal parents are currently sorting hints while generated Profile G tasks carry no dependency task CIDs.",
                            (
                                "Goal, import, interface, output-input, migration, and validation prerequisites become explicit DAG edges with provenance.",
                                "Only tasks whose prerequisite merge receipts succeeded are claimable.",
                                "Priority includes critical-path length, slack, downstream unlock value, age, and configured objective priority.",
                                "Cycles and missing dependencies produce bounded repair evidence rather than deadlock.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_planner.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q",
                            ),
                            task_id="REF-039",
                            depends_on=("REF-037",),
                        ),
                        _task(
                            "G9",
                            "G9.S2",
                            "Build an AST and changed-path conflict graph for lane coloring",
                            "P0",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/conflict_graph.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_vector_index.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py",
                            ),
                            "The current conflict domain uses one path root and lightweight semantic similarity, which misses multi-file and symbol overlap.",
                            (
                                "Conflict surfaces include all predicted files, AST symbols, interfaces, submodules, and generated artifacts.",
                                "Lane planning colors the conflict graph so overlapping tasks do not run concurrently unless explicitly allowed.",
                                "Actual branch diffs and conflict receipts update future conflict weights.",
                                "Planner output explains every co-location or separation decision.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_conflict_graph.py ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_objective_graph.py -q",
                            ),
                            task_id="REF-040",
                            depends_on=("REF-039",),
                        ),
                        _task(
                            "G9",
                            "G9.S2",
                            "Use llm_router to generate and evaluate structured plan branches",
                            "P1",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/task_proposal_router.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/plan_evaluator.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_daemon.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py",
                            ),
                            "Profile G currently records a single constant-scored plan branch and the LLM proposal router is not part of scheduler decisions.",
                            (
                                "Each eligible subgoal can produce multiple schema-validated plan branches through llm_router.",
                                "Candidates declare predicted files and symbols, dependencies, validation proof, cost, risk, and expected objective delta.",
                                "A deterministic evaluator selects a branch and retains rejected alternatives plus rationale.",
                                "Router failure falls back to deterministic planning without blocking ready work.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_plan_evaluator.py -q",
                            ),
                            task_id="REF-041",
                            depends_on=("REF-039",),
                        ),
                    ],
                },
                {
                    "id": "G9.S3",
                    "title": "Adapt execution capacity and validation cost",
                    "tasks": [
                        _task(
                            "G9",
                            "G9.S3",
                            "Schedule lanes from live resources and llm_router provider capacity",
                            "P1",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/resource_scheduler.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/lease_coordination.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/leased_lane.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_resource_scheduler.py",
                            ),
                            "Resource class, capability fit, and lane capacity are currently static even when workers are idle or providers are rate-limited.",
                            (
                                "Heartbeats report measured CPU, memory, disk, active phase, and available worker capacity.",
                                "Scheduler honors llm_router health, quota, latency, context, and token-budget constraints.",
                                "Concurrency scales within configured limits and applies backpressure before provider or host exhaustion.",
                                "Idle lanes advertise zero occupied capacity and can be reassigned.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_resource_scheduler.py -q",
                            ),
                            task_id="REF-042",
                            depends_on=("REF-037", "REF-041"),
                        ),
                        _task(
                            "G9",
                            "G9.S3",
                            "Add impact-selected cached and parallel validation stages",
                            "P1",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_commands.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/validation_scheduler.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_validation_scheduler.py",
                            ),
                            "Validation commands currently run serially without changed-file impact selection or reusable baseline results.",
                            (
                                "Cheap deterministic checks run before expensive tests and fail fast.",
                                "Independent validations run in parallel under a bounded resource budget.",
                                "Cache keys include target commit, command, relevant environment, and dependency state.",
                                "Impact selection is conservative, explainable, and escalates to broader validation before merge completion.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_validation_scheduler.py -q",
                            ),
                            task_id="REF-043",
                            depends_on=("REF-038",),
                        ),
                    ],
                },
                {
                    "id": "G9.S4",
                    "title": "Close the scheduler feedback and lifecycle loop",
                    "tasks": [
                        _task(
                            "G9",
                            "G9.S4",
                            "Publish authoritative throughput metrics and scheduler state",
                            "P1",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/scheduler_metrics.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/event_log.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/supervisor_watchdog.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/bundle_supervisor.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py",
                            ),
                            "Status is split across launch manifests, wrapper files, lane state, and event logs, so planners cannot measure useful capacity.",
                            (
                                "One event-derived snapshot reports ready, active, idle, blocked, validation, merge, and resolver phases.",
                                "Metrics include queue wait, implementation and validation duration, merge wait, conflict and retry rate, completions, tokens, and cost.",
                                "Every metric is keyed by canonical goal, subgoal, task, lane, and provider identity.",
                                "Scheduler decisions consume the same snapshot exposed to operators.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_scheduler_metrics.py -q",
                            ),
                            task_id="REF-044",
                            depends_on=("REF-037", "REF-038", "REF-039"),
                        ),
                        _task(
                            "G9",
                            "G9.S4",
                            "Make AST scans and implementation workspaces incremental and reusable",
                            "P2",
                            (
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/objective_graph.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/dataset_store.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/worktrees.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py",
                                "ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py",
                            ),
                            "Refill scans reread the tracked codebase and each implementation creates fresh worktree and submodule setup even when inputs are unchanged.",
                            (
                                "AST and evidence records are reused by blob hash and only changed files are reparsed.",
                                "Deleted and renamed files invalidate stale evidence deterministically.",
                                "Clean worktrees and dependency setups can be pooled without sharing task-local mutations.",
                                "Cold and warm paths produce equivalent plans and validation results with measured warm-path savings.",
                            ),
                            (
                                "PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_incremental_runtime.py -q",
                            ),
                            task_id="REF-045",
                            depends_on=("REF-040", "REF-042", "REF-043", "REF-044"),
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
    *,
    task_id: str = "",
    depends_on: tuple[str, ...] = (),
) -> RefactorTask:
    clean_files = tuple(dict.fromkeys(f for f in files if f))
    clean_dependencies = tuple(dict.fromkeys(item for item in depends_on if item))
    return RefactorTask(
        goal_id,
        subgoal_id,
        title,
        priority,
        clean_files,
        rationale,
        acceptance,
        validation,
        task_id,
        clean_dependencies,
    )


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
                    "- Validation: " + "; ".join(
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
        task_id = task.task_id or f"{TASK_PREFIX}{index:03d}"
        lines.append(_task_block(task, task_id, _task_checkbox_index(task_id, index)))
        lines.append("")
        index += 1
    return "\n".join(lines).rstrip() + "\n"


def _task_checkbox_index(task_id: str, fallback: int) -> int:
    match = re.fullmatch(rf"{re.escape(TASK_PREFIX)}(\d+)", task_id)
    return int(match.group(1)) if match else fallback


def _append_missing_explicit_seed_tasks(path: Path, goals: list[dict[str, Any]]) -> bool:
    if not path.exists():
        return False

    text = path.read_text(encoding="utf-8", errors="replace")
    header_pattern = re.compile(
        rf"^##\s+({re.escape(TASK_PREFIX)}\d+)\s+(.+?)\s*$",
        re.MULTILINE,
    )
    existing_titles = {match.group(1): match.group(2) for match in header_pattern.finditer(text)}
    additions: list[str] = []
    for fallback, task in enumerate(flatten_tasks(goals), start=1):
        if not task.task_id:
            continue
        existing_title = existing_titles.get(task.task_id)
        if existing_title is not None:
            if existing_title != task.title:
                raise RuntimeError(
                    f"Explicit seed id {task.task_id} already names {existing_title!r}, "
                    f"not {task.title!r}"
                )
            continue
        additions.append(
            _task_block(
                task,
                task.task_id,
                _task_checkbox_index(task.task_id, fallback),
            )
        )
        existing_titles[task.task_id] = task.title

    if not additions:
        return False
    path.write_text(text.rstrip() + "\n\n" + "\n\n".join(additions) + "\n", encoding="utf-8")
    return True


def _safe_bundle_key(value: str) -> str:
    cleaned = []
    for char in value.lower():
        if char.isalnum():
            cleaned.append(char)
        elif char in {"/", "-", "_", "."}:
            cleaned.append("-")
    key = "".join(cleaned).strip("-")
    while "--" in key:
        key = key.replace("--", "-")
    return key or "refactor-general"


def _task_ast_symbols(files: tuple[str, ...], *, limit: int = 80) -> list[str]:
    symbols: list[str] = []
    for rel in files:
        path = PROJECT_ROOT / rel
        if path.suffix != ".py" or not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            name = ""
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = node.name
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        name = target.id
                        break
            if name and name not in symbols:
                symbols.append(name)
            if len(symbols) >= limit:
                return symbols
    return symbols


def _task_block(task: RefactorTask, task_id: str, index: int) -> str:
    outputs = ", ".join(task.files) or str(TASKBOARD_DOC_PATH.relative_to(PROJECT_ROOT))
    validation = "; ".join(task.validation) or "python -m pytest --collect-only -q"
    bundle_key = f"refactor/{task.goal_id.lower()}/{task.subgoal_id.replace('.', '-').lower()}"
    symbols = ", ".join(_task_ast_symbols(task.files)[:30])
    return "\n".join(
        [
            f"- [ ] Task checkbox-{index}: {task_id} {task.title}",
            "",
            f"## {task_id} {task.title}",
            "",
            "- Status: todo",
            "- Completion: manual",
            f"- Priority: {task.priority}",
            f"- Track: {task.goal_id}",
            "- Depends on: " + ", ".join(task.depends_on),
            f"- Outputs: {outputs}",
            f"- Validation: {validation}",
            f"- Bundle: {bundle_key}",
            "- Bundle strategy: goal/subgoal bundle with AST-symbol locality",
            f"- Goal id: {task.subgoal_id}",
            f"- Missing evidence: {task.rationale}",
            f"- AST symbols: {symbols}",
            f"- Merge key: {bundle_key}",
            "- Candidate kind: seed",
            f"- Todo vector key: {task_id.lower()}-{_safe_bundle_key(task.title)[:48]}",
            "- Acceptance: " + "; ".join(task.acceptance),
        ]
    )


def write_seed_bundle_index(
    goals: list[dict[str, Any]],
    *,
    exclude_bundle_keys: set[str] | None = None,
) -> dict[str, Any]:
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    bundles: dict[str, dict[str, Any]] = {}
    excluded = exclude_bundle_keys or set()
    task_index = 1
    for task in flatten_tasks(goals):
        task_id = task.task_id or f"{TASK_PREFIX}{task_index:03d}"
        bundle_key = f"refactor/{task.goal_id.lower()}/{task.subgoal_id.replace('.', '-').lower()}"
        if bundle_key in excluded:
            task_index += 1
            continue
        safe_key = _safe_bundle_key(bundle_key)
        shard_path = BUNDLE_DIR / f"{safe_key}.todo.md"
        block = _task_block(task, task_id, _task_checkbox_index(task_id, task_index))
        if shard_path.exists():
            shard_text = shard_path.read_text(encoding="utf-8", errors="replace")
        else:
            shard_text = (
                f"# Objective Bundle: {bundle_key}\n\n"
                f"Source todo: {TODO_PATH.relative_to(PROJECT_ROOT)}\n"
                "Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.\n"
                "Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.\n"
            )
        if f"## {task_id} " not in shard_text:
            shard_text = shard_text.rstrip() + "\n\n" + block + "\n"
            shard_path.write_text(shard_text, encoding="utf-8")

        info = bundles.setdefault(
            bundle_key,
            {
                "bundle_key": bundle_key,
                "shard_path": shard_path.relative_to(PROJECT_ROOT).as_posix(),
                "parallel_lane": bundle_key,
                "bundle_strategy": "goal_subgoal_ast",
                "conflict_policy": "prefer bundle-local changes; reconcile generated worktrees before merge",
                "tasks": [],
            },
        )
        info["tasks"].append(
            {
                "task_id": task_id,
                "goal_id": task.subgoal_id,
                "graph_depth": 1,
                "parent_goal_ids": [task.goal_id],
                "missing_evidence": [task.rationale, *task.acceptance],
                "discovery_path": TASKBOARD_DOC_PATH.relative_to(PROJECT_ROOT).as_posix(),
                "bundle_strategy": "goal_subgoal_ast",
                "surplus_group": bundle_key,
                "merge_key": bundle_key,
                "merge_family": task.goal_id,
                "merge_role": "seed",
                "work_item_count": max(1, len(task.files)),
                "work_scope": "goal_subgoal_ast_locality",
                "goal_packet_key": task.subgoal_id,
                "goal_packet_role": "seed",
                "goal_packet_goal_ids": [task.goal_id, task.subgoal_id],
                "goal_packet_task_count": 1,
                "goal_packet_work_item_count": max(1, len(task.files)),
                "candidate_kind": "seed",
                "todo_vector_key": f"{task_id.lower()}-{_safe_bundle_key(task.title)[:48]}",
                "ast_symbols": _task_ast_symbols(task.files),
                "paths": list(task.files),
                "validation": list(task.validation),
                "depends_on": list(task.depends_on),
            }
        )
        task_index += 1

    index_payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_todo": TODO_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "schema": "complaint_generator.refactor_seed_bundle_index",
        "bundle_strategy": "goal_subgoal_ast",
        "bundles": bundles,
    }
    index_path = BUNDLE_DIR / "index.json"
    index_path.write_text(json.dumps(index_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "bundle_index_path": str(index_path),
        "bundle_count": len(bundles),
        "task_count": sum(len(bundle.get("tasks", [])) for bundle in bundles.values()),
        "excluded_bundle_keys": sorted(excluded),
    }


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


def _todo_task_header_count(path: Path = TODO_PATH) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    return len(
        re.findall(
            rf"^##\s+{re.escape(TASK_PREFIX)}\d+\b",
            text,
            flags=re.MULTILINE,
        )
    )


def seed_taskboard(
    *,
    refill_floor: int = 20,
    submit_bundles: bool = True,
    force: bool = False,
    full_scan: bool = False,
    exclude_bundle_keys: set[str] | None = None,
) -> dict[str, Any]:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    scan = scan_codebase()
    goals = build_goals(scan)

    goal_tree = _json_goal_tree(goals, scan)
    GOALS_PATH.write_text(json.dumps(goal_tree, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    objective_changed = _ensure_text(OBJECTIVE_PATH, _render_objective_heap(goals), overwrite=True)
    existing_todo_headers = _todo_task_header_count()
    todo_changed = _ensure_text(TODO_PATH, _render_seed_todo(goals), overwrite=existing_todo_headers == 0)
    if existing_todo_headers:
        todo_changed = _append_missing_explicit_seed_tasks(TODO_PATH, goals) or todo_changed
    bundle_seed = write_seed_bundle_index(goals, exclude_bundle_keys=exclude_bundle_keys)

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
                "bundle_seed": bundle_seed,
            },
        }
    )
    return {
        "objective_changed": objective_changed,
        "todo_changed": todo_changed,
        "counts": counts,
        "objective_result": objective_result,
        "backlog_result": backlog_result,
        "bundle_seed": bundle_seed,
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
        "--llm-merge-resolver-command",
        merge_resolver_command(),
        "--llm-merge-resolver-timeout-seconds",
        str(float(args.merge_resolver_timeout)),
        "--merge-reconciliation-max-merges",
        str(int(args.merge_reconciliation_max_merges)),
        "--auto-commit-generated-dirty",
        "--generated-dirty-commit-subject",
        "Agent: commit refactor supervisor generated outputs",
        "--generated-dirty-max-paths",
        str(int(args.generated_dirty_max_paths)),
        "--generated-dirty-stale-lock-seconds",
        str(float(args.generated_dirty_stale_lock_seconds)),
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


def run_parallel_bundle_supervisor(args: argparse.Namespace, *, start: bool) -> dict[str, Any]:
    exclude_bundle_keys = active_bundle_keys() if start and args.skip_active_bundle else set()
    seed_result = seed_taskboard(
        refill_floor=args.refill_floor,
        full_scan=bool(args.full_scan),
        exclude_bundle_keys=exclude_bundle_keys,
    )
    bundle_index_path = BUNDLE_DIR / "index.json"
    parser_factory, run_bundle_supervisor = _upstream_bundle_runner()
    argv = [
        "--bundle-index-path",
        str(bundle_index_path),
        "--repo-root",
        str(PROJECT_ROOT),
        "--state-root",
        str(BUNDLE_LANE_ROOT),
        "--worktree-root",
        str(BUNDLE_LANE_ROOT / "worktrees"),
        "--log-dir",
        str(BUNDLE_LANE_ROOT / "logs"),
        "--manifest-path",
        str(BUNDLE_LANE_MANIFEST),
        "--task-prefix",
        TASK_PREFIX,
        "--max-lanes",
        str(int(args.max_lanes)),
        "--daemon-interval",
        str(float(args.daemon_interval_s)),
        "--check-interval",
        str(float(args.interval_s)),
        "--max-restarts",
        str(int(args.max_restarts)),
        "--implementation-timeout",
        str(float(args.implementation_timeout)),
        "--llm-merge-resolver-command",
        merge_resolver_command(),
        "--llm-merge-resolver-timeout-seconds",
        str(float(args.merge_resolver_timeout)),
        "--merge-reconciliation-max-merges",
        str(int(args.merge_reconciliation_max_merges)),
        "--auto-commit-generated-dirty",
        "--generated-dirty-commit-subject",
        "Agent: commit refactor lane generated outputs",
        "--generated-dirty-max-paths",
        str(int(args.generated_dirty_max_paths)),
        "--generated-dirty-stale-lock-seconds",
        str(float(args.generated_dirty_stale_lock_seconds)),
        "--coordination-path",
        str(BUNDLE_COORDINATION_PATH),
        "--claimant-did",
        "did:web:complaint-generator.local",
        "--lease-ms",
        str(int(args.lease_ms)),
    ]
    argv.append("--implement" if args.implement else "--no-implement")
    if start:
        argv.append("--start")
    bundle_args = parser_factory().parse_args(argv)
    payload = run_bundle_supervisor(bundle_args)
    payload["seed"] = {
        "counts": seed_result.get("counts"),
        "bundle_seed": seed_result.get("bundle_seed"),
    }
    payload["mode"] = "start_parallel" if start else "plan_parallel"
    _write_status(
        {
            "status": "parallel_started" if start else "parallel_planned",
            "pid": 0,
            "pid_alive": False,
            "objective_path": str(OBJECTIVE_PATH),
            "todo_path": str(TODO_PATH),
            "bundle_dir": str(BUNDLE_DIR),
            "bundle_lane_manifest": str(BUNDLE_LANE_MANIFEST),
            "bundle_coordination_path": str(BUNDLE_COORDINATION_PATH),
            "last_parallel": payload,
        }
    )
    return payload


def active_bundle_keys() -> set[str]:
    state_path = SUPERVISOR_STATE_DIR / "complaint_generator_refactor_task_state.json"
    if not state_path.exists() or not TODO_PATH.exists():
        return set()
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    active_task_id = str(state.get("active_task_id") or "").strip()
    if not active_task_id:
        return set()
    text = TODO_PATH.read_text(encoding="utf-8", errors="replace")
    block_pattern = re.compile(
        rf"^##\s+{re.escape(active_task_id)}\s+.*?(?=^\s*-\s+\[\s?\]\s+Task checkbox-|^##\s+{re.escape(TASK_PREFIX)}|\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    match = block_pattern.search(text)
    if not match:
        return set()
    bundle_match = re.search(r"^-\s+Bundle:\s*(.+?)\s*$", match.group(0), flags=re.MULTILINE)
    if not bundle_match:
        return set()
    return {bundle_match.group(1).strip()}


def merge_event_paths() -> list[Path]:
    paths: list[Path] = []
    for root in (SUPERVISOR_STATE_DIR, BUNDLE_LANE_ROOT):
        if not root.exists():
            continue
        for path in root.rglob("*events.jsonl"):
            if path.is_file():
                paths.append(path)
    return sorted(dict.fromkeys(paths))


def resolve_merge_conflicts_once(*, timeout_seconds: float = 900.0, max_events: int = 1) -> dict[str, Any]:
    _ensure_accelerate_import_path()
    from ipfs_accelerate_py.agent_supervisor.merge_resolver import invoke_llm_resolver, resolver_payload

    results: list[dict[str, Any]] = []
    attempted = 0
    for events_path in merge_event_paths():
        try:
            payload = resolver_payload(
                events_path=events_path,
                repo_root=PROJECT_ROOT,
                prompt_heading="Resolve this complaint-generator autonomous refactor merge conflict.",
                completion_rule="Leave the repository merge-clean and preserve the implemented task intent.",
                extra_rules=[
                    "Prefer the smallest conflict resolution that keeps tests and task acceptance criteria meaningful.",
                    "Do not discard unrelated user changes in the main checkout.",
                    "If a generated worktree is involved, resolve inside that worktree and commit the merge there when appropriate.",
                ],
            )
            if not payload.get("found"):
                results.append({"events_path": str(events_path), "found": False})
                continue
            if attempted >= max(1, int(max_events)):
                results.append(
                    {
                        "events_path": str(events_path),
                        "found": True,
                        "task_id": payload.get("task_id"),
                        "skipped": True,
                        "skip_reason": "max_events reached for this watchdog cycle",
                    }
                )
                continue
            attempted += 1
            applied = invoke_llm_resolver(
                payload,
                command_template=merge_resolver_command(),
                timeout_seconds=timeout_seconds,
            )
            results.append(
                {
                    "events_path": str(events_path),
                    "found": True,
                    "task_id": applied.get("task_id"),
                    "applied": applied.get("applied", False),
                    "llm_returncode": applied.get("llm_returncode"),
                    "apply_error": applied.get("apply_error", ""),
                }
            )
        except Exception as exc:
            results.append({"events_path": str(events_path), "error": str(exc)})
    payload = {
        "status": "checked",
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event_log_count": len(results),
        "found_count": sum(1 for item in results if item.get("found")),
        "applied_count": sum(1 for item in results if item.get("applied")),
        "attempted_count": attempted,
        "results": results,
    }
    MERGE_RESOLVER_STATUS_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def run_merge_resolver_watchdog(*, interval_s: float, timeout_seconds: float, once: bool = False) -> dict[str, Any]:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    MERGE_RESOLVER_PID_PATH.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    cycle = 0
    last: dict[str, Any] = {}

    def _stop(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        while True:
            cycle += 1
            last = resolve_merge_conflicts_once(timeout_seconds=timeout_seconds, max_events=1)
            last["cycle"] = cycle
            last["status"] = "running" if not once else "checked"
            MERGE_RESOLVER_STATUS_PATH.write_text(json.dumps(last, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            if once:
                break
            time.sleep(max(10.0, float(interval_s)))
    except KeyboardInterrupt:
        last = {"status": "stopped", "cycle": cycle, "last": last}
        MERGE_RESOLVER_STATUS_PATH.write_text(json.dumps(last, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    finally:
        try:
            if MERGE_RESOLVER_PID_PATH.exists() and MERGE_RESOLVER_PID_PATH.read_text(encoding="utf-8").strip() == str(os.getpid()):
                MERGE_RESOLVER_PID_PATH.unlink()
        except Exception:
            pass
    return last


def start_merge_resolver_watchdog(args: argparse.Namespace) -> dict[str, Any]:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    if MERGE_RESOLVER_PID_PATH.exists():
        try:
            pid = int(MERGE_RESOLVER_PID_PATH.read_text(encoding="utf-8").strip())
        except Exception:
            pid = 0
        if _pid_alive(pid):
            return {"status": "already_running", "pid": pid, "status_path": str(MERGE_RESOLVER_STATUS_PATH)}
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ACCELERATE_REPO) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "merge-watchdog-run",
        "--interval-s",
        str(float(args.interval_s)),
        "--timeout-seconds",
        str(float(args.timeout_seconds)),
    ]
    log_handle = MERGE_RESOLVER_LOG_PATH.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    time.sleep(1.0)
    payload = {
        "status": "started",
        "pid": proc.pid,
        "status_path": str(MERGE_RESOLVER_STATUS_PATH),
        "log_path": str(MERGE_RESOLVER_LOG_PATH),
        "merge_resolver_command": merge_resolver_command(),
    }
    MERGE_RESOLVER_STATUS_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
        "bundle_lane_manifest": str(BUNDLE_LANE_MANIFEST),
        "bundle_coordination_path": str(BUNDLE_COORDINATION_PATH),
        "merge_resolver_command": merge_resolver_command(),
        "merge_resolver_enabled_for_new_launches": True,
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
    if BUNDLE_LANE_MANIFEST.exists():
        try:
            manifest = json.loads(BUNDLE_LANE_MANIFEST.read_text(encoding="utf-8"))
            payload["parallel_lanes"] = {
                "planned_count": manifest.get("planned_count", 0),
                "started_count": manifest.get("started_count", 0),
                "started": [
                    {
                        "bundle_key": item.get("bundle_key"),
                        "accepted": item.get("accepted"),
                        "pid": item.get("pid"),
                        "log_path": item.get("log_path"),
                    }
                    for item in manifest.get("started", [])[:10]
                    if isinstance(item, dict)
                ],
            }
        except Exception as exc:
            payload["parallel_lanes_error"] = str(exc)
    if MERGE_RESOLVER_STATUS_PATH.exists():
        try:
            merge_payload = json.loads(MERGE_RESOLVER_STATUS_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            merge_payload = {"status_read_error": str(exc)}
        if MERGE_RESOLVER_PID_PATH.exists():
            try:
                merge_pid = int(MERGE_RESOLVER_PID_PATH.read_text(encoding="utf-8").strip())
            except Exception:
                merge_pid = 0
            merge_payload["pid"] = merge_pid
            merge_payload["pid_alive"] = _pid_alive(merge_pid)
        payload["merge_resolver_watchdog"] = merge_payload
    return payload


def add_parallel_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--refill-floor", type=int, default=24)
    parser.add_argument("--max-lanes", type=int, default=4)
    parser.add_argument("--interval-s", type=float, default=120.0)
    parser.add_argument("--daemon-interval-s", type=float, default=120.0)
    parser.add_argument("--implementation-timeout", type=float, default=1800.0)
    parser.add_argument("--max-restarts", type=int, default=3)
    parser.add_argument("--merge-resolver-timeout", type=float, default=900.0)
    parser.add_argument("--merge-reconciliation-max-merges", type=int, default=2)
    parser.add_argument("--generated-dirty-max-paths", type=int, default=200)
    parser.add_argument("--generated-dirty-stale-lock-seconds", type=float, default=300.0)
    parser.add_argument("--lease-ms", type=int, default=300000)
    parser.add_argument("--full-scan", action="store_true", help="Run the expensive upstream objective AST scan before planning lanes.")
    parser.add_argument("--skip-active-bundle", action="store_true", default=True)
    implement_group = parser.add_mutually_exclusive_group()
    implement_group.add_argument("--implement", dest="implement", action="store_true")
    implement_group.add_argument("--no-implement", dest="implement", action="store_false")
    parser.set_defaults(implement=True)


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
    start.add_argument("--merge-resolver-timeout", type=float, default=900.0)
    start.add_argument("--merge-reconciliation-max-merges", type=int, default=2)
    start.add_argument("--generated-dirty-max-paths", type=int, default=200)
    start.add_argument("--generated-dirty-stale-lock-seconds", type=float, default=300.0)

    plan_parallel = sub.add_parser("plan-parallel", help="Plan goal/subgoal/AST bundle lanes without launching them.")
    add_parallel_args(plan_parallel)

    start_parallel = sub.add_parser("start-parallel", help="Launch upstream leased bundle supervisors for parallel task lanes.")
    add_parallel_args(start_parallel)

    resolve_merges = sub.add_parser("resolve-merges", help="Run one merge-conflict resolver scan over supervisor event logs.")
    resolve_merges.add_argument("--timeout-seconds", type=float, default=900.0)

    merge_watch = sub.add_parser("start-merge-watchdog", help="Start a background watchdog that resolves failed merge events.")
    merge_watch.add_argument("--interval-s", type=float, default=120.0)
    merge_watch.add_argument("--timeout-seconds", type=float, default=900.0)

    merge_run = sub.add_parser("merge-watchdog-run", help=argparse.SUPPRESS)
    merge_run.add_argument("--interval-s", type=float, default=120.0)
    merge_run.add_argument("--timeout-seconds", type=float, default=900.0)
    merge_run.add_argument("--once", action="store_true")

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
    elif args.command == "plan-parallel":
        payload = run_parallel_bundle_supervisor(args, start=False)
    elif args.command == "start-parallel":
        payload = run_parallel_bundle_supervisor(args, start=True)
    elif args.command == "resolve-merges":
        payload = resolve_merge_conflicts_once(timeout_seconds=args.timeout_seconds)
    elif args.command == "start-merge-watchdog":
        payload = start_merge_resolver_watchdog(args)
    elif args.command == "merge-watchdog-run":
        payload = run_merge_resolver_watchdog(
            interval_s=args.interval_s,
            timeout_seconds=args.timeout_seconds,
            once=args.once,
        )
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
