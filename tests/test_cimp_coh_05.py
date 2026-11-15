"""CIMP-COH-05: canonical formalization lives in the formalization sibling."""

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE = "ipfs_" + "datasets"
_SIBLING_STEM = "canonical_" + "formalization"
OWNER = REPO_ROOT / "integrations" / _PACKAGE / "logic.py"
SIBLING = REPO_ROOT / "integrations" / _PACKAGE / (_SIBLING_STEM + ".py")
EXTRACTED = (
    "_bridge_canonical_source_map",
    "audit_canonical_formalization_payload",
    "bind_current_definition_correspondence_owners",
    "extract_source_bound_rule_candidates",
    "connect_definition_handoff_proof",
)
SENTINELS = (
    "prepare_acquired_authority_record",
    "route_bound_legal_ir_proof",
)
EXPORTED = tuple(name for name in EXTRACTED if not name.startswith("_")) + SENTINELS
OWNER_MAX = 6420
SIBLING_MIN = 700
STEM = _SIBLING_STEM


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _defined(tree: ast.AST) -> dict:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _imported(tree: ast.AST) -> set:
    names = set()
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level != 1 or node.col_offset != 0 or node.module != STEM:
            continue
        names.update(alias.name for alias in node.names)
    return names


def _all_strings(tree: ast.AST) -> list:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            continue
        if not isinstance(node.value, ast.List):
            continue
        values = []
        for element in node.value.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                values.append(element.value)
        return values
    return []


def test_owner_reexports_canonical_formalization_functions() -> None:
    owner_text = OWNER.read_text(encoding="utf-8")
    sibling_text = SIBLING.read_text(encoding="utf-8")
    owner = _parse(OWNER)
    sibling = _parse(SIBLING)
    owner_defined = _defined(owner)
    sibling_defined = _defined(sibling)
    imported = _imported(owner)
    exported = _all_strings(owner)
    assert len(owner_text.splitlines()) <= OWNER_MAX
    assert len(sibling_text.splitlines()) >= SIBLING_MIN
    for name in EXTRACTED:
        assert name not in owner_defined, name
        assert name in sibling_defined, name
        assert name in imported, name
        assert len(sibling_defined[name].body) > 1, name
    for name in EXPORTED:
        assert name in exported, name
    for name in SENTINELS:
        assert name in owner_defined, name
        assert name not in sibling_defined, name
        assert len(owner_defined[name].body) > 1, name
