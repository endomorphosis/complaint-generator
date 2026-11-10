"""CIMP-SEA-12: chronology helpers live in formal_document_chronology."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER = REPO_ROOT / "mediator/formal_document.py"
SIBLING = REPO_ROOT / "mediator/formal_document_chronology.py"
OWNER_MAX = 2200
SIBLING_MIN = 280
MOVED = (
    "_build_claim_chronology_support",
    "_build_anchored_chronology_summary",
    "_build_claim_reasoning_temporal_fallbacks",
    "_formalize_allegation_fragment",
)
SENTINEL_CLASS = "ComplaintDocumentBuilder"
SENTINEL = "_build_claims"
REEXPORT = (
    "from .formal_document_chronology import _build_claim_chronology_support, "
    "_build_anchored_chronology_summary, _build_claim_reasoning_temporal_fallbacks, "
    "_formalize_allegation_fragment"
)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _module_functions(tree: ast.AST) -> dict:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _class_methods(tree: ast.AST, class_name: str) -> dict:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                item.name: item
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    return {}


def _reexport(tree: ast.AST) -> ast.ImportFrom | None:
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level != 1 or node.module != "formal_document_chronology":
            continue
        imported = tuple(alias.name for alias in node.names)
        if imported == MOVED:
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
    for node in owner.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.lineno < reexport.lineno
    for name in MOVED:
        assert name not in owner_functions, name
        function = sibling_functions[name]
        assert function.decorator_list == [], name
        assert len(function.body) > 1, name


def test_sentinel_stays_defined_in_the_owner() -> None:
    owner = _parse(OWNER)
    sibling = _parse(SIBLING)
    methods = _class_methods(owner, SENTINEL_CLASS)
    sibling_functions = _module_functions(sibling)
    sibling_methods = _class_methods(sibling, SENTINEL_CLASS)
    assert SENTINEL in methods
    assert SENTINEL not in sibling_functions
    assert SENTINEL not in sibling_methods
    assert len(methods[SENTINEL].body) > 1
