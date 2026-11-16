"""CIMP-RLS-01: document review assembly is defined on the review sibling."""

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
_SIBLING_STEM = "document_" + "review"
OWNER = REPO_ROOT / "applications" / ("document_" + "api.py")
SIBLING = REPO_ROOT / "applications" / (_SIBLING_STEM + ".py")
OWNER_MAX = 1392
SIBLING_MIN = 921
MOVED = (
    "_build_document_review_workflow_phase_priority",
    "_build_document_review_workflow_priority",
    "_build_document_builder_summary",
    "_annotate_review_links",
)
SENTINELS = ("create_document_router", "project_complaint_outline")
REEXPORT = (
    "from ."
    + _SIBLING_STEM
    + " import _build_document_review_workflow_phase_priority, "
    "_build_document_review_workflow_priority, "
    "_build_document_builder_summary, "
    "_annotate_review_links"
)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _module_functions(tree: ast.AST) -> dict:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _reexport(tree: ast.AST) -> ast.ImportFrom | None:
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level != 1 or node.module != _SIBLING_STEM:
            continue
        imported = tuple(alias.name for alias in node.names)
        if imported == MOVED and node.col_offset == 0:
            return node
    return None


def test_moved_functions_live_only_on_the_sibling() -> None:
    owner_text = OWNER.read_text(encoding="utf-8")
    sibling_text = SIBLING.read_text(encoding="utf-8")
    assert len(owner_text.splitlines()) <= OWNER_MAX
    assert len(sibling_text.splitlines()) >= SIBLING_MIN
    assert REEXPORT in owner_text
    owner = _parse(OWNER)
    sibling = _parse(SIBLING)
    owner_functions = _module_functions(owner)
    sibling_functions = _module_functions(sibling)
    reexport = _reexport(owner)
    assert reexport is not None
    for name in MOVED:
        assert name not in owner_functions, name
        function = sibling_functions[name]
        assert function.decorator_list == [], name
        assert len(function.body) > 1, name


def test_sentinels_stay_defined_in_the_owner() -> None:
    owner_functions = _module_functions(_parse(OWNER))
    sibling_functions = _module_functions(_parse(SIBLING))
    for name in SENTINELS:
        assert name in owner_functions, name
        assert name not in sibling_functions, name
        assert len(owner_functions[name].body) > 1, name
