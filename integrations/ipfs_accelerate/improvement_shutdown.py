"""Close only Docker workers bound to one recorded complaint campaign launch.

This is an operator shutdown observation, not provider callback settlement or
task completion. Unknown ownership or Docker state cannot establish closure.
"""

from datetime import datetime, timezone
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


def _sealed_managed_session_closed(state_dir: Path, record: Mapping[str, Any], context: Mapping[str, Any]) -> None:
    """Observe retained native markers after an independently performed fence.

    The native record stores the original parent PID, not its start ticks.
    Bind it to the same-boot launch and a strictly later child birth; neither
    numeric PID may currently exist, including as a different process birth.
    This verifier never signals, removes markers or manufactures a heartbeat.
    """
    from . import improvement_runner as runner
    from .improvement_recovery import _owned_bytes
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_runtime as native

    parent = record['identity']
    pid_path = state_dir / f'{runner.STATE_PREFIX}_managed_daemon.pid'
    identity_path = native.supervised_child_identity_path(pid_path)
    def markers():
        result = {}
        for path in (pid_path, identity_path):
            first = path.lstat()
            raw = _owned_bytes(path, 65_536, legacy_group_write=True)
            last = path.lstat()
            fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            key = tuple(getattr(first, name) for name in fields)
            if key != tuple(getattr(last, name) for name in fields):
                raise ValueError('retained native daemon marker changed during read')
            result[path] = (raw, key)
        return result

    snapshot = markers()
    before = {path: value[0] for path, value in snapshot.items()}
    payload = json.loads(before[identity_path])
    identity = native.SupervisedChildIdentity.from_dict(payload)
    if identity is None or identity.to_dict() != payload:
        raise ValueError('retained native daemon identity is invalid')
    birth = identity.process_birth
    current = native.read_process_birth(os.getpid())
    repo = Path(context['repo_root'])
    entrypoint = repo / 'integrations/ipfs_accelerate/improvement_runner.py'
    scope = {'repo_root': str(repo), 'state_dir': str(state_dir),
             'state_prefix': runner.STATE_PREFIX, 'todo_path': record['board_path'],
             'daemon_entrypoint': str(entrypoint)}
    # This is the ordinary command emitted for the existing first-party
    # native_argv profile. No alternative entrypoint or extra option is admitted.
    command = (record['argv'][0], str(entrypoint), '--interval', '10.0',
        '--todo-path', record['board_path'], '--state-dir', str(state_dir),
        '--task-prefix', runner.TASK_PREFIX, '--board-namespace', 'complaint-intake-improvement',
        '--state-prefix', runner.STATE_PREFIX, '--max-task-attempts', '3',
        '--task-source-kind', 'legacy-markdown', '--authority-mode', 'legacy_markdown',
        '--validation-max-workers', '1', '--merge-target-branch', record['merge_target'],
        '--merge-queue-dir', str(state_dir / 'merge-queue'), '--implement',
        '--implementation-timeout', str(float(runner.TIMEOUT_SECONDS)),
        '--worktree-root', context['worktree_root'],
        '--worktree-submodule-path', 'external/ipfs_datasets_py',
        '--task-shard-count', '1', '--task-shard-index', '0')
    if (dict(identity.owner_scope) != scope or identity.command != command
            or before[pid_path] != f'{birth.pid}\n'.encode('ascii')
            or birth.parent_pid != parent['pid'] or birth.pid == parent['pid']
            or current is None or current.boot_id != parent['boot_id']
            or birth.boot_id != parent['boot_id']
            or birth.start_time_ticks <= parent['start_ticks']
            or not context['started_at'] <= _timestamp(identity.created_at) <= time.time()):
        raise ValueError('retained native daemon is not bound to this launch')

    def absent(pid):
        try:
            (Path('/proc') / str(pid)).stat()
        except FileNotFoundError:
            return True
        return False

    if (not absent(parent['pid']) or not absent(birth.pid)
            or native.supervised_child_identity_liveness(identity) is not native.OwnerLiveness.DEAD
            or not native._supervised_child_identity_session_quiesced(identity)):
        raise ValueError('retained native daemon session is not proven absent')
    if (snapshot != markers() or not absent(parent['pid']) or not absent(birth.pid)
            or not native._supervised_child_identity_session_quiesced(identity)):
        raise ValueError('retained native daemon custody changed during observation')


