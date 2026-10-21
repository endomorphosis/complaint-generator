"""Real ownership files with fake Docker; no daemon/provider is launched."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from integrations.ipfs_accelerate import improvement_runner as runner
from integrations.ipfs_accelerate import improvement_shutdown as shutdown


pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]
IMAGE = 'sha256:' + 'a' * 64
CONTAINER = 'b' * 64
OTHER_CONTAINER = 'c' * 64


def stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    from integrations.ipfs_accelerate.improvement_plan import build_improvement_work_plan, load_spec
    repo = tmp_path / 'repository'
    spec = repo / runner.SPEC_RELATIVE
    spec.parent.mkdir(parents=True)
    spec.write_text(json.dumps({
        'schema_version': 'complaint-intake-improvement@1', 'title': 'Synthetic shutdown',
        'provider': {'router': 'ipfs_accelerate_py.llm_router', 'provider': 'grok_cli', 'model': 'grok-4.7', 'allow_fallback': False},
        'execution_policy': {'synthetic_only': True}, 'goals': [{'id': 'goal.tui', 'title': 'TUI', 'subgoals': [{'id': 'sub.tui', 'title': 'PTY'}]}],
        'tasks': [{'id': 'CIMP-TUI-01', 'title': 'Synthetic PTY', 'goal_id': 'goal.tui', 'subgoal_id': 'sub.tui',
                  'priority': 'P0', 'targets': ['tests/test_synthetic.py'], 'depends_on': [],
                  'acceptance': ['Synthetic PTY passes'], 'validation_commands': ['python -m pytest tests/test_synthetic.py'],
                  'implementation_prompt': 'Use only synthetic fixtures.'}],
    }))
    plan = build_improvement_work_plan(load_spec(spec)).plan_id
    state = tmp_path / 'epoch'
    state.mkdir(mode=0o700)
    workspace = state / 'worktrees/workspace_synthetic_01'
    workspace.mkdir(parents=True)
    started = time.time() - 60
    argv = [sys.executable, str(repo / 'scripts/run_complaint_improvement_supervisor.py'), '_run',
            '--repo-root', str(repo), '--spec', str(spec), '--state-dir', str(state),
            '--owner-token', 'synthetic-owner', '--merge-target', 'synthetic-campaign']
    identity = {'pid': 991115, 'start_ticks': 123456, 'boot_id': 'synthetic-boot',
                'session': 991115, 'process_group': 991115, 'argv': argv}
    record = {'schema_version': 'complaint-improvement-launcher@1', 'identity': identity, 'argv': argv,
              'owner_token': 'synthetic-owner', 'started_at': started, 'status': 'stopped',
              'repo_root': str(repo), 'spec_path': str(spec), 'state_dir': str(state),
              'board_path': str(repo / 'docs/task_boards/complaint_intake_task_board.md'),
              'plan_id': plan, 'provider': 'grok_cli', 'model': 'grok-4.7', 'allow_fallback': False,
              'merge_target': 'synthetic-campaign'}
    runner._atomic_json(state / 'launcher.json', record)
    event = {'type': 'implementation_started', 'event_id': 'sha256:' + 'd' * 64,
             'timestamp': stamp(started + 5), 'task_id': 'CIMP-TUI-01', 'canonical_task_cid': 'b' + 'a' * 58,
             'attempt': 1, 'worktree_path': str(workspace)}
    (state / 'complaint_intake_events.jsonl').write_text(json.dumps(event) + '\n')
    (state / 'complaint_intake_events.jsonl').chmod(0o664)
    runner._atomic_json(state / 'complaint_intake_supervisor_status.json', {
        'status': 'stopped', 'repo_root': str(repo), 'supervisor_pid': identity['pid'],
        'updated_at': stamp(started + 20), 'managed_daemon_cleanup': {'quiesced': True}})
    monkeypatch.setattr(runner, 'process_identity', lambda _pid: None)
    return SimpleNamespace(repo=repo, spec=spec, state=state, workspace=workspace,
                           record=record, event=event, started=started)


def container(campaign, identifier=CONTAINER, *, workspace=None):
    workspace = workspace or campaign.workspace
    return {'Id': identifier, 'Image': IMAGE, 'Created': stamp(campaign.started + 10),
            'Name': '/ipfs-accelerate-grok-991116-' + 'e' * 32,
            'WorkingDir': str(workspace), 'Label': 'true',
            'State': {'Status': 'running', 'Running': True, 'Restarting': False,
                      'Paused': False, 'Pid': 991116, 'StartedAt': stamp(campaign.started + 11)},
            'Mounts': [{'Type': 'bind', 'Source': str(workspace), 'Destination': str(workspace), 'RW': True}]}


class FakeDocker:
    def __init__(self, values=()):
        self.containers = {value['Id']: deepcopy(value) for value in values}
        self.effects = []
        self.calls = []
        self.ps_count = 0
        self.inspect_count = 0
        self.before_inspect = None
        self.before_ps = None
        self.failed_stop = False
        self.failed_remove = False
        self.inspect_unavailable = False
        self.timed_out = False

    def __call__(self, argv, **kwargs):
        assert argv[:2] == ['/trusted/native/docker', '--host=unix:///var/run/docker.sock']
        assert '--config' in argv
        assert kwargs['env'] == {'PATH': '/usr/bin'}
        assert 0 < kwargs['timeout'] <= 5
        op = argv[4]
        args = argv[5:]
        self.calls.append((op, args))
        if op == 'ps':
            if self.timed_out:
                raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
            self.ps_count += 1
            if self.before_ps:
                self.before_ps(self)
            return SimpleNamespace(returncode=0, stdout=''.join(value + '\n' for value in self.containers), stderr='')
        identifier = args[-1]
        if op == 'inspect':
            self.inspect_count += 1
            assert '.Config.Env' not in args[1] and '.Logs' not in args[1]
            if self.before_inspect:
                self.before_inspect(self, identifier)
            value = self.containers.get(identifier)
            if value is None or self.inspect_unavailable:
                return SimpleNamespace(returncode=1, stdout='', stderr='inspection unavailable')
            return SimpleNamespace(returncode=0, stdout=json.dumps(value), stderr='')
        self.effects.append((op, identifier))
        if op == 'stop':
            assert args == ['--time=3', identifier]
            if not self.failed_stop:
                self.containers[identifier]['State'].update(Status='exited', Running=False, Pid=0)
        elif op == 'rm':
            assert args == [identifier]  # Never --force or a mutable name.
            if not self.failed_remove:
                self.containers.pop(identifier)
        else:
            pytest.fail('unexpected Docker operation')
        return SimpleNamespace(returncode=0, stdout=identifier + '\n', stderr='')


@pytest.fixture
def docker(monkeypatch):
    fake = FakeDocker()
    native = SimpleNamespace(_docker_isolation_binary=lambda: '/trusted/native/docker',
        _docker_ordinary_task_toolchain_image_id=lambda *_args, **_kwargs: IMAGE,
        _docker_control_env=lambda: {'PATH': '/usr/bin'})
    monkeypatch.setattr(shutdown, '_native_runtime', lambda: native)
    monkeypatch.setattr(shutdown.subprocess, 'run', fake)
    return fake, native


def close(campaign, **kwargs):
    return shutdown.close_campaign_containers(campaign.state, campaign.record, **kwargs)


def test_historical_stopped_parent_closes_only_exact_owned_container(campaign, docker):
    fake, _ = docker
    fake.containers = {CONTAINER: container(campaign),
                       OTHER_CONTAINER: container(campaign, OTHER_CONTAINER, workspace=campaign.repo / 'other-workspace')}
    original_events = (campaign.state / 'complaint_intake_events.jsonl').read_bytes()
    result = close(campaign)
    assert result['status'] == 'stopped' and result['quiesced'] is True
    assert fake.effects == [('stop', CONTAINER), ('rm', CONTAINER)]
    assert list(fake.containers) == [OTHER_CONTAINER]
    assert (campaign.state / 'complaint_intake_events.jsonl').read_bytes() == original_events
    receipt = json.loads((campaign.state / shutdown.RECEIPT_NAME).read_text())
    assert receipt['plan_id'] == campaign.record['plan_id']
    assert receipt['owner_token_sha256'] == hashlib.sha256(campaign.record['owner_token'].encode()).hexdigest()
    assert receipt['containers'][0]['event_id'] == campaign.event['event_id']
    assert receipt['containers'][0]['created'] == stamp(campaign.started + 10)
    assert receipt['completion_authority'] is False and receipt['provider_callback_settled'] is False
    assert receipt['attempt_refunded'] is False and receipt['manual_holds_preserved'] is True


def test_legacy_process_only_record_never_acquires_docker_authority(tmp_path, monkeypatch):
    monkeypatch.setattr(shutdown, '_native_runtime', lambda: pytest.fail('legacy Docker call'))
    result = shutdown.close_campaign_containers(tmp_path, {'identity': {'pid': 1234}, 'started_at': time.time()})
    assert result['applicable'] is False and not result['quiesced']


@pytest.mark.parametrize('field,value', [('plan_id', 'other-plan'), ('state_dir', '/another/epoch'),
    ('repo_root', '/another/repository'), ('allow_fallback', True)])
def test_changed_launcher_binding_has_no_docker_effect(campaign, docker, field, value):
    campaign.record[field] = value
    runner._atomic_json(campaign.state / 'launcher.json', campaign.record)
    result = close(campaign)
    assert result['status'] == 'stop_incomplete' and not docker[0].calls


def test_launcher_file_changed_or_symlinked_has_no_authority(campaign, docker):
    owner = campaign.state / 'launcher.json'
    moved = campaign.state / 'owner-copy.json'
    owner.rename(moved)
    owner.symlink_to(moved)
    assert close(campaign)['status'] == 'stop_incomplete'
    assert not docker[0].calls


@pytest.mark.parametrize('mutation', ['old_event', 'escaping_workspace', 'symlink_workspace', 'wrong_image', 'missing_label', 'before_launch', 'future_created', 'missing_mount'])
def test_unbound_campaign_container_never_receives_effect(campaign, docker, mutation):
    fake, _ = docker
    value = container(campaign)
    if mutation == 'old_event':
        campaign.event['timestamp'] = stamp(campaign.started - 10)
        (campaign.state / 'complaint_intake_events.jsonl').write_text(json.dumps(campaign.event) + '\n')
    elif mutation == 'escaping_workspace':
        campaign.event['worktree_path'] = str(campaign.repo / 'elsewhere')
        (campaign.state / 'complaint_intake_events.jsonl').write_text(json.dumps(campaign.event) + '\n')
    elif mutation == 'symlink_workspace':
        campaign.workspace.rmdir()
        campaign.workspace.symlink_to(campaign.repo, target_is_directory=True)
    elif mutation == 'wrong_image':
        value['Image'] = 'sha256:' + 'f' * 64
    elif mutation == 'missing_label':
        value['Label'] = None
    elif mutation == 'before_launch':
        value['Created'] = stamp(campaign.started - 1)
    elif mutation == 'future_created':
        value['Created'] = stamp(time.time() + 60)
    elif mutation == 'missing_mount':
        value['Mounts'] = []
    fake.containers[CONTAINER] = value
    assert close(campaign)['status'] == 'stop_incomplete'
    assert not fake.effects


def test_container_immutable_identity_is_rechecked_before_stop(campaign, docker):
    fake, _ = docker
    fake.containers[CONTAINER] = container(campaign)
    def replace_identity(fake, identifier):
        if fake.inspect_count == 2:
            fake.containers[identifier]['Created'] = stamp(campaign.started + 12)
    fake.before_inspect = replace_identity
    assert close(campaign)['status'] == 'stop_incomplete'
    assert not fake.effects


@pytest.mark.parametrize('failure', ['inspection', 'stop', 'remove', 'image', 'docker', 'timeout'])
def test_unknown_docker_closure_cannot_claim_stopped(campaign, docker, failure):
    fake, native = docker
    fake.containers[CONTAINER] = container(campaign)
    if failure == 'inspection': fake.inspect_unavailable = True
    elif failure == 'stop': fake.failed_stop = True
    elif failure == 'remove': fake.failed_remove = True
    elif failure == 'image': native._docker_ordinary_task_toolchain_image_id = lambda *_args, **_kwargs: ''
    elif failure == 'docker': native._docker_isolation_binary = lambda: ''
    elif failure == 'timeout': fake.timed_out = True
    result = close(campaign)
    assert result['status'] == 'stop_incomplete' and result['quiesced'] is False


def test_inventory_is_bounded(campaign, docker):
    fake, _ = docker
    fake.containers = {f'{number:064x}': {} for number in range(shutdown.MAX_CONTAINERS + 1)}
    assert close(campaign)['status'] == 'stop_incomplete'
    assert not fake.effects


@pytest.mark.parametrize('empty_stream', [False, True])
def test_startup_without_task_events_still_observes_empty_docker_inventory(campaign, docker, empty_stream):
    events = campaign.state / 'complaint_intake_events.jsonl'
    if empty_stream:
        events.write_text('')
    else:
        events.unlink()
    result = close(campaign)
    assert result['quiesced'] is True
    assert docker[0].ps_count == 2 and not docker[0].effects


def test_dead_parent_without_owned_shutdown_evidence_is_incomplete(campaign, docker):
    (campaign.state / 'complaint_intake_supervisor_status.json').unlink()
    assert close(campaign)['status'] == 'stop_incomplete'
    assert not docker[0].calls


def test_second_inventory_closes_container_created_during_parent_stop(campaign, docker):
    fake, _ = docker
    def late_create(fake):
        if fake.ps_count == 2:
            fake.containers[CONTAINER] = container(campaign)
    fake.before_ps = late_create
    result = close(campaign, parent_quiesced=True)
    assert result['quiesced'] is True
    assert fake.effects == [('stop', CONTAINER), ('rm', CONTAINER)]


def test_optional_retention_requires_observed_nonrunning_state(campaign, docker):
    fake, _ = docker
    fake.containers[CONTAINER] = container(campaign)
    result = close(campaign, remove_stopped=False)
    assert result['quiesced'] is True
    assert fake.effects == [('stop', CONTAINER)]
    assert fake.containers[CONTAINER]['State']['Running'] is False
    assert all(not item['removed'] for item in result['containers'])


def test_stop_checks_docker_even_when_original_launcher_is_dead(campaign, docker):
    fake, _ = docker
    fake.containers[CONTAINER] = container(campaign)
    result = runner.stop(campaign.state, timeout=0)
    assert result['status'] == 'stopped' and result['signalled'] is False
    assert fake.effects == [('stop', CONTAINER), ('rm', CONTAINER)]


def test_stop_never_returns_stopped_when_container_fence_is_unknown(campaign, docker):
    fake, _ = docker
    fake.containers[CONTAINER] = container(campaign)
    fake.failed_stop = True
    assert runner.stop(campaign.state, timeout=0)['status'] == 'stop_incomplete'


def test_live_process_stop_checks_containers_after_birth_bound_signals(campaign, docker, monkeypatch):
    fake, _ = docker
    current = {campaign.record['identity']['pid']: campaign.record['identity']}
    monkeypatch.setattr(runner, 'process_identity', lambda pid: current.get(pid))
    monkeypatch.setattr(runner, '_descendants', lambda _identity: [])
    def signal_birth(identity, _signal):
        current.pop(identity['pid'], None)
        fake.containers[CONTAINER] = container(campaign)
        return True
    monkeypatch.setattr(runner, '_signal_birth', signal_birth)
    result = runner.stop(campaign.state, timeout=0)
    assert result['status'] == 'stopped' and result['signalled'] is True
    assert fake.effects == [('stop', CONTAINER), ('rm', CONTAINER)]
