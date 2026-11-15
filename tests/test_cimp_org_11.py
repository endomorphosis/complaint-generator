"""CIMP-ORG-11: owner-currency sibling table and line floors."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER_NOTE = REPO_ROOT / "docs/architecture/owner_currency.md"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
OWNER_ROWS = (
    ("complaint_phases/denoiser_answer.py", "complaint_phases/denoiser.py", 1800),
    ("integrations/ipfs_datasets/temporal_reasoning.py", "integrations/ipfs_datasets/logic.py", 550),
    ("mediator/legal_authority_search.py", "mediator/legal_authority_hooks.py", 560),
    ("complaint_phases/knowledge_graph_build.py", "complaint_phases/knowledge_graph.py", 700),
    ("integrations/private_storage_legacy.py", "integrations/private_storage.py", 450),
)
LINKED_MAPS = (
    "docs/architecture/current_layout.md",
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


def test_owner_table_lists_the_five_siblings_in_order() -> None:
    text = OWNER_NOTE.read_text(encoding="utf-8")
    expected = tuple((sibling, owner) for sibling, owner, _floor in OWNER_ROWS)
    assert _table_rows(text) == expected
    assert "INTERFACE_SCHEMA" in text
    assert INTERFACE_SCHEMA in text
    assert "INTERFACE_VERSION" in text
    assert INTERFACE_VERSION in text
    targets = [match.group(1) for match in _LINK.finditer(text)]
    for target in LINKED_MAPS:
        assert target in targets
        assert (REPO_ROOT / target).is_file()


def test_each_sibling_exists_and_meets_its_line_floor() -> None:
    for sibling, _owner, floor in OWNER_ROWS:
        path = REPO_ROOT / sibling
        assert path.is_file(), sibling
        assert _line_count(sibling) >= floor, sibling
