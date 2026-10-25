"""Revocation and rotation of collaborative case key grants.

Positive cases recheck an active grant on read, write, download, and late-result
admission, then re-wrap a surviving grant above the cutoff. Negative cases show
that a revoked generation fails those same entries, including after a cold store
and a freshly unlocked session. Already downloaded plaintext and a copied wrap
remain usable outside the store, and the revocation result says so.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from applications.case_directory import CaseDirectory
from applications.case_membership import CaseMembershipStore
from applications.principal_store import PrincipalStore
from integrations.private_collaboration import (
    LIMITATIONS,
    CaseResourceKeyGrantError,
    CaseResourceKeyGrantStore,
)
from integrations.private_storage import (
    PrivateArtifactBinding,
    UserOwnedKeySession,
)

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

ARTIFACT_KIND = "case-note"
REVISION = "4"
ACTIONS = {"case.read", "case.download", "case.message.send"}


def _world(tmp_path: Path):
    store_key = os.urandom(32)
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    counsel = principals.install_server_role(role="lawyer")
    admin = principals.install_server_role(role="operational_admin")
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
        key=store_key,
        key_id="resource-grant-key",
        principals=principals,
        cases=cases,
        memberships=memberships,
    )
    owner_session = UserOwnedKeySession(tmp_path / "owner-keys")
    owner_session.create(protection="passphrase", passphrase="owner-passphrase")
    lawyer_session = UserOwnedKeySession(tmp_path / "lawyer-keys")
    lawyer_session.create(protection="passphrase", passphrase="lawyer-passphrase")
    counsel_session = UserOwnedKeySession(tmp_path / "counsel-keys")
    counsel_session.create(protection="passphrase", passphrase="counsel-passphrase")
    owner_session.ensure_data_key(case.tenant_id, case.case_id)
    return {
        "root": tmp_path,
        "store_key": store_key,
        "principals": principals,
        "cases": cases,
        "memberships": memberships,
        "grants": grants,
        "owner": owner,
        "lawyer": lawyer,
        "counsel": counsel,
        "admin": admin,
        "case": case,
        "owner_session": owner_session,
        "lawyer_session": lawyer_session,
        "counsel_session": counsel_session,
    }


def _accept(world, member, session_name: str, key: str):
    case = world["case"]
    pending = world["memberships"].invite(
        owner_principal_id=world["owner"].principal_id,
        member_principal_id=member.principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions=set(ACTIONS),
        expires_at=1_700_003_600,
        expected_case_revision=case.revision,
        idempotency_key=key,
    )
    accepted = world["memberships"].accept(
        member_principal_id=member.principal_id,
        grant_id=pending.grant_id,
        expected_version=pending.version,
        idempotency_key=key + "-accept",
    )
    granted = world["grants"].issue(
        actor_principal_id=world["owner"].principal_id,
        recipient_principal_id=member.principal_id,
        membership_grant_id=accepted.grant_id,
        membership_version=accepted.version,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        artifact_kind=ARTIFACT_KIND,
        artifact_revision=REVISION,
        owner_session=world["owner_session"],
        recipient_session=world[session_name],
        idempotency_key=key + "-grant",
    )
    return accepted, granted


def _seal(world, payload: bytes) -> bytes:
    case = world["case"]
    binding = PrivateArtifactBinding(
        tenant_id=case.tenant_id,
        case_id=case.case_id,
        artifact_kind=ARTIFACT_KIND,
        revision=REVISION,
        principal_id=case.tenant_id,
    )
    key_id, key = world["owner_session"].provider().resolve(binding)
    from integrations.private_storage import seal_private_artifact

    return seal_private_artifact(payload, binding=binding, key=key, key_id=key_id)


def _delegated(world, member, membership, grant, session_name: str):
    case = world["case"]
    return {
        "actor_principal_id": member.principal_id,
        "membership_grant_id": membership.grant_id,
        "membership_version": membership.version,
        "key_grant_id": grant.key_grant_id,
        "case_id": case.case_id,
        "tenant_id": case.tenant_id,
        "resource_id": case.resource_id,
        "artifact_kind": ARTIFACT_KIND,
        "artifact_revision": REVISION,
        "recipient_session": world[session_name],
    }


def _resume(world) -> CaseResourceKeyGrantStore:
    return CaseResourceKeyGrantStore(
        world["root"] / "key-grants",
        key=world["store_key"],
        key_id="resource-grant-key",
        principals=world["principals"],
        cases=world["cases"],
        memberships=world["memberships"],
    )


def test_active_grant_is_rechecked_then_revoked_under_cutoff(tmp_path: Path) -> None:
    world = _world(tmp_path)
    payload = b"synthetic-collaboration-note"
    envelope = _seal(world, payload)
    lawyer_membership, lawyer_grant = _accept(world, world["lawyer"], "lawyer_session", "lawyer")
    counsel_membership, counsel_grant = _accept(world, world["counsel"], "counsel_session", "counsel")
    assert lawyer_grant.generation == 1
    assert lawyer_grant.status == "active"
    assert counsel_grant.generation == 1
    copied_wrap = {"nonce": lawyer_grant.wrapped_nonce, "ciphertext": lawyer_grant.wrapped_ciphertext}
    lawyer_args = _delegated(world, world["lawyer"], lawyer_membership, lawyer_grant, "lawyer_session")
    counsel_args = _delegated(world, world["counsel"], counsel_membership, counsel_grant, "counsel_session")

    opened = world["grants"].read_delegated(envelope=envelope, **lawyer_args)
    assert opened["data"] == payload
    assert opened["operation"] == "read"
    assert opened["generation"] == 1
    assert LIMITATIONS[0] in opened["limitations"]

    written = world["grants"].write_delegated(plaintext=payload, **lawyer_args)
    assert written["operation"] == "write"
    assert written["envelope"] != envelope
    downloaded = world["grants"].download_delegated(envelope=envelope, **lawyer_args)
    assert downloaded["data"] == payload
    assert downloaded["downloaded_plaintext_erased"] is False
    admitted = world["grants"].admit_late_result(envelope=envelope, prepared_generation=1, **lawyer_args)
    assert admitted["data"] == payload
    assert admitted["operation"] == "late_result"

    with pytest.raises(CaseResourceKeyGrantError) as low_cutoff:
        world["grants"].revoke_and_rotate(
            actor_principal_id=world["owner"].principal_id,
            recipient_principal_id=world["lawyer"].principal_id,
            case_id=world["case"].case_id,
            tenant_id=world["case"].tenant_id,
            resource_id=world["case"].resource_id,
            cutoff=0,
            owner_session=world["owner_session"],
            recipient_sessions={world["counsel"].principal_id: world["counsel_session"]},
            idempotency_key="revoke-lawyer",
        )
    assert low_cutoff.value.code == "cutoff_invalid"

    with pytest.raises(CaseResourceKeyGrantError) as stranger:
        world["grants"].revoke_and_rotate(
            actor_principal_id=world["lawyer"].principal_id,
            recipient_principal_id=world["counsel"].principal_id,
            case_id=world["case"].case_id,
            tenant_id=world["case"].tenant_id,
            resource_id=world["case"].resource_id,
            cutoff=1,
            owner_session=world["owner_session"],
            recipient_sessions={},
            idempotency_key="lawyer-cannot-revoke",
        )
    assert stranger.value.code == "missing_case"

    with pytest.raises(CaseResourceKeyGrantError) as admin:
        world["grants"].revoke_and_rotate(
            actor_principal_id=world["admin"].principal_id,
            recipient_principal_id=world["lawyer"].principal_id,
            case_id=world["case"].case_id,
            tenant_id=world["case"].tenant_id,
            resource_id=world["case"].resource_id,
            cutoff=1,
            owner_session=world["owner_session"],
            idempotency_key="admin-revoke",
        )
    assert admin.value.code == "admin_cannot_decrypt"

    retained_key = world["lawyer_session"].unwrap_granted_resource_key(
        copied_wrap,
        tenant_id=lawyer_grant.tenant_id,
        case_id=lawyer_grant.case_id,
        canonical_principal_id=lawyer_grant.canonical_owner_principal_id,
        revision=lawyer_grant.artifact_revision,
        recipient_principal_id=lawyer_grant.recipient_principal_id,
        artifact_kind=lawyer_grant.artifact_kind,
        resource_id=lawyer_grant.resource_id,
        membership_grant_id=lawyer_grant.membership_grant_id,
        membership_version=lawyer_grant.membership_version,
        data_key_id=lawyer_grant.data_key_id,
        recipient_wrap_key_id=lawyer_grant.recipient_wrap_key_id,
    )
    revoked = world["grants"].revoke_and_rotate(
        actor_principal_id=world["owner"].principal_id,
        recipient_principal_id=world["lawyer"].principal_id,
        case_id=world["case"].case_id,
        tenant_id=world["case"].tenant_id,
        resource_id=world["case"].resource_id,
        cutoff=1,
        owner_session=world["owner_session"],
        recipient_sessions={world["counsel"].principal_id: world["counsel_session"]},
        idempotency_key="revoke-lawyer",
        retained_plaintext=downloaded["data"],
        retained_key=retained_key,
    )
    assert revoked["cutoff"] == 1
    assert revoked["generation"] == 2
    assert revoked["grant_wrap_rotated"] is True
    assert revoked["future_access_revoked"] is True
    assert revoked["downloaded_plaintext_erased"] is False
    assert revoked["downloaded_keys_erased"] is False
    assert revoked["limitation"] == "revocation_cannot_erase_already_downloaded_plaintext_or_keys"
    assert downloaded["data"] == payload
    assert len(retained_key) == 32
    again = world["grants"].revoke_and_rotate(
        actor_principal_id=world["owner"].principal_id,
        recipient_principal_id=world["lawyer"].principal_id,
        case_id=world["case"].case_id,
        tenant_id=world["case"].tenant_id,
        resource_id=world["case"].resource_id,
        cutoff=1,
        owner_session=world["owner_session"],
        recipient_sessions={world["counsel"].principal_id: world["counsel_session"]},
        idempotency_key="revoke-lawyer",
    )
    assert again["generation"] == 2
    assert again["revoked_key_grant_ids"] == revoked["revoked_key_grant_ids"]

    stored = world["grants"].load(lawyer_grant.key_grant_id)
    assert stored.status == "revoked"
    assert stored.wrapped_ciphertext == ""
    assert stored.generation == 1
    survived = world["grants"].load(counsel_grant.key_grant_id)
    assert survived.status == "active"
    assert survived.generation == 2
    assert survived.wrapped_ciphertext != counsel_grant.wrapped_ciphertext

    for call in (
        lambda: world["grants"].read_delegated(envelope=envelope, **lawyer_args),
        lambda: world["grants"].write_delegated(plaintext=payload, **lawyer_args),
        lambda: world["grants"].download_delegated(envelope=envelope, **lawyer_args),
    ):
        with pytest.raises(CaseResourceKeyGrantError) as denied:
            call()
        assert denied.value.code == "grant_revoked"
    with pytest.raises(CaseResourceKeyGrantError) as late:
        world["grants"].admit_late_result(envelope=envelope, prepared_generation=1, **lawyer_args)
    assert late.value.code == "late_result_after_cutoff"

    counsel_open = world["grants"].download_delegated(envelope=envelope, **counsel_args)
    assert counsel_open["data"] == payload
    assert counsel_open["generation"] == 2
    counsel_late = world["grants"].admit_late_result(
        envelope=envelope,
        prepared_generation=2,
        **counsel_args,
    )
    assert counsel_late["data"] == payload
    with pytest.raises(CaseResourceKeyGrantError) as stale:
        world["grants"].admit_late_result(envelope=envelope, prepared_generation=1, **counsel_args)
    assert stale.value.code == "late_result_after_cutoff"

    resumed = _resume(world)
    stale_session = UserOwnedKeySession(tmp_path / "lawyer-keys")
    stale_session.unlock_passphrase("lawyer-passphrase")
    lawyer_args["recipient_session"] = stale_session
    with pytest.raises(CaseResourceKeyGrantError) as cold:
        resumed.download_delegated(envelope=envelope, **lawyer_args)
    assert cold.value.code == "grant_revoked"
    with pytest.raises(CaseResourceKeyGrantError) as replay:
        resumed.issue(
            actor_principal_id=world["owner"].principal_id,
            recipient_principal_id=world["lawyer"].principal_id,
            membership_grant_id=lawyer_membership.grant_id,
            membership_version=lawyer_membership.version,
            case_id=world["case"].case_id,
            resource_id=world["case"].resource_id,
            tenant_id=world["case"].tenant_id,
            artifact_kind=ARTIFACT_KIND,
            artifact_revision=REVISION,
            owner_session=world["owner_session"],
            recipient_session=stale_session,
            idempotency_key="lawyer-grant",
        )
    assert replay.value.code == "grant_revoked"

    still_unwraps = stale_session.unwrap_granted_resource_key(
        copied_wrap,
        tenant_id=lawyer_grant.tenant_id,
        case_id=lawyer_grant.case_id,
        canonical_principal_id=lawyer_grant.canonical_owner_principal_id,
        revision=lawyer_grant.artifact_revision,
        recipient_principal_id=lawyer_grant.recipient_principal_id,
        artifact_kind=lawyer_grant.artifact_kind,
        resource_id=lawyer_grant.resource_id,
        membership_grant_id=lawyer_grant.membership_grant_id,
        membership_version=lawyer_grant.membership_version,
        data_key_id=lawyer_grant.data_key_id,
        recipient_wrap_key_id=lawyer_grant.recipient_wrap_key_id,
    )
    assert still_unwraps == retained_key
    assert downloaded["data"] == payload
