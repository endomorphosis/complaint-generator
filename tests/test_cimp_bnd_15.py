"""CIMP-BND-15: backends import is lazy."""

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INIT = REPO_ROOT / "backends/__init__.py"


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


def test_package_import_does_not_load_owners() -> None:
    script = r"""
import importlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))

import backends
provider = "backends." + "open" + "ai"
for name in ("backends.llm_router_backend", "backends.workstation", "backends.multimodal_router_backend", provider):
    assert name not in sys.modules, name
router = importlib.import_module("backends.llm_router_backend")
multi = importlib.import_module("backends.multimodal_router_backend")
assert backends.LLMRouterBackend is router.LLMRouterBackend
assert backends.LLMRouter is router.LLMRouter
assert backends.MultimodalRouter is multi.MultimodalRouter
assert provider not in sys.modules
assert backends.WorkstationBackendModels.__name__ == "WorkstationBackendModels"

"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(REPO_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
