"""Versioned encrypt-before-addressing boundary for private workspace artifacts.

Public legal-source storage stays on ``integrations.ipfs_datasets.storage.store_bytes``
and is not reclassified as private. This module seals private bytes with
AES-256-GCM before any content identifier, hash, pin, replication, cache, or
durable journal sees them.

The wire envelope carries only opaque routing: schema version, key id, a fresh
96-bit nonce, and ciphertext (including the GCM tag). Tenant, case, principal,
artifact kind, and revision are authenticated as associated data and are not
stored beside the ciphertext. Decrypt uses the caller-expected binding, so a
whole authentic envelope from another case does not open under the caller's
binding.

Key material is injected. Unlock, recovery, and OS keyring persistence belong
to PRIV004. This module does not mint a default key, write a raw ``.key`` file,
or copy key bytes into the process environment. FILE, ENVIRONMENT, HSM, VAULT,
and TPM key backends are intentionally unused.

Dependency contract (not a Kit package version):

* Root ``pyproject.toml`` and ``requirements.txt`` require ``cryptography>=41.0.0``.
* Upstream ``external/ipfs_kit_py/requirements.txt`` floors ``cryptography>=38.0.0``.
  That floor is the Kit library requirement, not the Kit release version.
* Optional ``keyring`` is declared as an extra and is not installed by default.
* ``ipfs_kit_py.aes_encryption.AESEncryption`` encrypts strings with PBKDF2 and
  has no caller associated data, so it is not the bytes contract.
* ``EncryptionManager`` plus an injected MEMORY ``KeyManager`` can apply
  AES-256-GCM with associated data, but ``EncryptedData.to_dict`` exposes
  original size and other rich fields. The canonical envelope does not
  serialize that object. Kit is not started as a daemon.

Existing sessions and artifacts are not migrated here. Coverage of historical
bytes is DUR002. A missing ``cryptography`` install raises
``PrivateCryptoCapabilityError`` and writes nothing. There is no XOR, plaintext
tempfile, or fake encrypted-success path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

SCHEMA_NAME = "private-artifact-aad"
SCHEMA_VERSION = 2
ENVELOPE_AAD_DOMAIN = b"complaint-generator/private-artifact/AES-256-GCM/header@2\x00"
ENVELOPE_MAGIC = b"CGPE"
NONCE_BYTES = 12
TAG_BYTES = 16
DATA_KEY_BYTES = 32
MAX_LABEL_BYTES = 256
MAX_KEY_ID_BYTES = 128
MAX_ENVELOPE_BYTES = 8 * 1024 * 1024
ALGORITHM_NAME = "AES-256-GCM"

# Root contract versus the Kit floor. 38.0.0 is not a Kit package version.
ROOT_CRYPTOGRAPHY_SPEC = "cryptography>=41.0.0"
KIT_CRYPTOGRAPHY_FLOOR = "cryptography>=38.0.0"
KIT_CRYPTOGRAPHY_FLOOR_IS_PACKAGE_VERSION = False

_FORBIDDEN_RECEIPT_FIELDS = frozenset({
    "plaintext",
    "plaintext_length",
    "original_size",
    "size",
    "filename",
    "file_name",
    "description",
    "source_text",
    "complaint_hash",
    "content_hash",
    "name",
    "metadata",
    "content_type",
    "aad",
    "additional_authenticated_data",
    "key",
    "data_key",
    "master_key",
})


class PrivateStorageError(Exception):
    """Base error for the private artifact boundary."""

    code = "private_storage_error"
    recoverable = False

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


class PrivateCryptoCapabilityError(PrivateStorageError):
    """Cryptography cannot perform AES-256-GCM. Callers can recover by retrying later.

    No ciphertext, plaintext fallback, or backend write is produced.
    """

    code = "private_crypto_unavailable"
    recoverable = True
    capability = "aes-256-gcm"

    def __init__(self, message: str = "AES-256-GCM is unavailable") -> None:
        super().__init__(message, code=self.code)


class PrivateArtifactIntegrityError(PrivateStorageError):
    """Envelope authentication, version, or structure check failed."""

    code = "private_artifact_integrity"
    recoverable = False

    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "authentication_failed")
        super().__init__(f"private artifact rejected: {self.reason}", code=self.reason)


class PrivateArtifactBindingError(PrivateStorageError):
    """Caller access does not match the expected principal and case binding."""

    code = "private_artifact_binding"
    recoverable = False

    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "binding_rejected")
        super().__init__(f"private artifact binding rejected: {self.reason}", code=self.reason)


class PrivateKeyMaterialError(PrivateStorageError):
    """Injected per-case key material is missing or the wrong width.

    This is not a license to generate or persist a key.
    """

    code = "private_key_material"
    recoverable = True

    def __init__(self, reason: str = "key_unavailable") -> None:
        self.reason = str(reason or "key_unavailable")
        super().__init__(f"private data key rejected: {self.reason}", code=self.reason)


@dataclass(frozen=True)
class PrivateArtifactBinding:
    """Caller-expected identity bound into AES-GCM associated data."""

    tenant_id: str
    case_id: str
    artifact_kind: str
    revision: str
    principal_id: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise PrivateArtifactIntegrityError("unsupported_version")
        for label in (
            self.tenant_id,
            self.case_id,
            self.artifact_kind,
            self.revision,
            self.principal_id,
        ):
            _require_label(label)


def _require_label(value: str) -> None:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise PrivateArtifactBindingError("empty_label")
    if "\x00" in value or "\n" in value or "\r" in value:
        raise PrivateArtifactBindingError("illegal_label")
    if len(value.encode("utf-8")) > MAX_LABEL_BYTES:
        raise PrivateArtifactBindingError("label_too_long")


def canonical_associated_data(binding: PrivateArtifactBinding) -> bytes:
    """Length-prefixed associated data for the expected binding.

    The envelope does not carry this byte string. Decrypt rebuilds it from the
    caller's expected binding and passes it to AES-GCM.
    """

    if not isinstance(binding, PrivateArtifactBinding):
        raise PrivateArtifactBindingError("binding_type")
    fields: Sequence[str] = (
        SCHEMA_NAME,
        str(binding.schema_version),
        binding.tenant_id,
        binding.case_id,
        binding.principal_id,
        binding.artifact_kind,
        binding.revision,
    )
    chunks: list[bytes] = []
    for field in fields:
        raw = field.encode("utf-8")
        chunks.append(len(raw).to_bytes(4, "big"))
        chunks.append(raw)
    return b"".join(chunks)



def _envelope_associated_data(binding: PrivateArtifactBinding, header: bytes) -> bytes:
    """Version2 binds exact routing bytes as well as the caller's case context.

    Version1 did not authenticate key_id. It is rejected, never silently opened
    with the new scheme; no persisted-session migration is claimed here.
    """
    return ENVELOPE_AAD_DOMAIN + len(header).to_bytes(4, "big") + header + canonical_associated_data(binding)


def cryptography_available() -> bool:
    try:
        load_aesgcm()
    except PrivateCryptoCapabilityError:
        return False
    return True


def load_aesgcm() -> Any:
    """Return ``cryptography`` AESGCM or raise a typed capability error."""

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except Exception as exc:
        raise PrivateCryptoCapabilityError(
            "AES-256-GCM is unavailable because the cryptography package cannot be imported"
        ) from None
    if AESGCM is None:
        raise PrivateCryptoCapabilityError("AES-256-GCM is unavailable")
    return AESGCM



def _aesgcm_context(key: bytes) -> Any:
    try:
        return load_aesgcm()(key)
    except Exception:
        raise PrivateCryptoCapabilityError("AES-256-GCM backend unavailable") from None


def _unsupported_crypto_operation(error: Exception) -> bool:
    if isinstance(error, (ImportError, NotImplementedError, PrivateCryptoCapabilityError)):
        return True
    try:
        from cryptography.exceptions import UnsupportedAlgorithm
    except Exception:
        return False
    return isinstance(error, UnsupportedAlgorithm)


def _require_data_key(key: bytes) -> bytes:
    if not isinstance(key, (bytes, bytearray)) or len(key) != DATA_KEY_BYTES:
        raise PrivateKeyMaterialError("key_width")
    return bytes(key)


def _require_key_id(key_id: str) -> bytes:
    if not isinstance(key_id, str) or key_id.strip() == "" or key_id != key_id.strip():
        raise PrivateKeyMaterialError("key_id")
    raw = key_id.encode("utf-8")
    if len(raw) > MAX_KEY_ID_BYTES or any(byte < 32 or byte > 126 for byte in raw):
        raise PrivateKeyMaterialError("key_id")
    return raw


class InjectedCaseKeyProvider:
    """In-memory map of per-tenant/case data keys supplied by the caller.

    Nothing is written to disk, the environment, or a keyring. Missing entries
    are not replaced with a generated key.
    """

    def __init__(self, material: Mapping[tuple[str, str], tuple[str, bytes]]) -> None:
        stored: dict[tuple[str, str], tuple[str, bytes]] = {}
        for pair, item in dict(material).items():
            if (
                not isinstance(pair, tuple)
                or len(pair) != 2
                or not isinstance(item, tuple)
                or len(item) != 2
            ):
                raise PrivateKeyMaterialError("provider_entry")
            tenant, case = pair
            key_id, key = item
            _require_label(str(tenant))
            _require_label(str(case))
            key_bytes = _require_data_key(key)
            _require_key_id(str(key_id))
            stored[(str(tenant), str(case))] = (str(key_id), key_bytes)
        self._material = stored

    def resolve(self, binding: PrivateArtifactBinding) -> tuple[str, bytes]:
        found = self._material.get((binding.tenant_id, binding.case_id))
        if found is None:
            raise PrivateKeyMaterialError("key_unavailable")
        return found


def assert_access_matches_binding(access: Any, binding: PrivateArtifactBinding) -> None:
    """Require an authenticated or explicit trusted-local principal and case.

    A caller-supplied user id on some other object is not authorization. The
    access object's own principal and case must equal the expected binding.
    """

    trust = str(getattr(access, "trust", "") or "")
    if trust not in {"authenticated", "trusted_local"}:
        raise PrivateArtifactBindingError("access_denied")
    principal = getattr(access, "principal_id", None)
    case_id = getattr(access, "case_id", None)
    if not isinstance(principal, str) or principal != binding.principal_id:
        raise PrivateArtifactBindingError("principal_mismatch")
    if not isinstance(case_id, str) or case_id != binding.case_id:
        raise PrivateArtifactBindingError("case_mismatch")


def seal_private_artifact(
    plaintext: bytes,
    *,
    binding: PrivateArtifactBinding,
    key: bytes,
    key_id: str,
) -> bytes:
    """Encrypt ``plaintext`` into a versioned opaque envelope. No I/O."""

    if not isinstance(plaintext, (bytes, bytearray)):
        raise PrivateArtifactIntegrityError("malformed")
    payload = bytes(plaintext)
    overhead = len(ENVELOPE_MAGIC) + 2 + MAX_KEY_ID_BYTES + NONCE_BYTES + TAG_BYTES
    if len(payload) > MAX_ENVELOPE_BYTES - overhead:
        raise PrivateArtifactIntegrityError("oversized")
    key_bytes = _require_data_key(key)
    key_id_raw = _require_key_id(key_id)
    cipher = _aesgcm_context(key_bytes)
    try:
        nonce = os.urandom(NONCE_BYTES)
    except Exception:
        raise PrivateCryptoCapabilityError("AES-256-GCM secure nonce source unavailable") from None
    if not isinstance(nonce, bytes) or len(nonce) != NONCE_BYTES:
        raise PrivateCryptoCapabilityError("AES-256-GCM nonce source failed")
    header = ENVELOPE_MAGIC + bytes((SCHEMA_VERSION, len(key_id_raw))) + key_id_raw
    associated = _envelope_associated_data(binding, header)
    try:
        ciphertext = cipher.encrypt(nonce, payload, associated)
    except Exception:
        raise PrivateCryptoCapabilityError("AES-256-GCM encrypt failed") from None
    if not isinstance(ciphertext, (bytes, bytearray)) or len(ciphertext) < TAG_BYTES:
        raise PrivateCryptoCapabilityError("AES-256-GCM encrypt returned no ciphertext")
    envelope = b"".join((
        header,
        nonce,
        bytes(ciphertext),
    ))
    if len(envelope) > MAX_ENVELOPE_BYTES:
        raise PrivateArtifactIntegrityError("oversized")
    return envelope


def open_private_artifact(
    envelope: bytes,
    *,
    binding: PrivateArtifactBinding,
    key: bytes,
    expected_key_id: str | None = None,
) -> bytes:
    """Decrypt using caller-expected associated data. Stored headers are not trusted as AAD."""

    parsed = parse_private_envelope(envelope)
    if expected_key_id is not None and parsed["key_id"] != expected_key_id:
        raise PrivateArtifactIntegrityError("authentication_failed")
    key_bytes = _require_data_key(key)
    cipher = _aesgcm_context(key_bytes)
    header = bytes(envelope)[:6 + len(parsed["key_id"].encode("ascii"))]
    associated = _envelope_associated_data(binding, header)
    try:
        plaintext = cipher.decrypt(parsed["nonce"], parsed["ciphertext"], associated)
    except Exception as exc:
        if _unsupported_crypto_operation(exc):
            raise PrivateCryptoCapabilityError("AES-256-GCM decrypt unavailable") from None
        raise PrivateArtifactIntegrityError("authentication_failed") from None
    if not isinstance(plaintext, (bytes, bytearray)):
        raise PrivateArtifactIntegrityError("authentication_failed")
    return bytes(plaintext)


def parse_private_envelope(envelope: bytes) -> dict[str, Any]:
    """Split opaque routing fields. Does not decrypt or return associated data."""

    if not isinstance(envelope, (bytes, bytearray)):
        raise PrivateArtifactIntegrityError("malformed")
    blob = bytes(envelope)
    if len(blob) > MAX_ENVELOPE_BYTES:
        raise PrivateArtifactIntegrityError("oversized")
    minimum = len(ENVELOPE_MAGIC) + 2 + 1 + NONCE_BYTES + TAG_BYTES
    if len(blob) < minimum:
        raise PrivateArtifactIntegrityError("malformed")
    if blob[: len(ENVELOPE_MAGIC)] != ENVELOPE_MAGIC:
        raise PrivateArtifactIntegrityError("malformed")
    version = blob[4]
    if version != SCHEMA_VERSION:
        raise PrivateArtifactIntegrityError("unsupported_version")
    key_id_len = blob[5]
    if key_id_len < 1 or key_id_len > MAX_KEY_ID_BYTES:
        raise PrivateArtifactIntegrityError("malformed")
    cursor = 6
    key_id_end = cursor + key_id_len
    nonce_end = key_id_end + NONCE_BYTES
    if nonce_end + TAG_BYTES > len(blob):
        raise PrivateArtifactIntegrityError("malformed")
    try:
        key_id = blob[cursor:key_id_end].decode("ascii")
    except UnicodeDecodeError as exc:
        raise PrivateArtifactIntegrityError("malformed") from exc
    _require_key_id(key_id)
    nonce = blob[key_id_end:nonce_end]
    ciphertext = blob[nonce_end:]
    return {
        "schema_version": version,
        "key_id": key_id,
        "nonce": nonce,
        "ciphertext": ciphertext,
    }


def _resolve_key(
    binding: PrivateArtifactBinding,
    *,
    key: bytes | None,
    key_id: str | None,
    key_provider: InjectedCaseKeyProvider | None,
) -> tuple[str, bytes]:
    if key is not None or key_id is not None:
        if key is None or key_id is None:
            raise PrivateKeyMaterialError("key_unavailable")
        if key_provider is not None:
            provided_id, provided_key = key_provider.resolve(binding)
            if provided_id != key_id or provided_key != _require_data_key(key):
                raise PrivateKeyMaterialError("key_mismatch")
        return key_id, _require_data_key(key)
    if key_provider is None:
        raise PrivateKeyMaterialError("key_unavailable")
    return key_provider.resolve(binding)


def _opaque_receipt(*, cid: str, key_id: str, pinned: bool, status: str) -> dict[str, Any]:
    receipt = {
        "status": status,
        "cid": cid,
        "schema_version": SCHEMA_VERSION,
        "key_id": key_id,
        "algorithm": ALGORITHM_NAME,
        "pinned": bool(pinned),
        "private_artifact": True,
    }
    leaked = _FORBIDDEN_RECEIPT_FIELDS.intersection(receipt)
    if leaked:
        raise PrivateArtifactIntegrityError("malformed")
    return receipt


def store_private_artifact(
    data: bytes,
    *,
    access: Any,
    tenant_id: str,
    case_id: str,
    artifact_kind: str,
    revision: str,
    principal_id: str | None = None,
    key: bytes | None = None,
    key_id: str | None = None,
    key_provider: InjectedCaseKeyProvider | None = None,
    backend: Any = None,
    backend_name: str | None = None,
    pin_content: bool = True,
    replicate: Callable[[bytes], None] | None = None,
    journal: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Seal ``data`` and only then address, pin, replicate, cache, or journal it.

    ``store_bytes`` remains the public plaintext path. This function never
    writes the original bytes, a raw key, or an unencrypted tempfile.
    """

    load_aesgcm()
    binding = PrivateArtifactBinding(
        tenant_id=tenant_id,
        case_id=case_id,
        artifact_kind=artifact_kind,
        revision=revision,
        principal_id=principal_id if principal_id is not None else tenant_id,
    )
    assert_access_matches_binding(access, binding)
    resolved_id, resolved_key = _resolve_key(
        binding, key=key, key_id=key_id, key_provider=key_provider
    )
    envelope = seal_private_artifact(
        data, binding=binding, key=resolved_key, key_id=resolved_id
    )
    if replicate is not None:
        replicate(envelope)
    from integrations.ipfs_datasets.storage import store_bytes

    stored = store_bytes(
        envelope,
        pin_content=pin_content,
        backend=backend,
        backend_name=backend_name,
    )
    status = str(stored.get("status") or "error")
    cid = str(stored.get("cid") or "")
    if status not in {"available", "degraded"} or not cid:
        raise PrivateStorageError(
            "private artifact backend rejected ciphertext",
            code="backend_rejected",
        )
    receipt = _opaque_receipt(
        cid=cid,
        key_id=resolved_id,
        pinned=bool(pin_content and stored.get("pinned", pin_content)),
        status=status,
    )
    if journal is not None:
        journal(dict(receipt))
    return receipt


