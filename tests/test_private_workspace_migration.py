"""Private workspace migration stays inside the envelope boundary.

Synthetic complaints only. No live IPFS, provider calls, or user home data.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from applications.complaint_workspace import (
    ComplaintWorkspaceService,
    WorkspaceAccess,
    WorkspacePersistenceError,
)
from complaint_generator.legacy_session_migration import (
    PrivateMigrationError,
    PrivateMigrationInterrupted,
    migrate_private_workspace,
)
from integrations.ipfs_datasets.draft_logic_pipeline import pin_proof_report_to_ipfs
from integrations.ipfs_datasets.graphs import persist_graph_snapshot
from integrations.private_storage import open_private_artifact, parse_private_envelope
from integrations.private_storage import PrivateArtifactBinding

SENTINEL = "SENTINEL-PRIV-DUR002-7f3a9c"
KEY_A = bytes(range(32))
KEY_B = bytes(range(32, 64))
KEY_A_ID = "case-key-a"
KEY_B_ID = "case-key-b"


class _HermeticBytes:
    measurement_label = "measured-hermetic"

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}
        self.seen: list[bytes] = []
        self._n = 0

    def add_bytes(self, data, pin=True):
        del pin
        blob = bytes(data)
        self.seen.append(blob)
        self._n += 1
        cid = f"bafyhermetic{self._n:04d}"
        self.blobs[cid] = blob
        return {"success": True, "cid": cid, "pinned": False}

    def cat(self, cid):
        return self.blobs[cid]

    def pin(self, cid):
        return {"success": True, "cid": cid, "pinned": True}


def _access(principal: str, case_id: str) -> WorkspaceAccess:
    return WorkspaceAccess.authenticated(principal, case_id=case_id)


def _artifact(root: Path, name: str, payload: bytes, *, tenant: str, case_id: str, kind: str, key: bytes, key_id: str, revision: str = "rev-1") -> dict:
    source = root / name
    source.write_bytes(payload)
    return {
        "tenant_id": tenant,
        "case_id": case_id,
        "principal_id": tenant,
        "artifact_kind": kind,
        "revision": revision,
        "source_path": source,
        "key": key,
        "key_id": key_id,
        "access": _access(tenant, case_id),
        "owner_record": {"owner": tenant, "case_id": case_id},
    }


def _scan(roots: list[Path], sentinel: str = SENTINEL) -> list[str]:
    hits: list[str] = []
    needle = sentinel.encode("utf-8")
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if sentinel in path.name:
                hits.append(str(path))
            if path.is_file() and not path.is_symlink():
                if needle in path.read_bytes():
                    hits.append(str(path))
    return hits


def test_migration_seals_every_class_and_resumes(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    dest = tmp_path / "private"
    catalog = tmp_path / "graph-catalog"
    cache = tmp_path / "cache"
    backups = tmp_path / "backups"
    logs = tmp_path / "logs"
    for path in (source, catalog, cache, backups, logs):
        path.mkdir()
    log_file = logs / "migration.log"
    log_file.write_text("migration start\n", encoding="utf-8")
    os.environ["COMPLAINT_GENERATOR_GRAPH_CATALOG"] = str(catalog)
    kinds = [
        "session", "answers", "attachment", "extracted-text", "assertion-envelope",
        "fact-graph", "rule-evaluation", "annotation", "draft", "proof-history",
        "theorem-source", "index", "backup-manifest",
    ]
    artifacts = []
    for tenant, case_id, key, key_id in (
        ("tenant-a", "case-a", KEY_A, KEY_A_ID),
        ("tenant-b", "case-b", KEY_B, KEY_B_ID),
    ):
        for kind in kinds:
            payload = json.dumps({
                "kind": kind,
                "tenant": tenant,
                "source_text": SENTINEL,
                "source_span": SENTINEL,
                "lean4": SENTINEL,
            }).encode("utf-8")
            artifacts.append(_artifact(
                source, f"{tenant}-{kind}.bin", payload,
                tenant=tenant, case_id=case_id, kind=kind, key=key, key_id=key_id,
            ))
    originals = {str(item["source_path"]): Path(item["source_path"]).read_bytes() for item in artifacts}
    with pytest.raises(PrivateMigrationInterrupted) as interrupted:
        migrate_private_workspace(
            source_root=source,
            destination_root=dest,
            artifacts=artifacts,
            fail_after_committed=1,
        )
    assert interrupted.value.partial["committed"] == 1
    for path, payload in originals.items():
        assert Path(path).read_bytes() == payload
    resumed = migrate_private_workspace(source_root=source, destination_root=dest, artifacts=artifacts)
    assert resumed["status"] == "complete"
    assert resumed["complete"] is True
    assert resumed["cleanup_performed"] is False
    manifest = json.loads((dest / "private_migration_manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "complaint-private-migration/v1"
    assert len(manifest["entries"]) == len(artifacts)
    for entry in manifest["entries"]:
        assert set(entry) == {"artifact_ref", "ciphertext_name", "ciphertext_sha256", "readback", "status"}
        assert entry["readback"] == "verified"
        assert SENTINEL not in json.dumps(entry)
    assert _scan([dest, catalog, cache, backups, logs]) == []
    for path, payload in originals.items():
        assert Path(path).read_bytes() == payload
    again = migrate_private_workspace(source_root=source, destination_root=dest, artifacts=artifacts)
    assert again["status"] == "complete"
    assert again["committed"] == len(artifacts)


def test_locked_corrupt_owner_and_cleanup(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    dest = tmp_path / "private"
    snap = tmp_path / "snap"
    source.mkdir()
    snap.mkdir()
    artifact = _artifact(
        source, "session.json", f"answers {SENTINEL}".encode("utf-8"),
        tenant="tenant-a", case_id="case-a", kind="session", key=KEY_A, key_id=KEY_A_ID,
    )
    locked = dict(artifact)
    locked["locked"] = True
    locked["key"] = None
    before = Path(artifact["source_path"]).read_bytes()
    locked_result = migrate_private_workspace(source_root=source, destination_root=dest, artifacts=[locked])
    assert locked_result["status"] == "unlock_needed"
    assert Path(artifact["source_path"]).read_bytes() == before
    assert list(dest.glob("*.bin")) == []

    done = migrate_private_workspace(source_root=source, destination_root=dest, artifacts=[artifact])
    assert done["complete"] is True
    dest_file = next(dest.glob("*.bin"))
    sealed = dest_file.read_bytes()
    dest_file.write_bytes(sealed[:-1] + bytes([sealed[-1] ^ 0x01]))
    corrupt_dest = dest_file.read_bytes()
    corrupt = migrate_private_workspace(source_root=source, destination_root=dest, artifacts=[artifact])
    assert corrupt["status"] == "recoverable"
    assert dest_file.read_bytes() == corrupt_dest
    assert Path(artifact["source_path"]).read_bytes() == before
    dest_file.write_bytes(sealed)

    wrong = dict(artifact)
    wrong["key"] = KEY_B
    wrong["key_id"] = KEY_B_ID
    preserved = dest_file.read_bytes()
    rejected = migrate_private_workspace(source_root=source, destination_root=dest, artifacts=[wrong])
    assert rejected["status"] == "recoverable"
    assert dest_file.read_bytes() == preserved
    assert Path(artifact["source_path"]).read_bytes() == before

    mismatched = dict(artifact)
    mismatched["owner_record"] = {"owner": "other", "case_id": "case-a"}
    mismatched["source_path"] = source / "tenant-b-looking-name.json"
    Path(mismatched["source_path"]).write_bytes(before)
    owner = migrate_private_workspace(
        source_root=source, destination_root=dest, artifacts=[mismatched],
    )
    assert owner["complete"] is False
    assert Path(mismatched["source_path"]).read_bytes() == before

    link = snap / "hardlink"
    os.link(artifact["source_path"], link)
    copy = snap / "copy"
    copy.write_bytes(before)
    copied = dict(artifact)
    copied["copy_paths"] = [copy]
    outside = tmp_path / "outside-link"
    os.link(artifact["source_path"], outside)
    blocked = migrate_private_workspace(
        source_root=source, destination_root=dest, artifacts=[copied],
        snapshot_roots=[snap], cleanup=True,
    )
    assert blocked["cleanup_complete"] is False
    assert Path(artifact["source_path"]).read_bytes() == before
    assert outside.read_bytes() == before
    outside.unlink()
    cleaned = migrate_private_workspace(
        source_root=source, destination_root=dest, artifacts=[copied],
        snapshot_roots=[snap], cleanup=True,
    )
    assert cleaned["cleanup_performed"] is True
    assert cleaned["cleanup_complete"] is True
    assert not Path(artifact["source_path"]).exists()
    assert not link.exists()
    assert not copy.exists()
    assert _scan([dest, snap]) == []

    manifest = dest / "private_migration_manifest.json"
    manifest.write_text("{", encoding="utf-8")
    fresh = source / "fresh.json"
    fresh.write_bytes(b"keep-me")
    broken = dict(artifact)
    broken["source_path"] = fresh
    with pytest.raises(PrivateMigrationError) as caught:
        migrate_private_workspace(source_root=source, destination_root=dest, artifacts=[broken])
    assert caught.value.code == "malformed_manifest"
    assert fresh.read_bytes() == b"keep-me"


def test_workspace_session_graph_proof_and_export(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    access = _access("tenant-a", "case-a")
    service = ComplaintWorkspaceService(root, access=access)
    service.bind_private_case_key(
        tenant_id="tenant-a", case_id="case-a", principal_id="tenant-a",
        key_id=KEY_A_ID, key=KEY_A,
    )
    missing = service._load_state("tenant-a")
    assert missing["missing_new_session"] is True
    assert missing["session_readable"] is True
    missing["intake_answers"] = {"harm": SENTINEL}
    missing["draft"] = {"body": SENTINEL}
    service._save_state(missing)
    session_file = next(root.glob("p-*.json"))
    assert SENTINEL.encode("utf-8") not in session_file.read_bytes()
    assert session_file.read_bytes().startswith(b"CGPE")
    reloaded = service._load_state("tenant-a")
    assert reloaded["intake_answers"]["harm"] == SENTINEL
    sealed = session_file.read_bytes()

    service.bind_private_case_key(
        tenant_id="tenant-a", case_id="case-a", principal_id="tenant-a",
        key_id=KEY_A_ID, key=None, locked=True,
    )
    locked = service._load_state("tenant-a")
    assert locked["status"] == "unlock_needed"
    assert locked["missing_new_session"] is False
    with pytest.raises(WorkspacePersistenceError):
        service._save_state({"user_id": "tenant-a", "case_id": "case-a", "intake_answers": {}})
    assert session_file.read_bytes() == sealed

    session_file.write_bytes(b"not-json-and-not-envelope")
    corrupt = service._load_state("tenant-a")
    assert corrupt["status"] == "recoverable"
    assert corrupt["code"] == "corrupt_session"
    with pytest.raises(WorkspacePersistenceError):
        service._save_state({"user_id": "tenant-a", "case_id": "case-a", "intake_answers": {"harm": "empty"}})
    assert session_file.read_bytes() == b"not-json-and-not-envelope"
    session_file.write_bytes(sealed)

    service.bind_private_case_key(
        tenant_id="tenant-a", case_id="case-a", principal_id="tenant-a",
        key_id=KEY_A_ID, key=KEY_A,
    )
    backend = _HermeticBytes()
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    os.environ["COMPLAINT_GENERATOR_GRAPH_CATALOG"] = str(catalog)
    graph = persist_graph_snapshot(
        {"entities": [{"text": SENTINEL, "source_text": SENTINEL}], "relationships": []},
        graph_id="case-graph",
        private_context={
            "access": access,
            "tenant_id": "tenant-a",
            "case_id": "case-a",
            "principal_id": "tenant-a",
            "key": KEY_A,
            "key_id": KEY_A_ID,
            "revision": "fact-graph-1",
            "backend": backend,
            "destination_dir": tmp_path / "graphs",
        },
    )
    assert graph["private_indexing"] == "unsupported"
    assert graph["plaintext_catalog"] is False
    assert graph["verified"] is True
    report = pin_proof_report_to_ipfs(
        {
            "proof_status": "blocked",
            "errors": [SENTINEL],
            "theorem_export": {"lean4": f"theorem sentinel : {SENTINEL}", "coq": SENTINEL},
            "source_text": SENTINEL,
        },
        claim_id="claim-1",
        private_context={
            "access": access,
            "tenant_id": "tenant-a",
            "case_id": "case-a",
            "principal_id": "tenant-a",
            "key": KEY_A,
            "key_id": KEY_A_ID,
            "revision": "proof-1",
            "backend": backend,
        },
    )
    assert report["private_artifact"] is True
    assert report["verified"] is True
    assert report["plaintext_exported"] is False
    materials = service.persist_private_case_materials(
        "tenant-a",
        {
            "answers": f"answers {SENTINEL}".encode("utf-8"),
            "assertion-envelope": json.dumps({"source_text": SENTINEL, "source_span": SENTINEL}).encode("utf-8"),
            "rule-evaluation": f"rule {SENTINEL}".encode("utf-8"),
            "annotation": f"note {SENTINEL}".encode("utf-8"),
            "draft": f"draft {SENTINEL}".encode("utf-8"),
            "index": f"index {SENTINEL}".encode("utf-8"),
            "backup-manifest": f"backup {SENTINEL}".encode("utf-8"),
            "attachment": f"file {SENTINEL}".encode("utf-8"),
            "extracted-text": f"text {SENTINEL}".encode("utf-8"),
        },
        case_id="case-a",
        backend=backend,
    )
    assert materials["written"] is True
    memory = service.ingest_memory_evidence(
        "tenant-a",
        files=[{"filename": "note.txt", "data": f"upload {SENTINEL}".encode("utf-8")}],
        backend=backend,
    )
    assert memory["plaintext_disk"] is False
    assert memory["imported"][0]["extraction"]["method"] == "ephemeral-memory"
    filing = tmp_path / "filing" / "complaint.txt"
    exported = service.export_readable_filing(
        "tenant-a",
        destination=filing,
        protection="user_chosen_plaintext",
        content=f"filing {SENTINEL}".encode("utf-8"),
    )
    assert exported["automatic"] is False
    assert exported["protection"] == "user_chosen_plaintext"
    assert filing.read_text(encoding="utf-8").endswith(SENTINEL)
    with pytest.raises(WorkspacePersistenceError):
        service.export_readable_filing(
            "tenant-a",
            destination=root / "hidden.txt",
            protection="user_chosen_plaintext",
            content=b"nope",
        )
    assert _scan([root, catalog, tmp_path / "graphs"]) == []
    assert all(SENTINEL.encode("utf-8") not in blob for blob in backend.seen)
    opened = open_private_artifact(
        backend.seen[0],
        binding=PrivateArtifactBinding(
            tenant_id="tenant-a",
            case_id="case-a",
            artifact_kind="fact-graph",
            revision="fact-graph-1",
            principal_id="tenant-a",
        ),
        key=KEY_A,
        expected_key_id=KEY_A_ID,
    )
    assert SENTINEL.encode("utf-8") in opened
    assert parse_private_envelope(backend.seen[0])["key_id"] == KEY_A_ID
