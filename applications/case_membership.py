"""Durable explicit case membership and scoped action grants.

Owner approval creates a pending membership. The recipient accepts or declines.
Only an accepted grant authorizes its explicit actions, and only until expiry.
Grant identifiers stay stable across version changes. A request body cannot
mint a grant, set a status, or supply actions.

The authenticated actor stays distinct from the canonical encrypted owner,
which is the case tenant. This store does not issue recipient key grants,
rewrite ``CaseActionAuthorizer`` process memory, or erase a download that
already completed. Revocation and removal deny later use.

Storage is one sealed envelope per grant. Routing hints are untrusted until
the injected key opens the envelope under the expected tenant, case, and
revision. Concurrent edits use an exclusive lock and an expected version.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from applications.case_access import ASSIGNED_LAWYER_ACTIONS
from applications.case_directory import CaseDirectory, CaseDirectoryError
from applications.principal_store import PrincipalStore, PrincipalStoreError
from integrations.private_storage import (
    PrivateArtifactBinding,
    PrivateArtifactIntegrityError,
    assert_access_matches_binding,
    open_private_artifact,
    seal_private_artifact,
)

TASK_ID = "CIMP-GUI-10"
SCHEMA_VERSION = 1
ARTIFACT_KIND = "case-membership-grant"
GRANT_ACTIONS = ASSIGNED_LAWYER_ACTIONS
STATUSES = frozenset({"pending", "accepted", "declined", "removed"})
CALLER_MINT_FIELDS = frozenset({
    "trusted_local",
    "trust",
    "role",
    "roles",
    "staff_role",
    "is_admin",
    "is_staff",
    "is_lawyer",
    "is_member",
    "membership",
    "grant",
    "grant_id",
    "actions",
    "status",
    "expires_at",
    "version",
    "accepted",
    "case_plaintext",
    "credentials",
    "credential",
    "narrative",
    "evidence",
})


class CaseMembershipError(Exception):
    """Fail-closed membership error. ``code`` is a stable machine reason."""

    def __init__(self, code: str) -> None:
        self.code = str(code)
        super().__init__(self.code)


@dataclass(frozen=True)
class _CanonicalAccess:
    trust: str
    principal_id: str
    case_id: str


@dataclass(frozen=True)
class OpenRequest:
    request_id: str
    actor_principal_id: str
    action: str
    grant_version: int


@dataclass(frozen=True)
class MembershipGrant:
    """Owner-approved membership. ``grant_id`` does not change when ``version`` does."""

    grant_id: str
    version: int
    status: str
    owner_principal_id: str
    member_principal_id: str
    tenant_id: str
    case_id: str
    resource_id: str
    actions: tuple[str, ...]
    expires_at: int
    case_revision: int
    invite_key: str
    decision_key: str | None
    open_requests: tuple[OpenRequest, ...]

    def public_view(self) -> dict[str, Any]:
        return {
            "grant_id": self.grant_id,
            "version": self.version,
            "status": self.status,
            "owner_principal_id": self.owner_principal_id,
            "member_principal_id": self.member_principal_id,
            "tenant_id": self.tenant_id,
            "case_id": self.case_id,
            "resource_id": self.resource_id,
            "actions": list(self.actions),
            "expires_at": self.expires_at,
            "case_revision": self.case_revision,
            "schema_version": SCHEMA_VERSION,
            "open_request_ids": [item.request_id for item in self.open_requests],
        }


@dataclass(frozen=True)
class MembershipDecision:
    """Allow result for one explicit action. Denials raise ``CaseMembershipError``."""

    grant_id: str
    version: int
    action: str
    actor_principal_id: str
    tenant_id: str
    case_id: str
    resource_id: str
    expires_at: int
    canonical_owner_principal_id: str
    actor_is_encrypted_owner: bool
    permits_case_content: bool


@dataclass(frozen=True)
class OpenCaseRequest:
    """In-flight use of an accepted grant. Removal invalidates ``finish``."""

    request_id: str
    grant_id: str
    grant_version: int
    actor_principal_id: str
    action: str
    tenant_id: str
    case_id: str


def _opaque_id() -> str:
    return uuid.uuid4().hex


def _label(value: str, code: str) -> str:
    if not isinstance(value, str) or value.strip() == "" or value != value.strip():
        raise CaseMembershipError(code)
    if any(char in value for char in ("\x00", "\n", "\r", "/", "\\")):
        raise CaseMembershipError(code)
    return value


def _fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CaseMembershipStore:
    """File-backed membership grants for one injected data key."""

    def __init__(
        self,
        root: str | Path,
        *,
        key: bytes,
        key_id: str,
        principals: PrincipalStore,
        cases: CaseDirectory,
        clock: Callable[[], int] | None = None,
    ) -> None:
        if not isinstance(key, (bytes, bytearray)) or isinstance(key, memoryview):
            raise CaseMembershipError("key_material")
        if len(bytes(key)) != 32:
            raise CaseMembershipError("key_material")
        if not isinstance(principals, PrincipalStore) or not isinstance(cases, CaseDirectory):
            raise CaseMembershipError("authority_owners")
        self._key = bytes(key)
        self._key_id = _label(key_id, "key_id")
        self._principals = principals
        self._cases = cases
        self._clock = clock or (lambda: int(time.time()))
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        os.chmod(self._root, 0o700)
        self._lock_path = self._root / ".lock"
        self._lock_path.touch(mode=0o600)
        (self._root / "grants").mkdir(mode=0o700, exist_ok=True)
        (self._root / "idem").mkdir(mode=0o700, exist_ok=True)

    def invite(
        self,
        *,
        owner_principal_id: str,
        member_principal_id: str,
        case_id: str,
        resource_id: str,
        tenant_id: str,
        actions: frozenset[str] | set[str],
        expires_at: int,
        expected_case_revision: int,
        idempotency_key: str,
    ) -> MembershipGrant:
        """Owner creates one pending grant. The same key replays the same grant id."""

        owner = self._active(owner_principal_id)
        member = self._active(member_principal_id)
        if "lawyer" not in member.roles:
            raise CaseMembershipError("lawyer_role_required")
        if member.principal_id == owner.principal_id:
            raise CaseMembershipError("actor_not_owner")
        granted = self._actions(actions)
        expiry = self._expiry(expires_at)
        key = _label(idempotency_key, "idempotency_key")
        case = self._select(owner.principal_id, case_id)
        if case.owner_principal_id != owner.principal_id:
            raise CaseMembershipError("actor_not_owner")
        if tenant_id != case.tenant_id:
            raise CaseMembershipError("tenant_mismatch")
        if resource_id != case.resource_id:
            raise CaseMembershipError("resource_mismatch")
        if type(expected_case_revision) is not int or expected_case_revision != case.revision:
            raise CaseMembershipError("revision_conflict")
        fingerprint = _fingerprint({
            "owner_principal_id": owner.principal_id,
            "member_principal_id": member.principal_id,
            "case_id": case.case_id,
            "resource_id": case.resource_id,
            "tenant_id": case.tenant_id,
            "actions": list(granted),
            "expires_at": expiry,
            "case_revision": case.revision,
        })
        with self._locked():
            existing_id = self._idem_grant(key)
            if existing_id is not None:
                existing = self._load(existing_id)
                if existing.invite_key != key or _invite_fingerprint(existing) != fingerprint:
                    raise CaseMembershipError("replay_mismatch")
                return existing
            record = MembershipGrant(
                grant_id=_opaque_id(),
                version=1,
                status="pending",
                owner_principal_id=owner.principal_id,
                member_principal_id=member.principal_id,
                tenant_id=case.tenant_id,
                case_id=case.case_id,
                resource_id=case.resource_id,
                actions=granted,
                expires_at=expiry,
                case_revision=case.revision,
                invite_key=key,
                decision_key=None,
                open_requests=(),
            )
            self._seal(record)
            self._write_idem(key, record.grant_id)
            return record

    def accept(
        self,
        *,
        member_principal_id: str,
        grant_id: str,
        expected_version: int,
        idempotency_key: str,
    ) -> MembershipGrant:
        return self._decide(
            member_principal_id=member_principal_id,
            grant_id=grant_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            status="accepted",
        )

    def decline(
        self,
        *,
        member_principal_id: str,
        grant_id: str,
        expected_version: int,
        idempotency_key: str,
    ) -> MembershipGrant:
        return self._decide(
            member_principal_id=member_principal_id,
            grant_id=grant_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            status="declined",
        )

    def update_scope(
        self,
        *,
        owner_principal_id: str,
        grant_id: str,
        expected_version: int,
        actions: frozenset[str] | set[str] | None = None,
        expires_at: int | None = None,
    ) -> MembershipGrant:
        """Owner edits actions or expiry. The grant id stays the same."""

        owner = self._active(owner_principal_id)
        if actions is None and expires_at is None:
            raise CaseMembershipError("empty_update")
        granted = None if actions is None else self._actions(actions)
        expiry = None if expires_at is None else self._expiry(expires_at)
        with self._locked():
            current = self._load(_label(grant_id, "grant_id"))
            if current.owner_principal_id != owner.principal_id:
                raise CaseMembershipError("actor_not_owner")
            if current.status not in {"pending", "accepted"}:
                raise CaseMembershipError("membership_terminal")
            self._expect_version(current, expected_version)
            updated = _replace(
                current,
                version=current.version + 1,
                actions=current.actions if granted is None else granted,
                expires_at=current.expires_at if expiry is None else expiry,
            )
            self._seal(updated)
            return updated

    def remove(
        self,
        *,
        owner_principal_id: str,
        grant_id: str,
        expected_version: int,
    ) -> MembershipGrant:
        """Owner withdraws a pending or accepted grant, including during an open request."""

        owner = self._active(owner_principal_id)
        with self._locked():
            current = self._load(_label(grant_id, "grant_id"))
            if current.owner_principal_id != owner.principal_id:
                raise CaseMembershipError("actor_not_owner")
            if current.status not in {"pending", "accepted"}:
                raise CaseMembershipError("membership_terminal")
            self._expect_version(current, expected_version)
            updated = _replace(current, version=current.version + 1, status="removed")
            self._seal(updated)
            return updated

    def authorize(
        self,
        *,
        actor_principal_id: str,
        grant_id: str,
        tenant_id: str,
        case_id: str,
        resource_id: str,
        action: str,
        expected_version: int,
    ) -> MembershipDecision:
        """Authorize one explicit action. Pending, declined, removed, and expired grants fail."""

        actor = self._active(actor_principal_id)
        requested = self._one_action(action)
        with self._locked():
            grant = self._usable(
                actor_id=actor.principal_id,
                grant_id=grant_id,
                tenant_id=tenant_id,
                case_id=case_id,
                resource_id=resource_id,
                action=requested,
                expected_version=expected_version,
            )
            return MembershipDecision(
                grant_id=grant.grant_id,
                version=grant.version,
                action=requested,
                actor_principal_id=actor.principal_id,
                tenant_id=grant.tenant_id,
                case_id=grant.case_id,
                resource_id=grant.resource_id,
                expires_at=grant.expires_at,
                canonical_owner_principal_id=grant.tenant_id,
                actor_is_encrypted_owner=False,
                permits_case_content=True,
            )

    def begin_request(
        self,
        *,
        actor_principal_id: str,
        grant_id: str,
        tenant_id: str,
        case_id: str,
        resource_id: str,
        action: str,
        expected_version: int,
        request_id: str,
    ) -> OpenCaseRequest:
        """Record an open use. A later removal makes ``finish_request`` fail."""

        actor = self._active(actor_principal_id)
        requested = self._one_action(action)
        identity = _label(request_id, "request_id")
        with self._locked():
            grant = self._usable(
                actor_id=actor.principal_id,
                grant_id=grant_id,
                tenant_id=tenant_id,
                case_id=case_id,
                resource_id=resource_id,
                action=requested,
                expected_version=expected_version,
            )
            for item in grant.open_requests:
                if item.request_id == identity:
                    if item.actor_principal_id != actor.principal_id or item.action != requested:
                        raise CaseMembershipError("replay_mismatch")
                    return _ticket(grant, item)
            opened = OpenRequest(
                request_id=identity,
                actor_principal_id=actor.principal_id,
                action=requested,
                grant_version=grant.version,
            )
            updated = _replace(grant, open_requests=grant.open_requests + (opened,))
            self._seal(updated)
            return _ticket(updated, opened)

    def finish_request(self, ticket: OpenCaseRequest) -> MembershipDecision:
        """Complete an open request. Removal or a version change after begin denies it."""

        if not isinstance(ticket, OpenCaseRequest):
            raise CaseMembershipError("request_ticket")
        with self._locked():
            grant = self._load(ticket.grant_id)
            match = None
            for item in grant.open_requests:
                if item.request_id == ticket.request_id:
                    match = item
                    break
            if match is None or match.grant_version != ticket.grant_version:
                raise CaseMembershipError("replay_mismatch")
            if grant.status == "removed" or grant.version != ticket.grant_version:
                raise CaseMembershipError("membership_removed")
            if grant.status != "accepted":
                raise CaseMembershipError(f"membership_{grant.status}")
            if self._now() >= grant.expires_at:
                raise CaseMembershipError("grant_expired")
            if ticket.tenant_id != grant.tenant_id:
                raise CaseMembershipError("tenant_mismatch")
            if ticket.case_id != grant.case_id or ticket.actor_principal_id != match.actor_principal_id:
                raise CaseMembershipError("case_mismatch")
            remaining = tuple(item for item in grant.open_requests if item.request_id != ticket.request_id)
            updated = _replace(grant, open_requests=remaining)
            self._seal(updated)
            return MembershipDecision(
                grant_id=grant.grant_id,
                version=grant.version,
                action=match.action,
                actor_principal_id=match.actor_principal_id,
                tenant_id=grant.tenant_id,
                case_id=grant.case_id,
                resource_id=grant.resource_id,
                expires_at=grant.expires_at,
                canonical_owner_principal_id=grant.tenant_id,
                actor_is_encrypted_owner=False,
                permits_case_content=True,
            )

    def invite_from_request(self, body: Mapping[str, Any]) -> MembershipGrant:
        """Request mappings cannot mint grants. Flags and a well-formed body both fail."""

        if not isinstance(body, Mapping):
            raise CaseMembershipError("request_body")
        if any(name in body for name in CALLER_MINT_FIELDS):
            raise CaseMembershipError("request_cannot_mint_grant")
        if body.get("trusted_local") is True or body.get("trust") == "trusted_local":
            raise CaseMembershipError("request_cannot_mint_grant")
        raise CaseMembershipError("request_cannot_mint_grant")

    def load(self, grant_id: str) -> MembershipGrant:
        with self._locked():
            return self._load(_label(grant_id, "grant_id"))

    def recover(self) -> tuple[MembershipGrant, ...]:
        with self._locked():
            records: list[MembershipGrant] = []
            for path in sorted((self._root / "grants").glob("*.envelope")):
                if not path.is_file() or path.is_symlink():
                    raise CaseMembershipError("unexpected_path")
                records.append(self._load(path.name[: -len(".envelope")]))
            return tuple(records)

    def _decide(
        self,
        *,
        member_principal_id: str,
        grant_id: str,
        expected_version: int,
        idempotency_key: str,
        status: str,
    ) -> MembershipGrant:
        member = self._active(member_principal_id)
        key = _label(idempotency_key, "idempotency_key")
        with self._locked():
            current = self._load(_label(grant_id, "grant_id"))
            if current.member_principal_id != member.principal_id:
                raise CaseMembershipError("actor_not_member")
            if current.decision_key == key and current.status == status:
                return current
            if current.decision_key is not None or current.status != "pending":
                if current.status == "removed":
                    raise CaseMembershipError("membership_removed")
                raise CaseMembershipError("membership_replay")
            self._expect_version(current, expected_version)
            if self._now() >= current.expires_at:
                raise CaseMembershipError("grant_expired")
            updated = _replace(
                current,
                version=current.version + 1,
                status=status,
                decision_key=key,
            )
            self._seal(updated)
            return updated

    def _usable(
        self,
        *,
        actor_id: str,
        grant_id: str,
        tenant_id: str,
        case_id: str,
        resource_id: str,
        action: str,
        expected_version: int,
    ) -> MembershipGrant:
        grant = self._load(_label(grant_id, "grant_id"))
        if grant.member_principal_id != actor_id:
            raise CaseMembershipError("actor_not_member")
        if tenant_id != grant.tenant_id:
            raise CaseMembershipError("tenant_mismatch")
        if case_id != grant.case_id or resource_id != grant.resource_id:
            raise CaseMembershipError("case_mismatch")
        if grant.status == "pending":
            raise CaseMembershipError("membership_pending")
        if grant.status == "declined":
            raise CaseMembershipError("membership_declined")
        if grant.status == "removed":
            raise CaseMembershipError("membership_removed")
        if grant.status != "accepted":
            raise CaseMembershipError("membership_required")
        self._expect_version(grant, expected_version)
        if action not in grant.actions:
            raise CaseMembershipError("action_not_permitted")
        if self._now() >= grant.expires_at:
            raise CaseMembershipError("grant_expired")
        case = self._select(grant.owner_principal_id, grant.case_id)
        if case.tenant_id != grant.tenant_id or case.resource_id != grant.resource_id:
            raise CaseMembershipError("membership_required")
        if case.revision != grant.case_revision:
            raise CaseMembershipError("revision_conflict")
        return grant

    def _select(self, actor_id: str, case_id: str):
        try:
            return self._cases.select_case(actor_principal_id=actor_id, case_id=case_id)
        except CaseDirectoryError as exc:
            raise CaseMembershipError(exc.code) from exc

    def _active(self, principal_id: str):
        try:
            record = self._principals.load(principal_id)
        except PrincipalStoreError as exc:
            raise CaseMembershipError("missing_principal") from exc
        if record.status != "active":
            raise CaseMembershipError("inactive_principal")
        return record

    def _actions(self, actions: frozenset[str] | set[str]) -> tuple[str, ...]:
        if not isinstance(actions, (set, frozenset)) or not actions:
            raise CaseMembershipError("action_not_permitted")
        if any(not isinstance(item, str) for item in actions) or not set(actions) <= GRANT_ACTIONS:
            raise CaseMembershipError("action_not_permitted")
        return tuple(sorted(actions))

    def _one_action(self, action: str) -> str:
        if not isinstance(action, str) or action not in GRANT_ACTIONS:
            raise CaseMembershipError("action_not_permitted")
        return action

    def _expiry(self, expires_at: int) -> int:
        if type(expires_at) is not int or expires_at <= self._now():
            raise CaseMembershipError("expiry")
        return expires_at

    def _now(self) -> int:
        value = self._clock()
        if type(value) is not int:
            raise CaseMembershipError("clock")
        return value

    def _expect_version(self, grant: MembershipGrant, expected_version: int) -> None:
        if type(expected_version) is not int or expected_version != grant.version:
            raise CaseMembershipError("revision_conflict")

    def _load(self, grant_id: str) -> MembershipGrant:
        path = self._grant_path(grant_id)
        if not path.is_file() or path.is_symlink():
            raise CaseMembershipError("missing_grant")
        pointer = self._root / "grants" / f"{grant_id}.revision"
        tenant_path = self._root / "grants" / f"{grant_id}.tenant"
        case_path = self._root / "grants" / f"{grant_id}.case"
        if not pointer.is_file() or not tenant_path.is_file() or not case_path.is_file():
            raise CaseMembershipError("missing_revision")
        revision_text = pointer.read_text(encoding="utf-8").strip()
        if not revision_text.isdigit():
            raise CaseMembershipError("revision_pointer")
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
            raise CaseMembershipError("integrity") from exc
        grant = _grant_from_document(json.loads(plaintext.decode("utf-8")))
        if grant.grant_id != grant_id or grant.tenant_id != tenant_id or grant.case_id != case_id:
            raise CaseMembershipError("binding_mismatch")
        if grant.version != revision:
            raise CaseMembershipError("revision_mismatch")
        return grant

    def _seal(self, grant: MembershipGrant) -> None:
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
        path = directory / f"{grant.grant_id}.envelope"
        temporary = directory / f"{grant.grant_id}.envelope.tmp"
        temporary.write_bytes(envelope)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        self._write_text(directory / f"{grant.grant_id}.revision", str(grant.version))
        self._write_text(directory / f"{grant.grant_id}.tenant", grant.tenant_id)
        self._write_text(directory / f"{grant.grant_id}.case", grant.case_id)

    def _idem_grant(self, key: str) -> str | None:
        path = self._idem_path(key)
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8").strip() or None

    def _write_idem(self, key: str, grant_id: str) -> None:
        self._write_text(self._idem_path(key), grant_id)

    def _idem_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._root / "idem" / digest

    def _grant_path(self, grant_id: str) -> Path:
        return self._root / "grants" / f"{grant_id}.envelope"

    def _write_text(self, path: Path, text: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)

    def _locked(self):
        return _FileLock(self._lock_path)


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


def _replace(grant: MembershipGrant, **changes: Any) -> MembershipGrant:
    data = {
        "grant_id": grant.grant_id,
        "version": grant.version,
        "status": grant.status,
        "owner_principal_id": grant.owner_principal_id,
        "member_principal_id": grant.member_principal_id,
        "tenant_id": grant.tenant_id,
        "case_id": grant.case_id,
        "resource_id": grant.resource_id,
        "actions": grant.actions,
        "expires_at": grant.expires_at,
        "case_revision": grant.case_revision,
        "invite_key": grant.invite_key,
        "decision_key": grant.decision_key,
        "open_requests": grant.open_requests,
    }
    data.update(changes)
    return MembershipGrant(**data)


def _ticket(grant: MembershipGrant, item: OpenRequest) -> OpenCaseRequest:
    return OpenCaseRequest(
        request_id=item.request_id,
        grant_id=grant.grant_id,
        grant_version=item.grant_version,
        actor_principal_id=item.actor_principal_id,
        action=item.action,
        tenant_id=grant.tenant_id,
        case_id=grant.case_id,
    )


def _invite_fingerprint(grant: MembershipGrant) -> str:
    return _fingerprint({
        "owner_principal_id": grant.owner_principal_id,
        "member_principal_id": grant.member_principal_id,
        "case_id": grant.case_id,
        "resource_id": grant.resource_id,
        "tenant_id": grant.tenant_id,
        "actions": list(grant.actions),
        "expires_at": grant.expires_at,
        "case_revision": grant.case_revision,
    })


def _grant_document(grant: MembershipGrant) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "grant_id": grant.grant_id,
        "version": grant.version,
        "status": grant.status,
        "owner_principal_id": grant.owner_principal_id,
        "member_principal_id": grant.member_principal_id,
        "tenant_id": grant.tenant_id,
        "case_id": grant.case_id,
        "resource_id": grant.resource_id,
        "actions": list(grant.actions),
        "expires_at": grant.expires_at,
        "case_revision": grant.case_revision,
        "invite_key": grant.invite_key,
        "decision_key": grant.decision_key,
        "open_requests": [
            {
                "request_id": item.request_id,
                "actor_principal_id": item.actor_principal_id,
                "action": item.action,
                "grant_version": item.grant_version,
            }
            for item in grant.open_requests
        ],
    }


def _grant_from_document(document: Mapping[str, Any]) -> MembershipGrant:
    if int(document.get("schema_version") or 0) != SCHEMA_VERSION:
        raise CaseMembershipError("schema")
    version = document.get("version")
    expires_at = document.get("expires_at")
    case_revision = document.get("case_revision")
    if type(version) is not int or version < 1:
        raise CaseMembershipError("revision")
    if type(expires_at) is not int or type(case_revision) is not int:
        raise CaseMembershipError("schema")
    status = str(document.get("status") or "")
    if status not in STATUSES:
        raise CaseMembershipError("schema")
    actions = tuple(str(item) for item in document.get("actions") or ())
    if not actions or any(item not in GRANT_ACTIONS for item in actions):
        raise CaseMembershipError("action_not_permitted")
    opens: list[OpenRequest] = []
    for item in document.get("open_requests") or ():
        if not isinstance(item, Mapping):
            raise CaseMembershipError("schema")
        opened_version = item.get("grant_version")
        if type(opened_version) is not int:
            raise CaseMembershipError("schema")
        opens.append(OpenRequest(
            request_id=_label(str(item.get("request_id") or ""), "request_id"),
            actor_principal_id=_label(str(item.get("actor_principal_id") or ""), "principal_id"),
            action=_label(str(item.get("action") or ""), "action"),
            grant_version=opened_version,
        ))
    decision = document.get("decision_key")
    return MembershipGrant(
        grant_id=_label(str(document.get("grant_id") or ""), "grant_id"),
        version=version,
        status=status,
        owner_principal_id=_label(str(document.get("owner_principal_id") or ""), "principal_id"),
        member_principal_id=_label(str(document.get("member_principal_id") or ""), "principal_id"),
        tenant_id=_label(str(document.get("tenant_id") or ""), "tenant_id"),
        case_id=_label(str(document.get("case_id") or ""), "case_id"),
        resource_id=_label(str(document.get("resource_id") or ""), "resource_id"),
        actions=tuple(sorted(actions)),
        expires_at=expires_at,
        case_revision=case_revision,
        invite_key=_label(str(document.get("invite_key") or ""), "idempotency_key"),
        decision_key=None if decision is None else _label(str(decision), "idempotency_key"),
        open_requests=tuple(opens),
    )
