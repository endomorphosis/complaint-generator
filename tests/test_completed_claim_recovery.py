"""Synthetic interrupted callback histories, genuine Native CP/claim/queue/Git.
No model, provider, actual campaign, or fabricated terminal lifecycle is used.
"""
from copy import deepcopy
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from integrations.ipfs_accelerate import completed_claim_recovery as repair
from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def daemon_for(root, state):
    return native.PortalImplementationDaemon(
        todo_path=root / "board.md", state_path=state / "task_state.json",
        strategy_path=state / "strategy.json", events_path=state / "events.jsonl",
        repo_root=root, task_header_prefix="## SYN-", implement=False, max_task_attempts=3,
        use_ephemeral_worktree=True, worktree_root=root.parent / "worktrees",
        worktree_submodule_paths=[], merge_target_branch="main", implementation_protected_paths=["board.md"],
        merge_queue_dir=state / "merge-queue", llm_merge_resolver_command="")


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import utc_now
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.worktrees import WorktreePool
    base = tmp_path_factory.mktemp("genuine_native_callback")
    root, state = base / "repo", base / "state"
    root.mkdir(); state.mkdir(mode=0o700)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Synthetic Native callback fixture")
    git(root, "config", "user.email", "synthetic@example.invalid")
    (root / "board.md").write_text("# Synthetic task\n\n## SYN-40 Interrupted callback\n\n"
        "- Status: ready\n- Completion: validation\n- Priority: P1\n- Track: ops\n"
        "- Outputs: result.txt\n- Validation: test -f result.txt\n"
        "- Acceptance: A synthetic local result is recorded.\n")
    git(root, "add", "board.md"); git(root, "commit", "-qm", "Synthetic pending task")
    baseline = git(root, "rev-parse", "HEAD")
    daemon = daemon_for(root, state)
    task = daemon._load_tasks()[0]
    daemon._register_task_identities([task])  # Genuine synthetic-root registration, never live.
    identity = daemon._identity_for_task(task)
    branch = "implementation/syn-40-interrupted-attempt-1"
    pool = WorktreePool(repo_root=root, worktree_root=base / "worktrees")
    lease = pool.acquire(cache_key="synthetic-callback", base_ref="main", branch_name=branch)
    started_at = utc_now()
    # A real short-lived Native claim producer records its actual birth and exits.
    driver = base / "claim_producer.py"
    driver.write_text("import sys,json\nfrom pathlib import Path\nsys.path[:0]=" + repr(list(sys.path)) + "\n"
        "from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as n\n"
        "d=n.PortalImplementationDaemon(todo_path=Path(sys.argv[1]),state_path=Path(sys.argv[2]),"
        "strategy_path=Path(sys.argv[3]),events_path=Path(sys.argv[4]),repo_root=Path(sys.argv[5]),"
        "task_header_prefix='## SYN-',implement=False,use_ephemeral_worktree=False,"
        "worktree_submodule_paths=[],merge_queue_dir=Path(sys.argv[6]),llm_merge_resolver_command='')\n"
        "t=d._load_tasks()[0]\nm=d._build_implementation_task_claim_metadata(t,1,sys.argv[7])\n"
        "p=d._implementation_task_claim_path(t.task_id,canonical_task_cid=d._identity_for_task(t).canonical_task_cid)\n"
        "ok,reason,prior=d._try_acquire_implementation_task_claim(p,m)\nassert ok,reason\n")
    subprocess.run([sys.executable, "-I", "-B", str(driver), str(daemon.todo_path),
        str(daemon.state_path), str(daemon.strategy_path), str(daemon.events_path),
        str(root), str(state / "merge-queue"), started_at], check=True, timeout=90)
    claim_path = daemon._implementation_task_claim_path(task.task_id,
        canonical_task_cid=identity.canonical_task_cid)
    claim = json.loads(claim_path.read_text())
    current = native.PortalTaskState.load(daemon.state_path)
    current.implementation_attempts[task.task_id] = 1
    current.implementation_attempts_by_cid[identity.canonical_task_cid] = 1
    current.task_statuses[task.task_id] = "ready"
    current.task_identities[task.task_id] = identity.to_dict()
    current.last_implementation_task_id = task.task_id
    current.last_implementation_task_cid = identity.canonical_task_cid
    current.last_implementation_started_at = started_at
    current.last_implementation_worktree_path = str(lease.path)
    current.last_implementation_branch = branch
    current.save(daemon.state_path)
    def emit(kind, values):
        daemon._record_event(kind, {"synthetic_history": True, **values})
    common = {"task_id": task.task_id, "attempt": 1}
    emit("implementation_started", {**common, "branch": branch, "worktree_path": str(lease.path),
                                  "baseline_ref": baseline})
    (lease.path / "result.txt").write_text("synthetic local result\n")
    git(lease.path, "add", "result.txt")
    git(lease.path, "commit", "-qm", "Synthetic implementation")
    candidate = git(lease.path, "rev-parse", "HEAD")
    emit("implementation_proposal_validated", {**common, "accepted": True, "proposal_id": "synthetic-local-only"})
    emit("implementation_candidate_handoff_verified", {**common, "allowed": True,
        "implementation_commit": candidate})
    released = lease.release()
    assert released["released"] and released["reason"] == "clean_prepared_workspace"
    emit("worktree_pool_lease_released", released)
    metadata = {"schema": "ipfs_accelerate_py/agent-supervisor/merge-candidate@3",
        "task": {"task_id": task.task_id}, "completion_task_cids": {task.task_id: identity.canonical_task_cid},
        "repo_root": str(root), "todo_path": str(daemon.todo_path), "state_path": str(daemon.state_path),
        "events_path": str(daemon.events_path), "implementation_commit": candidate, "baseline_ref": baseline,
        "target_repository_id": daemon.merge_target_repository_id, "target_branch": "main",
        "validation_proof": {"passed": True, "returncode": 0, "selection": {"scope": "pre_merge"},
                             "synthetic_local_validation_only": True}}
    request = daemon.merge_queue.enqueue(branch_name=branch, task_id=task.task_id,
        canonical_task_id=identity.canonical_task_cid, canonical_task_key=identity.canonical_task_key,
        commit_sha=candidate, metadata=metadata, target_repository_id=daemon.merge_target_repository_id,
        target_branch="main")
    emit("merge_candidate_enqueued", {**common, "branch": branch, "request_id": request.request_id,
                                     "implementation_commit": candidate})
    git(root, "merge", "--no-ff", "--no-edit", branch)
    merged = git(root, "rev-parse", "HEAD")
    emit("merge_finished", {"branch": branch, "target_branch": "main", "merged": True,
        "attempted": True, "returncode": 0, "merge_commit": merged, "integration_base_commit": baseline})
    git(root, "branch", "-D", branch)
    emit("cleanup_finished", {"branch": branch, "cleaned": True, "deleted_branch": True})
    # Use the genuine Native callback, not a hand-written completed status/event.
    callback = daemon._mark_task_completed_in_todo(task.task_id,
        expected_task_cids={task.task_id: identity.canonical_task_cid})
    assert callback["updated"]
    processing = daemon.merge_queue.claim_pending_request(request, consumer_id="synthetic-native-completion")
    assert processing is not None
    daemon.merge_queue.complete(processing)
    # Deliberately do not save the old Portal snapshot after its actual callback.
    assert native.PortalTaskState.load(daemon.state_path).task_statuses[task.task_id] == "ready"
    assert not daemon.worktree_lifecycle.workspace_path_for(lease.path).exists()
    return dict(daemon=daemon, root=root, state=state, claim_path=claim_path,
        claim=claim, task=task, identity=identity, branch=branch, workspace=lease.path,
        head=git(root, "rev-parse", "HEAD"), callback=callback, request=request)


