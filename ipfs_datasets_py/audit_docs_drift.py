"""
Documentation drift audit for the complaint-generator MCP stack.

Usage::

    python ipfs_datasets_py/audit_docs_drift.py [--output drift_report_mcp.json]

Compares API symbols exposed by the codebase with what is documented and
produces a JSON report of missing / stale entries.
"""

from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Set


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_public_symbols(package_root: Path) -> Dict[str, List[str]]:
    """
    Walk *package_root* and collect all top-level public symbol names per
    module, by static-parsing ``def`` and ``class`` statements.
    """
    symbols: Dict[str, List[str]] = {}
    for py_file in sorted(package_root.rglob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        module_key = str(py_file.relative_to(package_root.parent))
        syms: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    syms.append(node.name)
        if syms:
            symbols[module_key] = syms
    return symbols


def _collect_documented_symbols(docs_root: Path) -> Set[str]:
    """
    Walk *docs_root* for ``.md`` and ``.rst`` files and collect all
    identifiers that appear in code blocks or inline code spans.
    """
    documented: Set[str] = set()
    for doc_file in docs_root.rglob("*"):
        if doc_file.suffix not in {".md", ".rst", ".txt"}:
            continue
        try:
            text = doc_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Very simple heuristic: extract backtick-quoted identifiers
        for segment in text.split("`"):
            seg = segment.strip()
            if seg.isidentifier() and not seg.startswith("_"):
                documented.add(seg)
    return documented


# ---------------------------------------------------------------------------
# Audit logic
# ---------------------------------------------------------------------------

def run_audit(
    package_root: Path,
    docs_root: Path,
) -> Dict[str, Any]:
    """
    Run the drift audit and return a raw report dict.

    Issues are classified as:
    - ``undocumented``  — symbol exported but not mentioned in docs
    - ``stale``         — identifier in docs but no longer exported
    """
    code_symbols = _collect_public_symbols(package_root)
    documented = _collect_documented_symbols(docs_root)

    all_code_syms: Set[str] = set()
    for syms in code_symbols.values():
        all_code_syms.update(syms)

    undocumented = sorted(all_code_syms - documented)
    stale = sorted(documented - all_code_syms)

    issues: List[Dict[str, Any]] = []
    for sym in undocumented:
        issues.append({"symbol": sym, "severity": "warning", "category": "undocumented"})
    for sym in stale:
        issues.append({"symbol": sym, "severity": "info", "category": "stale"})

    by_severity: Dict[str, int] = {}
    by_category: Dict[str, int] = {}
    for issue in issues:
        by_severity[issue["severity"]] = by_severity.get(issue["severity"], 0) + 1
        by_category[issue["category"]] = by_category.get(issue["category"], 0) + 1

    return {
        "summary": {
            "total_issues": len(issues),
            "by_severity": by_severity,
            "by_category": by_category,
            "total_code_symbols": len(all_code_syms),
            "total_documented_symbols": len(documented),
        },
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(output_path: str = "drift_report_mcp.json") -> None:
    repo_root = Path(__file__).parent.parent
    package_root = repo_root / "ipfs_datasets_py"
    docs_root = repo_root / "docs"

    if not package_root.exists():
        print(f"Package root not found: {package_root}", file=sys.stderr)
        sys.exit(1)
    if not docs_root.exists():
        docs_root = repo_root  # Fall back to repo root

    report = run_audit(package_root, docs_root)

    output = Path(output_path)
    output.write_text(json.dumps(report, indent=2))
    print(f"Drift report written to {output}")
    print(f"Total issues: {report['summary']['total_issues']}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Audit documentation drift")
    parser.add_argument(
        "--output",
        default="drift_report_mcp.json",
        help="Path for the JSON report (default: drift_report_mcp.json)",
    )
    args = parser.parse_args()
    main(args.output)
