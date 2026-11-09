"""CIMP-DEP-12: hook effect dispatch lives in hook_runtime_dispatch."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER = REPO_ROOT / 'mediator/hook_runtime.py'
SIBLING = REPO_ROOT / 'mediator/hook_runtime_dispatch.py'
EXTRACTED = (
    'dispatch_observed_hook_purpose',
    'accept_bound_hook_effect',
)
SENTINEL = 'dispatch_registered_hook_operation'
OWNER_MAX = 4000
SIBLING_MIN = 500
STEM = 'hook_runtime_dispatch'


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
        if isinstance(node, ast.ImportFrom) and node.module == STEM:
            names.update(alias.name for alias in node.names)
    return names


def test_owner_reexports_moved_functions() -> None:
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
