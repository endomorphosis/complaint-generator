"""CIMP-ORG-04: gap finding, merge, and text build delegate to knowledge_graph_build."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER = REPO_ROOT / "complaint_phases/knowledge_graph.py"
SIBLING = REPO_ROOT / "complaint_phases/knowledge_graph_build.py"
QUALIFIER = "knowledge_graph_build"
OWNER_MAX = 3120
SIBLING_MIN = 700

MOVED = (
    ("KnowledgeGraph", "find_gaps"),
    ("KnowledgeGraph", "merge_with"),
    ("KnowledgeGraphBuilder", "build_from_text"),
)
SENTINELS = ("record_answer_graph_revision",)


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


def _defined(tree: ast.AST) -> dict:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _sibling_import(tree: ast.AST) -> ast.ImportFrom | None:
    found = None
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module is None:
            names = [alias.name for alias in node.names]
            if names == [QUALIFIER]:
                found = node
    return found


def _assert_one_line_call(method: ast.FunctionDef, name: str) -> None:
    assert len(method.body) == 1, name
    statement = method.body[0]
    assert isinstance(statement, ast.Return), name
    call = statement.value
    assert isinstance(call, ast.Call), name
    assert isinstance(call.func, ast.Attribute), name
    assert call.func.attr == name
    assert isinstance(call.func.value, ast.Name)
    assert call.func.value.id == QUALIFIER
    assert call.args
    assert isinstance(call.args[0], ast.Name)
    assert call.args[0].id == method.args.args[0].arg


def test_named_methods_delegate_in_one_return() -> None:
    owner_text = OWNER.read_text(encoding="utf-8")
    sibling_text = SIBLING.read_text(encoding="utf-8")
    assert len(owner_text.splitlines()) <= OWNER_MAX
    assert len(sibling_text.splitlines()) >= SIBLING_MIN
    owner = _parse(OWNER)
    sibling = _parse(SIBLING)
    defined = _defined(sibling)
    owner_defined = _defined(owner)
    imported = _sibling_import(owner)
    assert imported is not None
    assert imported is owner.body[-1]
    import_line = owner_text.splitlines()[imported.lineno - 1]
    assert import_line == "from . import knowledge_graph_build"
    for node in owner.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assert node.lineno < imported.lineno
    for class_name, name in MOVED:
        methods = _methods(owner, class_name)
        _assert_one_line_call(methods[name], name)
        function = defined[name]
        assert function.decorator_list == [], name
        assert len(function.body) > 1, name
        assert name not in owner_defined


def test_record_answer_graph_revision_keeps_its_body() -> None:
    owner_defined = _defined(_parse(OWNER))
    sibling_defined = _defined(_parse(SIBLING))
    for name in SENTINELS:
        assert name in owner_defined, name
        assert name not in sibling_defined, name
        assert len(owner_defined[name].body) > 1, name
        statement = owner_defined[name].body[-1]
        returns_sibling = (
            isinstance(statement, ast.Return)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Attribute)
            and isinstance(statement.value.func.value, ast.Name)
            and statement.value.func.value.id == QUALIFIER
        )
        assert returns_sibling is False
