"""CIMP-COH-04: intake temporal registry builders live in the temporal sibling."""

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
_PHASES = "complaint_" + "phases"
_OWNER_STEM = "intake_case_" + "file"
_SIBLING_STEM = "intake_case_" + "temporal"
OWNER = REPO_ROOT / _PHASES / (_OWNER_STEM + ".py")
SIBLING = REPO_ROOT / _PHASES / (_SIBLING_STEM + ".py")
EXTRACTED = (
    "build_temporal_relation_registry",
    "_build_temporal_graph_record",
    "build_timeline_consistency_summary",
    "_parse_single_temporal_expression",
    "_enrich_canonical_facts_with_relative_anchor_dates",
)
SENTINEL = "refresh_intake_case_file"
OWNER_MAX = 3010
SIBLING_MIN = 540
STEM = _SIBLING_STEM


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _defined(tree: ast.AST) -> dict:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _imported(tree: ast.AST) -> set:
    names = set()
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level != 1 or node.col_offset != 0 or node.module != STEM:
            continue
        names.update(alias.name for alias in node.names)
    return names


def test_owner_reexports_moved_temporal_functions() -> None:
    owner_text = OWNER.read_text(encoding="utf-8")
    sibling_text = SIBLING.read_text(encoding="utf-8")
    owner = _parse(OWNER)
    sibling = _parse(SIBLING)
    owner_defined = _defined(owner)
    sibling_defined = _defined(sibling)
    imported = _imported(owner)
    assert len(owner_text.splitlines()) <= OWNER_MAX
    assert len(sibling_text.splitlines()) >= SIBLING_MIN
    for name in EXTRACTED:
        assert name not in owner_defined, name
        assert name in sibling_defined, name
        assert name in imported, name
        assert len(sibling_defined[name].body) > 1, name
    assert SENTINEL in owner_defined
    assert len(owner_defined[SENTINEL].body) > 1
    assert SENTINEL not in sibling_defined
