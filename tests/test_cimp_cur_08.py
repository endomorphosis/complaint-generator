"""CIMP-CUR-08: applications guide names the versioned application entry."""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUIDE = REPO_ROOT / "docs/APPLICATIONS.md"
SECURITY = REPO_ROOT / "docs/SECURITY.md"
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

INTERFACE_MODULE = "applications.interface"
OWNERS = (
    "applications.server",
    "applications.case_routes",
    "applications.launcher",
)
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
HUB = "applications/dashboard_hub.py"
UI = "applications/dashboard_ui.py"
ROUTER = "create_dashboard_ui_router"
HEADING = "## Current entry"
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)")


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text[start + len(heading):]
    end = rest.find("\n## ")
    body = rest if end < 0 else rest[:end]
    return heading + body


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_current_entry_names_interface_owners_schema_and_hub_split() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    section = _section(text, HEADING)
    assert INTERFACE_MODULE in section
    for owner in OWNERS:
        assert owner in section
    assert "INTERFACE_SCHEMA" in section
    assert INTERFACE_SCHEMA in section
    assert "INTERFACE_VERSION" in section
    assert INTERFACE_VERSION in section
    assert HUB in section
    assert UI in section
    assert ROUTER in section
    hub_path = REPO_ROOT / HUB
    ui_path = REPO_ROOT / UI
    assert hub_path.is_file()
    assert ui_path.is_file()
    assert (REPO_ROOT / "applications/interface.py").is_file()
    assert _line_count(hub_path) > _line_count(ui_path)
    assert ROUTER in ui_path.read_text(encoding="utf-8")


def test_security_link_resolves() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    section = _section(text, HEADING)
    targets = [match.group(1) for match in LINK.finditer(section) if "SECURITY.md" in match.group(1)]
    assert targets
    for target in targets:
        resolved = (GUIDE.parent / target).resolve()
        assert resolved == SECURITY.resolve()
        assert resolved.is_file()
        assert _line_count(resolved) > 0
