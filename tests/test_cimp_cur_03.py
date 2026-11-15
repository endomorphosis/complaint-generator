"""CIMP-CUR-03: temporal predicate builders delegate to mediator_temporal."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER = REPO_ROOT / "mediator/mediator.py"
SIBLING = REPO_ROOT / "mediator/mediator_temporal.py"
CLASS_NAME = "Mediator"
SENTINELS = (
    "research_case_automatically",
    "get_claim_follow_up_plan",
    "get_support_timeline",
)
EXTRACTED = (
    "_build_temporal_next_actions_for_task",
    "_derive_missing_temporal_predicates",
    "_author_temporal_case_file_state",
    "_build_temporal_relation_formulas_by_id",
    "_build_timeline_anchor_ids_by_fact_id",
    "_is_temporal_rule_gap_follow_up",
    "_accumulate_temporal_rule_profile_counts",
    "_build_support_packet_timeline_drilldown",
    "_preferred_support_kind_for_temporal_rule_profile",
)
OWNER_MAX = 10750
SIBLING_MIN = 380
QUALIFIER = "mediator_temporal"


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
        receiver = call.args[0]
        assert isinstance(receiver, ast.Name)
        assert receiver.id == method.args.args[0].arg
        if any(isinstance(item, ast.Name) and item.id == "staticmethod" for item in method.decorator_list):
            assert receiver.id != "self", name
            assert receiver.id != "cls", name


def _implemented_statement_count(method: ast.AST) -> int:
    body = list(method.body)
    if len(body) == 1 and isinstance(body[0], ast.Try):
        handler_body = [statement for handler in body[0].handlers for statement in handler.body]
        body = list(body[0].body) + handler_body + list(body[0].orelse) + list(body[0].finalbody)
    return len(body)


def test_sentinels_stay_on_their_class() -> None:
    methods = _methods(_parse(OWNER), CLASS_NAME)
    defined = _defined(_parse(SIBLING))
    for name in SENTINELS:
        assert name in methods, name
        assert name not in defined, name
        method = methods[name]
        assert _implemented_statement_count(method) > 1, name
        assert not (
            len(method.body) == 1 and isinstance(method.body[0], ast.Return)
        ), name
