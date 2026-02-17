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


def _ipfs_origin_warnings(recorded: list[warnings.WarningMessage]) -> list[warnings.WarningMessage]:
    return [
        w
        for w in recorded
        if "ipfs_datasets_py" in (getattr(w, "filename", "") or "")
    ]


def test_logic_package_import_is_quiet(monkeypatch):
    monkeypatch.delenv("IPFS_DATASETS_PY_WARN_OPTIONAL_IMPORTS", raising=False)

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        _fresh_import("ipfs_datasets_py.logic")

    ipfs_warnings = _ipfs_origin_warnings(recorded)
    assert ipfs_warnings == [], [str(w.message) for w in ipfs_warnings]


def test_logic_tools_shim_warns_on_access(monkeypatch):
    monkeypatch.delenv("IPFS_DATASETS_PY_WARN_OPTIONAL_IMPORTS", raising=False)

    logic = _fresh_import("ipfs_datasets_py.logic")

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        _ = logic.tools

    dep_warnings = [w for w in recorded if issubclass(w.category, DeprecationWarning)]
    assert dep_warnings != []


def test_logic_api_all_symbols_resolve(monkeypatch):
    """The canonical facade must export a stable, resolvable surface."""

    monkeypatch.delenv("IPFS_DATASETS_PY_WARN_OPTIONAL_IMPORTS", raising=False)

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        api = _fresh_import("ipfs_datasets_py.logic.api")

    ipfs_warnings = _ipfs_origin_warnings(recorded)
    assert ipfs_warnings == [], [str(w.message) for w in ipfs_warnings]

    missing: list[str] = []
    for name in getattr(api, "__all__", []):
        if not hasattr(api, name):
            missing.append(name)

    assert missing == [], missing
