"""CIMP-RLS-09: readme links the release note."""

import ast
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
RELEASE = "docs" + "/" + "RELEASE.md"
CURRENT_LAYOUT = "docs/architecture/current_layout.md"
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


def test_readme_links_release_note_and_keeps_root_markdown() -> None:
    text = README.read_text(encoding="utf-8")
    assert len(text.splitlines()) > 0
    targets = _links(text)
    assert targets.count(RELEASE) == 1
    assert CURRENT_LAYOUT in targets
    assert (REPO_ROOT / RELEASE).is_file()
    assert (REPO_ROOT / CURRENT_LAYOUT).is_file()
    root_markdown = tuple(sorted(path.name for path in REPO_ROOT.glob("*.md") if path.is_file()))
    assert root_markdown == tuple(sorted(ROOT_MARKDOWN))
    parsed = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    assert isinstance(parsed, ast.Module)
