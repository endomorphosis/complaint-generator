from __future__ import annotations

import ast
import importlib
import runpy
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_IMPORT_MODULES = [
    "applications.complaint_workspace",
    "applications.document_api",
    "integrations.ipfs_datasets.loader",
]

SCRIPT_ENTRYPOINTS = [
    "scripts/agentic_complaint_evidence_scraper.py",
    "scripts/agentic_scraper_cli.py",
    "scripts/backfill_claim_testimony_links.py",
    "scripts/check_hacc_routers.py",
    "scripts/enrich_email_timeline_authorities.py",
    "scripts/generate_decision_trees.py",
    "scripts/generate_email_search_plan.py",
    "scripts/generate_hacc_email_seed_plan.py",
    "scripts/gmail_duckdb_daemon.py",
]

ENTRYPOINT_FILES = [
    "applications/complaint_workspace.py",
    "applications/document_api.py",
    "integrations/ipfs_datasets/loader.py",
    *SCRIPT_ENTRYPOINTS,
]


def _is_sys_path_mutator_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in {"append", "extend", "insert", "remove", "pop", "clear"}:
        return False
    value = func.value
    return (
        isinstance(value, ast.Attribute)
        and value.attr == "path"
        and isinstance(value.value, ast.Name)
        and value.value.id == "sys"
    )


def test_expected_entrypoints_do_not_mutate_sys_path_statically():
    offenders: list[str] = []
    for relative_path in ENTRYPOINT_FILES:
        path = PROJECT_ROOT / relative_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if _is_sys_path_mutator_call(node):
                offenders.append(f"{relative_path}:{node.lineno}")

    assert offenders == []


def test_production_package_imports_do_not_change_sys_path():
    before = list(sys.path)

    for module_name in PRODUCTION_IMPORT_MODULES:
        importlib.import_module(module_name)

    assert sys.path == before


def test_script_entrypoints_load_without_changing_sys_path():
    before = list(sys.path)

    for relative_path in SCRIPT_ENTRYPOINTS:
        runpy.run_path(str(PROJECT_ROOT / relative_path), run_name=f"test_import_{relative_path}")

    assert sys.path == before
