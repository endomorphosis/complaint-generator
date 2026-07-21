from __future__ import annotations

import ast
import importlib
import runpy
import sys
import tomllib
import warnings
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = REPO_ROOT
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
ARCHITECTURE_PATH = REPO_ROOT / "docs" / "ARCHITECTURE.md"

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


def _load_boundary_config() -> tuple[list[str], dict[str, list[str]]]:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    boundary_config = pyproject["tool"]["complaint_generator"]["import_boundaries"]
    enforced_packages = list(boundary_config["enforced_packages"])
    allowed_imports = dict(boundary_config["allowed_imports"])
    return enforced_packages, allowed_imports


def _python_files(package_name: str) -> Iterable[Path]:
    package_dir = REPO_ROOT / package_name
    return sorted(path for path in package_dir.rglob("*.py") if path.is_file())


def _absolute_import_roots(file_path: Path) -> set[str]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    import_roots: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            import_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            import_roots.add(node.module.split(".", 1)[0])

    return import_roots


def test_configured_package_import_boundaries_are_enforced():
    enforced_packages, allowed_imports = _load_boundary_config()
    enforced_package_set = set(enforced_packages)
    violations: list[str] = []

    for package_name in enforced_packages:
        allowed_for_package = set(allowed_imports[package_name])
        for file_path in _python_files(package_name):
            imported_roots = _absolute_import_roots(file_path)
            disallowed_roots = sorted(
                imported_root
                for imported_root in imported_roots & enforced_package_set
                if imported_root not in allowed_for_package
            )
            if disallowed_roots:
                relative_path = file_path.relative_to(REPO_ROOT).as_posix()
                violations.append(f"{relative_path}: {', '.join(disallowed_roots)}")

    assert not violations, (
        "Package import boundary violations found. Update the code or the documented "
        f"architecture contract before proceeding: {violations}"
    )


def test_import_boundary_config_is_documented():
    enforced_packages, allowed_imports = _load_boundary_config()
    architecture = ARCHITECTURE_PATH.read_text(encoding="utf-8")

    assert "### Allowed Import Direction" in architecture
    assert "### Shared Code Rule" in architecture

    for package_name in enforced_packages:
        expected_imports = ", ".join(f"`{import_name}/`" for import_name in allowed_imports[package_name])
        assert f"| `{package_name}/` | {expected_imports} |" in architecture


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
        module_path_before = list(sys.path)
        importlib.import_module(module_name)
        assert sys.path == module_path_before, f"{module_name} changed sys.path during import"

    assert sys.path == before


def test_script_entrypoints_load_without_changing_sys_path():
    before = list(sys.path)

    for relative_path in SCRIPT_ENTRYPOINTS:
        runpy.run_path(str(PROJECT_ROOT / relative_path), run_name=f"test_import_{relative_path}")

    assert sys.path == before
