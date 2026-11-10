"""CIMP-SEA-13: encrypted workspace transfer lives in private_workspace_transfer."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER = REPO_ROOT / "integrations/private_storage.py"
SIBLING = REPO_ROOT / "integrations/private_workspace_transfer.py"
OWNER_MAX = 9200
SIBLING_MIN = 400
MOVED = (
    "import_encrypted_workspace",
    "restore_encrypted_workspace",
    "commit_private_revision",
    "recover_private_revision",
)
SENTINEL = "publish_case_manifest"
OWNER_CLASS = "UserOwnedKeySession"
REEXPORT = (
    "from .private_workspace_transfer import import_encrypted_workspace, "
    "restore_encrypted_workspace, commit_private_revision, recover_private_revision"
)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _module_functions(tree: ast.AST) -> dict:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _classes(tree: ast.AST) -> dict:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }


def _reexport(tree: ast.AST) -> ast.ImportFrom | None:
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level != 1 or node.module != "private_workspace_transfer":
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
    owner_functions = _module_functions(owner)
    sibling_functions = _module_functions(sibling)
    assert SENTINEL in owner_functions
    assert SENTINEL not in sibling_functions
    assert len(owner_functions[SENTINEL].body) > 1
    owner_classes = _classes(owner)
    sibling_classes = _classes(sibling)
    assert OWNER_CLASS in owner_classes
    assert OWNER_CLASS not in sibling_classes
    assert owner_classes[OWNER_CLASS].body
