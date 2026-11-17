"""CIMP-RDY-07: index and readme link the current release note."""

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX = REPO_ROOT / "DOCUMENTATION_INDEX.md"
README = REPO_ROOT / "README.md"
READINESS = "docs/architecture/release_readiness.md"
RELEASE = "docs" + "/" + "RELEASE.md"
KEPT_LINKS = (
    RELEASE,
    "docs/architecture/root_release.md",
    "docs/architecture/current_layout.md",
    "docs/architecture/owner_currency.md",
    "docs/architecture/cohesive_moves.md",
    "docs/architecture/consolidation_modules.md",
    "docs/architecture/module_boundaries.md",
    "docs/architecture/module_seams.md",
)
README_KEPT_LINKS = (
    RELEASE,
    "docs/architecture/current_layout.md",
    "docs/architecture/consolidation_modules.md",
    "docs/architecture/module_boundaries.md",
    "docs/architecture/module_seams.md",
)
STALE_STATISTICS = ("79+", "13 root-level", "61 docs/", "250+")
OLD_EXAMPLE_PHRASE = "23 example scripts"
NEW_EXAMPLE_PHRASE = "26 example scripts"
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
    marker = "]("
    while True:
        open_at = literal.find(marker, start)
        if open_at < 0:
            break
        close_at = literal.find(")", open_at + len(marker))
        targets.append(literal[open_at + len(marker) : close_at])
        start = close_at + 1
    return tuple(targets)


def test_index_and_readme_link_the_current_release_note() -> None:
    index = INDEX.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    assert len(index.splitlines()) > 0
    assert len(readme.splitlines()) > 0
    index_links = _links(index)
    readme_links = _links(readme)
    assert index_links.count(READINESS) == 1
    assert readme_links.count(READINESS) == 1
    assert (REPO_ROOT / READINESS).is_file()
    assert OLD_EXAMPLE_PHRASE not in index
    assert index.count(NEW_EXAMPLE_PHRASE) == 2
    for link in KEPT_LINKS:
        assert index_links.count(link) >= 1
        assert (REPO_ROOT / link).is_file()
    for link in README_KEPT_LINKS:
        assert readme_links.count(link) >= 1
    for stale in STALE_STATISTICS:
        assert stale not in index
        assert stale not in readme
    root_markdown = tuple(sorted(path.name for path in REPO_ROOT.glob("*.md") if path.is_file()))
    assert root_markdown == tuple(sorted(ROOT_MARKDOWN))


def test_this_module_has_no_skips() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert isinstance(tree, ast.Module)
    skip_names = {"skip", "importorskip", "xfail"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in skip_names:
            raise AssertionError(node.attr)
        if isinstance(node, ast.Name) and node.id in skip_names:
            raise AssertionError(node.id)
    marks = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets
        ):
            assert isinstance(node.value, ast.List)
            for element in node.value.elts:
                assert isinstance(element, ast.Attribute)
                marks.append(element.attr)
    assert marks == ["no_auto_llm", "no_auto_network", "no_auto_heavy"]
