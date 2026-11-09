"""Versioned public surface over the three integration facades.

Importing this module records those facade modules. It does not import
private storage or datasets legal logic."""

from __future__ import annotations

import importlib

INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
MODULE = "integrations.interface"

OWNER_MODULES = (
    "integrations.ipfs_datasets.interface",
    "integrations.mike.interface",
    "integrations.ipfs_accelerate.interface",
)

_LAZY_EXPORTS = {
    "ipfs_datasets": ("integrations.ipfs_datasets.interface", None),
    "mike": ("integrations.mike.interface", None),
    "ipfs_accelerate": ("integrations.ipfs_accelerate.interface", None),
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
