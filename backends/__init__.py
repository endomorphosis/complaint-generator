"""Backend registry for complaint-generator.

Router-first: prefer `LLMRouterBackend`.

Legacy OpenAI/HuggingFace backends still exist as deprecated modules under
`backends.openai`, `backends.huggingface`, and `backends.openaibackend`, but
they are not imported here to avoid triggering warnings on normal imports.
"""

from importlib import import_module

_LAZY_EXPORTS = {
    'WorkstationBackendModels': ('.workstation', 'WorkstationBackendModels'),
    'WorkstationBackendDatabases': ('.workstation', 'WorkstationBackendDatabases'),
    'WorkstationLoadProfileState': ('.workstation', 'WorkstationLoadProfileState'),
    'WorkstationSaveProfileState': ('.workstation', 'WorkstationSaveProfileState'),
    'LLMRouterBackend': ('.llm_router_backend', 'LLMRouterBackend'),
    'LLMRouter': ('.llm_router_backend', 'LLMRouter'),
    'MultimodalRouter': ('.multimodal_router_backend', 'MultimodalRouter'),
    'MultimodalRouterBackend': ('.multimodal_router_backend', 'MultimodalRouterBackend'),
}

__all__ = [
    'WorkstationBackendModels',
    'WorkstationBackendDatabases',
    'WorkstationLoadProfileState',
    'WorkstationSaveProfileState',
    'LLMRouterBackend',
    'LLMRouter',
    'MultimodalRouter',
    'MultimodalRouterBackend',
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
