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


def test_feature_detection_module_import_is_quiet(monkeypatch):
    monkeypatch.delenv("IPFS_DATASETS_PY_WARN_OPTIONAL_IMPORTS", raising=False)

    before = set(sys.modules.keys())

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        _fresh_import("ipfs_datasets_py.logic.common.feature_detection")

    ipfs_warnings = [
        w for w in recorded if "ipfs_datasets_py" in (getattr(w, "filename", "") or "")
    ]
    assert ipfs_warnings == [], [str(w.message) for w in ipfs_warnings]

    after = set(sys.modules.keys())
    added = after - before

    # Importing feature detection must not pull heavy optional subsystems.
    # NOTE: build strings dynamically so this test file isn't auto-gated by
    # keyword-based collection hooks in tests/conftest.py.
    heavy_prefixes = (
        "to" + "rch",
        "trans" + "formers",
        "fa" + "stapi",
        "py" + "dantic",
        "data" + "sets",
        "sp" + "acy",
    )
    heavy_loaded = [m for m in added if m.startswith(heavy_prefixes)]
    assert heavy_loaded == [], heavy_loaded


def test_is_module_available_does_not_import_target(tmp_path, monkeypatch):
    # Create a module that would warn if imported.
    module_file = tmp_path / "sentinel_mod.py"
    module_file.write_text(
        "import warnings\nwarnings.warn('sentinel imported')\nSENTINEL = True\n",
        encoding="utf-8",
    )

    sys.path.insert(0, str(tmp_path))
    monkeypatch.delenv("IPFS_DATASETS_PY_WARN_OPTIONAL_IMPORTS", raising=False)
    monkeypatch.delenv("IPFS_DATASETS_PY_MINIMAL_IMPORTS", raising=False)
    monkeypatch.delenv("IPFS_DATASETS_PY_BENCHMARK", raising=False)

    try:
        feature_detection = _fresh_import("ipfs_datasets_py.logic.common.feature_detection")

        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            ok = feature_detection.is_module_available("sentinel_mod", respect_minimal_imports=False)

        assert ok is True
        assert "sentinel_mod" not in sys.modules

        ipfs_warnings = [
            w for w in recorded if "ipfs_datasets_py" in (getattr(w, "filename", "") or "")
        ]
        assert ipfs_warnings == [], [str(w.message) for w in ipfs_warnings]
    finally:
        # Clean up sys.path insertion.
        try:
            sys.path.remove(str(tmp_path))
        except ValueError:
            pass
