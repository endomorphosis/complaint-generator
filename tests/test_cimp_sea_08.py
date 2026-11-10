"""CIMP-SEA-08: document-generation fallback delegates to session_document_fallback."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER = REPO_ROOT / "adversarial_harness/session.py"
SIBLING = REPO_ROOT / "adversarial_harness/session_document_fallback.py"
QUALIFIER = "session_document_fallback"
OWNER_MAX = 3450
SIBLING_MIN = 320
EXTRACTED = (
    ("AdversarialSession", "_build_document_generation_fallback"),
    ("AdversarialSession", "_build_fallback_probe"),
    ("AdversarialSession", "_run_document_generation"),
    ("AdversarialSession", "_compact_document_generation_result"),
)
SENTINEL_CLASS = "AdversarialSession"
SENTINELS = ("run",)
STATICMETHODS = frozenset({"_compact_document_generation_result"})


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


def _imports_sibling(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level != 1:
            continue
        if node.module == QUALIFIER:
            return True
        if any(alias.name == QUALIFIER or alias.asname == QUALIFIER for alias in node.names):
            return True
    return False


def _decorator_names(method: ast.FunctionDef) -> list:
    names = []
    for dec in method.decorator_list:
        if isinstance(dec, ast.Name):
            names.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            names.append(dec.attr)
    return names


def test_extracted_methods_delegate_with_one_return_call() -> None:
    owner_text = OWNER.read_text(encoding="utf-8")
    sibling_text = SIBLING.read_text(encoding="utf-8")
    owner = _parse(OWNER)
    sibling = _parse(SIBLING)
    defined = _defined(sibling)
    assert len(owner_text.splitlines()) <= OWNER_MAX
    assert len(sibling_text.splitlines()) >= SIBLING_MIN
    assert _imports_sibling(owner)
    for class_name, name in EXTRACTED:
        methods = _methods(owner, class_name)
        function = defined[name]
        assert len(function.body) > 1, name
        assert function.decorator_list == [], name
        method = methods[name]
        if name in STATICMETHODS:
            assert "staticmethod" in _decorator_names(method), name
            assert "classmethod" not in _decorator_names(method), name
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
        if name in STATICMETHODS:
            assert call.args[0].id != "self"
            assert call.args[0].id != "cls"


def test_sentinels_stay_on_their_class() -> None:
    methods = _methods(_parse(OWNER), SENTINEL_CLASS)
    defined = _defined(_parse(SIBLING))
    for name in SENTINELS:
        assert name in methods, name
        assert name not in defined, name
        assert len(methods[name].body) > 1, name