@pytest.fixture
def unchanged_world(world):
    d = world["daemon"]
    files = [world["claim_path"], d.todo_path, d.events_path]
    original = {p: p.read_bytes() for p in files}
    state = native.PortalTaskState.load(d.state_path)
    yield world
    for p, raw in original.items():
        p.write_bytes(raw)
    (wstate := world["state"] / native.IMPLEMENTATION_PROTECTED_ACTIVE_SNAPSHOT_FILENAME).unlink(missing_ok=True)
    state.save(d.state_path)
    git(world["root"], "update-ref", "refs/heads/main", world["head"])


def test_real_native_callback_proof_with_stale_cp_and_no_lifecycle(unchanged_world):
    w = unchanged_world
    value = repair.review_completed_claim(w["daemon"])
    assert value["source_status"] == "completed"
    assert value["portal_projection_status"] == "ready"
    assert value["claim"]["owner_process_birth"]["pid"] != os.getpid()


def test_exact_native_primitive_retires_only_claim_preserving_full_cp(unchanged_world):
    w = unchanged_world
    before = asdict(native.PortalTaskState.load(w["daemon"].state_path))
    closures = []
    result = repair.reconcile_completed_claim(w["daemon"], reprove_closure=lambda: closures.append(True))
    assert result["reconciled"] and len(closures) == 3
    assert not w["claim_path"].exists()
    assert asdict(native.PortalTaskState.load(w["daemon"].state_path)) == before
    assert not result["completion_authority"] and not result["attempt_refunded"]
    assert json.loads(Path(result["receipt_path"]).read_text())["phase"] == "released"


