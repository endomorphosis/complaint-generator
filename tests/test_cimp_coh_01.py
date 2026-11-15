"""CIMP-COH-01: chronology and fact-entry assembly delegates to the chronology sibling."""

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
_OWNER_NAME = "document_" + "pipeline.py"
_SIBLING_STEM = "document_" + "pipeline_" + "chronology"
OWNER = REPO_ROOT / "complaint_phases" / _OWNER_NAME
SIBLING = REPO_ROOT / "complaint_phases" / (_SIBLING_STEM + ".py")
CLASS_NAME = "FormalComplaintDocumentBuilder"
SENTINEL_CLASS = "FormalComplaintDocumentBuilder"
SENTINELS = ("build_package",)
EXTRACTED = (
    "_collect_claim_fact_entries",
    "_build_claim_chronology_support",
    "_build_document_provenance_summary",
    "_collect_uploaded_evidence_fact_entries",
    "_build_chronology_blocker_summary",
    "_build_summary_fact_entries",
    "_merge_claim_support_policy_entries",
)
OWNER_MAX = 7300
SIBLING_MIN = 800
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
        assert _arg_names(function)[0] == "self", name
        assert len(function.body) > 1, name
        method = methods[name]
        assert method.decorator_list == [], name
        assert _arg_names(method) == _arg_names(function), name
        assert len(method.body) == 1, name
        statement = method.body[0]
        assert isinstance(statement, ast.Return), name
        call = statement.value
        assert isinstance(call, ast.Call), name
        assert isinstance(call.func, ast.Attribute), name
        assert call.func.attr == name
        assert isinstance(call.func.value, ast.Name)
        assert call.func.value.id == QUALIFIER
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
