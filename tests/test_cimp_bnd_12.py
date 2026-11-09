"""CIMP-BND-12: mediator import is lazy."""

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INIT = REPO_ROOT / "mediator/__init__.py"


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


def test_public_names_cover_the_hooks() -> None:
    names = [item.value for item in _assigned(_tree(), "__all__").elts]
    assert names[:5] == [
        "Mediator", "MODULE_OWNERSHIP", "RUNTIME_ENTRYPOINT_ROLE",
        "ALIGNMENT_TASK_UPDATE_HISTORY_LIMIT", "FOLLOW_UP_REVIEWABLE_ESCALATION_STATUSES",
    ]
    for name in ("WorkflowService", "ClaimSupportHook", "ComplaintDocumentBuilder", "LegalCorpusRAGHook"):
        assert name in names
    assert len(names) == 22


def test_package_import_does_not_load_owners() -> None:
    script = r"""
import importlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))

import mediator
for name in (
    "mediator.mediator", "mediator.workflow_service", "mediator.evidence_hooks",
    "mediator.claim_support_hooks", "mediator.formal_document",
):
    assert name not in sys.modules, name
owner = importlib.import_module("mediator.mediator")
workflow = importlib.import_module("mediator.workflow_service")
hooks = importlib.import_module("mediator.claim_support_hooks")
document = importlib.import_module("mediator.formal_document")
assert mediator.Mediator is owner.Mediator
assert mediator.MODULE_OWNERSHIP is owner.MODULE_OWNERSHIP
assert mediator.WorkflowService is workflow.WorkflowService
assert mediator.ClaimSupportHook is hooks.ClaimSupportHook
assert mediator.ComplaintDocumentBuilder is document.ComplaintDocumentBuilder

"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(REPO_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
