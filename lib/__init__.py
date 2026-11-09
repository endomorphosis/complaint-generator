"""Shared reusable library helpers for complaint-generator."""

from importlib import import_module

_LAZY_EXPORTS = {
    'deontic_logic': ('.deontic_logic', None),
    'document_render': ('.document_render', None),
    'formal_logic': ('.formal_logic', None),
    'legal_document': ('.legal_document', None),
    'runtime_ownership': ('.runtime_ownership', None),
    'support_map': ('.support_map', None),
}

__all__ = [
    'deontic_logic',
    'document_render',
    'formal_logic',
    'legal_document',
    'runtime_ownership',
    'support_map',
]


def __getattr__(name: str):
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(module_name, __name__)
    value = module if attribute_name is None else getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
