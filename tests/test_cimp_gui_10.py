"""Durable case membership grants.

Positive cases persist an owner invite, accept it, and authorize only the
explicit actions under a stable grant id, expiry, and version. Negative cases
reject caller-minted grants, cross-case and cross-tenant use, invite replay
with a different payload, concurrent scope edits, pending and declined
memberships, and removal while a request is still open.
"""

from __future__ import annotations

import os
from pathlib import Path
import threading

import pytest

from applications.case_directory import CaseDirectory
from applications.case_membership import (
    SCHEMA_VERSION,
    CaseMembershipError,
    CaseMembershipStore,
)
from applications.principal_store import PrincipalStore

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]


def _world(tmp_path: Path, *, now: int = 1_700_000_000):
    clock = {"now": now}
    principals = PrincipalStore(tmp_path / "principals", key=os.urandom(32), key_id="principal-key")
    cases = CaseDirectory(tmp_path / "cases", key=os.urandom(32), key_id="case-key")
    owner = principals.register_from_request({})
    lawyer = principals.install_server_role(role="lawyer")
    admin = principals.install_server_role(role="operational_admin")
    stranger = principals.register_from_request({})
    case = cases.create_case(actor_principal_id=owner.principal_id)
    other = cases.create_case(actor_principal_id=stranger.principal_id)
    membership_key = os.urandom(32)
    store = CaseMembershipStore(
        tmp_path / "memberships",
        key=membership_key,
        key_id="membership-key",
        principals=principals,
        cases=cases,
        clock=lambda: clock["now"],
    )
    return store, membership_key, principals, cases, owner, lawyer, admin, stranger, case, other, clock


def _invite(store, owner, lawyer, case, *, key: str = "invite-1", actions=None, expires_at: int = 1_700_003_600):
    return store.invite(
        owner_principal_id=owner.principal_id,
        member_principal_id=lawyer.principal_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        tenant_id=case.tenant_id,
        actions=set(actions or {"case.read", "case.review"}),
        expires_at=expires_at,
        expected_case_revision=case.revision,
        idempotency_key=key,
    )


