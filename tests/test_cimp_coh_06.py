"""CIMP-COH-06: optimization guidance lives in the guidance sibling."""

import ast
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

REPO_ROOT = Path(__file__).resolve().parents[1]
_OWNER_STEM = "document_" + "optimization"
_SIBLING_STEM = _OWNER_STEM + "_guidance"
OWNER = REPO_ROOT / "complaint_phases" / (_OWNER_STEM + ".py")
SIBLING = REPO_ROOT / "complaint_phases" / (_SIBLING_STEM + ".py")
CLASS_NAME = "AgenticDocumentOptimizer"
MOVED = (
    "_heuristic_review",
    "_build_workflow_optimization_guidance",
    "_select_support_context",
    "_build_workflow_phase_targeting",
)
SENTINEL = "optimize_draft"
OWNER_MAX = 2920
SIBLING_MIN = 720


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class_methods(tree: ast.AST) -> dict:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == CLASS_NAME:
            return {
                item.name: item
                for item in node.body
                if isinstance(item, ast.FunctionDef)
            }
    return {}


def _module_functions(tree: ast.AST) -> dict:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }


def _sibling_import(tree: ast.AST) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level != 1 or node.col_offset != 0 or node.module not in {None, _SIBLING_STEM}:
            continue
        if any(alias.name == _SIBLING_STEM for alias in node.names):
            return True
    return False


def _single_return_call(fn: ast.FunctionDef) -> ast.Call:
    assert len(fn.body) == 1, fn.name
    statement = fn.body[0]
    assert isinstance(statement, ast.Return), fn.name
    assert isinstance(statement.value, ast.Call), fn.name
    returns = [node for node in ast.walk(fn) if isinstance(node, ast.Return)]
    assert len(returns) == 1, fn.name
    return statement.value


def test_optimization_guidance_methods_delegate_within_line_bounds() -> None:
    owner_text = OWNER.read_text(encoding="utf-8")
    sibling_text = SIBLING.read_text(encoding="utf-8")
    owner = _parse(OWNER)
    sibling = _parse(SIBLING)
    owner_methods = _class_methods(owner)
    sibling_functions = _module_functions(sibling)

    assert len(owner_text.splitlines()) <= OWNER_MAX
    assert len(sibling_text.splitlines()) >= SIBLING_MIN
    assert _sibling_import(owner)

    sentinel = owner_methods[SENTINEL]
    assert SENTINEL not in sibling_functions
    assert len(sentinel.body) > 1
    assert not sentinel.decorator_list

    for name in MOVED:
        method = owner_methods[name]
        function = sibling_functions[name]
        assert not method.decorator_list, name
        assert not function.decorator_list, name
        assert [arg.arg for arg in method.args.args] == [arg.arg for arg in function.args.args]
        assert method.args.args[0].arg == "self"
        assert [arg.arg for arg in method.args.kwonlyargs] == [arg.arg for arg in function.args.kwonlyargs]
        assert len(function.body) > 1, name
        call = _single_return_call(method)
        target = call.func
        assert isinstance(target, ast.Attribute), name
        assert isinstance(target.value, ast.Name) and target.value.id == _SIBLING_STEM, name
        assert target.attr == name
        assert [arg.id for arg in call.args if isinstance(arg, ast.Name)] == ["self"]
        assert len(call.args) == 1
        assert [keyword.arg for keyword in call.keywords] == [arg.arg for arg in method.args.kwonlyargs]
        assert not call.keywords or all(
            isinstance(keyword.value, ast.Name) and keyword.value.id == keyword.arg
            for keyword in call.keywords
        )
