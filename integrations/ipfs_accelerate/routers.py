"""Single production import path for accelerate inference routers.

Datasets modules named ``llm_router``, ``embeddings_router``, and
``multimodal_router`` are temporary aliases. New call sites use this facade,
which puts the accelerate checkout on ``sys.path`` before importing.
"""

from __future__ import annotations

from typing import Any

from integrations.ipfs_datasets.loader import ensure_import_paths, import_attr_optional, import_failure_message


COMPLAINT_PROVIDER_ALIASES = {
    "local": "local_hf",
    "local_hf": "local_hf",
    "hf": "local_hf",
    "huggingface": "hf_inference_api",
    "p2p": "p2p_task_queue",
    "p2p_task": "p2p_task_queue",
    "remote_queue": "p2p_task_queue",
    "task_queue": "p2p_task_queue",
}

# Names accelerate's routers accept. Complaint aliases are translated here,
# after the historical Hugging Face router rewrite in llm.py.
_ACCELERATE_PROVIDER_ALIASES = {
    "local": "huggingface",
    "local_hf": "huggingface",
    "hf": "huggingface",
    "hf_inference_api": "huggingface",
    "huggingface_inference": "huggingface",
    "huggingface_router": "huggingface",
    "system_one": "typesafe",
    "openai_vision": "openai",
}


def accelerate_provider_name(provider: str | None) -> str:
    """Return the complaint-facing provider id used by backend objects."""

    raw = str(provider or "").strip()
    if not raw:
        return ""
    return COMPLAINT_PROVIDER_ALIASES.get(raw.lower(), raw)


def normalize_accelerate_provider(provider: str | None) -> str | None:
    """Map a complaint provider id onto the accelerate router provider id."""

    raw = str(provider or "").strip()
    if not raw:
        return None
    mapped = _ACCELERATE_PROVIDER_ALIASES.get(raw.lower(), raw)
    return mapped or None


def _load_symbol(module_name: str, attr_name: str) -> tuple[Any | None, Any]:
    ensure_import_paths(module_name)
    return import_attr_optional(module_name, attr_name)


def load_llm_symbols() -> tuple[Any | None, Any | None, Any]:
    generate_text, error = _load_symbol("ipfs_accelerate_py.llm_router", "generate_text")
    trace, trace_error = _load_symbol("ipfs_accelerate_py.llm_router", "get_last_generation_trace")
    return generate_text, trace, error or trace_error


def load_embedding_symbols() -> tuple[Any | None, Any | None, Any | None, Any | None, Any | None, Any]:
    from integrations.ipfs_datasets.loader import import_module_optional

    module_name = "ipfs_accelerate_py.embeddings_router"
    ensure_import_paths(module_name)
    embed_text, embed_text_error = import_attr_optional(module_name, "embed_text")
    embed_texts, embed_texts_error = import_attr_optional(module_name, "embed_texts")
    embed_texts_batched, batched_error = import_attr_optional(module_name, "embed_texts_batched")
    router_cls, router_error = import_attr_optional(module_name, "EmbeddingsRouter")
    embeddings_module, embeddings_module_error = import_module_optional(module_name)
    return (
        embed_text,
        embed_texts,
        embed_texts_batched,
        router_cls,
        embeddings_module,
        embed_text_error or embed_texts_error or batched_error or router_error or embeddings_module_error,
    )


def load_multimodal_symbols() -> tuple[Any | None, Any | None, Any | None, Any]:
    module_name = "ipfs_accelerate_py.multimodal_router"
    generate_multimodal_text, generate_error = _load_symbol(module_name, "generate_multimodal_text")
    build_multimodal_messages, messages_error = _load_symbol(module_name, "build_multimodal_messages")
    encode_image_as_data_url, encode_error = _load_symbol(module_name, "encode_image_as_data_url")
    return (
        generate_multimodal_text,
        build_multimodal_messages,
        encode_image_as_data_url,
        generate_error or messages_error or encode_error,
    )


def load_multimodal_generate() -> tuple[Any | None, Any]:
    return _load_symbol("ipfs_accelerate_py.multimodal_router", "generate_multimodal")


def router_symbol_status(loader_name: str) -> dict[str, Any]:
    """Return availability for one accelerate router without raising."""

    loaders = {
        "llm_router": lambda: load_llm_symbols()[0],
        "embeddings_router": lambda: load_embedding_symbols()[1],
        "multimodal_router": lambda: load_multimodal_symbols()[0],
    }
    loader = loaders.get(loader_name)
    if loader is None:
        return {"available": False, "error": f"unknown router {loader_name}"}
    try:
        symbol = loader()
    except Exception as exc:
        return {"available": False, "error": import_failure_message(exc) or str(exc)}
    return {"available": callable(symbol), "error": "" if callable(symbol) else "router symbol is not callable"}


__all__ = [
    "COMPLAINT_PROVIDER_ALIASES",
    "accelerate_provider_name",
    "load_embedding_symbols",
    "load_llm_symbols",
    "load_multimodal_generate",
    "load_multimodal_symbols",
    "normalize_accelerate_provider",
    "router_symbol_status",
]
