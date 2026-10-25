"""Closed failure capture; explicit policy doubles never run campaign effects."""
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import threading
import time

import pytest

from integrations.ipfs_accelerate import watchdog_failure_evidence as evidence

pytestmark = [pytest.mark.no_auto_llm,pytest.mark.no_auto_network,pytest.mark.no_auto_heavy]


def _inputs():
    scope = {key:'b'+'a'*40 for key in ('repository_root_cid','policy_root','run_cid')}
    observation = {'status':'stalled','healthy':False,'manual_hold':False,'hold_reason':'',
        'completion_verified':False,'active_task_id':'CIMP-SYNTHETIC-01','active_task_cid':'b'+'b'*40,
        'attempt':1,'owner_binding_verified':True,'recovery_permitted':True,'progress_verified':False}
    status = {'status':'stalled','worker_liveness':'alive','owned_process_alive':True,
        'native_state':{'active_task_id':observation['active_task_id'],'active_task_cid':observation['active_task_cid'],
            'active_attempt':1,'active_phase':'validating'},
        'auto_rescue_activity_evidence':{'reason':'provider_deadline_expired','deadline_at':1000,
            'log_bytes':500,'frame_counts':{'thought':2,'usage':1},'text':'secret-provider-text','argv':['secret-token']},
        'provider_execution_evidence':{'frame_counts':{'thought':2,'usage':1},'log_bytes':500,
            'provider_terminal_observed':True,'text':'secret-provider-text'},
        'validation_activity_evidence':{'deadline_at':1010,'private_body':'secret-body'}}
    return {'scope':scope,'observation':observation,'status':status,
        'preflight':{'grok_binary_present':False,'secret-token':'secret-value'},'observed_at':1000}


def _records(directory):
    return sorted((directory/'failure-evidence').glob('*.json'))


def test_first_failure_is_private_closed_and_immutable_across_healthy_and_byte_changes(tmp_path):
    directory = tmp_path/'watchdog'; inputs = _inputs()
    result = evidence.capture(directory,**inputs)
    assert result['status']=='captured'
    record = directory/'failure-evidence'/result['record']
    original = record.read_bytes(); value = json.loads(original)
    assert record.stat().st_mode&0o777==0o600 and record.stat().st_nlink==1
    assert directory.stat().st_mode&0o777==0o700
    assert record.parent.stat().st_mode&0o777==0o700
    assert 'secret' not in original.decode() and 'argv' not in original.decode() and 'text' not in value
    assert value['capture_stage']=='initial_observation_before_recovery' and value['completion_authority'] is False
    assert value['preflight']=={'grok_binary_present':False}
    changed = deepcopy(inputs);changed['observed_at']=2000
    changed['status']['auto_rescue_activity_evidence']['log_bytes']=900
    changed['status']['auto_rescue_activity_evidence']['frame_counts']['thought']=25
    changed['status']['provider_execution_evidence']['frame_counts']['usage']=3
    assert evidence.capture(directory,**changed)=={'status':'already_captured','record':result['record']}
    changed['observation'].update(status='active',healthy=True)
    assert evidence.capture(directory,**changed)=={'status':'not_failure'}
    assert record.read_bytes()==original and len(_records(directory))==1
    assert not (record.parent/'.pending').exists()


def test_capacity_retains_the_first_sixteen_and_does_not_rotate_on_healthy_ticks(tmp_path):
    directory=tmp_path/'watchdog'; inputs=_inputs()
    originals={}
    for i in range(evidence.MAX_RECORDS):
        inputs['observation']['active_task_id']=inputs['status']['native_state']['active_task_id']=f'CIMP-SYNTHETIC-{i:02}'
        result=evidence.capture(directory,**inputs)
        assert result['status']=='captured'
        path=directory/'failure-evidence'/result['record'];originals[path]=path.read_bytes()
    inputs['observation']['active_task_id']=inputs['status']['native_state']['active_task_id']='CIMP-SYNTHETIC-99'
    assert evidence.capture(directory,**inputs)=={'status':'archive_full','capacity':16}
    inputs['observation'].update(status='active',healthy=True)
    assert evidence.capture(directory,**inputs)=={'status':'not_failure'}
    assert len(_records(directory))==16 and all(p.read_bytes()==raw for p,raw in originals.items())


