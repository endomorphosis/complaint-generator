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
    root = module_name.split(".", 1)[0]
    for name in list(sys.modules.keys()):
        if name == root or name.startswith(root + "."):
            sys.modules.pop(name, None)
    for name in list(sys.modules.keys()):
        if name == module_name or name.startswith(module_name + "."):
            sys.modules.pop(name, None)
    importlib.invalidate_caches()
    return importlib.import_module(module_name)


def test_logic_zkp_import_is_quiet_and_lazy(monkeypatch):
    monkeypatch.delenv("IPFS_DATASETS_PY_WARN_OPTIONAL_IMPORTS", raising=False)

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        zkp = _fresh_import("ipfs_datasets_py.logic.zkp")

    ipfs_warnings = [
        w for w in recorded if "ipfs_datasets_py" in (getattr(w, "filename", "") or "")
    ]
    assert ipfs_warnings == [], [str(w.message) for w in ipfs_warnings]

    # Importing the package must not eagerly load its submodules.
    eager = [
        "ipfs_datasets_py.logic.zkp.zkp_prover",
        "ipfs_datasets_py.logic.zkp.zkp_verifier",
        "ipfs_datasets_py.logic.zkp.circuits",
    ]
    loaded = [m for m in sys.modules.keys() if m in eager]
    assert loaded == [], loaded

    # First real API access should emit a simulation warning.
    with warnings.catch_warnings(record=True) as recorded2:
        warnings.simplefilter("always")
        _ = zkp.ZKPProver

    user_warnings = [w for w in recorded2 if w.category is UserWarning]
    assert user_warnings, "expected a simulation UserWarning on first API access"
