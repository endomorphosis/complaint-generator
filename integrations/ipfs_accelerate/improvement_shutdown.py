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
MAX_EVENTS_BYTES = 128 * 1024 * 1024
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


def _managed_native_command(record: Mapping[str, Any], context: Mapping[str, Any],
                            submodules: tuple[str, ...] = ('external/ipfs_datasets_py', 'external/ipfs_kit_py')) -> tuple[str, ...]:
    from . import improvement_runner as runner
    state_dir = Path(context['state_dir'])
    entrypoint = Path(context['repo_root']) / 'integrations/ipfs_accelerate/improvement_runner.py'
    prefix = (record['argv'][0], str(entrypoint), '--interval', '10.0',
        '--todo-path', record['board_path'], '--state-dir', str(state_dir),
        '--task-prefix', runner.TASK_PREFIX, '--board-namespace', 'complaint-intake-improvement',
        '--state-prefix', runner.STATE_PREFIX, '--max-task-attempts', '3',
        '--task-source-kind', 'legacy-markdown', '--authority-mode', 'legacy_markdown',
        '--validation-max-workers', '1', '--merge-target-branch', record['merge_target'],
        '--merge-queue-dir', str(state_dir / 'merge-queue'), '--implement',
        '--implementation-timeout', str(float(runner.TIMEOUT_SECONDS)),
        '--worktree-root', context['worktree_root'],
        )
    return prefix + tuple(part for relative in submodules for part in ('--worktree-submodule-path', relative)) + (
        '--task-shard-count', '1', '--task-shard-index', '0')