def test_owner_grant_is_stable_and_caller_flags_cannot_mint(tmp_path: Path) -> None:
    store, membership_key, principals, _cases, owner, lawyer, admin, stranger, case, other, _clock = _world(tmp_path)
    with pytest.raises(CaseMembershipError) as minted:
        store.invite_from_request({
            "actor_principal_id": lawyer.principal_id,
            "owner_principal_id": owner.principal_id,
            "tenant_id": case.tenant_id,
            "case_id": case.case_id,
            "resource_id": case.resource_id,
            "actions": ["case.read"],
            "status": "accepted",
            "is_member": True,
            "trusted_local": True,
            "expires_at": 1_700_003_600,
            "version": 1,
        })
    assert minted.value.code == "request_cannot_mint_grant"
    with pytest.raises(CaseMembershipError) as bare:
        store.invite_from_request({
            "actor_principal_id": owner.principal_id,
            "case_id": case.case_id,
        })
    assert bare.value.code == "request_cannot_mint_grant"
    assert store.recover() == ()

    with pytest.raises(CaseMembershipError) as not_owner:
        store.invite(
            owner_principal_id=admin.principal_id,
            member_principal_id=lawyer.principal_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            tenant_id=case.tenant_id,
            actions={"case.read"},
            expires_at=1_700_003_600,
            expected_case_revision=case.revision,
            idempotency_key="admin-invite",
        )
    assert not_owner.value.code == "missing_case"
    with pytest.raises(CaseMembershipError) as not_lawyer:
        _invite(store, owner, stranger, case, key="stranger")
    assert not_lawyer.value.code == "lawyer_role_required"
    with pytest.raises(CaseMembershipError) as owner_action:
        _invite(store, owner, lawyer, case, key="too-wide", actions={"case.update"})
    assert owner_action.value.code == "action_not_permitted"

    pending = _invite(store, owner, lawyer, case)
    replay = _invite(store, owner, lawyer, case)
    assert replay.grant_id == pending.grant_id
    assert replay.version == 1
    assert replay.status == "pending"
    assert replay.actions == ("case.read", "case.review")
    assert replay.expires_at == 1_700_003_600
    assert pending.public_view()["schema_version"] == SCHEMA_VERSION
    with pytest.raises(CaseMembershipError) as changed:
        _invite(store, owner, lawyer, case, actions={"case.read"})
    assert changed.value.code == "replay_mismatch"

    with pytest.raises(CaseMembershipError) as cross_case:
        store.invite(
            owner_principal_id=owner.principal_id,
            member_principal_id=lawyer.principal_id,
            case_id=other.case_id,
            resource_id=other.resource_id,
            tenant_id=other.tenant_id,
            actions={"case.read"},
            expires_at=1_700_003_600,
            expected_case_revision=other.revision,
            idempotency_key="other-case",
        )
    assert cross_case.value.code == "missing_case"
    with pytest.raises(CaseMembershipError) as cross_tenant:
        store.invite(
            owner_principal_id=owner.principal_id,
            member_principal_id=lawyer.principal_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            tenant_id=other.tenant_id,
            actions={"case.read"},
            expires_at=1_700_003_600,
            expected_case_revision=case.revision,
            idempotency_key="other-tenant",
        )
    assert cross_tenant.value.code == "tenant_mismatch"

    accepted = store.accept(
        member_principal_id=lawyer.principal_id,
        grant_id=pending.grant_id,
        expected_version=pending.version,
        idempotency_key="accept-1",
    )
    again = store.accept(
        member_principal_id=lawyer.principal_id,
        grant_id=pending.grant_id,
        expected_version=accepted.version,
        idempotency_key="accept-1",
    )
    assert again == accepted
    assert accepted.grant_id == pending.grant_id
    assert accepted.version == 2
    assert accepted.status == "accepted"
    with pytest.raises(CaseMembershipError) as second_decision:
        store.decline(
            member_principal_id=lawyer.principal_id,
            grant_id=pending.grant_id,
            expected_version=accepted.version,
            idempotency_key="decline-later",
        )
    assert second_decision.value.code == "membership_replay"

    decision = store.authorize(
        actor_principal_id=lawyer.principal_id,
        grant_id=accepted.grant_id,
        tenant_id=case.tenant_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        action="case.review",
        expected_version=accepted.version,
    )
    assert decision.permits_case_content is True
    assert decision.grant_id == accepted.grant_id
    assert decision.version == accepted.version
    assert decision.expires_at == accepted.expires_at
    assert decision.actor_principal_id == lawyer.principal_id
    assert decision.canonical_owner_principal_id == case.tenant_id
    assert decision.actor_is_encrypted_owner is False
    with pytest.raises(CaseMembershipError) as update_denied:
        store.authorize(
            actor_principal_id=lawyer.principal_id,
            grant_id=accepted.grant_id,
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            action="case.update",
            expected_version=accepted.version,
        )
    assert update_denied.value.code == "action_not_permitted"
    with pytest.raises(CaseMembershipError) as other_case_use:
        store.authorize(
            actor_principal_id=lawyer.principal_id,
            grant_id=accepted.grant_id,
            tenant_id=case.tenant_id,
            case_id=other.case_id,
            resource_id=other.resource_id,
            action="case.read",
            expected_version=accepted.version,
        )
    assert other_case_use.value.code == "case_mismatch"
    with pytest.raises(CaseMembershipError) as other_tenant_use:
        store.authorize(
            actor_principal_id=lawyer.principal_id,
            grant_id=accepted.grant_id,
            tenant_id=other.tenant_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            action="case.read",
            expected_version=accepted.version,
        )
    assert other_tenant_use.value.code == "tenant_mismatch"

    reopened = CaseMembershipStore(
        tmp_path / "memberships",
        key=membership_key,
        key_id="membership-key",
        principals=principals,
        cases=_cases,
        clock=lambda: 1_700_000_000,
    )
    loaded = reopened.load(accepted.grant_id)
    assert loaded.grant_id == accepted.grant_id
    assert loaded.version == accepted.version
    assert loaded.status == "accepted"
    assert {item.principal_id for item in principals.recover()} >= {
        owner.principal_id,
        lawyer.principal_id,
    }