def retrieve_private_artifact(
    cid: str,
    *,
    access: Any,
    tenant_id: str,
    case_id: str,
    artifact_kind: str,
    revision: str,
    principal_id: str | None = None,
    key: bytes | None = None,
    key_id: str | None = None,
    key_provider: InjectedCaseKeyProvider | None = None,
    backend: Any = None,
    backend_name: str | None = None,
) -> dict[str, Any]:
    """Load ciphertext by CID and open it only for the caller-expected binding."""

    load_aesgcm()
    if not isinstance(cid, str) or not cid:
        raise PrivateArtifactIntegrityError("malformed")
    binding = PrivateArtifactBinding(
        tenant_id=tenant_id,
        case_id=case_id,
        artifact_kind=artifact_kind,
        revision=revision,
        principal_id=principal_id if principal_id is not None else tenant_id,
    )
    assert_access_matches_binding(access, binding)
    resolved_id, resolved_key = _resolve_key(
        binding, key=key, key_id=key_id, key_provider=key_provider
    )
    from integrations.ipfs_datasets.storage import retrieve_bytes

    loaded = retrieve_bytes(cid, backend=backend, backend_name=backend_name)
    status = str(loaded.get("status") or "error")
    blob = loaded.get("data")
    if status not in {"available", "degraded"} or not isinstance(blob, (bytes, bytearray)):
        raise PrivateStorageError("private artifact ciphertext is unavailable", code="backend_rejected")
    plaintext = open_private_artifact(
        bytes(blob),
        binding=binding,
        key=resolved_key,
        expected_key_id=resolved_id,
    )
    return {
        "status": "available",
        "cid": cid,
        "data": plaintext,
        "schema_version": SCHEMA_VERSION,
        "key_id": resolved_id,
        "algorithm": ALGORITHM_NAME,
        "private_artifact": True,
    }


