"""Encrypted workspace import, restore, and private revision transfer.

These operations move ciphertext between a workspace and a recovery archive
or publish a sealed revision. Key derivation, wrapping, revocation, and
recovery proofs stay in the private storage owner.
"""

from __future__ import annotations

import json
import uuid
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Callable, Mapping

from .private_storage import (
    PrivateArtifactBindingError,
    PrivateArtifactIntegrityError,
    PrivateKeyLockedError,
    PrivatePortabilityError,
    PrivateRevisionError,
    PrivateRevisionInterrupted,
    PrivateStorageError,
    RevisionPublication,
    UNRECOVERED_KEY_EXPLANATION,
    UserOwnedKeySession,
    _PORTABILITY_LOG,
    _REVISION_SCHEMA,
    _ReceiptWriter,
    _WORKSPACE_CATALOG,
    _WORKSPACE_FRAME,
    _WORKSPACE_OWNER,
    _WORKSPACE_PENDING,
    _acquire_lock,
    _apply_intent,
    _assert_workspace_owner,
    _authenticate_intent,
    _authenticate_recovery_journal,
    _authenticate_revision_owner,
    _bounded_provider_call,
    _head_record,
    _identity_args,
    _intent_document,
    _json_bytes,
    _load_portability_manifest,
    _load_wal,
    _manifest_bytes,
    _open_head,
    _open_manifest,
    _open_workspace_frame,
    _process_lock,
    _read_exact,
    _read_json_file,
    _recovery_status,
    _reject_tombstoned_case,
    _release_lock,
    _replica_digest,
    _require_committed_revision,
    _require_label,
    _seal_role,
    _store_object,
    _wal_identity,
    _workspace_identity,
    _workspace_ledger,
    _write_workspace_bytes,
    inspect_revision_journal,
    read_private_workspace_generation,
)

