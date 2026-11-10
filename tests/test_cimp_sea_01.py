"""CIMP-SEA-01: Mike handoff helpers delegate to complaint_workspace_mike."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER = REPO_ROOT / "applications/complaint_workspace.py"
SIBLING = REPO_ROOT / "applications/complaint_workspace_mike.py"
CLASS_NAME = "ComplaintWorkspaceService"
SENTINEL_CLASS = "ComplaintWorkspaceService"
SENTINELS = ("improve_draft",)
EXTRACTED = (
    "get_mike_integration_status",
    "_build_mike_submodule_inventory",
    "_build_mike_logic_review",
    "_build_mike_sync_diagnostics",
    "_check_mike_citation_links",
    "_normalize_mike_sync_provenance",
    "_build_mike_reasoning_predicates",
    "_summarize_mike_evidence_context",
)
OWNER_MAX = 16750
SIBLING_MIN = 450
QUALIFIER = "complaint_workspace_mike"


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _methods(tree: ast.AST, class_name: str) -> dict:
    klass = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return {
        node.name: node
        for node in klass.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _defined(tree: ast.AST) -> set:
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _imports_sibling(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level != 1:
            continue
        if node.module == QUALIFIER:
            return True
        if any(alias.name == QUALIFIER or alias.asname == QUALIFIER for alias in node.names):
            return True
    return False


def _sibling_function(tree: ast.AST, name: str):
    return next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )


def test_extracted_methods_delegate_with_one_return_call() -> None:
    owner_text = OWNER.read_text(encoding="utf-8")
    sibling_text = SIBLING.read_text(encoding="utf-8")
    owner = _parse(OWNER)
    sibling = _parse(SIBLING)
    methods = _methods(owner, CLASS_NAME)
    defined = _defined(sibling)
    assert len(owner_text.splitlines()) <= OWNER_MAX
    assert len(sibling_text.splitlines()) >= SIBLING_MIN
    assert _imports_sibling(owner)
    for name in EXTRACTED:
        assert name in defined, name
        function = _sibling_function(sibling, name)
        assert function.decorator_list == [], name
        assert len(function.body) > 1, name
        method = methods[name]
        assert len(method.body) == 1, name
        statement = method.body[0]
        assert isinstance(statement, ast.Return), name
        call = statement.value
        assert isinstance(call, ast.Call), name
        assert isinstance(call.func, ast.Attribute), name
        assert call.func.attr == name
        assert isinstance(call.func.value, ast.Name)
        assert call.func.value.id == QUALIFIER


def test_sentinels_stay_on_their_class() -> None:
    methods = _methods(_parse(OWNER), SENTINEL_CLASS)
    defined = _defined(_parse(SIBLING))
    for name in SENTINELS:
        assert name in methods, name
        assert name not in defined, name
        assert len(methods[name].body) > 1, name
