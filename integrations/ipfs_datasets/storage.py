from __future__ import annotations

import os
import hashlib
import shutil
from pathlib import Path
from typing import Any

from .loader import get_repo_paths, import_attr_optional
from .types import with_adapter_metadata


add_bytes, _add_error = import_attr_optional("ipfs_datasets_py.ipfs_backend_router", "add_bytes")
cat, _cat_error = import_attr_optional("ipfs_datasets_py.ipfs_backend_router", "cat")
pin, _pin_error = import_attr_optional("ipfs_datasets_py.ipfs_backend_router", "pin")
get_ipfs_backend, _backend_error = import_attr_optional(
    "ipfs_datasets_py.ipfs_backend_router",
    "get_ipfs_backend",
)
set_default_ipfs_backend, _set_default_error = import_attr_optional(
    "ipfs_datasets_py.ipfs_backend_router",
    "set_default_ipfs_backend",
)
clear_ipfs_backend_router_caches, _clear_cache_error = import_attr_optional(
    "ipfs_datasets_py.ipfs_backend_router",
    "clear_ipfs_backend_router_caches",
)

IPFS_AVAILABLE = all(value is not None for value in (add_bytes, cat, pin))
IPFS_ERROR = _add_error or _cat_error or _pin_error or _backend_error or _set_default_error or _clear_cache_error

if get_ipfs_backend is None:
    def get_ipfs_backend() -> Any:
        return None

if set_default_ipfs_backend is None:
    def set_default_ipfs_backend(_backend: Any) -> None:
        return None

if clear_ipfs_backend_router_caches is None:
    def clear_ipfs_backend_router_caches() -> None:
        return None


class LocalCacheIPFSBackend:
    """Content-addressed local fallback for environments without a working IPFS daemon."""

    def __init__(self, cache_dir: str | None = None) -> None:
        root = cache_dir or os.environ.get("COMPLAINT_GENERATOR_IPFS_CACHE_DIR", "").strip()
        self.cache_dir = Path(root or (Path.home() / ".cache" / "complaint-generator" / "ipfs_fallback"))
        self.blobs_dir = self.cache_dir / "blobs"
        self.pins_dir = self.cache_dir / "pins"
        self.blobs_dir.mkdir(parents=True, exist_ok=True)
        self.pins_dir.mkdir(parents=True, exist_ok=True)

    def _blob_path(self, cid: str) -> Path:
        return self.blobs_dir / cid

    def _pin_path(self, cid: str) -> Path:
        return self.pins_dir / cid

    def _cid_for_bytes(self, data: bytes) -> str:
        return f"bafy{hashlib.sha256(data).hexdigest()[:55]}"

    def add_bytes(self, data: bytes, *, pin: bool = True) -> str:
        cid = self._cid_for_bytes(data)
        self._blob_path(cid).write_bytes(data)
        if pin:
            self.pin(cid)
        return cid

    def cat(self, cid: str) -> bytes:
        return self._blob_path(cid).read_bytes()

    def pin(self, cid: str) -> None:
        if not self._blob_path(cid).exists():
            raise FileNotFoundError(f"unknown cid: {cid}")
        self._pin_path(cid).write_text("", encoding="utf-8")

    def unpin(self, cid: str) -> None:
        self._pin_path(cid).unlink(missing_ok=True)

    def block_put(self, data: bytes, *, codec: str = "raw") -> str:
        _ = codec
        return self.add_bytes(data, pin=False)

    def block_get(self, cid: str) -> bytes:
        return self.cat(cid)

    def add_path(self, path: str, *, recursive: bool = True, pin: bool = True, chunker: str | None = None) -> str:
        _ = recursive, chunker
        return self.add_bytes(Path(path).read_bytes(), pin=pin)

    def get_to_path(self, cid: str, *, output_path: str) -> None:
        Path(output_path).write_bytes(self.cat(cid))

    def ls(self, cid: str) -> list[str]:
        _ = cid
        return []

    def dag_export(self, cid: str) -> bytes:
        return self.cat(cid)


