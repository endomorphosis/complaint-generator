"""CIMP-ORG-10: lib readme names the versioned lib entry."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "lib" / "README.md"

INTERFACE_MODULE = "lib.interface"
OWNERS = (
    "lib.log",
    "lib.formal_logic",
    "lib.knowledge_graph_export",
)
LEGACY_NAMES = (
    "lib.deontic_logic",
    "lib.legal_document",
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
    for legacy in LEGACY_NAMES:
        assert legacy not in text
    assert (REPO_ROOT / "lib" / "interface.py").is_file()
    assert _line_count(README) > 0
