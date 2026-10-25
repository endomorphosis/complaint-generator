"""Append-only encrypted case audit history.

Each event records an action, the authenticated actor, the case resource,
the case revision, a grant reference, and a purpose reference. The canonical
encrypted owner remains the case tenant. The actor principal is stored
separately and is never written into artifact associated data as the owner.

Envelopes are sealed with the injected case-audit key. Replay of the same
idempotency key returns the original event and does not append. Operational
logs, in-app notifications, and error payloads carry only those references.
Complaint text and key material are rejected and are not copied into those
surfaces.

This store does not export audit bundles, does not rewrite history after
revocation, and does not erase plaintext a caller already holds.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from applications.case_access import OWNER_ACTIONS
from applications.case_directory import CaseDirectory, CaseDirectoryError, CaseNamespace
from applications.case_membership import CaseMembershipError, CaseMembershipStore
from applications.principal_store import PrincipalStore, PrincipalStoreError
from integrations.private_collaboration import CaseResourceKeyGrantError, CaseResourceKeyGrantStore
from integrations.private_storage import (
    PrivateArtifactBinding,
    PrivateArtifactBindingError,
    PrivateArtifactIntegrityError,
    assert_access_matches_binding,
    open_private_artifact,
    seal_private_artifact,
)

TASK_ID = "CIMP-GUI-13"
SCHEMA_VERSION = 1
ARTIFACT_KIND = "case-audit-event"
GRANT_KINDS = frozenset({"owner", "membership", "key"})
PURPOSE_RE = re.compile(r"purpose:[a-z0-9][a-z0-9._-]{0,63}\Z")
LIMITATIONS = (
    "history_is_append_only",
    "revocation_does_not_rewrite_recorded_events",
    "operational_surfaces_omit_complaint_text_and_key_material",
    "actor_is_distinct_from_canonical_encrypted_owner",
    "export_controls_are_not_this_store",
)
SENSITIVE_FIELDS = frozenset({
    "complaint",
    "complaint_text",
    "narrative",
    "evidence",
    "message",
    "messages",
    "plaintext",
    "body",
    "note",
    "notes",
    "summary",
    "key",
    "data_key",
    "wrap_key",
    "master_key",
    "private_key",
    "browser_key",
    "raw_key",
    "ciphertext",
    "wrapped_ciphertext",
    "nonce",
    "wrapped",
    "wrapped_data_key",
    "credentials",
    "credential",
    "password",
    "passphrase",
    "secret",
    "token",
    "trusted_local",
})
REQUEST_FIELDS = frozenset({
    "actor_principal_id",
    "case_id",
    "tenant_id",
    "resource_id",
    "action",
    "expected_revision",
    "grant_id",
    "grant_kind",
    "purpose_ref",
    "idempotency_key",
    "membership_version",
})


class CaseAuditError(Exception):
    """Fail-closed audit error. ``code`` is the only public message."""

    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


@dataclass(frozen=True)
class _CanonicalAccess:
    trust: str
    principal_id: str
    case_id: str


@dataclass(frozen=True)
class CaseAuditEvent:
    """One sealed history entry. Fields are references, not case content."""

    event_id: str
    sequence: int
    action: str
    actor_principal_id: str
    resource_id: str
    revision: int
    resource_revision: str
    grant_id: str
    grant_kind: str
    grant_version: int
    membership_version: int
    membership_grant_id: str
    purpose_ref: str
    tenant_id: str
    case_id: str
    canonical_owner_principal_id: str
    actor_is_encrypted_owner: bool
    previous_digest: str
    idempotency_key: str

    def public_view(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "sequence": self.sequence,
            "action": self.action,
            "actor_principal_id": self.actor_principal_id,
            "resource_id": self.resource_id,
            "revision": self.revision,
            "resource_revision": self.resource_revision,
            "grant_id": self.grant_id,
            "grant_kind": self.grant_kind,
            "grant_version": self.grant_version,
            "membership_version": self.membership_version,
            "membership_grant_id": self.membership_grant_id,
            "purpose_ref": self.purpose_ref,
            "tenant_id": self.tenant_id,
            "case_id": self.case_id,
            "canonical_owner_principal_id": self.canonical_owner_principal_id,
            "actor_is_encrypted_owner": self.actor_is_encrypted_owner,
            "schema_version": SCHEMA_VERSION,
            "limitations": list(LIMITATIONS),
        }


def owner_grant_reference(tenant_id: str) -> str:
    """Stable grant reference for the canonical owner binding, not the actor."""

    return "owner-binding:" + _label(tenant_id, "tenant_id")


def operational_log(event: CaseAuditEvent) -> dict[str, Any]:
    """Log record without complaint text or key material."""

    if not isinstance(event, CaseAuditEvent):
        raise CaseAuditError("audit_event")
    return {
        "record": "case_audit",
        "event_id": event.event_id,
        "sequence": event.sequence,
        "action": event.action,
        "actor_principal_id": event.actor_principal_id,
        "resource_id": event.resource_id,
        "revision": event.revision,
        "grant_id": event.grant_id,
        "grant_kind": event.grant_kind,
        "purpose_ref": event.purpose_ref,
    }


def notification_payload(event: CaseAuditEvent) -> dict[str, Any]:
    """In-app notification that names the audit references only."""

    if not isinstance(event, CaseAuditEvent):
        raise CaseAuditError("audit_event")
    return {
        "channel": "in_app",
        "template": "case_audit_recorded",
        "event_id": event.event_id,
        "action": event.action,
        "actor_principal_id": event.actor_principal_id,
        "resource_id": event.resource_id,
        "revision": event.revision,
        "grant_id": event.grant_id,
        "purpose_ref": event.purpose_ref,
    }


def error_payload(error: BaseException) -> dict[str, str]:
    """Machine reason only. Exception text is not copied."""

    if isinstance(error, CaseAuditError) and error.code.isidentifier():
        return {"code": error.code}
    return {"code": "audit_failed"}


def _opaque_id() -> str:
    return uuid.uuid4().hex


def _label(value: str, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise CaseAuditError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise CaseAuditError(code)
    if len(value) > 200:
        raise CaseAuditError(code)
    return value


def _same_request(
    event: CaseAuditEvent,
    *,
    actor_principal_id: str,
    case_id: str,
    tenant_id: str,
    resource_id: str,
    action: str,
    expected_revision: int,
    grant_id: str,
    grant_kind: str,
    purpose_ref: str,
    idempotency_key: str,
    membership_version: int | None,
) -> bool:
    if membership_version is None:
        version_ok = event.grant_kind == "owner" and event.membership_version == 0
    else:
        version_ok = event.membership_version == membership_version
    return (
        version_ok
        and event.actor_principal_id == actor_principal_id
        and event.case_id == case_id
        and event.tenant_id == tenant_id
        and event.resource_id == resource_id
        and event.action == action
        and event.revision == expected_revision
        and event.grant_id == grant_id
        and event.grant_kind == grant_kind
        and event.purpose_ref == purpose_ref
        and event.idempotency_key == idempotency_key
    )


def _fingerprint(event: CaseAuditEvent) -> str:
    payload = {
        "action": event.action,
        "actor_principal_id": event.actor_principal_id,
        "resource_id": event.resource_id,
        "revision": event.revision,
        "resource_revision": event.resource_revision,
        "grant_id": event.grant_id,
        "grant_kind": event.grant_kind,
        "grant_version": event.grant_version,
        "membership_version": event.membership_version,
        "membership_grant_id": event.membership_grant_id,
        "purpose_ref": event.purpose_ref,
        "tenant_id": event.tenant_id,
        "case_id": event.case_id,
        "idempotency_key": event.idempotency_key,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _document_digest(document: Mapping[str, Any]) -> str:
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CaseAuditStore:
    """File-backed append-only audit log for one injected data key."""

    def __init__(
        self,
        root: str | Path,
        *,
        key: bytes,
        key_id: str,
        principals: PrincipalStore,
        cases: CaseDirectory,
        memberships: CaseMembershipStore,
        key_grants: CaseResourceKeyGrantStore,
    ) -> None:
        if not isinstance(key, (bytes, bytearray)) or isinstance(key, memoryview) or len(bytes(key)) != 32:
            raise CaseAuditError("key_material")
        if not isinstance(principals, PrincipalStore) or not isinstance(cases, CaseDirectory):
            raise CaseAuditError("authority_owners")
        if not isinstance(memberships, CaseMembershipStore):
            raise CaseAuditError("membership_owner")
        if not isinstance(key_grants, CaseResourceKeyGrantStore):
            raise CaseAuditError("key_grant_owner")
        self._key = bytes(key)
        self._key_id = _label(key_id, "key_id")
        self._principals = principals
        self._cases = cases
        self._memberships = memberships
        self._key_grants = key_grants
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        os.chmod(self._root, 0o700)
        self._lock_path = self._root / ".lock"
        self._lock_path.touch(mode=0o600)
        (self._root / "events").mkdir(mode=0o700, exist_ok=True)
        (self._root / "idem").mkdir(mode=0o700, exist_ok=True)
        self._logs: list[dict[str, Any]] = []
        self._notifications: list[dict[str, Any]] = []
        self._errors: list[dict[str, str]] = []

    def record(
        self,
        *,
        actor_principal_id: str,
        case_id: str,
        tenant_id: str,
        resource_id: str,
        action: str,
        expected_revision: int,
        grant_id: str,
        grant_kind: str,
        purpose_ref: str,
        idempotency_key: str,
        membership_version: int | None = None,
    ) -> CaseAuditEvent:
        """Append one event, or return the original event when the key replays."""

        try:
            event = self._record(
                actor_principal_id=actor_principal_id,
                case_id=case_id,
                tenant_id=tenant_id,
                resource_id=resource_id,
                action=action,
                expected_revision=expected_revision,
                grant_id=grant_id,
                grant_kind=grant_kind,
                purpose_ref=purpose_ref,
                idempotency_key=idempotency_key,
                membership_version=membership_version,
            )
        except CaseAuditError as exc:
            self._errors.append(error_payload(exc))
            raise
        return event

    def record_from_request(self, body: Mapping[str, Any]) -> CaseAuditEvent:
        """Record from a mapping. Sensitive fields and unknown keys are refused."""

        try:
            if not isinstance(body, Mapping):
                raise CaseAuditError("request_body")
            self._reject_sensitive(body)
            unexpected = set(body) - REQUEST_FIELDS
            if unexpected:
                raise CaseAuditError("unknown_field")
            version = body.get("membership_version")
            if version is not None and type(version) is not int:
                raise CaseAuditError("grant_version")
            revision = body.get("expected_revision")
            if type(revision) is not int:
                raise CaseAuditError("revision_conflict")
        except CaseAuditError as exc:
            self._errors.append(error_payload(exc))
            raise
        return self.record(
            actor_principal_id=str(body.get("actor_principal_id") or ""),
            case_id=str(body.get("case_id") or ""),
            tenant_id=str(body.get("tenant_id") or ""),
            resource_id=str(body.get("resource_id") or ""),
            action=str(body.get("action") or ""),
            expected_revision=revision,
            grant_id=str(body.get("grant_id") or ""),
            grant_kind=str(body.get("grant_kind") or ""),
            purpose_ref=str(body.get("purpose_ref") or ""),
            idempotency_key=str(body.get("idempotency_key") or ""),
            membership_version=version,
        )

    def history(
        self,
        *,
        actor_principal_id: str,
        case_id: str,
        tenant_id: str,
        resource_id: str,
        grant_id: str,
        grant_kind: str,
        expected_revision: int,
        membership_version: int | None = None,
    ) -> tuple[CaseAuditEvent, ...]:
        """Read the chain. Authorization is checked before any event is returned."""

        try:
            actor = self._active(actor_principal_id)
            case_label = _label(case_id, "case_id")
            self._authorize_read(
                actor_id=actor.principal_id,
                case_id=case_label,
                tenant_id=_label(tenant_id, "tenant_id"),
                resource_id=_label(resource_id, "resource_id"),
                grant_id=_label(grant_id, "grant_id"),
                grant_kind=self._grant_kind(grant_kind),
                expected_revision=expected_revision,
                membership_version=membership_version,
            )
            with self._locked():
                return self._chain(case_label)
        except CaseAuditError as exc:
            self._errors.append(error_payload(exc))
            raise

    def operational_logs(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._logs)

    def notifications(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._notifications)

    def error_payloads(self) -> tuple[dict[str, str], ...]:
        return tuple(self._errors)

    def _record(
        self,
        *,
        actor_principal_id: str,
        case_id: str,
        tenant_id: str,
        resource_id: str,
        action: str,
        expected_revision: int,
        grant_id: str,
        grant_kind: str,
        purpose_ref: str,
        idempotency_key: str,
        membership_version: int | None,
    ) -> CaseAuditEvent:
        actor = self._active(actor_principal_id)
        kind = self._grant_kind(grant_kind)
        requested = _label(action, "action_not_permitted")
        purpose = self._purpose(purpose_ref)
        key_name = _label(idempotency_key, "idempotency_key")
        case_label = _label(case_id, "case_id")
        tenant_label = _label(tenant_id, "tenant_id")
        resource_label = _label(resource_id, "resource_id")
        grant_label = _label(grant_id, "grant_id")
        if type(expected_revision) is not int or expected_revision < 1:
            raise CaseAuditError("revision_conflict")
        with self._locked():
            prior = self._idem_pointer(key_name)
            if prior is not None:
                existing = self._load(prior["case_id"], prior["sequence"], prior["event_id"])
                if not _same_request(
                    existing,
                    actor_principal_id=actor.principal_id,
                    case_id=case_label,
                    tenant_id=tenant_label,
                    resource_id=resource_label,
                    action=requested,
                    expected_revision=expected_revision,
                    grant_id=grant_label,
                    grant_kind=kind,
                    purpose_ref=purpose,
                    idempotency_key=key_name,
                    membership_version=membership_version,
                ):
                    raise CaseAuditError("replay_mismatch")
                return existing
        bound = self._resolve_grant(
            actor_id=actor.principal_id,
            case_id=case_label,
            tenant_id=tenant_label,
            resource_id=resource_label,
            action=requested,
            expected_revision=expected_revision,
            grant_id=grant_label,
            grant_kind=kind,
            membership_version=membership_version,
            require_action=True,
        )
        draft = CaseAuditEvent(
            event_id="",
            sequence=0,
            action=requested,
            actor_principal_id=actor.principal_id,
            resource_id=bound["resource_id"],
            revision=bound["revision"],
            resource_revision=bound["resource_revision"],
            grant_id=bound["grant_id"],
            grant_kind=kind,
            grant_version=bound["grant_version"],
            membership_version=bound["membership_version"],
            membership_grant_id=bound["membership_grant_id"],
            purpose_ref=purpose,
            tenant_id=bound["tenant_id"],
            case_id=bound["case_id"],
            canonical_owner_principal_id=bound["canonical_owner_principal_id"],
            actor_is_encrypted_owner=False,
            previous_digest="",
            idempotency_key=key_name,
        )
        with self._locked():
            prior = self._idem_pointer(key_name)
            if prior is not None:
                existing = self._load(prior["case_id"], prior["sequence"], prior["event_id"])
                if not _same_request(
                    existing,
                    actor_principal_id=actor.principal_id,
                    case_id=case_label,
                    tenant_id=tenant_label,
                    resource_id=resource_label,
                    action=requested,
                    expected_revision=expected_revision,
                    grant_id=grant_label,
                    grant_kind=kind,
                    purpose_ref=purpose,
                    idempotency_key=key_name,
                    membership_version=membership_version,
                ):
                    raise CaseAuditError("replay_mismatch")
                return existing
            chain = self._chain(bound["case_id"])
            sequence = len(chain) + 1
            previous = "0" * 64 if not chain else _document_digest(_event_document(chain[-1]))
            event = CaseAuditEvent(
                event_id=_opaque_id(),
                sequence=sequence,
                action=draft.action,
                actor_principal_id=draft.actor_principal_id,
                resource_id=draft.resource_id,
                revision=draft.revision,
                resource_revision=draft.resource_revision,
                grant_id=draft.grant_id,
                grant_kind=draft.grant_kind,
                grant_version=draft.grant_version,
                membership_version=draft.membership_version,
                membership_grant_id=draft.membership_grant_id,
                purpose_ref=draft.purpose_ref,
                tenant_id=draft.tenant_id,
                case_id=draft.case_id,
                canonical_owner_principal_id=draft.canonical_owner_principal_id,
                actor_is_encrypted_owner=False,
                previous_digest=previous,
                idempotency_key=key_name,
            )
            if event.actor_principal_id == event.canonical_owner_principal_id:
                raise CaseAuditError("owner_impersonation")
            self._seal(event)
            self._write_idem(key_name, event)
        self._logs.append(operational_log(event))
        self._notifications.append(notification_payload(event))
        return event

    def _resolve_grant(
        self,
        *,
        actor_id: str,
        case_id: str,
        tenant_id: str,
        resource_id: str,
        action: str,
        expected_revision: int,
        grant_id: str,
        grant_kind: str,
        membership_version: int | None,
        require_action: bool,
    ) -> dict[str, Any]:
        if grant_kind == "owner":
            case = self._select_owner_case(actor_id, case_id)
            self._expect_case(case, tenant_id=tenant_id, resource_id=resource_id, expected_revision=expected_revision)
            if actor_id == case.tenant_id:
                raise CaseAuditError("owner_impersonation")
            if grant_id != owner_grant_reference(case.tenant_id):
                raise CaseAuditError("grant_mismatch")
            if require_action and action not in OWNER_ACTIONS:
                raise CaseAuditError("action_not_permitted")
            if membership_version is not None:
                raise CaseAuditError("grant_mismatch")
            return {
                "case_id": case.case_id,
                "tenant_id": case.tenant_id,
                "resource_id": case.resource_id,
                "revision": case.revision,
                "resource_revision": str(case.revision),
                "grant_id": grant_id,
                "grant_version": 0,
                "membership_version": 0,
                "membership_grant_id": "",
                "canonical_owner_principal_id": case.tenant_id,
            }
        if grant_kind == "membership":
            if type(membership_version) is not int:
                raise CaseAuditError("grant_version")
            decision = self._authorize_membership(
                actor_id=actor_id,
                grant_id=grant_id,
                tenant_id=tenant_id,
                case_id=case_id,
                resource_id=resource_id,
                action=action,
                expected_version=membership_version,
            )
            if decision.version != membership_version or decision.revision_case != expected_revision:
                raise CaseAuditError("revision_conflict")
            return {
                "case_id": decision.case_id,
                "tenant_id": decision.tenant_id,
                "resource_id": decision.resource_id,
                "revision": expected_revision,
                "resource_revision": str(expected_revision),
                "grant_id": decision.grant_id,
                "grant_version": decision.version,
                "membership_version": decision.version,
                "membership_grant_id": decision.grant_id,
                "canonical_owner_principal_id": decision.canonical_owner_principal_id,
            }
        loaded = self._load_key_grant(grant_id)
        if loaded.status != "active":
            raise CaseAuditError("grant_revoked")
        if loaded.recipient_principal_id != actor_id:
            raise CaseAuditError("actor_not_recipient")
        if loaded.case_id != case_id or loaded.tenant_id != tenant_id or loaded.resource_id != resource_id:
            raise CaseAuditError("grant_mismatch")
        if type(membership_version) is not int or membership_version != loaded.membership_version:
            raise CaseAuditError("grant_version")
        if loaded.version < 1:
            raise CaseAuditError("grant_mismatch")
        decision = self._authorize_membership(
            actor_id=actor_id,
            grant_id=loaded.membership_grant_id,
            tenant_id=tenant_id,
            case_id=case_id,
            resource_id=resource_id,
            action=action,
            expected_version=membership_version,
        )
        if expected_revision != decision.revision_case:
            raise CaseAuditError("revision_conflict")
        return {
            "case_id": loaded.case_id,
            "tenant_id": loaded.tenant_id,
            "resource_id": loaded.resource_id,
            "revision": expected_revision,
            "resource_revision": loaded.artifact_revision,
            "grant_id": loaded.key_grant_id,
            "grant_version": loaded.version,
            "membership_version": membership_version,
            "membership_grant_id": loaded.membership_grant_id,
            "canonical_owner_principal_id": loaded.canonical_owner_principal_id,
        }

    def _authorize_read(
        self,
        *,
        actor_id: str,
        case_id: str,
        tenant_id: str,
        resource_id: str,
        grant_id: str,
        grant_kind: str,
        expected_revision: int,
        membership_version: int | None,
    ) -> None:
        self._resolve_grant(
            actor_id=actor_id,
            case_id=case_id,
            tenant_id=tenant_id,
            resource_id=resource_id,
            action="case.read",
            expected_revision=expected_revision,
            grant_id=grant_id,
            grant_kind=grant_kind,
            membership_version=membership_version,
            require_action=True,
        )

    def _authorize_membership(
        self,
        *,
        actor_id: str,
        grant_id: str,
        tenant_id: str,
        case_id: str,
        resource_id: str,
        action: str,
        expected_version: int,
    ) -> Any:
        try:
            decision = self._memberships.authorize(
                actor_principal_id=actor_id,
                grant_id=grant_id,
                tenant_id=tenant_id,
                case_id=case_id,
                resource_id=resource_id,
                action=action,
                expected_version=expected_version,
            )
        except CaseMembershipError as exc:
            raise CaseAuditError(exc.code if exc.code.isidentifier() else "membership_required") from exc
        grant = self._load_membership(grant_id)
        if type(grant.case_revision) is not int or grant.case_revision < 1:
            raise CaseAuditError("revision_conflict")
        return _MembershipView(
            grant_id=decision.grant_id,
            version=decision.version,
            case_id=decision.case_id,
            tenant_id=decision.tenant_id,
            resource_id=decision.resource_id,
            canonical_owner_principal_id=decision.canonical_owner_principal_id,
            revision_case=grant.case_revision,
        )

    def _load_membership(self, grant_id: str) -> Any:
        try:
            return self._memberships.load(grant_id)
        except CaseMembershipError as exc:
            raise CaseAuditError(exc.code if exc.code.isidentifier() else "missing_grant") from exc

    def _load_key_grant(self, grant_id: str) -> Any:
        try:
            return self._key_grants.load(grant_id)
        except CaseResourceKeyGrantError as exc:
            raise CaseAuditError(exc.code if exc.code.isidentifier() else "missing_grant") from exc

    def _select_owner_case(self, actor_id: str, case_id: str) -> CaseNamespace:
        try:
            case = self._cases.select_case(actor_principal_id=actor_id, case_id=case_id)
        except CaseDirectoryError as exc:
            raise CaseAuditError(exc.code if exc.code.isidentifier() else "missing_case") from exc
        if case.owner_principal_id != actor_id:
            raise CaseAuditError("actor_not_owner")
        return case

    def _expect_case(
        self,
        case: CaseNamespace,
        *,
        tenant_id: str,
        resource_id: str,
        expected_revision: int,
    ) -> None:
        if tenant_id != case.tenant_id:
            raise CaseAuditError("tenant_mismatch")
        if resource_id != case.resource_id:
            raise CaseAuditError("resource_mismatch")
        if expected_revision != case.revision:
            raise CaseAuditError("revision_conflict")

    def _active(self, principal_id: str) -> Any:
        try:
            record = self._principals.load(_label(principal_id, "actor"))
        except (PrincipalStoreError, CaseAuditError) as exc:
            code = getattr(exc, "code", "missing_principal")
            raise CaseAuditError(code if isinstance(code, str) and code.isidentifier() else "missing_principal") from exc
        if record.status != "active":
            raise CaseAuditError("inactive_principal")
        if record.principal_id == "":
            raise CaseAuditError("missing_principal")
        return record

    def _grant_kind(self, value: str) -> str:
        kind = _label(value, "grant_kind")
        if kind not in GRANT_KINDS:
            raise CaseAuditError("grant_kind")
        return kind

    def _purpose(self, value: str) -> str:
        purpose = _label(value, "purpose_ref")
        if PURPOSE_RE.fullmatch(purpose) is None:
            raise CaseAuditError("purpose_ref")
        return purpose

    def _reject_sensitive(self, body: Mapping[str, Any]) -> None:
        for name, value in body.items():
            if not isinstance(name, str) or name.lower() in SENSITIVE_FIELDS:
                raise CaseAuditError("sensitive_field")
            if isinstance(value, Mapping) or isinstance(value, (list, tuple)):
                raise CaseAuditError("sensitive_field")
            if isinstance(value, (bytes, bytearray)):
                raise CaseAuditError("sensitive_field")
            if isinstance(value, str) and (len(value) > 200 or "\n" in value or "\x00" in value):
                raise CaseAuditError("sensitive_field")

    def _chain(self, case_id: str) -> tuple[CaseAuditEvent, ...]:
        directory = self._event_dir(case_id)
        if not directory.is_dir():
            return ()
        sequences: list[int] = []
        for path in directory.iterdir():
            if path.is_symlink():
                raise CaseAuditError("unexpected_path")
            if not path.is_file() or not path.name.endswith(".envelope"):
                if path.name.endswith(".event") or path.name.endswith(".tenant"):
                    continue
                raise CaseAuditError("unexpected_path")
            stem = path.name[: -len(".envelope")]
            if not stem.isdigit() or stem.startswith("0"):
                raise CaseAuditError("audit_chain_broken")
            sequences.append(int(stem))
        if not sequences:
            return ()
        ordered = sorted(sequences)
        if ordered != list(range(1, ordered[-1] + 1)):
            raise CaseAuditError("audit_chain_broken")
        events: list[CaseAuditEvent] = []
        previous_digest = "0" * 64
        previous_document: dict[str, Any] | None = None
        for sequence in ordered:
            pointer = directory / f"{sequence}.event"
            tenant_path = directory / f"{sequence}.tenant"
            if not pointer.is_file() or pointer.is_symlink() or not tenant_path.is_file():
                raise CaseAuditError("audit_chain_broken")
            event_id = pointer.read_text(encoding="utf-8").strip()
            event = self._load(case_id, sequence, event_id)
            if event.sequence != sequence or event.previous_digest != previous_digest:
                raise CaseAuditError("audit_chain_broken")
            if previous_document is not None and event.previous_digest != _document_digest(previous_document):
                raise CaseAuditError("audit_chain_broken")
            document = _event_document(event)
            previous_document = document
            previous_digest = _document_digest(document)
            events.append(event)
        return tuple(events)

    def _load(self, case_id: str, sequence: int, event_id: str) -> CaseAuditEvent:
        directory = self._event_dir(case_id)
        path = directory / f"{sequence}.envelope"
        tenant_path = directory / f"{sequence}.tenant"
        if not path.is_file() or path.is_symlink() or not tenant_path.is_file() or tenant_path.is_symlink():
            raise CaseAuditError("audit_chain_broken")
        tenant_id = tenant_path.read_text(encoding="utf-8").strip()
        binding = PrivateArtifactBinding(
            tenant_id=tenant_id,
            case_id=case_id,
            artifact_kind=ARTIFACT_KIND,
            revision=str(sequence),
            principal_id=tenant_id,
        )
        access = _CanonicalAccess("authenticated", tenant_id, case_id)
        try:
            assert_access_matches_binding(access, binding)
            plaintext = open_private_artifact(
                path.read_bytes(),
                binding=binding,
                key=self._key,
                expected_key_id=self._key_id,
            )
        except (PrivateArtifactIntegrityError, PrivateArtifactBindingError) as exc:
            raise CaseAuditError("integrity") from exc
        event = _event_from_document(json.loads(plaintext.decode("utf-8")))
        if event.event_id != event_id or event.sequence != sequence:
            raise CaseAuditError("binding_mismatch")
        if event.case_id != case_id or event.tenant_id != tenant_id:
            raise CaseAuditError("binding_mismatch")
        if event.actor_principal_id == event.canonical_owner_principal_id:
            raise CaseAuditError("owner_impersonation")
        if event.actor_is_encrypted_owner:
            raise CaseAuditError("owner_impersonation")
        return event

    def _seal(self, event: CaseAuditEvent) -> None:
        binding = PrivateArtifactBinding(
            tenant_id=event.tenant_id,
            case_id=event.case_id,
            artifact_kind=ARTIFACT_KIND,
            revision=str(event.sequence),
            principal_id=event.tenant_id,
        )
        access = _CanonicalAccess("authenticated", event.tenant_id, event.case_id)
        assert_access_matches_binding(access, binding)
        payload = json.dumps(_event_document(event), sort_keys=True, separators=(",", ":")).encode("utf-8")
        envelope = seal_private_artifact(payload, binding=binding, key=self._key, key_id=self._key_id)
        directory = self._event_dir(event.case_id)
        directory.mkdir(mode=0o700, exist_ok=True)
        path = directory / f"{event.sequence}.envelope"
        if path.exists():
            raise CaseAuditError("audit_append_conflict")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
        descriptor = os.open(path, flags, 0o600)
        try:
            view = envelope
            while view:
                wrote = os.write(descriptor, view)
                view = view[wrote:]
        finally:
            os.close(descriptor)
        self._write_text(directory / f"{event.sequence}.event", event.event_id)
        self._write_text(directory / f"{event.sequence}.tenant", event.tenant_id)

    def _idem_pointer(self, key: str) -> dict[str, Any] | None:
        path = self._idem_path(key)
        if not path.is_file() or path.is_symlink():
            return None
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) != 4:
            raise CaseAuditError("replay_mismatch")
        case_id, sequence_text, event_id, actor_id = lines
        if not sequence_text.isdigit():
            raise CaseAuditError("replay_mismatch")
        return {
            "case_id": case_id,
            "sequence": int(sequence_text),
            "event_id": event_id,
            "actor_principal_id": actor_id,
        }

    def _write_idem(self, key: str, event: CaseAuditEvent) -> None:
        body = "\n".join((
            event.case_id,
            str(event.sequence),
            event.event_id,
            event.actor_principal_id,
        ))
        self._write_text(self._idem_path(key), body)

    def _idem_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._root / "idem" / digest

    def _event_dir(self, case_id: str) -> Path:
        return self._root / "events" / case_id

    def _write_text(self, path: Path, text: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)

    def _locked(self):
        return _FileLock(self._lock_path)


@dataclass(frozen=True)
class _MembershipView:
    grant_id: str
    version: int
    case_id: str
    tenant_id: str
    resource_id: str
    canonical_owner_principal_id: str
    revision_case: int


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


def _event_document(event: CaseAuditEvent) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": event.event_id,
        "sequence": event.sequence,
        "action": event.action,
        "actor_principal_id": event.actor_principal_id,
        "resource_id": event.resource_id,
        "revision": event.revision,
        "resource_revision": event.resource_revision,
        "grant_id": event.grant_id,
        "grant_kind": event.grant_kind,
        "grant_version": event.grant_version,
        "membership_version": event.membership_version,
        "membership_grant_id": event.membership_grant_id,
        "purpose_ref": event.purpose_ref,
        "tenant_id": event.tenant_id,
        "case_id": event.case_id,
        "canonical_owner_principal_id": event.canonical_owner_principal_id,
        "actor_is_encrypted_owner": event.actor_is_encrypted_owner,
        "previous_digest": event.previous_digest,
        "idempotency_key": event.idempotency_key,
        "fingerprint": _fingerprint(event),
    }


def _event_from_document(document: Mapping[str, Any]) -> CaseAuditEvent:
    if int(document.get("schema_version") or 0) != SCHEMA_VERSION:
        raise CaseAuditError("schema")
    sequence = document.get("sequence")
    revision = document.get("revision")
    grant_version = document.get("grant_version")
    membership_version = document.get("membership_version")
    if type(sequence) is not int or sequence < 1:
        raise CaseAuditError("schema")
    if type(revision) is not int or revision < 1 or type(grant_version) is not int or grant_version < 0:
        raise CaseAuditError("schema")
    if type(membership_version) is not int or membership_version < 0:
        raise CaseAuditError("schema")
    kind = str(document.get("grant_kind") or "")
    if kind not in GRANT_KINDS:
        raise CaseAuditError("schema")
    if document.get("actor_is_encrypted_owner") is not False:
        raise CaseAuditError("owner_impersonation")
    event = CaseAuditEvent(
        event_id=_label(str(document.get("event_id") or ""), "schema"),
        sequence=sequence,
        action=_label(str(document.get("action") or ""), "schema"),
        actor_principal_id=_label(str(document.get("actor_principal_id") or ""), "schema"),
        resource_id=_label(str(document.get("resource_id") or ""), "schema"),
        revision=revision,
        resource_revision=_label(str(document.get("resource_revision") or ""), "schema"),
        grant_id=_label(str(document.get("grant_id") or ""), "schema"),
        grant_kind=kind,
        grant_version=grant_version,
        membership_version=membership_version,
        membership_grant_id=str(document.get("membership_grant_id") or ""),
        purpose_ref=_label(str(document.get("purpose_ref") or ""), "schema"),
        tenant_id=_label(str(document.get("tenant_id") or ""), "schema"),
        case_id=_label(str(document.get("case_id") or ""), "schema"),
        canonical_owner_principal_id=_label(str(document.get("canonical_owner_principal_id") or ""), "schema"),
        actor_is_encrypted_owner=False,
        previous_digest=_label(str(document.get("previous_digest") or ""), "schema"),
        idempotency_key=_label(str(document.get("idempotency_key") or ""), "schema"),
    )
    if kind == "owner" and event.membership_grant_id != "":
        raise CaseAuditError("schema")
    if kind == "membership" and event.membership_grant_id != event.grant_id:
        raise CaseAuditError("schema")
    if kind == "key":
        _label(event.membership_grant_id, "schema")
    if PURPOSE_RE.fullmatch(event.purpose_ref) is None:
        raise CaseAuditError("schema")
    if len(event.previous_digest) != 64:
        raise CaseAuditError("schema")
    stored = str(document.get("fingerprint") or "")
    if stored != _fingerprint(event):
        raise CaseAuditError("integrity")
    return event
