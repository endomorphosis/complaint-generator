"""Close only Docker workers bound to one recorded complaint campaign launch.

This is an operator shutdown observation, not provider callback settlement or
task completion. Unknown ownership or Docker state cannot establish closure.
"""

from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
from typing import Any, Mapping


SCHEMA = 'complaint-improvement-container-shutdown@1'
RECEIPT_NAME = 'container_shutdown.json'
MAX_CONTAINERS = 32
MAX_EVENTS_BYTES = 16_000_000
MAX_INSPECT_BYTES = 262_144
_CID = re.compile(r'[0-9a-f]{64}\Z')
_EVENT_ID = re.compile(r'sha256:[0-9a-f]{64}\Z')
_TASK_CID = re.compile(r'b[a-z2-7]{30,120}\Z')
_INSPECT = (
    '{"Id":{{json .Id}},"Image":{{json .Image}},"Created":{{json .Created}},'
    '"Name":{{json .Name}},"WorkingDir":{{json .Config.WorkingDir}},'
    '"Label":{{json (index .Config.Labels "ipfs_accelerate.grok_isolation")}},'
    '"State":{{json .State}},"Mounts":{{json .Mounts}}}'
)


def _timestamp(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError('invalid shutdown timestamp')
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('shutdown timestamps require a timezone')
        result = parsed.timestamp()
    else:
        raise ValueError('invalid shutdown timestamp')
    if not math.isfinite(result) or result <= 0:
        raise ValueError('invalid shutdown timestamp')
    return result


def _confined_workspace(value: Any, state_dir: Path, *, worktree_root: Path | None = None) -> Path:
    if not isinstance(value, str):
        raise ValueError('worker workspace missing')
    path = Path(value)
    parent = worktree_root if worktree_root is not None else state_dir / 'worktrees'
    if (not path.is_absolute() or path.parent != parent or path.resolve() != path
            or parent.is_symlink() or not re.fullmatch(r'workspace_[A-Za-z0-9_\-]{1,100}', path.name)):
        raise ValueError('worker workspace is not a direct confined campaign worktree')
    return path


def _native_runtime():
    from ipfs_accelerate_py.agent_supervisor.runtime import grok_cli_runner
    return grok_cli_runner


def _context(state_dir: Path, record: Mapping[str, Any]) -> dict[str, Any] | None:
    # Older unit-test/launcher records did not establish repo/plan ownership.
    # They retain their process-only behavior and acquire no Docker authority.
    if not any(key in record for key in ('schema_version', 'repo_root', 'plan_id', 'state_dir')):
        return None
    from . import improvement_recovery as recovery
    from .improvement_plan import BOARD_RELATIVE
    from .improvement_runner import recorded_worktree_root
    if record.get('schema_version') != 'complaint-improvement-launcher@1':
        raise ValueError('full launcher ownership record required')
    if state_dir.resolve() != state_dir:
        raise ValueError('campaign state directory traverses a symlink')
    state_stat = state_dir.stat()
    if state_stat.st_uid != os.getuid() or state_stat.st_mode & 0o077:
        raise ValueError('campaign state directory must be owned and private')
    raw = recovery._owned_bytes(state_dir / 'launcher.json')
    if json.loads(raw) != record:
        raise ValueError('launcher ownership changed')
    repo = Path(str(record.get('repo_root') or ''))
    spec = Path(str(record.get('spec_path') or ''))
    if (not repo.is_absolute() or repo.resolve() != repo or record.get('state_dir') != str(state_dir)
            or not spec.is_absolute() or spec.resolve() != spec or not spec.is_relative_to(repo)
            or record.get('board_path') != str(repo / BOARD_RELATIVE)):
        raise ValueError('launcher repository/epoch paths differ')
    plan = recovery._plan_id(repo, spec)
    if record.get('plan_id') != plan or record.get('provider') != 'grok_cli' or record.get('model') != 'grok-4.7' or record.get('allow_fallback') is not False:
        raise ValueError('launcher plan/provider binding differs')
    identity, argv, token = record.get('identity'), record.get('argv'), record.get('owner_token')
    if not isinstance(identity, dict) or not isinstance(argv, list) or not isinstance(token, str) or not token:
        raise ValueError('launcher historical process identity missing')
    worktree_root, root_binding = recorded_worktree_root(record, state_dir)
    pid = identity.get('pid')
    expected = [argv[0] if argv else '', str(repo / 'scripts/run_complaint_improvement_supervisor.py'), '_run',
                '--repo-root', str(repo), '--spec', str(spec), '--state-dir', str(state_dir),
                '--owner-token', token, '--merge-target', record.get('merge_target')]
    if root_binding is not None:
        expected.extend(['--worktree-root', str(worktree_root)])
    if (argv != expected or identity.get('argv') != argv or type(pid) is not int or pid <= 1
            or identity.get('session') != pid or identity.get('process_group') != pid
            or type(identity.get('start_ticks')) is not int or identity['start_ticks'] <= 0
            or not isinstance(identity.get('boot_id'), str) or not identity['boot_id']
            or not Path(str(argv[0])).is_absolute() or not record.get('merge_target')):
        raise ValueError('launcher historical process/argv binding differs')
    started = _timestamp(record.get('started_at'))
    if started > time.time():
        raise ValueError('launcher start time is in the future')
    return {'repo_root': str(repo), 'plan_id': plan, 'state_dir': str(state_dir),
            'worktree_root': str(worktree_root), 'worktree_root_binding': root_binding,
            'started_at': started, 'owner_token_sha256': hashlib.sha256(token.encode()).hexdigest(),
            'launcher_sha256': hashlib.sha256(raw).hexdigest()}


def _events(state_dir: Path, started_at: float, *, worktree_root: Path | None = None) -> tuple[dict[Path, list[dict[str, Any]]], str]:
    from .improvement_recovery import _owned_bytes
    path = state_dir / 'complaint_intake_events.jsonl'
    if not os.path.lexists(path):
        return {}, ''
    if path.lstat().st_size == 0:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(descriptor)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                    or before.st_nlink != 1 or before.st_mode & 0o002 or before.st_size != 0):
                raise ValueError('empty native event stream ownership differs')
            current = path.lstat()
            if any(getattr(before, field) != getattr(current, field)
                   for field in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')):
                raise ValueError('empty native event stream changed')
        finally:
            os.close(descriptor)
        return {}, hashlib.sha256(b'').hexdigest()
    # Native legacy event streams use the operator's group-writable umask.
    # The validated 0700 epoch prevents other users reaching these files.
    raw = _owned_bytes(path, MAX_EVENTS_BYTES, legacy_group_write=True)
    workspaces: dict[Path, list[dict[str, Any]]] = {}
    identities = set()
    for line in raw.splitlines():
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError('native event is not an object')
        if event.get('type') != 'implementation_started':
            continue
        stamp = _timestamp(event.get('timestamp'))
        if stamp < started_at:
            continue
        event_id, cid = event.get('event_id'), event.get('canonical_task_cid')
        if (not isinstance(event_id, str) or not _EVENT_ID.fullmatch(event_id)
                or event_id in identities or not isinstance(cid, str) or not _TASK_CID.fullmatch(cid)
                or not re.fullmatch(r'CIMP-[A-Z]+-\d+', str(event.get('task_id') or ''))
                or type(event.get('attempt')) is not int or event['attempt'] < 1
                or stamp > time.time()):
            raise ValueError('native start event identity differs')
        identities.add(event_id)
        workspace = _confined_workspace(event.get('worktree_path'), state_dir, worktree_root=worktree_root)
        workspaces.setdefault(workspace, []).append({'event_id': event_id, 'started_at': stamp,
            'task_id': event['task_id'], 'canonical_task_cid': cid, 'attempt': event['attempt']})
        if len(identities) > 1024:
            raise ValueError('native start event inventory exceeds bound')
    return workspaces, hashlib.sha256(raw).hexdigest()


def _parent_closed(state_dir: Path, record: Mapping[str, Any], context: Mapping[str, Any], supplied: bool) -> None:
    from . import improvement_runner as runner
    from .improvement_recovery import _object
    birth = record['identity']
    current = runner.process_identity(birth['pid'])
    if current and all(current.get(key) == birth.get(key) for key in ('pid', 'start_ticks', 'boot_id')):
        raise ValueError('recorded campaign parent is still alive')
    if supplied:
        return
    heartbeat = _object(state_dir / 'complaint_intake_supervisor_status.json', legacy_group_write=True)
    if (heartbeat.get('status') != 'stopped' or heartbeat.get('repo_root') != context['repo_root']
            or heartbeat.get('supervisor_pid') != birth['pid']
            or _timestamp(heartbeat.get('updated_at')) < context['started_at']
            or (heartbeat.get('managed_daemon_cleanup') or {}).get('quiesced') is not True):
        raise ValueError('historical campaign lacks current owned shutdown evidence')


def close_campaign_containers(state_dir: Path, record: Mapping[str, Any], *, parent_quiesced: bool = False,
                             remove_stopped: bool = True, timeout_seconds: float = 25.0) -> dict[str, Any]:
    """Fence exact owned containers after the recorded parent is quiescent.

    All Docker calls use a trusted native CLI, local socket and empty config.
    Full CID plus immutable Created/Image/workspace identity is rechecked before
    each effect; name or PID alone never grants authority.
    """
    state_dir = Path(state_dir)
    result: dict[str, Any] = {'schema': SCHEMA, 'applicable': True, 'quiesced': False,
        'status': 'stop_incomplete', 'containers': [], 'completion_authority': False,
        'provider_callback_settled': False, 'attempt_refunded': False, 'manual_holds_preserved': True}
    context = None
    deadline = time.monotonic() + max(1.0, min(float(timeout_seconds), 30.0))
    try:
        context = _context(state_dir, record)
        if context is None:
            return {**result, 'applicable': False, 'status': 'not_applicable', 'reason': 'legacy_process_only_record'}
        result.update(context)
        _parent_closed(state_dir, record, context, parent_quiesced)
        starts, event_sha = _events(state_dir, context['started_at'], worktree_root=Path(context['worktree_root']))
        result['event_log_sha256'] = event_sha
        native = _native_runtime()
        docker = native._docker_isolation_binary()
        if not docker:
            raise ValueError('trusted Docker inspection unavailable')
        with tempfile.TemporaryDirectory(prefix='complaint-docker-shutdown-config-') as temporary:
            config = Path(temporary)
            image = native._docker_ordinary_task_toolchain_image_id(docker, docker_config=config)
            if not isinstance(image, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
                raise ValueError('ordinary worker image source qualification unavailable')
            command = [docker, '--host=unix:///var/run/docker.sock', '--config', temporary]

            def run(arguments):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError('Docker shutdown deadline exceeded')
                completed = subprocess.run(command + arguments, stdin=subprocess.DEVNULL, text=True,
                    capture_output=True, timeout=min(5.0, remaining), check=False, env=native._docker_control_env())
                if len(completed.stdout or '') > MAX_INSPECT_BYTES or len(completed.stderr or '') > MAX_INSPECT_BYTES:
                    raise ValueError('Docker shutdown observation exceeds bound')
                return completed

            def inventory():
                observed = run(['ps', '-a', '--no-trunc', '--filter', 'label=ipfs_accelerate.grok_isolation=true', '--format', '{{.ID}}'])
                identifiers = observed.stdout.splitlines()
                if observed.returncode or len(identifiers) > MAX_CONTAINERS or len(set(identifiers)) != len(identifiers) or any(not _CID.fullmatch(value) for value in identifiers):
                    raise ValueError('Docker shutdown inventory unavailable or unbounded')
                return identifiers

            def inspect(identifier):
                observed = run(['inspect', '--format', _INSPECT, identifier])
                if observed.returncode:
                    # CLI errors cannot distinguish absence from unavailable
                    # daemon/permissions. Require a successful fresh inventory.
                    if identifier not in inventory():
                        return None
                    raise ValueError('Docker container inspection unavailable')
                value = json.loads(observed.stdout)
                if not isinstance(value, dict) or value.get('Id') != identifier:
                    raise ValueError('Docker container identity changed')
                return value

            def bound(value):
                workspace_text = value.get('WorkingDir')
                mounts = value.get('Mounts')
                if not isinstance(mounts, list) or len(mounts) > 256:
                    raise ValueError('Docker mount observation unavailable')
                scope = Path(context['worktree_root'])
                possible = [workspace_text, *(item.get('Source') for item in mounts if isinstance(item, dict))]
                touches = any(isinstance(item, str) and Path(item).is_absolute() and Path(item).is_relative_to(scope) for item in possible)
                if not touches:
                    return None
                workspace = _confined_workspace(workspace_text, state_dir, worktree_root=scope)
                created = _timestamp(value.get('Created'))
                candidates = [start for start in starts.get(workspace, ()) if start['started_at'] <= created]
                if (value.get('Image') != image or value.get('Label') != 'true'
                        or not re.fullmatch(r'/ipfs-accelerate-grok-\d+-[0-9a-f]{32}', str(value.get('Name') or ''))
                        or created < context['started_at'] or created > time.time() or not candidates
                        or not any(mount.get('Type') == 'bind' and mount.get('Source') == str(workspace)
                                   and mount.get('Destination') == str(workspace) and mount.get('RW') is True
                                   for mount in mounts if isinstance(mount, dict))):
                    raise ValueError('campaign container is not bound to a qualified native start event')
                event = max(candidates, key=lambda item: item['started_at'])
                return {'container_id': value['Id'], 'created': value['Created'], 'image_id': image,
                        'workspace': str(workspace), **event}

            def unchanged(identifier, identity):
                from .improvement_recovery import _owned_bytes
                if hashlib.sha256(_owned_bytes(state_dir / 'launcher.json')).hexdigest() != context['launcher_sha256']:
                    raise ValueError('launcher ownership changed before Docker effect')
                from .improvement_runner import recorded_worktree_root
                if recorded_worktree_root(record, state_dir) != (Path(context['worktree_root']), context['worktree_root_binding']):
                    raise ValueError('worktree root ownership changed before Docker effect')
                _parent_closed(state_dir, record, context, parent_quiesced)
                if _events(state_dir, context['started_at'], worktree_root=Path(context['worktree_root']))[1] != event_sha:
                    raise ValueError('native start evidence changed before Docker effect')
                value = inspect(identifier)
                if value is not None and bound(value) != identity:
                    raise ValueError('container immutable identity changed before Docker effect')
                return value

            def stopped(value):
                state = value.get('State')
                if not isinstance(state, dict) or type(state.get('Pid')) is not int or type(state.get('Running')) is not bool:
                    raise ValueError('Docker running state unavailable')
                return (state['Running'] is False and state['Pid'] == 0
                        and state.get('Restarting') is False and state.get('Paused') is False
                        and state.get('Status') in {'exited', 'dead', 'created'})

            # Inventory again after closure to catch a create request that
            # reached Docker during the parent's graceful shutdown interval.
            for _pass in range(2):
                for identifier in inventory():
                    value = inspect(identifier)
                    if value is None:
                        continue
                    identity = bound(value)
                    if identity is None:
                        continue
                    value = unchanged(identifier, identity)
                    if value is None:
                        continue
                    if not stopped(value):
                        run(['stop', '--time=3', identifier])
                        value = unchanged(identifier, identity)
                        if value is not None and not stopped(value):
                            raise ValueError('owned Docker worker did not stop')
                    removed = value is None
                    if value is not None and remove_stopped:
                        value = unchanged(identifier, identity)
                        if value is not None:
                            if not stopped(value):
                                raise ValueError('owned Docker worker restarted before removal')
                            run(['rm', identifier])
                            removed = inspect(identifier) is None
                            if not removed:
                                raise ValueError('owned Docker worker removal is unverified')
                    result['containers'].append({**identity, 'quiesced': True, 'removed': removed})
            result.update(status='stopped', quiesced=True, reason='owned_container_closure_verified')
    except (OSError, ValueError, TypeError, RuntimeError, subprocess.TimeoutExpired) as error:
        result['reason'] = str(error) if isinstance(error, ValueError) else type(error).__name__
    if context is not None:
        from .improvement_runner import _atomic_json
        try:
            _atomic_json(state_dir / RECEIPT_NAME, result)
        except OSError:
            result.update(status='stop_incomplete', quiesced=False, reason='shutdown_receipt_unavailable')
    return result
