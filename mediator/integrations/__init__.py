"""Integration primitives for ipfs_datasets_py enhancements."""

from importlib import import_module

_LAZY_EXPORTS = {
    "IPFSDatasetsAdapter": (".adapter", "IPFSDatasetsAdapter"),
    "detect_ipfs_datasets_capabilities": (".adapter", "detect_ipfs_datasets_capabilities"),
    "CapabilityCatalog": (".contracts", "CapabilityCatalog"),
    "CapabilityStatus": (".contracts", "CapabilityStatus"),
    "NormalizedRetrievalBundle": (".contracts", "NormalizedRetrievalBundle"),
    "NormalizedRetrievalRecord": (".contracts", "NormalizedRetrievalRecord"),
    "IntegrationFeatureFlags": (".settings", "IntegrationFeatureFlags"),
    "RetrievalOrchestrator": (".retrieval_orchestrator", "RetrievalOrchestrator"),
    "ProvenanceRecord": (".provenance", "ProvenanceRecord"),
    "build_provenance_record": (".provenance", "build_provenance_record"),
    "TTLCache": (".caching", "TTLCache"),
    "VectorRetrievalAugmentor": (".vector_tools", "VectorRetrievalAugmentor"),
    "GraphRetrievalAugmentor": (".graph_tools", "GraphRetrievalAugmentor"),
    "GraphAwareRetrievalReranker": (".graph_tools", "GraphAwareRetrievalReranker"),
}

__all__ = [
    "IPFSDatasetsAdapter",
    "detect_ipfs_datasets_capabilities",
    "CapabilityCatalog",
    "CapabilityStatus",
    "NormalizedRetrievalBundle",
    "NormalizedRetrievalRecord",
    "IntegrationFeatureFlags",
    "RetrievalOrchestrator",
    "ProvenanceRecord",
    "build_provenance_record",
    "TTLCache",
    "VectorRetrievalAugmentor",
    "GraphRetrievalAugmentor",
    "GraphAwareRetrievalReranker",
]


def __getattr__(name: str):
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(module_name, __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
