"""User-owned private key unlock, wrapping, and recovery.

These tests use temporary stores and injected keyrings. They do not touch a
system keyring and they do not skip when that keyring is missing.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

from integrations.private_storage import (
    PrivateArtifactBinding,
    PrivateArtifactBindingError,
    PrivateArtifactIntegrityError,
    PrivateKeyLockedError,
    UserOwnedKeySession,
    assert_store_isolated_from_exports,
    open_private_artifact,
    read_unlock_passphrase,
    seal_private_artifact,
    task_key_receipt,
)

PASSPHRASE = "sentinel-passphrase-do-not-persist"
RECOVERY = "sentinel-recovery-do-not-persist"
TENANT = "tenant-a"
CASE = "case-a"
OTHER_CASE = "case-b"


class MemoryKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, account: str, password: str) -> None:
        self.values[(service, account)] = password

    def get_password(self, service: str, account: str) -> str:
        return self.values[(service, account)]


class LockedKeyring:
    def set_password(self, service: str, account: str, password: str) -> None:
        raise RuntimeError("keyring locked")

    def get_password(self, service: str, account: str) -> str | None:
        raise RuntimeError("keyring locked")


def _binding(case: str = CASE) -> PrivateArtifactBinding:
    return PrivateArtifactBinding(
        tenant_id=TENANT,
        case_id=case,
        artifact_kind="draft",
        revision="1",
        principal_id=TENANT,
    )


def _assert_owner_only(directory: Path) -> None:
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    store = directory / "keystore.json"
    assert store.is_file()
    assert stat.S_IMODE(store.stat().st_mode) == 0o600
    assert list(directory.glob("*.key")) == []


def _disk_text(directory: Path) -> str:
    chunks: list[str] = []
    for path in directory.rglob("*"):
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="surrogateescape"))
    return "\n".join(chunks)


def test_passphrase_wrap_restart_and_permissions(tmp_path: Path) -> None:
    store = tmp_path / "keys"
    created = UserOwnedKeySession(store)
    state = created.create(protection="passphrase", passphrase=PASSPHRASE)
    assert state["unlocked"] is True
    assert state["raw_key_persisted"] is False
    assert state["unlock_is_remote_consent"] is False
    key_id = created.ensure_data_key(TENANT, CASE)
    provider = created.provider()
    resolved_id, resolved_key = provider.resolve(_binding())
    assert resolved_id == key_id
    envelope = seal_private_artifact(b"private-bytes", binding=_binding(), key=resolved_key, key_id=resolved_id)
    created.lock()
    assert created.unlocked is False
    with pytest.raises(PrivateKeyLockedError):
        created.provider()

    restarted = UserOwnedKeySession(store)
    assert restarted.unlocked is False
    assert restarted.public_state()["status"] == "unlock_needed"
    assert "passphrase_unlock" in restarted.public_state()["actions"]
    with pytest.raises(PrivateArtifactIntegrityError):
        restarted.unlock_passphrase("wrong-passphrase")
    assert restarted.unlocked is False
    restarted.unlock_passphrase(PASSPHRASE)
    again_id, again_key = restarted.provider().resolve(_binding())
    assert again_id == key_id
    assert open_private_artifact(envelope, binding=_binding(), key=again_key, expected_key_id=again_id) == b"private-bytes"
    _assert_owner_only(store)
    blob = _disk_text(store)
    assert PASSPHRASE not in blob
    assert resolved_key.hex() not in blob
    assert b"private-bytes".hex() not in blob
    receipt = json.dumps(task_key_receipt(restarted.public_state()))
    assert PASSPHRASE not in receipt
    assert "master_key" not in receipt


def test_tampered_wrapped_key_and_locked_store_is_not_overwritten(tmp_path: Path) -> None:
    store = tmp_path / "keys"
    session = UserOwnedKeySession(store)
    session.create(protection="passphrase", passphrase=PASSPHRASE)
    session.ensure_data_key(TENANT, CASE)
    session.lock()
    before = (store / "keystore.json").read_bytes()
    with pytest.raises(PrivateKeyLockedError):
        session.ensure_data_key(TENANT, OTHER_CASE)
    assert (store / "keystore.json").read_bytes() == before

    document = json.loads(before.decode("utf-8"))
    ciphertext = document["wrapped_master"]["ciphertext"]
    flipped = ("A" if ciphertext[0] != "A" else "B") + ciphertext[1:]
    document["wrapped_master"]["ciphertext"] = flipped
    (store / "keystore.json").write_bytes(json.dumps(document).encode("utf-8"))
    os.chmod(store / "keystore.json", 0o600)
    tampered = UserOwnedKeySession(store)
    with pytest.raises(PrivateArtifactIntegrityError):
        tampered.unlock_passphrase(PASSPHRASE)
    assert tampered.unlocked is False


def test_keyring_lock_does_not_downgrade_to_raw_file(tmp_path: Path) -> None:
    store = tmp_path / "keys"
    refused = UserOwnedKeySession(store)
    with pytest.raises(PrivateKeyLockedError) as locked:
        refused.create(protection="keyring", keyring=LockedKeyring())
    assert locked.value.public_state()["code"] == "keyring_unavailable"
    assert "create_with_passphrase" in locked.value.public_state()["actions"]
    assert not store.exists() or list(store.glob("*.key")) == []
    assert list(tmp_path.rglob("*.key")) == []

    ring = MemoryKeyring()
    created = UserOwnedKeySession(store)
    created.create(protection="keyring", keyring=ring)
    created.ensure_data_key(TENANT, CASE)
    created.lock()
    blob = _disk_text(store)
    for secret in ring.values.values():
        assert secret not in blob
    restarted = UserOwnedKeySession(store)
    with pytest.raises(PrivateKeyLockedError) as unavailable:
        restarted.unlock_keyring(LockedKeyring())
    state = unavailable.value.public_state()
    assert state["status"] == "unlock_needed"
    assert state["protection_downgrade"] is False
    assert "recovery_import" in state["actions"]
    assert list(store.glob("*.key")) == []
    restarted.unlock_keyring(ring)
    assert restarted.provider().resolve(_binding())[0].startswith("d-")


def test_recovery_roundtrip_and_foreign_case_denial(tmp_path: Path) -> None:
    store = tmp_path / "keys"
    session = UserOwnedKeySession(store)
    session.create(protection="passphrase", passphrase=PASSPHRASE)
    destination = tmp_path / "recovery" / "case-recovery.json"
    exported = session.export_recovery(TENANT, CASE, RECOVERY, destination)
    assert exported["deliberate_export"] is True
    assert exported["automatic_backup"] is False
    assert RECOVERY not in destination.read_text(encoding="utf-8")
    with pytest.raises(Exception):
        session.export_recovery(TENANT, CASE, RECOVERY, tmp_path / "backups" / "case.json")

    session.lock()
    before = (store / "keystore.json").read_bytes()
    with pytest.raises(PrivateKeyLockedError):
        session.import_recovery(
            exported["bytes"],
            tenant_id=TENANT,
            case_id=CASE,
            recovery_passphrase=RECOVERY,
        )
    assert (store / "keystore.json").read_bytes() == before

    fresh = UserOwnedKeySession(tmp_path / "imported")
    with pytest.raises(PrivateArtifactBindingError):
        fresh.import_recovery(
            exported["bytes"],
            tenant_id=TENANT,
            case_id=OTHER_CASE,
            recovery_passphrase=RECOVERY,
            store_passphrase=PASSPHRASE,
        )
    assert not (tmp_path / "imported").exists()
    with pytest.raises(PrivateArtifactIntegrityError):
        fresh.import_recovery(
            exported["bytes"],
            tenant_id=TENANT,
            case_id=CASE,
            recovery_passphrase="not-the-recovery-passphrase",
            store_passphrase=PASSPHRASE,
        )
    imported = fresh.import_recovery(
        exported["bytes"],
        tenant_id=TENANT,
        case_id=CASE,
        recovery_passphrase=RECOVERY,
        store_passphrase="another-store-passphrase",
    )
    assert imported["unlocked"] is True
    assert imported["automatic_backup"] is False
    source = UserOwnedKeySession(store)
    source.unlock_passphrase(PASSPHRASE)
    source_id, source_key = source.provider().resolve(_binding())
    imported_session = UserOwnedKeySession(tmp_path / "imported")
    imported_session.unlock_passphrase("another-store-passphrase")
    imported_id, imported_key = imported_session.provider().resolve(_binding())
    assert imported_id == source_id
    assert imported_key == source_key


def test_passphrase_prompt_rejects_argv_and_receipts(tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["complaint", "--passphrase", PASSPHRASE])
    with pytest.raises(Exception):
        read_unlock_passphrase(getpass_fn=lambda prompt: PASSPHRASE)
    monkeypatch.setattr(sys, "argv", ["complaint", "keys-unlock", "--store-dir", str(tmp_path)])
    captured: list[str] = []

    def _capture(prompt: str) -> str:
        captured.append(prompt)
        assert PASSPHRASE not in prompt
        return PASSPHRASE

    assert read_unlock_passphrase(getpass_fn=_capture) == PASSPHRASE
    assert captured and captured[0].endswith(": ")
    caplog.set_level("DEBUG")
    session = UserOwnedKeySession(tmp_path / "keys")
    session.create(protection="passphrase", passphrase=PASSPHRASE)
    assert PASSPHRASE not in caplog.text
    assert "sentinel-passphrase" not in json.dumps(task_key_receipt(session.public_state()))


def test_workspace_unlock_is_not_remote_consent_and_supervisor_can_continue(tmp_path: Path) -> None:
    from applications.complaint_workspace import ComplaintWorkspaceService

    service = ComplaintWorkspaceService(tmp_path / "workspace")
    before = service.get_privacy_policy("user-a")
    created = service.initialize_private_keys(protection="passphrase", passphrase=PASSPHRASE)
    assert created["unlocked"] is True
    assert created["cloud_processing_enabled"] is False
    assert created["unlock_is_remote_consent"] is False
    after = service.get_privacy_policy("user-a")
    assert after["policy"] == before["policy"]
    assert after["policy"].get("cloud_processing_enabled") in {False, None} or after["load"].get("cloud_processing_enabled") is False

    locked = service.lock_private_keys()
    assert locked["unlocked"] is False
    continued = service.continue_without_private_keys()
    assert continued["status"] == "awaiting_user"
    assert continued["worker_state"] == "ready_for_independent_tasks"
    assert continued["invented_key"] is False
    assert continued["privacy_bypassed"] is False
    with pytest.raises(PrivateKeyLockedError):
        service.private_key_provider()

    restarted = ComplaintWorkspaceService(tmp_path / "workspace")
    assert restarted.private_key_status()["status"] == "unlock_needed"
    opened = restarted.unlock_private_keys(passphrase=PASSPHRASE)
    assert opened["unlocked"] is True
    assert opened["unlock_is_remote_consent"] is False
    ensured = restarted.ensure_private_case_key(TENANT, CASE)
    assert ensured["data_key_id"].startswith("d-")
    assert PASSPHRASE not in json.dumps({key: value for key, value in ensured.items() if key != "data_key_id"})
    provider = restarted.private_key_provider()
    assert provider.resolve(_binding())[0] == ensured["data_key_id"]


def test_export_directory_cannot_hold_the_key_store(tmp_path: Path) -> None:
    exports = tmp_path / "exports"
    exports.mkdir()
    with pytest.raises(Exception):
        assert_store_isolated_from_exports(exports, exports)
    with pytest.raises(Exception):
        assert_store_isolated_from_exports(exports / "nested", exports)
    hostname = Path("/etc/hostname")
    if hostname.exists():
        assert hostname.read_text(encoding="utf-8").strip() not in PASSPHRASE


def test_cli_rejects_passphrase_arguments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import applications.complaint_workspace as workspace

    monkeypatch.setattr(
        workspace.ComplaintWorkspaceService,
        "__init__",
        lambda self, root_dir=None, **kwargs: None,
    )
    from complaint_generator.cli import keys_status

    monkeypatch.setattr(sys, "argv", ["complaint", "keys-status", "--passphrase", PASSPHRASE])
    with pytest.raises(SystemExit):
        keys_status(store_dir=str(tmp_path / "keys"))
    monkeypatch.setattr(sys, "argv", ["complaint", "keys-status", "--store-dir", str(tmp_path / "missing")])
    keys_status(store_dir=str(tmp_path / "missing"))
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "absent"
    assert PASSPHRASE not in json.dumps(receipt)
    assert receipt["worker_may_continue"] is True
