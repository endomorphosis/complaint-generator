"""CIMP-RDY-04: optimizer report types live on the reports sibling."""

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
_SIBLING_STEM = "optimizer_" + "reports"
OWNER = REPO_ROOT / "adversarial_harness" / "optimizer.py"
SIBLING = REPO_ROOT / "adversarial_harness" / (_SIBLING_STEM + ".py")
OWNER_MAX = 3890
SIBLING_MIN = 220
REPORT_CLASSES = (
    "OptimizationReport",
    "WorkflowOptimizationBundle",
    "UIUXOptimizationBundle",
    "UIOptimizationBundle",
)
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
REEXPORT = "from ." + _SIBLING_STEM + " import " + ", ".join(REPORT_CLASSES)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _classes(tree: ast.AST) -> dict:
    return {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}


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


def test_report_types_moved_and_bounds_hold() -> None:
    owner_text = OWNER.read_text(encoding="utf-8")
    sibling_text = SIBLING.read_text(encoding="utf-8")
    assert len(owner_text.splitlines()) <= OWNER_MAX
    assert len(sibling_text.splitlines()) >= SIBLING_MIN
    assert REEXPORT in owner_text
    owner = _parse(OWNER)
    sibling = _parse(SIBLING)
    owner_classes = _classes(owner)
    sibling_classes = _classes(sibling)
    owner_assigned = _assigned(owner)
    sibling_assigned = _assigned(sibling)
    for name in REPORT_CLASSES:
        assert name not in owner_classes, name
        assert name not in owner_assigned, name
        report_class = sibling_classes[name]
        assert report_class.decorator_list, name
        decorator = report_class.decorator_list[0]
        assert isinstance(decorator, ast.Name)
        assert decorator.id == "dataclass"
        methods = [item.name for item in report_class.body if isinstance(item, ast.FunctionDef)]
        assert "to_dict" in methods, name
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
            if imported == REPORT_CLASSES:
                reexport = node
    assert reexport is not None
    sentinel = owner_classes["Optimizer"]
    assert len(sentinel.body) > 1
    assert "Optimizer" not in sibling_classes


def test_module_pytestmark_has_required_marks() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    marks: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets):
            continue
        assert isinstance(node.value, ast.List)
        for element in node.value.elts:
            assert isinstance(element, ast.Attribute)
            assert isinstance(element.value, ast.Attribute)
            assert isinstance(element.value.value, ast.Name)
            assert element.value.value.id == "pytest"
            assert element.value.attr == "mark"
            marks.append(element.attr)
    assert marks == ["no_auto_llm", "no_auto_network", "no_auto_heavy"]
    for node in ast.walk(tree):
        assert not (isinstance(node, ast.Attribute) and node.attr in {"skip", "skipif"})
