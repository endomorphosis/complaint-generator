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

Artifact sealing takes an injected per-case data key. User ownership lives in
``UserOwnedKeySession``: high-entropy master and data keys stay unwrapped only
in an unlocked session. Disk receives authenticated wrapped keys plus salt,
KDF, schema, and opaque key ids, under owner-only directory and file modes.
Wrapping is a user passphrase or an explicitly supplied OS keyring. A missing
or locked keyring is an actionable unlock state with a passphrase or recovery
import path. It never writes a raw ``.key`` file, derives a key from
machine-id, hostname, or a constant, or copies key bytes into the environment.
FILE, ENVIRONMENT, HSM, VAULT, and TPM backends stay unused.

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

import base64
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
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


KEY_STORE_SCHEMA = "complaint-generator/private-key-store"
KEY_STORE_VERSION = 1
KEY_RECOVERY_SCHEMA = "complaint-generator/private-key-recovery"
KEY_RECOVERY_VERSION = 1
KEY_STORE_FILENAME = "keystore.json"
MASTER_WRAP_AAD = b"complaint-generator/private-key/master-wrap@1\x00"
DATA_WRAP_DOMAIN = b"complaint-generator/private-key/data-wrap@1\x00"
RECOVERY_WRAP_DOMAIN = b"complaint-generator/private-key/recovery@1\x00"
SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
_KEYRING_SERVICE = "complaint-generator.private-keys"
_RECEIPT_FIELDS = (
    "status",
    "code",
    "protection",
    "unlocked",
    "actions",
    "message",
    "awaiting_user",
    "worker_may_continue",
    "worker_state",
    "unlock_is_remote_consent",
    "cloud_processing_enabled",
    "overwrites_encrypted_state",
    "raw_key_persisted",
    "protection_downgrade",
    "case_count",
    "invented_key",
    "privacy_bypassed",
    "deliberate_export",
    "automatic_backup",
)


class PrivateKeyLockedError(PrivateKeyMaterialError):
    """Existing wrapped keys cannot be used or replaced until the user unlocks.

    The coding supervisor is not asked to invent a key. Independent work can
    continue while this state is waiting on the user.
    """

    def __init__(
        self,
        message: str,
        *,
        actions: Sequence[str],
        protection: str | None = None,
        code: str = "unlock_needed",
    ) -> None:
        super().__init__(code)
        self.message = str(message)
        self.actions = tuple(actions)
        self.protection = protection
        self.public_code = code

    def public_state(self) -> dict[str, Any]:
        return _public_key_state(
            status="unlock_needed" if self.public_code == "unlock_needed" else "keyring_unavailable",
            code=self.public_code,
            protection=self.protection,
            unlocked=False,
            actions=self.actions,
            message=self.message,
            awaiting_user=True,
        )


def _public_key_state(
    *,
    status: str,
    code: str,
    protection: str | None,
    unlocked: bool,
    actions: Sequence[str],
    message: str,
    awaiting_user: bool,
    case_count: int = 0,
) -> dict[str, Any]:
    return {
        "status": status,
        "code": code,
        "protection": protection,
        "unlocked": unlocked,
        "actions": list(actions),
        "message": message,
        "awaiting_user": awaiting_user,
        "worker_may_continue": True,
        "worker_state": "ready_for_independent_tasks",
        "unlock_is_remote_consent": False,
        "cloud_processing_enabled": False,
        "overwrites_encrypted_state": False,
        "raw_key_persisted": False,
        "protection_downgrade": False,
        "case_count": case_count,
        "invented_key": False,
        "privacy_bypassed": False,
    }


def task_key_receipt(state: Mapping[str, Any]) -> dict[str, Any]:
    """Fields safe for a task receipt. Passphrases and key bytes are omitted."""

    receipt = {field: state[field] for field in _RECEIPT_FIELDS if field in state}
    leaked = {"passphrase", "password", "master_key", "data_key", "wrapping_key", "salt", "ciphertext"}
    if leaked.intersection(receipt):
        raise PrivateKeyMaterialError("receipt_leak")
    return receipt


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise PrivateArtifactIntegrityError("malformed")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:
        raise PrivateArtifactIntegrityError("malformed") from exc