def _complete_process_inventory(minimum_owned_start_ticks: int) -> list[dict[str, Any]]:
    """Read bounded process metadata; unavailable observations are not absence.

    No environment, log, executable content or argv is returned in a receipt.
    Disappeared processes may be skipped; changed/reused numeric identities and
    inaccessible postlaunch entries invalidate the entire observation. Canonical
    Native per-launch workers are newly spawned, so older process births remain
    in the group/session census but cannot be descendants of this launcher.
    """
    if type(minimum_owned_start_ticks) is not int or minimum_owned_start_ticks <= 0:
        raise ValueError('invalid historical launcher birth bound')
    try:
        hz = os.sysconf('SC_CLK_TCK')
        current_ticks = int(time.clock_gettime(time.CLOCK_BOOTTIME) * hz)
        if type(hz) is not int or hz <= 0 or minimum_owned_start_ticks > current_ticks:
            raise ValueError('invalid historical launcher birth bound')
    except (OSError, ValueError, AttributeError, OverflowError) as exc:
        raise ValueError('historical launcher birth bound is unavailable') from exc
    result = []
    try:
        entries = tuple(Path('/proc').iterdir())
    except OSError as exc:
        raise ValueError('complete process inventory is unavailable') from exc
    if len(entries) > 131072:
        raise ValueError('complete process inventory exceeds bound')
    for directory in entries:
        if not directory.name.isdecimal():
            continue
        try:
            first = directory.stat()
            raw = (directory / 'stat').read_text()
            fields = raw[raw.rindex(')') + 2:].split()
            pid = int(directory.name)
            if int(raw.split(' ', 1)[0]) != pid or len(fields) < 20:
                raise ValueError('process identity is malformed')
            identity = (int(fields[1]), int(fields[2]), int(fields[3]), int(fields[19]))
            argv: tuple[str, ...] = ()
            cwd = None
            scope_required = first.st_uid == os.getuid() and identity[3] >= minimum_owned_start_ticks
            prelaunch_excluded = first.st_uid == os.getuid() and identity[3] < minimum_owned_start_ticks
            if scope_required:
                with (directory / 'cmdline').open('rb') as stream:
                    command = stream.read(131073)
                if len(command) > 131072:
                    raise ValueError('process argv exceeds inspection bound')
                argv = tuple(part.decode('utf-8', errors='strict') for part in command.split(b'\0') if part)
                if fields[0] != 'Z':
                    cwd = os.readlink(directory / 'cwd')
                    if not Path(cwd).is_absolute():
                        raise ValueError('process working directory is unknown')
            after = directory.stat()
            last = (directory / 'stat').read_text()
            final = last[last.rindex(')') + 2:].split()
            if (first.st_uid != after.st_uid or identity !=
                    (int(final[1]), int(final[2]), int(final[3]), int(final[19]))):
                raise ValueError('process identity changed during inventory')
            result.append({'pid': pid, 'uid': first.st_uid, 'ppid': identity[0],
                'process_group': identity[1], 'session': identity[2],
                'start_ticks': identity[3], 'argv': argv, 'cwd': cwd,
                'scope_metadata_required': scope_required, 'prelaunch_scope_excluded': prelaunch_excluded})
        except (FileNotFoundError, ProcessLookupError) as exc:
            # A missing cwd/cmdline is not death while the numeric process
            # directory still exists (for example an inaccessible namespace).
            try:
                directory.lstat()
            except FileNotFoundError:
                continue
            except OSError as unavailable:
                raise ValueError('complete process inventory is unavailable') from unavailable
            raise ValueError('complete process inventory is unavailable') from exc
        except (OSError, ValueError, IndexError, UnicodeError) as exc:
            raise ValueError('complete process inventory is unavailable') from exc
    return result