def import_encrypted_workspace(
    repository: str | Path,
    export_dir: str | Path,
    recovery_path: str | Path,
    store_dir: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    recovery_passphrase: str,
    store_passphrase: str | None = None,
) -> dict[str, Any]:
    """Restore an archive into a workspace. Failures do not reset existing ciphertext."""

    _require_label(tenant_id)
    _require_label(case_id)
    _require_label(principal_id)
    _reject_tombstoned_case(repository, tenant_id, case_id)
    recovery_file = Path(recovery_path)
    if not recovery_file.is_file():
        raise PrivatePortabilityError(
            "Recovery material is missing, so the encryption key is unrecovered. " + UNRECOVERED_KEY_EXPLANATION,
            code="recovery_key_missing",
            actions=("recovery_import", "retry_with_recovery_file"),
        )
    manifest = _load_portability_manifest(Path(export_dir))
    if manifest.get("tenant_id") != tenant_id or manifest.get("case_id") != case_id or manifest.get("principal_id") != principal_id:
        raise PrivateArtifactBindingError("foreign_case")
    frame_name = str(manifest.get("ciphertext") or "")
    if frame_name != "ciphertext.frame":
        raise PrivatePortabilityError(
            "The archive ciphertext name is not the versioned frame. Nothing was restored.",
            code="corrupt_manifest",
            actions=("export_retry",),
        )
    frame = _read_exact(Path(export_dir) / frame_name)
    if frame is None or _replica_digest(frame) != manifest.get("ciphertext_sha256"):
        raise PrivatePortabilityError(
            "The ciphertext archive does not match its manifest. Encrypted state was not reset.",
            code="readback_mismatch",
            actions=("export_retry",),
        )
    session = UserOwnedKeySession(store_dir)
    try:
        session.import_recovery(
            recovery_file.read_bytes(),
            tenant_id=tenant_id,
            case_id=case_id,
            recovery_passphrase=recovery_passphrase,
            store_passphrase=store_passphrase if store_passphrase is not None else recovery_passphrase,
        )
    except PrivateArtifactIntegrityError as exc:
        raise PrivatePortabilityError(
            "The recovery passphrase did not authenticate. " + UNRECOVERED_KEY_EXPLANATION,
            code="authentication_failed",
            actions=("retry_passphrase", "recovery_import"),
        ) from exc
    except PrivateKeyLockedError:
        raise
    key_id = str(manifest.get("data_key_id") or "")
    key = session.lookup_data_key(tenant_id, case_id, key_id)
    if key is None:
        raise PrivatePortabilityError(
            "The recovery file did not provide the archive data key. " + UNRECOVERED_KEY_EXPLANATION,
            code="recovery_key_missing",
            actions=("recovery_import",),
        )
    try:
        opened = _open_workspace_frame(
            frame,
            tenant_id=tenant_id,
            case_id=case_id,
            principal_id=principal_id,
            key=key,
            key_id=key_id,
        )
    except PrivateStorageError as exc:
        raise PrivatePortabilityError(
            "The archive did not open with the recovered key. " + UNRECOVERED_KEY_EXPLANATION,
            code="authentication_failed",
            actions=("recovery_import",),
        ) from exc
    if opened["revision"] != manifest.get("revision"):
        raise PrivatePortabilityError(
            "The opened revision does not match the manifest. The destination workspace was not replaced.",
            code="revision_mismatch",
            actions=("export_retry",),
        )
    ledger = _workspace_ledger(repository)
    identity = _workspace_identity(tenant_id, case_id, principal_id, key_id)
    _assert_workspace_owner(ledger, identity)
    if _read_json_file(ledger / _WORKSPACE_OWNER) is None:
        _write_workspace_bytes(ledger, _WORKSPACE_OWNER, _json_bytes(identity))
    catalog = {
        "digest": _replica_digest(frame),
        "version": opened["revision"],
        "revision": opened["revision"],
        "desired": 1,
        "minimum": 1,
        "mode": "local_private",
        "providers": [],
    }
    _write_workspace_bytes(ledger, _WORKSPACE_FRAME, frame)
    _write_workspace_bytes(ledger, _WORKSPACE_CATALOG, _json_bytes(catalog))
    restored = read_private_workspace_generation(
        repository,
        session,
        tenant_id=tenant_id,
        case_id=case_id,
        principal_id=principal_id,
    )
    _PORTABILITY_LOG.info("imported ciphertext archive with a separate recovery file")
    restored.update({
        "status": "imported",
        "code": "imported",
        "operation": "import",
        "manifest_version": int(manifest.get("manifest_version") or 0),
        "imported": True,
        "keys_reconstructed": False,
        "data_reset": False,
        "unwrapped_master_included": False,
        "recovery_separated": True,
        "message": "Restored the case, fact graph, and proof revision from the ciphertext archive.",
    })
    return restored

