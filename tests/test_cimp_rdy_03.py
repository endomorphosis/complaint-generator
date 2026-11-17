"""CIMP-RDY-03: denoiser diagnostics live on the diagnostics sibling."""

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
_SIBLING_STEM = "denoiser_" + "diagnostics"
OWNER = REPO_ROOT / "complaint_phases" / "denoiser.py"
SIBLING = REPO_ROOT / "complaint_phases" / (_SIBLING_STEM + ".py")
OWNER_MAX = 4620
SIBLING_MIN = 520
FUNCTIONS = (
    "_clip_public",
    "_state_token",
    "_mapping",
    "_factual_target_view",
    "_law_requirement_view",
    "_admitted_authorities",
    "_support_states",
    "_support_conditions",
    "question_support_view",
    "_support_display_lines",
    "public_why_diagnostic_receipt",
    "redact_diagnostic_value",
    "format_terminal_why",
    "project_stopping_policy",
    "dependency_lane_for",
    "publish_authorized_dependency_action",
)
LANE_CONSTANTS = (
    "_DEPENDENCY_LANE_ALIASES",
    "_DEPENDENCY_LANE_ACTIONS",
    "MAX_DEPENDENCY_ACTION_ATTEMPTS",
)
PUBLIC = (
    "question_support_view",
    "public_why_diagnostic_receipt",
    "redact_diagnostic_value",
    "format_terminal_why",
    "project_stopping_policy",
    "MAX_DEPENDENCY_ACTION_ATTEMPTS",
    "dependency_lane_for",
    "publish_authorized_dependency_action",
)
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
REEXPORT = "from ." + _SIBLING_STEM + " import " + ", ".join(PUBLIC)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _functions(tree: ast.AST) -> dict:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _assigned(tree: ast.AST) -> dict:
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found[target.id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found[node.target.id] = node
    return found


def _constant(node: ast.AST):
    if isinstance(node, ast.Constant):
        return node.value
    return None


def test_diagnostics_moved_and_bounds_hold() -> None:
    owner_text = OWNER.read_text(encoding="utf-8")
    sibling_text = SIBLING.read_text(encoding="utf-8")
    assert len(owner_text.splitlines()) <= OWNER_MAX
    assert len(sibling_text.splitlines()) >= SIBLING_MIN
    assert REEXPORT in owner_text
    owner = _parse(OWNER)
    sibling = _parse(SIBLING)
    owner_functions = _functions(owner)
    sibling_functions = _functions(sibling)
    owner_assigned = _assigned(owner)
    sibling_assigned = _assigned(sibling)
    for name in FUNCTIONS:
        assert name not in owner_functions, name
        assert name not in owner_assigned, name
        function = sibling_functions[name]
        assert function.decorator_list == [], name
        assert not any(isinstance(item, (ast.Global, ast.Nonlocal)) for item in ast.walk(function))
    for name in LANE_CONSTANTS:
        assert name not in owner_assigned, name
        assert name not in owner_functions, name
        assert name in sibling_assigned, name
    schema = sibling_assigned["INTERFACE_SCHEMA"]
    version = sibling_assigned["INTERFACE_VERSION"]
    assert _constant(schema.value) == INTERFACE_SCHEMA
    assert _constant(version.value) == INTERFACE_VERSION
    reexport = None
    for node in owner.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level == 1 and node.module == _SIBLING_STEM and node.col_offset == 0:
            imported = tuple(alias.name for alias in node.names)
            if imported == PUBLIC:
                reexport = node
    assert reexport is not None
    classes = {
        node.name: node
        for node in owner.body
        if isinstance(node, ast.ClassDef)
    }
    sentinel = classes["ComplaintDenoiser"]
    assert len(sentinel.body) > 1
    sibling_classes = [node.name for node in sibling.body if isinstance(node, ast.ClassDef)]
    assert "ComplaintDenoiser" not in sibling_classes
