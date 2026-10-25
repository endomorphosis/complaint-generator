"""Recipient-bound encrypted case resource key grants.

The authenticated actor is verified separately from the canonical artifact
owner. They may coincide for a verified adopted owner-only case.
Associated data for a sealed case artifact is the tenant, case, canonical
principal (the case tenant), and revision. A delegated read does not rewrite
that binding and does not impersonate the owner.

A delegated open needs both an accepted membership from
``CaseMembershipStore`` and a key grant wrapped to the recipient's
``UserOwnedKeySession`` wrap key. Membership alone does not unwrap. Browser
keys, the owner master key, and an operational-admin master decrypt are
rejected. Owner reads continue to use the owner session and the existing
envelope contract, including schema version 2.

Reads, writes, downloads, and late-result admission recheck the sealed grant
against the case cutoff. Revocation stops future access and re-wraps surviving
grants at the next generation. A cold store and a stale unlocked session cannot
revive a revoked generation. Revocation does not erase plaintext or key bytes
the recipient already copied.
"""

from __future__ import annotations

import fcntl
import base64
import hashlib
import json
import os
import stat
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from applications.case_directory import CaseDirectory, CaseDirectoryError
from applications.case_membership import CaseMembershipError, CaseMembershipStore
from applications.principal_store import PrincipalStore, PrincipalStoreError
from integrations.private_storage import (
    PrivateArtifactBinding,
    PrivateArtifactIntegrityError,
    PrivateKeyMaterialError,
    UserOwnedKeySession,
    assert_access_matches_binding,
    open_private_artifact,
    parse_private_envelope,
    seal_private_artifact,
)

TASK_ID = "CIMP-GUI-12"
SCHEMA_VERSION = 1
ARTIFACT_KIND = "case-resource-key-grant"
GENERATION_KIND = "case-key-generation"
WRITE_ACTION = "case.message.send"
DOWNLOAD_ACTION = "case.download"
READ_ACTION = "case.read"
LIMITATIONS = (
    "revocation_cannot_erase_already_downloaded_plaintext_or_keys",
    "cold_resume_cannot_recover_revoked_authority",
    "browser_keys_are_rejected",
    "admin_master_decryption_is_rejected",
    "owner_impersonation_does_not_change_aad",
)

BROWSER_KEY_FIELDS = frozenset({
    "key",
    "data_key",
    "master_key",
    "wrap_key",
    "recipient_wrap_key",
    "browser_key",
    "raw_key",
    "private_key",
    "wrapped",
    "wrapped_data_key",
    "nonce",
    "ciphertext",
    "trusted_local",
    "trust",
    "role",
    "roles",
    "is_admin",
    "is_lawyer",
    "grant",
    "key_grant",
    "actions",
    "status",
})


class CaseResourceKeyGrantError(Exception):
    """Fail-closed key-grant error. ``code`` is a stable machine reason."""

    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


@dataclass(frozen=True)
class _CanonicalAccess:
    trust: str
    principal_id: str
    case_id: str


@dataclass(frozen=True)
class ResourceKeyGrant:
    """Wrapped case data key bound to one recipient and one artifact revision."""

    key_grant_id: str
    version: int
    membership_grant_id: str
    membership_version: int
    owner_principal_id: str
    recipient_principal_id: str
    tenant_id: str
    case_id: str
    resource_id: str
    canonical_owner_principal_id: str
    artifact_kind: str
    artifact_revision: str
    data_key_id: str
    recipient_wrap_key_id: str
    wrapped_nonce: str
    wrapped_ciphertext: str
    idempotency_key: str
    status: str = "active"
    generation: int = 1
    historical_wrapped_keys: tuple[tuple[str, str, str], ...] = ()

    def public_view(self) -> dict[str, Any]:
        return {
            "key_grant_id": self.key_grant_id,
            "version": self.version,
            "membership_grant_id": self.membership_grant_id,
            "membership_version": self.membership_version,
            "owner_principal_id": self.owner_principal_id,
            "recipient_principal_id": self.recipient_principal_id,
            "tenant_id": self.tenant_id,
            "case_id": self.case_id,
            "resource_id": self.resource_id,
            "canonical_owner_principal_id": self.canonical_owner_principal_id,
            "actor_is_encrypted_owner": self.owner_principal_id == self.canonical_owner_principal_id,
            "artifact_kind": self.artifact_kind,
            "artifact_revision": self.artifact_revision,
            "data_key_id": self.data_key_id,
            "recipient_wrap_key_id": self.recipient_wrap_key_id,
            "status": self.status,
            "generation": self.generation,
            "historical_data_key_ids": [entry[0] for entry in self.historical_wrapped_keys],
            "schema_version": SCHEMA_VERSION,
            "envelope_schema_version": 2,
            "limitations": list(LIMITATIONS),
        }


def _opaque_id() -> str:
    return uuid.uuid4().hex