def ensure_ipfs_backend(*, prefer_local_fallback: bool = False, cache_dir: str | None = None) -> Any:
    if not IPFS_AVAILABLE:
        return None

    try:
        backend = get_ipfs_backend()
    except Exception:
        backend = None

    backend_name = type(backend).__name__ if backend is not None else ""
    if prefer_local_fallback and (
        backend is None
        or (
            backend_name == "KuboCLIBackend"
            and not shutil.which(str(getattr(backend, "_cmd", None) or "ipfs"))
        )
    ):
        fallback_backend = LocalCacheIPFSBackend(cache_dir=cache_dir)
        set_default_ipfs_backend(fallback_backend)
        clear_ipfs_backend_router_caches()
        return fallback_backend

    return backend


def _repo_local_ipfs_kit_root() -> Path:
    kit_repo = get_repo_paths().ipfs_kit_repo
    if kit_repo is not None:
        return kit_repo
    return Path(__file__).resolve().parents[2] / "external" / "ipfs_kit_py"


def _discover_repo_local_kubo_cmd() -> str:
    configured = os.environ.get("IPFS_DATASETS_PY_KUBO_CMD", "").strip()
    if configured:
        return configured

    env_cmd = os.environ.get("KUBO_CMD", "").strip()
    if env_cmd:
        return env_cmd

    resolved_path = shutil.which("ipfs")
    if resolved_path:
        return resolved_path

    candidate = _repo_local_ipfs_kit_root() / "bin" / "ipfs"
    if candidate.exists():
        return str(candidate)

    return ""


def _discover_repo_local_ipfs_path() -> str:
    configured = os.environ.get("IPFS_PATH", "").strip()
    if configured:
        return configured

    candidate = _repo_local_ipfs_kit_root() / ".ipfs"
    config_path = candidate / "config"
    if config_path.exists():
        return str(candidate)

    return ""


def _ensure_local_kubo_environment() -> str:
    """Discover local Kubo configuration without leaking probe state.

    Runtime probes may be called repeatedly under different environments (for
    example after an operator installs or removes Kubo).  Writing an
    auto-discovered command into ``os.environ`` made the first probe override
    all later discovery and could falsely report a missing backend as healthy.
    Explicit environment settings remain honored by the discovery helpers.
    """
    discovered_cmd = _discover_repo_local_kubo_cmd()
    return discovered_cmd


def _runtime_backend_probe() -> dict[str, Any]:
    discovered_cmd = _ensure_local_kubo_environment()
    if os.environ.get("COMPLAINT_GENERATOR_ENABLE_LOCAL_IPFS_FALLBACK", "").strip().lower() in {"1", "true", "yes", "on"}:
        ensure_ipfs_backend(prefer_local_fallback=True)
    if not IPFS_AVAILABLE:
        return {
            "backend": None,
            "backend_name": "",
            "status": "unavailable",
            "reason": IPFS_ERROR or "ipfs router unavailable",
        }

    try:
        backend = get_ipfs_backend()
    except Exception as exc:
        return {
            "backend": None,
            "backend_name": "",
            "status": "unavailable",
            "reason": str(exc),
        }

    backend_name = type(backend).__name__ if backend is not None else ""
    if backend is None:
        return {
            "backend": None,
            "backend_name": backend_name,
            "status": "unavailable",
            "reason": "no backend instance resolved",
        }

    cmd = getattr(backend, "_cmd", None)
    if backend_name == "KuboCLIBackend":
        resolved = shutil.which(str(cmd or "ipfs"))
        if not resolved and discovered_cmd:
            resolved = discovered_cmd
            try:
                setattr(backend, "_cmd", discovered_cmd)
            except Exception as exc:
                return {
                    "backend": backend,
                    "backend_name": backend_name,
                    "status": "unavailable",
                    "reason": (
                        "failed to configure discovered ipfs CLI binary "
                        f"{discovered_cmd!r}: {type(exc).__name__}: {exc}"
                    ),
                }
        if not resolved:
            return {
                "backend": backend,
                "backend_name": backend_name,
                "status": "unavailable",
                "reason": f"missing ipfs CLI binary: {cmd or 'ipfs'}",
            }

    return {
        "backend": backend,
        "backend_name": backend_name,
        "status": "available",
        "reason": "",
    }


