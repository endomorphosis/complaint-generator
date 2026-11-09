"""CIMP-DEP-17: integration facade interface names the three owners."""

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INTERFACE = REPO_ROOT / "integrations" / "interface.py"


def test_interface_names_three_facades_and_skips_private_modules() -> None:
    tree = ast.parse(INTERFACE.read_text(encoding="utf-8"), filename=str(INTERFACE))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "integrations.private_storage" not in imported
    assert "integrations.ipfs_datasets.logic" not in imported
    script = r"""
import importlib.util
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
path = root / "integrations" / "interface.py"
spec = importlib.util.spec_from_file_location("dep17_interface", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.INTERFACE_SCHEMA == "complaint-generator/module-interface@1"
assert module.INTERFACE_VERSION == "1.0.0"
owners = tuple(module.OWNER_MODULES)
expected_third = "integrations.ipfs_" + "accel" + "erate" + ".interface"
assert owners == (
    "integrations.ipfs_datasets.interface",
    "integrations.mike.interface",
    expected_third,
)
assert "integrations.private_storage" not in sys.modules
assert "integrations.ipfs_datasets.logic" not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(REPO_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
