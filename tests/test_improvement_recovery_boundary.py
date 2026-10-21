"""Regression controls for the actual native attempt log and recovery custody."""
from contextlib import contextmanager
import json
import os

import pytest

from tests.test_improvement_recovery import _dead_attempt, _identity, _stamp, _write_campaign
import integrations.ipfs_accelerate.improvement_runner as runner

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _real_shaped_progress(tmp_path, monkeypatch):
    selected = _stamp(302)
    started = _stamp(300)
    emitted = _stamp(252)
    log = tmp_path / "state" / "implementation_logs" / "owned-attempt.log"
    payload = _dead_attempt(
        active_task_started_at=selected, active_log_path=str(log),
        last_implementation_started_at=started, last_implementation_task_id='CIMP-OPS-03',
        last_implementation_task_cid='bafyattemptcid', last_implementation_log_path=str(log),
        last_implementation_worktree_path=str(tmp_path / 'work'),
        active_worktree_path=str(tmp_path / "work"),
        owner_process_birth=_identity(991120),
    )
    root, spec, state, record = _write_campaign(tmp_path, monkeypatch, payload, started_ago=310)
    log.parent.mkdir(mode=0o700)
    log.write_text(f"Task: {payload['active_task_id']} Synthetic\nStarted: {started}\nWorkspace: {payload['active_worktree_path']}\n" + json.dumps({"type": "usage", "signature": "synthetic", "usage": {"inputTokens": 15}}) + "\n")
    log.chmod(0o600)
    start = {
        "type": "implementation_started", "timestamp": emitted,
        "task_id": payload["active_task_id"], "canonical_task_cid": payload["active_task_cid"],
        "attempt": payload["active_attempt"], "worktree_path": payload["active_worktree_path"],
        "log_path": str(log), "execution_mode": "model-assisted", "provider_dispatched": False,
    }
    events = state / f"{runner.STATE_PREFIX}_events.jsonl"
    events.write_text(json.dumps(start) + "\n")
    return root, spec, state, record, log, start


def test_real_native_log_frames_are_current_attempt_progress(tmp_path, monkeypatch):
    root, spec, state, _, _, _ = _real_shaped_progress(tmp_path, monkeypatch)
    result = runner.status(root, spec, state)
    assert result["provider_execution_verified"] is True
    assert result["provider_progress_verified"] is True
    assert result["healthy"] is True
    assert result["provider_execution_evidence"]["source"] == "owned_attempt_log"
    assert result["completion_authority"] is False


@pytest.mark.parametrize("mismatch", ["cid", "attempt", "log", "start", "symlink", "old_log"])
def test_attempt_log_progress_rejects_wrong_custody(tmp_path, monkeypatch, mismatch):
    root, spec, state, _, log, start = _real_shaped_progress(tmp_path, monkeypatch)
    if mismatch == "cid":
        start["canonical_task_cid"] = "bafyforeigncid"
    elif mismatch == "attempt":
        start["attempt"] -= 1
    elif mismatch == "log":
        start["log_path"] += ".another"
    elif mismatch == "start":
        start["timestamp"] = _stamp(301)
    elif mismatch == "symlink":
        other = log.with_suffix(".elsewhere")
        log.rename(other)
        log.symlink_to(other)
    elif mismatch == "old_log":
        stale = runner.time.time() - 500
        os.utime(log, (stale, stale))
    (state / f"{runner.STATE_PREFIX}_events.jsonl").write_text(json.dumps(start) + "\n")
    assert runner.status(root, spec, state)["provider_progress_verified"] is False


def test_log_prefix_is_not_the_current_log_identity(tmp_path, monkeypatch):
    root, spec, state, _, log, start = _real_shaped_progress(tmp_path, monkeypatch)
    event = dict(start, type="implementation_provider_started", timestamp=_stamp(1), log_path=str(log) + ".old")
    (state / f"{runner.STATE_PREFIX}_events.jsonl").write_text(json.dumps(event) + "\n")
    assert runner.status(root, spec, state)["provider_execution_verified"] is False


def test_development_awaiting_phase_cannot_hide_hard_deadline(tmp_path, monkeypatch):
    payload = _dead_attempt(active_phase="awaiting_user", active_task_started_at=_stamp(runner.TIMEOUT_SECONDS + 1))
    root, spec, state, _ = _write_campaign(tmp_path, monkeypatch, payload, started_ago=runner.TIMEOUT_SECONDS + 20)
    assert runner.status(root, spec, state)["status"] == "stalled"


