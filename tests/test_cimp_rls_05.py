"""CIMP-RLS-05: build a local wheel from the project metadata."""

import compileall
import os
import tomllib
import zipfile
from pathlib import Path

import pytest
from setuptools.build_meta import build_wheel

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_PATH = REPO_ROOT / "pyproject.toml"
PRODUCT_PACKAGES = (
    "adversarial_harness",
    "applications",
    "backends",
    "complaint_analysis",
    "complaint_generator",
    "complaint_phases",
    "integrations",
    "lib",
    "mediator",
)
ENTRY_MODULE = "complaint_generator/entrypoints.py"
CONSOLE_SCRIPT = "complaint-generator"
CONSOLE_TARGET = "complaint_generator.entrypoints:main"
ENTRY_POINTS_SUFFIX = ".dist-info/entry_points.txt"


def _project_table() -> dict:
    project = tomllib.loads(PROJECT_PATH.read_text(encoding="utf-8"))
    table = project["project"]
    assert isinstance(table, dict)
    return table


def _wheel_prefix(project: dict) -> str:
    name = project["name"]
    version = project["version"]
    assert isinstance(name, str) and isinstance(version, str)
    normalized = name.replace("-", "_")
    return f"{normalized}-{version}"


def test_local_wheel_names_console_script_and_packages_compile(tmp_path: Path) -> None:
    project = _project_table()
    scripts = project["scripts"]
    assert isinstance(scripts, dict)
    assert scripts[CONSOLE_SCRIPT] == CONSOLE_TARGET
    prefix = _wheel_prefix(project)
    assert prefix == "complaint_generator-0.1.0"

    for package_name in PRODUCT_PACKAGES:
        package_dir = REPO_ROOT / package_name
        assert package_dir.is_dir()
        compiled = compileall.compile_dir(str(package_dir), quiet=1)
        assert compiled is True

    previous = Path.cwd()
    os.chdir(REPO_ROOT)
    try:
        wheel_name = build_wheel(str(tmp_path))
    finally:
        os.chdir(previous)

    assert isinstance(wheel_name, str)
    assert wheel_name.startswith(prefix)
    wheel_path = tmp_path / wheel_name
    assert wheel_path.is_file()

    with zipfile.ZipFile(wheel_path) as archive:
        names = archive.namelist()
        assert ENTRY_MODULE in names
        entry_files = [name for name in names if name.endswith(ENTRY_POINTS_SUFFIX)]
        assert len(entry_files) == 1
        metadata = archive.read(entry_files[0]).decode("utf-8")
    assert CONSOLE_SCRIPT in metadata
    assert CONSOLE_TARGET in metadata