@pytest.mark.parametrize('damage',['scope','task','cid','attempt_bool','foreign_native_task','foreign_native_attempt'])
def test_malformed_or_mixed_identity_cannot_be_archived_as_a_current_task(tmp_path,damage):
    inputs=_inputs()
    if damage=='scope':inputs['scope']['run_cid']='secret-freeform-scope'
    elif damage=='task':inputs['observation']['active_task_id']='../secret-path'
    elif damage=='cid':inputs['observation']['active_task_cid']='secret-freeform-cid'
    elif damage=='attempt_bool':inputs['observation']['attempt']=True
    elif damage=='foreign_native_task':inputs['status']['native_state']['active_task_id']='CIMP-OTHER'
    else:inputs['status']['native_state']['active_attempt']=2
    directory=tmp_path/'watchdog'
    assert evidence.capture(directory,**inputs)=={'status':'capture_unavailable'}
    assert not directory.exists()


@pytest.mark.parametrize('damage',['symlink_directory','world_directory','symlink_lock','hardlink_record','symlink_record','extra_field'])
def test_foreign_or_aliased_capture_files_are_refused_without_overwrite(tmp_path,damage):
    inputs=_inputs();directory=tmp_path/'watchdog'
    if damage=='symlink_directory':
        target=tmp_path/'foreign';target.mkdir(mode=0o700);directory.symlink_to(target)
        assert evidence.capture(directory,**inputs)['status']=='capture_unavailable' and list(target.iterdir())==[]
        return
    if damage=='world_directory':
        directory.mkdir(mode=0o755)
        assert evidence.capture(directory,**inputs)['status']=='capture_unavailable' and list(directory.iterdir())==[]
        return
    result=evidence.capture(directory,**inputs)
    record=directory/'failure-evidence'/result['record'];original=record.read_bytes()
    if damage=='symlink_lock':
        lock=record.parent/'capture.lock';lock.unlink();lock.symlink_to(record)
    elif damage=='hardlink_record':os.link(record,tmp_path/'external-link')
    elif damage=='symlink_record':
        record.unlink();target=tmp_path/'foreign.json';target.write_bytes(original);record.symlink_to(target)
    else:
        value=json.loads(original);value['private_text']='secret-body';record.write_text(json.dumps(value));record.chmod(0o600)
        original=record.read_bytes()
    assert evidence.capture(directory,**inputs)['status']=='capture_unavailable'
    assert record.read_bytes()==original


def test_busy_lock_and_retained_crash_stage_never_wait_or_erase_evidence(tmp_path):
    inputs=_inputs();directory=tmp_path/'watchdog'
    directory.mkdir(mode=0o700);archive=directory/'failure-evidence';archive.mkdir(mode=0o700)
    lock=archive/'capture.lock';lock.touch(mode=0o600)
    with lock.open('r+') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        start=time.monotonic()
        assert evidence.capture(directory,**inputs)=={'status':'capture_busy'}
        assert time.monotonic()-start<1
    pending=archive/'.pending';pending.write_bytes(b'closed-private-staging-diagnostic');pending.chmod(0o600)
    assert evidence.capture(directory,**inputs)=={'status':'capture_pending'}
    assert pending.read_bytes()==b'closed-private-staging-diagnostic' and _records(directory)==[]