def restore_encrypted_workspace(
    repository: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes,
    key_id: str,
    providers: Mapping[str, Any] | None = None,
    timeout_seconds: float | None = None,
    clock: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Open the local primary, or repair it from a verified ciphertext replica."""

    del clock
    _reject_tombstoned_case(repository, tenant_id, case_id)
    ledger = _workspace_ledger(repository)
    identity = _workspace_identity(tenant_id, case_id, principal_id, key_id)
    _assert_workspace_owner(ledger, identity)
    options = {
        "tenant_id": tenant_id,
        "case_id": case_id,
        "principal_id": principal_id,
        "key": key,
        "key_id": key_id,
    }
    lock = _process_lock(ledger)
    with lock:
        descriptor = _acquire_lock(ledger)
        try:
            _assert_workspace_owner(ledger, identity)
            local = _read_exact(ledger / _WORKSPACE_FRAME)
            catalog_bytes = _read_exact(ledger / _WORKSPACE_CATALOG) or b""
            catalog = _read_json_file(ledger / _WORKSPACE_CATALOG)
            digest_matches = local is not None and (catalog is None or _replica_digest(local) == catalog.get("digest"))
            interrupted_catalog = None
            if local is not None and not digest_matches:
                intent = _read_json_file(ledger / _WORKSPACE_PENDING) or {}
                following = intent.get("catalog")
                if (isinstance(following, dict)
                        and intent.get("previous_catalog_sha256") == _replica_digest(catalog_bytes)
                        and following.get("digest") == _replica_digest(local)):
                    interrupted_catalog = following
            if digest_matches or interrupted_catalog is not None:
                opened = _open_workspace_frame(local, **options)
                if interrupted_catalog is not None:
                    if opened["revision"] != interrupted_catalog.get("version"):
                        raise PrivateStorageError("replica publication version mismatch", code="readback_mismatch")
                    _write_workspace_bytes(ledger, _WORKSPACE_CATALOG,
                                           json.dumps(interrupted_catalog, sort_keys=True, separators=(",", ":")).encode("utf-8"))
                    catalog = interrupted_catalog
                opened["source"] = "local"
                opened["status"] = "ready"
                return opened
        finally:
            _release_lock(descriptor)
    if not catalog or not catalog.get("digest") or not catalog.get("version"):
        raise PrivateStorageError("verified replica unavailable", code="replica_unavailable")
    digest = str(catalog["digest"])
    version = str(catalog["version"])
    timed_out = False
    for provider in (providers or {}).values():
        loaded = _bounded_provider_call(provider.readback, timeout_seconds, digest=digest, version=version)
        if not isinstance(loaded, Mapping):
            continue
        if loaded.get("error_category") == "timeout" or loaded.get("status") == "timeout":
            timed_out = True
            continue
        remote = loaded.get("frame")
        if loaded.get("status") != "available" or loaded.get("version") != version:
            continue
        if not isinstance(remote, (bytes, bytearray)) or _replica_digest(bytes(remote)) != digest:
            continue
        frame = bytes(remote)
        try:
            opened = _open_workspace_frame(frame, **options)
        except PrivateStorageError:
            continue
        lock = _process_lock(ledger)
        lock.acquire()
        descriptor = None
        try:
            descriptor = _acquire_lock(ledger)
            _assert_workspace_owner(ledger, identity)
            current_catalog = _read_json_file(ledger / _WORKSPACE_CATALOG)
            if current_catalog != catalog:
                raise PrivateStorageError("replica revision changed during restore", code="revision_conflict")
            _write_workspace_bytes(ledger, _WORKSPACE_FRAME, frame)
        finally:
            if descriptor is not None:
                _release_lock(descriptor)
            lock.release()
        opened["source"] = "replica"
        opened["status"] = "ready"
        opened["verified_replica_count"] = 1
        return opened
    if timed_out:
        raise PrivateStorageError("replica provider timed out", code="replica_timeout")
    raise PrivateStorageError("verified replica unavailable", code="replica_unavailable")

def commit_private_revision(
    repository: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes,
    key_id: str,
    expected_revision: str | None,
    session: bytes,
    fact_graph: bytes,
    proof: bytes,
    transaction_id: str | None = None,
    effect_id: str | None = None,
    crash_injector: Callable[..., Any] | None = None,
    writer: Any | None = None,
    fsync_file: Callable[[int], None] | None = None,
    fsync_directory: Callable[[int], None] | None = None,
    before_publish: Callable[[], Any] | None = None,
    key_resolver: Callable[[str], bytes | None] | None = None,
    publication_scope: Callable[[], Any] | None = None,
) -> RevisionPublication:
    """Publish one answer revision across session, fact graph, and proof.

    Objects are sealed first. The visible head changes only inside the effect,
    after the intent is durable. ``network_pinned`` stays false.

    ``before_publish`` is a trusted in-process late admission check. It runs
    after authenticated encryption and head staging/fsync, inside the revision
    CAS effect immediately before replacing the visible head. A refusal raises through the normal terminal
    WAL abort path; recovery cannot replay that refused transaction. Readers
    and key/session reproofs may be used by the callback, but it must not start
    another revision write under this same lock.
    """

    if before_publish is not None and not callable(before_publish):
        raise TypeError("before_publish must be a trusted callable")
    if publication_scope is not None and not callable(publication_scope):
        raise TypeError("publication_scope must be a trusted scope factory")
    wal = _load_wal()
    root = Path(repository)
    transaction_id, effect_id = _identity_args(transaction_id, effect_id)
    process_lock = _process_lock(root)
    process_lock.acquire()
    lock = None
    coordinator = None
    inner = None
    owns_writer = writer is None
    try:
        issue = inspect_revision_journal(root) if root.exists() else None
        if issue:
            raise PrivateRevisionError(
                f"revision journal is corrupt ({issue}); original bytes were preserved",
                code="journal_corrupt",
                state="recoverable",
            )
        lock = _acquire_lock(root)
        expected = "0" if expected_revision in {None, ""} else str(expected_revision)
        _authenticate_revision_owner(root, tenant_id=tenant_id, case_id=case_id,
            principal_id=principal_id, key=key, key_id=key_id, create=True,
            fsync_file=fsync_file, fsync_directory=fsync_directory, key_resolver=key_resolver)
        head_raw, recorded_revision = _head_record(root)
        current = recorded_revision or "0"
        if current in {"",}:
            current = "0"
        if current != expected:
            raise PrivateRevisionError(
                "stale revision",
                code="revision_conflict",
                state="conflict",
            )
        if expected != "0":
            current_manifest = _open_manifest(
                head_raw or b"",
                tenant_id=tenant_id,
                case_id=case_id,
                principal_id=principal_id,
                revision=expected,
                key=key,
                key_id=key_id,
                key_resolver=key_resolver,
            )
            _require_committed_revision(root, current_manifest, tenant_id=tenant_id,
                case_id=case_id, principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
            if current_manifest.get("effect_id") == effect_id and current_manifest.get("transaction_id") == transaction_id:
                return RevisionPublication(
                    True, "committed", transaction_id, effect_id, expected,
                    wal["WALAcknowledgementMode"].WAL_FSYNC_PARENT.value, 0,
                )
        else:
            if head_raw not in {None, b""}:
                raise PrivateRevisionError("unexpected head", code="revision_conflict", state="conflict")
        _recovery_status(root, options=dict(tenant_id=tenant_id, case_id=case_id,
            principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver), phase="pending",
            fsync_file=fsync_file, fsync_directory=fsync_directory)
        next_revision = str(int(expected) + 1) if expected.isdigit() else uuid.uuid4().hex
        sealed = {}
        for role, payload in (("session", session), ("fact_graph", fact_graph), ("proof", proof)):
            sealed[role] = _seal_role(
                payload,
                tenant_id=tenant_id,
                case_id=case_id,
                principal_id=principal_id,
                kind=role,
                revision=next_revision,
                key=key,
                key_id=key_id,
            )
        previous_head_ref = ""
        if head_raw:
            previous_head_ref = _store_object(root, head_raw, fsync_file=fsync_file, fsync_directory=fsync_directory)
        object_refs = {
            role: _store_object(root, blob, fsync_file=fsync_file, fsync_directory=fsync_directory)
            for role, blob in sealed.items()
        }
        manifest = {
            "schema": _REVISION_SCHEMA,
            "revision": next_revision,
            "parent_revision": expected,
            "transaction_id": transaction_id,
            "effect_id": effect_id,
            "objects": object_refs,
        }
        manifest_envelope = _seal_role(
            _manifest_bytes(manifest),
            tenant_id=tenant_id,
            case_id=case_id,
            principal_id=principal_id,
            kind="revision-manifest",
            revision=next_revision,
            key=key,
            key_id=key_id,
        )
        manifest_ref = _store_object(
            root, manifest_envelope, fsync_file=fsync_file, fsync_directory=fsync_directory,
        )
        wal_transaction_id = _wal_identity(key, b"transaction\x00", transaction_id)
        wal_effect_id = _wal_identity(key, b"effect\x00", effect_id)
        intent = _intent_document(
            transaction_id=wal_transaction_id,
            effect_id=wal_effect_id,
            expected_revision=expected,
            revision=next_revision,
            previous_head_ref=previous_head_ref,
            manifest_ref=manifest_ref,
            objects=object_refs,
        )
        inner = writer
        if inner is None:
            inner = __import__(
                "ipfs_kit_py.core.wal.writer", fromlist=["WALWriter"]
            ).WALWriter(root / "wal" / "records")
        bridge = _ReceiptWriter(inner)
        coordinator = wal["WALTransactionCoordinator"](
            root / "wal",
            writer=bridge,
            crash_injector=crash_injector,
        )

        publication_hold = ExitStack()
        publication_entered = False
        def admit_publication():
            nonlocal publication_entered
            if publication_scope is not None and not publication_entered:
                publication_hold.enter_context(publication_scope())
                publication_entered = True
            if before_publish is not None:
                return before_publish()

        def effect() -> bool:
            _authenticate_intent(root, intent, tenant_id=tenant_id, case_id=case_id,
                                 principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
            return _apply_intent(
                root, intent, install=True, fsync_file=fsync_file, fsync_directory=fsync_directory,
                **({"before_publish": admit_publication} if before_publish is not None or publication_scope is not None else {}),
            )

        def compensate() -> bool:
            _authenticate_intent(root, intent, tenant_id=tenant_id, case_id=case_id,
                                 principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
            return _apply_intent(
                root, intent, install=False, fsync_file=fsync_file, fsync_directory=fsync_directory,
            )

        with publication_hold:
            try:
                result = coordinator.execute(
                    intent,
                    effect,
                    compensate,
                    transaction_id=wal_transaction_id,
                    effect_id=wal_effect_id,
                )
            except wal["WALTransactionCrash"] as exc:
                raise PrivateRevisionInterrupted(str(getattr(exc, "args", ["crash"])[0]), transaction_id) from exc
            except wal["WALQueueFullError"] as exc:
                raise PrivateRevisionError("WAL backpressure", code="wal_backpressure", state="recoverable") from exc
            except wal["WALWriterError"] as exc:
                raise PrivateRevisionError("WAL writer is closed", code="wal_closed", state="recoverable") from exc
            except wal["WALTransactionError"] as exc:
                raise PrivateRevisionError(str(exc), code="transaction_failed", state="recoverable") from exc
            except PrivateRevisionError:
                raise
            if not result.committed or not bridge.receipts:
                raise PrivateRevisionError("commit receipt missing", code="durability_unproven", state="recoverable")
            mode = bridge.receipts[-1].acknowledgement_mode
            return RevisionPublication(
                True,
                "committed",
                transaction_id,
                effect_id,
                next_revision,
                getattr(mode, "value", str(mode)),
                len(bridge.receipts),
            )
    finally:
        if coordinator is not None:
            coordinator.close()
        if owns_writer and inner is not None:
            inner.close()
        if lock is not None:
            _release_lock(lock)
        process_lock.release()

def recover_private_revision(
    repository: str | Path,
    *,
    tenant_id: str,
    case_id: str,
    principal_id: str,
    key: bytes,
    key_id: str,
    fsync_file: Callable[[int], None] | None = None,
    fsync_directory: Callable[[int], None] | None = None,
    key_resolver: Callable[[str], bytes | None] | None = None,
) -> RevisionPublication:
    """Replay a committed revision or compensate an open one. A second call is a no-op."""

    wal = _load_wal()
    root = Path(repository)
    issue = inspect_revision_journal(root)
    if issue:
        raise PrivateRevisionError(
            f"revision journal is corrupt ({issue}); original bytes were preserved",
            code="journal_corrupt",
            state="recoverable",
        )
    process_lock = _process_lock(root)
    process_lock.acquire()
    lock = None
    coordinator = None
    writer = None
    try:
        lock = _acquire_lock(root)
        _authenticate_revision_owner(root, tenant_id=tenant_id, case_id=case_id,
            principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
        _open_head(root, tenant_id=tenant_id, case_id=case_id,
                   principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
        lineage = _authenticate_recovery_journal(root, tenant_id=tenant_id, case_id=case_id,
                   principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
        writer = __import__(
            "ipfs_kit_py.core.wal.writer", fromlist=["WALWriter"]
        ).WALWriter(root / "wal" / "records")
        bridge = _ReceiptWriter(writer)
        coordinator = wal["WALTransactionCoordinator"](root / "wal", writer=bridge)

        def replay(intent: Mapping[str, Any], effect_id: str) -> bool:
            if str(intent.get("effect_id") or "") != effect_id:
                return False
            _authenticate_intent(root, intent, tenant_id=tenant_id, case_id=case_id,
                                 principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
            return _apply_intent(root, intent, install=True, fsync_file=fsync_file, fsync_directory=fsync_directory, lineage=lineage)

        def rollback(intent: Mapping[str, Any], effect_id: str) -> bool:
            if str(intent.get("effect_id") or "") != effect_id:
                return False
            _authenticate_intent(root, intent, tenant_id=tenant_id, case_id=case_id,
                                 principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
            return _apply_intent(root, intent, install=False, fsync_file=fsync_file, fsync_directory=fsync_directory, lineage=lineage)

        try:
            counts = coordinator.recover(replay, rollback)
        except wal["WALTransactionError"] as exc:
            raise PrivateRevisionError(str(exc), code="recovery_failed", state="recoverable") from exc
        _, revision = _head_record(root)
        manifest = None
        if revision:
            try:
                manifest = _open_head(
                    root,
                    tenant_id=tenant_id,
                    case_id=case_id,
                    principal_id=principal_id,
                    key=key,
                    key_id=key_id,
                    revision_hint=revision,
                    key_resolver=key_resolver,
                )
            except PrivateRevisionError:
                raise
        if manifest is not None:
            _require_committed_revision(root, manifest, tenant_id=tenant_id, case_id=case_id,
                                       principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver)
        committed = bool(manifest) and counts["rolled_back"] == 0 and (
            counts["replayed"] > 0 or revision is not None
        )
        # A rollback that restored a parent still has a head. Distinguish by
        # whether this recovery invoked rollback.
        if counts["rolled_back"]:
            state = "compensated"
            committed = False
        elif manifest is None:
            state = "compensated"
            committed = False
        else:
            state = "committed"
            committed = True
        if manifest is None:
            _recovery_status(root, options=dict(tenant_id=tenant_id, case_id=case_id,
                principal_id=principal_id, key=key, key_id=key_id, key_resolver=key_resolver), phase="recovered_empty",
                fsync_file=fsync_file, fsync_directory=fsync_directory)
        effect = str((manifest or {}).get("effect_id") or "")
        transaction = str((manifest or {}).get("transaction_id") or "")
        return RevisionPublication(
            committed,
            state,
            transaction,
            effect,
            revision if committed or manifest else None,
            wal["WALAcknowledgementMode"].WAL_FSYNC_PARENT.value if bridge.receipts else None,
            len(bridge.receipts),
            replayed=counts["replayed"],
            rolled_back=counts["rolled_back"],
        )
    finally:
        if coordinator is not None:
            coordinator.close()
        if writer is not None:
            writer.close()
        if lock is not None:
            _release_lock(lock)
        process_lock.release()
