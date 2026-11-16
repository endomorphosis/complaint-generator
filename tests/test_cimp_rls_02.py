"""CIMP-RLS-02: intake timeline updates live on the timeline sibling."""

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
_SIBLING_STEM = "dependency_graph_" + "timeline"
OWNER = REPO_ROOT / "complaint_phases" / "dependency_graph.py"
SIBLING = REPO_ROOT / "complaint_phases" / (_SIBLING_STEM + ".py")
OWNER_MAX = 2220
SIBLING_MIN = 504
MOVED = (
    "sync_intake_timeline_to_graph",
    "add_fact_rule_link",
    "apply_retrieval_nomination",
    "invalidate_factual_dependents",
    "apply_derived_dependency_requirements",
)
SENTINEL_CLASS = "DependencyGraph"
SENTINEL = "_optimize_blocker_issues_for_actor_critic"
OWNER_CLASS = "DependencyGraphBuilder"


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class_methods(tree: ast.AST, class_name: str) -> dict:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                item.name: item
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    return {}


def _module_functions(tree: ast.AST) -> dict:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _sibling_import(tree: ast.AST) -> ast.ImportFrom | None:
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        imported = tuple(alias.name for alias in node.names)
        if (
            node.level == 1
            and node.module is None
            and imported == (_SIBLING_STEM,)
            and node.col_offset == 0
        ):
            return node
    return None


def _is_single_return_call(function: ast.AST, name: str) -> bool:
    if len(function.body) != 1 or not isinstance(function.body[0], ast.Return):
        return False
    call = function.body[0].value
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != name:
        return False
    if not isinstance(func.value, ast.Name) or func.value.id != _SIBLING_STEM:
        return False
    if not call.args or not isinstance(call.args[0], ast.Name) or call.args[0].id != "self":
        return False
    return True


def test_timeline_methods_delegate_to_the_sibling() -> None:
    owner_text = OWNER.read_text(encoding="utf-8")
    sibling_text = SIBLING.read_text(encoding="utf-8")
    assert len(owner_text.splitlines()) <= OWNER_MAX
    assert len(sibling_text.splitlines()) >= SIBLING_MIN
    owner = _parse(OWNER)
    sibling = _parse(SIBLING)
    assert _sibling_import(owner) is not None
    methods = _class_methods(owner, OWNER_CLASS)
    functions = _module_functions(sibling)
    for name in MOVED:
        method = methods[name]
        assert method.decorator_list == [], name
        assert _is_single_return_call(method, name), name
        function = functions[name]
        assert function.decorator_list == [], name
        assert function.args.args and function.args.args[0].arg == "self", name
        assert len(function.body) > 1, name


def test_blocker_optimizer_stays_on_the_owner() -> None:
    owner = _parse(OWNER)
    sibling = _parse(SIBLING)
    methods = _class_methods(owner, SENTINEL_CLASS)
    assert SENTINEL in methods
    assert len(methods[SENTINEL].body) > 1
    assert SENTINEL not in _module_functions(sibling)
    assert SENTINEL not in _class_methods(owner, OWNER_CLASS)