def translate_kit_operation_result(result: Any, *, backend_name: str = "kit") -> dict[str, Any]:
    """Map a kit OperationResult, or a dict/string from IPFSSimpleAPI, onto the storage dict."""

    data = None
    if isinstance(result, (bytes, bytearray)):
        return {
            "cid": "",
            "status": "available",
            "backend_name": backend_name,
            "data": bytes(result),
            "error": "",
        }
    if isinstance(result, str) and result:
        return {"cid": result, "status": "available", "backend_name": backend_name, "data": None, "error": ""}

    if isinstance(result, dict):
        success = result.get("success")
        cid = str(result.get("cid") or result.get("resulting_content_cid") or result.get("Hash") or "")
        error = result.get("error")
        data = result.get("data")
        state = str(result.get("state") or result.get("status") or "")
    else:
        success = getattr(result, "success", None)
        cid = str(getattr(result, "resulting_content_cid", "") or getattr(result, "cid", "") or "")
        error = getattr(result, "error", None)
        data = getattr(result, "data", None)
        state = str(getattr(result, "state", "") or "")

    if success is False or state.lower() in {"error", "failed", "failure"}:
        return {
            "cid": cid,
            "status": "error",
            "backend_name": backend_name,
            "data": data,
            "error": str(error or "kit operation failed"),
        }
    if success is True or cid or isinstance(data, (bytes, bytearray)):
        return {"cid": cid, "status": "available", "backend_name": backend_name, "data": data, "error": ""}
    return {
        "cid": cid,
        "status": "error",
        "backend_name": backend_name,
        "data": data,
        "error": str(error or "kit operation did not return a cid"),
    }


def _kit_enabled() -> bool:
    return os.environ.get("COMPLAINT_GENERATOR_ENABLE_IPFS_KIT", "").strip().lower() in {"1", "true", "yes", "on"}


def _load_optional_kit_backend() -> Any:
    """Return an IPFSSimpleAPI only when kit storage is explicitly enabled.

    CanonicalStorageService is an execute() protocol and does not expose
    add_bytes/cat/pin. IPFSSimpleAPI construction can start a node, so the
    default path keeps the datasets router and the local cache.
    """

    if not _kit_enabled():
        return None
    from .loader import ensure_import_paths

    ensure_import_paths("ipfs_kit_py")
    simple_api, _error = import_attr_optional("ipfs_kit_py", "IPFSSimpleAPI")
    canonical, _canonical_error = import_attr_optional("ipfs_kit_py", "CanonicalStorageService")
    if canonical is not None and all(callable(getattr(canonical, name, None)) for name in ("add_bytes", "cat", "pin")):
        try:
            return canonical()
        except Exception:
            pass
    if simple_api is None:
        return None
    try:
        return simple_api()
    except Exception:
        return None


def _storage_error_type() -> type[BaseException]:
    error_type, _error = import_attr_optional("ipfs_kit_py", "StorageError")
    if isinstance(error_type, type) and issubclass(error_type, BaseException):
        return error_type
    return Exception


def _invoke_byte_backend(backend: Any, action: str, payload: Any, *, pin_content: bool = True) -> Any:
    if action == "add":
        if callable(getattr(backend, "add_bytes", None)):
            return backend.add_bytes(payload, pin=pin_content)
        if callable(getattr(backend, "add", None)):
            return backend.add(payload, pin=pin_content)
    if action == "cat" and callable(getattr(backend, "cat", None)):
        return backend.cat(payload)
    if action == "pin" and callable(getattr(backend, "pin", None)):
        return backend.pin(payload)
    raise RuntimeError(f"storage backend does not implement {action}")


def _result_from_backend_call(raw: Any, *, backend_name: str, fallback_cid: str = "") -> dict[str, Any]:
    if isinstance(raw, str) and raw:
        return {"cid": raw, "status": "available", "backend_name": backend_name, "data": None, "error": ""}
    if isinstance(raw, (bytes, bytearray)):
        return {"cid": fallback_cid, "status": "available", "backend_name": backend_name, "data": bytes(raw), "error": ""}
    translated = translate_kit_operation_result(raw, backend_name=backend_name)
    if not translated.get("cid") and fallback_cid:
        translated["cid"] = fallback_cid
    return translated


