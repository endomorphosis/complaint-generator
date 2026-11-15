"""CIMP-ORG-03: authority search programs delegate to legal_authority_search."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER = REPO_ROOT / "mediator/legal_authority_hooks.py"
SIBLING = REPO_ROOT / "mediator/legal_authority_search.py"
QUALIFIER = "legal_authority_search"
OWNER_MAX = 3150
SIBLING_MIN = 560

SEARCH_MOVED = (
    "build_search_programs",
    "search_all_sources",
    "_search_courtlistener_fallback",
    "_normalize_courtlistener_result",
    "_search_oregon_statutes_fallback",
    "_search_federal_statutes_fallback",
    "_search_ecfr_fallback",
    "_search_agency_guidance_fallback",
    "_collect_search_diagnostics",
)
STORAGE_MOVED = (
    "_build_search_program_records",
    "_normalize_search_programs",
    "_build_search_program_summary",
)
MOVED = SEARCH_MOVED + STORAGE_MOVED
SENTINELS = ("search_case_law",)
KEPT_ON_SEARCH = (
    "search_state_laws",
    "search_us_code",
    "search_federal_register",
    "search_administrative_law",
    "search_web_archives",
    "_generate_search_terms",
)


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


def test_named_search_methods_delegate_in_one_return() -> None:
    owner_text = OWNER.read_text(encoding="utf-8")
    sibling_text = SIBLING.read_text(encoding="utf-8")
    assert len(owner_text.splitlines()) <= OWNER_MAX
    assert len(sibling_text.splitlines()) >= SIBLING_MIN
    owner = _parse(OWNER)
    sibling = _parse(SIBLING)
    defined = _defined(sibling)
    search = _methods(owner, "LegalAuthoritySearchHook")
    storage = _methods(owner, "LegalAuthorityStorageHook")
    owner_defined = _defined(owner)
    imported = _sibling_import(owner)
    assert imported is not None
    assert imported is owner.body[-1]
    for node in owner.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assert node.lineno < imported.lineno
    for name in SEARCH_MOVED:
        _assert_one_line_call(search[name], name)
        function = defined[name]
        assert function.decorator_list == [], name
        assert len(function.body) > 1, name
        assert name not in owner_defined
    for name in STORAGE_MOVED:
        _assert_one_line_call(storage[name], name)
        function = defined[name]
        assert function.decorator_list == [], name
        assert len(function.body) > 1, name
        assert name not in owner_defined


def test_search_case_law_keeps_its_body() -> None:
    search = _methods(_parse(OWNER), "LegalAuthoritySearchHook")
    defined = _defined(_parse(SIBLING))
    for name in SENTINELS:
        assert name in search, name
        assert name not in defined, name
        assert len(search[name].body) > 1, name
        statement = search[name].body[-1]
        returns_sibling = (
            isinstance(statement, ast.Return)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Attribute)
            and isinstance(statement.value.func.value, ast.Name)
            and statement.value.func.value.id == QUALIFIER
        )
        assert returns_sibling is False


def test_unmoved_search_methods_stay_on_the_owner() -> None:
    search = _methods(_parse(OWNER), "LegalAuthoritySearchHook")
    defined = _defined(_parse(SIBLING))
    for name in KEPT_ON_SEARCH:
        assert name in search, name
        assert name not in defined, name
        method = search[name]
        delegated = (
            len(method.body) == 1
            and isinstance(method.body[0], ast.Return)
            and isinstance(method.body[0].value, ast.Call)
            and isinstance(method.body[0].value.func, ast.Attribute)
            and isinstance(method.body[0].value.func.value, ast.Name)
            and method.body[0].value.func.value.id == QUALIFIER
        )
        assert delegated is False, name
