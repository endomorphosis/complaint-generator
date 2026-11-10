"""CIMP-SEA-10: bounded corpus lookup is defined on the sibling module."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER = REPO_ROOT / "integrations/ipfs_datasets/legal.py"
SIBLING = REPO_ROOT / "integrations/ipfs_datasets/legal_corpus.py"
OWNER_MAX = 5100
SIBLING_MIN = 800
MOVED = (
    "lookup_bounded_legal_corpus",
    "build_bounded_legal_acquisition_request",
    "constrain_assertions_to_corpus",
    "handoff_acquired_legal_sources",
)
SENTINELS = ("search_state_laws",)
REEXPORT = (
    "from .legal_corpus import lookup_bounded_legal_corpus, "
    "build_bounded_legal_acquisition_request, constrain_assertions_to_corpus, "
    "handoff_acquired_legal_sources"
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
        if node.level != 1 or node.module != "legal_corpus":
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
    owner_functions = _module_functions(_parse(OWNER))
    sibling_functions = _module_functions(_parse(SIBLING))
    for name in SENTINELS:
        assert name in owner_functions, name
        assert name not in sibling_functions, name
        assert len(owner_functions[name].body) > 1, name
