"""CIMP-BND-11: complaint analysis import is lazy."""

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INIT = REPO_ROOT / "complaint_analysis/__init__.py"


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


def test_public_names_and_version_stay() -> None:
    tree = _tree()
    names = [item.value for item in _assigned(tree, "__all__").elts]
    version = _assigned(tree, "__version__")
    assert len(names) == 63
    assert names[:3] == ["BaseLegalPatternExtractor", "BaseKeywordRegistry", "BaseRiskScorer"]
    for name in ("ComplaintAnalyzer", "LegalPatternExtractor", "ResponseParserFactory", "RiskScorer", "ComplaintLegalPatternExtractor"):
        assert name in names
    assert isinstance(version, ast.Constant) and version.value == "2.0.0"


def test_package_import_does_not_load_owners() -> None:
    script = r"""
import importlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))

import complaint_analysis
for name in ("complaint_analysis.analyzer", "complaint_analysis.legal_patterns", "complaint_analysis.response_parsers"):
    assert name not in sys.modules, name
analyzer = importlib.import_module("complaint_analysis.analyzer")
patterns = importlib.import_module("complaint_analysis.legal_patterns")
parsers = importlib.import_module("complaint_analysis.response_parsers")
scoring = importlib.import_module("complaint_analysis.risk_scoring")
assert complaint_analysis.ComplaintAnalyzer is analyzer.ComplaintAnalyzer
assert complaint_analysis.LegalPatternExtractor is patterns.LegalPatternExtractor
assert complaint_analysis.ResponseParserFactory is parsers.ResponseParserFactory
assert complaint_analysis.RiskScorer is scoring.ComplaintRiskScorer
assert complaint_analysis.ComplaintLegalPatternExtractor is patterns.LegalPatternExtractor

"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(REPO_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