def _finish_storage_call(
    translated: dict[str, Any],
    *,
    operation: str,
    size: int = 0,
    pinned: bool | None = None,
    cid: str = "",
) -> dict[str, Any]:
    status = str(translated.get("status") or "error")
    payload: dict[str, Any] = {
        "status": status,
        "cid": str(translated.get("cid") or cid or ""),
        "backend_name": str(translated.get("backend_name") or ""),
        "error": str(translated.get("error") or ""),
    }
    if operation == "store_bytes":
        payload["size"] = size
        payload["pinned"] = bool(pinned)
    elif operation == "retrieve_bytes":
        data = translated.get("data")
        payload["data"] = bytes(data) if isinstance(data, (bytes, bytearray)) else b""
        payload["size"] = len(payload["data"])
    elif operation == "pin_cid":
        payload["pinned"] = status == "available"
        payload["result"] = translated.get("data")
    return with_adapter_metadata(
        payload,
        operation=operation,
        backend_available=status == "available",
        degraded_reason=payload["error"] or None,
        implementation_status="available" if status == "available" else "degraded",
        extra_metadata={"backend_name": payload["backend_name"]},
    )


def _store_with_object(backend: Any, data: bytes, *, pin_content: bool, backend_name: str) -> dict[str, Any]:
    raw = _invoke_byte_backend(backend, "add", data, pin_content=pin_content)
    translated = _result_from_backend_call(raw, backend_name=backend_name)
    if translated["status"] != "available":
        raise RuntimeError(translated["error"] or "kit add failed")
    return _finish_storage_call(translated, operation="store_bytes", size=len(data), pinned=pin_content)


def _retrieve_with_object(backend: Any, cid: str, *, backend_name: str) -> dict[str, Any]:
    raw = _invoke_byte_backend(backend, "cat", cid)
    translated = _result_from_backend_call(raw, backend_name=backend_name, fallback_cid=cid)
    if translated["status"] != "available":
        raise RuntimeError(translated["error"] or "kit cat failed")
    return _finish_storage_call(translated, operation="retrieve_bytes", cid=cid)


def _pin_with_object(backend: Any, cid: str, *, backend_name: str) -> dict[str, Any]:
    raw = _invoke_byte_backend(backend, "pin", cid)
    translated = _result_from_backend_call(raw if raw is not None else {"success": True, "cid": cid}, backend_name=backend_name, fallback_cid=cid)
    if translated["status"] != "available":
        raise RuntimeError(translated["error"] or "kit pin failed")
    return _finish_storage_call(translated, operation="pin_cid", cid=cid)


def _local_cache_store(data: bytes, *, pin_content: bool, reason: str) -> dict[str, Any]:
    cid = LocalCacheIPFSBackend().add_bytes(data, pin=pin_content)
    return _finish_storage_call(
        {"cid": cid, "status": "degraded", "backend_name": "local_cache", "error": reason},
        operation="store_bytes",
        size=len(data),
        pinned=pin_content,
    )


def _local_cache_retrieve(cid: str, *, reason: str) -> dict[str, Any]:
    try:
        payload = LocalCacheIPFSBackend().cat(cid)
    except Exception as exc:
        return _finish_storage_call(
            {"cid": cid, "status": "error", "backend_name": "local_cache", "error": str(exc), "data": b""},
            operation="retrieve_bytes",
            cid=cid,
        )
    return _finish_storage_call(
        {"cid": cid, "status": "degraded", "backend_name": "local_cache", "error": reason, "data": payload},
        operation="retrieve_bytes",
        cid=cid,
    )


def _local_cache_pin(cid: str, *, reason: str) -> dict[str, Any]:
    try:
        LocalCacheIPFSBackend().pin(cid)
    except Exception as exc:
        return _finish_storage_call(
            {"cid": cid, "status": "error", "backend_name": "local_cache", "error": str(exc)},
            operation="pin_cid",
            cid=cid,
        )
    return _finish_storage_call(
        {"cid": cid, "status": "degraded", "backend_name": "local_cache", "error": reason, "data": {"pinned": True}},
        operation="pin_cid",
        cid=cid,
    )


