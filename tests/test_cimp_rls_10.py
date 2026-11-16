"""CIMP-RLS-10: the documentation index links the release notes."""

import ast
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX = REPO_ROOT / "DOCUMENTATION_INDEX.md"
RELEASE = "docs" + "/" + "RELEASE.md"
ROOT_RELEASE = "docs/architecture/root_release.md"
KEPT_LINKS = (
    "docs/architecture/consolidation_modules.md",
    "docs/architecture/module_boundaries.md",
    "docs/architecture/module_seams.md",
    "docs/architecture/current_layout.md",
    "docs/architecture/owner_currency.md",
    "docs/architecture/cohesive_moves.md",
)
STALE_STATISTICS = ("79+", "13 root-level", "61 docs/", "250+")
ROOT_MARKDOWN = (
    "README.md",
    "DOCUMENTATION_INDEX.md",
    "CONTRIBUTING.md",
    "TESTING.md",
    "TODO.md",
)


def _links(text: str) -> tuple[str, ...]:
    tree = ast.parse(repr(text))
    literal = ast.literal_eval(tree.body[0].value)
    assert isinstance(literal, str)
    targets = []
    start = 0
    while True:
        open_at = literal.find("](", start)
        if open_at < 0:
            break
        close_at = literal.find(")", open_at + 2)
        targets.append(literal[open_at + 2 : close_at])
        start = close_at + 1
    return tuple(targets)


def test_index_links_release_notes_and_keeps_architecture_links() -> None:
    text = INDEX.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert len(lines) > 0
    targets = _links(text)
    assert targets.count(RELEASE) == 1
    assert targets.count(ROOT_RELEASE) == 1
    assert (REPO_ROOT / RELEASE).is_file()
    assert (REPO_ROOT / ROOT_RELEASE).is_file()
    for link in KEPT_LINKS:
        assert targets.count(link) >= 1
        assert (REPO_ROOT / link).is_file()
    assert "complaint-generator/module-interface@1" in text
    assert "INTERFACE_VERSION" in text
    assert "1.0.0" in text
    for stale in STALE_STATISTICS:
        assert stale not in text
    root_markdown = tuple(sorted(path.name for path in REPO_ROOT.glob("*.md") if path.is_file()))
    assert root_markdown == tuple(sorted(ROOT_MARKDOWN))
    parsed = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    assert isinstance(parsed, ast.Module)
