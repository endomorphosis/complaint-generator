"""CIMP-RLS-06: requirements.txt names every project dependency."""

import re
import tomllib
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"
PROJECT_PATH = REPO_ROOT / "pyproject.toml"

EDITABLE_LINES = (
    "-e .",
    "-e ./external/ipfs_kit_py[api,ipld,ai_ml]",
    "-e ./external/ipfs_datasets_py[file_conversion,ipld,knowledge_graphs,logic,scraping,vectors,api]",
)
CRYPTO_FLOOR = "cryptography>=41.0.0"
MCP_FLOOR = "mcp>=1.2.0"
_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def _distribution_name(requirement: str) -> str:
    head = requirement.split(";", 1)[0].strip()
    match = _NAME.match(head)
    assert match is not None
    return match.group(1)


def test_requirements_lock_project_dependency_names() -> None:
    requirements_text = REQUIREMENTS_PATH.read_text(encoding="utf-8")
    lines = requirements_text.splitlines()
    project = tomllib.loads(PROJECT_PATH.read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    assert isinstance(dependencies, list)
    assert dependencies

    for editable in EDITABLE_LINES:
        assert editable in lines
    assert CRYPTO_FLOOR in lines
    assert MCP_FLOOR in lines
    assert any(line.split(";", 1)[0].strip().startswith("pyarrow") for line in lines)

    for requirement in dependencies:
        assert isinstance(requirement, str)
        name = _distribution_name(requirement)
        assert name in requirements_text
