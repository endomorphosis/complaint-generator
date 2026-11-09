"""Versioned public surface for the adversarial harness.

Importing this module does not import the harness, optimizer, or session
owners. The first access of each name loads that class."""

from __future__ import annotations

import importlib

INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
MODULE = "adversarial_harness.interface"

OWNER_MODULES = (
    "adversarial_harness.harness",
    "adversarial_harness.optimizer",
    "adversarial_harness.session",
)

_LAZY_EXPORTS = {
    "AdversarialHarness": ("adversarial_harness.harness", "AdversarialHarness"),
    "Optimizer": ("adversarial_harness.optimizer", "Optimizer"),
    "AdversarialSession": ("adversarial_harness.session", "AdversarialSession"),
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
