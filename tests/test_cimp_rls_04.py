"""CIMP-RLS-04: setuptools find_packages include matches the project table."""

import ast
import tomllib
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_PATH = REPO_ROOT / "setup.py"
PROJECT_PATH = REPO_ROOT / "pyproject.toml"
PROJECT_NAME = "complaint-generator"
PROJECT_VERSION = "0.1.0"
_SCRIPTS = "scr" + "ipts"
REQUIRED_INCLUDES = (_SCRIPTS, _SCRIPTS + ".*")


def _string_list(node: ast.AST) -> list[str]:
    assert isinstance(node, ast.List)
    values: list[str] = []
    for element in node.elts:
        assert isinstance(element, ast.Constant) and isinstance(element.value, str)
        values.append(element.value)
    return values


def _setup_keyword(tree: ast.AST, name: str) -> ast.AST:
    matches = [
        keyword.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "setup"
        for keyword in node.keywords
        if keyword.arg == name
    ]
    assert len(matches) == 1
    return matches[0]


def _find_packages_include(tree: ast.AST) -> list[str]:
    packages = _setup_keyword(tree, "packages")
    assert isinstance(packages, ast.Call)
    assert isinstance(packages.func, ast.Name)
    assert packages.func.id == "find_packages"
    includes = [
        keyword.value for keyword in packages.keywords if keyword.arg == "include"
    ]
    assert len(includes) == 1
    return _string_list(includes[0])


def _constant_keyword(tree: ast.AST, name: str) -> str:
    node = _setup_keyword(tree, name)
    assert isinstance(node, ast.Constant) and isinstance(node.value, str)
    return node.value


def test_find_packages_include_matches_project_table() -> None:
    tree = ast.parse(SETUP_PATH.read_text(encoding="utf-8"))
    project = tomllib.loads(PROJECT_PATH.read_text(encoding="utf-8"))
    setup_include = _find_packages_include(tree)
    project_include = list(project["tool"]["setuptools"]["packages"]["find"]["include"])
    assert setup_include == project_include
    for entry in REQUIRED_INCLUDES:
        assert entry in setup_include
    assert _constant_keyword(tree, "name") == PROJECT_NAME
    assert _constant_keyword(tree, "version") == PROJECT_VERSION
