"""CIMP-DEP-14: adversarial harness interface is lazy."""

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INTERFACE = REPO_ROOT / "adversarial_harness" / "interface.py"


def test_schema_is_recorded_without_importing_owners() -> None:
    script = r"""
import importlib
import importlib.util
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
path = root / "adversarial_harness" / "interface.py"
spec = importlib.util.spec_from_file_location("dep14_interface", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
owners = (
    "adversarial_harness.harness",
    "adversarial_harness.optimizer",
    "adversarial_harness.session",
)
for name in owners:
    assert name not in sys.modules, name
assert module.INTERFACE_SCHEMA == "complaint-generator/module-interface@1"
assert module.INTERFACE_VERSION == "1.0.0"
assert module.OWNER_MODULES == owners
assert module.AdversarialHarness is importlib.import_module("adversarial_harness.harness").AdversarialHarness
assert module.Optimizer is importlib.import_module("adversarial_harness.optimizer").Optimizer
assert module.AdversarialSession is importlib.import_module("adversarial_harness.session").AdversarialSession
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(REPO_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    text = INTERFACE.read_text(encoding="utf-8")
    assert "complaint-generator/module-interface@1" in text
    assert "1.0.0" in text
