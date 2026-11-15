"""CIMP-CUR-10: the contribution guide links the current layout note."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUIDE_PATH = REPO_ROOT / "CONTRIBUTING.md"
CURRENT_LAYOUT = "docs/architecture/current_layout.md"
REQUIRED_SENTENCES = (
    "docs/archive/sessions",
    "docs/archive/reports",
    "root shims",
    "complaint-generator/module-interface@1",
    "1.0.0",
)
ARCHITECTURE_LINKS = (
    "docs/architecture/consolidation_modules.md",
    "docs/architecture/module_boundaries.md",
    "docs/architecture/module_seams.md",
)
ROOT_MARKDOWN = (
    "README.md",
    "DOCUMENTATION_INDEX.md",
    "CONTRIBUTING.md",
    "TESTING.md",
    "TODO.md",
)
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def guide_lines() -> list[str]:
    """Return guide lines using splitlines(), the repository line count."""
    return GUIDE_PATH.read_text(encoding="utf-8").splitlines()


def guide_text() -> str:
    return "\n".join(guide_lines()) + "\n"


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


def test_contribution_guide_links_the_current_layout() -> None:
    lines = guide_lines()
    text = "\n".join(lines)
    assert lines
    assert len(lines) == len(GUIDE_PATH.read_text(encoding="utf-8").splitlines())
    for sentence in REQUIRED_SENTENCES:
        assert sentence in text
    targets = markdown_link_targets(guide_text())
    assert targets.count(CURRENT_LAYOUT) == 1
    assert (REPO_ROOT / CURRENT_LAYOUT).is_file()
    for link in ARCHITECTURE_LINKS:
        assert link in targets
        assert (REPO_ROOT / link).is_file()
    root_markdown = tuple(sorted(path.name for path in REPO_ROOT.glob("*.md")))
    assert root_markdown == tuple(sorted(ROOT_MARKDOWN))