def test_real_concurrent_capture_can_publish_only_one_first_snapshot(tmp_path):
    directory=tmp_path/'watchdog';inputs=_inputs();barrier=threading.Barrier(8);results=[]
    def run(i):
        item=deepcopy(inputs);item['observed_at']=1000+i
        barrier.wait();results.append(evidence.capture(directory,**item))
    threads=[threading.Thread(target=run,args=(i,)) for i in range(8)]
    for t in threads:t.start()
    for t in threads:t.join(5);assert not t.is_alive()
    assert [r['status'] for r in results].count('captured')==1
    assert all(r['status'] in {'captured','already_captured','capture_busy'} for r in results)
    assert len(_records(directory))==1 and _records(directory)[0].stat().st_nlink==1


def test_host_captures_initial_failure_before_sdk_recovery_replaces_latest_status(tmp_path,monkeypatch):
    from tests.test_campaign_watchdog import _adapter
    from ipfs_accelerate_py.agent_supervisor.rescue import campaign_watchdog as sdk
    watcher,_,view=_adapter(tmp_path,monkeypatch,state='stalled')
    view['native_state'].update(active_task_id='TASK-1',active_task_cid='b'+'b'*40,active_attempt=1,active_phase='validating')
    view['provider_execution_evidence']={'frame_counts':{'usage':4},'text':'secret-body'}
    calls=[]
    def run_once(instance):
        first=instance.observe();calls.append(first)
        view.update(status='active',healthy=True,provider_execution_evidence={'frame_counts':{'usage':20}})
        watcher.observe()
        return {'status':'recovered','reason':'verified_work_progress','provider_calls_by_watchdog':0}
    monkeypatch.setattr(sdk.CampaignProgressWatchdog,'run_once',run_once)
    report=watcher.run_once()
    assert len(calls)==1 and report['status']=='recovered' and report['native_status']=='active'
    assert report['initial_failure_capture']['status']=='captured'
    records=_records(watcher.directory);assert len(records)==1
    raw=records[0].read_bytes();record=json.loads(raw)
    assert record['failure_class']=='stalled' and record['activity_evidence']['provider_frame_counts']=={'usage':4}
    assert 'secret' not in raw.decode()
    watcher.run_once()
    assert records[0].read_bytes()==raw and len(_records(watcher.directory))==1


def test_capture_failure_cannot_replace_the_sdk_verdict_or_touch_existing_ledger(tmp_path,monkeypatch):
    from tests.test_campaign_watchdog import _adapter
    from ipfs_accelerate_py.agent_supervisor.rescue import campaign_watchdog as sdk
    watcher,_,_=_adapter(tmp_path,monkeypatch,state='stalled')
    watcher.directory.mkdir(mode=0o700)
    ledger=watcher.directory/'campaign-progress-watchdog.json';original=b'explicit-synthetic-preexisting-ledger\n'
    ledger.write_bytes(original);ledger.chmod(0o600)
    archive=watcher.directory/'failure-evidence';archive.symlink_to(tmp_path)
    calls=[]
    def run_once(instance):
        calls.append(True);instance.observe()
        return {'status':'exhausted','reason':'incident_recovery_budget_exhausted'}
    monkeypatch.setattr(sdk.CampaignProgressWatchdog,'run_once',run_once)
    report=watcher.run_once()
    assert calls==[True] and report['status']=='exhausted'
    assert report['initial_failure_capture']['status']=='capture_unavailable' and ledger.read_bytes()==original


def test_only_typed_dependency_hold_is_captured_and_healthy_never_creates_an_archive(tmp_path):
    inputs=_inputs();directory=tmp_path/'watchdog'
    inputs['observation'].update(status='active',healthy=True)
    assert evidence.capture(directory,**inputs)=={'status':'not_failure'} and not directory.exists()
    inputs['observation'].update(status='stalled',healthy=False,manual_hold=True,hold_reason='manual_hold')
    assert evidence.capture(directory,**inputs)=={'status':'not_failure'} and not directory.exists()
    inputs['observation']['hold_reason']='dependency_unavailable'
    assert evidence.capture(directory,**inputs)['status']=='captured'
    record=json.loads(_records(directory)[0].read_bytes())
    assert record['reason']==record['failure_class']=='dependency_unavailable'
