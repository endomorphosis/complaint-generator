"""CIMP-COH-09: the mike package note names the interface entry."""

import ast
import re
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

REPO_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_PARENT = "integr" + "ations"
_PACKAGE_CHILD = "mike"
_PACKAGE = _PACKAGE_PARENT + "." + _PACKAGE_CHILD
_FACADE_STEM = "inter" + "face"
NOTE = REPO_ROOT / _PACKAGE_PARENT / _PACKAGE_CHILD / "README.md"
SURFACE = REPO_ROOT / _PACKAGE_PARENT / _PACKAGE_CHILD / (_FACADE_STEM + ".py")
ENTRY = _PACKAGE + "." + _FACADE_STEM
OWNERS = (
    _PACKAGE,
    _PACKAGE + ".llm_patch",
    _PACKAGE + ".skills",
)
SCHEMA_NAME = "INTERFACE_" + "SCHEMA"
VERSION_NAME = "INTERFACE_" + "VERSION"
SCHEMA = "complaint-generator/module-" + "interface@1"
VERSION = "1.0.0"
_DOTTED = re.compile(
    r"integrations\.mike(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
)


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
    assert f"current entry is `{ENTRY}`" in lowered
    assert SCHEMA_NAME in text
    assert SCHEMA in text
    assert VERSION_NAME in text
    assert VERSION in text
    assert "the only owners are" in lowered
    for owner in OWNERS:
        assert owner in text
    named = set(_DOTTED.findall(text))
    assert named == {ENTRY, *OWNERS}
    assert "importing the interface does not import those owners" in lowered
    assert "root mike compatibility directory" in lowered
    assert "external/mike" in lowered

    assigned = _assigned(_parse(SURFACE))
    assert assigned[SCHEMA_NAME] == SCHEMA
    assert assigned[VERSION_NAME] == VERSION
    assert assigned["MODULE"] == ENTRY
    assert assigned["OWNER_MODULES"] == OWNERS


def test_note_check_does_not_import_the_package() -> None:
    tree = _parse(Path(__file__))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert _PACKAGE not in imported
    assert _PACKAGE_PARENT not in imported
    assert not any(
        name == _PACKAGE or name.startswith(_PACKAGE + ".") or name == _PACKAGE_PARENT
        for name in imported
    )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        attr = func.attr if isinstance(func, ast.Attribute) else ""
        ident = func.id if isinstance(func, ast.Name) else ""
        assert attr not in {"skip", "importorskip"}
        assert ident not in {"skip", "importorskip"}
