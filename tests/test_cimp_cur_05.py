"""CIMP-CUR-05: architecture overview names current UI, HTTP, and planner modules."""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE = REPO_ROOT / "docs/ARCHITECTURE.md"
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

STALE_SIZES = (
    "10,852 lines",
    "7,881 lines",
    "6,933 lines",
    "5,691 lines",
    "5,562 lines",
    "5,309 lines",
)
FUTURE_PHRASES = (
    "Browser-based UI (future)",
    "RESTful API for integrations (future)",
)
OLD_TASKBOARD = "docs/REFACTOR_SUPERVISOR_TASKBOARD.md"
PLAN_COMPILER = "integrations/ipfs_" + "acc" + "elerate/improvement_plan.py"
_SIZE = re.compile(r"^\| `([^`]+)` \| (\d+) lines \|")


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    end = text.index("\n### ", start + 1)
    return text[start:end]


def _lines(relative: str) -> int:
    return len((REPO_ROOT / relative).read_text(encoding="utf-8").splitlines())


def test_layer1_names_dashboard_and_http_modules() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    for phrase in FUTURE_PHRASES:
        assert phrase not in text
    layer = _section(text, "### Layer 1: User Interface")
    assert "applications/dashboard_ui.py" in layer
    assert "applications/dashboard_hub.py" in layer
    assert "applications/server.py" in layer
    assert "applications/case_routes.py" in layer
    assert "browser UI" in layer
    assert "HTTP API" in layer
    for relative in (
        "applications/dashboard_ui.py",
        "applications/dashboard_hub.py",
        "applications/server.py",
        "applications/case_routes.py",
    ):
        assert (REPO_ROOT / relative).is_file()


def test_supervisor_row_points_at_the_plan_compiler() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    assert OLD_TASKBOARD not in text
    rows = [
        line
        for line in text.splitlines()
        if "scripts/refactor_agent_supervisor.py" in line and line.startswith("|")
    ]
    assert len(rows) == 1
    row = rows[0]
    assert "older operator script" in row
    assert PLAN_COMPILER in row
    assert (REPO_ROOT / "scripts/refactor_agent_supervisor.py").is_file()
    assert (REPO_ROOT / PLAN_COMPILER).is_file()


def test_extraction_priorities_match_splitlines() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    for stale in STALE_SIZES:
        assert stale not in text
    section = _section(text, "### Current Extraction Priorities")
    rows = [match.groups() for match in (_SIZE.match(line) for line in section.splitlines()) if match]
    found = {path: int(count) for path, count in rows}
    assert "applications/dashboard_hub.py" in found
    assert found
    for path, count in found.items():
        assert count == _lines(path), path
