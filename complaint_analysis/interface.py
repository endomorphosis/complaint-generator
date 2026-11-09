"""Versioned public surface for complaint analysis.

Importing this module does not import the analyzer, pattern, or parser
owners. The first access of each name loads that class."""

from __future__ import annotations

import importlib

INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
MODULE = "complaint_analysis.interface"

OWNER_MODULES = (
    "complaint_analysis.analyzer",
    "complaint_analysis.legal_patterns",
    "complaint_analysis.response_parsers",
)

_LAZY_EXPORTS = {
    "ComplaintAnalyzer": ("complaint_analysis.analyzer", "ComplaintAnalyzer"),
    "LegalPatternExtractor": ("complaint_analysis.legal_patterns", "LegalPatternExtractor"),
    "ResponseParserFactory": ("complaint_analysis.response_parsers", "ResponseParserFactory"),
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
