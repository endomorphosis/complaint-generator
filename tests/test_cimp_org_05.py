"""CIMP-ORG-05: legacy private-storage migration lives in the sibling module."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER = REPO_ROOT / "integrations/private_storage.py"
SIBLING = REPO_ROOT / "integrations/private_storage_legacy.py"
OWNER_MAX = 8100
SIBLING_MIN = 450
MOVED = (
    "_legacy_hook_migration",
    "delete_private_case",
    "reconstruct_workflow_continuity",
)
SENTINELS = ("publish_case_manifest",)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _defined(tree: ast.AST) -> dict:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _legacy_import(tree: ast.AST) -> ast.ImportFrom | None:
    found = None
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module == "private_storage_legacy":
            found = node
    return found


def test_moved_functions_are_defined_only_in_the_sibling() -> None:
    owner_text = OWNER.read_text(encoding="utf-8")
    sibling_text = SIBLING.read_text(encoding="utf-8")
    assert len(owner_text.splitlines()) <= OWNER_MAX
    assert len(sibling_text.splitlines()) >= SIBLING_MIN
    owner = _parse(OWNER)
    sibling = _parse(SIBLING)
    owner_defined = _defined(owner)
    sibling_defined = _defined(sibling)
    imported = _legacy_import(owner)
    assert imported is not None
    assert imported is owner.body[-1]
    imported_names = [alias.name for alias in imported.names]
    assert imported_names == list(MOVED)
    for name in MOVED:
        assert name not in owner_defined, name
        function = sibling_defined[name]
        assert function.decorator_list == [], name
        assert len(function.body) > 1, name


def test_publish_case_manifest_stays_defined_in_the_owner() -> None:
    owner_defined = _defined(_parse(OWNER))
    sibling_defined = _defined(_parse(SIBLING))
    for name in SENTINELS:
        assert name in owner_defined, name
        assert name not in sibling_defined, name
        assert len(owner_defined[name].body) > 1, name
