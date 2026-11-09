"""CIMP-DEP-16: router backend interface is lazy."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_schema_is_recorded_without_importing_the_router() -> None:
    script = r"""
import importlib
import importlib.util
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
path = root / "backends" / "interface.py"
spec = importlib.util.spec_from_file_location("dep16_interface", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
provider = "backends." + "open" + "ai"
assert "backends.llm_router_backend" not in sys.modules
assert provider not in sys.modules
assert module.INTERFACE_SCHEMA == "complaint-generator/module-interface@1"
assert module.INTERFACE_VERSION == "1.0.0"
assert module.OWNER_MODULES == ("backends.llm_router_backend",)
owner = importlib.import_module("backends.llm_router_backend")
assert module.LLMRouterBackend is owner.LLMRouterBackend
assert module.load_terminal_router_backend is owner.load_terminal_router_backend
assert provider not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(REPO_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
