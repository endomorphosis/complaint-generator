from __future__ import annotations

import importlib
import re
import sys
import warnings

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
_IPFS_DATASETS_SRC = _REPO_ROOT / "ipfs_datasets_py"
if _IPFS_DATASETS_SRC.exists():
    sys.path.insert(0, str(_IPFS_DATASETS_SRC))


def _ipfs_origin_warnings(recorded: list[warnings.WarningMessage]) -> list[warnings.WarningMessage]:
    return [
        w
        for w in recorded
        if "ipfs_datasets_py" in (getattr(w, "filename", "") or "")
    ]


def test_logic_readme_relative_links_exist() -> None:
    logic_dir = _IPFS_DATASETS_SRC / "ipfs_datasets_py" / "logic"
    readme = logic_dir / "README.md"
    assert readme.is_file(), str(readme)

    text = readme.read_text(encoding="utf-8", errors="ignore")

    # Validate all relative markdown links, including links that point outside the
    # logic/ directory (e.g., ../../examples/... or ../../IMPLEMENTATION_SUMMARY.md).
    # We intentionally do not validate external URLs here.
    raw_targets = re.findall(r"\(([^)]+)\)", text)

    missing: list[str] = []
    for raw in raw_targets:
        target = raw.strip()
        if not target or target.startswith("#"):
            continue
        if "://" in target or target.startswith("mailto:"):
            continue

        # Drop any anchor fragment.
        target_no_anchor = target.split("#", 1)[0]
        if not target_no_anchor.endswith(".md"):
            continue

        resolved = (readme.parent / target_no_anchor).resolve()
        if not resolved.is_file():
            missing.append(target_no_anchor)

    assert missing == [], missing


def test_logic_quick_start_imports_resolve(monkeypatch) -> None:
    monkeypatch.delenv("IPFS_DATASETS_PY_WARN_OPTIONAL_IMPORTS", raising=False)

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")

        # These mirror the Quick Start snippets, but do not execute any logic.
        importlib.import_module("ipfs_datasets_py.logic")
        importlib.import_module("ipfs_datasets_py.logic.api")
        importlib.import_module("ipfs_datasets_py.logic.integration")
        importlib.import_module("ipfs_datasets_py.logic.TDFOL.tdfol_parser")

    ipfs_warnings = _ipfs_origin_warnings(recorded)
    assert ipfs_warnings == [], [str(w.message) for w in ipfs_warnings]
