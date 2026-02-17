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


def test_stable_subpackages_export_expected_symbols(monkeypatch):
    monkeypatch.delenv("IPFS_DATASETS_PY_WARN_OPTIONAL_IMPORTS", raising=False)

    modules_and_exports: dict[str, set[str]] = {
        "ipfs_datasets_py.logic.fol": {"FOLConverter", "convert_text_to_fol"},
        "ipfs_datasets_py.logic.deontic": {"DeonticConverter", "convert_legal_text_to_deontic"},
        "ipfs_datasets_py.logic.common": {
            "LogicError",
            "ConversionError",
            "ValidationError",
            "LogicConverter",
            "ConversionResult",
            "ConversionStatus",
            "BoundedCache",
            "ProofCache",
            "get_global_cache",
            "is_module_available",
        },
        "ipfs_datasets_py.logic.types": {
            "DeonticOperator",
            "DeonticFormula",
            "ProofResult",
            "ProofStatus",
            "LogicTranslationTarget",
            "Formula",
            "And",
            "FOLOutputFormat",
        },
    }

    for module_name, expected in modules_and_exports.items():
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            mod = _fresh_import(module_name)

        ipfs_warnings = _ipfs_origin_warnings(recorded)
        assert ipfs_warnings == [], [str(w.message) for w in ipfs_warnings]

        exported = set(getattr(mod, "__all__", []))
        missing_from_all = sorted(expected - exported)
        assert missing_from_all == [], (module_name, missing_from_all)

        missing_attrs = sorted(name for name in expected if not hasattr(mod, name))
        assert missing_attrs == [], (module_name, missing_attrs)


def test_integration_import_does_not_pull_engine_env_helper(monkeypatch):
    monkeypatch.delenv("IPFS_DATASETS_PY_WARN_OPTIONAL_IMPORTS", raising=False)
    monkeypatch.setenv("IPFS_DATASETS_SYMBOLICAI_AUTOCONFIGURE", "1")

    for name in list(sys.modules.keys()):
        if name == "ipfs_datasets_py" or name.startswith("ipfs_datasets_py."):
            sys.modules.pop(name, None)
    importlib.invalidate_caches()

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        integration = importlib.import_module("ipfs_datasets_py.logic.integration")

    ipfs_warnings = _ipfs_origin_warnings(recorded)
    assert ipfs_warnings == [], [str(w.message) for w in ipfs_warnings]

    assert getattr(integration, "SYMBOLIC_AI_AVAILABLE") is False
    assert "ipfs_datasets_py.utils.engine_env" not in set(sys.modules.keys())
