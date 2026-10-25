"""Recipient-bound case resource key grants.

Positive cases wrap a case data key to an accepted member and open the
artifact under the canonical tenant/case/principal/revision binding. Negative
cases reject membership without a grant, a grant without membership, browser
keys, admin master decryption, owner impersonation, and a changed revision.
Existing owner-only associated-data denial and schema version 2 stay in force.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from applications.case_directory import CaseDirectory
from applications.case_membership import CaseMembershipStore
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import (
    SCHEMA_VERSION,
    CaseResourceKeyGrantError,
    CaseResourceKeyGrantStore,
)
from integrations.private_storage import (
    KEY_STORE_VERSION,
    PrivateArtifactBinding,
    PrivateArtifactBindingError,
    PrivateArtifactIntegrityError,
    UserOwnedKeySession,
    assert_access_matches_binding,
    open_private_artifact,
    seal_private_artifact,
)

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ARTIFACT_KIND = "case-note"
REVISION = "3"


class _Access:
    def __init__(self, principal_id: str, case_id: str, trust: str = "authenticated") -> None:
        self.principal_id = principal_id
        self.case_id = case_id
        self.trust = trust


def _world(tmp_path: Path):
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    admin = principals.install_server_role(role="operational_admin")
    stranger = principals.register_from_request({})
    case = cases.create_case(actor_principal_id=owner.principal_id)
    memberships = CaseMembershipStore(
        tmp_path / "memberships",
        key=os.urandom(32),
        key_id="membership-key",
        principals=principals,
        cases=cases,
        clock=lambda: 1_700_000_000,
    )
    grants = CaseResourceKeyGrantStore(
        tmp_path / "key-grants",
        key=os.urandom(32),
        key_id="resource-grant-key",
        principals=principals,
        cases=cases,
        memberships=memberships,
    )
    owner_session = UserOwnedKeySession(tmp_path / "owner-keys")
    owner_session.create(protection="passphrase", passphrase="owner-passphrase")
    recipient_session = UserOwnedKeySession(tmp_path / "lawyer-keys")
    recipient_session.create(protection="passphrase", passphrase="lawyer-passphrase")
    owner_session.ensure_data_key(case.tenant_id, case.case_id)
    return {
        "principals": principals,
        "cases": cases,
        "memberships": memberships,
        "grants": grants,
        "owner": owner,
        "lawyer": lawyer,
        "admin": admin,
        "stranger": stranger,
        "case": case,
        "owner_session": owner_session,
        "recipient_session": recipient_session,
    }


def _accept(world, *, actions=None, key: str = "invite-1"):
    pending = world["memberships"].invite(
        owner_principal_id=world["owner"].principal_id,
        member_principal_id=world["lawyer"].principal_id,
        case_id=world["case"].case_id,
        resource_id=world["case"].resource_id,
        tenant_id=world["case"].tenant_id,
        actions=set(actions or {"case.read"}),
        expires_at=1_700_003_600,
        expected_case_revision=world["case"].revision,
        idempotency_key=key,
    )
    return world["memberships"].accept(
        member_principal_id=world["lawyer"].principal_id,
        grant_id=pending.grant_id,
        expected_version=pending.version,
        idempotency_key=key + "-accept",
    )


def _seal(world, payload: bytes = b"synthetic-case-note", *, revision: str = REVISION) -> bytes:
    case = world["case"]
    binding = PrivateArtifactBinding(
        tenant_id=case.tenant_id,
        case_id=case.case_id,
        artifact_kind=ARTIFACT_KIND,
        revision=revision,
        principal_id=case.tenant_id,
    )
    key_id, key = world["owner_session"].provider().resolve(binding)
    return seal_private_artifact(payload, binding=binding, key=key, key_id=key_id)


def _issue(world, membership, *, revision: str = REVISION, key: str = "grant-1"):
    case = world["case"]
    return world["grants"].issue(
        actor_principal_id=world["owner"].principal_id,
        recipient_principal_id=world["lawyer"].principal_id,
        membership_grant_id=membership.grant_id,
        membership_version=membership.version,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        artifact_kind=ARTIFACT_KIND,
        artifact_revision=revision,
        owner_session=world["owner_session"],
        recipient_session=world["recipient_session"],
        idempotency_key=key,
    )


def test_delegated_read_requires_membership_and_recipient_grant(tmp_path: Path) -> None:
    world = _world(tmp_path)
    case = world["case"]
    payload = b"synthetic-case-note"
    envelope = _seal(world, payload)
    pending = world["memberships"].invite(
        owner_principal_id=world["owner"].principal_id,
        member_principal_id=world["lawyer"].principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions={"case.read"},
        expires_at=1_700_003_600,
        expected_case_revision=case.revision,
        idempotency_key="pending-invite",
    )
    with pytest.raises(CaseResourceKeyGrantError) as pending_grant:
        _issue(world, pending, key="pending-grant")
    assert pending_grant.value.code == "membership_pending"

    accepted = _accept(world)
    with pytest.raises(CaseResourceKeyGrantError) as browser:
        world["grants"].issue_from_request({
            "actor_principal_id": world["owner"].principal_id,
            "recipient_principal_id": world["lawyer"].principal_id,
            "browser_key": "raw-browser-key",
            "data_key": "aa" * 32,
            "trusted_local": True,
        })
    assert browser.value.code == "browser_key_rejected"
    with pytest.raises(CaseResourceKeyGrantError) as bare:
        world["grants"].issue_from_request({"actor_principal_id": world["owner"].principal_id})
    assert bare.value.code == "request_cannot_mint_key_grant"

    with pytest.raises(CaseResourceKeyGrantError) as missing_grant:
        world["grants"].read_delegated(
            actor_principal_id=world["lawyer"].principal_id,
            membership_grant_id=accepted.grant_id,
            membership_version=accepted.version,
            key_grant_id="missing-grant",
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            envelope=envelope,
            recipient_session=world["recipient_session"],
        )
    assert missing_grant.value.code == "key_grant_required"

    granted = _issue(world, accepted)
    again = _issue(world, accepted)
    assert again.key_grant_id == granted.key_grant_id
    assert granted.owner_principal_id == world["owner"].principal_id
    assert granted.canonical_owner_principal_id == case.tenant_id
    assert granted.owner_principal_id != granted.canonical_owner_principal_id
    assert granted.recipient_principal_id == world["lawyer"].principal_id
    view = granted.public_view()
    assert view["schema_version"] == SCHEMA_VERSION
    assert view["envelope_schema_version"] == 2
    assert view["actor_is_encrypted_owner"] is False
    assert "wrapped_ciphertext" not in view
    assert "data_key" not in view
    assert "browser_keys_are_rejected" in view["limitations"]
    stored = (tmp_path / "key-grants" / "grants" / f"{granted.key_grant_id}.envelope").read_bytes()
    binding = PrivateArtifactBinding(
        tenant_id=case.tenant_id,
        case_id=case.case_id,
        artifact_kind=ARTIFACT_KIND,
        revision=REVISION,
        principal_id=case.tenant_id,
    )
    _key_id, data_key = world["owner_session"].provider().resolve(binding)
    assert data_key not in stored
    assert stat.S_IMODE((tmp_path / "key-grants" / "grants" / f"{granted.key_grant_id}.envelope").stat().st_mode) == 0o600
    keystore = json.loads((tmp_path / "lawyer-keys" / "keystore.json").read_text(encoding="utf-8"))
    assert keystore["schema_version"] == KEY_STORE_VERSION
    assert keystore["raw_key_persisted"] is False

    opened = world["grants"].read_delegated(
        actor_principal_id=world["lawyer"].principal_id,
        membership_grant_id=accepted.grant_id,
        membership_version=accepted.version,
        key_grant_id=granted.key_grant_id,
        case_id=case.case_id,
        tenant_id=case.tenant_id,
        resource_id=case.resource_id,
        artifact_kind=ARTIFACT_KIND,
        artifact_revision=REVISION,
        envelope=envelope,
        recipient_session=world["recipient_session"],
    )
    assert opened["data"] == payload
    assert opened["actor_principal_id"] == world["lawyer"].principal_id
    assert opened["canonical_owner_principal_id"] == case.tenant_id
    assert opened["actor_is_encrypted_owner"] is False
    assert opened["artifact_revision"] == REVISION
    assert opened["key_grant_id"] == granted.key_grant_id

    owner_opened = world["grants"].read_as_owner(
        actor_principal_id=world["owner"].principal_id,
        case_id=case.case_id,
        tenant_id=case.tenant_id,
        resource_id=case.resource_id,
        artifact_kind=ARTIFACT_KIND,
        artifact_revision=REVISION,
        envelope=envelope,
        owner_session=world["owner_session"],
    )
    assert owner_opened["data"] == payload
    assert owner_opened["actor_principal_id"] != owner_opened["canonical_owner_principal_id"]
    assert owner_opened["membership"] == "owner"
    assert owner_opened["key_grant_id"] is None


def test_owner_only_denial_impersonation_and_version_stay_closed(tmp_path: Path) -> None:
    world = _world(tmp_path)
    case = world["case"]
    payload = b"owner-only-bytes"
    envelope = _seal(world, payload)
    accepted = _accept(world)
    granted = _issue(world, accepted)

    binding = PrivateArtifactBinding(
        tenant_id=case.tenant_id,
        case_id=case.case_id,
        artifact_kind=ARTIFACT_KIND,
        revision=REVISION,
        principal_id=case.tenant_id,
    )
    lawyer_access = _Access(world["lawyer"].principal_id, case.case_id)
    with pytest.raises(PrivateArtifactBindingError) as mismatch:
        assert_access_matches_binding(lawyer_access, binding)
    assert mismatch.value.reason == "principal_mismatch"
    owner_actor_binding = PrivateArtifactBinding(
        tenant_id=case.tenant_id,
        case_id=case.case_id,
        artifact_kind=ARTIFACT_KIND,
        revision=REVISION,
        principal_id=world["owner"].principal_id,
    )
    key_id, key = world["owner_session"].provider().resolve(binding)
    with pytest.raises(PrivateArtifactIntegrityError) as aad:
        open_private_artifact(envelope, binding=owner_actor_binding, key=key, expected_key_id=key_id)
    assert aad.value.reason == "authentication_failed"

    stale = bytearray(envelope)
    assert stale[4] == 2
    stale[4] = 1
    with pytest.raises(PrivateArtifactIntegrityError) as version:
        open_private_artifact(bytes(stale), binding=binding, key=key, expected_key_id=key_id)
    assert version.value.reason == "unsupported_version"
    with pytest.raises(CaseResourceKeyGrantError) as owner_version:
        world["grants"].read_as_owner(
            actor_principal_id=world["owner"].principal_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            envelope=bytes(stale),
            owner_session=world["owner_session"],
        )
    assert owner_version.value.code == "unsupported_version"
    still = open_private_artifact(envelope, binding=binding, key=key, expected_key_id=key_id)
    assert still == payload

    with pytest.raises(CaseResourceKeyGrantError) as impersonate:
        world["grants"].read_as_owner(
            actor_principal_id=world["owner"].principal_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            envelope=envelope,
            owner_session=world["owner_session"],
            aad_principal_id=world["owner"].principal_id,
        )
    assert impersonate.value.code == "owner_impersonation"
    with pytest.raises(CaseResourceKeyGrantError) as delegate_as_actor:
        world["grants"].read_delegated(
            actor_principal_id=world["lawyer"].principal_id,
            membership_grant_id=accepted.grant_id,
            membership_version=accepted.version,
            key_grant_id=granted.key_grant_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            envelope=envelope,
            recipient_session=world["recipient_session"],
            aad_principal_id=world["lawyer"].principal_id,
        )
    assert delegate_as_actor.value.code == "owner_impersonation"

    with pytest.raises(CaseResourceKeyGrantError) as lawyer_owner:
        world["grants"].read_as_owner(
            actor_principal_id=world["lawyer"].principal_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            envelope=envelope,
            owner_session=world["owner_session"],
        )
    assert lawyer_owner.value.code == "missing_case"
    with pytest.raises(CaseResourceKeyGrantError) as admin_read:
        world["grants"].read_as_owner(
            actor_principal_id=world["admin"].principal_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            envelope=envelope,
            owner_session=world["owner_session"],
        )
    assert admin_read.value.code == "admin_cannot_decrypt"
    with pytest.raises(CaseResourceKeyGrantError) as admin_master:
        world["grants"].decrypt_with_admin_master(master_key=os.urandom(32), envelope=envelope)
    assert admin_master.value.code == "admin_cannot_decrypt"
    with pytest.raises(CaseResourceKeyGrantError) as same_session:
        world["grants"].issue(
            actor_principal_id=world["owner"].principal_id,
            recipient_principal_id=world["lawyer"].principal_id,
            membership_grant_id=accepted.grant_id,
            membership_version=accepted.version,
            case_id=case.case_id,
            resource_id=case.resource_id,
            tenant_id=case.tenant_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            owner_session=world["owner_session"],
            recipient_session=world["owner_session"],
            idempotency_key="impersonated-session",
        )
    assert same_session.value.code == "owner_impersonation"

    with pytest.raises(CaseResourceKeyGrantError) as stranger:
        world["grants"].read_delegated(
            actor_principal_id=world["stranger"].principal_id,
            membership_grant_id=accepted.grant_id,
            membership_version=accepted.version,
            key_grant_id=granted.key_grant_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            envelope=envelope,
            recipient_session=world["recipient_session"],
        )
    assert stranger.value.code == "actor_not_member"
    with pytest.raises(CaseResourceKeyGrantError) as wrong_revision:
        world["grants"].read_delegated(
            actor_principal_id=world["lawyer"].principal_id,
            membership_grant_id=accepted.grant_id,
            membership_version=accepted.version,
            key_grant_id=granted.key_grant_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision="4",
            envelope=envelope,
            recipient_session=world["recipient_session"],
        )
    assert wrong_revision.value.code == "revision_mismatch"
    with pytest.raises(CaseResourceKeyGrantError) as replay:
        _issue(world, accepted, revision="9", key="grant-1")
    assert replay.value.code == "replay_mismatch"

    world["recipient_session"].lock()
    with pytest.raises(CaseResourceKeyGrantError) as locked:
        world["grants"].read_delegated(
            actor_principal_id=world["lawyer"].principal_id,
            membership_grant_id=accepted.grant_id,
            membership_version=accepted.version,
            key_grant_id=granted.key_grant_id,
            case_id=case.case_id,
            tenant_id=case.tenant_id,
            resource_id=case.resource_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            envelope=envelope,
            recipient_session=world["recipient_session"],
        )
    assert locked.value.code == "key_grant_rejected"
    owner_still = world["grants"].read_as_owner(
        actor_principal_id=world["owner"].principal_id,
        case_id=case.case_id,
        tenant_id=case.tenant_id,
        resource_id=case.resource_id,
        artifact_kind=ARTIFACT_KIND,
        artifact_revision=REVISION,
        envelope=envelope,
        owner_session=world["owner_session"],
    )
    assert owner_still["data"] == payload
