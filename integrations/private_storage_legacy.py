"""Legacy private-storage migration, case deletion, and workflow continuity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .private_storage import (
    DELETION_PHASES,
    DELETION_POLICIES,
    DELETION_SCHEMA,
    DELETION_VERSION,
    LEGACY_HOOK_ARTIFACT_CLASS,
    LEGACY_HOOK_RETENTION,
    PrivateArtifactBinding,
    PrivateArtifactIntegrityError,
    PrivateCryptoCapabilityError,
    PrivateKeyMaterialError,
    PrivatePortabilityError,
    PrivateRevisionError,
    PrivateStorageError,
    _LEGACY_HOOK_SCHEMA,
    _PUBLIC_IPFS_LIMITATION,
    _WORKFLOW_SCHEMA,
    _capture_deletion_plan,
    _classify_head_failure,
    _delete_local_private_bytes,
    _deletion_receipt,
    _inspect_legacy_hook_source,
    _json_bytes,
    _legacy_hook_binding,
    _legacy_hook_keys,
    _legacy_preimage,
    _load_deletion_journal,
    _load_legacy_head,
    _publish_legacy_head,
    _read_nofollow_bytes,
    _refused_deletion_receipt,
    _remove_case_references,
    _request_remote_deletion,
    _require_label,
    _retire_legacy_source,
    _save_deletion_journal,
    _tombstone_path,
    _unpin_managed_replicas,
    _workflow_refusal,
    _write_exclusive,
    _write_json_object,
    assert_access_matches_binding,
    durability_statement,
    load_aesgcm,
    open_private_artifact,
    read_case_tombstone,
    read_private_revision,
    seal_private_artifact,
)

def _legacy_hook_migration(
    source_path: str | Path,
    *,
    source_preimage: str,
    destination: str | Path,
    access: Any,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    revision: str,
    retention_policy: str,
    key: bytes | None,
    key_id: str | None,
    key_provider: InjectedCaseKeyProvider | None,
    commit: bool,
    interrupt_at: str | None,
) -> dict[str, Any]:
    if interrupt_at not in {None, "before_object", "before_head", "before_retire"}:
        raise PrivateStorageError("unknown migration interrupt", code="interrupt_at")
    preimage = _legacy_preimage(source_preimage)
    _require_label(revision)
    if retention_policy not in LEGACY_HOOK_RETENTION:
        raise PrivateKeyMaterialError("retention_policy")
    binding_record = _legacy_hook_binding(
        tenant_id=tenant_id, case_id=case_id, principal_id=principal_id, revision=revision,
    )
    artifact_binding = PrivateArtifactBinding(
        tenant_id=tenant_id,
        case_id=case_id,
        artifact_kind=LEGACY_HOOK_ARTIFACT_CLASS,
        revision=revision,
        principal_id=principal_id,
    )
    assert_access_matches_binding(access, artifact_binding)

    def finish(**kwargs: Any) -> dict[str, Any]:
        return _legacy_hook_receipt(
            revision=revision,
            preimage=preimage,
            binding=binding_record,
            retention_policy=retention_policy,
            **kwargs,
        )

    source = Path(source_path)
    dest = Path(destination)
    if source.is_symlink():
        return finish(status="rejected", code="aliased_source", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=True, last_valid_head_preserved=True, prior_head_present=False,
                      encryption_established=False)
    try:
        source_resolved = source.resolve()
        dest_resolved = dest.resolve() if dest.exists() else dest.absolute()
    except OSError:
        return finish(status="unavailable", code="destination_unavailable", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=True, last_valid_head_preserved=True, prior_head_present=False,
                      encryption_established=False)
    if source_resolved == dest_resolved or dest_resolved in source_resolved.parents or source_resolved in dest_resolved.parents:
        return finish(status="rejected", code="source_destination_overlap", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=True, last_valid_head_preserved=True, prior_head_present=False,
                      encryption_established=False)
    if dest.is_symlink() or (dest.exists() and not dest.is_dir()):
        return finish(status="unavailable", code="destination_unavailable", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=True, last_valid_head_preserved=True, prior_head_present=False,
                      encryption_established=False)
    head_before = _load_legacy_head(dest) if dest.exists() else {"present": False}
    prior = bool(head_before.get("present"))
    inspected = _inspect_legacy_hook_source(source)
    source_existed = source.exists() or source.is_symlink()
    original = inspected.get("data") if inspected.get("ok") else (source.read_bytes() if source.is_file() and not source.is_symlink() else None)

    def preserved() -> bool:
        if original is None:
            return not source.exists()
        if not source.is_file() or source.is_symlink():
            return False
        try:
            return source.read_bytes() == original and source.stat().st_nlink >= 1
        except OSError:
            return False

    if head_before.get("aliased"):
        return finish(status="rejected", code="aliased_source", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=prior,
                      encryption_established=False)
    if not inspected.get("ok"):
        code = str(inspected.get("code") or "source_missing")
        status = "rejected" if code in {"aliased_source", "corrupt_source", "empty_source", "preimage_mismatch"} else "pending"
        if code == "source_missing" and prior and not head_before.get("corrupt"):
            status = "pending"
        return finish(status=status, code=code, encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved() if source_existed or original is not None else True,
                      last_valid_head_preserved=True, prior_head_present=prior, encryption_established=False)
    payload = bytes(inspected["data"])
    if hashlib.sha256(payload).hexdigest() != preimage:
        return finish(status="rejected", code="corrupt_source", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=prior,
                      encryption_established=False)
    if head_before.get("corrupt"):
        return finish(status="rejected", code="corrupt_head", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=True,
                      encryption_established=False)
    try:
        resolved_id, resolved_key = _legacy_hook_keys(
            artifact_binding, key=key, key_id=key_id, key_provider=key_provider,
        )
    except PrivateCryptoCapabilityError:
        return finish(status="unavailable", code="private_crypto_unavailable", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=prior,
                      encryption_established=False)
    except PrivateKeyMaterialError as exc:
        return finish(status="unavailable", code=str(exc.reason or "key_unavailable"), encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=prior,
                      encryption_established=False)

    document = head_before.get("document") if head_before.get("present") else None
    if isinstance(document, dict):
        same_binding = (
            document.get("tenant_id") == tenant_id
            and document.get("case_id") == case_id
            and document.get("principal_id") == principal_id
            and document.get("revision") == revision
            and document.get("artifact_class") == LEGACY_HOOK_ARTIFACT_CLASS
        )
        if not same_binding:
            return finish(status="rejected", code="binding_mismatch", encrypted=False, pending_kind="encryption",
                          verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                          source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=True,
                          encryption_established=False)
        if str(document.get("key_id") or "") != resolved_id:
            return finish(status="rejected", code="wrong_key", encrypted=False, pending_kind="encryption",
                          verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                          source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=True,
                          encryption_established=False)
        try:
            opened = open_private_artifact(
                head_before["envelope"], binding=artifact_binding, key=resolved_key, expected_key_id=resolved_id,
            )
        except PrivateArtifactIntegrityError:
            return finish(status="rejected", code="wrong_key", encrypted=False, pending_kind="encryption",
                          verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                          source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=True,
                          encryption_established=False)
        if opened != payload or str(document.get("source_preimage") or "") != preimage:
            return finish(status="rejected", code="preimage_mismatch", encrypted=False, pending_kind="encryption",
                          verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                          source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=True,
                          encryption_established=False)
        retired = document.get("plaintext_retired") is True and not source.exists()
        if commit and retention_policy == "retire_plaintext_after_verified_commit" and not retired and interrupt_at != "before_retire":
            retired = _retire_legacy_source(source, inspected, payload)
            if retired:
                updated = dict(document)
                updated["plaintext_retired"] = True
                _publish_legacy_head(dest, _json_bytes(updated))
        retirement = "retired" if retired else ("pending" if retention_policy == "retire_plaintext_after_verified_commit" else "retained")
        return finish(
            status="committed" if commit else "preflight",
            code="",
            encrypted=True,
            pending_kind="" if retirement != "pending" else "plaintext_retirement",
            verified_commit=True,
            plaintext_retired=retired,
            plaintext_retirement=retirement,
            source_bytes_preserved=not retired,
            last_valid_head_preserved=True,
            prior_head_present=True,
            encryption_established=True,
        )

    if not commit or interrupt_at == "before_object":
        return finish(
            status="preflight" if not commit else "interrupted",
            code="" if not commit else "interrupted",
            encrypted=False,
            pending_kind="encryption",
            verified_commit=False,
            plaintext_retired=False,
            plaintext_retirement="retained",
            source_bytes_preserved=preserved(),
            last_valid_head_preserved=True,
            prior_head_present=prior,
            encryption_established=False,
        )
    try:
        load_aesgcm()
        envelope = seal_private_artifact(payload, binding=artifact_binding, key=resolved_key, key_id=resolved_id)
        if open_private_artifact(envelope, binding=artifact_binding, key=resolved_key, expected_key_id=resolved_id) != payload:
            raise PrivateArtifactIntegrityError("readback_mismatch")
    except PrivateCryptoCapabilityError:
        return finish(status="unavailable", code="private_crypto_unavailable", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=prior,
                      encryption_established=False)
    digest = hashlib.sha256(envelope).hexdigest()
    object_path = dest / "objects" / f"{digest}.bin"
    if not object_path.exists():
        _write_exclusive(object_path, envelope)
    else:
        existing = _read_nofollow_bytes(object_path)
        if existing != envelope:
            return finish(status="rejected", code="destination_conflict", encrypted=False, pending_kind="encryption",
                          verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                          source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=prior,
                          encryption_established=False)
    if interrupt_at == "before_head":
        return finish(status="interrupted", code="interrupted", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=prior,
                      encryption_established=False)
    head_document = {
        "schema": _LEGACY_HOOK_SCHEMA,
        "schema_version": 1,
        "artifact_class": LEGACY_HOOK_ARTIFACT_CLASS,
        "tenant_id": tenant_id,
        "case_id": case_id,
        "principal_id": principal_id,
        "revision": revision,
        "source_preimage": preimage,
        "ciphertext_sha256": digest,
        "key_id": resolved_id,
        "verified_commit": True,
        "plaintext_retired": False,
    }
    _publish_legacy_head(dest, _json_bytes(head_document))
    reread = _load_legacy_head(dest)
    if reread.get("corrupt") or reread.get("envelope") != envelope:
        return finish(status="rejected", code="readback_mismatch", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=prior,
                      encryption_established=False)
    confirmed = open_private_artifact(reread["envelope"], binding=artifact_binding, key=resolved_key, expected_key_id=resolved_id)
    if confirmed != payload or not preserved():
        return finish(status="rejected", code="readback_mismatch", encrypted=False, pending_kind="encryption",
                      verified_commit=False, plaintext_retired=False, plaintext_retirement="retained",
                      source_bytes_preserved=preserved(), last_valid_head_preserved=True, prior_head_present=True,
                      encryption_established=False)
    retired = False
    if retention_policy == "retire_plaintext_after_verified_commit" and interrupt_at != "before_retire":
        retired = _retire_legacy_source(source, inspected, payload)
        if retired:
            head_document["plaintext_retired"] = True
            _publish_legacy_head(dest, _json_bytes(head_document))
    retirement = "retired" if retired else ("pending" if retention_policy == "retire_plaintext_after_verified_commit" else "retained")
    return finish(
        status="committed",
        code="",
        encrypted=True,
        pending_kind="" if retirement != "pending" else "plaintext_retirement",
        verified_commit=True,
        plaintext_retired=retired,
        plaintext_retirement=retirement,
        source_bytes_preserved=not retired,
        last_valid_head_preserved=True,
        prior_head_present=prior,
        encryption_established=True,
    )


def delete_private_case(
    repository: str | Path,
    session: UserOwnedKeySession | None,
    *,
    tenant_id: str,
    case_id: str,
    policy: str,
    legal_hold: bool = False,
    workspace_required: bool = False,
    providers: Mapping[str, Any] | None = None,
    timeout_seconds: float | None = None,
    crash_at: str | None = None,
) -> dict[str, Any]:
    """Delete one case's private state without touching another case's shared sources.

    ``crash_at`` persists that phase and then raises so a later call can resume.
    A second call after the tombstone is committed is idempotent.
    """

    _require_label(tenant_id)
    _require_label(case_id)
    if policy not in DELETION_POLICIES:
        raise PrivatePortabilityError(
            "Deletion needs an explicit retention policy. Nothing was erased.",
            code="retention_policy",
            actions=DELETION_POLICIES,
        )
    if crash_at not in {None, *DELETION_PHASES}:
        raise PrivateKeyMaterialError("deletion_phase")
    if legal_hold:
        return _refused_deletion_receipt(
            tenant_id=tenant_id,
            case_id=case_id,
            policy=policy,
            code="legal_hold",
            message="Legal hold is an explicit retention need. The case was not deleted.",
        )
    if workspace_required:
        return _refused_deletion_receipt(
            tenant_id=tenant_id,
            case_id=case_id,
            policy=policy,
            code="workspace_required",
            message="The workspace still requires this case. The case was not deleted.",
        )
    existing = read_case_tombstone(repository, tenant_id, case_id)
    journal = _load_deletion_journal(repository, tenant_id, case_id)
    if existing is not None and "tombstoned" in (journal.get("completed") or []):
        journal["tombstone"] = existing
        receipt = _deletion_receipt(journal, idempotent=True, resumed_from=None)
        receipt["tombstone"] = existing
        return receipt
    journal["retention_policy"] = policy
    if not journal.get("plan"):
        journal["plan"] = _capture_deletion_plan(repository, tenant_id, case_id)
        _save_deletion_journal(repository, journal)
    plan = journal["plan"]
    completed = list(journal.get("completed") or [])
    resumed_from = completed[-1] if completed else None
    phases = dict(journal.get("phases") or {})

    def _finish(phase: str, result: Mapping[str, Any]) -> None:
        phases[phase] = dict(result)
        if phase not in completed:
            completed.append(phase)
        journal["completed"] = completed
        journal["phases"] = phases
        _save_deletion_journal(repository, journal)
        if crash_at == phase:
            raise PrivateRevisionInterrupted(phase, _case_scope_token(tenant_id, case_id))

    if "references_removed" not in completed:
        _finish("references_removed", _remove_case_references(repository, plan))
    if "local_deleted" not in completed:
        _finish("local_deleted", _delete_local_private_bytes(repository, tenant_id, case_id, plan))
    if "unpinned" not in completed:
        _finish("unpinned", _unpin_managed_replicas(repository, plan, providers, timeout_seconds))
    if "remote_requested" not in completed:
        _finish("remote_requested", _request_remote_deletion(plan, providers, timeout_seconds))
    if "keys_destroyed" not in completed:
        if policy == "retain_keys":
            key_result = {
                "step": "destroy_case_keys",
                "status": "retained_by_policy",
                "encryption_key_destroyed": False,
                "recovery_path_destroyed": False,
                "master_key_destroyed": False,
            }
        else:
            if session is None:
                raise PrivateKeyMaterialError("key_unavailable")
            destroyed = session.destroy_case_keys(tenant_id, case_id)
            key_result = {
                "step": "destroy_case_keys",
                "status": "destroyed",
                "encryption_key_destroyed": True,
                "recovery_path_destroyed": True,
                "master_key_destroyed": False,
                "other_cases_retained": True,
                "data_key_ids": list(destroyed.get("data_key_ids") or []),
            }
        _finish("keys_destroyed", key_result)
    if "tombstoned" not in completed:
        remote = dict(phases.get("remote_requested") or {})
        keys = dict(phases.get("keys_destroyed") or {})
        tombstone = {
            "schema": DELETION_SCHEMA,
            "schema_version": DELETION_VERSION,
            "status": "tombstoned",
            "tenant_id": tenant_id,
            "case_id": case_id,
            "case_keys_destroyed": bool(keys.get("encryption_key_destroyed")),
            "universal_erasure": False,
            "public_ipfs_erased": False,
            "external_replica_limitation": _PUBLIC_IPFS_LIMITATION,
            "residual_replicas": list(remote.get("residual_replicas") or []),
            "pending_remote_removals": list(remote.get("pending") or []),
            "unreachable_remote_removals": list(remote.get("unreachable") or []),
        }
        _write_json_object(_tombstone_path(repository, tenant_id, case_id), tombstone)
        journal["tombstone"] = tombstone
        _finish("tombstoned", {"step": "tombstone", "status": "tombstoned"})
    receipt = _deletion_receipt(journal, idempotent=False, resumed_from=resumed_from)
    if resumed_from is not None:
        receipt["idempotent"] = False
        receipt["resumed"] = True
    else:
        receipt["resumed"] = False
    receipt["tombstone"] = read_case_tombstone(repository, tenant_id, case_id)
    return receipt


def reconstruct_workflow_continuity(
    repository: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes | None,
    key_id: str | None,
    browser_cache: Any = None,
    key_resolver: Callable[[str], bytes | None] | None = None,
) -> dict[str, Any]:
    """Rebuild services and the wallet descriptor from the encrypted head.

    ``browser_cache`` is discarded. A missing key, a key id that is not the
    envelope's key id, or a head that fails authentication returns no workflow
    plaintext and does not create a case.
    """

    del browser_cache
    root = Path(repository)
    if key is None or not key_id:
        return _workflow_refusal("missing_key")
    try:
        opened = read_private_revision(
            root,
            tenant_id=tenant_id,
            case_id=case_id,
            principal_id=principal_id,
            key=key,
            key_id=key_id,
            key_resolver=key_resolver,
        )
    except PrivateKeyMaterialError:
        return _workflow_refusal("missing_key")
    except PrivateArtifactIntegrityError:
        return _workflow_refusal(_classify_head_failure(root, key_id))
    except PrivateRevisionError as exc:
        code = str(exc.code or "")
        if code in {"corrupt_manifest", "journal_corrupt"}:
            return _workflow_refusal("tampered_head")
        if code == "authentication_failed":
            return _workflow_refusal(_classify_head_failure(root, key_id))
        if code in {"recovery_required", "missing_object"}:
            return _workflow_refusal("recovery_required")
        return _workflow_refusal("unproven")
    if opened is None:
        return _workflow_refusal("missing_store")
    try:
        session = json.loads(opened["session"])
        facts = json.loads(opened["fact_graph"])
        proof = json.loads(opened["proof"])
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError):
        return _workflow_refusal("tampered_head")
    if not isinstance(session, dict) or session.get("schema") != _WORKFLOW_SCHEMA:
        return _workflow_refusal("tampered_head")
    wallet = session.get("wallet") if isinstance(session.get("wallet"), dict) else None
    services = session.get("services") if isinstance(session.get("services"), list) else None
    if wallet is None or services is None or wallet.get("key_id") != key_id or wallet.get("case_id") != case_id:
        return _workflow_refusal("tampered_head")
    if not isinstance(facts, dict) or not isinstance(proof, dict):
        return _workflow_refusal("tampered_head")
    rebuilt = []
    for item in services:
        if not isinstance(item, dict) or not item.get("service_id"):
            return _workflow_refusal("tampered_head")
        rebuilt.append({
            "service_id": item["service_id"],
            "kind": item.get("kind"),
            "label": item.get("label"),
            "source": "encrypted_store",
        })
    draft = proof.get("draft") if isinstance(proof.get("draft"), dict) else None
    return {
        "schema": _WORKFLOW_SCHEMA,
        "resumed": True,
        "code": "resumed",
        "revision": opened["revision"],
        "reconstructed_from_browser_cache": False,
        "browser_cache_ignored": True,
        "empty_case_created": False,
        "services": rebuilt,
        "wallet": {
            "wallet_id": wallet.get("wallet_id"),
            "key_id": wallet.get("key_id"),
            "protection": wallet.get("protection"),
            "case_id": case_id,
            "source": "encrypted_store",
        },
        "pending_questions": list(facts.get("pending_questions") or []),
        "evidence_annotations": list(facts.get("evidence_annotations") or []),
        "evidence_links": list(facts.get("evidence_links") or []),
        "source_context": facts.get("source_context"),
        "draft": draft,
        "correspondence": list(proof.get("correspondence") or []),
        "durability": durability_statement(local_readback=True),
    }
