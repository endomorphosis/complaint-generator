"""Lazy public exports for the formal logic package."""

import ast
import subprocess
import sys
from pathlib import Path


_PUBLIC_NAMES = [
    "Action",
    "Conjunction",
    "DeonticKnowledgeBase",
    "DeonticModality",
    "DeonticStatement",
    "Disjunction",
    "Frame",
    "FrameKnowledgeBase",
    "FrameSlotEvidence",
    "CANONICAL_COMPILER_CAPABILITY_SCHEMA",
    "CanonicalCompilerCapability",
    "CanonicalCompilerSupport",
    "FormalLogicCapability",
    "FormalLogicCapabilityError",
    "FormalLogicDegradedError",
    "FormalLogicOperation",
    "FormalLogicUnavailableError",
    "Implication",
    "LogicalOperator",
    "LogicCapabilityState",
    "LogicCapabilityStatus",
    "capability_state_from_payload",
    "classify_canonical_compiler_capability",
    "Negation",
    "Party",
    "Predicate",
    "Proposition",
    "TemporalOperator",
    "TimeInterval",
]

_OWNERS = {
    "Action": "core",
    "Conjunction": "core",
    "DeonticKnowledgeBase": "core",
    "DeonticModality": "core",
    "DeonticStatement": "core",
    "Disjunction": "core",
    "Implication": "core",
    "LogicalOperator": "core",
    "Negation": "core",
    "Party": "core",
    "Predicate": "core",
    "Proposition": "core",
    "TemporalOperator": "core",
    "TimeInterval": "core",
    "Frame": "frames",
    "FrameKnowledgeBase": "frames",
    "FrameSlotEvidence": "frames",
    "CANONICAL_COMPILER_CAPABILITY_SCHEMA": "capabilities",
    "CanonicalCompilerCapability": "capabilities",
    "CanonicalCompilerSupport": "capabilities",
    "FormalLogicCapability": "capabilities",
    "FormalLogicCapabilityError": "capabilities",
    "FormalLogicDegradedError": "capabilities",
    "FormalLogicOperation": "capabilities",
    "FormalLogicUnavailableError": "capabilities",
    "LogicCapabilityState": "capabilities",
    "LogicCapabilityStatus": "capabilities",
    "capability_state_from_payload": "capabilities",
    "classify_canonical_compiler_capability": "capabilities",
}

_MODULE_DOC = "Reusable formal-logic primitives for complaint-generator."


def _init_path() -> Path:
    return Path(__file__).resolve().parents[1] / "lib" / "formal_logic" / "__init__.py"


def test_init_imports_only_importlib():
    tree = ast.parse(_init_path().read_text(encoding="utf-8"))
    assert isinstance(tree.body[0], ast.Expr)
    assert isinstance(tree.body[0].value, ast.Constant)
    assert tree.body[0].value.value == _MODULE_DOC
    exported = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name == "importlib"
        elif isinstance(node, ast.ImportFrom):
            assert node.module == "importlib"
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    assert isinstance(node.value, ast.List)
                    exported = [
                        element.value
                        for element in node.value.elts
                        if isinstance(element, ast.Constant)
                    ]
    assert exported == _PUBLIC_NAMES
    assert len(exported) == 29
    assert any(isinstance(node, ast.FunctionDef) and node.name == "__getattr__" for node in tree.body)


def test_import_does_not_execute_owners_and_names_match():
    package = "lib.formal_logic"
    owners_literal = repr(_OWNERS)
    script = (
        "import sys\n"
        "package = sys.argv[1]\n"
        "owners = " + owners_literal + "\n"
        "mod = __import__(package, fromlist=['__all__'])\n"
        "for owner in ('capabilities', 'core', 'frames'):\n"
        "    assert package + '.' + owner not in sys.modules\n"
        "for name in mod.__all__:\n"
        "    value = getattr(mod, name)\n"
        "    owner = package + '.' + owners[name]\n"
        "    assert getattr(sys.modules[owner], name) is value\n"
        "action = getattr(mod, 'Action')\n"
        "frame = getattr(mod, 'Frame')\n"
        "assert action is sys.modules[package + '.core'].Action\n"
        "assert frame is sys.modules[package + '.frames'].Frame\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, package],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
