"""CIMP-ORG-08: backends guide names the versioned backend entry."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUIDE = REPO_ROOT / "docs" / "BACKENDS.md"

INTERFACE_MODULE = "backends.interface"
OWNER = "backends.llm_router_backend"
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


def test_current_entry_names_interface_owner_schema_and_version() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    section = _section(text, HEADING)
    assert INTERFACE_MODULE in section
    assert OWNER in section
    assert "INTERFACE_SCHEMA" in section
    assert INTERFACE_SCHEMA in section
    assert "INTERFACE_VERSION" in section
    assert INTERFACE_VERSION in section
    assert (REPO_ROOT / "backends" / "interface.py").is_file()
    assert _line_count(GUIDE) > 0
