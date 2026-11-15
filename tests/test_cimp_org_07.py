"""CIMP-ORG-07: harness readme names the versioned harness entry."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "adversarial_harness" / "README.md"
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

INTERFACE_MODULE = "adversarial_harness.interface"
OWNERS = (
    "adversarial_harness.harness",
    "adversarial_harness.optimizer",
    "adversarial_harness.session",
)
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
HEADING = "## Current entry"


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text[start + len(heading):]
    end = rest.find("\n## ")
    body = rest if end < 0 else rest[:end]
    return heading + body


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_current_entry_names_interface_owners_schema_and_version() -> None:
    text = README.read_text(encoding="utf-8")
    section = _section(text, HEADING)
    assert INTERFACE_MODULE in section
    for owner in OWNERS:
        assert owner in section
    assert "INTERFACE_SCHEMA" in section
    assert INTERFACE_SCHEMA in section
    assert "INTERFACE_VERSION" in section
    assert INTERFACE_VERSION in section
    assert (REPO_ROOT / "adversarial_harness" / "interface.py").is_file()
    assert _line_count(README) > 0
