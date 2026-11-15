"""CIMP-COH-11: cohesive-move sibling table and line floors."""

import ast
import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
NOTE = REPO_ROOT / "docs" / "architecture" / "cohesive_moves.md"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
_PHASES = "complaint_phases"
_HARNESS = "adversarial_harness"
_MEDIATOR = "mediator"
_DATASETS = "integrations" + "/" + "ipfs_datasets"
ROWS = (
    (
        _PHASES + "/" + "document_" + "pipeline_" + "chronology.py",
        _PHASES + "/" + "document_" + "pipeline.py",
        800,
    ),
    (
        _HARNESS + "/" + "optimizer_" + "workflow.py",
        _HARNESS + "/" + "optimizer.py",
        800,
    ),
    (
        _MEDIATOR + "/" + "claim_" + "support_" + "retrieval.py",
        _MEDIATOR + "/" + "claim_" + "support_" + "hooks.py",
        650,
    ),
    (
        _PHASES + "/" + "intake_" + "case_" + "temporal.py",
        _PHASES + "/" + "intake_" + "case_" + "file.py",
        540,
    ),
    (
        _DATASETS + "/" + "canonical_" + "formalization.py",
        _DATASETS + "/" + "logic.py",
        700,
    ),
    (
        _PHASES + "/" + "document_" + "optimization_" + "guidance.py",
        _PHASES + "/" + "document_" + "optimization.py",
        720,
    ),
)
LINKED_MAPS = (
    "docs/architecture/current_layout.md",
    "docs/architecture/owner_currency.md",
    "docs/architecture/consolidation_modules.md",
    "docs/architecture/module_boundaries.md",
    "docs/architecture/module_seams.md",
)
_ROW = re.compile(r"^\| `([^`]+)` \| `([^`]+)` \|$")
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _table_rows(text: str) -> tuple[tuple[str, str], ...]:
    separators = [line for line in text.splitlines() if line.startswith("| ---")]
    assert separators == ["| --- | --- |"]
    rows = [match.groups() for match in (_ROW.match(line) for line in text.splitlines()) if match]
    return tuple(rows)


def _line_count(relative: str) -> int:
    return len((REPO_ROOT / relative).read_text(encoding="utf-8").splitlines())


def test_note_lists_the_six_siblings_in_order() -> None:
    text = NOTE.read_text(encoding="utf-8")
    expected = tuple((sibling, owner) for sibling, owner, _floor in ROWS)
    assert _table_rows(text) == expected
    assert "INTERFACE_SCHEMA" in text
    assert INTERFACE_SCHEMA in text
    assert "INTERFACE_VERSION" in text
    assert INTERFACE_VERSION in text
    targets = [match.group(1) for match in _LINK.finditer(text)]
    assert targets == list(LINKED_MAPS)
    for target in LINKED_MAPS:
        assert (REPO_ROOT / target).is_file()


def test_each_sibling_exists_parses_and_meets_its_line_floor() -> None:
    for sibling, _owner, floor in ROWS:
        path = REPO_ROOT / sibling
        assert path.is_file(), sibling
        source = path.read_text(encoding="utf-8")
        assert len(source.splitlines()) >= floor, sibling
        ast.parse(source, filename=str(path))
