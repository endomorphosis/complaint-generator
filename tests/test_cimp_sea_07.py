"""CIMP-SEA-07: scraper queue delegates to evidence_scraper_queue."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER = REPO_ROOT / "mediator/evidence_hooks.py"
SIBLING = REPO_ROOT / "mediator/evidence_scraper_queue.py"
CLASS_NAME = "EvidenceStateHook"
SENTINEL_CLASS = "EvidenceStateHook"
SENTINELS = ("get_scraper_queue_state",)
EXTRACTED = (
    "get_scraper_run_details",
    "complete_scraper_job",
    "enqueue_scraper_job",
    "claim_next_scraper_job",
    "get_scraper_runs",
    "get_scraper_queue",
)
OWNER_MAX = 3400
SIBLING_MIN = 280
QUALIFIER = "evidence_scraper_queue"


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
        if not isinstance(node, ast.ImportFrom) or node.level != 1:
            continue
        if node.module == QUALIFIER:
            return True
        if any(alias.name == QUALIFIER or alias.asname == QUALIFIER for alias in node.names):
            return True
    return False


def _sibling_function(tree: ast.AST, name: str):
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    assert len(matches) == 1, name
    return matches[0]


def _is_static(method: ast.FunctionDef) -> bool:
    return any(isinstance(item, ast.Name) and item.id == "staticmethod" for item in method.decorator_list)


def _is_class(method: ast.FunctionDef) -> bool:
    return any(isinstance(item, ast.Name) and item.id == "classmethod" for item in method.decorator_list)


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
        if _is_static(method):
            assert method.args.args == [], name
            assert call.args == [], name
        elif _is_class(method):
            receiver = method.args.args[0].arg
            assert call.args, name
            assert isinstance(call.args[0], ast.Name), name
            assert call.args[0].id == receiver, name
        else:
            receiver = method.args.args[0].arg
            assert call.args, name
            assert isinstance(call.args[0], ast.Name), name
            assert call.args[0].id == receiver, name


def test_sentinels_stay_on_their_class() -> None:
    methods = _methods(_parse(OWNER), SENTINEL_CLASS)
    defined = _defined(_parse(SIBLING))
    for name in SENTINELS:
        assert name in methods, name
        assert name not in defined, name
        assert len(methods[name].body) > 1, name
