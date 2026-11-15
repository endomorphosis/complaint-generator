"""CIMP-CUR-14: the mediator readme names the current module entry."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "mediator" / "readme.md"
SECTION_HEADING = "## Current module entry"
REQUIRED_NAMES = (
    "mediator.interface",
    "mediator.workflow_service",
    "mediator.hook_runtime",
    "mediator.state",
    "INTERFACE_SCHEMA",
    "complaint-generator/module-interface@1",
    "INTERFACE_VERSION",
    "1.0.0",
    "mediator/mediator.py",
    "Mediator",
)


def readme_lines() -> list[str]:
    """Return readme lines using splitlines(), the repository line count."""
    return README_PATH.read_text(encoding="utf-8").splitlines()


def current_module_entry(lines: list[str]) -> str:
    start = lines.index(SECTION_HEADING)
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end])


def test_mediator_readme_names_current_module_entry() -> None:
    lines = readme_lines()
    text = "\n".join(lines)
    assert lines
    assert len(lines) == len(README_PATH.read_text(encoding="utf-8").splitlines())
    assert SECTION_HEADING in text
    section = current_module_entry(lines)
    for name in REQUIRED_NAMES:
        assert name in section
    assert "Mediator owner" in section
    assert "still defines" in section