def test_dead_worker_does_not_authorize_signalling_live_supervisor(tmp_path, monkeypatch):
    root, spec, state, _ = _write_campaign(tmp_path, monkeypatch, _dead_attempt())
    signalled = []
    monkeypatch.setattr(runner, "_descendants", lambda identity: [])
    monkeypatch.setattr(runner, "_signal_birth", lambda identity, signum: signalled.append(identity["pid"]) or False)
    monkeypatch.setattr(runner, "_open_recovery_daemon", lambda *args: pytest.fail("live-supervisor recovery"))
    result = runner.recover_stalled_worker(root, spec, state)
    assert signalled == []
    assert result["reconciled"] is False
    assert result["paid_dispatch"] is False and result["attempt_refunded"] is False


def test_changed_launcher_before_recovery_never_reaches_fence(tmp_path, monkeypatch):
    root, spec, state, record = _write_campaign(tmp_path, monkeypatch, _dead_attempt())
    reached = []
    real_lock = runner._lock

    @contextmanager
    def lock(path, name="launcher.lock", **kwargs):
        if name == "recovery.lock":
            changed = dict(record, owner_token="new-synthetic-owner")
            runner._atomic_json(state / "launcher.json", changed)
        with real_lock(path, name, **kwargs):
            yield

    monkeypatch.setattr(runner, "_lock", lock)
    monkeypatch.setattr(runner, "_fence_owned_tree", lambda record: reached.append(record) or {"fenced": False, "remaining_pids": []})
    runner.recover_stalled_worker(root, spec, state)
    assert reached == []


def test_provider_end_is_post_provider_not_fresh_provider_progress(tmp_path, monkeypatch):
    root, spec, state, _, log, _ = _real_shaped_progress(tmp_path, monkeypatch)
    with log.open('a') as handle:
        handle.write(json.dumps({'type':'end','stopReason':'end_turn'})+'\n')
    observed=runner.status(root,spec,state)
    assert observed['status']=='post_provider' and observed['healthy'] is True
    assert observed['provider_execution_verified'] is True
    assert observed['provider_progress_verified'] is False
    assert observed['provider_execution_evidence']['provider_terminal_observed'] is True


@pytest.mark.parametrize('change',['launcher','state','shutdown','live_parent','container'])
def test_full_campaign_cas_and_closure_refuse_before_native_mutation(tmp_path, monkeypatch, change):
    from tests.test_improvement_recovery import _native_recovery_campaign
    daemon,root,workspace,protected,task,claim,spec,record,inventories=_native_recovery_campaign(tmp_path,monkeypatch)
    state=daemon.state_path.parent
    before=runner._read_native_state(root,daemon.state_path)[0]
    before_claim=claim.read_bytes()
    real_lock=runner._lock
    @contextmanager
    def locked(path,name='launcher.lock',**kwargs):
        if name=='runner.lock':
            if change=='launcher':
                runner._atomic_json(state/'launcher.json',dict(record,owner_token='different-owner'))
            elif change=='state':
                from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalTaskState
                value=PortalTaskState.load(daemon.state_path)
                value.active_task_started_at=_stamp(1)
                value.save(daemon.state_path)
            elif change=='shutdown':
                value=json.loads((state/'container_shutdown.json').read_text())
                value['started_at']+=1
                runner._atomic_json(state/'container_shutdown.json',value)
            elif change=='container':
                monkeypatch.setattr(runner,'_observe_campaign_containers',lambda *args: False)
            else:
                monkeypatch.setattr(runner,'process_identity',lambda pid: record['identity'] if pid==record['identity']['pid'] else None)
        with real_lock(path,name,**kwargs):yield
    monkeypatch.setattr(runner,'_lock',locked)
    monkeypatch.setattr(runner,'_open_recovery_daemon',lambda *a,**kw:pytest.fail('CAS/closure bypass'))
    import ipfs_accelerate_py.agent_supervisor.merge.merge_queue as queue_module
    monkeypatch.setattr(queue_module,'MergeQueue',lambda *a,**kw:pytest.fail('queue preparation before closure'))
    result=runner.recover_stalled_worker(root,spec,state)
    assert result['reconciled'] is False and result['selection_performed'] is False
    assert result['paid_dispatch'] is False and result['attempt_refunded'] is False
    assert claim.read_bytes()==before_claim
    if change!='state':assert runner._read_native_state(root,daemon.state_path)[0]==before


def test_recovery_config_ignores_untrusted_native_path_and_command_overrides(tmp_path,monkeypatch):
    from tests.test_improvement_recovery import _native_recovery_campaign
    daemon,root,workspace,protected,task,claim,spec,record,_=_native_recovery_campaign(tmp_path,monkeypatch)
    config=runner._recovery_config(root,daemon.state_path.parent,
        dict(record,native_daemon={'state_path':'/foreign/state','todo_path':'/foreign/board',
            'implementation_command':'foreign-provider','worktree_root':'/foreign/root'}))
    assert config.state_path==daemon.state_path and config.todo_path==daemon.todo_path
    assert config.worktree_root==daemon.worktree_root
    assert config.implementation_command!='foreign-provider'
