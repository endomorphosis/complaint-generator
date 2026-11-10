"""Complaint-generator facade for ipfs_accelerate_py inference and supervision."""

import importlib

__all__ = [
    "COMPLAINT_PROVIDER_ALIASES",
    "accelerate_provider_name",
    "load_embedding_symbols",
    "load_llm_symbols",
    "load_multimodal_symbols",
    "normalize_accelerate_provider",
]

_OWNER = "routers"
_EXPORTS = {name: _OWNER for name in __all__}


def __getattr__(name: str):
    owner = _EXPORTS.get(name)
    if owner is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module("." + owner, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