def store_bytes(
    data: bytes,
    *,
    pin_content: bool = True,
    backend: Any = None,
    backend_name: str | None = None,
) -> dict[str, Any]:
    """Store public bytes as given.

    Private complaint artifacts must use ``store_private_artifact``. This
    function does not encrypt and must not be treated as the private boundary.
    """
    if backend is not None:
        try:
            return _store_with_object(backend, data, pin_content=pin_content, backend_name=backend_name or "kit")
        except Exception as exc:
            return _finish_storage_call(
                {"cid": "", "status": "error", "backend_name": backend_name or "kit", "error": str(exc)},
                operation="store_bytes",
                size=len(data),
                pinned=pin_content,
            )

    kit_backend = _load_optional_kit_backend()
    if kit_backend is not None:
        try:
            return _store_with_object(kit_backend, data, pin_content=pin_content, backend_name="kit")
        except _storage_error_type():
            pass
        except Exception:
            pass

    if add_bytes is None:
        return _local_cache_store(data, pin_content=pin_content, reason=str(IPFS_ERROR or "ipfs router unavailable"))

    probe = _runtime_backend_probe()
    if add_bytes is None or probe["status"] != "available":
        return with_adapter_metadata(
            {
                "status": "unavailable",
                "cid": "",
                "size": len(data),
                "pinned": bool(pin_content),
                "error": probe["reason"] if probe["status"] != "available" else "",
            },
            operation="store_bytes",
            backend_available=False,
            degraded_reason=probe["reason"] or IPFS_ERROR,
            implementation_status="unavailable",
        )

    try:
        cid = add_bytes(data, pin=pin_content)
    except Exception as exc:
        return with_adapter_metadata(
            {
                "status": "error",
                "cid": "",
                "size": len(data),
                "pinned": bool(pin_content),
                "error": str(exc),
            },
            operation="store_bytes",
            backend_available=True,
            implementation_status="available",
        )

    return with_adapter_metadata(
        {
            "status": "available",
            "cid": cid,
            "size": len(data),
            "pinned": bool(pin_content),
            "backend_name": str(probe.get("backend_name") or "datasets_router"),
        },
        operation="store_bytes",
        backend_available=True,
        implementation_status="available",
        extra_metadata={"backend_name": str(probe.get("backend_name") or "datasets_router")},
    )


def retrieve_bytes(cid: str, *, backend: Any = None, backend_name: str | None = None) -> dict[str, Any]:
    if backend is not None:
        try:
            return _retrieve_with_object(backend, cid, backend_name=backend_name or "kit")
        except Exception as exc:
            return _finish_storage_call(
                {"cid": cid, "status": "error", "backend_name": backend_name or "kit", "error": str(exc), "data": b""},
                operation="retrieve_bytes",
                cid=cid,
            )
    kit_backend = _load_optional_kit_backend()
    if kit_backend is not None:
        try:
            return _retrieve_with_object(kit_backend, cid, backend_name="kit")
        except Exception:
            pass
    if cat is None:
        return _local_cache_retrieve(cid, reason=str(IPFS_ERROR or "ipfs router unavailable"))
    probe = _runtime_backend_probe()
    if cat is None or probe["status"] != "available":
        return with_adapter_metadata(
            {
                "status": "unavailable",
                "cid": cid,
                "data": b"",
                "size": 0,
                "error": probe["reason"] if probe["status"] != "available" else "",
            },
            operation="retrieve_bytes",
            backend_available=False,
            degraded_reason=probe["reason"] or IPFS_ERROR,
            implementation_status="unavailable",
        )

    try:
        data = cat(cid)
    except Exception as exc:
        return with_adapter_metadata(
            {
                "status": "error",
                "cid": cid,
                "data": b"",
                "size": 0,
                "error": str(exc),
            },
            operation="retrieve_bytes",
            backend_available=True,
            implementation_status="available",
        )

    payload = data if isinstance(data, (bytes, bytearray)) else bytes(str(data), "utf-8")
    return with_adapter_metadata(
        {
            "status": "available",
            "cid": cid,
            "data": bytes(payload),
            "size": len(payload),
            "backend_name": str(probe.get("backend_name") or "datasets_router"),
        },
        operation="retrieve_bytes",
        backend_available=True,
        implementation_status="available",
        extra_metadata={"backend_name": str(probe.get("backend_name") or "datasets_router")},
    )