@pytest.mark.parametrize("damage", ["pending", "changed_definition", "wrong_cid", "wrong_key",
    "attempt", "live_owner", "fence", "corrupt_journal", "nonancestor", "new_lane"])
def test_unknown_or_nonterminal_authority_cannot_release(unchanged_world, damage):
    w = unchanged_world; d = w["daemon"]
    if damage in {"pending", "changed_definition"}:
        text = d.todo_path.read_text()
        d.todo_path.write_text(text.replace("Status: completed", "Status: ready") if damage == "pending"
                              else text.replace("result.txt", "other.txt"))
    elif damage in {"wrong_cid", "wrong_key", "live_owner", "fence"}:
        value = json.loads(w["claim_path"].read_text())
        if damage == "wrong_cid": value["canonical_task_cid"] += "x"
        elif damage == "wrong_key": value["canonical_task_key"] += "x"
        elif damage == "live_owner":
            from ipfs_accelerate_py.agent_supervisor.merge.worktree_lifecycle import current_process_birth
            value["owner_process_birth"] = current_process_birth().to_dict()
            value["pid"] = os.getpid()
        else:
            (w["state"] / native.IMPLEMENTATION_PROTECTED_ACTIVE_SNAPSHOT_FILENAME).write_text("{}")
        w["claim_path"].write_text(json.dumps(value))
    elif damage in {"attempt", "new_lane"}:
        value = native.PortalTaskState.load(d.state_path)
        if damage == "attempt": value.implementation_attempts[w["task"].task_id] = 2
        else: value.implementation_in_progress = True
        value.save(d.state_path)
    elif damage == "corrupt_journal":
        d.events_path.write_bytes(d.events_path.read_bytes().replace(b'"synthetic_history":true', b'"synthetic_history":false', 1))
    else:
        git(w["root"], "update-ref", "refs/heads/main",
            git(w["root"], "rev-list", "--max-parents=0", "HEAD"))
    raw = w["claim_path"].read_bytes()
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        repair.reconcile_completed_claim(d, reprove_closure=lambda: None)
    assert w["claim_path"].read_bytes() == raw


def test_replacement_at_closure_cannot_be_released(unchanged_world):
    w = unchanged_world
    count = 0
    def closure():
        nonlocal count
        count += 1
        if count == 2:
            value = json.loads(w["claim_path"].read_text())
            value["lease_id"] += "replacement"
            w["claim_path"].write_text(json.dumps(value))
    with pytest.raises(ValueError, match="proof_changed"):
        repair.reconcile_completed_claim(w["daemon"], reprove_closure=closure)
    assert w["claim_path"].exists()

