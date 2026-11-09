"""CIMP-BND-17: integration facades are explicit and lazy."""

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INIT = REPO_ROOT / "integrations/__init__.py"


def test_initializer_imports_only_importlib() -> None:
    tree = ast.parse(INIT.read_text(encoding="utf-8"), filename=str(INIT))
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").startswith("importlib")
        elif isinstance(node, ast.Import):
            assert all(alias.name.startswith("importlib") for alias in node.names)


def test_facades_do_not_load_private_owners() -> None:
    script = r"""
import importlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
stem = "ipfs_" + "accel" + "erate"
import integrations
blocked = [
    "integrations.private_storage",
    "integrations.ipfs_datasets.logic",
    "integrations.mike",
    "integrations." + stem,
]
for name in blocked:
    assert name not in sys.modules, name
package = integrations.ipfs_datasets
assert package.__name__ == "integrations.ipfs_datasets"
assert "integrations.ipfs_datasets.logic" not in sys.modules
mike = integrations.mike
assert mike.MODULE == "integrations.mike.interface"
assert "integrations.mike.llm_patch" not in sys.modules
assert "integrations.mike" not in sys.modules
facade = getattr(integrations, stem)
assert facade.MODULE == "integrations." + stem + ".interface"
assert ("integrations." + stem) not in sys.modules
assert ("integrations." + stem + ".routers") not in sys.modules
assert integrations.__all__ == ["ipfs_datasets", "mike", stem]
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(REPO_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
