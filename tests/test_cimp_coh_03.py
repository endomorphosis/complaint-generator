"""CIMP-COH-03: retrieval sessions and proof cards delegate to the retrieval sibling."""

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
_OWNER_NAME = "claim_" + "support_" + "hooks.py"
_SIBLING_STEM = "claim_" + "support_" + "retrieval"
OWNER = REPO_ROOT / "mediator" / _OWNER_NAME
SIBLING = REPO_ROOT / "mediator" / (_SIBLING_STEM + ".py")
CLASS_NAME = "ClaimSupportHook"
SENTINEL_CLASS = "ClaimSupportHook"
SENTINELS = ("upsert_support_link",)
STAY = (
    "_build_temporal_next_actions",
    "_initialize_schema",
    "_enrich_support_link",
)
INSTANCE = (
    "get_element_proof_card",
    "get_formal_validation_report",
    "run_retrieval_session",
    "_build_retrieval_ranking_payload",
    "_build_validation_decision_trace",
)
EXTRACTED = INSTANCE
OWNER_MAX = 7100
SIBLING_MIN = 650
QUALIFIER = _SIBLING_STEM


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
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.level != 1 or node.col_offset != 0:
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


def _arg_names(node: ast.FunctionDef) -> list:
    return [arg.arg for arg in node.args.args]


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
    for name in INSTANCE:
        function = _sibling_function(sibling, name)
        method = methods[name]
        assert method.decorator_list == [], name
        assert _arg_names(function)[0] == "self", name
        assert _arg_names(method) == _arg_names(function), name
        call = method.body[0].value
        assert call.args, name
        assert isinstance(call.args[0], ast.Name)
        assert call.args[0].id == "self"


def test_sentinels_stay_on_their_class() -> None:
    methods = _methods(_parse(OWNER), SENTINEL_CLASS)
    defined = _defined(_parse(SIBLING))
    for name in SENTINELS:
        assert name in methods, name
        assert name not in defined, name
        assert len(methods[name].body) > 1, name
    for name in STAY:
        assert name in methods, name
        assert name not in defined, name