def _missing_marker_session_closed(state_dir: Path, record: Mapping[str, Any],
                                   context: Mapping[str, Any]) -> dict[str, Any]:
    """Observe a crashed launch without restoring or inventing native markers.

    An owned heartbeat is historical scope, never a death/healthy declaration.
    Both numeric leaders, their entire groups/sessions, and escaped matching
    campaign processes must be absent in two complete fresh observations.
    """
    from . import improvement_runner as runner
    from .improvement_recovery import _owned_bytes, _campaign_process_argv
    parent = record['identity']
    launcher_path = state_dir / 'launcher.json'
    heartbeat_path = state_dir / 'complaint_intake_supervisor_status.json'
    pid_path = state_dir / f'{runner.STATE_PREFIX}_managed_daemon.pid'
    # This is the public Native identity path recipe, without loading an
    # absent identity or calling a Native constructor or lifecycle operation.
    identity_path = pid_path.with_suffix('.identity.json')
    def missing_markers():
        for path in (pid_path, identity_path):
            try:
                path.lstat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise ValueError('native marker absence is unavailable') from exc
            raise ValueError('both canonical native markers must be absent')
    def custody():
        launch = _owned_bytes(launcher_path)
        heartbeat = _owned_bytes(heartbeat_path, legacy_group_write=True)
        if json.loads(launch) != record or hashlib.sha256(launch).hexdigest() != context['launcher_sha256']:
            raise ValueError('missing-marker launcher custody changed')
        return launch, heartbeat
    missing_markers()
    before = custody()
    heartbeat = json.loads(before[1])
    repo = Path(context['repo_root'])
    daemon = heartbeat.get('daemon_pid')
    native_state = str(state_dir / f'{runner.STATE_PREFIX}_task_state.json')
    expected_paths = {'repo_root': str(repo), 'todo_path': record['board_path'],
        'state_path': native_state, 'current_status_path': native_state, 'progress_path': native_state,
        'child_pid_path': str(pid_path),
        'supervisor_lock_path': str(state_dir / f'{runner.STATE_PREFIX}_supervisor.lock'),
        'state_prefix': runner.STATE_PREFIX, 'task_prefix': runner.TASK_PREFIX}
    source_revision = heartbeat.get('control_plane_source_revision')
    if (heartbeat.get('schema') != 'ipfs_accelerate_py.agent_supervisor.todo_implementation_supervisor.supervisor'
        or heartbeat.get('status') not in {'running', 'termination_blocked'}
        or heartbeat.get('supervisor_pid') != parent['pid']
        or type(daemon) is not int or daemon <= 1 or daemon == parent['pid']
        or heartbeat.get('max_task_attempts') != 3
        or any(heartbeat.get(key) != value for key, value in expected_paths.items())
        or not context['started_at'] <= _timestamp(heartbeat.get('updated_at')) <= time.time()
        or heartbeat.get('control_plane_source_schema') != 'ipfs_accelerate_py.agent_supervisor.control_plane_source@1'
        or not isinstance(source_revision, str) or not re.fullmatch(r'[0-9a-f]{40}', source_revision)
        or heartbeat.get('control_plane_current_source_revision') != source_revision
        or not isinstance(heartbeat.get('control_plane_source_id'), str)
        or not _TASK_CID.fullmatch(heartbeat['control_plane_source_id'])
        or heartbeat.get('control_plane_current_source_id') != heartbeat['control_plane_source_id']):
        raise ValueError('missing-marker heartbeat is not bound to the full launch scope')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if boot != parent['boot_id']:
        raise ValueError('missing-marker launch is from a different boot')
    run_id = heartbeat.get('run_id')
    if (not isinstance(run_id, str) or not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z', run_id)
        or not math.floor(context['started_at']) <= datetime.strptime(run_id, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).timestamp() <= _timestamp(heartbeat['updated_at'])
        or heartbeat.get('log_path') != str(state_dir / f'{runner.STATE_PREFIX}_managed_daemon_{run_id}.log')):
        raise ValueError('missing-marker heartbeat run paths differ')
    old_ids = {parent['pid'], daemon}
    worktree_root = Path(context['worktree_root'])
    def absent():
        for pid in old_ids:
            try:
                (Path('/proc') / str(pid)).lstat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise ValueError('historical numeric PID absence is unavailable') from exc
            raise ValueError('historical numeric PID is still present')
    def scoped_path(value, root):
        return isinstance(value, str) and Path(value).is_absolute() and Path(value).is_relative_to(root)
    def scan():
        absent()
        prelaunch_exclusions = 0
        for process in _complete_process_inventory(parent['start_ticks']):
            prelaunch_exclusions += int(process.get('prelaunch_scope_excluded') is True)
            if process['pid'] in old_ids or process['process_group'] in old_ids or process['session'] in old_ids:
                raise ValueError('historical group or session is still present')
            if process['uid'] != os.getuid() or process['pid'] == os.getpid():
                continue
            argv = list(process['argv'])
            workspace_argument = any(scoped_path(value, worktree_root) for value in argv)
            workspace_cwd = scoped_path(process['cwd'], worktree_root)
            relevant = _campaign_process_argv(argv, repo_root=repo, state_dir=state_dir)
            campaign_argument = any(scoped_path(value, state_dir) for value in argv)
            if workspace_argument or workspace_cwd or (relevant and campaign_argument):
                raise ValueError('matching campaign process remains outside historical session')
        absent()
        return prelaunch_exclusions
    first_exclusions = scan()
    if custody() != before:
        raise ValueError('missing-marker custody changed during process inventory')
    missing_markers()
    second_exclusions = scan()
    if custody() != before or Path('/proc/sys/kernel/random/boot_id').read_text().strip() != boot:
        raise ValueError('missing-marker custody changed during second process inventory')
    missing_markers()
    return {'source': 'owned_historical_heartbeat_and_double_complete_proc_inventory',
        'proc_census_complete': True, 'observations': 2, 'recorded_pids_absent': True,
        'scope_birth_policy': 'same_uid_birth_at_or_after_owned_launcher_requires_argv_and_cwd',
        'minimum_owned_start_ticks': parent['start_ticks'],
        'prelaunch_scope_exclusions': [first_exclusions, second_exclusions],
        'all_births_group_and_session_checked': True,
        'matching_processes': 0, 'canonical_markers_absent': True,
        'sealed_native_identity_used': False, 'daemon_birth_ticks_claimed': False,
        'heartbeat_status_preserved': heartbeat['status'],
        'heartbeat_sha256': hashlib.sha256(before[1]).hexdigest(),
        'signals_sent': False, 'completion_authority': False, 'attempt_refunded': False}


