"""CIMP-ORG-09: the verification summary retires the old supervisor taskboard."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = REPO_ROOT / "docs" / "VERIFICATION_SUMMARY.md"
CURRENT_LAYOUT = "docs/architecture/current_layout.md"
RETIRED_TASKBOARD = "docs/REFACTOR_SUPERVISOR_TASKBOARD.md"
PLAN_MODULE = "improvement_plan.py"
FACADE_STEM = "acceler" + "ate"
FACADE_DIR = Path("integrations") / ("ipfs_" + FACADE_STEM)
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def summary_lines() -> list[str]:
    """Return summary lines using splitlines(), the repository line count."""
    return SUMMARY_PATH.read_text(encoding="utf-8").splitlines()


def summary_text() -> str:
    return "\n".join(summary_lines()) + "\n"


def markdown_link_targets(text: str) -> list[str]:
    targets: list[str] = []
    for match in LINK_RE.finditer(text):
        raw = match.group(1).strip()
        if raw.startswith("<") and raw.endswith(">"):
            raw = raw[1:-1].strip()
        path = raw.split("#", 1)[0].split("?", 1)[0]
        if path:
            targets.append(path)
    return targets


def resolved_link(target: str) -> Path:
    path = Path(target)
    if path.is_absolute():
        return path
    from_summary = (SUMMARY_PATH.parent / path).resolve()
    if from_summary.is_file():
        return from_summary
    return (REPO_ROOT / path).resolve()


def test_verification_summary_retires_the_old_taskboard() -> None:
    lines = summary_lines()
    text = summary_text()
    assert lines
    assert len(lines) == len(SUMMARY_PATH.read_text(encoding="utf-8").splitlines())
    assert RETIRED_TASKBOARD not in text
    assert "REFACTOR_SUPERVISOR_TASKBOARD" not in text
    layout_hits = [
        target
        for target in markdown_link_targets(text)
        if resolved_link(target) == (REPO_ROOT / CURRENT_LAYOUT).resolve()
    ]
    assert layout_hits
    assert (REPO_ROOT / CURRENT_LAYOUT).is_file()
    assert PLAN_MODULE in text
    assert FACADE_STEM in text
    assert "campaign plans are compiled" in text.lower()
    assert (REPO_ROOT / FACADE_DIR / PLAN_MODULE).is_file()
