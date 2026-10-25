"""Private synthetic campaigns, real Native claims/events and inert Popen.

No model, task completion, merge, retry/refund or live campaign is invoked.
The provider emits synthetic NDJSON under Native's actual rescue producer.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import threading
import time

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate import auto_rescue_activity as activity

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]


def _stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


@contextmanager
def _native_world(tmp_path, monkeypatch, *, frame_kind="thought"):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_runtime as runtime
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import portal_task_state_control_plane as plane
    from integrations.ipfs_accelerate.reconciliation_activity import catalog_path
    root = Path(runner.__file__).resolve().parents[2]
    spec = root / "docs/task_boards/complaint_gui_collaboration_spec.json"
    _, artifacts = runner._campaign_spec(root, spec)
    campaign = tmp_path / "campaign"; campaign.mkdir(mode=0o700)
    workspace = campaign / "worktrees/inert-rescue"; workspace.mkdir(parents=True)
    daemon = native.PortalImplementationDaemon(todo_path=root / artifacts.board_relative,
        state_path=campaign / (runner.STATE_PREFIX + "_task_state.json"),
        strategy_path=campaign / (runner.STATE_PREFIX + "_strategy.json"),
        events_path=campaign / (runner.STATE_PREFIX + "_events.jsonl"),
        repo_root=root, task_header_prefix=runner.TASK_PREFIX,
        worktree_root=campaign / "worktrees", board_namespace=artifacts.board_namespace,
        implementation_timeout=runner.TIMEOUT_SECONDS, implement=False)
    tasks = daemon._load_tasks(); daemon._register_task_identities(tasks)
    task = next(task for task in tasks if task.task_id == "CIMP-GUI-60")
    identity = daemon._identity_for_task(task)
    now = time.time(); started = _stamp(now)
    lease = daemon._build_implementation_lock_metadata(task, 1, started)
    claim = daemon._build_implementation_task_claim_metadata(task, 1, started)
    lease_path = daemon._implementation_lock_path()
    claim_path = daemon._implementation_task_claim_path(task.task_id, canonical_task_cid=identity.canonical_task_cid)
    assert daemon._try_acquire_implementation_lock(lease_path, lease)[0]
    assert daemon._try_acquire_implementation_task_claim(claim_path, claim)[0]
    log = campaign / "implementation_logs" / (task.task_id.lower() + "-attempt-1-" + "a"*32 + ".log")
    log.parent.mkdir(); log.write_text(f"Task: {task.task_id} Synthetic inert repair\nStarted: {started}\nWorkspace: {workspace}\n")
    log.chmod(0o600)
    # A real inert primary stream, including its terminal frame, precedes the
    # real Native repair producer. These are not manufactured birth receipts.
    with log.open("a") as handle:
        runtime.run_process_group_stream([sys.executable, "-I", "-B", "-c",
            "import json; print(json.dumps({'type':'usage','usage':{}}),flush=True); print(json.dumps({'type':'end'}),flush=True)"],
            cwd=workspace, stdout=handle, env={}, inherit_environment=False, timeout_seconds=10)
    daemon._record_event("implementation_started", {"task_id": task.task_id, "attempt": 1,
        "worktree_path": str(workspace), "log_path": str(log), "execution_mode": "model-assisted"})
    state = native.PortalTaskState()
    for key, value in {"active_task_id":task.task_id,"active_task_cid":identity.canonical_task_cid,
        "active_task_key":identity.canonical_task_key,"active_attempt":1,"implementation_in_progress":True,
        "active_phase":"validating","active_task_started_at":_stamp(now-300),"active_phase_started_at":started,
        "active_worktree_path":str(workspace),"active_log_path":str(log),
        "last_implementation_task_id":task.task_id,"last_implementation_task_cid":identity.canonical_task_cid,
        "last_implementation_task_key":identity.canonical_task_key,"last_implementation_started_at":started,
        "last_implementation_worktree_path":str(workspace),"last_implementation_log_path":str(log),
        "owner_process_birth":runtime.read_process_birth(os.getpid()).to_dict()}.items():
        setattr(state,key,value)
    state.implementation_attempts={task.task_id:1};state.implementation_attempts_by_cid={identity.canonical_task_cid:1}
    target,_ = catalog_path(runner,campaign);plane.bind_task_state_control_plane(daemon.state_path,str(target))
    state.save(daemon.state_path)
    body=runner._validation_activity_snapshot(campaign)["body"]
    launcher={"schema_version":"complaint-improvement-launcher@1","repo_root":str(root),
        "state_dir":str(campaign),"spec_path":str(spec),"board_path":str(root/artifacts.board_relative),
        "plan_id":runner._requested_plan_id(spec),"provider":"grok_cli","model":runner.MODEL,"allow_fallback":False}
    runner._atomic_json(campaign/"launcher.json",launcher)
    runtime.write_supervised_child_identity(campaign/(runner.STATE_PREFIX+"_managed_daemon.identity.json"),
        pid=os.getpid(), command=runtime.read_process_command_argv(os.getpid()), owner_scope={
        "repo_root":str(root),"state_dir":str(campaign),"state_prefix":runner.STATE_PREFIX,
        "todo_path":str(root/artifacts.board_relative),"daemon_entrypoint":str(Path(runner.__file__).resolve())})
    # Only planning/output-validation are synthetic here; the actual rescue
    # body owns its real start event, child, stdout, budget and cleanup.
    monkeypatch.setattr(daemon,"_expected_outputs_present_on_disk",lambda *a:True)
    monkeypatch.setattr(daemon,"_dirty_in_scope_declared_output_paths",lambda *a:())
    monkeypatch.setattr(daemon,"_stage_declared_candidate_outputs",lambda *a:())
    monkeypatch.setattr(daemon,"_run_validation_with_candidate_binding",lambda *a,**kw:{"passed":False,"reason":"synthetic_validation_not_performed"})
    monkeypatch.setattr(daemon,"_apply_implementation_failure_review",lambda **kw:dict(kw["validation_result"]))
    program = """import json,pathlib,sys,time
