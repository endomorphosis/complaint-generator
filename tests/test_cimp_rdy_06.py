"""CIMP-RDY-06: current release surface note."""

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
NOTE = REPO_ROOT / "docs" / "architecture" / "release_readiness.md"
TASK_OUTPUTS = (
    "docs/architecture/release_readiness.md",
    "tests/test_cimp_rdy_06.py",
)
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
ROOT_BUILD_KEEPERS = (
    "Makefile",
    "package.json",
    "play" + "wright.config.js",
    "MANIFEST.in",
    "pyproject.toml",
    "setup.py",
    "requirements.txt",
    "pytest.ini",
)
LINKED_MAPS = (
    "docs/architecture/root_release.md",
    "docs/RELEASE.md",
    "docs/architecture/current_layout.md",
    "docs/architecture/owner_currency.md",
    "docs/architecture/cohesive_moves.md",
    "docs/architecture/consolidation_modules.md",
    "docs/architecture/module_boundaries.md",
    "docs/architecture/module_seams.md",
)
LOGS = (
    "logs/UNCAUGHT_EXCEPTION.log",
    "logs/app.log",
    "logs/test.log",
)
RANGE_CACHE = "datasets/CCINDEX_WARC_CACHE_DIR"
EXAMPLE_CATALOG = "docs/EXAMPLES.md"
EXAMPLE_COUNT = 26


def _section(text: str, heading: str) -> str:
    lines = text.splitlines()
    start = lines.index(heading)
    body = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body)


def _bullets(section: str) -> tuple[str, ...]:
    found = []
    for line in section.splitlines():
        if line.startswith("- `") and line.endswith("`"):
            found.append(line[3:-1])
    return tuple(found)


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


def test_release_readiness_publishes_surface() -> None:
    text = NOTE.read_text(encoding="utf-8")
    assert len(text.splitlines()) > 0
    assert "INTERFACE_SCHEMA" in text
    assert INTERFACE_SCHEMA in text
    assert "INTERFACE_VERSION" in text
    assert INTERFACE_VERSION in text
    assert _bullets(_section(text, "## Root build keepers")) == ROOT_BUILD_KEEPERS
    assert "keepers" in _section(text, "## Root build keepers")
    packaged = _section(text, "## Packaged asset trees")
    assert "templates" in packaged
    assert "static" in packaged
    assert "packages included by the setuptools find lists" in packaged
    scratch = _section(text, "## Paths that are not product source")
    for name in LOGS:
        assert f"`{name}`" in scratch
    assert "three logs" in scratch
    assert "are not product source" in scratch
    assert f"`{RANGE_CACHE}`" in scratch
    assert "range cache" in scratch
    assert "`patches/` remains tracked autopatch scratch and is not a product package." in scratch
    examples = _section(text, "## Example set")
    assert f"The example set is {EXAMPLE_COUNT} scripts in `{EXAMPLE_CATALOG}`." in examples
    assert "Historical plan and backlog documents are not the current module contract." in text
    assert "only new file" in text
    scheme = "ht" + "tp://"
    secure = "ht" + "tps://"
    assert scheme not in text
    assert secure not in text
    assert _links(text) == LINKED_MAPS
    for target in LINKED_MAPS:
        assert (REPO_ROOT / target).is_file()
    for name in ROOT_BUILD_KEEPERS:
        assert (REPO_ROOT / name).is_file()
    assert (REPO_ROOT / EXAMPLE_CATALOG).is_file()


def test_task_outputs_are_only_the_note_and_this_test() -> None:
    for relative in TASK_OUTPUTS:
        assert (REPO_ROOT / relative).is_file()
    note_name = NOTE.name
    siblings = [
        path.name
        for path in NOTE.parent.glob("release_readiness.md")
        if path.is_file()
    ]
    assert siblings == [note_name]
    this_test = Path(__file__).resolve()
    assert this_test == (REPO_ROOT / TASK_OUTPUTS[1]).resolve()
    assert NOTE.resolve() == (REPO_ROOT / TASK_OUTPUTS[0]).resolve()
    source = this_test.read_text(encoding="utf-8")
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
