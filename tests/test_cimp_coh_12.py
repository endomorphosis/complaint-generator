"""CIMP-COH-12: the documentation index links the cohesive-move note."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = REPO_ROOT / "DOCUMENTATION_INDEX.md"
COHESIVE_NOTE = "docs/architecture/cohesive_moves.md"
STALE_STATISTICS = ("79+", "13 root-level", "61 docs/", "250+")
REQUIRED_SENTENCES = (
    "docs/archive/sessions",
    "docs/archive/reports",
    "root shims",
    "complaint-generator/module-interface@1",
    "1.0.0",
)
KEPT_LINKS = (
    "docs/architecture/consolidation_modules.md",
    "docs/architecture/module_boundaries.md",
    "docs/architecture/module_seams.md",
    "docs/architecture/current_layout.md",
    "docs/architecture/owner_currency.md",
)
ROOT_MARKDOWN = (
    "README.md",
    "DOCUMENTATION_INDEX.md",
    "CONTRIBUTING.md",
    "TESTING.md",
    "TODO.md",
)
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def index_lines() -> list[str]:
    """Return index lines using splitlines(), the repository line count."""
    return INDEX_PATH.read_text(encoding="utf-8").splitlines()


def index_text() -> str:
    return "\n".join(index_lines()) + "\n"


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


def test_index_links_the_cohesive_move_note() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    ast.parse(source, filename=str(Path(__file__)))
    lines = index_lines()
    text = index_text()
    assert lines
    assert len(lines) == len(INDEX_PATH.read_text(encoding="utf-8").splitlines())
    for stale in STALE_STATISTICS:
        assert stale not in text
    for sentence in REQUIRED_SENTENCES:
        assert sentence in text
    targets = markdown_link_targets(text)
    cohesive_hits = [target for target in targets if target == COHESIVE_NOTE]
    assert cohesive_hits == [COHESIVE_NOTE]
    assert (REPO_ROOT / COHESIVE_NOTE).is_file()
    for link in KEPT_LINKS:
        assert f"]({link})" in text
        assert (REPO_ROOT / link).is_file()
    root_markdown = tuple(sorted(path.name for path in REPO_ROOT.glob("*.md") if path.is_file()))
    assert root_markdown == tuple(sorted(ROOT_MARKDOWN))
