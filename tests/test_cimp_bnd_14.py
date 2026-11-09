"""CIMP-BND-14: lib import is lazy."""

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INIT = REPO_ROOT / "lib/__init__.py"


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


def test_public_names_stay() -> None:
    names = [item.value for item in _assigned(_tree(), "__all__").elts]
    assert names == [
        "deontic_logic", "document_render", "formal_logic",
        "legal_document", "runtime_ownership", "support_map",
    ]


def test_package_import_does_not_load_owners() -> None:
    script = r"""
import importlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))

import lib
for name in (
    "lib.deontic_logic", "lib.document_render", "lib.formal_logic",
    "lib.legal_document", "lib.runtime_ownership", "lib.support_map",
):
    assert name not in sys.modules, name
module = importlib.import_module("lib.deontic_logic")
assert lib.deontic_logic is module

"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(REPO_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