sys.stdin.read()
root=pathlib.Path.cwd()
kind=sys.argv[1]
while not (root/'release').exists():
 frame={'type':kind,'text':'synthetic inert provider output'}
 if kind=='usage':frame['usage']={}
 print(json.dumps(frame),flush=True)
 (root/'ready').touch()
 time.sleep(0.025)
print(json.dumps({'type':'end'}),flush=True)
"""
    results, errors = [], []
    def run():
        try:
            results.append(daemon._automatic_implementation_rescue(task=task,attempt=1,workspace_path=workspace,
                branch_name="synthetic-inert-rescue",baseline_ref="a"*40,
                validation_result={"passed":False,"reason":"declared_validation_failed","error":"validation_command_failed",
                    "failed_commands":["synthetic validation"],"failure_review":{"decision":"guide_rescue","reason_codes":["validation_command_failed"]}},
                log_path=log,state=state,command=[sys.executable,"-I","-B","-c",program,frame_kind],
                base_prompt="Synthetic inert provider fixture; no model.",provider_deadline=time.monotonic()+runner.TIMEOUT_SECONDS))
        except BaseException as exc:errors.append(exc)
    worker=threading.Thread(target=run,daemon=True);worker.start()
    deadline=time.monotonic()+15
    while not (workspace/"ready").exists() and worker.is_alive() and time.monotonic()<deadline:time.sleep(.01)
    try:
        assert (workspace/"ready").exists(), errors
        yield {"root":root,"campaign":campaign,"workspace":workspace,"daemon":daemon,"task":task,
            "body":body,"log":log,"lease_path":lease_path,"claim_path":claim_path,"worker":worker}
    finally:
        (workspace/"release").touch();worker.join(15)
        assert not worker.is_alive() and not errors, errors
        assert results and not results[0].get("passed"), "Fixture cannot manufacture completion."
        assert daemon._release_implementation_task_claim(claim_path,claim)
        assert daemon._release_implementation_lock(lease_path,lease)


@pytest.mark.parametrize("kind",["thought","text","usage","tool_call","tool_call_update"])
def test_actual_native_rescue_producer_has_owned_bounded_activity(tmp_path,monkeypatch,kind):
    with _native_world(tmp_path,monkeypatch,frame_kind=kind) as world:
        result=activity.observe(runner,world["root"],world["campaign"],world["body"],now_ts=time.time())
        assert result["activity_verified"] is True,result
        assert result["work_progress_verified"] is (kind in activity._WORK)
        assert result["reason"]=="bounded_native_rescue_activity"
        assert result["deadline_at"] <= runner._event_timestamp({"timestamp":world["body"]["active_task_started_at"]})+runner.TIMEOUT_SECONDS
        assert result["provider_birth"]["parent_pid"]==os.getpid()
        assert result["completion_authority"] is False


def test_actual_growing_stdout_preserves_complete_owned_prefix(tmp_path,monkeypatch):
    with _native_world(tmp_path,monkeypatch) as world:
        real=os.pread; appended=[]
        def read(descriptor,size,offset):
            data=real(descriptor,size,offset)
            if not appended:
                current=world["log"].stat().st_size
                deadline=time.monotonic()+2
                while world["log"].stat().st_size==current and time.monotonic()<deadline:time.sleep(.005)
                assert world["log"].stat().st_size>current
                appended.append(True)
            return data
        monkeypatch.setattr(activity.os,"pread",read)
        raw, info=activity._append_prefix(world["log"])
        assert len(raw)==info.st_size and appended
        assert world["log"].stat().st_size>len(raw)


def test_primary_terminal_followed_by_real_native_thought_is_not_work_progress(tmp_path,monkeypatch):
    with _native_world(tmp_path,monkeypatch) as world:
        binding=runner._attempt_binding(world["body"])
        original=runner._owned_attempt_log_evidence(world["daemon"].events_path,world["campaign"],binding,
            started_at=runner._event_timestamp({"timestamp":world["body"]["active_task_started_at"]})-1,now=time.time())
        # This is a real producer reproduction of the old reader's condition,
        # not a claim about the uncaptured actual Task35 rejection branch.
        assert original is None or original["provider_terminal_observed"] is True
        current=activity.observe(runner,world["root"],world["campaign"],world["body"],now_ts=time.time())
        assert current["activity_verified"] is True and current["work_progress_verified"] is False,current
