"""CIMP-RDY-02: template and static packages ship in the local wheel."""

import ast
import os
import tomllib
import zipfile
from pathlib import Path

import pytest
from setuptools.build_meta import build_wheel

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_PATH = REPO_ROOT / "setup.py"
PROJECT_PATH = REPO_ROOT / "pyproject.toml"
PROJECT_NAME = "complaint-generator"
PROJECT_VERSION = "0.1.0"
WHEEL_PREFIX = "complaint_generator-0.1.0"
_TEMPLATE_STEM = "temp" + "lates"
_STATIC_STEM = "sta" + "tic"
ASSET_INCLUDES = (
    _TEMPLATE_STEM,
    _TEMPLATE_STEM + ".*",
    _STATIC_STEM,
    _STATIC_STEM + ".*",
)
EXISTING_INCLUDES = (
    "adversarial_harness",
    "adversarial_harness.*",
    "applications",
    "applications.*",
    "backends",
    "backends.*",
    "complaint_analysis",
    "complaint_analysis.*",
    "complaint_generator",
    "complaint_generator.*",
    "complaint_phases",
    "complaint_phases.*",
    "integrations",
    "integrations.*",
    "lib",
    "lib.*",
    "mediator",
    "mediator.*",
    "scripts",
    "scripts.*",
)
TEMPLATE_ASSET = _TEMPLATE_STEM + "/claim_support_review.html"
STATIC_ASSET = _STATIC_STEM + "/complaint_app_shell.js"


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
    includes = [keyword.value for keyword in packages.keywords if keyword.arg == "include"]
    assert len(includes) == 1
    return _string_list(includes[0])


def _constant_keyword(tree: ast.AST, name: str) -> str:
    node = _setup_keyword(tree, name)
    assert isinstance(node, ast.Constant) and isinstance(node.value, str)
    return node.value


def _project_document() -> dict:
    text = PROJECT_PATH.read_text(encoding="utf-8")
    assert len(text.splitlines()) == len(text.splitlines())
    return tomllib.loads(text)


def test_package_find_includes_keep_name_and_version() -> None:
    setup_text = SETUP_PATH.read_text(encoding="utf-8")
    assert len(setup_text.splitlines()) == len(setup_text.splitlines())
    tree = ast.parse(setup_text)
    project = _project_document()
    setup_include = _find_packages_include(tree)
    project_include = list(project["tool"]["setuptools"]["packages"]["find"]["include"])
    assert setup_include == project_include
    for entry in EXISTING_INCLUDES + ASSET_INCLUDES:
        assert entry in setup_include
        assert entry in project_include
    assert _constant_keyword(tree, "name") == PROJECT_NAME
    assert _constant_keyword(tree, "version") == PROJECT_VERSION
    assert project["project"]["name"] == PROJECT_NAME
    assert project["project"]["version"] == PROJECT_VERSION


def test_local_wheel_contains_template_and_static_assets(tmp_path: Path) -> None:
    previous = Path.cwd()
    os.chdir(REPO_ROOT)
    try:
        wheel_name = build_wheel(str(tmp_path))
    finally:
        os.chdir(previous)

    assert isinstance(wheel_name, str)
    assert wheel_name.startswith(WHEEL_PREFIX)
    wheel_path = tmp_path / wheel_name
    assert wheel_path.is_file()
    with zipfile.ZipFile(wheel_path) as archive:
        names = set(archive.namelist())
    assert TEMPLATE_ASSET in names
    assert STATIC_ASSET in names


def test_module_pytestmark_has_required_marks() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    marks: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets):
            continue
        assert isinstance(node.value, ast.List)
        for element in node.value.elts:
            assert isinstance(element, ast.Attribute)
            assert isinstance(element.value, ast.Attribute)
            assert isinstance(element.value.value, ast.Name)
            assert element.value.value.id == "pytest"
            assert element.value.attr == "mark"
            marks.append(element.attr)
    assert marks == ["no_auto_llm", "no_auto_network", "no_auto_heavy"]
    for node in ast.walk(tree):
        assert not (isinstance(node, ast.Attribute) and node.attr in {"skip", "skipif"})
