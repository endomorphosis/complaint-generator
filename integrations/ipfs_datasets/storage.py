from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import json
import logging
import math
import os
import re
import shutil
import stat
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

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
        malformed = ("success" in result and not isinstance(success, bool)) or (
            "pinned" in result and not isinstance(result["pinned"], bool)
        )
    else:
        success = getattr(result, "success", None)
        cid = str(getattr(result, "resulting_content_cid", "") or getattr(result, "cid", "") or "")
        error = getattr(result, "error", None)
        data = getattr(result, "data", None)
        state = str(getattr(result, "state", "") or "")
        pinned = getattr(result, "pinned", None)
        malformed = (success is not None and not isinstance(success, bool)) or (
            pinned is not None and not isinstance(pinned, bool)
        )

    failed_states = {"error", "failed", "failure", "rejected", "unsupported", "cancelled", "canceled", "timed_out", "unavailable", "deferred"}
    if error or malformed or success is False or state.lower().rsplit(".", 1)[-1] in failed_states:
        return {
            "cid": cid,
            "status": "error",
            "backend_name": backend_name,
            "data": data,
            "error": str(error or ("malformed storage acknowledgement" if malformed else "kit operation failed")),
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


# Operation ids that already exist in Kit source. Dispatch uses one only when
# the bound registry actually declares it. Missing ids are deferred, not invented.
_DECLARED_ROUTER_OPERATIONS: dict[str, tuple[str, ...]] = {
    "add": ("storage.ipfs.add", "storage.local-durable.put"),
    "cat": ("storage.ipfs.cat", "storage.ipfs.get", "storage.local-durable.get"),
    "pin": ("storage.ipfs.pin", "storage.ipfs.pin.add"),
}
_LIVE_BACKEND_NAMES = frozenset({"datasets_router", "kubo", "pinned_ipfs"})
_PSEUDO_HEX = frozenset("0123456789abcdef")


def _load_optional_kit_backend() -> Any:
    """Return an IPFSSimpleAPI only when kit storage is explicitly enabled.

    CanonicalStorageService is an execute() protocol reached through
    ServiceRouter.dispatch. It is not constructed here and it is not treated
    as an add_bytes/cat/pin object. IPFSSimpleAPI construction can start a
    node, so import and probe keep the datasets router and the local cache
    until COMPLAINT_GENERATOR_ENABLE_IPFS_KIT is set.
    """

    if not _kit_enabled():
        return None
    from .loader import ensure_import_paths

    ensure_import_paths("ipfs_kit_py")
    simple_api, _error = import_attr_optional("ipfs_kit_py", "IPFSSimpleAPI")
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


def _measurement_label(backend: Any) -> str:
    label = getattr(backend, "measurement_label", None) or getattr(backend, "provider_label", None)
    return str(label or "")


def _is_service_router(backend: Any) -> bool:
    return callable(getattr(backend, "dispatch", None)) and getattr(backend, "registry", None) is not None


def _is_execute_protocol(backend: Any) -> bool:
    """CanonicalStorageService shape: execute() without a byte API or router."""

    if _is_service_router(backend) or callable(getattr(backend, "add_bytes", None)):
        return False
    return callable(getattr(backend, "execute", None))


def _registry_index(registry: Any) -> dict[str, Any]:
    found: dict[str, Any] = {}
    operations = getattr(registry, "operations", None)
    if not callable(operations):
        return found
    for definition in operations() or ():
        operation_id = getattr(definition, "operation_id", None)
        if isinstance(operation_id, str) and operation_id:
            found[operation_id] = definition
        for alias in getattr(definition, "aliases", ()) or ():
            if isinstance(alias, str) and alias:
                found[alias] = definition
    return found


def _select_declared_operation(registry: Any, action: str) -> str | None:
    found = _registry_index(registry)
    for candidate in _DECLARED_ROUTER_OPERATIONS.get(action, ()):
        if candidate in found:
            return str(found[candidate].operation_id)
    return None


def _is_local_byte_operation(backend: Any, action: str) -> bool:
    if isinstance(backend, LocalCacheIPFSBackend):
        return True
    if _is_service_router(backend):
        operation_id = _select_declared_operation(backend.registry, action)
        return bool(operation_id and operation_id.startswith("storage.local-durable."))
    return False


def _router_request(operation_id: str, action: str, payload: Any, *, pin_content: bool) -> dict[str, Any]:
    import base64

    if operation_id == "storage.local-durable.put":
        blob = bytes(payload)
        digest = hashlib.sha256(blob).hexdigest()
        return {
            "path": f"objects/{digest}",
            "data_b64": base64.b64encode(blob).decode("ascii"),
            "pin": bool(pin_content),
        }
    if operation_id == "storage.local-durable.get":
        locator = payload if isinstance(payload, str) else ""
        return {"path": locator}
    if action == "add":
        return {"data": payload, "pin": bool(pin_content)}
    return {"cid": payload}


def _invoke_byte_backend(backend: Any, action: str, payload: Any, *, pin_content: bool = True) -> Any:
    if _is_execute_protocol(backend):
        raise RuntimeError(
            "CanonicalStorageService is an execute protocol; bind it with "
            "ServiceRouter.bind_service and dispatch a declared operation. "
            "It does not provide add_bytes, cat, or pin."
        )
    if _is_service_router(backend):
        operation_id = _select_declared_operation(backend.registry, action)
        if operation_id is None:
            raise RuntimeError(f"bound registry has no declared operation for {action}")
        request = _router_request(operation_id, action, payload, pin_content=pin_content)
        return backend.dispatch(operation_id, request)
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


def _explicit_pinned(raw: Any) -> bool | None:
    if isinstance(raw, dict) and "pinned" in raw:
        return raw["pinned"] if isinstance(raw["pinned"], bool) else None
    pinned = getattr(raw, "pinned", None)
    if isinstance(pinned, bool):
        return pinned
    return None


def _result_from_backend_call(raw: Any, *, backend_name: str, fallback_cid: str = "") -> dict[str, Any]:
    if isinstance(raw, str) and raw:
        translated = {"cid": raw, "status": "available", "backend_name": backend_name, "data": None, "error": ""}
    elif isinstance(raw, (bytes, bytearray)):
        translated = {
            "cid": fallback_cid,
            "status": "available",
            "backend_name": backend_name,
            "data": bytes(raw),
            "error": "",
        }
    elif raw is None or isinstance(raw, (int, float, list, tuple)):
        translated = {
            "cid": fallback_cid,
            "status": "error",
            "backend_name": backend_name,
            "data": None,
            "error": "malformed storage result",
        }
    else:
        translated = translate_kit_operation_result(raw, backend_name=backend_name)
        if not translated.get("cid") and fallback_cid:
            translated["cid"] = fallback_cid
    explicit = _explicit_pinned(raw)
    if explicit is not None:
        translated["pinned_observed"] = explicit
    if isinstance(raw, dict):
        locator = raw.get("path") or raw.get("locator")
        if isinstance(locator, str) and locator:
            translated["locator"] = locator
    return translated


def _pin_acknowledgement(raw: Any, *, cid: str, backend_name: str) -> dict[str, Any]:
    """Normalize a pin acknowledgement while binding it to the requested CID."""
    if raw is None:
        raw = {"success": True, "cid": cid, "pinned": True}
    if isinstance(raw, dict) and "Pins" in raw:
        # Kubo pin/add replies with {"Pins": [cid, ...]}. The requested root
        # must be present; an array for another root is not this call's receipt.
        candidate = dict(raw)
        candidate.setdefault("cid", cid)
        translated = _result_from_backend_call(candidate, backend_name=backend_name, fallback_cid=cid)
        pins = raw["Pins"]
        cid_aliases_match = all(
            isinstance(raw[name], str) and bool(raw[name]) and raw[name] == cid
            for name in ("cid", "resulting_content_cid", "Hash") if name in raw
        )
        valid = (
            isinstance(pins, list) and bool(pins)
            and all(isinstance(item, str) and bool(item.strip()) for item in pins)
            and cid in pins and cid_aliases_match and translated.get("cid") == cid
            and translated.get("pinned_observed") is not False
        )
        if translated["status"] == "available" and valid:
            translated["pinned_observed"] = True
            return translated
        translated["status"] = "error"
        translated["cid"] = cid
        translated["pinned_observed"] = False
        translated["error"] = translated.get("error") or "pin acknowledgement does not confirm requested CID"
        return translated
    return _result_from_backend_call(raw, backend_name=backend_name, fallback_cid=cid)


def _cid_kind(cid: str, *, backend_name: str, stored_local: bool) -> str:
    if not cid:
        return "missing"
    if cid.startswith("sha256:"):
        return "sha256_fallback"
    body = cid[4:] if cid.startswith("bafy") else ""
    if backend_name == "local_cache" or (
        len(body) == 55 and all(character in _PSEUDO_HEX for character in body)
    ):
        return "pseudo_cid"
    return "content_cid"


def _durability_view(
    *,
    backend: Any,
    backend_name: str,
    cid: str,
    status: str,
    stored_local: bool,
    uploaded: bool,
    pinned: bool,
    verified: bool,
    replicated: bool = False,
    deferred: bool = False,
    verification: dict[str, Any] | None = None,
    pin_evidence: str = "",
    error: str = "",
) -> dict[str, Any]:
    """Keep each durability claim independent of a nonempty CID or success flag."""

    kind = _cid_kind(cid, backend_name=backend_name, stored_local=stored_local)
    measurement = _measurement_label(backend)
    local_only = stored_local or kind in {"pseudo_cid", "sha256_fallback"}
    if local_only:
        pinned = False
        uploaded = False
    live_backend = backend_name in _LIVE_BACKEND_NAMES or bool(getattr(backend, "live_provider", False))
    if measurement == "measured-hermetic":
        live_backend = False
    network_durable = bool(
        live_backend and uploaded and pinned and verified and kind == "content_cid" and status == "available"
    )
    verification_payload = dict(verification or {"matched": bool(verified), "method": "readback"})
    receipt = {
        "backend_name": backend_name,
        "cid": cid,
        "cid_kind": kind,
        "status": status,
        "pin_evidence": pin_evidence,
        "measurement": measurement,
        "network_durable": network_durable,
        "error": error,
    }
    return {
        "stored_local": bool(stored_local),
        "uploaded": bool(uploaded),
        "pinned": bool(pinned),
        "verified": bool(verified),
        "replicated": bool(replicated),
        "deferred": bool(deferred),
        "network_durable": network_durable,
        "cid_kind": kind,
        "measurement": measurement,
        "verification": verification_payload,
        "receipt": receipt,
    }


def _finish_storage_call(
    translated: dict[str, Any],
    *,
    operation: str,
    size: int = 0,
    pinned: bool | None = None,
    cid: str = "",
    backend: Any = None,
    stored_local: bool = False,
    uploaded: bool = False,
    verified: bool = False,
    deferred: bool = False,
    verification: dict[str, Any] | None = None,
    pin_evidence: str = "",
) -> dict[str, Any]:
    status = str(translated.get("status") or "error")
    backend_name = str(translated.get("backend_name") or "")
    resolved_cid = str(translated.get("cid") or cid or "")
    payload: dict[str, Any] = {
        "status": status,
        "cid": resolved_cid,
        "backend_name": backend_name,
        "error": str(translated.get("error") or ""),
    }
    if operation == "retrieve_bytes":
        data = translated.get("data")
        payload["data"] = bytes(data) if isinstance(data, (bytes, bytearray)) else b""
        payload["size"] = len(payload["data"])
        verified = verified or bool(payload["data"])
    pin_flag = bool(pinned) and status in {"available", "degraded"}
    if operation == "pin_cid":
        payload["result"] = translated.get("data")
        if status != "available":
            pin_flag = False
    if operation == "store_bytes":
        payload["size"] = size
    durability = _durability_view(
        backend=backend,
        backend_name=backend_name,
        cid=resolved_cid,
        status=status,
        stored_local=stored_local or backend_name == "local_cache",
        uploaded=uploaded and status in {"available", "degraded"},
        pinned=pin_flag,
        verified=verified and status in {"available", "degraded"},
        deferred=deferred or status == "unavailable",
        verification=verification,
        pin_evidence=pin_evidence,
        error=payload["error"],
    )
    payload.update(durability)
    return with_adapter_metadata(
        payload,
        operation=operation,
        backend_available=status == "available",
        degraded_reason=payload["error"] or None,
        implementation_status="available" if status == "available" else ("unavailable" if status == "unavailable" else "degraded"),
        extra_metadata={"backend_name": payload["backend_name"]},
    )


def _readback(backend: Any, cid: str, expected: bytes, *, locator: str = "") -> dict[str, Any]:
    target: Any = locator or cid
    try:
        raw = _invoke_byte_backend(backend, "cat", target)
    except Exception as exc:
        return {"matched": False, "verified": False, "method": "readback", "reason": str(exc)}
    translated = _result_from_backend_call(raw, backend_name="readback", fallback_cid=cid)
    if translated["status"] != "available":
        return {
            "matched": False,
            "verified": False,
            "method": "readback",
            "reason": str(translated.get("error") or "readback rejected"),
        }
    data = translated.get("data")
    if isinstance(raw, (bytes, bytearray)):
        data = bytes(raw)
    elif isinstance(data, str):
        data = data.encode("utf-8")
    matched = isinstance(data, (bytes, bytearray)) and bytes(data) == expected
    return {
        "matched": matched,
        "verified": matched,
        "method": "readback",
        "reason": "" if matched else "readback mismatch",
    }


def _store_with_object(backend: Any, data: bytes, *, pin_content: bool, backend_name: str) -> dict[str, Any]:
    operation_id = _select_declared_operation(backend.registry, "add") if _is_service_router(backend) else None
    stored_local = _is_local_byte_operation(backend, "add")
    # A locator belongs to this call. A later pin/read call must not overwrite
    # it, and concurrent writes must not share mutable function attributes.
    locator = ""
    if operation_id == "storage.local-durable.put":
        locator = str(_router_request(operation_id, "add", data, pin_content=pin_content)["path"])
    raw = _invoke_byte_backend(backend, "add", data, pin_content=pin_content)
    translated = _result_from_backend_call(raw, backend_name=backend_name)
    if translated["status"] != "available":
        raise RuntimeError(translated["error"] or "kit add failed")
    observed = translated.get("pinned_observed")
    pinned = bool(observed) if observed is not None else False
    pin_evidence = "add_result" if observed is not None else "not_observed"
    pin_error = ""
    if pin_content and observed is not True and (
        callable(getattr(backend, "pin", None)) or _is_service_router(backend)
    ):
        try:
            pin_raw = _invoke_byte_backend(backend, "pin", translated["cid"])
            pin_translated = _pin_acknowledgement(pin_raw, backend_name=backend_name, cid=translated["cid"])
            pin_observed = pin_translated.get("pinned_observed")
            pinned = pin_translated["status"] == "available" and (pin_observed is not False)
            pin_evidence = "pin_call"
            if not pinned:
                pin_error = str(pin_translated.get("error") or "pin failed")
        except Exception as exc:
            pinned = False
            pin_evidence = "pin_call_failed"
            pin_error = str(exc)
    elif pin_content and observed is False:
        pin_evidence = "add_result_unpinned"
    locator = str(translated.get("locator") or locator)
    verification = _readback(backend, translated["cid"], data, locator=locator)
    if pin_error and not translated.get("error"):
        translated["error"] = pin_error
    if not verification.get("matched") and not translated.get("error"):
        translated["error"] = str(verification.get("reason") or "readback failed")
    return _finish_storage_call(
        translated,
        operation="store_bytes",
        size=len(data),
        pinned=pinned,
        backend=backend,
        stored_local=stored_local,
        uploaded=not stored_local,
        verified=bool(verification.get("matched")),
        verification=verification,
        pin_evidence=pin_evidence,
    )


def _retrieve_with_object(backend: Any, cid: str, *, backend_name: str) -> dict[str, Any]:
    raw = _invoke_byte_backend(backend, "cat", cid)
    translated = _result_from_backend_call(raw, backend_name=backend_name, fallback_cid=cid)
    if translated["status"] != "available":
        raise RuntimeError(translated["error"] or "kit cat failed")
    return _finish_storage_call(
        translated,
        operation="retrieve_bytes",
        cid=cid,
        backend=backend,
        stored_local=_is_local_byte_operation(backend, "cat"),
        uploaded=not _is_local_byte_operation(backend, "cat") and backend_name not in {"local_cache", ""},
        verified=isinstance(translated.get("data"), (bytes, bytearray)),
    )


def _pin_with_object(backend: Any, cid: str, *, backend_name: str) -> dict[str, Any]:
    raw = _invoke_byte_backend(backend, "pin", cid)
    translated = _pin_acknowledgement(raw, backend_name=backend_name, cid=cid)
    if translated["status"] != "available":
        raise RuntimeError(translated["error"] or "kit pin failed")
    observed = translated.get("pinned_observed")
    pinned = True if observed is None else bool(observed)
    if observed is False:
        raise RuntimeError("pin result reported pinned=false")
    return _finish_storage_call(
        translated,
        operation="pin_cid",
        cid=cid,
        pinned=pinned,
        backend=backend,
        stored_local=_is_local_byte_operation(backend, "pin"),
        uploaded=not _is_local_byte_operation(backend, "pin"),
        pin_evidence="pin_call",
    )


def _local_cache_store(data: bytes, *, pin_content: bool, reason: str) -> dict[str, Any]:
    cache = LocalCacheIPFSBackend()
    cid = cache.add_bytes(data, pin=False)
    try:
        readback = cache.cat(cid)
        matched = readback == data
    except Exception as exc:
        matched = False
        readback_error = str(exc)
    else:
        readback_error = "" if matched else "readback mismatch"
    return _finish_storage_call(
        {"cid": cid, "status": "degraded", "backend_name": "local_cache", "error": reason},
        operation="store_bytes",
        size=len(data),
        pinned=False,
        stored_local=True,
        uploaded=False,
        verified=matched,
        verification={"matched": matched, "verified": matched, "method": "local-readback", "reason": readback_error},
        pin_evidence="local_marker_is_not_a_network_pin" if pin_content else "pin_not_requested",
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
        {"cid": cid, "status": "degraded", "backend_name": "local_cache", "error": reason, "data": {"local_pin_marker": True}},
        operation="pin_cid",
        cid=cid,
        pinned=False,
        stored_local=True,
        pin_evidence="local_marker_is_not_a_network_pin",
        verification={"matched": False, "method": "none", "reason": "local pin marker is not network durability"},
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
            deferred = "no declared operation" in str(exc) or "does not implement" in str(exc)
            return _finish_storage_call(
                {"cid": "", "status": "deferred" if deferred else "error", "backend_name": backend_name or "kit", "error": str(exc)},
                operation="store_bytes",
                size=len(data),
                pinned=False,
                backend=backend,
                deferred=deferred,
                pin_evidence="not_pinned",
            )

    kit_backend = _load_optional_kit_backend()
    if kit_backend is not None:
        try:
            return _store_with_object(kit_backend, data, pin_content=pin_content, backend_name="kit")
        except Exception as exc:
            return _finish_storage_call(
                {"cid": "", "status": "error", "backend_name": "kit", "error": str(exc)},
                operation="store_bytes", size=len(data), backend=kit_backend,
                deferred=True, pin_evidence="add_failed",
            )
    if _kit_enabled():
        return _finish_storage_call(
            {"cid": "", "status": "unavailable", "backend_name": "kit", "error": "explicit Kit backend unavailable"},
            operation="store_bytes", size=len(data), deferred=True,
        )

    if add_bytes is None:
        return _local_cache_store(data, pin_content=pin_content, reason=str(IPFS_ERROR or "ipfs router unavailable"))

    probe = _runtime_backend_probe()
    if add_bytes is None or probe["status"] != "available":
        return _finish_storage_call(
            {
                "status": "unavailable",
                "cid": "",
                "backend_name": str(probe.get("backend_name") or ""),
                "error": probe["reason"] if probe["status"] != "available" else "",
            },
            operation="store_bytes",
            size=len(data),
            pinned=False,
            deferred=True,
            pin_evidence="backend_unavailable",
        )

    try:
        cid = add_bytes(data, pin=pin_content)
    except Exception as exc:
        return _finish_storage_call(
            {"status": "error", "cid": "", "backend_name": str(probe.get("backend_name") or "datasets_router"), "error": str(exc)},
            operation="store_bytes",
            size=len(data),
            pinned=False,
            pin_evidence="add_failed",
        )

    router_local = isinstance(probe.get("backend"), LocalCacheIPFSBackend)
    router_name = "local_cache" if router_local else str(probe.get("backend_name") or "datasets_router")
    # add_bytes(..., pin=) is the datasets router contract. A bare CID is not a
    # pin receipt, so pinned stays false until a later pin_cid observation.
    return _finish_storage_call(
        {
            "status": "available",
            "cid": str(cid or ""),
            "backend_name": router_name,
            "error": "",
        },
        operation="store_bytes",
        size=len(data),
        pinned=False,
        backend=probe.get("backend"),
        stored_local=router_local,
        uploaded=bool(cid) and not router_local,
        verified=False,
        verification={"matched": False, "method": "readback", "reason": "datasets router bytes were not read back"},
        pin_evidence="router_pin_argument_unconfirmed" if pin_content else "pin_not_requested",
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
        except Exception as exc:
            return _finish_storage_call(
                {"cid": cid, "status": "error", "backend_name": "kit", "error": str(exc), "data": b""},
                operation="retrieve_bytes", cid=cid, backend=kit_backend, deferred=True,
            )
    if _kit_enabled():
        return _finish_storage_call(
            {"cid": cid, "status": "unavailable", "backend_name": "kit", "error": "explicit Kit backend unavailable", "data": b""},
            operation="retrieve_bytes", cid=cid, deferred=True,
        )
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
        except Exception as exc:
            return _finish_storage_call(
                {"cid": cid, "status": "error", "backend_name": "kit", "error": str(exc)},
                operation="pin_cid", cid=cid, backend=kit_backend, deferred=True,
            )
    if _kit_enabled():
        return _finish_storage_call(
            {"cid": cid, "status": "unavailable", "backend_name": "kit", "error": "explicit Kit backend unavailable"},
            operation="pin_cid", cid=cid, deferred=True,
        )
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

    router_local = isinstance(probe.get("backend"), LocalCacheIPFSBackend)
    router_name = "local_cache" if router_local else str(probe.get("backend_name") or "datasets_router")
    # The datasets pin protocol returns None on success. Other acknowledgements
    # still undergo the same explicit-failure checks as injected byte backends.
    translated = _pin_acknowledgement(result, backend_name=router_name, cid=cid)
    translated["data"] = result
    return _finish_storage_call(
        translated, operation="pin_cid", cid=cid,
        pinned=translated["status"] == "available" and translated.get("pinned_observed") is not False,
        backend=probe.get("backend"), stored_local=router_local,
        uploaded=not router_local, pin_evidence="datasets_pin_call",
    )


AUTOMATIC_PRIVATE_ARTIFACT_KINDS = frozenset({
    "session",
    "answers",
    "attachment",
    "extracted-text",
    "assertion-envelope",
    "fact-graph",
    "legal-graph",
    "rule-evaluation",
    "annotation",
    "draft",
    "proof-history",
    "theorem-source",
    "index",
    "backup-manifest",
    "embedding",
    "case-alias",
    "interview-snapshot",
    "complaint-text",
    "transcript",
    "export",
    "durability-payload",
})

# Public CID metadata, filenames, the global index, and default logs may carry
# only these keys. Case names, complaint text, document filenames, graph labels,
# and claim-specific queries are not public fields.
_PUBLIC_METADATA_KEYS = frozenset({
    "cid",
    "cid_kind",
    "artifact_class",
    "schema",
    "status",
    "opaque_name",
    "classification",
})
_FORBIDDEN_PUBLIC_KEYS = frozenset({
    "user_name",
    "user_id",
    "case_name",
    "case_id",
    "display_name",
    "complaint",
    "complaint_text",
    "filename",
    "file_name",
    "original_filename",
    "document_filename",
    "node_label",
    "graph_label",
    "label",
    "query",
    "claim_query",
    "legal_query",
    "prompt",
    "payload",
    "token",
    "api_key",
    "key",
    "data_key",
    "master_key",
    "embedding",
    "embeddings",
    "plaintext",
    "source_text",
    "mapping",
})
_PUBLIC_ARTIFACT_CLASSES = frozenset({
    "public_legal_source",
    "opaque_private_ref",
})
_FILENAME_KIND = re.compile(r"[^a-z0-9]+")
_DIAGNOSTIC_FIELDS = (
    "operation_id",
    "status",
    "error_category",
    "duration_ms",
    "synthetic_source",
)

# Encryption hides plaintext bytes. It does not hide ciphertext size, when a
# request happened, or which opaque object was fetched. Padding is optional and
# only changes size inside a declared bound. It is not a claim that metadata
# is gone.
RESIDUAL_METADATA_EXPOSURE = (
    "Encryption does not hide ciphertext size, request timing, or access patterns. "
    "Those residuals stay visible to anyone who can see the public object, the "
    "transport, or the default log clock. Padding is an optional policy. When it "
    "is enabled, the block size must sit between 256 and 65536 bytes. Padding is "
    "not a promise that encryption hides all metadata."
)
PADDING_MIN_BLOCK_BYTES = 256
PADDING_MAX_BLOCK_BYTES = 65536
PADDING_POLICY = {
    "optional": True,
    "min_block_bytes": PADDING_MIN_BLOCK_BYTES,
    "max_block_bytes": PADDING_MAX_BLOCK_BYTES,
    "hides_all_metadata": False,
    "residual_exposure": RESIDUAL_METADATA_EXPOSURE,
}

_public_index_lock = threading.Lock()
_public_index: list[dict[str, Any]] = []
_storage_logger = logging.getLogger(__name__)
_PUBLIC_ALIAS_KEY = os.urandom(32)
_PUBLIC_STATUSES = frozenset({"unknown", "available", "unavailable", "ready", "starting", "running",
    "stored", "pending", "degraded", "failed", "error", "complete", "completed", "stopped",
    "paused", "cancelled", "timeout", "denied", "not_found", "repairing", "healthy"})
_PUBLIC_OPERATIONS = frozenset({"unspecified", "daemon", "store-private-artifact", "publish-reference",
    "store", "load", "save", "restore", "export", "render", "optimize", "poll", "pause", "resume", "status"})
_PUBLIC_ERRORS = frozenset({"", "operation_error", "backend_unavailable", "provider_unavailable",
    "privacy_denied", "permission_denied", "auth_denied", "timeout", "offline", "not_found",
    "invalid_input", "validation_error", "configuration_error", "cancelled", "network_unavailable", "export_failed"})
_PUBLIC_SOURCE_LABELS = frozenset({"synthetic-unspecified", "fixture-source-a", "ui-optimizer-daemon"})
_PUBLIC_FILENAME_KINDS = frozenset({"object", "attachment", "document", "complaint", "graph", "proof",
    "index", "snapshot", "embedding", "backup", "evidence"})


def _diagnostic_alias(value: str, domain: str, record: Mapping[str, Any]) -> str:
    scope = [str(record.get(key) or "") for key in ("user_id", "case_id")]
    material = json.dumps([domain, *scope, value], ensure_ascii=False, separators=(",", ":")).encode()
    return domain + "-" + hmac.new(_PUBLIC_ALIAS_KEY, material, hashlib.sha256).hexdigest()[:24]


def _public_content_reference(value: Any) -> str | None:
    """Accept bounded digest references and canonical SHA-256 IPFS CIDs."""
    if not isinstance(value, str) or len(value) > 200:
        return None
    if re.fullmatch(r"[0-9a-f]{64}", value):
        return value
    if re.fullmatch(r"Qm[1-9A-HJ-NP-Za-km-z]{44}", value):
        alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        number = 0
        for character in value:
            number = number * 58 + alphabet.index(character)
        decoded = number.to_bytes((number.bit_length() + 7) // 8, "big")
        return value if len(decoded) == 34 and decoded[:2] == b"\x12\x20" else None
    if not re.fullmatch(r"b[a-z2-7]{10,190}", value):
        return None
    try:
        payload = value[1:]
        decoded = base64.b32decode(payload.upper() + "=" * (-len(payload) % 8))
        position = 0
        def varint():
            nonlocal position
            result = 0
            for shift in range(0, 63, 7):
                byte = decoded[position]; position += 1
                result |= (byte & 127) << shift
                if byte < 128:
                    if shift and byte == 0:
                        raise ValueError("noncanonical_varint")
                    return result
            raise ValueError("unbounded_varint")
        version, codec, algorithm, size = varint(), varint(), varint(), varint()
        canonical = "b" + base64.b32encode(decoded).decode().lower().rstrip("=")
        return value if version == 1 and codec > 0 and algorithm == 0x12 and size == 32 and len(decoded) - position == 32 and canonical == value else None
    except (ValueError, IndexError):
        return None


def _sensitive_hit(value: str, literals: Sequence[str]) -> bool:
    for literal in literals:
        text = str(literal or "")
        if len(text) >= 4 and text in value:
            return True
    return False


def project_public_cid_metadata(
    raw: Mapping[str, Any] | None,
    *,
    sensitive_literals: Sequence[str] = (),
) -> dict[str, Any]:
    """Allow-list public CID metadata.

    Forbidden keys are dropped. String values that still contain a caller-supplied
    case name, complaint excerpt, filename, graph label, or claim query are dropped.
    """

    raw = raw if isinstance(raw, Mapping) else {}
    artifact_class = raw.get("artifact_class")
    if not isinstance(artifact_class, str) or artifact_class not in _PUBLIC_ARTIFACT_CLASSES:
        artifact_class = "opaque_private_ref"
    classification = raw.get("classification")
    if not isinstance(classification, str) or classification not in {"opaque", "private_derived", "public"}:
        classification = "public" if artifact_class == "public_legal_source" else "opaque"
    if classification == "private_derived":
        artifact_class = "opaque_private_ref"
    projected: dict[str, Any] = {"schema": "public-cid-metadata/v1", "artifact_class": artifact_class,
        "classification": classification}
    cid = _public_content_reference(raw.get("cid"))
    if cid is not None:
        projected["cid"] = cid
    if isinstance(raw.get("cid_kind"), str) and raw["cid_kind"] in {"opaque", "ipfs", "local", "sha256", "ciphertext", "encrypted"}:
        projected["cid_kind"] = raw["cid_kind"]
    if isinstance(raw.get("status"), str) and raw["status"] in _PUBLIC_STATUSES:
        projected["status"] = raw["status"]
    name = raw.get("opaque_name")
    if isinstance(name, str) and any(re.fullmatch(re.escape(kind) + r"-[0-9a-f]{32}\.bin", name) for kind in _PUBLIC_FILENAME_KINDS):
        projected["opaque_name"] = name
    for field, value in list(projected.items()):
        if isinstance(value, str) and _sensitive_hit(value, sensitive_literals):
            del projected[field]
    return projected


def opaque_storage_filename(kind: str, secret_name: str) -> str:
    """Filename for a stored object. The original document name is not recoverable."""

    kind_text = kind if isinstance(kind, str) and kind in _PUBLIC_FILENAME_KINDS else "object"
    return f"{kind_text}-{os.urandom(16).hex()}.bin"


def clear_public_index() -> None:
    with _public_index_lock:
        _public_index.clear()


def publish_public_index_entry(
    entry: Mapping[str, Any],
    *,
    sensitive_literals: Sequence[str] = (),
) -> dict[str, Any]:
    """Record one global-index row that cannot carry private case metadata."""

    projected = project_public_cid_metadata(entry, sensitive_literals=sensitive_literals)
    if entry.get("classification") == "private_derived":
        projected["classification"] = "private_derived"
        projected["artifact_class"] = "opaque_private_ref"
    encoded = json.dumps(projected, sort_keys=True)
    for literal in sensitive_literals:
        text = str(literal or "")
        if len(text) >= 4 and text in encoded:
            raise ValueError("public index refused a private literal")
    with _public_index_lock:
        _public_index.append(dict(projected))
    return dict(projected)


def public_index_snapshot() -> list[dict[str, Any]]:
    with _public_index_lock:
        return [dict(item) for item in _public_index]


def redact_private_diagnostic(record: Mapping[str, Any] | None) -> dict[str, Any]:
    """Keep operation identity and drop payloads, keys, tokens, and case text.

    ``synthetic_source`` is the only identity copied through. A raw user or case
    name is hashed when the caller did not already supply a synthetic source.
    """

    source = ""
    status = "unknown"
    operation_id = "unspecified"
    error_category = ""
    duration_ms: int | float | None = None
    if isinstance(record, Mapping):
        source = str(record.get("synthetic_source") or record.get("source_identity") or "")
        status = str(record.get("status") or "unknown")
        operation_id = str(record.get("operation_id") or record.get("phase") or "unspecified")
        error_category = str(record.get("error_category") or record.get("error_kind") or "")
        raw_duration = record.get("duration_ms")
        if isinstance(raw_duration, bool) or not isinstance(raw_duration, (int, float)):
            raw_duration = record.get("phase_elapsed_seconds")
            if not isinstance(raw_duration, bool) and isinstance(raw_duration, (int, float)):
                raw_duration *= 1000
        if isinstance(raw_duration, bool) or not isinstance(raw_duration, (int, float)):
            duration_ms = None
        else:
            duration_ms = raw_duration
        if not source:
            raw_user = str(record.get("user_id") or record.get("user_name") or "")
            if raw_user:
                source = "syn-" + hashlib.sha256(raw_user.encode("utf-8")).hexdigest()[:16]
    if not source:
        source = "synthetic-unspecified"
    if not error_category and isinstance(record, Mapping) and record.get("error"):
        error_category = "operation_error"
    record = record if isinstance(record, Mapping) else {}
    if duration_ms is not None and (duration_ms < 0 or duration_ms > 86400000 or not math.isfinite(duration_ms)):
        duration_ms = None
    diagnostic = {
        "operation_id": operation_id if operation_id in _PUBLIC_OPERATIONS else _diagnostic_alias(operation_id, "op", record),
        "status": status if status in _PUBLIC_STATUSES else "unknown",
        "error_category": error_category if error_category in _PUBLIC_ERRORS else "operation_error",
        "duration_ms": duration_ms,
        "synthetic_source": source if source in _PUBLIC_SOURCE_LABELS else _diagnostic_alias(source, "src", record),
    }
    return {key: diagnostic[key] for key in _DIAGNOSTIC_FIELDS}


def emit_default_storage_log(record: Mapping[str, Any] | None) -> dict[str, Any]:
    """Log one redacted diagnostic. The message is the allow-listed JSON object."""

    diagnostic = redact_private_diagnostic(record)
    _storage_logger.info("storage_diagnostic %s", json.dumps(diagnostic, sort_keys=True))
    return diagnostic


def optional_size_padding(
    data: bytes,
    *,
    enabled: bool = False,
    block_size: int | None = None,
) -> dict[str, Any]:
    """Apply optional size padding inside the declared bounds.

    Disabled padding returns the original bytes. Enabled padding never claims
    that size, timing, or access patterns are hidden.
    """

    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("padding input must be bytes")
    payload = bytes(data)
    policy = dict(PADDING_POLICY)
    if not enabled:
        return {"applied": False, "data": payload, "block_size": None, "policy": policy}
    if type(block_size) is not int or block_size < PADDING_MIN_BLOCK_BYTES or block_size > PADDING_MAX_BLOCK_BYTES:
        raise ValueError("padding_block_out_of_bounds")
    remainder = len(payload) % block_size
    pad = 0 if remainder == 0 else block_size - remainder
    if pad == 0:
        pad = block_size
    return {
        "applied": True,
        "data": payload + b"\x00" * pad,
        "block_size": block_size,
        "policy": policy,
    }


def store_private_artifact(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Encrypt a private artifact, then delegate ciphertext to the public backend."""

    from integrations.private_storage import store_private_artifact as _store_private_artifact

    return _store_private_artifact(*args, **kwargs)


def store_automatic_private_artifact(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Route an automatic workspace artifact through the private repository first.

    Public legal-source corpora stay on ``store_bytes``. Kinds in
    ``AUTOMATIC_PRIVATE_ARTIFACT_KINDS`` are sealed before any hash, cache,
    pin, index, or backup. Plaintext is never written as a fallback.
    """

    kind = str(kwargs.get("artifact_kind") or "")
    if kind not in AUTOMATIC_PRIVATE_ARTIFACT_KINDS:
        raise ValueError(f"unsupported automatic private artifact kind: {kind}")
    return store_private_artifact(*args, **kwargs)


def retrieve_private_artifact(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Read ciphertext from the public backend and open it for the expected binding."""

    from integrations.private_storage import retrieve_private_artifact as _retrieve_private_artifact

    return _retrieve_private_artifact(*args, **kwargs)


def configure_replica_policy(**kwargs: Any) -> Any:
    """Explicit desired/minimum replica policy. Does not open a network client."""

    from integrations.private_storage import configure_replica_policy as _configure

    return _configure(**kwargs)


def replica_policy(**kwargs: Any) -> Any:
    """Workspace desired/minimum policy. Does not open a network client."""

    from integrations.private_storage import replica_policy as _policy

    return _policy(**kwargs)


def select_private_storage_mode(mode: str) -> Any:
    """Local private mode constructs no remote store and performs no pin."""

    from integrations.private_storage import select_private_storage_mode as _select

    return _select(mode)


def remote_storage_activation_count() -> int:
    from integrations.private_storage import remote_storage_activation_count as _count

    return _count()


def publish_encrypted_replicas(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from integrations.private_storage import publish_encrypted_replicas as _publish

    return _publish(*args, **kwargs)


def reconcile_encrypted_replicas(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from integrations.private_storage import reconcile_encrypted_replicas as _reconcile

    return _reconcile(*args, **kwargs)


def restore_encrypted_replicas(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from integrations.private_storage import restore_encrypted_replicas as _restore

    return _restore(*args, **kwargs)


def restore_encrypted_workspace(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from integrations.private_storage import restore_encrypted_workspace as _restore

    return _restore(*args, **kwargs)


def count_verified_ciphertext_replicas(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    from integrations.private_storage import count_verified_ciphertext_replicas as _count

    return _count(observations)


UPSTREAM_REPLICA_FIXTURES = (
    "tests/unit/test_wallet_storage_factory.py",
    "tests/unit/test_wallet_storage_replicas_optional.py",
)


def upstream_replication_fixture_qualification(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Acceptance-suite qualification. Missing upstream suites are not passes."""

    from integrations.private_storage import upstream_replication_fixture_qualification as _qualify

    return _qualify(*args, **kwargs)


def upstream_replica_fixture_qualification() -> dict[str, Any]:
    """Run datasets wallet replica fixtures in that package tree and report them separately.

    A missing fixture is not a pass. The report never replaces first-party assertions.
    """

    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2] / "external" / "ipfs_datasets_py"
    suites = []
    for relative in UPSTREAM_REPLICA_FIXTURES:
        path = root / relative
        if not path.is_file():
            suites.append({
                "suite": relative,
                "status": "missing",
                "passed": False,
                "counts_as_passed": False,
                "returncode": None,
            })
            continue
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONNOUSERSITE"] = "1"
        env["IPFS_DATASETS_AUTO_INSTALL"] = "false"
        env["IPFS_AUTO_INSTALL"] = "false"
        env["IPFS_DATASETS_PY_MINIMAL_IMPORTS"] = "1"
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "--override-ini",
                    "addopts=",
                    "-p",
                    "no:cacheprovider",
                    "--noconftest",
                    relative,
                ],
                cwd=root,
                env=env,
                capture_output=True,
                timeout=60,
                check=False,
            )
            passed = completed.returncode == 0
            status = "passed" if passed else "failed"
            returncode = completed.returncode
        except (OSError, subprocess.TimeoutExpired):
            passed = False
            status = "failed"
            returncode = None
        suites.append({
            "suite": relative,
            "status": status,
            "passed": passed,
            "counts_as_passed": False if status == "missing" else passed,
            "returncode": returncode,
        })
    return {
        "package_root": str(root),
        "intended_environment": "ipfs_datasets_py",
        "substitutes_first_party": False,
        "suites": suites,
    }


INTERVIEW_SNAPSHOT_SCHEMA = "interview-snapshot-v1"
INTERVIEW_HEAD_SCHEMA = "interview-snapshot-head-v1"
UNENCRYPTED_INTERVIEW_NAME = "unencrypted-interview-snapshot.json"
_INTERVIEW_PROTECTIONS = frozenset({"user_chosen_encrypted", "user_chosen_plaintext"})
_INTERVIEW_PART_KINDS = (
    "complaint-text",
    "transcript",
    "fact-graph",
    "legal-graph",
    "export",
    "durability-payload",
    "interview-snapshot",
)
_INTERVIEW_REQUIRED = (
    "schema_version",
    "snapshot_id",
    "session_id",
    "revision",
    "revisions",
    "outcome_reason",
    "pending_inquiry",
    "provenance",
    "graphs",
    "unknown_items",
    "deferred_items",
    "complaint_text",
    "transcript",
    "exports",
    "durability_payload",
)


class InterviewSnapshotError(RuntimeError):
    """Private interview snapshot could not be committed or opened."""

    def __init__(self, message: str, *, code: str, public_status: str = "recoverable") -> None:
        super().__init__(message)
        self.code = code
        self.public_status = public_status


def assemble_interview_snapshot(
    *,
    session_id: str,
    revision: str,
    outcome_reason: str,
    pending_inquiry: Mapping[str, Any],
    knowledge_graph: Mapping[str, Any],
    dependency_graph: Mapping[str, Any],
    provenance: Mapping[str, Any],
    unknown_items: Sequence[Any],
    deferred_items: Sequence[Any],
    complaint_text: str,
    transcript: Sequence[Any],
    exports: Mapping[str, Any],
    durability_payload: Mapping[str, Any],
    revisions: Mapping[str, Any],
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Build one complete snapshot. Missing sections stay explicit, not omitted."""

    document = {
        "schema_version": INTERVIEW_SNAPSHOT_SCHEMA,
        "snapshot_id": snapshot_id or ("snap-" + uuid.uuid4().hex),
        "session_id": str(session_id),
        "revision": str(revision),
        "revisions": {
            "session_revision": revisions.get("session_revision", "unknown"),
            "question_revision": revisions.get("question_revision", "unknown"),
            "graph_revision": revisions.get("graph_revision", "unknown"),
        },
        "outcome_reason": str(outcome_reason or "unknown"),
        "pending_inquiry": dict(pending_inquiry) if isinstance(pending_inquiry, Mapping) else {"status": "unknown"},
        "provenance": dict(provenance) if isinstance(provenance, Mapping) else {"status": "unknown"},
        "graphs": {
            "knowledge_graph": dict(knowledge_graph) if isinstance(knowledge_graph, Mapping) else {"status": "unknown"},
            "dependency_graph": dict(dependency_graph) if isinstance(dependency_graph, Mapping) else {"status": "unknown"},
        },
        "unknown_items": [item for item in unknown_items],
        "deferred_items": [item for item in deferred_items],
        "complaint_text": str(complaint_text),
        "transcript": [item for item in transcript],
        "exports": dict(exports) if isinstance(exports, Mapping) else {"status": "unknown"},
        "durability_payload": dict(durability_payload) if isinstance(durability_payload, Mapping) else {"status": "unknown"},
        "explicit_dispositions": {"unknown": "recorded", "deferred": "recorded"},
    }
    return validate_interview_snapshot(document)


def validate_interview_snapshot(document: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(document, Mapping):
        raise InterviewSnapshotError("snapshot must be an object", code="snapshot_invalid")
    missing = [key for key in _INTERVIEW_REQUIRED if key not in document]
    if missing:
        raise InterviewSnapshotError("snapshot is missing required sections", code="snapshot_invalid")
    if document.get("schema_version") != INTERVIEW_SNAPSHOT_SCHEMA:
        raise InterviewSnapshotError("unsupported snapshot schema", code="unsupported_schema")
    graphs = document.get("graphs")
    if not isinstance(graphs, Mapping) or "knowledge_graph" not in graphs or "dependency_graph" not in graphs:
        raise InterviewSnapshotError("both graphs are required", code="snapshot_invalid")
    revisions = document.get("revisions")
    if not isinstance(revisions, Mapping):
        raise InterviewSnapshotError("revisions are required", code="snapshot_invalid")
    for key in ("session_revision", "question_revision", "graph_revision"):
        if key not in revisions:
            raise InterviewSnapshotError("graph and question revisions are required", code="snapshot_invalid")
    if not isinstance(document.get("unknown_items"), list) or not isinstance(document.get("deferred_items"), list):
        raise InterviewSnapshotError("unknown and deferred items must be explicit lists", code="snapshot_invalid")
    if not isinstance(document.get("pending_inquiry"), Mapping):
        raise InterviewSnapshotError("pending inquiry is required", code="snapshot_invalid")
    if not isinstance(document.get("provenance"), Mapping):
        raise InterviewSnapshotError("provenance is required", code="snapshot_invalid")
    if not isinstance(document.get("outcome_reason"), str) or not document.get("outcome_reason"):
        raise InterviewSnapshotError("outcome reason is required", code="snapshot_invalid")
    if not isinstance(document.get("complaint_text"), str):
        raise InterviewSnapshotError("complaint text must be a string", code="snapshot_invalid")
    if not isinstance(document.get("transcript"), list):
        raise InterviewSnapshotError("transcript must be a list", code="snapshot_invalid")
    copied = json.loads(json.dumps(document, sort_keys=True))
    return copied


def interview_snapshot_receipt(
    snapshot: Mapping[str, Any],
    *,
    status: str,
    operation_id: str,
    protection: str,
    error_category: str = "",
    recovered_from: str | None = None,
) -> dict[str, Any]:
    """Identifiers and operational status only. No complaint text and no key."""

    receipt = {
        "operation_id": operation_id,
        "status": status,
        "error_category": error_category,
        "protection": protection,
        "schema_version": INTERVIEW_SNAPSHOT_SCHEMA,
        "snapshot_id": str(snapshot.get("snapshot_id") or ""),
        "session_id": str(snapshot.get("session_id") or ""),
        "revision": str(snapshot.get("revision") or ""),
        "outcome_reason": str(snapshot.get("outcome_reason") or ""),
        "parts": list(_INTERVIEW_PART_KINDS),
        "recovered_from": recovered_from,
    }
    encoded = json.dumps(receipt, sort_keys=True)
    complaint = snapshot.get("complaint_text")
    if isinstance(complaint, str) and len(complaint) >= 8 and complaint in encoded:
        raise InterviewSnapshotError("receipt leaked complaint text", code="receipt_leak")
    emit_default_storage_log({
        "operation_id": "save" if operation_id.endswith("commit") else "load",
        "status": "available" if status in {"available", "recovered"} else "failed",
        "error_category": "operation_error" if error_category else "",
        "synthetic_source": "fixture-source-a",
    })
    return receipt


def _interview_prepare(directory: Path) -> int:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    for name in ("revisions", "parts"):
        child = directory / name
        child.mkdir(mode=0o700, exist_ok=True)
        os.chmod(child, 0o700)
    metadata = directory.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise InterviewSnapshotError("snapshot directory is not private", code="permission_denied", public_status="unavailable")
    if metadata.st_mode & 0o077:
        os.chmod(directory, 0o700)
    return os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def _interview_write_exclusive(dir_fd: int, relative: str, payload: bytes) -> str:
    parent, _, name = relative.rpartition("/")
    parent_fd = dir_fd
    close_parent = False
    if parent:
        parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
        close_parent = True
    temporary = "." + name + "." + uuid.uuid4().hex + ".tmp"
    fd = -1
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
        os.fchmod(fd, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        return relative
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temporary, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        if close_parent:
            os.close(parent_fd)


def _interview_read(dir_fd: int, relative: str) -> bytes:
    fd = os.open(relative, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise InterviewSnapshotError("snapshot file is not a private regular file", code="permission_denied", public_status="unavailable")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _interview_lock(dir_fd: int) -> int:
    fd = os.open(".interview-write.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=dir_fd)
    os.fchmod(fd, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def _seal_part(payload: bytes, *, kind: str, revision: str, tenant_id: str, case_id: str, principal_id: str, key: bytes, key_id: str) -> bytes:
    from integrations.private_storage import PrivateArtifactBinding, PrivateArtifactIntegrityError, PrivateCryptoCapabilityError, PrivateStorageError, seal_private_artifact

    binding = PrivateArtifactBinding(
        tenant_id=tenant_id,
        case_id=case_id,
        artifact_kind=kind,
        revision=revision,
        principal_id=principal_id,
    )
    try:
        return seal_private_artifact(payload, binding=binding, key=key, key_id=key_id)
    except PrivateCryptoCapabilityError as exc:
        raise InterviewSnapshotError(str(exc), code="private_crypto_unavailable", public_status="unavailable") from None
    except (PrivateStorageError, PrivateArtifactIntegrityError) as exc:
        raise InterviewSnapshotError("private snapshot seal failed", code="authentication_failed") from exc


def _open_part(envelope: bytes, *, kind: str, revision: str, tenant_id: str, case_id: str, principal_id: str, key: bytes, key_id: str) -> bytes:
    from integrations.private_storage import PrivateArtifactBinding, PrivateArtifactIntegrityError, PrivateCryptoCapabilityError, open_private_artifact

    binding = PrivateArtifactBinding(
        tenant_id=tenant_id,
        case_id=case_id,
        artifact_kind=kind,
        revision=revision,
        principal_id=principal_id,
    )
    try:
        return open_private_artifact(envelope, binding=binding, key=key, expected_key_id=key_id)
    except PrivateCryptoCapabilityError as exc:
        raise InterviewSnapshotError(str(exc), code="private_crypto_unavailable", public_status="unavailable") from None
    except PrivateArtifactIntegrityError as exc:
        raise InterviewSnapshotError("private snapshot authentication failed", code="authentication_failed") from exc


def _head_document(dir_fd: int) -> dict[str, Any] | None:
    try:
        raw = _interview_read(dir_fd, "head.json")
    except FileNotFoundError:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InterviewSnapshotError("snapshot head is corrupt", code="corrupt_head") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != INTERVIEW_HEAD_SCHEMA:
        raise InterviewSnapshotError("snapshot head is corrupt", code="corrupt_head")
    return payload


def _legacy_bytes(dir_fd: int) -> bytes | None:
    try:
        return _interview_read(dir_fd, UNENCRYPTED_INTERVIEW_NAME)
    except FileNotFoundError:
        return None


def _part_bodies(snapshot: Mapping[str, Any]) -> dict[str, bytes]:
    graphs = snapshot["graphs"]
    return {
        "complaint-text": str(snapshot["complaint_text"]).encode("utf-8"),
        "transcript": json.dumps(snapshot["transcript"], sort_keys=True).encode("utf-8"),
        "fact-graph": json.dumps(graphs["knowledge_graph"], sort_keys=True).encode("utf-8"),
        "legal-graph": json.dumps(graphs["dependency_graph"], sort_keys=True).encode("utf-8"),
        "export": json.dumps(snapshot["exports"], sort_keys=True).encode("utf-8"),
        "durability-payload": json.dumps(snapshot["durability_payload"], sort_keys=True).encode("utf-8"),
        "interview-snapshot": json.dumps(snapshot, sort_keys=True).encode("utf-8"),
    }


def persist_interview_snapshot(
    directory: str | Path,
    snapshot: Mapping[str, Any],
    *,
    protection: str,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes | None = None,
    key_id: str | None = None,
    expected_revision: str | None = None,
    migrate_plaintext: bool = False,
    fail_before_head: bool = False,
    writer: Callable[[bytes], None] | None = None,
) -> dict[str, Any]:
    """Commit one interview snapshot with private atomic files.

    Encrypted mode seals complaint text, transcripts, both graphs, exports,
    and the durability payload. A locked or missing key never writes plaintext.
    An existing unencrypted snapshot is left byte-for-byte in place.
    """

    if protection not in _INTERVIEW_PROTECTIONS:
        raise InterviewSnapshotError("protection state required", code="protection_required", public_status="unavailable")
    if protection == "user_chosen_encrypted" and (key is None or key_id is None):
        raise InterviewSnapshotError("Private interview keys require unlock.", code="unlock_needed", public_status="unlock_needed")
    document = validate_interview_snapshot(snapshot)
    root_fd = _interview_prepare(Path(directory))
    lock_fd = -1
    try:
        lock_fd = _interview_lock(root_fd)
        legacy = _legacy_bytes(root_fd)
        if protection == "user_chosen_encrypted":
            if legacy is not None and not migrate_plaintext:
                raise InterviewSnapshotError(
                    "Prior unencrypted snapshot requires explicit migration.",
                    code="migration_required",
                )
        try:
            head = _head_document(root_fd)
        except InterviewSnapshotError as exc:
            if exc.code != "corrupt_head":
                raise
            head = None
        if head and head.get("protection") == "user_chosen_encrypted" and protection == "user_chosen_plaintext":
            raise InterviewSnapshotError(
                "Encrypted interview snapshots do not fall back to plaintext.",
                code="plaintext_fallback_refused",
            )
        current = str((head or {}).get("revision") or "0")
        expected = "0" if expected_revision in {None, ""} else str(expected_revision)
        if current != expected:
            raise InterviewSnapshotError(
                "The interview snapshot changed; retry from its current revision.",
                code="revision_conflict",
            )
        next_revision = str(int(current) + 1)
        document["revision"] = next_revision
        document["durability_payload"] = {
            **dict(document.get("durability_payload") or {}),
            "previous_revision": current,
            "committed_revision": next_revision,
        }
        document = validate_interview_snapshot(document)
        revision_label = "snapshot-rev-" + next_revision
        part_names: dict[str, str] = {}
        if protection == "user_chosen_encrypted":
            assert key is not None and key_id is not None
            for kind, body in _part_bodies(document).items():
                envelope = _seal_part(
                    body, kind=kind, revision=revision_label, tenant_id=tenant_id,
                    case_id=case_id, principal_id=principal_id, key=key, key_id=key_id,
                )
                opened = _open_part(
                    envelope, kind=kind, revision=revision_label, tenant_id=tenant_id,
                    case_id=case_id, principal_id=principal_id, key=key, key_id=key_id,
                )
                if opened != body:
                    raise InterviewSnapshotError("snapshot readback failed", code="readback_mismatch")
                if writer is not None:
                    writer(envelope)
                relative = "parts/" + opaque_storage_filename("snapshot", kind)
                _interview_write_exclusive(root_fd, relative, envelope)
                part_names[kind] = relative
            blob_body = _interview_read(root_fd, part_names["interview-snapshot"])
        else:
            blob_body = json.dumps(document, sort_keys=True).encode("utf-8")
            if writer is not None:
                writer(blob_body)
            relative = "revisions/plain-" + revision_label + "-" + uuid.uuid4().hex + ".json"
            _interview_write_exclusive(root_fd, relative, blob_body)
            part_names = {kind: relative for kind in _INTERVIEW_PART_KINDS}
        if fail_before_head:
            raise InterviewSnapshotError(
                "durability head was not committed; the previous revision stands",
                code="durability_unproven",
            )
        history = [item for item in list((head or {}).get("history") or []) if isinstance(item, dict)]
        history.append({
            "revision": next_revision,
            "blob": part_names["interview-snapshot"],
            "digest": hashlib.sha256(blob_body).hexdigest(),
            "protection": protection,
        })
        new_head = {
            "schema_version": INTERVIEW_HEAD_SCHEMA,
            "revision": next_revision,
            "protection": protection,
            "snapshot_id": document["snapshot_id"],
            "session_id": document["session_id"],
            "blob": part_names["interview-snapshot"],
            "digest": hashlib.sha256(blob_body).hexdigest(),
            "parts": part_names,
            "history": history,
            "status": "committed",
            "migrated_plaintext": bool(legacy is not None and migrate_plaintext),
        }
        encoded_head = json.dumps(new_head, sort_keys=True).encode("utf-8")
        if document["complaint_text"] and document["complaint_text"] in encoded_head.decode("utf-8"):
            raise InterviewSnapshotError("head leaked complaint text", code="receipt_leak")
        _interview_write_exclusive(root_fd, "head.json", encoded_head)
        os.fsync(root_fd)
        if legacy is not None and _legacy_bytes(root_fd) != legacy:
            raise InterviewSnapshotError("unencrypted snapshot was overwritten", code="legacy_overwritten")
        receipt = interview_snapshot_receipt(
            document, status="available", operation_id="interview_snapshot_commit", protection=protection,
        )
        return {"snapshot": document, "receipt": receipt, "head": new_head}
    finally:
        if lock_fd >= 0:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        os.close(root_fd)


def _decode_snapshot_blob(
    raw: bytes,
    *,
    protection: str,
    revision: str,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes | None,
    key_id: str | None,
) -> dict[str, Any]:
    if protection == "user_chosen_plaintext":
        payload = json.loads(raw.decode("utf-8"))
        return validate_interview_snapshot(payload)
    if key is None or key_id is None:
        raise InterviewSnapshotError("Private interview keys require unlock.", code="unlock_needed", public_status="unlock_needed")
    opened = _open_part(
        raw, kind="interview-snapshot", revision="snapshot-rev-" + revision,
        tenant_id=tenant_id, case_id=case_id, principal_id=principal_id, key=key, key_id=key_id,
    )
    payload = json.loads(opened.decode("utf-8"))
    return validate_interview_snapshot(payload)


def load_interview_snapshot(
    directory: str | Path,
    *,
    protection: str,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes | None = None,
    key_id: str | None = None,
) -> dict[str, Any]:
    """Open the latest valid snapshot. Wrong keys never return plaintext."""

    if protection not in _INTERVIEW_PROTECTIONS:
        raise InterviewSnapshotError("protection state required", code="protection_required", public_status="unavailable")
    if protection == "user_chosen_encrypted" and (key is None or key_id is None):
        raise InterviewSnapshotError("Private interview keys require unlock.", code="unlock_needed", public_status="unlock_needed")
    root_fd = _interview_prepare(Path(directory))
    lock_fd = -1
    try:
        lock_fd = _interview_lock(root_fd)
        legacy = _legacy_bytes(root_fd)
        try:
            head = _head_document(root_fd)
        except InterviewSnapshotError as exc:
            if exc.code != "corrupt_head":
                raise
            head = None
        if head is None:
            if protection == "user_chosen_encrypted":
                raise InterviewSnapshotError(
                    "No encrypted interview snapshot is committed.",
                    code="migration_required" if legacy is not None else "snapshot_missing",
                )
            if legacy is None:
                raise InterviewSnapshotError("No interview snapshot is committed.", code="snapshot_missing")
            payload = validate_interview_snapshot(json.loads(legacy.decode("utf-8")))
            receipt = interview_snapshot_receipt(
                payload, status="available", operation_id="interview_snapshot_load", protection=protection,
            )
            return {"snapshot": payload, "receipt": receipt, "recovered": False}
        if head.get("protection") == "user_chosen_encrypted" and protection != "user_chosen_encrypted":
            raise InterviewSnapshotError(
                "Encrypted interview snapshots do not fall back to plaintext.",
                code="plaintext_fallback_refused",
            )
        if protection == "user_chosen_encrypted" and head.get("protection") != "user_chosen_encrypted":
            raise InterviewSnapshotError(
                "Prior unencrypted snapshot requires explicit migration.",
                code="migration_required",
            )
        candidates = list(reversed([item for item in list(head.get("history") or []) if isinstance(item, dict)]))
        if not candidates:
            candidates = [{"revision": head.get("revision"), "blob": head.get("blob"), "digest": head.get("digest"), "protection": head.get("protection")}]
        auth_failed = False
        for item in candidates:
            blob_name = str(item.get("blob") or "")
            revision = str(item.get("revision") or "")
            item_protection = str(item.get("protection") or head.get("protection") or "")
            if protection == "user_chosen_encrypted" and item_protection != "user_chosen_encrypted":
                continue
            if not blob_name or blob_name.endswith(".json") and protection == "user_chosen_encrypted":
                continue
            try:
                raw = _interview_read(root_fd, blob_name)
            except (FileNotFoundError, OSError):
                continue
            digest = str(item.get("digest") or "")
            if digest and hashlib.sha256(raw).hexdigest() != digest:
                continue
            try:
                payload = _decode_snapshot_blob(
                    raw, protection=item_protection, revision=revision, tenant_id=tenant_id,
                    case_id=case_id, principal_id=principal_id, key=key, key_id=key_id,
                )
            except InterviewSnapshotError as exc:
                if exc.code == "authentication_failed":
                    auth_failed = True
                    continue
                if exc.code in {"snapshot_invalid", "unsupported_schema"}:
                    continue
                raise
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            recovered = str(payload.get("revision")) != str(head.get("revision"))
            receipt = interview_snapshot_receipt(
                payload,
                status="recovered" if recovered else "available",
                operation_id="interview_snapshot_load",
                protection=protection,
                error_category="operation_error" if recovered else "",
                recovered_from=str(head.get("revision") or "") if recovered else None,
            )
            return {"snapshot": payload, "receipt": receipt, "recovered": recovered}
        if auth_failed:
            raise InterviewSnapshotError("private snapshot authentication failed", code="authentication_failed")
        raise InterviewSnapshotError("no valid interview revision remains", code="corrupt_snapshot")
    finally:
        if lock_fd >= 0:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        os.close(root_fd)


def migrate_unencrypted_interview_snapshot(
    directory: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes,
    key_id: str,
) -> dict[str, Any]:
    """Seal a preserved plaintext snapshot without replacing its original bytes."""

    root = Path(directory)
    root_fd = _interview_prepare(root)
    try:
        legacy = _legacy_bytes(root_fd)
        try:
            head = _head_document(root_fd)
        except InterviewSnapshotError as exc:
            if exc.code != "corrupt_head":
                raise
            head = None
    finally:
        os.close(root_fd)
    if legacy is None:
        raise InterviewSnapshotError("No owned unencrypted snapshot was found.", code="legacy_missing")
    if head and head.get("protection") == "user_chosen_encrypted":
        return {
            "status": "complete",
            "legacy_plaintext_retained": True,
            "source_bytes_preserved": True,
            "existing_private_preserved": True,
            "revision": head.get("revision"),
        }
    try:
        document = validate_interview_snapshot(json.loads(legacy.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InterviewSnapshotError("Unencrypted snapshot is corrupt and was preserved.", code="corrupt_snapshot") from exc
    result = persist_interview_snapshot(
        root, document, protection="user_chosen_encrypted", tenant_id=tenant_id, case_id=case_id,
        principal_id=principal_id, key=key, key_id=key_id, migrate_plaintext=True,
        expected_revision=str((head or {}).get("revision") or "0"),
    )
    preserved = (root / UNENCRYPTED_INTERVIEW_NAME).read_bytes()
    if preserved != legacy:
        raise InterviewSnapshotError("unencrypted snapshot was overwritten", code="legacy_overwritten")
    result["legacy_plaintext_retained"] = True
    result["source_bytes_preserved"] = True
    return result


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
    "store_automatic_private_artifact",
    "AUTOMATIC_PRIVATE_ARTIFACT_KINDS",
    "retrieve_bytes",
    "retrieve_private_artifact",
    "pin_cid",
    "configure_replica_policy",
    "replica_policy",
    "select_private_storage_mode",
    "remote_storage_activation_count",
    "publish_encrypted_replicas",
    "reconcile_encrypted_replicas",
    "restore_encrypted_replicas",
    "restore_encrypted_workspace",
    "count_verified_ciphertext_replicas",
    "upstream_replica_fixture_qualification",
    "upstream_replication_fixture_qualification",
    "UPSTREAM_REPLICA_FIXTURES",
    "storage_backend_status",
    "translate_kit_operation_result",
    "IPFS_AVAILABLE",
    "IPFS_ERROR",
    "RESIDUAL_METADATA_EXPOSURE",
    "PADDING_POLICY",
    "project_public_cid_metadata",
    "opaque_storage_filename",
    "clear_public_index",
    "publish_public_index_entry",
    "public_index_snapshot",
    "redact_private_diagnostic",
    "emit_default_storage_log",
    "optional_size_padding",
    "INTERVIEW_SNAPSHOT_SCHEMA",
    "InterviewSnapshotError",
    "assemble_interview_snapshot",
    "validate_interview_snapshot",
    "interview_snapshot_receipt",
    "persist_interview_snapshot",
    "load_interview_snapshot",
    "migrate_unencrypted_interview_snapshot",
    "UNENCRYPTED_INTERVIEW_NAME",
]
