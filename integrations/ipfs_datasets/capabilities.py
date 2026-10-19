from __future__ import annotations

from functools import lru_cache

from .loader import (
    import_attr_optional,
    import_failure_message,
    import_failure_type,
    import_module_optional,
)
from .types import CapabilityStatus


@lru_cache(maxsize=1)
def get_ipfs_datasets_capabilities() -> dict[str, CapabilityStatus]:
    module_map = {
        "llm_router": {
            "module_path": "ipfs_accelerate_py.llm_router",
            "adapter_module": "integrations.ipfs_accelerate.routers",
            "contract_family": "generation",
            "owner": "ipfs_accelerate_py",
            "symbol": "generate_text",
            "bridge": "ipfs_datasets_py.llm_router",
            "public_adapter": "integrations.ipfs_datasets.llm",
        },
        "embeddings_router": {
            "module_path": "ipfs_accelerate_py.embeddings_router",
            "adapter_module": "integrations.ipfs_accelerate.routers",
            "contract_family": "retrieval",
            "owner": "ipfs_accelerate_py",
            "symbol": "embed_texts",
            "bridge": "ipfs_datasets_py.embeddings_router",
            "public_adapter": "integrations.ipfs_datasets.vector_store",
        },
        "multimodal_router": {
            "module_path": "ipfs_accelerate_py.multimodal_router",
            "adapter_module": "integrations.ipfs_accelerate.routers",
            "contract_family": "generation",
            "owner": "ipfs_accelerate_py",
            "symbol": "generate_multimodal_text",
            "bridge": "ipfs_datasets_py.multimodal_router",
            "public_adapter": "integrations.ipfs_datasets.multimodal",
        },
        "agent_supervisor": {
            "module_path": "ipfs_accelerate_py.agent_supervisor",
            "adapter_module": "integrations.ipfs_accelerate.supervisor",
            "contract_family": "supervision",
            "owner": "ipfs_accelerate_py",
            "probe": "agent_supervisor",
        },
        "ipfs_storage": {
            "module_path": "ipfs_kit_py",
            "adapter_module": "integrations.ipfs_datasets.storage",
            "contract_family": "storage",
            "owner": "ipfs_kit_py",
            "symbol": "OperationResult",
            "bridge": "ipfs_datasets_py.ipfs_backend_router",
        },
        "web_archiving": {
            "module_path": "ipfs_datasets_py.web_archiving",
            "adapter_module": "integrations.ipfs_datasets.search",
            "contract_family": "acquisition",
        },
        "common_crawl": {
            "module_path": "ipfs_datasets_py.processors.web_archiving.common_crawl_integration",
            "adapter_module": "integrations.ipfs_datasets.search",
            "contract_family": "acquisition",
        },
        "documents": {
            "module_path": "ipfs_datasets_py.processors",
            "adapter_module": "integrations.ipfs_datasets.documents",
            "contract_family": "documents",
        },
        "legal_scrapers": {
            "module_path": "ipfs_datasets_py.processors.legal_scrapers",
            "adapter_module": "integrations.ipfs_datasets.legal",
            "contract_family": "legal",
        },
        "knowledge_graphs": {
            "module_path": "ipfs_datasets_py.knowledge_graphs",
            "adapter_module": "integrations.ipfs_datasets.graphs",
            "contract_family": "graphs",
            "owner": "ipfs_datasets_py",
            "symbol": "Client",
        },
        "legal_data": {
            "module_path": "ipfs_datasets_py.processors.legal_data",
            "adapter_module": "integrations.ipfs_datasets.legal_data",
            "contract_family": "legal",
            "owner": "ipfs_datasets_py",
            "symbol": "DocketDatasetBuilder",
        },
        "multimedia": {
            "module_path": "ipfs_datasets_py.processors.multimedia",
            "adapter_module": "integrations.ipfs_datasets.multimedia",
            "contract_family": "documents",
            "owner": "ipfs_datasets_py",
            "symbol": "attachment_text_extractor",
        },
        "graphrag": {
            "module_path": "ipfs_datasets_py.optimizers.graphrag",
            "adapter_module": "integrations.ipfs_datasets.graphrag",
            "contract_family": "validation",
        },
        "logic_tools": {
            "module_path": "ipfs_datasets_py.logic",
            "adapter_module": "integrations.ipfs_datasets.logic",
            "contract_family": "validation",
            "owner": "ipfs_datasets_py",
            "canonical_modules": "logic.fol,logic.deontic,logic.integration,logic.external_provers,logic.TDFOL",
            "deprecated_upstream": "logic.tools",
        },
        "vector_store": {
            "module_path": "ipfs_datasets_py.vector_stores",
            "adapter_module": "integrations.ipfs_datasets.vector_store",
            "contract_family": "retrieval",
        },
        "mcp_gateway": {
            "module_path": "ipfs_datasets_py.mcp_server",
            "adapter_module": "integrations.ipfs_datasets.mcp_gateway",
            "contract_family": "mcp",
        },
    }
    capabilities: dict[str, CapabilityStatus] = {}
    for name, metadata in module_map.items():
        module_path = metadata["module_path"]
        owner = str(metadata.get("owner") or "ipfs_datasets_py")
        symbol = str(metadata.get("symbol") or "")
        if name == "legal_data":
            from .loader import get_repo_paths

            legal_dir = get_repo_paths().ipfs_datasets_repo / "ipfs_datasets_py" / "processors" / "legal_data"
            module = legal_dir if (legal_dir / "__init__.py").is_file() and (legal_dir / "docket_dataset.py").is_file() else None
            error = None if module is not None else "legal_data package is not in the datasets checkout"
            available = module is not None
        else:
            module, error = import_module_optional(module_path)
            available = module is not None
        if available and symbol and metadata.get("probe") != "agent_supervisor" and name != "legal_data":
            if owner == "ipfs_accelerate_py":
                from integrations.ipfs_accelerate.routers import router_symbol_status

                router_status = router_symbol_status(name)
                symbol_ok = bool(router_status["available"])
                symbol_error = router_status["error"] or None
            elif name == "multimedia":
                value, symbol_error = import_attr_optional(
                    "ipfs_datasets_py.processors.multimedia.attachment_text_extractor",
                    "extract_attachment_text",
                )
                symbol_ok = callable(value)
            else:
                value, symbol_error = import_attr_optional(module_path, symbol)
                symbol_ok = value is not None
            if not symbol_ok:
                available = False
                error = symbol_error or error
        if metadata.get("probe") == "agent_supervisor":
            from integrations.ipfs_accelerate.supervisor import probe_agent_supervisor

            probe = probe_agent_supervisor()
            available = bool(probe.get("available"))
            if not available:
                error = probe.get("error") or error
            metadata = {**metadata, "probe_result": "passed" if probe.get("probed") else "failed"}
        if name == "ipfs_storage" and not available:
            bridge, bridge_error = import_module_optional("ipfs_datasets_py.ipfs_backend_router")
            if bridge is not None:
                available = True
                error = None
            elif error is None:
                error = bridge_error
        degraded_reason = import_failure_message(error)
        details = {
            "capability": name,
            "error_type": import_failure_type(error),
            "adapter_module": metadata["adapter_module"],
            "contract_family": metadata["contract_family"],
            "owner": owner,
        }
        for field in ("bridge", "public_adapter", "canonical_modules", "deprecated_upstream", "probe_result"):
            if metadata.get(field):
                details[field] = metadata[field]
        capabilities[name] = CapabilityStatus(
            status="available" if available else "degraded",
            available=available,
            module_path=module_path,
            degraded_reason=degraded_reason,
            provider=owner,
            details=details,
        )
    return capabilities


