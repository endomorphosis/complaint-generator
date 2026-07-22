from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .loader import ImportFailure, build_import_failure_diagnostic, import_module_optional
from .types import CapabilityStatus


CAPABILITY_SCHEMA_VERSION = "ipfs-datasets-capabilities/v1"


@dataclass(frozen=True)
class CapabilityDefinition:
    """Static metadata for one public adapter capability group."""

    name: str
    module_path: str
    adapter_module: str
    contract_family: str
    install_extra: str


# This is the canonical adapter-group contract.  It is deliberately independent
# of import results so full, partial, and degraded environments expose the same
# ordered keys.  Groups backed only by local normalization code are omitted;
# every entry here describes an optional upstream provider boundary.
CAPABILITY_DEFINITIONS = (
    CapabilityDefinition(
        "llm_router",
        "ipfs_datasets_py.llm_router",
        "integrations.ipfs_datasets.llm",
        "generation",
        "api",
    ),
    CapabilityDefinition(
        "multimodal_router",
        "ipfs_datasets_py.multimodal_router",
        "integrations.ipfs_datasets.multimodal",
        "generation",
        "api",
    ),
    CapabilityDefinition(
        "ipfs_storage",
        "ipfs_datasets_py.ipfs_backend_router",
        "integrations.ipfs_datasets.storage",
        "storage",
        "ipld",
    ),
    CapabilityDefinition(
        "web_archiving",
        "ipfs_datasets_py.web_archiving",
        "integrations.ipfs_datasets.search",
        "acquisition",
        "scraping",
    ),
    CapabilityDefinition(
        "common_crawl",
        "ipfs_datasets_py.processors.web_archiving.common_crawl_integration",
        "integrations.ipfs_datasets.search",
        "acquisition",
        "scraping",
    ),
    CapabilityDefinition(
        "documents",
        "ipfs_datasets_py.processors",
        "integrations.ipfs_datasets.documents",
        "documents",
        "file_conversion",
    ),
    CapabilityDefinition(
        "legal_scrapers",
        "ipfs_datasets_py.processors.legal_scrapers",
        "integrations.ipfs_datasets.legal",
        "legal",
        "scraping,vectors",
    ),
    CapabilityDefinition(
        "knowledge_graphs",
        "ipfs_datasets_py.knowledge_graphs",
        "integrations.ipfs_datasets.graphs",
        "graphs",
        "knowledge_graphs",
    ),
    CapabilityDefinition(
        "graphrag",
        "ipfs_datasets_py.optimizers.graphrag",
        "integrations.ipfs_datasets.graphrag",
        "validation",
        "knowledge_graphs,logic",
    ),
    CapabilityDefinition(
        "logic_tools",
        "ipfs_datasets_py.logic",
        "integrations.ipfs_datasets.logic",
        "validation",
        "logic",
    ),
    CapabilityDefinition(
        "policy_rules",
        "ipfs_datasets_py.processors.file_converter.converter",
        "integrations.ipfs_datasets.policy_rules",
        "validation",
        "file_conversion,knowledge_graphs",
    ),
    CapabilityDefinition(
        "vector_store",
        "ipfs_datasets_py.vector_stores",
        "integrations.ipfs_datasets.vector_store",
        "retrieval",
        "vectors",
    ),
    CapabilityDefinition(
        "mcp_gateway",
        "ipfs_datasets_py.mcp_server",
        "integrations.ipfs_datasets.mcp_gateway",
        "mcp",
        "api",
    ),
)

CAPABILITY_NAMES = tuple(definition.name for definition in CAPABILITY_DEFINITIONS)
# Descriptive alias for report consumers and compatibility with early callers.
CAPABILITY_GROUP_KEYS = CAPABILITY_NAMES


def _probe_capability(definition: CapabilityDefinition) -> CapabilityStatus:
    module, error = import_module_optional(definition.module_path)
    available = module is not None
    if not available and error is None:
        # Optional import helpers normally return a typed error.  Synthesize one
        # if an alternate implementation returns ``(None, None)`` so degraded
        # status can never collapse back to a generic "unavailable" string.
        error = ImportFailure(
            module_name=definition.module_path,
            error_type="ModuleNotFoundError",
            message=f"No module named '{definition.module_path}'",
            missing_module_name=definition.module_path,
        )
    diagnostic = build_import_failure_diagnostic(
        None if available else error,
        module_name=definition.module_path,
        capability=definition.name,
        install_extra=definition.install_extra,
    )
    return CapabilityStatus(
        status="available" if available else "degraded",
        available=available,
        module_path=definition.module_path,
        degraded_reason=diagnostic["degraded_reason"],
        details={
            "capability": definition.name,
            "adapter_module": definition.adapter_module,
            "contract_family": definition.contract_family,
            "install_extra": definition.install_extra,
            **diagnostic,
        },
    )


@lru_cache(maxsize=1)
def get_ipfs_datasets_capabilities() -> dict[str, CapabilityStatus]:
    """Return capability status for every optional IPFS datasets adapter group.

    Probes are cached because importing the provider can be expensive.  Call
    ``get_ipfs_datasets_capabilities.cache_clear()`` after changing installed
    extras in a long-running process.
    """

    return {
        definition.name: _probe_capability(definition)
        for definition in CAPABILITY_DEFINITIONS
    }


def summarize_ipfs_datasets_capabilities() -> dict[str, str]:
    """Return a compact, human-readable summary with the canonical group keys."""

    return {
        name: (
            "available"
            if status.available
            else f"degraded: {status.degraded_reason or 'optional provider unavailable'}"
        )
        for name, status in get_ipfs_datasets_capabilities().items()
    }


def summarize_ipfs_datasets_capability_report() -> dict[str, object]:
    capabilities = get_ipfs_datasets_capabilities()
    available_capabilities = sorted(
        name for name, status in capabilities.items() if status.available
    )
    degraded_capabilities = {
        name: status.degraded_reason or "optional provider unavailable"
        for name, status in capabilities.items()
        if not status.available
    }
    family_counts: dict[str, int] = {}
    for status in capabilities.values():
        family = str(status.details.get("contract_family") or "")
        if family:
            family_counts[family] = family_counts.get(family, 0) + 1

    available = not degraded_capabilities
    degraded_reason = None
    if degraded_capabilities:
        degraded_reason = (
            f"{len(degraded_capabilities)} optional capability group(s) are degraded: "
            f"{', '.join(sorted(degraded_capabilities))}. "
            "See degraded_capabilities for remediation."
        )

    return {
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "status": "available" if available else "degraded",
        "available": available,
        "degraded_reason": degraded_reason,
        "available_count": len(available_capabilities),
        "degraded_count": len(degraded_capabilities),
        "capability_keys": list(CAPABILITY_NAMES),
        "available_capabilities": available_capabilities,
        "degraded_capabilities": degraded_capabilities,
        "family_counts": family_counts,
        "capabilities": {
            name: status.as_dict() for name, status in capabilities.items()
        },
    }


def summarize_ipfs_datasets_startup_payload() -> dict[str, object]:
    capability_report = summarize_ipfs_datasets_capability_report()
    return {
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "status": capability_report["status"],
        "available": capability_report["available"],
        "degraded_reason": capability_report["degraded_reason"],
        "capability_report": capability_report,
        "capabilities": capability_report["capabilities"],
    }
