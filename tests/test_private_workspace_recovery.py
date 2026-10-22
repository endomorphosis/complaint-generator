"""Joined intake revision recovery over the Kit WAL.

Synthetic repositories only. Upstream Kit WAL suites are a separate
compatibility qualification and do not replace these assertions.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from applications.complaint_workspace import (
    ComplaintWorkspaceService,
    WorkspaceAccess,
    workspace_access_scope,
)
from integrations.private_storage import (
    PrivateRevisionError,
    PrivateRevisionInterrupted,
    _prefer_vendored_kit,
    commit_acknowledged_by_receipt,
    commit_private_revision,
    read_private_revision,
    recover_private_revision,
)

_prefer_vendored_kit()
from ipfs_kit_py.core.wal.contracts import WALAcknowledgementMode
from ipfs_kit_py.core.wal.coordinator import WALTransactionCrash
from ipfs_kit_py.core.wal.writer import WALQueueFullError, WALWriter

SENTINEL = "SENTINEL-DUR003-answer-7c1e"
KEY = bytes(range(1, 33))
KEY_ID = "k-opaque"
OTHER_KEY = bytes(range(33, 65))
TENANT = "tenant-a"
CASE = "case-a"
PRINCIPAL = "tenant-a"

BOUNDARIES = (
    "before_begin",
    "after_begin",
    "before_intent",
    "after_intent",
    "before_effect",
    "after_effect",
    "before_commit",
    "after_commit",
)

UPSTREAM_WAL_SUITES = (
    "tests/runtime_readiness/wal/test_wal_writer.py",
    "tests/runtime_readiness/wal/test_wal_recovery.py",
    "tests/runtime_readiness/wal/test_joined_crash_matrix.py",
)


def _payloads(answer: str, effect_id: str, revision: str) -> tuple[bytes, bytes, bytes]:
    session = {
        "intake_answers": {"harm": answer},
        "intake_history": [{"effect_id": effect_id, "question_id": "harm"}],
        "private_revision": revision,
    }
    graph = {"relationships": [{"id": effect_id, "kind": "intake-answer", "revision": revision}]}
    proof = {"entries": [{"effect_id": effect_id, "kind": "intake-revision", "revision": revision}]}
    return (
        json.dumps(session, sort_keys=True).encode("utf-8"),
        json.dumps(graph, sort_keys=True).encode("utf-8"),
        json.dumps(proof, sort_keys=True).encode("utf-8"),
    )


def _commit(root: Path, *, answer: str = SENTINEL, effect: str = "effect-1", transaction: str = "tx-1", expected: str | None = "0", **kwargs):
    revision = str(int(expected or "0") + 1)
    session, graph, proof = _payloads(answer, effect, revision)
    return commit_private_revision(
        root,
        tenant_id=TENANT,
        case_id=CASE,
        principal_id=PRINCIPAL,
        key=KEY,
        key_id=KEY_ID,
        expected_revision=expected,
        session=session,
        fact_graph=graph,
        proof=proof,
        transaction_id=transaction,
        effect_id=effect,
        **kwargs,
    )


def _crash(boundary: str):
    def inject(name: str, transaction_id: str | None = None) -> None:
        del transaction_id
        if name == boundary:
            raise WALTransactionCrash(name)

    return inject


def _scan(root: Path) -> list[str]:
    hits = []
    needle = SENTINEL.encode("utf-8")
    key_needle = KEY
    for path in root.rglob("*"):
        if SENTINEL in path.name or "passphrase" in path.name.lower() or path.name.endswith(".key"):
            hits.append(str(path))
        if path.is_file() and not path.is_symlink():
            data = path.read_bytes()
            if needle in data or key_needle in data:
                # Ciphertext may theoretically collide; authenticated plaintext must not.
                if path.suffix in {".jsonl", ".rev", ".tmp"} or "wal" in path.parts or path.name.startswith("."):
                    hits.append(str(path))
                elif path.parent.name != "o" and path.name != "head.cgpe":
                    hits.append(str(path))
    return hits


def _visible(root: Path) -> dict | None:
    return read_private_revision(
        root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
    )


def test_receipt_not_buffered_or_queued(tmp_path: Path) -> None:
    writer = WALWriter(tmp_path / "wal")
    try:
        buffered = writer.append("mutate", acknowledgement_mode=WALAcknowledgementMode.BUFFERED, record_key="b")
        queued = writer.append("mutate", acknowledgement_mode=WALAcknowledgementMode.QUEUED, record_key="q")
        durable = writer.append(
            "mutate",
            acknowledgement_mode=WALAcknowledgementMode.WAL_FSYNC_PARENT,
            record_key="d",
        )
    finally:
        writer.close()
    assert commit_acknowledged_by_receipt(buffered) is False
    assert commit_acknowledged_by_receipt(queued) is False
    assert buffered.fsync_receipt is None
    assert durable.fsync_receipt is not None
    assert commit_acknowledged_by_receipt(durable) is True
    assert durable.durable is True


def test_commit_publishes_one_revision_without_plaintext_journal(tmp_path: Path) -> None:
    publication = _commit(tmp_path)
    assert publication.committed is True
    assert publication.network_pinned is False
    assert publication.receipt_count >= 1
    assert publication.acknowledgement_mode == WALAcknowledgementMode.WAL_FSYNC_PARENT.value
    opened = _visible(tmp_path)
    assert opened is not None
    assert json.loads(opened["session"])["intake_answers"]["harm"] == SENTINEL
    assert len(json.loads(opened["fact_graph"])["relationships"]) == 1
    assert len(json.loads(opened["proof"])["entries"]) == 1
    assert opened["manifest"]["transaction_id"] == "tx-1"
    assert opened["manifest"]["effect_id"] == "effect-1"
    assert _scan(tmp_path) == []
    again = recover_private_revision(
        tmp_path, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
    )
    twice = recover_private_revision(
        tmp_path, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
    )
    assert again.committed is True
    assert twice.replayed == 0
    reopened = _visible(tmp_path)
    assert len(json.loads(reopened["fact_graph"])["relationships"]) == 1
    assert len(json.loads(reopened["proof"])["entries"]) == 1
    assert json.loads(reopened["session"])["intake_history"][0]["effect_id"] == "effect-1"


@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_crash_boundary_reopens_to_committed_or_compensated(tmp_path: Path, boundary: str) -> None:
    root = tmp_path / boundary
    with pytest.raises(PrivateRevisionInterrupted) as caught:
        _commit(root, crash_injector=_crash(boundary), transaction=f"tx-{boundary}", effect=f"ef-{boundary}")
    assert caught.value.committed is False
    assert caught.value.boundary == boundary
    first = recover_private_revision(
        root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
    )
    second = recover_private_revision(
        root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
    )
    assert first.state in {"committed", "compensated"}
    assert second.replayed == 0
    assert second.rolled_back == 0
    opened = _visible(root)
    if boundary == "after_commit":
        assert first.committed is True
        assert opened is not None
        session = json.loads(opened["session"])
        assert session["intake_answers"]["harm"] == SENTINEL
        assert len(json.loads(opened["fact_graph"])["relationships"]) == 1
        assert len(json.loads(opened["proof"])["entries"]) == 1
    elif boundary in {"before_begin", "after_begin", "before_intent", "after_intent", "before_effect", "after_effect", "before_commit"}:
        assert first.committed is False
        assert first.state == "compensated"
        assert opened is None or SENTINEL.encode("utf-8") not in opened["session"]
    assert _scan(root) == []


def test_ack_lost_after_effect_does_not_duplicate_on_second_recovery(tmp_path: Path) -> None:
    root = tmp_path / "ack-lost"
    with pytest.raises(PrivateRevisionInterrupted):
        _commit(root, crash_injector=_crash("after_effect"), effect="effect-lost", transaction="tx-lost")
    first = recover_private_revision(
        root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
    )
    second = recover_private_revision(
        root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
    )
    assert first.state == "compensated"
    assert first.committed is False
    assert second.rolled_back == 0
    assert _visible(root) is None


def test_corrupt_journal_preserves_bytes(tmp_path: Path) -> None:
    root = tmp_path / "corrupt"
    _commit(root)
    decisions = root / "wal" / "transaction-decisions.jsonl"
    original = decisions.read_bytes()
    lines = original.splitlines(keepends=True)
    lines.insert(1, b"{this is not json\n")
    decisions.write_bytes(b"".join(lines))
    preserved = decisions.read_bytes()
    with pytest.raises(PrivateRevisionError) as caught:
        recover_private_revision(
            root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
        )
    assert caught.value.code == "journal_corrupt"
    assert caught.value.committed is False
    assert decisions.read_bytes() == preserved
    assert (root / "head.cgpe").exists()


def test_torn_tail_stays_recoverable(tmp_path: Path) -> None:
    root = tmp_path / "torn"
    _commit(root)
    decisions = root / "wal" / "transaction-decisions.jsonl"
    decisions.write_bytes(decisions.read_bytes() + b'{"kind":"commit"')
    recovered = recover_private_revision(
        root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
    )
    assert recovered.state == "committed"
    assert json.loads(_visible(root)["session"])["intake_answers"]["harm"] == SENTINEL


def test_stale_revision_and_wrong_key_and_case(tmp_path: Path) -> None:
    root = tmp_path / "cas"
    _commit(root)
    with pytest.raises(PrivateRevisionError) as stale:
        _commit(root, expected="0", transaction="tx-2", effect="effect-2", answer="other-answer")
    assert stale.value.code == "revision_conflict"
    assert json.loads(_visible(root)["session"])["intake_answers"]["harm"] == SENTINEL
    with pytest.raises(PrivateRevisionError) as wrong_key:
        read_private_revision(
            root, tenant_id=TENANT, case_id=CASE, principal_id=PRINCIPAL, key=OTHER_KEY, key_id=KEY_ID,
        )
    assert wrong_key.value.code == "authentication_failed"
    with pytest.raises(PrivateRevisionError) as wrong_case:
        read_private_revision(
            root, tenant_id=TENANT, case_id="case-b", principal_id=PRINCIPAL, key=KEY, key_id=KEY_ID,
        )
    assert wrong_case.value.code == "authentication_failed"
    assert (root / "head.cgpe").read_bytes()


def test_fsync_failure_is_not_a_commit(tmp_path: Path) -> None:
    def fail(_fd: int) -> None:
        raise OSError("injected fsync failure")

    root = tmp_path / "fsync"
    with pytest.raises(PrivateRevisionError) as caught:
        _commit(root, fsync_file=fail)
    assert caught.value.committed is False
    assert caught.value.code == "file_fsync_failed"
    assert not (root / "head.cgpe").exists()

    parent = tmp_path / "parent-fsync"
    with pytest.raises(PrivateRevisionError) as parent_caught:
        _commit(parent, fsync_directory=fail)
    assert parent_caught.value.committed is False
    assert parent_caught.value.code == "directory_fsync_failed"
    assert not (parent / "head.cgpe").exists()


def test_closed_writer_and_backpressure(tmp_path: Path) -> None:
    writer = WALWriter(tmp_path / "closed-writer")
    writer.close()
    with pytest.raises(PrivateRevisionError) as closed:
        _commit(tmp_path / "closed-repo", writer=writer)
    assert closed.value.code == "wal_closed"
    assert closed.value.committed is False

    class Full:
        def append(self, *args, **kwargs):
            del args, kwargs
            raise WALQueueFullError("bounded")

        def close(self) -> None:
            return None

    with pytest.raises(PrivateRevisionError) as blocked:
        _commit(tmp_path / "full-repo", writer=Full())
    assert blocked.value.code == "wal_backpressure"
    assert not (tmp_path / "full-repo" / "head.cgpe").exists()


def test_concurrent_answers_do_not_share_a_temp_name(tmp_path: Path) -> None:
    root = tmp_path / "race"
    barrier = threading.Barrier(2)
    outcomes: list[object] = []
    lock = threading.Lock()

    def attempt(name: str, effect: str) -> None:
        barrier.wait()
        try:
            result = _commit(root, answer=name, effect=effect, transaction=effect, expected="0")
            with lock:
                outcomes.append(result)
        except PrivateRevisionError as exc:
            with lock:
                outcomes.append(exc)
        except Exception as exc:  # surface unexpected races in the assertion below
            with lock:
                outcomes.append(exc)

    threads = [
        threading.Thread(target=attempt, args=("answer-one", "effect-a")),
        threading.Thread(target=attempt, args=("answer-two", "effect-b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    committed = [item for item in outcomes if getattr(item, "committed", False)]
    conflicts = [item for item in outcomes if getattr(item, "code", "") == "revision_conflict"]
    detail = [f"{type(item).__name__}:{getattr(item, 'code', '')}:{getattr(item, 'committed', '')}:{item}" for item in outcomes]
    assert len(committed) == 1, detail
    assert len(conflicts) == 1, detail
    opened = _visible(root)
    body = opened["session"]
    assert (b"answer-one" in body) ^ (b"answer-two" in body)
    temps = [path.name for path in root.rglob("*.tmp")]
    assert len(temps) == len(set(temps))
    assert "session.tmp" not in temps


def test_workspace_join_uses_the_same_revision_identity(tmp_path: Path) -> None:
    service = ComplaintWorkspaceService(tmp_path / "ws")

    class Provider:
        def resolve(self, binding):
            del binding
            return (KEY_ID, KEY)

    service.private_key_provider = lambda: Provider()
    with workspace_access_scope(WorkspaceAccess.trusted_local()):
        receipt = service.commit_joined_intake_revision(
            "tenant-a",
            question_id="harm",
            answer=SENTINEL,
            transaction_id="tx-ws",
            effect_id="effect-ws",
            case_id="case-a",
            expected_revision="0",
        )
    assert receipt["committed"] is True
    assert receipt["network_pinned"] is False
    assert receipt["transaction_id"] == "tx-ws"
    assert receipt["effect_id"] == "effect-ws"
    opened = read_private_revision(
        service.joined_revision_repository(),
        tenant_id="tenant-a",
        case_id="case-a",
        principal_id="tenant-a",
        key=KEY,
        key_id=KEY_ID,
    )
    session = json.loads(opened["session"])
    assert session["intake_answers"]["harm"] == SENTINEL
    assert session["annotation_knowledge_graph"]["relationships"][0]["id"] == "effect-ws"
    assert session["proof_history"][0]["effect_id"] == "effect-ws"
    assert _scan(service.joined_revision_repository()) == []
    with workspace_access_scope(WorkspaceAccess.trusted_local()):
        first = service.recover_joined_intake_revision("tenant-a", case_id="case-a")
        second = service.recover_joined_intake_revision("tenant-a", case_id="case-a")
    assert first["committed"] is True
    assert second["replayed"] == 0


def test_upstream_wal_suites_are_a_separate_qualification() -> None:
    """Optional Kit fixtures stay a compatibility report.

    A missing or failing upstream file is not counted as a first-party pass.
    """

    root = Path(__file__).resolve().parents[1] / "external" / "ipfs_kit_py"
    report = []
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    for relative in UPSTREAM_WAL_SUITES:
        suite = root / relative
        entry = {"suite": relative, "counts_as_passed": False, "status": "missing"}
        if not suite.is_file():
            report.append(entry)
            continue
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=no", str(suite)],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        entry["returncode"] = completed.returncode
        if completed.returncode == 0:
            entry["status"] = "passed"
            entry["counts_as_passed"] = True
        elif completed.returncode == 5:
            entry["status"] = "missing"
        else:
            entry["status"] = "failed"
        report.append(entry)
    assert [item["suite"] for item in report] == list(UPSTREAM_WAL_SUITES)
    for item in report:
        if item["status"] != "passed":
            assert item["counts_as_passed"] is False
        assert item["status"] in {"passed", "failed", "missing", "unavailable"}
    # The qualification record is explicit even when every suite passes.
    assert all("counts_as_passed" in item for item in report)