def _parent_closed(state_dir: Path, record: Mapping[str, Any], context: Mapping[str, Any], supplied: bool) -> dict[str, Any] | None:
    from . import improvement_runner as runner
    from .improvement_recovery import _object
    birth = record['identity']
    current = runner.process_identity(birth['pid'])
    if current and all(current.get(key) == birth.get(key) for key in ('pid', 'start_ticks', 'boot_id')):
        raise ValueError('recorded campaign parent is still alive')
    if supplied:
        return
    heartbeat = _object(state_dir / 'complaint_intake_supervisor_status.json', legacy_group_write=True)
    if (heartbeat.get('repo_root') != context['repo_root'] or heartbeat.get('supervisor_pid') != birth['pid']
            or _timestamp(heartbeat.get('updated_at')) < context['started_at']):
        raise ValueError('historical campaign lacks current owned shutdown evidence')
    if heartbeat.get('status') == 'stopped' and (heartbeat.get('managed_daemon_cleanup') or {}).get('quiesced') is True:
        return
    if heartbeat.get('status') in {'running', 'termination_blocked'}:
        pid_path = state_dir / f'{runner.STATE_PREFIX}_managed_daemon.pid'
        identity_path = pid_path.with_suffix('.identity.json')
        if not os.path.lexists(pid_path) and not os.path.lexists(identity_path):
            return _missing_marker_session_closed(state_dir, record, context)
    if heartbeat.get('status') != 'termination_blocked':
        raise ValueError('historical campaign lacks current owned shutdown evidence')
    _sealed_managed_session_closed(state_dir, record, context)


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
        process_closure = _parent_closed(state_dir, record, context, parent_quiesced)
        if process_closure is not None:
            result['process_closure'] = process_closure
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