def summarize_ipfs_datasets_capabilities() -> dict[str, str]:
    summary: dict[str, str] = {}
    for name, status in get_ipfs_datasets_capabilities().items():
        if status.available:
            summary[name] = "available"
        else:
            summary[name] = f"degraded: {status.degraded_reason or 'unavailable'}"
    return summary


def summarize_ipfs_datasets_capability_report() -> dict[str, object]:
    capabilities = get_ipfs_datasets_capabilities()
    available_capabilities = sorted(name for name, status in capabilities.items() if status.available)
    degraded_capabilities = {
        name: status.degraded_reason or "unavailable"
        for name, status in capabilities.items()
        if not status.available
    }
    family_counts: dict[str, int] = {}
    for status in capabilities.values():
        family = str(status.details.get("contract_family") or "")
        if not family:
            continue
        family_counts[family] = family_counts.get(family, 0) + 1
    return {
        "status": "available" if not degraded_capabilities else "degraded",
        "available_count": len(available_capabilities),
        "degraded_count": len(degraded_capabilities),
        "available_capabilities": available_capabilities,
        "degraded_capabilities": degraded_capabilities,
        "family_counts": family_counts,
        "capabilities": {
            name: status.as_dict()
            for name, status in capabilities.items()
        },
    }


def summarize_ipfs_datasets_startup_payload() -> dict[str, object]:
    capabilities = get_ipfs_datasets_capabilities()
    capability_report = summarize_ipfs_datasets_capability_report()
    return {
        "capability_report": capability_report,
        "capabilities": {
            name: status.as_dict()
            for name, status in capabilities.items()
        },
    }