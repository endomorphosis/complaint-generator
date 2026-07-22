from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "CapabilityStatus": "capabilities",
    "get_ipfs_datasets_capabilities": "capabilities",
    "summarize_ipfs_datasets_capability_report": "capabilities",
    "summarize_ipfs_datasets_capabilities": "capabilities",
    "summarize_ipfs_datasets_startup_payload": "capabilities",
    "CaseArtifact": "types",
    "CaseAuthority": "types",
    "CaseClaimElement": "types",
    "CaseFact": "types",
    "CaseSupportEdge": "types",
    "DocumentChunk": "types",
    "DocumentParseResult": "types",
    "DocumentParseSummary": "types",
    "DocumentTransformLineage": "types",
    "GraphEntity": "types",
    "GraphPayload": "types",
    "GraphRelationship": "types",
    "GraphSnapshotResult": "types",
    "GraphSupportMatch": "types",
    "GraphSupportResult": "types",
    "GraphSupportSummary": "types",
    "FormalPredicate": "types",
    "ProvenanceRecord": "types",
    "ValidationRun": "types",
    "normalize_degraded_reason": "types",
    "with_adapter_metadata": "types",
    "discover_seeded_commoncrawl": "search",
    "download_url": "search",
    "download_with_recovery": "search",
    "evaluate_scraped_content": "search",
    "recover_manifest_downloads": "search",
    "scrape_archived_domain": "search",
    "scrape_web_content": "search",
    "search_brave_web": "search",
    "search_multi_engine_web": "search",
    "DOCUMENTS_AVAILABLE": "documents",
    "DOCUMENTS_ERROR": "documents",
    "extract_text_content": "documents",
    "ingest_download_manifest": "documents",
    "ingest_local_document": "documents",
    "parse_document": "documents",
    "parse_pdf_to_record": "documents",
    "generate_text_with_metadata": "llm",
    "llm_router_status": "llm",
    "get_router_status_report": "router_status",
    "build_ontology": "graphrag",
    "validate_ontology": "graphrag",
    "run_refinement_cycle": "graphrag",
    "ingest_pdf_to_graphrag": "graphrag",
    "extract_pdf_entities": "graphrag",
    "analyze_pdf_relationships": "graphrag",
    "cross_analyze_pdf_documents": "graphrag",
    "batch_process_pdfs": "graphrag",
    "query_pdf_knowledge_graph": "graphrag",
    "build_policy_rule_corpus": "policy_rules",
    "extract_policy_rules_from_pdf": "policy_rules",
    "pin_cid": "storage",
    "retrieve_bytes": "storage",
    "storage_backend_status": "storage",
    "store_bytes": "storage",
    "LocalCacheIPFSBackend": "storage",
    "clear_ipfs_backend_router_caches": "storage",
    "ensure_ipfs_backend": "storage",
    "set_default_ipfs_backend": "storage",
    "EMBEDDINGS_AVAILABLE": "vector_store",
    "EMBEDDINGS_ERROR": "vector_store",
    "VECTOR_STORE_AVAILABLE": "vector_store",
    "VECTOR_STORE_ERROR": "vector_store",
    "create_vector_store_async": "vector_store",
    "embeddings_backend_status": "vector_store",
    "vector_index_backend_status": "vector_store",
    "create_vector_index": "vector_store",
    "get_embeddings_router": "vector_store",
    "search_vector_index": "vector_store",
}

__all__ = list(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(f"{__name__}.{module_name}")
    value = getattr(module, name)
    globals()[name] = value
    return value
