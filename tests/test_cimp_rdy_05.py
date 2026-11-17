"""CIMP-RDY-05: example catalog matches the tracked example scripts."""

import ast
import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "docs" / "EXAMPLES.md"
EXAMPLES_DIR = REPO_ROOT / "examples"
TRACKED_COUNT = 26
CATEGORY_COUNTS = (7, 5, 9, 5)
CATEGORY_TITLES = (
    "Core System Examples",
    "Complaint Analysis Examples",
    "Adversarial Testing Examples",
    "Advanced Examples",
)
_BACKTICK = "`"
_PY_NAME = re.compile(_BACKTICK + r"([A-Za-z0-9_]+\.py)" + _BACKTICK)
_OVERVIEW_COUNT = re.compile(r"\((\d+)\)")
_TABLE_COUNT = re.compile(r"^\| \*\*[^*]+\*\* \| (\d+) \|", re.MULTILINE)


def _catalog_text() -> str:
    text = CATALOG_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert len(lines) == len(text.splitlines())
    return text


def _quoted_python_names(text: str) -> list[str]:
    return _PY_NAME.findall(text)


def _tracked_example_names() -> set[str]:
    return {path.name for path in EXAMPLES_DIR.glob("*.py") if path.is_file()}


def _section_bodies(text: str) -> dict[str, str]:
    bodies: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            bodies[current] = []
            continue
        if current is not None:
            bodies[current].append(line)
    return {title: "\n".join(lines) for title, lines in bodies.items()}


def _overview_counts(text: str) -> list[int]:
    overview = _section_bodies(text)["Overview"]
    return [int(value) for value in _OVERVIEW_COUNT.findall(overview)]


def test_backtick_names_match_tracked_examples() -> None:
    text = _catalog_text()
    quoted = _quoted_python_names(text)
    tracked = _tracked_example_names()
    assert len(quoted) == len(set(quoted)) == TRACKED_COUNT
    assert set(quoted) == tracked
    assert len(list(EXAMPLES_DIR.glob("*.py"))) == TRACKED_COUNT


def test_overview_and_category_counts_sum_to_tracked() -> None:
    text = _catalog_text()
    overview_counts = _overview_counts(text)
    table_counts = [int(value) for value in _TABLE_COUNT.findall(text)]
    assert overview_counts == list(CATEGORY_COUNTS)
    assert table_counts == list(CATEGORY_COUNTS)
    assert sum(overview_counts) == TRACKED_COUNT
    assert sum(table_counts) == TRACKED_COUNT

    bodies = _section_bodies(text)
    grouped: list[str] = []
    for title, expected in zip(CATEGORY_TITLES, CATEGORY_COUNTS, strict=True):
        names = _quoted_python_names(bodies[title])
        assert len(names) == len(set(names)) == expected
        grouped.extend(names)
    assert set(grouped) == _tracked_example_names()
    assert "22 example scripts" not in text
    assert "22 demonstration scripts" not in text


def test_module_pytestmark_has_required_marks() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    marks: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets):
            continue
        assert isinstance(node.value, ast.List)
        for element in node.value.elts:
            assert isinstance(element, ast.Attribute)
            assert isinstance(element.value, ast.Attribute)
            assert isinstance(element.value.value, ast.Name)
            assert element.value.value.id == "pytest"
            assert element.value.attr == "mark"
            marks.append(element.attr)
    assert marks == ["no_auto_llm", "no_auto_network", "no_auto_heavy"]
    for node in ast.walk(tree):
        assert not (isinstance(node, ast.Attribute) and node.attr in {"skip", "skipif"})
