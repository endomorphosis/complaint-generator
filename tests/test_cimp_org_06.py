"""CIMP-ORG-06: analysis readme names the versioned analysis entry."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "complaint_analysis" / "README.md"

INTERFACE_MODULE = "complaint_analysis.interface"
OWNERS = (
    "complaint_analysis.analyzer",
    "complaint_analysis.legal_patterns",
    "complaint_analysis.response_parsers",
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
    assert (REPO_ROOT / "complaint_analysis" / "interface.py").is_file()