def kit_crypto_contract() -> dict[str, Any]:
    """Document the Kit versus root cryptography contract without starting Kit."""

    return {
        "root_cryptography_spec": ROOT_CRYPTOGRAPHY_SPEC,
        "kit_cryptography_floor": KIT_CRYPTOGRAPHY_FLOOR,
        "kit_cryptography_floor_is_package_version": KIT_CRYPTOGRAPHY_FLOOR_IS_PACKAGE_VERSION,
        "canonical_algorithm": ALGORITHM_NAME,
        "canonical_implementation": "cryptography.hazmat.primitives.ciphers.aead.AESGCM",
        "aes_encryption_string_api_sufficient": False,
        "encrypted_data_to_dict_used_on_wire": False,
        "key_storage_backends_used": ["injected-memory"],
        "key_storage_backends_rejected": ["file", "environment", "hsm", "vault", "tpm"],
        "keyring_installed_by_default": False,
        "default_key_generated": False,
        "historical_sessions_migrated": False,
        "migration_task": "CIMP-DUR-002",
    }


def kit_memory_gcm_associated_data_probe(
    plaintext: bytes,
    key: bytes,
    associated: bytes,
) -> dict[str, Any]:
    """Optional probe of Kit's MEMORY EncryptionManager. Not used for the envelope.

    Failure or absence is a compatibility note. It does not authorize XOR,
    ``AESEncryption``, rich ``to_dict`` persistence, or a successful private store.
    """

    report: dict[str, Any] = {
        "status": "unavailable",
        "passed": False,
        "substitutes_for_first_party": False,
        "used_on_canonical_envelope": False,
        "reason": "",
    }
    try:
        from ipfs_kit_py.mcp.enterprise.encryption import (
            EncryptionAlgorithm,
            EncryptionManager,
            KeyManager,
            KeyStorageType,
            KeyType,
        )
    except Exception as exc:
        report["reason"] = f"kit encryption manager import failed: {type(exc).__name__}"
        return report
    try:
        manager_key = KeyManager(storage_type=KeyStorageType.MEMORY)
        metadata = manager_key.generate_key(
            KeyType.DATA,
            EncryptionAlgorithm.AES_256_GCM,
            description="probe",
        )
        key_id = str(metadata.id)
        manager_key._key_cache[key_id] = _require_data_key(key)
        encrypted = EncryptionManager(manager_key).encrypt(
            bytes(plaintext),
            key_id=key_id,
            algorithm=EncryptionAlgorithm.AES_256_GCM,
            additional_authenticated_data=bytes(associated),
        )
        opened = EncryptionManager(manager_key).decrypt(encrypted)
        rich = encrypted.to_dict()
        report["rich_to_dict_has_original_size"] = "original_size" in rich
        report["opened"] = opened == bytes(plaintext)
        report["status"] = "qualified" if opened == bytes(plaintext) else "failed"
        report["passed"] = False
        report["reason"] = (
            "Kit MEMORY AES-256-GCM accepts associated data, but EncryptedData.to_dict "
            "is richer than the private envelope and is not the canonical wire format. "
            "AESEncryption remains insufficient because it has no caller associated data."
        )
    except Exception as exc:
        report["status"] = "unavailable"
        report["passed"] = False
        report["reason"] = f"kit memory probe failed: {type(exc).__name__}"
    return report


__all__ = [
    "ALGORITHM_NAME",
    "DATA_KEY_BYTES",
    "ENVELOPE_MAGIC",
    "InjectedCaseKeyProvider",
    "KIT_CRYPTOGRAPHY_FLOOR",
    "KIT_CRYPTOGRAPHY_FLOOR_IS_PACKAGE_VERSION",
    "MAX_ENVELOPE_BYTES",
    "NONCE_BYTES",
    "PrivateArtifactBinding",
    "PrivateArtifactBindingError",
    "PrivateArtifactIntegrityError",
    "PrivateCryptoCapabilityError",
    "PrivateKeyMaterialError",
    "PrivateStorageError",
    "ROOT_CRYPTOGRAPHY_SPEC",
    "SCHEMA_VERSION",
    "assert_access_matches_binding",
    "canonical_associated_data",
    "cryptography_available",
    "kit_crypto_contract",
    "kit_memory_gcm_associated_data_probe",
    "load_aesgcm",
    "open_private_artifact",
    "parse_private_envelope",
    "retrieve_private_artifact",
    "seal_private_artifact",
    "store_private_artifact",
]
