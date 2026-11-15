"""CIMP-CUR-04: separate current docs from historical plans in the index.

The documentation index must drop stale file and page counts, name the
root markdown set exactly, and keep historical plan links under one heading.
Every markdown link must resolve to a file in this checkout.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = REPO_ROOT / "DOCUMENTATION_INDEX.md"

STALE_STATISTICS = ("79+", "13 root-level", "61 docs/", "250+")
HISTORICAL_FRAGMENTS = (
    "IMPROVEMENT_PLAN",
    "EXECUTION_BACKLOG",
    "TASKLIST",
    "NEXT_BATCH",
    "FILE_WORKLIST",
)
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
ROOT_SET_SENTENCE = (
    "exactly README.md, DOCUMENTATION_INDEX.md, CONTRIBUTING.md, TESTING.md, and TODO.md"
)
HISTORICAL_HEADING = "## Historical plans"
STATISTICS_HEADING = "## Documentation Statistics"
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


def test_statistics_name_the_root_markdown_set_without_stale_counts() -> None:
    lines = index_lines()
    text = "\n".join(lines)
    assert lines, "DOCUMENTATION_INDEX.md is empty"
    assert len(lines) == len(INDEX_PATH.read_text(encoding="utf-8").splitlines())
    for stale in STALE_STATISTICS:
        assert stale not in text
    assert HISTORICAL_HEADING in text
    before, _after = text.split(HISTORICAL_HEADING, 1)
    for fragment in HISTORICAL_FRAGMENTS:
        assert fragment not in before
    for sentence in REQUIRED_SENTENCES:
        assert sentence in text
    for link in ARCHITECTURE_LINKS:
        assert f"]({link})" in text
        assert (REPO_ROOT / link).is_file()
    stats_at = text.index(STATISTICS_HEADING)
    next_heading = text.index("\n## ", stats_at + len(STATISTICS_HEADING))
    stats = text[stats_at:next_heading]
    assert ROOT_SET_SENTENCE in stats
    root_markdown = tuple(sorted(path.name for path in REPO_ROOT.glob("*.md")))
    assert root_markdown == tuple(sorted(ROOT_MARKDOWN))


def test_historical_plan_links_resolve_only_under_that_heading() -> None:
    text = index_text()
    _before, after = text.split(HISTORICAL_HEADING, 1)
    historical_targets = [
        target
        for target in markdown_link_targets(after)
        if any(fragment in target for fragment in HISTORICAL_FRAGMENTS)
    ]
    assert historical_targets, "historical plan links were removed instead of moved"
    for target in historical_targets:
        assert (REPO_ROOT / target).is_file(), target
    earlier_targets = markdown_link_targets(text.split(HISTORICAL_HEADING, 1)[0])
    leaked = [
        target
        for target in earlier_targets
        if any(fragment in target for fragment in HISTORICAL_FRAGMENTS)
    ]
    assert leaked == []


def test_every_markdown_link_in_the_index_resolves() -> None:
    text = index_text()
    targets = markdown_link_targets(text)
    assert targets
    missing = [
        target
        for target in targets
        if not (REPO_ROOT / target).resolve().is_file()
    ]
    assert missing == []
