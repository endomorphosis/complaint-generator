from __future__ import annotations

import importlib
import sys
import warnings

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
_IPFS_DATASETS_SRC = _REPO_ROOT / "ipfs_datasets_py"
if _IPFS_DATASETS_SRC.exists():
    sys.path.insert(0, str(_IPFS_DATASETS_SRC))


def _fresh_import(module_name: str) -> object:
    # Ensure we exercise import-time behavior deterministically.
    for name in list(sys.modules.keys()):
        if name == module_name or name.startswith(module_name + "."):
            sys.modules.pop(name, None)
    importlib.invalidate_caches()
    return importlib.import_module(module_name)


def test_logic_api_import_emits_no_ipfs_datasets_warnings(monkeypatch):
    # Default policy: missing optional deps must not warn at import time.
    monkeypatch.delenv("IPFS_DATASETS_PY_WARN_OPTIONAL_IMPORTS", raising=False)

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        _fresh_import("ipfs_datasets_py.logic.api")

    ipfs_warnings = [
        w
        for w in recorded
        if "ipfs_datasets_py" in (getattr(w, "filename", "") or "")
    ]
    assert ipfs_warnings == [], [str(w.message) for w in ipfs_warnings]
