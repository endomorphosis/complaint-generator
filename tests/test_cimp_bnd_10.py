"""CIMP-BND-10: adversarial harness import is lazy."""

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INIT = REPO_ROOT / "adversarial_harness/__init__.py"


def _tree() -> ast.AST:
    return ast.parse(INIT.read_text(encoding="utf-8"), filename=str(INIT))


def _assigned(tree: ast.AST, name: str):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return node.value
    raise AssertionError(name)


def test_initializer_has_no_owner_import() -> None:
    for node in _tree().body:
        if isinstance(node, ast.Import):
            assert [alias.name for alias in node.names] == ["importlib"]
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").startswith("importlib")


def test_public_names_stay_in_order() -> None:
    names = [item.value for item in _assigned(_tree(), "__all__").elts]
    assert names == [
        "Complainant", "ComplaintGenerator", "ComplaintContext", "Critic", "CriticScore",
        "AdversarialSession", "SessionResult", "AdversarialHarness", "Optimizer",
        "OptimizationReport", "WorkflowOptimizationBundle", "UIOptimizationBundle",
        "UIUXOptimizationBundle", "SeedComplaintLibrary", "ComplaintTemplate",
        "build_hacc_evidence_seeds", "DEFAULT_HACC_QUERY_SPECS", "HACC_QUERY_PRESETS",
        "get_hacc_query_specs", "SearchEnrichedSeedGenerator", "DecisionTreeEnhancer",
        "MediatorSearchIntegration",
    ]


def test_package_import_does_not_load_owners() -> None:
    script = r"""
import importlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))

import adversarial_harness
for name in ("adversarial_harness.optimizer", "adversarial_harness.session", "adversarial_harness.harness"):
    assert name not in sys.modules, name
assert len(adversarial_harness.__all__) == 22
optimizer = importlib.import_module("adversarial_harness.optimizer")
session = importlib.import_module("adversarial_harness.session")
harness = importlib.import_module("adversarial_harness.harness")
assert adversarial_harness.Optimizer is optimizer.Optimizer
assert adversarial_harness.AdversarialSession is session.AdversarialSession
assert adversarial_harness.AdversarialHarness is harness.AdversarialHarness

"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(REPO_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
