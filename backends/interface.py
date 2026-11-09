"""Versioned public surface for router backends.

Importing this module does not import the router implementation or a
provider backend. The first access of each name loads that object."""

from __future__ import annotations

import importlib

INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
MODULE = "backends.interface"

OWNER_MODULES = (
    "backends.llm_router_backend",
)

_LAZY_EXPORTS = {
    "LLMRouterBackend": ("backends.llm_router_backend", "LLMRouterBackend"),
    "load_terminal_router_backend": ("backends.llm_router_backend", "load_terminal_router_backend"),
}


def __getattr__(name: str):
    """Load a facade name from its owner module on first access."""
    spec = _LAZY_EXPORTS.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = spec
    owner = importlib.import_module(module_name)
    value = owner if attr is None else getattr(owner, attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
