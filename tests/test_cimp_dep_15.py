"""CIMP-DEP-15: complaint analysis interface is lazy."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_schema_is_recorded_without_importing_owners() -> None:
    script = r"""
import importlib
import importlib.util
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
path = root / "complaint_analysis" / "interface.py"
spec = importlib.util.spec_from_file_location("dep15_interface", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
owners = (
    "complaint_analysis.analyzer",
    "complaint_analysis.legal_patterns",
    "complaint_analysis.response_parsers",
)
for name in owners:
    assert name not in sys.modules, name
assert module.INTERFACE_SCHEMA == "complaint-generator/module-interface@1"
assert module.INTERFACE_VERSION == "1.0.0"
assert module.OWNER_MODULES == owners
assert module.ComplaintAnalyzer is importlib.import_module("complaint_analysis.analyzer").ComplaintAnalyzer
assert module.LegalPatternExtractor is importlib.import_module("complaint_analysis.legal_patterns").LegalPatternExtractor
assert module.ResponseParserFactory is importlib.import_module("complaint_analysis.response_parsers").ResponseParserFactory
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(REPO_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