def fence_owned_orphan_native_child(state_dir: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    """Fence the exact sealed child of an absent launcher during explicit stop.

    This does not reconcile task state, release claims, or grant a retry. The
    ordinary shutdown verifier must still prove process and container closure.
    """
    from . import improvement_runner as runner
    from .improvement_recovery import _owned_bytes

    context = _context(state_dir, record)
    if context is None:
        return {'status': 'not_applicable', 'fenced': False}
    parent = record['identity']
    if (Path('/proc') / str(parent['pid'])).exists():
        raise ValueError('orphan launcher numeric PID is still present')
    pid_path = state_dir / f'{runner.STATE_PREFIX}_managed_daemon.pid'
    identity_path = pid_path.with_suffix('.identity.json')
    if not os.path.lexists(pid_path) and not os.path.lexists(identity_path):
        return {'status': 'markers_absent', 'fenced': False}
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_runtime as native

    launcher_path = state_dir / 'launcher.json'
    paths = (launcher_path, pid_path, identity_path)
    captured = {path: _owned_bytes(path, 65536, legacy_group_write=path != launcher_path)
                for path in paths}
    if json.loads(captured[launcher_path]) != record:
        raise ValueError('orphan launch custody changed')
    identity = native.SupervisedChildIdentity.from_dict(json.loads(captured[identity_path]))
    if identity is None or identity.to_dict() != json.loads(captured[identity_path]):
        raise ValueError('orphan native identity is invalid')
    birth = identity.process_birth
    repo = Path(context['repo_root'])
    scope = {'repo_root': str(repo), 'state_dir': str(state_dir),
             'state_prefix': runner.STATE_PREFIX, 'todo_path': record['board_path'],
             'daemon_entrypoint': str(repo / 'integrations/ipfs_accelerate/improvement_runner.py')}
    if (dict(identity.owner_scope) != scope or identity.command != _managed_native_command(record, context)
            or captured[pid_path] != f'{birth.pid}\n'.encode('ascii')
            or birth.parent_pid != parent['pid'] or birth.pid == parent['pid']
            or birth.start_time_ticks <= parent['start_ticks']
            or birth.boot_id != parent['boot_id']
            or Path('/proc/sys/kernel/random/boot_id').read_text().strip() != parent['boot_id']
            or not context['started_at'] <= _timestamp(identity.created_at) <= time.time()):
        raise ValueError('orphan native identity differs from owned launch')
    live = native.supervised_child_identity_liveness(identity)
    process = Path('/proc') / str(birth.pid)
    if live is native.OwnerLiveness.DEAD:
        if process.exists():
            raise ValueError('orphan native numeric PID was reused')
        return {'status': 'already_closed', 'fenced': False}
    if (live is not native.OwnerLiveness.ALIVE or process.stat().st_uid != os.getuid()
            or os.getpgid(birth.pid) != birth.pid or os.getsid(birth.pid) != birth.pid
            or native.read_process_command_argv(birth.pid) != identity.command):
        raise ValueError('orphan native process custody is unavailable')
    if (any(_owned_bytes(path, 65536, legacy_group_write=path != launcher_path) != raw
            for path, raw in captured.items()) or (Path('/proc') / str(parent['pid'])).exists()
            or native.load_supervised_child_identity(identity_path) != identity):
        raise ValueError('orphan custody changed before native fence')
    handle = native.SupervisedChild(
        pid=birth.pid, command=identity.command,
        log_path=state_dir / 'complaint_intake_managed_daemon.latest.log',
        child_pid_path=pid_path, identity_path=identity_path,
        started_at=identity.created_at, identity_record_id=identity.record_id,
        identity_process_birth=birth, owned_process_group_id=birth.pid)
    if native.terminate_supervised_child(handle, grace_seconds=10.0, clear_pid_file=False) is not True:
        raise ValueError('owned orphan native fence refused')
    # A subreaper may have adopted this exact orphan. Native's signal fence can
    # finish before its zombie is reaped. Reap only the captured birth, without
    # blocking or treating a reused numeric PID as the original process.
    reap_deadline = time.monotonic() + 1.0
    while process.exists() and time.monotonic() < reap_deadline:
        try:
            info = process.stat()
            raw_stat = (process / 'stat').read_text()
            fields = raw_stat[raw_stat.rfind(')') + 2:].split()
            if (info.st_uid != os.getuid() or len(fields) < 20
                    or int(fields[19]) != birth.start_time_ticks):
                break
            try:
                os.waitpid(birth.pid, os.WNOHANG)
            except ChildProcessError:
                pass
        except FileNotFoundError:
            break
        if process.exists():
            time.sleep(.025)
    if (process.exists() or (Path('/proc') / str(parent['pid'])).exists()
            or any(_owned_bytes(path, 65536, legacy_group_write=path != launcher_path) != raw
                   for path, raw in captured.items())):
        raise ValueError('owned orphan native fence closure is unavailable')
    return {'status': 'fenced', 'fenced': True, 'native_pid': birth.pid,
            'native_start_ticks': birth.start_time_ticks, 'markers_preserved': True,
            'completion_authority': False, 'attempt_refunded': False}


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
    command = _managed_native_command(record, context)
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


def _scope_bytes(path: Path, maximum: int = 65536, *, root_owned: bool = False) -> bytes:
    """Read only fixed kernel/logind metadata, never process environment or logs."""
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError('foreign login metadata traverses an alias')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        first = os.fstat(descriptor)
        if (not stat.S_ISREG(first.st_mode) or first.st_nlink != 1
                or (root_owned and (first.st_uid != 0 or first.st_mode & 0o022))):
            raise ValueError('foreign login metadata ownership is unknown')
        body = bytearray()
        while len(body) <= maximum:
            block = os.read(descriptor, min(8192, maximum + 1 - len(body)))
            if not block:
                break
            body.extend(block)
        last = os.fstat(descriptor)
        current = path.lstat()
        identity = lambda value: (value.st_dev, value.st_ino, value.st_uid, value.st_mode,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if len(body) > maximum or identity(first) != identity(last) or identity(last) != identity(current):
            raise ValueError('foreign login metadata changed or exceeded its bound')
        return bytes(body)
    finally:
        os.close(descriptor)


def _scope_number(value: str, maximum: int = 2**64 - 1) -> int:
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,20}', value):
        raise ValueError('foreign login numeric metadata is malformed')
    result = int(value)
    if result > maximum:
        raise ValueError('foreign login numeric metadata exceeds its bound')
    return result


def _scope_root_path(path: Path, *, directory: bool) -> tuple[int, ...]:
    info = path.lstat()
    if (path.resolve(strict=True) != path or info.st_uid != 0 or info.st_mode & 0o022
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        raise ValueError('foreign login scope is aliased, delegated or writable')
    return (info.st_dev, info.st_ino, info.st_uid, info.st_mode, info.st_nlink)


def _scope_process(pid: int) -> dict[str, Any]:
    directory = Path('/proc') / str(pid)
    raw = _scope_bytes(directory / 'stat', 8192).decode('utf-8')
    fields = raw[raw.rindex(')') + 2:].split()
    if raw.split(' ', 1)[0] != str(pid) or len(fields) < 20 or fields[0] == 'Z':
        raise ValueError('foreign login process identity is unavailable')
    status = {}
    for line in _scope_bytes(directory / 'status').decode('ascii').splitlines():
        if ':' in line:
            key, value = line.split(':', 1)
            if key in status:
                raise ValueError('foreign login process status has duplicate fields')
            status[key] = value.strip()
    uids = tuple(_scope_number(value, 2**32 - 1) for value in status.get('Uid', '').split())
    caps = {}
    for key in ('CapEff', 'CapPrm', 'CapAmb'):
        if not re.fullmatch(r'[0-9a-fA-F]{1,16}', status.get(key, '')):
            raise ValueError('foreign login process capabilities are unknown')
        caps[key] = int(status.get(key, ''), 16)
    if (len(uids) != 4 or status.get('NSpid', '').split() != [str(pid)]
            or status.get('Pid') != str(pid)):
        raise ValueError('foreign login process credentials are unknown')
    return {'pid': pid, 'ppid': int(fields[1]), 'process_group': int(fields[2]),
        'session': int(fields[3]), 'start_ticks': int(fields[19]), 'uids': uids,
        'capabilities': caps,
        'audit': _scope_number(_scope_bytes(directory / 'sessionid', 64).decode('ascii').strip(), 2**32 - 1),
        'loginuid': _scope_number(_scope_bytes(directory / 'loginuid', 64).decode('ascii').strip(), 2**32 - 1),
        'cgroup': _scope_bytes(directory / 'cgroup', 8192).decode('ascii')}


def _foreign_login_cwd_proof(pid: int, minimum_owned_start_ticks: int) -> dict[str, Any]:
    """Prove foreign root-broker ownership only under a trusted privileged host.

    This is not proof that root never migrated a process historically. The
    exception concerns only an unreadable cwd; argv and all births/groups/
    sessions remain in the ordinary complete census and matching checks.
    """
    if os.getuid() <= 0 or os.geteuid() != os.getuid():
        raise ValueError('foreign login cwd proof requires an ordinary unprivileged observer')
    target = _scope_process(pid)
    if (target['uids'] != (os.getuid(),) * 4 or any(target['capabilities'].values())
            or not minimum_owned_start_ticks <= target['start_ticks']
            or not 0 < target['audit'] < 2**32 - 1 or target['loginuid'] != os.getuid()):
        raise ValueError('foreign login target credentials are unknown')
    boot = _scope_bytes(Path('/proc/sys/kernel/random/boot_id'), 128)
    reader = '/proc/' + str(os.getpid())
    namespace = os.readlink(reader + '/ns/time')
    offsets = _scope_bytes(Path(reader + '/timens_offsets'), 1024).decode('ascii').splitlines()
    init_offsets = _scope_bytes(Path('/proc/1/timens_offsets'), 1024).decode('ascii').splitlines()
    if (not re.fullmatch(r'time:\[[0-9]+\]', namespace)
            or sorted(line.split() for line in offsets) != [['boottime', '0', '0'], ['monotonic', '0', '0']]
            or sorted(line.split() for line in init_offsets) != [['boottime', '0', '0'], ['monotonic', '0', '0']]
            or _scope_bytes(Path(reader + '/uid_map'), 1024).split() != [b'0', b'0', b'4294967295']):
        raise ValueError('foreign login clock or user namespace is unavailable')
    record_path = Path('/run/systemd/sessions') / str(target['audit'])
    record_parents = [(str(parent), _scope_root_path(parent, directory=True))
        for parent in reversed(record_path.parents)]
    record_raw = _scope_bytes(record_path, root_owned=True)
    record = {}
    for line in record_raw.decode('utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        key, value = line.split('=', 1)
        if key in record or not re.fullmatch(r'[A-Z_]{1,64}', key):
            raise ValueError('foreign login session record is malformed')
        record[key] = value
    if (len(record) > 128 or _scope_number(record.get('UID'), 2**32 - 1) != os.getuid()
            or _scope_number(record.get('AUDIT'), 2**32 - 1) != target['audit']
            or record.get('REMOTE') != '1' or record.get('SERVICE') != 'sshd'
            or record.get('SCOPE') != f"session-{target['audit']}.scope"):
        raise ValueError('foreign login root session record does not match')
    leader = _scope_process(_scope_number(record.get('LEADER'), 2**31 - 1))
    broker = _scope_process(leader['ppid'])
    if (target['ppid'] != leader['pid'] or leader['uids'] != (0,) * 4
            or not minimum_owned_start_ticks < leader['start_ticks'] <= target['start_ticks']
            or leader['audit'] != target['audit'] or leader['loginuid'] != target['loginuid']
            or broker['uids'] != (0,) * 4 or not 0 < broker['start_ticks'] < minimum_owned_start_ticks
            or broker['audit'] != 2**32 - 1 or broker['loginuid'] != 2**32 - 1):
        raise ValueError('foreign login privileged broker lineage is unknown')
    hz = os.sysconf('SC_CLK_TCK')
    created = _scope_number(record.get('MONOTONIC'))
    # MONOTONIC excludes suspend whereas proc birth is BOOTTIME. This strict
    # inequality is conservative with zero namespace offsets, not an assertion
    # that the two clocks have equal historical offsets.
    if (type(hz) is not int or hz <= 0 or created * hz <= (minimum_owned_start_ticks + 1) * 1_000_000
            or created > int(time.clock_gettime(time.CLOCK_MONOTONIC) * 1_000_000)):
        raise ValueError('foreign login scope creation is not proven after launch')
    cgroup_lines = target['cgroup'].splitlines()
    if len(cgroup_lines) != 1 or not cgroup_lines[0].startswith('0::/') or leader['cgroup'] != target['cgroup']:
        raise ValueError('foreign login kernel cgroup membership is unknown')
    relative = cgroup_lines[0][3:]
    parts = relative.split('/')[1:]
    if (not 1 <= len(parts) <= 64 or any(not re.fullmatch(r'[A-Za-z0-9_.@:-]{1,255}', part) or part in {'.', '..'} for part in parts)
            or parts[-1] != record['SCOPE']):
        raise ValueError('foreign login scope path differs')
    mounts = _scope_bytes(Path(reader + '/mountinfo'), 262144).decode('utf-8').splitlines()
    matches = [line for line in mounts if ' - ' in line and line.split(' - ', 1)[1].split()[0] == 'cgroup2'
        and len(line.split(' - ', 1)[0].split()) >= 6 and line.split()[3:5] == ['/', '/sys/fs/cgroup']]
    if len(matches) != 1:
        raise ValueError('foreign login cgroup2 mount is unavailable')
    root = Path('/sys/fs/cgroup')
    for parent in reversed(root.parents):
        _scope_root_path(parent, directory=True)
    scope_metadata = []
    current = root
    for component in [None, *parts]:
        if component is not None:
            current = current / component
        scope_metadata.append((str(current), _scope_root_path(current, directory=True),
            _scope_root_path(current / 'cgroup.procs', directory=False),
            _scope_root_path(current / 'cgroup.threads', directory=False)))
    if _scope_bytes(current / 'cgroup.type', 128, root_owned=True).strip() != b'domain':
        raise ValueError('foreign login cgroup is not a nondelegated domain')
    if (target != _scope_process(pid) or leader != _scope_process(leader['pid'])
            or broker != _scope_process(broker['pid']) or record_raw != _scope_bytes(record_path, root_owned=True)
            or boot != _scope_bytes(Path('/proc/sys/kernel/random/boot_id'), 128)
            or namespace != os.readlink(reader + '/ns/time')
            or offsets != _scope_bytes(Path(reader + '/timens_offsets'), 1024).decode('ascii').splitlines()
            or init_offsets != _scope_bytes(Path('/proc/1/timens_offsets'), 1024).decode('ascii').splitlines()
            or record_parents != [(str(parent), _scope_root_path(parent, directory=True))
                for parent in reversed(record_path.parents)]
            or _scope_bytes(Path(reader + '/uid_map'), 1024).split() != [b'0', b'0', b'4294967295']
            or mounts != _scope_bytes(Path(reader + '/mountinfo'), 262144).decode('utf-8').splitlines()):
        raise ValueError('foreign login scope proof changed during observation')
    again = []
    current = root
    for component in [None, *parts]:
        if component is not None:
            current = current / component
        again.append((str(current), _scope_root_path(current, directory=True),
            _scope_root_path(current / 'cgroup.procs', directory=False),
            _scope_root_path(current / 'cgroup.threads', directory=False)))
    if (again != scope_metadata
            or _scope_bytes(current / 'cgroup.type', 128, root_owned=True).strip() != b'domain'):
        raise ValueError('foreign login cgroup custody changed during observation')
    digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'policy': 'fresh_root_broker_login_scope_unknown_cwd@1', 'cwd_known': False,
        'cwd_permission_denied': True, 'pid': pid, 'start_ticks': target['start_ticks'],
        'audit_session': target['audit'], 'leader_pid': leader['pid'], 'leader_start_ticks': leader['start_ticks'],
        'broker_pid': broker['pid'], 'record_sha256': hashlib.sha256(record_raw).hexdigest(),
        'kernel_identity_sha256': digest([target, leader, broker]), 'cgroup_metadata_sha256': digest(scope_metadata),
        'boot_sha256': hashlib.sha256(boot).hexdigest(), 'time_namespace': namespace,
        'trusted_privileged_host_boundary': True, 'historical_privileged_migration_impossible_claim': False}


def _complete_process_inventory(minimum_owned_start_ticks: int) -> list[dict[str, Any]]:
    """Read bounded process metadata; unavailable observations are not absence.

    No environment, log, executable content or argv is returned in a receipt.
    Disappeared processes may be skipped; changed/reused numeric identities and
    inaccessible postlaunch entries invalidate the entire observation except
    a cwd-only denial with a freshly rederived foreign root-login proof. Canonical
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
            foreign_cwd_proof = None
            scope_required = first.st_uid == os.getuid() and identity[3] >= minimum_owned_start_ticks
            prelaunch_excluded = first.st_uid == os.getuid() and identity[3] < minimum_owned_start_ticks
            if scope_required:
                with (directory / 'cmdline').open('rb') as stream:
                    command = stream.read(131073)
                if len(command) > 131072:
                    raise ValueError('process argv exceeds inspection bound')
                argv = tuple(part.decode('utf-8', errors='strict') for part in command.split(b'\0') if part)
                if fields[0] != 'Z':
                    try:
                        cwd = os.readlink(directory / 'cwd')
                    except PermissionError:
                        if not argv:
                            raise ValueError('foreign login cwd exception requires readable nonempty argv')
                        foreign_cwd_proof = _foreign_login_cwd_proof(pid, minimum_owned_start_ticks)
                    if foreign_cwd_proof is None and not Path(cwd).is_absolute():
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
                'scope_metadata_required': scope_required, 'prelaunch_scope_excluded': prelaunch_excluded,
                'foreign_cwd_proof': foreign_cwd_proof})
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


def _retained_launch_binding(record: Mapping[str, Any], context: Mapping[str, Any]) -> str:
    """Bind immutable launch scope while ordinary stop updates only its status."""
    material = {key: record.get(key) for key in ('identity', 'argv', 'started_at',
        'repo_root', 'spec_path', 'board_path', 'plan_id', 'merge_target', 'state_dir',
        'provider', 'model', 'allow_fallback', 'worktree_root', 'worktree_root_binding')}
    material['owner_token_sha256'] = context['owner_token_sha256']
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _retained_native_observation(state_dir: Path, record: Mapping[str, Any],
                                 context: Mapping[str, Any], proof: Mapping[str, Any]) -> dict[str, Any]:
    """Read explicit retained evidence solely for negative historical census scope.

    This is an operator-supplied observation under the owned-file trust boundary,
    not a signed Native receipt or positive execution/fencing authority. The
    external operator must authenticate its public-call provenance separately.
    All death, marker absence and complete population checks remain fresh.
    """
    from .improvement_recovery import _owned_bytes
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import supervisor_runtime as native
    if (type(proof) is not dict or set(proof) != {'schema', 'identity', 'effect', 'worktree_submodule_paths'}
            or proof.get('schema') != 'complaint-retained-native-child-observation@1'
            or proof['worktree_submodule_paths'] not in (['external/ipfs_datasets_py'],
                ['external/ipfs_datasets_py', 'external/ipfs_kit_py'])):
        raise ValueError('retained native observation descriptor differs')
    files = {}
    def read_ref(value):
        if (type(value) is not dict or set(value) != {'path', 'sha256'}
                or not isinstance(value['path'], str) or not Path(value['path']).is_absolute()
                or not isinstance(value['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', value['sha256'])):
            raise ValueError('retained native evidence reference differs')
        path = Path(value['path'])
        raw = _owned_bytes(path, 65536)
        if hashlib.sha256(raw).hexdigest() != value['sha256']:
            raise ValueError('retained native evidence hash changed')
        files[str(path)] = value['sha256']
        return raw
    identity_raw = read_ref(proof['identity'])
    payload = json.loads(identity_raw)
    if type(payload) is not dict:
        raise ValueError('retained native identity must be an object')
    identity = native.SupervisedChildIdentity.from_dict(payload)
    if identity is None or identity.to_dict() != payload:
        raise ValueError('retained native identity is invalid')
    effect = json.loads(read_ref(proof['effect']))
    expected_keys = {'schema', 'api', 'identity_record_id', 'identity_sha256',
        'launch_binding_sha256', 'native_source', 'canonical_pid_path',
        'canonical_identity_path', 'result'}
    if (type(effect) is not dict or set(effect) != expected_keys
            or effect.get('schema') != 'complaint-public-native-marker-clear-observation@1'
            or effect.get('api') != 'supervisor_runtime.clear_child_pid_file'
            or effect.get('identity_record_id') != identity.record_id
            or effect.get('identity_sha256') != proof['identity']['sha256']
            or effect.get('launch_binding_sha256') != _retained_launch_binding(record, context)):
        raise ValueError('retained public-clear observation scope differs')
    source = effect['native_source']
    native_path = Path(native.__file__).resolve(strict=True)
    if (type(source) is not dict or set(source) != {'path', 'sha256'}
            or source.get('path') != str(native_path)
            or hashlib.sha256(_owned_bytes(native_path, 2_000_000, legacy_group_write=True)).hexdigest() != source.get('sha256')):
        raise ValueError('retained public-clear Native source differs')
    files[str(native_path)] = source['sha256']
    pid_path = state_dir / 'complaint_intake_managed_daemon.pid'
    identity_path = pid_path.with_suffix('.identity.json')
    if (effect['canonical_pid_path'] != str(pid_path)
            or effect['canonical_identity_path'] != str(identity_path)):
        raise ValueError('retained public-clear canonical paths differ')
    result = json.loads(read_ref(effect['result']))
    if (type(result) is not dict or result.get('native_api') != 'clear_child_pid_file'
            or result.get('returned') is not True or result.get('canonical_pid_absent') is not True
            or result.get('canonical_identity_absent') is not True
            or result.get('signals_performed') is not False or result.get('completion_authority') is not False):
        raise ValueError('retained public-clear result is not an absence observation')
    birth, parent = identity.process_birth, record['identity']
    entrypoint = Path(context['repo_root']) / 'integrations/ipfs_accelerate/improvement_runner.py'
    scope = {'repo_root': context['repo_root'], 'state_dir': str(state_dir),
        'state_prefix': 'complaint_intake', 'todo_path': record['board_path'],
        'daemon_entrypoint': str(entrypoint)}
    if (dict(identity.owner_scope) != scope
            or identity.command != _managed_native_command(record, context, tuple(proof['worktree_submodule_paths']))
            or birth.parent_pid != parent['pid'] or birth.pid == parent['pid']
            or birth.start_time_ticks <= parent['start_ticks'] or birth.boot_id != parent['boot_id']
            or Path('/proc/sys/kernel/random/boot_id').read_text().strip() != parent['boot_id']
            or not context['started_at'] <= _timestamp(identity.created_at) <= time.time()
            or native.supervised_child_identity_liveness(identity) is not native.OwnerLiveness.DEAD
            or not native._supervised_child_identity_session_quiesced(identity)):
        raise ValueError('retained native birth/command/session is not bound and absent')
    # Native's birth record stores PID/ticks/boot/parent, not historical SID.
    # Identity-protected Native launch source requires a dedicated session;
    # both Native's live census and our double census check its PID as PGID/SID.
    # Neither a reused numeric PID nor a reappeared canonical marker is absence.
    for path in (Path('/proc') / str(parent['pid']), Path('/proc') / str(birth.pid), pid_path, identity_path):
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        raise ValueError('retained native numeric birth or canonical marker is present')
    return {'daemon_pid': birth.pid, 'daemon_start_ticks': birth.start_time_ticks,
        'identity_record_id': identity.record_id, 'files': files,
        'launch_binding_sha256': effect['launch_binding_sha256'],
        'proof': json.loads(json.dumps(proof, sort_keys=True, allow_nan=False)),
        'positive_execution_or_fencing_authority': False,
        'native_public_result_provenance_requires_external_operator_review': True}


def _failed_preflight_without_daemon(heartbeat: Mapping[str, Any], record: Mapping[str, Any],
                                     context: Mapping[str, Any]) -> bool:
    """Recognize Native's preflight failure before its first managed launch."""
    if heartbeat.get('status') != 'agentic_maintenance_failed':
        return False
    parent, birth = record['identity'], heartbeat.get('supervisor_process_birth')
    maintenance = heartbeat.get('supervisor_maintenance')
    if (not isinstance(birth, Mapping) or not isinstance(maintenance, Mapping)
            or any(birth.get(key) != parent.get(other) for key, other in
                (('pid', 'pid'), ('start_time_ticks', 'start_ticks'), ('boot_id', 'boot_id')))
            or heartbeat.get('daemon_pid') is not None or heartbeat.get('daemon_process_birth') is not None
            or heartbeat.get('active_agentic_maintenance_has_daemon') is not False
            or type(heartbeat.get('active_worker_count')) is not int
            or type(heartbeat.get('worker_descendant_count')) is not int
            or heartbeat.get('active_worker_count') != 0 or heartbeat.get('active_worker_pids') != []
            or heartbeat.get('worker_descendant_count') != 0
            or heartbeat.get('last_agentic_maintenance_status') != 'failed'
            or heartbeat.get('last_agentic_maintenance_phase') != 'worktree_reconciliation'
            or maintenance.get('schema') != 'ipfs_accelerate_py/agent-supervisor/supervisor-maintenance@1'
            or maintenance.get('phase') != 'failed'
            or not context['started_at'] <= _timestamp(maintenance.get('started_at'))
                <= _timestamp(maintenance.get('finished_at')) <= _timestamp(heartbeat.get('updated_at')) <= time.time()):
        raise ValueError('failed-preflight heartbeat does not prove the owned no-daemon phase')
    run_id = heartbeat.get('run_id')
    # Native assigns a fresh run ID only after its preflight returns. A retained
    # earlier run ID is historical data and supplies no child birth authority.
    if run_id and (not isinstance(run_id, str) or not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z', run_id)
            or datetime.strptime(run_id, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).timestamp()
                >= math.floor(context['started_at'])):
        raise ValueError('failed-preflight heartbeat contains a current managed run')
    starts, _digest = _events(Path(context['state_dir']), context['started_at'],
        worktree_root=Path(context['worktree_root']))
    if starts:
        raise ValueError('failed-preflight launch contains a paid implementation start')
    return True


def _missing_marker_session_closed(state_dir: Path, record: Mapping[str, Any],
                                   context: Mapping[str, Any],
                                   retained_native_child_proof: Mapping[str, Any] | None = None) -> dict[str, Any]:
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
    preflight_without_daemon = _failed_preflight_without_daemon(heartbeat, record, context)
    if preflight_without_daemon and retained_native_child_proof is not None:
        raise ValueError('failed preflight cannot borrow a historical child identity')
    daemon = heartbeat.get('daemon_pid')
    retained = (_retained_native_observation(state_dir, record, context, retained_native_child_proof)
        if retained_native_child_proof is not None else None)
    if retained is not None:
        if daemon is not None and daemon != retained['daemon_pid']:
            raise ValueError('heartbeat and retained native identity disagree')
        daemon = retained['daemon_pid']
    native_state = str(state_dir / f'{runner.STATE_PREFIX}_task_state.json')
    expected_paths = {'repo_root': str(repo), 'todo_path': record['board_path'],
        'state_path': native_state, 'current_status_path': native_state, 'progress_path': native_state,
        'child_pid_path': str(pid_path),
        'supervisor_lock_path': str(state_dir / f'{runner.STATE_PREFIX}_supervisor.lock'),
        'state_prefix': runner.STATE_PREFIX, 'task_prefix': runner.TASK_PREFIX}
    source_revision = heartbeat.get('control_plane_source_revision')
    if (heartbeat.get('schema') != 'ipfs_accelerate_py.agent_supervisor.todo_implementation_supervisor.supervisor'
        or heartbeat.get('status') not in {'running', 'termination_blocked', 'agentic_maintenance_failed'}
        or heartbeat.get('supervisor_pid') != parent['pid']
        or (not preflight_without_daemon and (type(daemon) is not int or daemon <= 1 or daemon == parent['pid']))
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
    if not preflight_without_daemon and (not isinstance(run_id, str) or not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z', run_id)
        or not math.floor(context['started_at']) <= datetime.strptime(run_id, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).timestamp() <= _timestamp(heartbeat['updated_at'])
        or heartbeat.get('log_path') != str(state_dir / f'{runner.STATE_PREFIX}_managed_daemon_{run_id}.log')):
        raise ValueError('missing-marker heartbeat run paths differ')
    old_ids = {parent['pid']} if preflight_without_daemon else {parent['pid'], daemon}
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
    foreign_cwd_observations = []
    def scan():
        absent()
        prelaunch_exclusions = 0
        foreign_cwd_proofs = []
        for process in _complete_process_inventory(parent['start_ticks']):
            prelaunch_exclusions += int(process.get('prelaunch_scope_excluded') is True)
            if process.get('foreign_cwd_proof') is not None:
                foreign_cwd_proofs.append(process['foreign_cwd_proof'])
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
        foreign_cwd_observations.append(foreign_cwd_proofs)
        return prelaunch_exclusions
    first_exclusions = scan()
    if retained is not None and _retained_native_observation(state_dir, record, context, retained_native_child_proof) != retained:
        raise ValueError('retained native observation changed during first census')
    if custody() != before:
        raise ValueError('missing-marker custody changed during process inventory')
    missing_markers()
    second_exclusions = scan()
    if retained is not None and _retained_native_observation(state_dir, record, context, retained_native_child_proof) != retained:
        raise ValueError('retained native observation changed during second census')
    if custody() != before or Path('/proc/sys/kernel/random/boot_id').read_text().strip() != boot:
        raise ValueError('missing-marker custody changed during second process inventory')
    missing_markers()
    return {'source': ('owned_preflight_failure_and_double_complete_proc_inventory' if preflight_without_daemon
            else 'owned_historical_heartbeat_and_double_complete_proc_inventory'),
        'preflight_without_managed_daemon': preflight_without_daemon,
        'retained_native_observation': retained,
        'proc_census_complete': True, 'observations': 2, 'recorded_pids_absent': True,
        'scope_birth_policy': 'same_uid_birth_at_or_after_owned_launcher_requires_argv_and_cwd',
        'minimum_owned_start_ticks': parent['start_ticks'],
        'prelaunch_scope_exclusions': [first_exclusions, second_exclusions],
        'foreign_cwd_policy': 'fresh_root_broker_login_scope_unknown_cwd@1',
        'foreign_cwd_observations': foreign_cwd_observations,
        'all_births_group_and_session_checked': True,
        'matching_processes': 0, 'canonical_markers_absent': True,
        'sealed_native_identity_used': retained is not None, 'daemon_birth_ticks_claimed': retained is not None,
        'heartbeat_status_preserved': heartbeat['status'],
        'heartbeat_sha256': hashlib.sha256(before[1]).hexdigest(),
        'signals_sent': False, 'completion_authority': False, 'attempt_refunded': False}


def _parent_closed(state_dir: Path, record: Mapping[str, Any], context: Mapping[str, Any], supplied: bool,
                   retained_native_child_proof: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    from . import improvement_runner as runner
    from .improvement_recovery import _object
    birth = record['identity']
    current = runner.process_identity(birth['pid'])
    if current and all(current.get(key) == birth.get(key) for key in ('pid', 'start_ticks', 'boot_id')):
        raise ValueError('recorded campaign parent is still alive')
    if supplied:
        if retained_native_child_proof is not None:
            raise ValueError('retained native observation never grants live fencing authority')
        return
    heartbeat = _object(state_dir / 'complaint_intake_supervisor_status.json', legacy_group_write=True)
    if (heartbeat.get('repo_root') != context['repo_root'] or heartbeat.get('supervisor_pid') != birth['pid']
            or _timestamp(heartbeat.get('updated_at')) < context['started_at']):
        raise ValueError('historical campaign lacks current owned shutdown evidence')
    if heartbeat.get('status') == 'stopped' and (heartbeat.get('managed_daemon_cleanup') or {}).get('quiesced') is True:
        return
    if heartbeat.get('status') in {'running', 'termination_blocked', 'agentic_maintenance_failed'}:
        pid_path = state_dir / f'{runner.STATE_PREFIX}_managed_daemon.pid'
        identity_path = pid_path.with_suffix('.identity.json')
        if not os.path.lexists(pid_path) and not os.path.lexists(identity_path):
            if retained_native_child_proof is None and heartbeat.get('daemon_pid') is None:
                try:
                    (state_dir / RECEIPT_NAME).lstat()
                except FileNotFoundError:
                    previous = {}
                else:
                    previous = _object(state_dir / RECEIPT_NAME)
                if runner._shutdown_verified(record, previous, Path(context['repo_root']), state_dir):
                    retained_native_child_proof = previous.get('retained_native_child_proof')
            return _missing_marker_session_closed(state_dir, record, context, retained_native_child_proof)
    if heartbeat.get('status') != 'termination_blocked':
        raise ValueError('historical campaign lacks current owned shutdown evidence')
    _sealed_managed_session_closed(state_dir, record, context)


def close_campaign_containers(state_dir: Path, record: Mapping[str, Any], *, parent_quiesced: bool = False,
                             remove_stopped: bool = True, timeout_seconds: float = 25.0,
                             retained_native_child_proof: Mapping[str, Any] | None = None) -> dict[str, Any]:
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
        process_closure = _parent_closed(state_dir, record, context, parent_quiesced, retained_native_child_proof)
        if process_closure is not None:
            result['process_closure'] = process_closure
            retained = process_closure.get('retained_native_observation')
            if retained is not None:
                result['retained_native_child_proof'] = retained['proof']
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