def pin_cid(cid: str, *, backend: Any = None, backend_name: str | None = None) -> dict[str, Any]:
    if backend is not None:
        try:
            return _pin_with_object(backend, cid, backend_name=backend_name or "kit")
        except Exception as exc:
            return _finish_storage_call(
                {"cid": cid, "status": "error", "backend_name": backend_name or "kit", "error": str(exc)},
                operation="pin_cid",
                cid=cid,
            )
    kit_backend = _load_optional_kit_backend()
    if kit_backend is not None:
        try:
            return _pin_with_object(kit_backend, cid, backend_name="kit")
        except Exception:
            pass
    if pin is None:
        return _local_cache_pin(cid, reason=str(IPFS_ERROR or "ipfs router unavailable"))
    probe = _runtime_backend_probe()
    if pin is None or probe["status"] != "available":
        return with_adapter_metadata(
            {
                "status": "unavailable",
                "cid": cid,
                "pinned": False,
                "result": None,
                "error": probe["reason"] if probe["status"] != "available" else "",
            },
            operation="pin_cid",
            backend_available=False,
            degraded_reason=probe["reason"] or IPFS_ERROR,
            implementation_status="unavailable",
        )

    try:
        result = pin(cid)
    except Exception as exc:
        return with_adapter_metadata(
            {
                "status": "error",
                "cid": cid,
                "pinned": False,
                "result": None,
                "error": str(exc),
            },
            operation="pin_cid",
            backend_available=True,
            implementation_status="available",
        )

    return with_adapter_metadata(
        {
            "status": "available",
            "cid": cid,
            "pinned": True,
            "result": result,
            "backend_name": str(probe.get("backend_name") or "datasets_router"),
        },
        operation="pin_cid",
        backend_available=True,
        implementation_status="available",
        extra_metadata={"backend_name": str(probe.get("backend_name") or "datasets_router")},
    )


def store_private_artifact(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Encrypt a private artifact, then delegate ciphertext to the public backend."""

    from integrations.private_storage import store_private_artifact as _store_private_artifact

    return _store_private_artifact(*args, **kwargs)


def retrieve_private_artifact(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Read ciphertext from the public backend and open it for the expected binding."""

    from integrations.private_storage import retrieve_private_artifact as _retrieve_private_artifact

    return _retrieve_private_artifact(*args, **kwargs)


def storage_backend_status() -> dict[str, Any]:
    probe = _runtime_backend_probe()
    backend = probe["backend"]
    backend_name = str(probe["backend_name"] or "")
    payload: dict[str, Any] = {
        "status": probe["status"],
        "backend_name": backend_name,
        "backend_present": backend is not None,
        "error": probe["reason"] or "",
    }
    if _kit_enabled():
        payload["kit_backend"] = "ipfs_kit_py"
        payload["kit_gate"] = "COMPLAINT_GENERATOR_ENABLE_IPFS_KIT"
    return with_adapter_metadata(
        payload,
        operation="storage_backend_status",
        backend_available=probe["status"] == "available",
        degraded_reason=probe["reason"] or (IPFS_ERROR if not IPFS_AVAILABLE else None),
        implementation_status="available" if probe["status"] == "available" else "unavailable",
    )


__all__ = [
    "add_bytes",
    "cat",
    "pin",
    "get_ipfs_backend",
    "set_default_ipfs_backend",
    "clear_ipfs_backend_router_caches",
    "LocalCacheIPFSBackend",
    "ensure_ipfs_backend",
    "store_bytes",
    "store_private_artifact",
    "retrieve_bytes",
    "retrieve_private_artifact",
    "pin_cid",
    "storage_backend_status",
    "translate_kit_operation_result",
    "IPFS_AVAILABLE",
    "IPFS_ERROR",
]
