"""CIMP-BND-16: complaint generator does not import workspace."""

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INIT = REPO_ROOT / "complaint_generator/__init__.py"


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


def test_workspace_names_are_lazy_and_public_list_stays() -> None:
    tree = _tree()
    names = [item.value for item in _assigned(tree, "__all__").elts]
    exports = _assigned(tree, "_LAZY_EXPORTS")
    mapping = {}
    for key, value in zip(exports.keys, exports.values):
        module = value.elts[0].value
        attribute = value.elts[1].value
        mapping[key.value] = (module, attribute)
    assert len(names) == 89
    assert set(names) <= set(mapping)
    for name in (
        "ComplaintWorkspaceService", "improve_draft", "run_intake_chat_turn",
        "sync_mike_final_draft", "generate_complaint",
    ):
        assert mapping[name] == (".workspace", name)


def test_package_import_does_not_load_owners() -> None:
    script = r"""
import importlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))

import complaint_generator
assert "complaint_generator.workspace" not in sys.modules
assert len(complaint_generator.__all__) == 89
owner = importlib.import_module("complaint_generator.workspace")
assert complaint_generator.ComplaintWorkspaceService is owner.ComplaintWorkspaceService

"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(REPO_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
