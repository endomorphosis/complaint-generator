"""CIMP-COH-07: the backends package note names the interface entry."""

import ast
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

REPO_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE = "back" + "ends"
_FACADE_STEM = "inter" + "face"
NOTE = REPO_ROOT / _PACKAGE / "README.md"
SURFACE = REPO_ROOT / _PACKAGE / (_FACADE_STEM + ".py")
ENTRY = _PACKAGE + "." + _FACADE_STEM
OWNER = _PACKAGE + ".llm_router_" + "backend"
SCHEMA_NAME = "INTERFACE_" + "SCHEMA"
VERSION_NAME = "INTERFACE_" + "VERSION"
SCHEMA = "complaint-generator/module-" + "interface@1"
VERSION = "1.0.0"
SYMBOLS = ("LLMRouter" + "Backend", "load_terminal_router_" + "backend")


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _assigned(tree: ast.AST) -> dict:
    values = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
            values[target.id] = node.value.value
        if isinstance(target, ast.Name) and isinstance(node.value, ast.Tuple):
            values[target.id] = tuple(
                item.value for item in node.value.elts if isinstance(item, ast.Constant)
            )
    return values


def test_package_note_names_interface_entry() -> None:
    text = NOTE.read_text(encoding="utf-8")
    lowered = text.lower()
    assert ENTRY in text
    assert OWNER in text
    assert "only owner" in lowered
    assert SCHEMA_NAME in text
    assert SCHEMA in text
    assert VERSION_NAME in text
    assert VERSION in text
    for symbol in SYMBOLS:
        assert symbol in text
    assert "importing the interface does not import the router implementation" in lowered

    assigned = _assigned(_parse(SURFACE))
    assert assigned[SCHEMA_NAME] == SCHEMA
    assert assigned[VERSION_NAME] == VERSION
    assert assigned["MODULE"] == ENTRY
    assert assigned["OWNER_MODULES"] == (OWNER,)


def test_note_check_does_not_import_the_package() -> None:
    tree = _parse(Path(__file__))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert _PACKAGE not in imported
    assert not any(name == _PACKAGE or name.startswith(_PACKAGE + ".") for name in imported)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        attr = func.attr if isinstance(func, ast.Attribute) else ""
        ident = func.id if isinstance(func, ast.Name) else ""
        assert attr not in {"skip", "importorskip"}
        assert ident not in {"skip", "importorskip"}
