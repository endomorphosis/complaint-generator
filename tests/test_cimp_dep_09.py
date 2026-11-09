"""CIMP-DEP-09: intake open-item builders live in intake_case_open_items."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER = REPO_ROOT / 'complaint_phases/intake_case_file.py'
SIBLING = REPO_ROOT / 'complaint_phases/intake_case_open_items.py'
EXTRACTED = (
    'build_open_items',
    'build_blocker_follow_up_summary',
    'build_temporal_issue_registry',
    'build_claim_temporal_graphs',
)
SENTINEL = 'refresh_intake_case_file'
OWNER_MAX = 3700
SIBLING_MIN = 950
STEM = 'intake_case_open_items'


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