def test_pending_declined_expiry_and_removal_while_request_is_open(tmp_path: Path) -> None:
    store, _membership_key, _principals, _cases, owner, lawyer, _admin, _stranger, case, _other, clock = _world(tmp_path)
    pending = _invite(store, owner, lawyer, case, key="pending")
    with pytest.raises(CaseMembershipError) as still_pending:
        store.authorize(
            actor_principal_id=lawyer.principal_id,
            grant_id=pending.grant_id,
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            action="case.read",
            expected_version=pending.version,
        )
    assert still_pending.value.code == "membership_pending"
    withdrawn = store.remove(
        owner_principal_id=owner.principal_id,
        grant_id=pending.grant_id,
        expected_version=pending.version,
    )
    assert withdrawn.grant_id == pending.grant_id
    assert withdrawn.version == pending.version + 1
    assert withdrawn.status == "removed"
    with pytest.raises(CaseMembershipError) as accept_removed:
        store.accept(
            member_principal_id=lawyer.principal_id,
            grant_id=pending.grant_id,
            expected_version=withdrawn.version,
            idempotency_key="too-late",
        )
    assert accept_removed.value.code == "membership_removed"

    declined_grant = _invite(store, owner, lawyer, case, key="decline-me")
    declined = store.decline(
        member_principal_id=lawyer.principal_id,
        grant_id=declined_grant.grant_id,
        expected_version=declined_grant.version,
        idempotency_key="decline-1",
    )
    assert declined.status == "declined"
    assert declined.grant_id == declined_grant.grant_id
    with pytest.raises(CaseMembershipError) as use_declined:
        store.authorize(
            actor_principal_id=lawyer.principal_id,
            grant_id=declined.grant_id,
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            action="case.read",
            expected_version=declined.version,
        )
    assert use_declined.value.code == "membership_declined"

    live = _invite(store, owner, lawyer, case, key="live", expires_at=1_700_000_100)
    accepted = store.accept(
        member_principal_id=lawyer.principal_id,
        grant_id=live.grant_id,
        expected_version=live.version,
        idempotency_key="accept-live",
    )
    ticket = store.begin_request(
        actor_principal_id=lawyer.principal_id,
        grant_id=accepted.grant_id,
        tenant_id=case.tenant_id,
        case_id=case.case_id,
        resource_id=case.resource_id,
        action="case.read",
        expected_version=accepted.version,
        request_id="request-open-1",
    )
    assert ticket.grant_id == accepted.grant_id
    assert ticket.grant_version == accepted.version
    removed = store.remove(
        owner_principal_id=owner.principal_id,
        grant_id=accepted.grant_id,
        expected_version=accepted.version,
    )
    assert removed.status == "removed"
    assert removed.grant_id == accepted.grant_id
    assert any(item.request_id == ticket.request_id for item in removed.open_requests)
    with pytest.raises(CaseMembershipError) as finished:
        store.finish_request(ticket)
    assert finished.value.code == "membership_removed"
    with pytest.raises(CaseMembershipError) as after_removal:
        store.authorize(
            actor_principal_id=lawyer.principal_id,
            grant_id=accepted.grant_id,
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            action="case.read",
            expected_version=removed.version,
        )
    assert after_removal.value.code == "membership_removed"

    expiring = _invite(store, owner, lawyer, case, key="expires", expires_at=1_700_000_050)
    accepted_expiring = store.accept(
        member_principal_id=lawyer.principal_id,
        grant_id=expiring.grant_id,
        expected_version=expiring.version,
        idempotency_key="accept-expiring",
    )
    clock["now"] = accepted_expiring.expires_at
    with pytest.raises(CaseMembershipError) as expired:
        store.authorize(
            actor_principal_id=lawyer.principal_id,
            grant_id=accepted_expiring.grant_id,
            tenant_id=case.tenant_id,
            case_id=case.case_id,
            resource_id=case.resource_id,
            action="case.read",
            expected_version=accepted_expiring.version,
        )
    assert expired.value.code == "grant_expired"


def test_concurrent_scope_edits_conflict_on_version(tmp_path: Path) -> None:
    store, _membership_key, _principals, _cases, owner, lawyer, _admin, _stranger, case, _other, _clock = _world(tmp_path)
    pending = _invite(store, owner, lawyer, case, key="race", actions={"case.read"})
    barrier = threading.Barrier(2)
    results: list[object] = []

    def edit(actions: set[str], expires_at: int) -> None:
        barrier.wait()
        try:
            updated = store.update_scope(
                owner_principal_id=owner.principal_id,
                grant_id=pending.grant_id,
                expected_version=pending.version,
                actions=actions,
                expires_at=expires_at,
            )
            results.append(updated)
        except CaseMembershipError as exc:
            results.append(exc)

    first = threading.Thread(target=edit, args=({"case.read", "case.review"}, 1_700_004_000))
    second = threading.Thread(target=edit, args=({"case.download"}, 1_700_005_000))
    first.start()
    second.start()
    first.join()
    second.join()
    winners = [item for item in results if not isinstance(item, CaseMembershipError)]
    losers = [item for item in results if isinstance(item, CaseMembershipError)]
    assert len(winners) == 1
    assert len(losers) == 1
    assert losers[0].code == "revision_conflict"
    assert winners[0].grant_id == pending.grant_id
    assert winners[0].version == pending.version + 1
    assert winners[0].status == "pending"
    loaded = store.load(pending.grant_id)
    assert loaded == winners[0]
    with pytest.raises(CaseMembershipError) as stale:
        store.update_scope(
            owner_principal_id=owner.principal_id,
            grant_id=pending.grant_id,
            expected_version=pending.version,
            actions={"case.message.send"},
        )
    assert stale.value.code == "revision_conflict"
