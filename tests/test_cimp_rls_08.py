"""CIMP-RLS-08: release build note."""

import ast
import tomllib
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

REPO_ROOT = Path(__file__).resolve().parents[1]
NOTE = REPO_ROOT / "docs" / "RELEASE.md"
PROJECT = REPO_ROOT / "pyproject.toml"
ROOT_RELEASE = "docs/architecture/root_release.md"
CONSOLE_NAME = "complaint-generator"
CONSOLE_TARGET = "complaint_generator.entrypoints:main"


def _links(text: str) -> tuple[str, ...]:
    tree = ast.parse(repr(text))
    literal = ast.literal_eval(tree.body[0].value)
    assert isinstance(literal, str)
    targets = []
    start = 0
    while True:
        open_at = literal.find("](", start)
        if open_at < 0:
            break
        close_at = literal.find(")", open_at + 2)
        targets.append(literal[open_at + 2 : close_at])
        start = close_at + 1
    return tuple(targets)


def test_release_note_states_local_build() -> None:
    text = NOTE.read_text(encoding="utf-8")
    assert len(text.splitlines()) > 0
    project = tomllib.loads(PROJECT.read_text(encoding="utf-8"))
    version = project["project"]["version"]
    backend = project["build-system"]["build-backend"]
    scripts = project["project"]["scripts"]
    assert version == "0.1.0"
    assert version in text
    assert backend == "setuptools.build_meta"
    assert backend in text
    assert "pyproject.toml" in text
    assert scripts[CONSOLE_NAME] == CONSOLE_TARGET
    assert CONSOLE_NAME in text
    assert CONSOLE_TARGET in text
    assert "console script" in text
    assert "local wheel" in text
    assert "release build" in text
    assert "has not been published to a package index" in text
    assert "was published" not in text
    assert _links(text) == (ROOT_RELEASE,)
    assert (REPO_ROOT / ROOT_RELEASE).is_file()
    parsed = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    assert isinstance(parsed, ast.Module)