def _random_secret() -> bytes:
    try:
        material = os.urandom(DATA_KEY_BYTES)
    except Exception as exc:
        raise PrivateCryptoCapabilityError("secure random source unavailable") from exc
    if not isinstance(material, bytes) or len(material) != DATA_KEY_BYTES or material == bytes(DATA_KEY_BYTES):
        raise PrivateCryptoCapabilityError("secure random source failed")
    return material


def _opaque_key_id(prefix: str) -> str:
    return prefix + os.urandom(16).hex()


def _kdf_bytes(passphrase: str, salt: bytes) -> bytes:
    if not isinstance(passphrase, str) or passphrase == "":
        raise PrivateKeyMaterialError("passphrase_required")
    if not isinstance(salt, bytes) or len(salt) < 16:
        raise PrivateArtifactIntegrityError("malformed")
    try:
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except Exception as exc:
        raise PrivateCryptoCapabilityError("scrypt is unavailable") from exc
    try:
        derived = Scrypt(salt=salt, length=DATA_KEY_BYTES, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(
            passphrase.encode("utf-8")
        )
    except Exception as exc:
        raise PrivateCryptoCapabilityError("scrypt failed") from exc
    return _require_data_key(derived)


def _wrap_secret(wrapping_key: bytes, plaintext: bytes, aad: bytes) -> dict[str, str]:
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = _aesgcm_context(wrapping_key).encrypt(nonce, plaintext, aad)
    return {"nonce": _b64e(nonce), "ciphertext": _b64e(ciphertext)}


def _unwrap_secret(wrapping_key: bytes, wrapped: Mapping[str, Any], aad: bytes) -> bytes:
    if not isinstance(wrapped, Mapping):
        raise PrivateArtifactIntegrityError("malformed")
    nonce = _b64d(str(wrapped.get("nonce") or ""))
    ciphertext = _b64d(str(wrapped.get("ciphertext") or ""))
    if len(nonce) != NONCE_BYTES or len(ciphertext) < TAG_BYTES:
        raise PrivateArtifactIntegrityError("malformed")
    try:
        opened = _aesgcm_context(wrapping_key).decrypt(nonce, ciphertext, aad)
    except Exception as exc:
        raise PrivateArtifactIntegrityError("authentication_failed") from exc
    return _require_data_key(opened)


def _data_aad(tenant_id: str, case_id: str, key_id: str) -> bytes:
    _require_label(tenant_id)
    _require_label(case_id)
    _require_key_id(key_id)
    return DATA_WRAP_DOMAIN + tenant_id.encode("utf-8") + b"\x00" + case_id.encode("utf-8") + b"\x00" + key_id.encode("utf-8")


def _recovery_aad(tenant_id: str, case_id: str, key_id: str) -> bytes:
    return RECOVERY_WRAP_DOMAIN + _data_aad(tenant_id, case_id, key_id)


def _kdf_metadata(salt: bytes) -> dict[str, Any]:
    return {
        "name": "scrypt",
        "n": SCRYPT_N,
        "r": SCRYPT_R,
        "p": SCRYPT_P,
        "length": DATA_KEY_BYTES,
        "salt": _b64e(salt),
    }


def _reject_secret_path(path: Path) -> None:
    name = path.name.lower()
    if name.endswith(".key") or name in {"master.key", "data.key"}:
        raise PrivateKeyMaterialError("raw_key_path")
    lowered = {part.lower() for part in path.parts}
    if "backups" in lowered or "backup" in lowered:
        raise PrivateKeyMaterialError("recovery_is_not_a_backup")


def _assert_owner_mode(path: Path, expected: int) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != expected:
        raise PrivateKeyMaterialError("permissions")


def _write_private_bytes(path: Path, payload: bytes, *, protect_parent: bool) -> None:
    _reject_secret_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if protect_parent:
        os.chmod(path.parent, 0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        view = payload
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise PrivateStorageError("key store write failed", code="key_store_io")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)
    if protect_parent:
        _assert_owner_mode(path.parent, 0o700)
    _assert_owner_mode(path, 0o600)


def _read_private_bytes(path: Path) -> bytes:
    _assert_owner_mode(path.parent, 0o700)
    _assert_owner_mode(path, 0o600)
    return path.read_bytes()


class UserOwnedKeySession:
    """Passphrase- or keyring-wrapped master key with per-case data keys.

    Unwrapped keys exist only in this object. ``lock`` drops them. A fresh
    process starts locked. Creating or importing over an existing store while
    locked is refused.
    """

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        _reject_secret_path(self.directory)
        self.path = self.directory / KEY_STORE_FILENAME
        self._document: dict[str, Any] | None = None
        self._master: bytes | None = None
        self._master_id: str | None = None
        self._data_keys: dict[tuple[str, str], tuple[str, bytes]] = {}
        if self.path.exists():
            self._document = self._load_document()

    @property
    def unlocked(self) -> bool:
        return self._master is not None

    def public_state(self) -> dict[str, Any]:
        document = self._document
        if document is None:
            return _public_key_state(
                status="absent",
                code="key_store_absent",
                protection=None,
                unlocked=False,
                actions=("create_with_passphrase", "create_with_keyring", "recovery_import"),
                message="No wrapped key store exists. Create one with a passphrase or an available keyring, or import recovery material.",
                awaiting_user=True,
            )
        protection = str(document.get("protection") or "")
        case_count = len(document.get("cases") or {})
        if self.unlocked:
            return _public_key_state(
                status="unlocked",
                code="unlocked",
                protection=protection,
                unlocked=True,
                actions=("lock", "recovery_export"),
                message="Keys are unwrapped in this session only.",
                awaiting_user=False,
                case_count=case_count,
            )
        actions = ["recovery_import"]
        if protection == "passphrase":
            actions.insert(0, "passphrase_unlock")
        elif protection == "keyring":
            actions.insert(0, "keyring_unlock")
            actions.append("passphrase_or_recovery_instead_of_raw_file")
        return _public_key_state(
            status="unlock_needed",
            code="unlock_needed",
            protection=protection,
            unlocked=False,
            actions=actions,
            message="Wrapped keys are locked. Unlock with the configured method or import a deliberate recovery export. No raw key file will be written.",
            awaiting_user=True,
            case_count=case_count,
        )

    def create(
        self,
        *,
        protection: str,
        passphrase: str | None = None,
        keyring: Any = None,
    ) -> dict[str, Any]:
        if protection not in {"passphrase", "keyring"}:
            raise PrivateKeyMaterialError("protection_mode")
        if self.path.exists():
            raise PrivateKeyLockedError(
                "A wrapped key store already exists and will not be replaced.",
                actions=self.public_state()["actions"],
                protection=str((self._document or {}).get("protection") or protection),
            )
        master = _random_secret()
        master_id = _opaque_key_id("m-")
        if protection == "passphrase":
            salt = os.urandom(16)
            wrapped = _wrap_secret(_kdf_bytes(str(passphrase), salt), master, MASTER_WRAP_AAD)
            document = self._new_document(
                protection="passphrase",
                master_id=master_id,
                wrapped=wrapped,
                kdf=_kdf_metadata(salt),
            )
        else:
            adapter = _require_keyring(keyring)
            wrapping = _random_secret()
            account = _opaque_key_id("kr-")
            try:
                adapter.set_password(_KEYRING_SERVICE, account, _b64e(wrapping))
            except Exception as exc:
                raise PrivateKeyLockedError(
                    "The OS keyring is unavailable or locked. Use a passphrase or import recovery material. A raw key file was not written.",
                    actions=("create_with_passphrase", "recovery_import"),
                    code="keyring_unavailable",
                ) from exc
            document = self._new_document(
                protection="keyring",
                master_id=master_id,
                wrapped=_wrap_secret(wrapping, master, MASTER_WRAP_AAD),
                kdf=None,
                keyring_account=account,
            )
        self._write_document(document)
        self._document = document
        self._master = master
        self._master_id = master_id
        return self.public_state()

    def unlock_passphrase(self, passphrase: str) -> dict[str, Any]:
        document = self._require_document()
        if document.get("protection") != "passphrase":
            raise PrivateKeyLockedError(
                "This store is not passphrase-wrapped. Retry the keyring or import a deliberate recovery export into a new store.",
                actions=("keyring_unlock", "recovery_import"),
                protection=str(document.get("protection") or ""),
                code="keyring_unavailable" if document.get("protection") == "keyring" else "unlock_needed",
            )
        kdf = document.get("kdf")
        if not isinstance(kdf, Mapping) or kdf.get("name") != "scrypt":
            raise PrivateArtifactIntegrityError("malformed")
        if int(kdf.get("n") or 0) != SCRYPT_N or int(kdf.get("r") or 0) != SCRYPT_R or int(kdf.get("p") or 0) != SCRYPT_P:
            raise PrivateArtifactIntegrityError("malformed")
        try:
            master = _unwrap_secret(
                _kdf_bytes(passphrase, _b64d(str(kdf.get("salt") or ""))),
                document.get("wrapped_master") or {},
                MASTER_WRAP_AAD,
            )
        except PrivateArtifactIntegrityError as exc:
            self.lock()
            raise PrivateArtifactIntegrityError(exc.reason) from None
        self._install_master(document, master)
        return self.public_state()

    def unlock_keyring(self, keyring: Any = None) -> dict[str, Any]:
        document = self._require_document()
        if document.get("protection") != "keyring":
            raise PrivateKeyLockedError(
                "This store is passphrase-wrapped. A keyring unlock was not attempted and no raw key file was written.",
                actions=("passphrase_unlock", "recovery_import"),
                protection="passphrase",
            )
        adapter = keyring if keyring is not None else _optional_system_keyring()
        if adapter is None:
            raise PrivateKeyLockedError(
                "No OS keyring is available. Unlock by importing a deliberate recovery export or creating a new passphrase-protected store. The existing store was not rewritten.",
                actions=("recovery_import", "create_with_passphrase"),
                protection="keyring",
                code="keyring_unavailable",
            )
        account = str(document.get("keyring_account") or "")
        try:
            stored = adapter.get_password(_KEYRING_SERVICE, account)
        except Exception as exc:
            raise PrivateKeyLockedError(
                "The OS keyring is locked. Enter a recovery export or retry the keyring. The wrapped store was not replaced with a raw key.",
                actions=("recovery_import", "keyring_unlock"),
                protection="keyring",
            ) from exc
        if not isinstance(stored, str) or stored == "":
            raise PrivateKeyLockedError(
                "The OS keyring did not return the wrapping key. Import recovery material or retry the keyring.",
                actions=("recovery_import", "keyring_unlock"),
                protection="keyring",
            )
        try:
            wrapping = _b64d(stored)
            master = _unwrap_secret(wrapping, document.get("wrapped_master") or {}, MASTER_WRAP_AAD)
        except PrivateArtifactIntegrityError as exc:
            self.lock()
            raise PrivateArtifactIntegrityError(exc.reason) from None
        self._install_master(document, master)
        return self.public_state()

    def lock(self) -> dict[str, Any]:
        if self._master is not None:
            self._master = bytes(DATA_KEY_BYTES)
            self._master = None
        self._data_keys.clear()
        self._master_id = None
        return self.public_state()

    def ensure_data_key(self, tenant_id: str, case_id: str) -> str:
        _require_label(tenant_id)
        _require_label(case_id)
        if not self.unlocked or self._master is None or self._document is None:
            raise PrivateKeyLockedError(
                "The case key is locked, so encrypted state was left unchanged.",
                actions=self.public_state()["actions"],
                protection=(self._document or {}).get("protection") if isinstance(self._document, dict) else None,
            )
        found = self._data_keys.get((tenant_id, case_id))
        if found is not None:
            return found[0]
        key_id = _opaque_key_id("d-")
        data_key = _random_secret()
        cases = dict(self._document.get("cases") or {})
        cases[f"{tenant_id}\n{case_id}"] = {
            "tenant_id": tenant_id,
            "case_id": case_id,
            "data_key_id": key_id,
            "wrapped_data_key": _wrap_secret(self._master, data_key, _data_aad(tenant_id, case_id, key_id)),
        }
        updated = dict(self._document)
        updated["cases"] = cases
        self._write_document(updated)
        self._document = updated
        self._data_keys[(tenant_id, case_id)] = (key_id, data_key)
        return key_id

    def provider(self) -> InjectedCaseKeyProvider:
        if not self.unlocked:
            raise PrivateKeyLockedError(
                "Cannot build an in-memory key provider while locked.",
                actions=self.public_state()["actions"],
                protection=(self._document or {}).get("protection") if isinstance(self._document, dict) else None,
            )
        return InjectedCaseKeyProvider(dict(self._data_keys))

    def export_recovery(self, tenant_id: str, case_id: str, recovery_passphrase: str, destination: str | Path | None = None) -> dict[str, Any]:
        if not self.unlocked:
            raise PrivateKeyLockedError(
                "Recovery export requires an unlocked session. Nothing was written.",
                actions=self.public_state()["actions"],
                protection=(self._document or {}).get("protection") if isinstance(self._document, dict) else None,
            )
        key_id = self.ensure_data_key(tenant_id, case_id)
        _key_id, data_key = self._data_keys[(tenant_id, case_id)]
        salt = os.urandom(16)
        payload = {
            "schema": KEY_RECOVERY_SCHEMA,
            "schema_version": KEY_RECOVERY_VERSION,
            "deliberate_export": True,
            "automatic_backup": False,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "data_key_id": key_id,
            "kdf": _kdf_metadata(salt),
            "wrapped_data_key": _wrap_secret(
                _kdf_bytes(recovery_passphrase, salt),
                data_key,
                _recovery_aad(tenant_id, case_id, key_id),
            ),
        }
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        if destination is not None:
            target = Path(destination)
            _reject_secret_path(target)
            if target.is_dir():
                raise PrivateKeyMaterialError("recovery_destination")
            _write_private_bytes(target, encoded, protect_parent=False)
        return {
            "deliberate_export": True,
            "automatic_backup": False,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "data_key_id": key_id,
            "bytes": encoded,
            "unlock_is_remote_consent": False,
        }

    def import_recovery(
        self,
        payload: bytes | str | Mapping[str, Any],
        *,
        tenant_id: str,
        case_id: str,
        recovery_passphrase: str,
        store_passphrase: str | None = None,
    ) -> dict[str, Any]:
        _require_label(tenant_id)
        _require_label(case_id)
        document_in = _parse_recovery(payload)
        if document_in.get("automatic_backup") is not False or document_in.get("deliberate_export") is not True:
            raise PrivateKeyMaterialError("recovery_not_deliberate")
        declared_tenant = str(document_in.get("tenant_id") or "")
        declared_case = str(document_in.get("case_id") or "")
        if declared_tenant != tenant_id or declared_case != case_id:
            raise PrivateArtifactBindingError("foreign_case")
        key_id = str(document_in.get("data_key_id") or "")
        kdf = document_in.get("kdf")
        if not isinstance(kdf, Mapping):
            raise PrivateArtifactIntegrityError("malformed")
        data_key = _unwrap_secret(
            _kdf_bytes(recovery_passphrase, _b64d(str(kdf.get("salt") or ""))),
            document_in.get("wrapped_data_key") or {},
            _recovery_aad(tenant_id, case_id, key_id),
        )
        if self.path.exists() and not self.unlocked:
            raise PrivateKeyLockedError(
                "The existing wrapped store is locked, so recovery import did not overwrite it.",
                actions=self.public_state()["actions"],
                protection=str((self._document or {}).get("protection") or ""),
            )
        if self._document is None:
            chosen = store_passphrase if store_passphrase is not None else recovery_passphrase
            self.create(protection="passphrase", passphrase=chosen)
        assert self._master is not None and self._document is not None
        cases = dict(self._document.get("cases") or {})
        slot = f"{tenant_id}\n{case_id}"
        current = cases.get(slot)
        if isinstance(current, Mapping) and current.get("data_key_id") not in {None, key_id}:
            raise PrivateKeyLockedError(
                "This case already has a different data key. The existing wrapped key was kept.",
                actions=("unlock", "recovery_export"),
                protection=str(self._document.get("protection") or ""),
            )
        cases[slot] = {
            "tenant_id": tenant_id,
            "case_id": case_id,
            "data_key_id": key_id,
            "wrapped_data_key": _wrap_secret(self._master, data_key, _data_aad(tenant_id, case_id, key_id)),
        }
        updated = dict(self._document)
        updated["cases"] = cases
        self._write_document(updated)
        self._document = updated
        self._data_keys[(tenant_id, case_id)] = (key_id, data_key)
        state = self.public_state()
        state["imported"] = True
        state["deliberate_export"] = True
        state["automatic_backup"] = False
        return state

    def assert_no_raw_key_files(self) -> None:
        if not self.directory.exists():
            return
        for path in self.directory.rglob("*"):
            if path.is_file() and path.name.lower().endswith(".key"):
                raise PrivateKeyMaterialError("raw_key_persisted")

    def _require_document(self) -> dict[str, Any]:
        if self._document is None:
            raise PrivateKeyMaterialError("key_store_absent")
        return self._document

    def _install_master(self, document: Mapping[str, Any], master: bytes) -> None:
        loaded: dict[tuple[str, str], tuple[str, bytes]] = {}
        cases = document.get("cases") or {}
        if not isinstance(cases, Mapping):
            raise PrivateArtifactIntegrityError("malformed")
        for item in cases.values():
            if not isinstance(item, Mapping):
                raise PrivateArtifactIntegrityError("malformed")
            tenant = str(item.get("tenant_id") or "")
            case = str(item.get("case_id") or "")
            key_id = str(item.get("data_key_id") or "")
            opened = _unwrap_secret(master, item.get("wrapped_data_key") or {}, _data_aad(tenant, case, key_id))
            loaded[(tenant, case)] = (key_id, opened)
        self._master = master
        self._master_id = str(document.get("master_key_id") or "")
        self._data_keys = loaded

    def _new_document(
        self,
        *,
        protection: str,
        master_id: str,
        wrapped: Mapping[str, str],
        kdf: Mapping[str, Any] | None,
        keyring_account: str | None = None,
    ) -> dict[str, Any]:
        document: dict[str, Any] = {
            "schema": KEY_STORE_SCHEMA,
            "schema_version": KEY_STORE_VERSION,
            "protection": protection,
            "algorithm": ALGORITHM_NAME,
            "master_key_id": master_id,
            "wrapped_master": dict(wrapped),
            "cases": {},
            "raw_key_persisted": False,
        }
        if kdf is not None:
            document["kdf"] = dict(kdf)
        if keyring_account is not None:
            document["keyring_service"] = _KEYRING_SERVICE
            document["keyring_account"] = keyring_account
        return document

    def _write_document(self, document: Mapping[str, Any]) -> None:
        encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.directory.mkdir(parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        temporary = self.directory / f".{KEY_STORE_FILENAME}.tmp"
        _write_private_bytes(temporary, encoded, protect_parent=True)
        os.replace(temporary, self.path)
        os.chmod(self.path, 0o600)
        _assert_owner_mode(self.path, 0o600)

    def _load_document(self) -> dict[str, Any]:
        raw = _read_private_bytes(self.path)
        try:
            document = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise PrivateArtifactIntegrityError("malformed") from exc
        if not isinstance(document, dict):
            raise PrivateArtifactIntegrityError("malformed")
        if document.get("schema") != KEY_STORE_SCHEMA or document.get("schema_version") != KEY_STORE_VERSION:
            raise PrivateArtifactIntegrityError("unsupported_version")
        if document.get("protection") not in {"passphrase", "keyring"}:
            raise PrivateArtifactIntegrityError("malformed")
        if document.get("raw_key_persisted") is not False:
            raise PrivateKeyMaterialError("raw_key_persisted")
        return document


def _parse_recovery(payload: bytes | str | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    if isinstance(payload, (bytes, bytearray)):
        try:
            parsed = json.loads(bytes(payload).decode("utf-8"))
        except Exception as exc:
            raise PrivateArtifactIntegrityError("malformed") from exc
    elif isinstance(payload, Mapping):
        parsed = dict(payload)
    else:
        raise PrivateArtifactIntegrityError("malformed")
    if not isinstance(parsed, dict):
        raise PrivateArtifactIntegrityError("malformed")
    if parsed.get("schema") != KEY_RECOVERY_SCHEMA or parsed.get("schema_version") != KEY_RECOVERY_VERSION:
        raise PrivateArtifactIntegrityError("unsupported_version")
    return parsed


def _require_keyring(keyring: Any) -> Any:
    if keyring is None:
        keyring = _optional_system_keyring()
    if keyring is None or not hasattr(keyring, "set_password") or not hasattr(keyring, "get_password"):
        raise PrivateKeyLockedError(
            "The OS keyring is unavailable. Choose passphrase protection or import recovery material. No raw key file was written.",
            actions=("create_with_passphrase", "recovery_import"),
            code="keyring_unavailable",
        )
    return keyring


def _optional_system_keyring() -> Any:
    try:
        import keyring
    except Exception:
        return None
    if not hasattr(keyring, "get_password") or not hasattr(keyring, "set_password"):
        return None
    return keyring


def read_unlock_passphrase(prompt: str = "Private key passphrase", *, getpass_fn: Callable[[str], str] | None = None) -> str:
    """Read a passphrase without echoing it and without accepting argv values."""

    import sys

    for token in sys.argv:
        if not token.startswith("-"):
            continue
        name = token.split("=", 1)[0].lower()
        if name in {"--passphrase", "--password", "--master-key", "--data-key", "--wrapping-key"}:
            raise PrivateKeyMaterialError("secret_in_argv")
    reader = getpass_fn
    if reader is None:
        import getpass

        reader = getpass.getpass
    try:
        value = reader(f"{prompt}: ")
    except Exception as exc:
        raise PrivateKeyMaterialError("passphrase_prompt_failed") from exc
    if not isinstance(value, str) or value == "":
        raise PrivateKeyMaterialError("passphrase_required")
    return value


def assert_store_isolated_from_exports(store_dir: str | Path, export_dir: str | Path) -> None:
    """Refuse to keep a key store inside or next to an encrypted export directory."""

    store = Path(store_dir).resolve()
    export = Path(export_dir).resolve()
    if store == export or store in export.parents or export in store.parents or store.parent == export:
        raise PrivateKeyMaterialError("key_beside_export")


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
    "KEY_STORE_SCHEMA",
    "KEY_RECOVERY_SCHEMA",
    "PrivateKeyLockedError",
    "UserOwnedKeySession",
    "assert_store_isolated_from_exports",
    "read_unlock_passphrase",
    "task_key_receipt",
]