def _label(value: str, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise CaseResourceKeyGrantError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise CaseResourceKeyGrantError(code)
    return value


def _artifact_key_id(envelope: bytes) -> str:
    """Read an untrusted routing hint; authenticated open still verifies it."""
    try:
        return str(parse_private_envelope(envelope)["key_id"])
    except PrivateArtifactIntegrityError as exc:
        raise CaseResourceKeyGrantError(exc.reason) from exc


def _identity(grant: ResourceKeyGrant) -> dict[str, Any]:
    return {
        "membership_grant_id": grant.membership_grant_id,
        "membership_version": grant.membership_version,
        "owner_principal_id": grant.owner_principal_id,
        "recipient_principal_id": grant.recipient_principal_id,
        "tenant_id": grant.tenant_id,
        "case_id": grant.case_id,
        "resource_id": grant.resource_id,
        "canonical_owner_principal_id": grant.canonical_owner_principal_id,
        "artifact_kind": grant.artifact_kind,
        "artifact_revision": grant.artifact_revision,
    }


class CaseResourceKeyGrantStore:
    """File-backed recipient key grants for one injected storage key."""

    def __init__(
        self,
        root: str | Path,
        *,
        key: bytes,
        key_id: str,
        principals: PrincipalStore,
        cases: CaseDirectory,
        memberships: CaseMembershipStore,
    ) -> None:
        if not isinstance(key, (bytes, bytearray)) or isinstance(key, memoryview) or len(bytes(key)) != 32:
            raise CaseResourceKeyGrantError("key_material")
        if not isinstance(principals, PrincipalStore) or not isinstance(cases, CaseDirectory):
            raise CaseResourceKeyGrantError("authority_owners")
        if not isinstance(memberships, CaseMembershipStore):
            raise CaseResourceKeyGrantError("membership_owner")
        self._key = bytes(key)
        self._key_id = _label(key_id, "key_id")
        self._principals = principals
        self._cases = cases
        self._memberships = memberships
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        os.chmod(self._root, 0o700)
        self._lock_path = self._root / ".lock"
        self._lock_path.touch(mode=0o600)
        (self._root / "grants").mkdir(mode=0o700, exist_ok=True)
        (self._root / "idem").mkdir(mode=0o700, exist_ok=True)
        (self._root / "generations").mkdir(mode=0o700, exist_ok=True)
        (self._root / "revoke-idem").mkdir(mode=0o700, exist_ok=True)

    def issue(
        self,
        *,
        actor_principal_id: str,
        recipient_principal_id: str,
        membership_grant_id: str,
        membership_version: int,
        case_id: str,
        resource_id: str,
        tenant_id: str,
        artifact_kind: str,
        artifact_revision: str,
        owner_session: UserOwnedKeySession,
        recipient_session: UserOwnedKeySession,
        idempotency_key: str,
    ) -> ResourceKeyGrant:
        """Owner wraps the case data key to the recipient session.

        The actor must be the case owner and must not be written into artifact
        associated data. The recipient must already hold an accepted membership
        for ``case.read``.
        """

        owner = self._active(actor_principal_id)
        recipient = self._active(recipient_principal_id)
        self._reject_admin(owner)
        self._reject_admin(recipient)
        if not isinstance(owner_session, UserOwnedKeySession) or not isinstance(recipient_session, UserOwnedKeySession):
            raise CaseResourceKeyGrantError("key_owner_required")
        if owner_session is recipient_session:
            raise CaseResourceKeyGrantError("owner_impersonation")
        case = self._select(owner.principal_id, case_id)
        if case.owner_principal_id != owner.principal_id:
            raise CaseResourceKeyGrantError("actor_not_owner")
        if tenant_id != case.tenant_id:
            raise CaseResourceKeyGrantError("tenant_mismatch")
        if resource_id != case.resource_id:
            raise CaseResourceKeyGrantError("resource_mismatch")
        if recipient.principal_id == case.tenant_id:
            raise CaseResourceKeyGrantError("owner_impersonation")
        self._require_membership(
            actor_principal_id=recipient.principal_id,
            grant_id=membership_grant_id,
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            expected_version=membership_version,
        )
        kind = _label(artifact_kind, "artifact_kind")
        revision = _label(artifact_revision, "artifact_revision")
        key_name = _label(idempotency_key, "idempotency_key")
        membership_id = _label(membership_grant_id, "membership_grant_id")
        identity = {
            "membership_grant_id": membership_id,
            "membership_version": membership_version,
            "owner_principal_id": owner.principal_id,
            "recipient_principal_id": recipient.principal_id,
            "tenant_id": case.tenant_id,
            "case_id": case.case_id,
            "resource_id": case.resource_id,
            "canonical_owner_principal_id": case.tenant_id,
            "artifact_kind": kind,
            "artifact_revision": revision,
        }
        with self._locked():
            existing_id = self._idem_grant(key_name)
            if existing_id is not None:
                existing = self._load(existing_id)
                if existing.idempotency_key != key_name or _identity(existing) != identity:
                    raise CaseResourceKeyGrantError("replay_mismatch")
                state = self._read_generation(existing.tenant_id, existing.case_id)
                self._reject_inactive_grant(
                    existing,
                    cutoff=int(state["cutoff"]),
                    generation=int(state["generation"]),
                )
                return existing
            generation = self._generation_state(case.tenant_id, case.case_id, case.resource_id)
            wrap_id = recipient_session.ensure_recipient_wrap_key()
            wrap_id_again, wrap_key = recipient_session.recipient_wrap_key()
            if wrap_id_again != wrap_id:
                raise CaseResourceKeyGrantError("recipient_mismatch")
            owner_session.ensure_data_key(case.tenant_id, case.case_id)
            wrapped = owner_session.wrap_case_key_for_recipient(
                tenant_id=case.tenant_id,
                case_id=case.case_id,
                recipient_wrap_key=wrap_key,
                recipient_wrap_key_id=wrap_id,
                canonical_principal_id=case.tenant_id,
                revision=revision,
                recipient_principal_id=recipient.principal_id,
                artifact_kind=kind,
                resource_id=case.resource_id,
                membership_grant_id=membership_id,
                membership_version=membership_version,
            )
            record = ResourceKeyGrant(
                key_grant_id=_opaque_id(),
                version=1,
                membership_grant_id=membership_id,
                membership_version=membership_version,
                owner_principal_id=owner.principal_id,
                recipient_principal_id=recipient.principal_id,
                tenant_id=case.tenant_id,
                case_id=case.case_id,
                resource_id=case.resource_id,
                canonical_owner_principal_id=case.tenant_id,
                artifact_kind=kind,
                artifact_revision=revision,
                data_key_id=str(wrapped["data_key_id"]),
                recipient_wrap_key_id=wrap_id,
                wrapped_nonce=str(wrapped["nonce"]),
                wrapped_ciphertext=str(wrapped["ciphertext"]),
                idempotency_key=key_name,
                status="active",
                generation=int(generation["generation"]),
            )
            current_key_id = generation.get("data_key_id")
            if current_key_id and current_key_id != record.data_key_id:
                raise CaseResourceKeyGrantError("case_key_epoch_mismatch")
            generation["data_key_id"] = record.data_key_id
            self._seal(record)
            self._write_generation(generation)
            self._write_idem(key_name, record.key_grant_id)
            return record

    def issue_from_request(self, body: Mapping[str, Any]) -> ResourceKeyGrant:
        """Request bodies cannot mint a key grant or supply key bytes."""

        if not isinstance(body, Mapping):
            raise CaseResourceKeyGrantError("request_body")
        if any(name in body for name in BROWSER_KEY_FIELDS):
            raise CaseResourceKeyGrantError("browser_key_rejected")
        raise CaseResourceKeyGrantError("request_cannot_mint_key_grant")

    def revoke_and_rotate(
        self,
        *,
        actor_principal_id: str,
        recipient_principal_id: str,
        case_id: str,
        tenant_id: str,
        resource_id: str,
        cutoff: int,
        owner_session: UserOwnedKeySession,
        recipient_sessions: Mapping[str, UserOwnedKeySession] | None = None,
        idempotency_key: str,
        retained_plaintext: bytes | None = None,
        retained_key: bytes | None = None,
    ) -> dict[str, Any]:
        """Revoke one recipient at ``cutoff`` and re-wrap every surviving grant.

        ``cutoff`` must be the current wrap generation. Surviving grants move to
        ``cutoff + 1``. The revoked wrap is wiped from the store. Bytes the
        caller already holds are reported as still present.
        """

        owner = self._active(actor_principal_id)
        recipient = self._active(recipient_principal_id)
        self._reject_admin(owner)
        self._reject_admin(recipient)
        if type(cutoff) is not int or cutoff < 1:
            raise CaseResourceKeyGrantError("cutoff_invalid")
        if not isinstance(owner_session, UserOwnedKeySession):
            raise CaseResourceKeyGrantError("key_owner_required")
        sessions = {} if recipient_sessions is None else recipient_sessions
        if not isinstance(sessions, Mapping):
            raise CaseResourceKeyGrantError("recipient_session_required")
        if recipient.principal_id in sessions:
            raise CaseResourceKeyGrantError("revoked_session_rejected")
        for principal_id, session in sessions.items():
            if not isinstance(principal_id, str) or not isinstance(session, UserOwnedKeySession):
                raise CaseResourceKeyGrantError("recipient_session_required")
        case = self._select(owner.principal_id, case_id)
        if case.owner_principal_id != owner.principal_id:
            raise CaseResourceKeyGrantError("actor_not_owner")
        if tenant_id != case.tenant_id:
            raise CaseResourceKeyGrantError("tenant_mismatch")
        if resource_id != case.resource_id:
            raise CaseResourceKeyGrantError("resource_mismatch")
        key_name = _label(idempotency_key, "idempotency_key")
        operation_identity = {"actor_principal_id": owner.principal_id,
            "recipient_principal_id": recipient.principal_id, "tenant_id": case.tenant_id,
            "case_id": case.case_id, "resource_id": case.resource_id, "cutoff": cutoff,
            "idempotency_sha256": hashlib.sha256(key_name.encode()).hexdigest()}
        operation_id = hashlib.sha256(json.dumps(operation_identity, sort_keys=True,
                                                 separators=(",", ":")).encode()).hexdigest()
        owner_session.ensure_data_key(case.tenant_id, case.case_id)
        with self._locked():
            state = self._generation_state(case.tenant_id, case.case_id, case.resource_id, allow_pending=True)
            replay = self._revoke_replay(key_name)
            pending = state.get("pending_revoke")
            if replay is not None:
                if any(replay.get(k) != v for k, v in operation_identity.items() if k != "idempotency_sha256"):
                    raise CaseResourceKeyGrantError("replay_mismatch")
                if pending is None:
                    return _revoke_view(replay, retained_plaintext, retained_key)
            if pending is None and state.get("last_revoke", {}).get("operation_id") == operation_id:
                summary = state["last_revoke"]["summary"]
                self._write_revoke_replay(key_name, summary)
                return _revoke_view(summary, retained_plaintext, retained_key)
            if pending is not None:
                if pending.get("operation_id") != operation_id or pending.get("identity") != operation_identity:
                    raise CaseResourceKeyGrantError("case_key_rotation_incomplete")
                grants = [_grant_from_document(doc) for doc in pending["grants"]]
            else:
                if int(state["generation"]) != cutoff or int(state["cutoff"]) >= cutoff:
                    raise CaseResourceKeyGrantError("cutoff_mismatch")
                grants = [grant for grant in self._grants_for_case(case.tenant_id, case.case_id)
                          if grant.status == "active"]
            targets = [grant for grant in grants if grant.recipient_principal_id == recipient.principal_id]
            if not targets:
                raise CaseResourceKeyGrantError("grant_not_active")
            if any(grant.generation != cutoff for grant in grants):
                raise CaseResourceKeyGrantError("stale_grant_generation")
            survivors = [grant for grant in grants if grant not in targets]
            missing = sorted({grant.recipient_principal_id for grant in survivors
                              if grant.recipient_principal_id not in sessions})
            if missing:
                raise CaseResourceKeyGrantError("recipient_session_required")
            # Validate every recipient before changing any key epoch.
            for grant in survivors:
                wrap_id, _wrap_key = sessions[grant.recipient_principal_id].recipient_wrap_key()
                if wrap_id != grant.recipient_wrap_key_id:
                    raise CaseResourceKeyGrantError("recipient_mismatch")
            old_key_id = str(state.get("data_key_id") or targets[0].data_key_id)
            if any(grant.data_key_id != old_key_id for grant in grants):
                raise CaseResourceKeyGrantError("case_key_epoch_mismatch")
            if pending is None:
                state["data_key_id"] = old_key_id
                state["pending_revoke"] = {"operation_id": operation_id, "identity": operation_identity,
                                           "grants": [_grant_document(grant) for grant in grants]}
                # A crash from this point fences delegated access. Cold retry
                # uses the same authenticated snapshots and keystore operation.
                self._write_generation(state)
            rotation = owner_session.rotate_case_grant_data_key(case.tenant_id, case.case_id,
                resource_id=case.resource_id, expected_data_key_id=old_key_id, operation_id=operation_id)
            new_key_id = str(rotation["new_data_key_id"])
            if new_key_id == old_key_id or rotation.get("old_data_key_id") != old_key_id:
                raise CaseResourceKeyGrantError("case_key_epoch_mismatch")
            rewrapped = []
            for grant in survivors:
                wrap_id, wrap_key = sessions[grant.recipient_principal_id].recipient_wrap_key()
                wrapped = owner_session.wrap_case_key_for_recipient(tenant_id=case.tenant_id,
                    case_id=case.case_id, recipient_wrap_key=wrap_key, recipient_wrap_key_id=wrap_id,
                    canonical_principal_id=case.tenant_id, revision=grant.artifact_revision,
                    recipient_principal_id=grant.recipient_principal_id, artifact_kind=grant.artifact_kind,
                    resource_id=case.resource_id, membership_grant_id=grant.membership_grant_id,
                    membership_version=grant.membership_version)
                if str(wrapped["data_key_id"]) != new_key_id:
                    raise CaseResourceKeyGrantError("case_key_epoch_mismatch")
                rewrapped.append(replace(grant, version=grant.version + 1, generation=cutoff + 1,
                    status="active", data_key_id=new_key_id, wrapped_nonce=str(wrapped["nonce"]),
                    wrapped_ciphertext=str(wrapped["ciphertext"]),
                    historical_wrapped_keys=grant.historical_wrapped_keys + (
                        (grant.data_key_id, grant.wrapped_nonce, grant.wrapped_ciphertext),)))
            for grant in targets:
                self._seal(replace(grant, version=grant.version + 1, status="revoked",
                                   wrapped_nonce="", wrapped_ciphertext="", historical_wrapped_keys=()))
            for grant in rewrapped:
                self._seal(grant)
            summary = {"schema_version": SCHEMA_VERSION, "operation": "revoke_and_rewrap",
                **{k: v for k, v in operation_identity.items() if k != "idempotency_sha256"},
                "generation": cutoff + 1, "revoked_key_grant_ids": [g.key_grant_id for g in targets],
                "rewrapped_key_grant_ids": [g.key_grant_id for g in rewrapped],
                "previous_data_key_id": old_key_id, "data_key_id": new_key_id,
                "data_key_rotated": True, "grant_wrap_rotated": True, "future_access_revoked": True,
                "downloaded_plaintext_erased": False, "downloaded_keys_erased": False,
                "limitation": LIMITATIONS[0]}
            # Publish the complete cutoff in one authenticated atomic record.
            # Its embedded receipt covers the gap before the replay sidecar.
            self._write_generation({"schema_version": SCHEMA_VERSION, "tenant_id": case.tenant_id,
                "case_id": case.case_id, "resource_id": case.resource_id, "generation": cutoff + 1,
                "cutoff": cutoff, "data_key_id": new_key_id,
                "last_revoke": {"operation_id": operation_id, "summary": summary}})
            self._write_revoke_replay(key_name, summary)
            return _revoke_view(summary, retained_plaintext, retained_key)

    def decrypt_with_admin_master(self, *_args: Any, **_kwargs: Any) -> bytes:
        """Operational admins have no master decrypt path."""

        raise CaseResourceKeyGrantError("admin_cannot_decrypt")

    def read_as_owner(
        self,
        *,
        actor_principal_id: str,
        case_id: str,
        tenant_id: str,
        resource_id: str,
        artifact_kind: str,
        artifact_revision: str,
        envelope: bytes,
        owner_session: UserOwnedKeySession,
        aad_principal_id: str | None = None,
    ) -> dict[str, Any]:
        """Open as the case owner without putting the actor into associated data."""

        actor = self._active(actor_principal_id)
        self._reject_admin(actor)
        if not isinstance(owner_session, UserOwnedKeySession):
            raise CaseResourceKeyGrantError("key_owner_required")
        case = self._select(actor.principal_id, case_id)
        if case.owner_principal_id != actor.principal_id:
            raise CaseResourceKeyGrantError("actor_not_owner")
        if tenant_id != case.tenant_id or resource_id != case.resource_id:
            raise CaseResourceKeyGrantError("tenant_mismatch" if tenant_id != case.tenant_id else "resource_mismatch")
        claimed = case.tenant_id if aad_principal_id is None else aad_principal_id
        if claimed != case.tenant_id:
            raise CaseResourceKeyGrantError("owner_impersonation")
        kind = _label(artifact_kind, "artifact_kind")
        revision = _label(artifact_revision, "artifact_revision")
        binding = PrivateArtifactBinding(
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            artifact_kind=kind,
            revision=revision,
            principal_id=case.tenant_id,
        )
        access = _CanonicalAccess("authenticated", case.tenant_id, case.case_id)
        assert_access_matches_binding(access, binding)
        key_id = _artifact_key_id(envelope)
        key = owner_session.lookup_data_key(case.tenant_id, case.case_id, key_id)
        if key is None:
            raise CaseResourceKeyGrantError("key_unavailable")
        try:
            plaintext = open_private_artifact(envelope, binding=binding, key=key, expected_key_id=key_id)
        except PrivateArtifactIntegrityError as exc:
            raise CaseResourceKeyGrantError(exc.reason) from exc
        finally:
            _zero(key)
        return self._receipt(
            actor_principal_id=actor.principal_id,
            canonical_owner_principal_id=case.tenant_id,
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            artifact_kind=kind,
            artifact_revision=revision,
            plaintext=plaintext,
            key_grant_id=None,
            membership="owner",
        )

    def read_delegated(
        self,
        *,
        actor_principal_id: str,
        membership_grant_id: str,
        membership_version: int,
        key_grant_id: str,
        case_id: str,
        tenant_id: str,
        resource_id: str,
        artifact_kind: str,
        artifact_revision: str,
        envelope: bytes,
        recipient_session: UserOwnedKeySession,
        aad_principal_id: str | None = None,
    ) -> dict[str, Any]:
        """Open only with verified membership and this recipient's key grant."""

        actor = self._active(actor_principal_id)
        self._reject_admin(actor)
        if not isinstance(recipient_session, UserOwnedKeySession):
            raise CaseResourceKeyGrantError("key_owner_required")
        if actor.principal_id == tenant_id:
            raise CaseResourceKeyGrantError("owner_impersonation")
        decision = self._require_membership(
            actor_principal_id=actor.principal_id,
            grant_id=membership_grant_id,
            tenant_id=tenant_id,
            case_id=case_id,
            resource_id=resource_id,
            expected_version=membership_version,
        )
        if decision.actor_is_encrypted_owner or decision.canonical_owner_principal_id == actor.principal_id:
            raise CaseResourceKeyGrantError("owner_impersonation")
        if decision.canonical_owner_principal_id != decision.tenant_id:
            raise CaseResourceKeyGrantError("canonical_owner_mismatch")
        claimed = decision.tenant_id if aad_principal_id is None else aad_principal_id
        if claimed != decision.tenant_id or claimed == actor.principal_id:
            raise CaseResourceKeyGrantError("owner_impersonation")
        with self._locked():
            grant = self._load(_label(key_grant_id, "key_grant_id"))
        if grant.recipient_principal_id != actor.principal_id:
            raise CaseResourceKeyGrantError("actor_not_recipient")
        if grant.membership_grant_id != decision.grant_id or grant.membership_version != decision.version:
            raise CaseResourceKeyGrantError("membership_required")
        if grant.tenant_id != decision.tenant_id or grant.case_id != decision.case_id:
            raise CaseResourceKeyGrantError("case_mismatch")
        if grant.resource_id != decision.resource_id:
            raise CaseResourceKeyGrantError("resource_mismatch")
        if grant.canonical_owner_principal_id != decision.canonical_owner_principal_id:
            raise CaseResourceKeyGrantError("canonical_owner_mismatch")
        kind = _label(artifact_kind, "artifact_kind")
        revision = _label(artifact_revision, "artifact_revision")
        if grant.artifact_kind != kind or grant.artifact_revision != revision:
            raise CaseResourceKeyGrantError("revision_mismatch")
        self._require_grant_owner(grant)
        self._reject_inactive_grant(grant)
        key_id = _artifact_key_id(envelope)
        wrapped = self._wrapped_key(grant, key_id)
        try:
            data_key = recipient_session.unwrap_granted_resource_key(
                wrapped,
                tenant_id=grant.tenant_id,
                case_id=grant.case_id,
                canonical_principal_id=grant.canonical_owner_principal_id,
                revision=grant.artifact_revision,
                recipient_principal_id=grant.recipient_principal_id,
                artifact_kind=grant.artifact_kind,
                resource_id=grant.resource_id,
                membership_grant_id=grant.membership_grant_id,
                membership_version=grant.membership_version,
                data_key_id=key_id,
                recipient_wrap_key_id=grant.recipient_wrap_key_id,
            )
        except (PrivateArtifactIntegrityError, PrivateKeyMaterialError) as exc:
            raise CaseResourceKeyGrantError("key_grant_rejected") from exc
        binding = PrivateArtifactBinding(
            tenant_id=grant.tenant_id,
            case_id=grant.case_id,
            artifact_kind=kind,
            revision=revision,
            principal_id=grant.canonical_owner_principal_id,
        )
        access = _CanonicalAccess("authenticated", grant.canonical_owner_principal_id, grant.case_id)
        assert_access_matches_binding(access, binding)
        try:
            plaintext = open_private_artifact(
                envelope,
                binding=binding,
                key=data_key,
                expected_key_id=key_id,
            )
        except PrivateArtifactIntegrityError as exc:
            raise CaseResourceKeyGrantError(exc.reason) from exc
        finally:
            _zero(data_key)
        receipt = self._receipt(
            actor_principal_id=actor.principal_id,
            canonical_owner_principal_id=grant.canonical_owner_principal_id,
            tenant_id=grant.tenant_id,
            case_id=grant.case_id,
            resource_id=grant.resource_id,
            artifact_kind=kind,
            artifact_revision=revision,
            plaintext=plaintext,
            key_grant_id=grant.key_grant_id,
            membership=decision.grant_id,
            operation="read",
        )
        receipt["generation"] = grant.generation
        return self._admit_result(grant, decision, action=READ_ACTION, receipt=receipt)

    def write_delegated(
        self,
        *,
        actor_principal_id: str,
        membership_grant_id: str,
        membership_version: int,
        key_grant_id: str,
        case_id: str,
        tenant_id: str,
        resource_id: str,
        artifact_kind: str,
        artifact_revision: str,
        plaintext: bytes,
        recipient_session: UserOwnedKeySession,
    ) -> dict[str, Any]:
        """Seal a collaborative write only while the grant generation is still active."""

        if not isinstance(plaintext, (bytes, bytearray)) or isinstance(plaintext, memoryview):
            raise CaseResourceKeyGrantError("plaintext_required")
        grant, decision, data_key = self._authorize_delegated(
            actor_principal_id=actor_principal_id,
            membership_grant_id=membership_grant_id,
            membership_version=membership_version,
            key_grant_id=key_grant_id,
            case_id=case_id,
            tenant_id=tenant_id,
            resource_id=resource_id,
            artifact_kind=artifact_kind,
            artifact_revision=artifact_revision,
            recipient_session=recipient_session,
            action=WRITE_ACTION,
        )
        binding = PrivateArtifactBinding(
            tenant_id=grant.tenant_id,
            case_id=grant.case_id,
            artifact_kind=grant.artifact_kind,
            revision=grant.artifact_revision,
            principal_id=grant.canonical_owner_principal_id,
        )
        try:
            envelope = seal_private_artifact(
                bytes(plaintext),
                binding=binding,
                key=data_key,
                key_id=grant.data_key_id,
            )
        finally:
            _zero(data_key)
        receipt = self._receipt(
            actor_principal_id=actor_principal_id,
            canonical_owner_principal_id=grant.canonical_owner_principal_id,
            tenant_id=grant.tenant_id,
            case_id=grant.case_id,
            resource_id=grant.resource_id,
            artifact_kind=grant.artifact_kind,
            artifact_revision=grant.artifact_revision,
            plaintext=b"",
            key_grant_id=grant.key_grant_id,
            membership=decision.grant_id,
            operation="write",
        )
        receipt["data"] = None
        receipt["envelope"] = envelope
        receipt["generation"] = grant.generation
        return self._admit_result(grant, decision, action=WRITE_ACTION, receipt=receipt)

    def download_delegated(
        self,
        *,
        actor_principal_id: str,
        membership_grant_id: str,
        membership_version: int,
        key_grant_id: str,
        case_id: str,
        tenant_id: str,
        resource_id: str,
        artifact_kind: str,
        artifact_revision: str,
        envelope: bytes,
        recipient_session: UserOwnedKeySession,
    ) -> dict[str, Any]:
        """Download plaintext only after a fresh grant check. The bytes stay with the caller."""

        opened = self._open_delegated(
            actor_principal_id=actor_principal_id,
            membership_grant_id=membership_grant_id,
            membership_version=membership_version,
            key_grant_id=key_grant_id,
            case_id=case_id,
            tenant_id=tenant_id,
            resource_id=resource_id,
            artifact_kind=artifact_kind,
            artifact_revision=artifact_revision,
            envelope=envelope,
            recipient_session=recipient_session,
            action=DOWNLOAD_ACTION,
            operation="download",
        )
        opened["downloaded_plaintext_erased"] = False
        opened["downloaded_keys_erased"] = False
        return opened

    def admit_late_result(
        self,
        *,
        actor_principal_id: str,
        membership_grant_id: str,
        membership_version: int,
        key_grant_id: str,
        case_id: str,
        tenant_id: str,
        resource_id: str,
        artifact_kind: str,
        artifact_revision: str,
        prepared_generation: int,
        envelope: bytes,
        recipient_session: UserOwnedKeySession,
        action: str = READ_ACTION,
    ) -> dict[str, Any]:
        """Admit a prepared result only when its generation is still above the cutoff."""

        if type(prepared_generation) is not int or prepared_generation < 1:
            raise CaseResourceKeyGrantError("cutoff_invalid")
        if action not in {READ_ACTION, WRITE_ACTION, DOWNLOAD_ACTION}:
            raise CaseResourceKeyGrantError("action_not_permitted")
        tenant = _label(tenant_id, "tenant_id")
        case = _label(case_id, "case_id")
        with self._locked():
            state = self._read_generation(tenant, case)
        if prepared_generation <= int(state["cutoff"]):
            raise CaseResourceKeyGrantError("late_result_after_cutoff")
        opened = self._open_delegated(
            actor_principal_id=actor_principal_id,
            membership_grant_id=membership_grant_id,
            membership_version=membership_version,
            key_grant_id=key_grant_id,
            case_id=case_id,
            tenant_id=tenant_id,
            resource_id=resource_id,
            artifact_kind=artifact_kind,
            artifact_revision=artifact_revision,
            envelope=envelope,
            recipient_session=recipient_session,
            action=action,
            operation="late_result",
            prepared_generation=prepared_generation,
        )
        if int(opened["generation"]) != prepared_generation:
            raise CaseResourceKeyGrantError("stale_session")
        opened["prepared_generation"] = prepared_generation
        return opened

    def load(self, key_grant_id: str) -> ResourceKeyGrant:
        with self._locked():
            grant = self._load(_label(key_grant_id, "key_grant_id"))
            self._read_generation(grant.tenant_id, grant.case_id)
            return grant

    def _open_delegated(
        self,
        *,
        actor_principal_id: str,
        membership_grant_id: str,
        membership_version: int,
        key_grant_id: str,
        case_id: str,
        tenant_id: str,
        resource_id: str,
        artifact_kind: str,
        artifact_revision: str,
        envelope: bytes,
        recipient_session: UserOwnedKeySession,
        action: str,
        operation: str,
        prepared_generation: int | None = None,
    ) -> dict[str, Any]:
        key_id = _artifact_key_id(envelope)
        grant, decision, data_key = self._authorize_delegated(
            actor_principal_id=actor_principal_id,
            membership_grant_id=membership_grant_id,
            membership_version=membership_version,
            key_grant_id=key_grant_id,
            case_id=case_id,
            tenant_id=tenant_id,
            resource_id=resource_id,
            artifact_kind=artifact_kind,
            artifact_revision=artifact_revision,
            recipient_session=recipient_session,
            action=action,
            artifact_key_id=key_id,
        )
        binding = PrivateArtifactBinding(
            tenant_id=grant.tenant_id,
            case_id=grant.case_id,
            artifact_kind=grant.artifact_kind,
            revision=grant.artifact_revision,
            principal_id=grant.canonical_owner_principal_id,
        )
        try:
            plaintext = open_private_artifact(
                envelope,
                binding=binding,
                key=data_key,
                expected_key_id=key_id,
            )
        except PrivateArtifactIntegrityError as exc:
            raise CaseResourceKeyGrantError(exc.reason) from exc
        finally:
            _zero(data_key)
        receipt = self._receipt(
            actor_principal_id=actor_principal_id,
            canonical_owner_principal_id=grant.canonical_owner_principal_id,
            tenant_id=grant.tenant_id,
            case_id=grant.case_id,
            resource_id=grant.resource_id,
            artifact_kind=grant.artifact_kind,
            artifact_revision=grant.artifact_revision,
            plaintext=plaintext,
            key_grant_id=grant.key_grant_id,
            membership=decision.grant_id,
            operation=operation,
        )
        receipt["generation"] = grant.generation
        return self._admit_result(grant, decision, action=action, receipt=receipt,
                                  prepared_generation=prepared_generation)

    def _authorize_delegated(
        self,
        *,
        actor_principal_id: str,
        membership_grant_id: str,
        membership_version: int,
        key_grant_id: str,
        case_id: str,
        tenant_id: str,
        resource_id: str,
        artifact_kind: str,
        artifact_revision: str,
        recipient_session: UserOwnedKeySession,
        action: str,
        artifact_key_id: str | None = None,
    ):
        actor = self._active(actor_principal_id)
        self._reject_admin(actor)
        if not isinstance(recipient_session, UserOwnedKeySession):
            raise CaseResourceKeyGrantError("key_owner_required")
        if actor.principal_id == tenant_id:
            raise CaseResourceKeyGrantError("owner_impersonation")
        decision = self._require_membership(
            actor_principal_id=actor.principal_id,
            grant_id=membership_grant_id,
            tenant_id=tenant_id,
            case_id=case_id,
            resource_id=resource_id,
            expected_version=membership_version,
            action=action,
        )
        if decision.actor_is_encrypted_owner or decision.canonical_owner_principal_id == actor.principal_id:
            raise CaseResourceKeyGrantError("owner_impersonation")
        if decision.canonical_owner_principal_id != decision.tenant_id:
            raise CaseResourceKeyGrantError("canonical_owner_mismatch")
        with self._locked():
            grant = self._load(_label(key_grant_id, "key_grant_id"))
            state = self._read_generation(grant.tenant_id, grant.case_id)
        self._reject_inactive_grant(grant, cutoff=int(state["cutoff"]), generation=int(state["generation"]))
        if grant.recipient_principal_id != actor.principal_id:
            raise CaseResourceKeyGrantError("actor_not_recipient")
        if grant.membership_grant_id != decision.grant_id or grant.membership_version != decision.version:
            raise CaseResourceKeyGrantError("membership_required")
        if grant.tenant_id != decision.tenant_id or grant.case_id != decision.case_id:
            raise CaseResourceKeyGrantError("case_mismatch")
        if grant.resource_id != decision.resource_id or grant.resource_id != resource_id:
            raise CaseResourceKeyGrantError("resource_mismatch")
        if grant.canonical_owner_principal_id != decision.canonical_owner_principal_id:
            raise CaseResourceKeyGrantError("canonical_owner_mismatch")
        kind = _label(artifact_kind, "artifact_kind")
        revision = _label(artifact_revision, "artifact_revision")
        if grant.artifact_kind != kind or grant.artifact_revision != revision:
            raise CaseResourceKeyGrantError("revision_mismatch")
        self._require_grant_owner(grant)
        key_id = grant.data_key_id if artifact_key_id is None else artifact_key_id
        wrapped = self._wrapped_key(grant, key_id)
        try:
            data_key = recipient_session.unwrap_granted_resource_key(
                wrapped,
                tenant_id=grant.tenant_id,
                case_id=grant.case_id,
                canonical_principal_id=grant.canonical_owner_principal_id,
                revision=grant.artifact_revision,
                recipient_principal_id=grant.recipient_principal_id,
                artifact_kind=grant.artifact_kind,
                resource_id=grant.resource_id,
                membership_grant_id=grant.membership_grant_id,
                membership_version=grant.membership_version,
                data_key_id=key_id,
                recipient_wrap_key_id=grant.recipient_wrap_key_id,
            )
        except (PrivateArtifactIntegrityError, PrivateKeyMaterialError) as exc:
            raise CaseResourceKeyGrantError("key_grant_rejected") from exc
        return grant, decision, data_key

    @staticmethod
    def _wrapped_key(grant: ResourceKeyGrant, key_id: str) -> dict[str, str]:
        if key_id == grant.data_key_id:
            return {"nonce": grant.wrapped_nonce, "ciphertext": grant.wrapped_ciphertext}
        for historical_id, nonce, ciphertext in grant.historical_wrapped_keys:
            if key_id == historical_id:
                return {"nonce": nonce, "ciphertext": ciphertext}
        raise CaseResourceKeyGrantError("key_grant_rejected")

    def _admit_result(self, grant: ResourceKeyGrant, decision: Any, *, action: str,
                      receipt: dict[str, Any], prepared_generation: int | None = None) -> dict[str, Any]:
        """Linearize emission against revocation, after crypto has completed.

        Plaintext already emitted before this cutoff cannot be recalled. A
        result still being prepared when revocation finishes must reauthorize.
        No caller-supplied receipt is accepted by a public access entry point.
        """
        with self._locked():
            state = self._read_generation(grant.tenant_id, grant.case_id)
            if prepared_generation is not None and prepared_generation <= int(state["cutoff"]):
                raise CaseResourceKeyGrantError("late_result_after_cutoff")
            current = self._load(grant.key_grant_id)
            self._reject_inactive_grant(current, cutoff=int(state["cutoff"]), generation=int(state["generation"]))
            if (current.version != grant.version or current.generation != grant.generation
                    or current.data_key_id != grant.data_key_id or _identity(current) != _identity(grant)):
                raise CaseResourceKeyGrantError("stale_grant_generation")
            expected_key_id = state.get("data_key_id")
            if expected_key_id and current.data_key_id != expected_key_id:
                raise CaseResourceKeyGrantError("case_key_epoch_mismatch")
            if prepared_generation is not None and prepared_generation != current.generation:
                raise CaseResourceKeyGrantError("stale_session")
            actor = self._active(grant.recipient_principal_id)
            self._reject_admin(actor)
            try:
                with self._memberships.authorization_scope(actor_principal_id=actor.principal_id,
                        grant_id=grant.membership_grant_id, tenant_id=grant.tenant_id,
                        case_id=grant.case_id, resource_id=grant.resource_id,
                        expected_version=grant.membership_version, action=action) as fresh:
                    if fresh.grant_id != decision.grant_id or fresh.version != decision.version:
                        raise CaseResourceKeyGrantError("membership_required")
                    return receipt
            except CaseMembershipError as exc:
                raise CaseResourceKeyGrantError(exc.code) from exc

    def _reject_inactive_grant(
        self,
        grant: ResourceKeyGrant,
        *,
        cutoff: int | None = None,
        generation: int | None = None,
    ) -> None:
        if cutoff is None or generation is None:
            with self._locked():
                state = self._read_generation(grant.tenant_id, grant.case_id)
            cutoff = int(state["cutoff"])
            generation = int(state["generation"])
        if grant.status != "active" or grant.wrapped_ciphertext == "" or grant.wrapped_nonce == "":
            raise CaseResourceKeyGrantError("grant_revoked")
        if grant.generation <= cutoff or grant.generation != generation:
            raise CaseResourceKeyGrantError("grant_revoked")

    def _generation_state(self, tenant_id: str, case_id: str, resource_id: str, *, allow_pending=False) -> dict[str, Any]:
        state = self._read_generation(tenant_id, case_id, allow_pending=allow_pending)
        if state.get("resource_id") not in {"", resource_id}:
            raise CaseResourceKeyGrantError("resource_mismatch")
        state["resource_id"] = resource_id
        state["tenant_id"] = tenant_id
        state["case_id"] = case_id
        return state

    def _read_generation(self, tenant_id: str, case_id: str, *, allow_pending=False) -> dict[str, Any]:
        digest = hashlib.sha256(f"{tenant_id}\n{case_id}".encode("utf-8")).hexdigest()
        directory = self._root / "generations"
        record = directory / f"{digest}.record"
        try:
            descriptor = os.open(record, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except FileNotFoundError:
            descriptor = None
        except OSError as exc:
            raise CaseResourceKeyGrantError("integrity") from exc
        if descriptor is not None:
            try:
                before = os.fstat(descriptor)
                if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                        or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != 0o600
                        or not 0 < before.st_size <= 8 * 1024 * 1024):
                    raise CaseResourceKeyGrantError("integrity")
                raw = os.read(descriptor, before.st_size + 1)
                after = os.fstat(descriptor)
                identity = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
                if len(raw) != before.st_size or identity(before) != identity(after):
                    raise CaseResourceKeyGrantError("integrity")
            finally:
                os.close(descriptor)
            try:
                wrapper = json.loads(raw)
                if (not isinstance(wrapper, dict) or set(wrapper) != {"revision", "envelope"}
                        or type(wrapper["revision"]) is not int or wrapper["revision"] < 1
                        or not isinstance(wrapper["envelope"], str)):
                    raise ValueError("record")
                revision = wrapper["revision"]
                envelope = base64.b64decode(wrapper["envelope"], validate=True)
            except (ValueError, TypeError, KeyError) as exc:
                raise CaseResourceKeyGrantError("integrity") from exc
        else:
            # Read the original committed format without silently replacing it.
            path = directory / f"{digest}.envelope"
            if not path.is_file():
                return {"schema_version": SCHEMA_VERSION, "tenant_id": tenant_id,
                    "case_id": case_id, "resource_id": "", "generation": 1, "cutoff": 0}
            revision_text = (directory / f"{digest}.revision").read_text(encoding="utf-8").strip()
            if not revision_text.isdigit():
                raise CaseResourceKeyGrantError("revision_pointer")
            revision, envelope = int(revision_text), path.read_bytes()
        binding = PrivateArtifactBinding(tenant_id=tenant_id, case_id=case_id,
            artifact_kind=GENERATION_KIND, revision=str(revision), principal_id=tenant_id)
        assert_access_matches_binding(_CanonicalAccess("authenticated", tenant_id, case_id), binding)
        try:
            document = json.loads(open_private_artifact(envelope, binding=binding,
                key=self._key, expected_key_id=self._key_id).decode("utf-8"))
        except (PrivateArtifactIntegrityError, ValueError, UnicodeDecodeError) as exc:
            raise CaseResourceKeyGrantError("integrity") from exc
        if (not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION
                or document.get("tenant_id") != tenant_id or document.get("case_id") != case_id
                or type(document.get("generation")) is not int or document["generation"] != revision
                or type(document.get("cutoff")) is not int or not 0 <= document["cutoff"] < revision):
            raise CaseResourceKeyGrantError("binding_mismatch")
        if document.get("pending_revoke") is not None and not allow_pending:
            raise CaseResourceKeyGrantError("case_key_rotation_incomplete")
        if (not allow_pending and revision > 1
                and (not isinstance(document.get("data_key_id"), str) or not document["data_key_id"])):
            raise CaseResourceKeyGrantError("case_key_epoch_unavailable")
        return document

    def _write_generation(self, state: Mapping[str, Any]) -> None:
        generation = int(state["generation"])
        binding = PrivateArtifactBinding(tenant_id=str(state["tenant_id"]), case_id=str(state["case_id"]),
            artifact_kind=GENERATION_KIND, revision=str(generation), principal_id=str(state["tenant_id"]))
        assert_access_matches_binding(_CanonicalAccess("authenticated", binding.tenant_id, binding.case_id), binding)
        payload = json.dumps(dict(state), sort_keys=True, separators=(",", ":")).encode("utf-8")
        envelope = seal_private_artifact(payload, binding=binding, key=self._key, key_id=self._key_id)
        raw = json.dumps({"revision": generation, "envelope": base64.b64encode(envelope).decode("ascii")},
                         sort_keys=True, separators=(",", ":")).encode()
        if len(raw) > 8 * 1024 * 1024:
            raise CaseResourceKeyGrantError("generation_size_limit")
        digest = hashlib.sha256(f"{binding.tenant_id}\n{binding.case_id}".encode("utf-8")).hexdigest()
        directory = self._root / "generations"
        path = directory / f"{digest}.record"
        temporary = directory / (".generation-" + uuid.uuid4().hex + ".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            try:
                remaining = memoryview(raw)
                while remaining:
                    written = os.write(descriptor, remaining)
                    if written <= 0:
                        raise OSError("generation_write_failed")
                    remaining = remaining[written:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.replace(temporary, path)
            parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _grants_for_case(self, tenant_id: str, case_id: str) -> list[ResourceKeyGrant]:
        found: list[ResourceKeyGrant] = []
        directory = self._root / "grants"
        for path in sorted(directory.glob("*.envelope")):
            if path.is_symlink():
                raise CaseResourceKeyGrantError("key_grant_required")
            grant = self._load(path.name[: -len(".envelope")])
            if grant.tenant_id == tenant_id and grant.case_id == case_id:
                found.append(grant)
        return found

    def _revoke_replay(self, key: str) -> dict[str, Any] | None:
        path = self._root / "revoke-idem" / hashlib.sha256(key.encode("utf-8")).hexdigest()
        if not path.is_file():
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise CaseResourceKeyGrantError("replay_mismatch")
        return document

    def _write_revoke_replay(self, key: str, summary: Mapping[str, Any]) -> None:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        self._write_text(self._root / "revoke-idem" / digest, json.dumps(dict(summary), sort_keys=True))

    def _require_membership(
        self,
        *,
        actor_principal_id: str,
        grant_id: str,
        tenant_id: str,
        case_id: str,
        resource_id: str,
        expected_version: int,
        action: str = READ_ACTION,
    ):
        try:
            return self._memberships.authorize(
                actor_principal_id=actor_principal_id,
                grant_id=grant_id,
                tenant_id=tenant_id,
                case_id=case_id,
                resource_id=resource_id,
                action=action,
                expected_version=expected_version,
            )
        except CaseMembershipError as exc:
            raise CaseResourceKeyGrantError(exc.code) from exc

    def _require_grant_owner(self, grant: ResourceKeyGrant) -> None:
        case = self._select(grant.owner_principal_id, grant.case_id)
        if (case.owner_principal_id != grant.owner_principal_id
                or case.tenant_id != grant.tenant_id
                or case.resource_id != grant.resource_id
                or case.tenant_id != grant.canonical_owner_principal_id):
            raise CaseResourceKeyGrantError("owner_impersonation")


    def _receipt(
        self,
        *,
        actor_principal_id: str,
        canonical_owner_principal_id: str,
        tenant_id: str,
        case_id: str,
        resource_id: str,
        artifact_kind: str,
        artifact_revision: str,
        plaintext: bytes,
        key_grant_id: str | None,
        membership: str,
        operation: str = "read",
    ) -> dict[str, Any]:
        actor_is_encrypted_owner = actor_principal_id == canonical_owner_principal_id
        if actor_is_encrypted_owner:
            if membership != "owner" or key_grant_id is not None:
                raise CaseResourceKeyGrantError("owner_impersonation")
            case = self._select(actor_principal_id, case_id)
            if (case.owner_principal_id != actor_principal_id or case.tenant_id != tenant_id
                    or canonical_owner_principal_id != case.tenant_id or case.resource_id != resource_id):
                raise CaseResourceKeyGrantError("owner_impersonation")
        return {
            "actor_principal_id": actor_principal_id,
            "canonical_owner_principal_id": canonical_owner_principal_id,
            "actor_is_encrypted_owner": actor_is_encrypted_owner,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "resource_id": resource_id,
            "artifact_kind": artifact_kind,
            "artifact_revision": artifact_revision,
            "schema_version": SCHEMA_VERSION,
            "envelope_schema_version": 2,
            "data": plaintext,
            "key_grant_id": key_grant_id,
            "membership": membership,
            "operation": operation,
            "limitations": list(LIMITATIONS),
        }

    def _reject_admin(self, principal: Any) -> None:
        if "operational_admin" in tuple(getattr(principal, "roles", ())):
            raise CaseResourceKeyGrantError("admin_cannot_decrypt")

    def _select(self, actor_id: str, case_id: str):
        try:
            return self._cases.select_case(actor_principal_id=actor_id, case_id=case_id)
        except CaseDirectoryError as exc:
            raise CaseResourceKeyGrantError(exc.code) from exc

    def _active(self, principal_id: str):
        try:
            record = self._principals.load(principal_id)
        except PrincipalStoreError as exc:
            raise CaseResourceKeyGrantError("missing_principal") from exc
        if record.status != "active":
            raise CaseResourceKeyGrantError("inactive_principal")
        return record

    def _load(self, key_grant_id: str) -> ResourceKeyGrant:
        path = self._root / "grants" / f"{key_grant_id}.envelope"
        if not path.is_file() or path.is_symlink():
            raise CaseResourceKeyGrantError("key_grant_required")
        pointer = self._root / "grants" / f"{key_grant_id}.revision"
        tenant_path = self._root / "grants" / f"{key_grant_id}.tenant"
        case_path = self._root / "grants" / f"{key_grant_id}.case"
        if not pointer.is_file() or not tenant_path.is_file() or not case_path.is_file():
            raise CaseResourceKeyGrantError("missing_revision")
        revision_text = pointer.read_text(encoding="utf-8").strip()
        if not revision_text.isdigit():
            raise CaseResourceKeyGrantError("revision_pointer")
        revision = int(revision_text)
        tenant_id = tenant_path.read_text(encoding="utf-8").strip()
        case_id = case_path.read_text(encoding="utf-8").strip()
        binding = PrivateArtifactBinding(
            tenant_id=tenant_id,
            case_id=case_id,
            artifact_kind=ARTIFACT_KIND,
            revision=str(revision),
            principal_id=tenant_id,
        )
        access = _CanonicalAccess("authenticated", tenant_id, case_id)
        assert_access_matches_binding(access, binding)
        try:
            plaintext = open_private_artifact(
                path.read_bytes(),
                binding=binding,
                key=self._key,
                expected_key_id=self._key_id,
            )
        except PrivateArtifactIntegrityError as exc:
            raise CaseResourceKeyGrantError("integrity") from exc
        document = json.loads(plaintext.decode("utf-8"))
        grant = _grant_from_document(document)
        if grant.key_grant_id != key_grant_id or grant.tenant_id != tenant_id or grant.case_id != case_id:
            raise CaseResourceKeyGrantError("binding_mismatch")
        if grant.version != revision:
            raise CaseResourceKeyGrantError("revision_mismatch")
        if grant.canonical_owner_principal_id != tenant_id:
            raise CaseResourceKeyGrantError("canonical_owner_mismatch")
        return grant

    def _seal(self, grant: ResourceKeyGrant) -> None:
        binding = PrivateArtifactBinding(
            tenant_id=grant.tenant_id,
            case_id=grant.case_id,
            artifact_kind=ARTIFACT_KIND,
            revision=str(grant.version),
            principal_id=grant.tenant_id,
        )
        access = _CanonicalAccess("authenticated", grant.tenant_id, grant.case_id)
        assert_access_matches_binding(access, binding)
        payload = json.dumps(_grant_document(grant), sort_keys=True, separators=(",", ":")).encode("utf-8")
        envelope = seal_private_artifact(payload, binding=binding, key=self._key, key_id=self._key_id)
        directory = self._root / "grants"
        path = directory / f"{grant.key_grant_id}.envelope"
        temporary = directory / f"{grant.key_grant_id}.envelope.tmp"
        temporary.write_bytes(envelope)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        self._write_text(directory / f"{grant.key_grant_id}.revision", str(grant.version))
        self._write_text(directory / f"{grant.key_grant_id}.tenant", grant.tenant_id)
        self._write_text(directory / f"{grant.key_grant_id}.case", grant.case_id)

    def _idem_grant(self, key: str) -> str | None:
        path = self._idem_path(key)
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8").strip() or None

    def _write_idem(self, key: str, key_grant_id: str) -> None:
        self._write_text(self._idem_path(key), key_grant_id)

    def _idem_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._root / "idem" / digest

    def _write_text(self, path: Path, text: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)

    def _locked(self):
        return _FileLock(self._lock_path)


def _grant_document(grant: ResourceKeyGrant) -> dict[str, Any]:
    return {
        "key_grant_id": grant.key_grant_id,
        "version": grant.version,
        "membership_grant_id": grant.membership_grant_id,
        "membership_version": grant.membership_version,
        "owner_principal_id": grant.owner_principal_id,
        "recipient_principal_id": grant.recipient_principal_id,
        "tenant_id": grant.tenant_id,
        "case_id": grant.case_id,
        "resource_id": grant.resource_id,
        "canonical_owner_principal_id": grant.canonical_owner_principal_id,
        "artifact_kind": grant.artifact_kind,
        "artifact_revision": grant.artifact_revision,
        "data_key_id": grant.data_key_id,
        "recipient_wrap_key_id": grant.recipient_wrap_key_id,
        "wrapped_nonce": grant.wrapped_nonce,
        "wrapped_ciphertext": grant.wrapped_ciphertext,
        "idempotency_key": grant.idempotency_key,
        "status": grant.status,
        "generation": grant.generation,
        "historical_wrapped_keys": [list(entry) for entry in grant.historical_wrapped_keys],
        "schema_version": SCHEMA_VERSION,
    }


def _grant_from_document(document: Mapping[str, Any]) -> ResourceKeyGrant:
    if not isinstance(document, Mapping) or document.get("schema_version") != SCHEMA_VERSION:
        raise CaseResourceKeyGrantError("unsupported_version")
    try:
        return ResourceKeyGrant(
            key_grant_id=str(document["key_grant_id"]),
            version=int(document["version"]),
            membership_grant_id=str(document["membership_grant_id"]),
            membership_version=int(document["membership_version"]),
            owner_principal_id=str(document["owner_principal_id"]),
            recipient_principal_id=str(document["recipient_principal_id"]),
            tenant_id=str(document["tenant_id"]),
            case_id=str(document["case_id"]),
            resource_id=str(document["resource_id"]),
            canonical_owner_principal_id=str(document["canonical_owner_principal_id"]),
            artifact_kind=str(document["artifact_kind"]),
            artifact_revision=str(document["artifact_revision"]),
            data_key_id=str(document["data_key_id"]),
            recipient_wrap_key_id=str(document["recipient_wrap_key_id"]),
            wrapped_nonce=str(document["wrapped_nonce"]),
            wrapped_ciphertext=str(document["wrapped_ciphertext"]),
            idempotency_key=str(document["idempotency_key"]),
            status=str(document.get("status") or "active"),
            generation=int(document.get("generation") or 1),
            historical_wrapped_keys=_history_from_document(document),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CaseResourceKeyGrantError("integrity") from exc


def _history_from_document(document: Mapping[str, Any]) -> tuple[tuple[str, str, str], ...]:
    entries = document.get("historical_wrapped_keys", [])
    if not isinstance(entries, list) or any(not isinstance(entry, (list, tuple)) or len(entry) != 3
            or any(not isinstance(value, str) or not value for value in entry) for entry in entries):
        raise CaseResourceKeyGrantError("integrity")
    history = tuple(tuple(entry) for entry in entries)
    if len({entry[0] for entry in history}) != len(history):
        raise CaseResourceKeyGrantError("integrity")
    return history


def _revoke_view(
    summary: Mapping[str, Any],
    retained_plaintext: bytes | None,
    retained_key: bytes | None,
) -> dict[str, Any]:
    view = dict(summary)
    view["downloaded_plaintext_erased"] = False
    view["downloaded_keys_erased"] = False
    view["limitation"] = LIMITATIONS[0]
    if retained_plaintext is not None:
        if not isinstance(retained_plaintext, (bytes, bytearray)):
            raise CaseResourceKeyGrantError("plaintext_required")
        view["retained_plaintext_sha256"] = hashlib.sha256(bytes(retained_plaintext)).hexdigest()
        view["retained_plaintext_len"] = len(retained_plaintext)
    if retained_key is not None:
        if not isinstance(retained_key, (bytes, bytearray)):
            raise CaseResourceKeyGrantError("key_material")
        view["retained_key_sha256"] = hashlib.sha256(bytes(retained_key)).hexdigest()
        view["retained_key_len"] = len(retained_key)
    return view


def _zero(material: bytes) -> None:
    if isinstance(material, (bytes, bytearray)):
        buffer = bytearray(material)
        buffer[:] = b"\x00" * len(buffer)


class _FileLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._handle: Any = None

    def __enter__(self) -> _FileLock:
        self._handle = self._path.open("a+")
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None
