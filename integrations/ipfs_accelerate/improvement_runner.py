"""Own and observe one Grok-only native implementation supervisor campaign.

This wrapper does not implement a second task scheduler. The native supervisor
owns its daemon, implementation deadlines, retries and task completion evidence.
Launcher records only establish process ownership; a PID is not progress proof.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import logging
import multiprocessing
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping


SPEC_RELATIVE = "docs/task_boards/complaint_intake_improvement_spec.json"
STATE_PREFIX = "complaint_intake"
TASK_PREFIX = "## CIMP-"
MODEL = "grok-4.7"
STARTUP_SECONDS = 90
STALL_SECONDS = 180
TIMEOUT_SECONDS = 900
MAX_EVENT_HISTORY_BYTES = 128 * 1024 * 1024
_LOGGER = logging.getLogger(__name__)
PRIVATE_PATHS_ENV = "IPFS_ACCELERATE_AGENT_GROK_PRIVATE_PATHS_JSON"
REASONING_EFFORT_ENV = "IPFS_ACCELERATE_AGENT_GROK_REASONING_EFFORT"
ORCHESTRATION_DIR_ENV = "IPFS_ACCELERATE_AGENT_ORCHESTRATION_DIR"
AUTOMATIC_RETRY_REARM_ENV = "IPFS_ACCELERATE_AGENT_AUTOMATIC_RETRY_REARM"
WORKTREE_MARKER = ".complaint-worktree-root.json"
_PRIVATE_ROOT_PATHS = (".complaint_workspace", "data", "output", "statefiles", "exports", "secrets",
                       "evidence", "uploads", "attachments", ".env*", "*.key", "*.pem")
# Native basename globs apply only at their explicit parent. Keep dependency
# source available while denying its private data and Git reconstruction path.
_PRIVATE_DEPENDENCY_ROOTS = ("external/ipfs_accelerate_py", "external/ipfs_datasets_py",
                             "external/ipfs_kit_py")
_PRIVATE_PATHS = (*_PRIVATE_ROOT_PATHS, *(f"{root}/{path}"
                  for root in _PRIVATE_DEPENDENCY_ROOTS for path in (*_PRIVATE_ROOT_PATHS, ".git")))


def default_state_dir(repo_root: Path) -> Path:
    identity = hashlib.sha256(str(repo_root.resolve()).encode()).hexdigest()[:16]
    return Path.home() / ".cache/complaint-generator/campaigns" / identity / "intake-improvement"


def _read_json(path: Path, *, limit: int = 2_000_000) -> dict[str, Any]:
    try:
        if path.stat().st_size > limit:
            return {"read_error": "size_limit", "path": str(path)}
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"read_error": "not_object"}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        return {"read_error": type(exc).__name__}


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def _lock(state_dir: Path, name: str = "launcher.lock", *, blocking: bool = True):
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state_dir / name).open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)



def _worktree_directory(path: Path, repo_root: Path, state_dir: Path) -> dict[str, Any]:
    """Validate a dedicated external root without creating it or following aliases."""
    if (not path.is_absolute() or path.resolve(strict=True) != path
            or path == repo_root or path.is_relative_to(repo_root) or repo_root.is_relative_to(path)
            or path == state_dir or path.is_relative_to(state_dir) or state_dir.is_relative_to(path)):
        raise ValueError("configured worktree root must be canonical and outside repository/state")
    metadata = path.lstat()
    if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700):
        raise ValueError("configured worktree root must be an existing UID-owned0700 directory")
    return {"schema_version": "complaint-worktree-root@1", "path": str(path),
            "device": metadata.st_dev, "inode": metadata.st_ino, "uid": metadata.st_uid, "mode": 0o700,
            "repo_root": str(repo_root), "state_dir": str(state_dir)}


def _worktree_marker(path: Path) -> tuple[dict[str, Any], str] | None:
    marker = path / WORKTREE_MARKER
    try:
        descriptor = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != 0o600 or before.st_size > 16384):
            raise ValueError("worktree root marker ownership differs")
        raw = os.read(descriptor, 16385)
        after = marker.lstat()
        if (len(raw) != before.st_size or any(getattr(before, field) != getattr(after, field)
                for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"))):
            raise ValueError("worktree root marker changed")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("worktree root marker must be an object")
        return value, hashlib.sha256(raw).hexdigest()
    finally:
        os.close(descriptor)


def _validate_worktree_root(repo_root: Path, state_dir: Path, path: Path, *,
                            expected: Mapping[str, Any] | None = None, claim: bool = False) -> dict[str, Any]:
    directory = _worktree_directory(path, repo_root, state_dir)
    marker = _worktree_marker(path)
    if marker is None:
        if expected is not None or any(path.iterdir()):
            raise ValueError("worktree root has no bound marker or is not a fresh dedicated directory")
        if not claim:
            return directory
        raw = (json.dumps(directory, sort_keys=True) + "\n").encode()
        try:
            descriptor = os.open(path / WORKTREE_MARKER, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            return _validate_worktree_root(repo_root, state_dir, path, expected=expected)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        directory_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        marker = _worktree_marker(path)
    if marker is None or marker[0] != directory:
        raise ValueError("worktree root marker belongs to a different repository/epoch/directory")
    binding = {**directory, "marker_sha256": marker[1]}
    if expected is not None and dict(expected) != binding:
        raise ValueError("recorded worktree root identity differs")
    if _worktree_directory(path, repo_root, state_dir) != directory:
        raise ValueError("worktree root directory changed")
    return binding


def recorded_worktree_root(record: Mapping[str, Any], state_dir: Path) -> tuple[Path, dict[str, Any] | None]:
    """Legacy records keep their original root; configured records require exact custody."""
    has_root = "worktree_root" in record or "worktree_root_binding" in record
    if not has_root:
        if "--worktree-root" in (record.get("argv") or []):
            raise ValueError("launcher worktree flag has no recorded binding")
        return state_dir / "worktrees", None
    value, binding = record.get("worktree_root"), record.get("worktree_root_binding")
    argv = record.get("argv")
    if (not isinstance(value, str) or not isinstance(binding, dict) or not isinstance(argv, list)
            or argv.count("--worktree-root") != 1
            or argv[argv.index("--worktree-root") + 1:][:1] != [value]):
        raise ValueError("launcher worktree flag/binding differs")
    repo = Path(str(record.get("repo_root") or ""))
    if not repo.is_absolute() or repo.resolve() != repo or record.get("state_dir") != str(state_dir):
        raise ValueError("launcher worktree repository/epoch differs")
    return Path(value), _validate_worktree_root(repo, state_dir, Path(value), expected=binding)


def _full_launch_record(record: Mapping[str, Any]) -> bool:
    """Process-only fixtures stay process-only; any campaign binding requires closure proof."""
    if not record or record.get("read_error"):
        return False
    return record.get("schema_version") == "complaint-improvement-launcher@1" or any(
        key in record for key in ("repo_root", "spec_path", "plan_id", "state_dir")
    )


def _requested_plan_id(spec_path: Path) -> str | None:
    from .improvement_plan import build_improvement_work_plan, load_spec
    try:
        return build_improvement_work_plan(load_spec(spec_path)).plan_id
    except (OSError, ValueError, TypeError, KeyError):
        return None


def _campaign_tuple_matches(record: Mapping[str, Any], repo_root: Path, spec_path: Path, state_dir: Path) -> bool:
    plan_id = _requested_plan_id(spec_path)
    return bool(
        plan_id and record.get("schema_version") == "complaint-improvement-launcher@1"
        and record.get("repo_root") == str(repo_root)
        and record.get("spec_path") == str(spec_path)
        and record.get("state_dir") == str(state_dir)
        and record.get("plan_id") == plan_id
        and record.get("provider") == "grok_cli"
        and record.get("model") == MODEL
        and record.get("allow_fallback") is False
    )


def _stop_incomplete(state_dir: Path, reason: str) -> dict[str, Any]:
    return {"status": "stop_incomplete", "signalled": False, "reason": reason,
            "state_dir": str(state_dir), "manual_holds_preserved": True}


def _shutdown_verified(record: Mapping[str, Any], shutdown: Mapping[str, Any], repo_root: Path, state_dir: Path) -> bool:
    return bool(
        record.get("schema_version") == "complaint-improvement-launcher@1"
        and shutdown.get("schema") == "complaint-improvement-container-shutdown@1"
        and shutdown.get("repo_root") == record.get("repo_root") == str(repo_root)
        and shutdown.get("state_dir") == record.get("state_dir") == str(state_dir)
        and shutdown.get("plan_id") == record.get("plan_id")
        and shutdown.get("started_at") == record.get("started_at")
        and isinstance(record.get("owner_token"), str)
        and shutdown.get("owner_token_sha256") == hashlib.sha256(record["owner_token"].encode()).hexdigest()
        and shutdown.get("quiesced") is True and shutdown.get("status") == "stopped"
        and shutdown.get("completion_authority") is False
        and shutdown.get("provider_callback_settled") is False
        and shutdown.get("attempt_refunded") is False
        and ("worktree_root" not in record or (shutdown.get("worktree_root") == record["worktree_root"]
             and shutdown.get("worktree_root_binding") == record.get("worktree_root_binding")))
    )


def _admission_docker_runtime():
    from ipfs_accelerate_py.agent_supervisor.runtime import grok_cli_runner
    return grok_cli_runner


def _observe_campaign_containers(repo_root: Path, state_dir: Path, worktree_root: Path,
                                 record: Mapping[str, Any], shutdown: Mapping[str, Any]) -> bool:
    """Observe complete Docker inventory without acquiring shutdown authority.

    A known stopped worker may remain after an explicit non-removing stop. All
    other containers touching this campaign require operator reconciliation.
    Admission never stops, removes, signals, or updates historical evidence.
    """
    from .improvement_shutdown import _CID, _INSPECT, _timestamp, MAX_INSPECT_BYTES
    deadline = time.monotonic() + 25.0
    scopes = {repo_root, state_dir, worktree_root}
    if _full_launch_record(record):
        scopes.add(recorded_worktree_root(record, state_dir)[0])
    retained = shutdown.get("containers", [])
    if not isinstance(retained, list):
        return False
    try:
        native = _admission_docker_runtime()
        docker = native._docker_isolation_binary()
        if not docker:
            return False
        with tempfile.TemporaryDirectory(prefix="complaint-docker-admission-config-") as temporary:
            command = [docker, "--host=unix:///var/run/docker.sock", "--config", temporary]

            def run(arguments):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("Docker admission deadline exceeded")
                result = subprocess.run(command + arguments, stdin=subprocess.DEVNULL, text=True,
                    capture_output=True, timeout=min(5.0, remaining), check=False, env=native._docker_control_env())
                if (len(result.stdout or "") > MAX_INSPECT_BYTES
                        or len(result.stderr or "") > MAX_INSPECT_BYTES):
                    raise ValueError("Docker admission observation exceeds bound")
                return result

            def inventory():
                result = run(["ps", "-a", "--no-trunc", "--format", "{{.ID}}"])
                identifiers = result.stdout.splitlines()
                if (result.returncode or len(identifiers) > 128 or len(set(identifiers)) != len(identifiers)
                        or any(not _CID.fullmatch(value) for value in identifiers)):
                    raise ValueError("complete Docker inventory unavailable")
                return identifiers

            def relevant(value):
                mounts, directory = value.get("Mounts"), value.get("WorkingDir")
                if (not isinstance(mounts, list) or len(mounts) > 256 or not isinstance(directory, str)
                        or any(not isinstance(mount, dict) for mount in mounts)):
                    raise ValueError("Docker workspace observation unavailable")
                # WorkingDir belongs to the container namespace; only its
                # descendants count. Bind sources are host paths and overlap
                # in either direction, including an ancestor mounted writable.
                if directory and Path(directory).is_absolute() and any(Path(directory).is_relative_to(scope) for scope in scopes):
                    return True
                for mount in mounts:
                    if not isinstance(mount.get("Type"), str) or not mount["Type"]:
                        raise ValueError("Docker mount type unavailable")
                    if mount.get("Type") != "bind":
                        continue
                    source = mount.get("Source")
                    if not isinstance(source, str) or not Path(source).is_absolute():
                        raise ValueError("Docker bind source unavailable")
                    source_path = Path(source).resolve()
                    if any(source_path.is_relative_to(scope) or scope.is_relative_to(source_path) for scope in scopes):
                        return True
                return False

            def known_stopped(value):
                image = value.get("Image")
                if (not isinstance(image, str) or not image.startswith("sha256:")
                        or not _CID.fullmatch(image[7:]) or _timestamp(value.get("Created")) > time.time()):
                    return False
                state = value.get("State")
                if (not isinstance(state, dict) or state.get("Running") is not False
                        or type(state.get("Pid")) is not int or state["Pid"] != 0
                        or state.get("Restarting") is not False or state.get("Paused") is not False
                        or state.get("Status") not in {"exited", "dead", "created"}):
                    return False
                return any(isinstance(item, dict) and item.get("container_id") == value["Id"]
                    and item.get("created") == value.get("Created") and item.get("image_id") == value.get("Image")
                    and item.get("workspace") == value.get("WorkingDir") and item.get("quiesced") is True
                    and item.get("removed") is False for item in retained)

            # Re-observe both identity and state after the first complete pass.
            # A newly arriving orphan or a retained worker restarting refuses.
            for _pass in range(2):
                for identifier in inventory():
                    result = run(["inspect", "--format", _INSPECT, identifier])
                    if result.returncode:
                        if identifier not in inventory():
                            continue
                        return False
                    value = json.loads(result.stdout)
                    if not isinstance(value, dict) or value.get("Id") != identifier:
                        return False
                    if relevant(value) and not known_stopped(value):
                        return False
        return True
    except (OSError, ValueError, TypeError, RuntimeError, subprocess.TimeoutExpired):
        return False


def _select_worktree_root(repo_root: Path, state_dir: Path, record: Mapping[str, Any],
                          requested: Path | None) -> tuple[Path, dict[str, Any] | None]:
    previous, binding = recorded_worktree_root(record, state_dir)
    if requested is None or requested == previous:
        return previous, binding
    if record:
        identity = record.get("identity") or {}
        current = process_identity(identity.get("pid")) if isinstance(identity, dict) else None
        old_birth_alive = current and all(current.get(key) == identity.get(key) for key in ("pid", "start_ticks", "boot_id"))
        from .improvement_shutdown import _context
        if _context(state_dir, record) is None:
            raise ValueError("changing worktree root requires a full previous ownership receipt")
        if (old_birth_alive or record.get("status") != "stopped"
                or not _shutdown_verified(record, _read_json(state_dir / "container_shutdown.json"), repo_root, state_dir)):
            raise ValueError("changing worktree root requires a stopped, closure-verified previous launch")
    return requested, _validate_worktree_root(repo_root, state_dir, requested)


def process_identity(pid: int) -> dict[str, Any] | None:
    """Read Linux process birth and argv without trusting a recycled PID."""
    try:
        if type(pid) is not int or pid <= 1:
            return None
        raw = Path(f"/proc/{pid}/stat").read_text()
        fields = raw[raw.rfind(")") + 2 :].split()
        if fields[0] == "Z":
            return None
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        return {
            "pid": pid, "start_ticks": int(fields[19]),
            "ppid": int(fields[1]), "process_group": int(fields[2]),
            "session": int(fields[3]),
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "argv": [part.decode(errors="replace") for part in argv if part],
        }
    except (OSError, ValueError, IndexError):
        return None


def owns_process(record: Mapping[str, Any]) -> bool:
    identity = record.get("identity")
    if not isinstance(identity, dict):
        return False
    current = process_identity(identity.get("pid"))
    token = record.get("owner_token")
    argv = record.get("argv")
    return bool(
        current and token and isinstance(argv, list)
        and "_run" in argv and "--owner-token" in argv
        and argv[argv.index("--owner-token") + 1 :][:1] == [token]
        and current["argv"] == argv
        and all(current.get(key) == identity.get(key) for key in
                ("pid", "start_ticks", "boot_id", "session", "process_group"))
        and current["session"] == current["pid"] == current["process_group"]
    )


def _context_exclusions(context_exclude: Any = None) -> list[str]:
    values = [] if context_exclude is None else context_exclude
    if not isinstance(values, list) or len(values) > 64:
        raise ValueError("context_exclude must contain at most 64 bounded repository-relative paths")
    result = list(_PRIVATE_PATHS)
    for value in values:
        if (not isinstance(value, str) or not value.strip() or len(value) > 256
                or Path(value).is_absolute() or ".." in Path(value).parts
                or value in {"*", "**", ".", "./"}):
            raise ValueError("private exclusions must be bounded repository-relative paths")
        value = value.removeprefix("./")
        # Exact mandatory directories already cover all descendant patterns.
        if any(value == item or value.startswith(item + "/") for item in result
               if "*" not in item and "?" not in item):
            continue
        if value not in result:
            result.append(value)
    if len(result) > 64:
        raise ValueError("private exclusions exceed the native 64-pattern bound")
    return result


def campaign_environment(repo_root: Path, ambient: Mapping[str, str] | None = None,
                         *, context_exclude: Any = None, state_dir: Path | None = None) -> dict[str, str]:
    """Pin routing and remove inherited campaign/fallback/command authority."""
    env = dict(os.environ if ambient is None else ambient)
    remove_exact = {
        "IMPLEMENTATION_DAEMON_COMMAND", "IPFS_ACCELERATE_AGENT_LLM_MERGE_RESOLVER_COMMAND",
        "IPFS_ACCELERATE_AGENT_PRODUCTION_PROVIDER_POLICY", "LLM_PROVIDER", "LLM_MODEL",
        "TODO_DAEMON_LLM_BACKEND", "TODO_DAEMON_LLM_PROVIDER", "TODO_DAEMON_LLM_MODEL",
        "IPFS_ACCELERATE_AGENT_IMPLEMENTATION_PROVIDER_ATTEMPT_STORE",
        "IPFS_ACCELERATE_AGENT_QUACK_ENDPOINT", "IPFS_ACCELERATE_AGENT_CONTROL_DUCKDB",
        "IPFS_ACCELERATE_AGENT_CONTROL_DUCKLAKE",
        "IPFS_ACCELERATE_AGENT_TASK_SOURCE_KIND", "IPFS_ACCELERATE_AGENT_EVENT_STORE_PATH",
        "IPFS_ACCELERATE_AGENT_RUNTIME_REGISTRY_PATH", "IPFS_ACCELERATE_AGENT_EXPORT_PROFILE",
    }
    for key in tuple(env):
        if key in remove_exact or key.startswith((
            "IPFS_ACCELERATE_AGENT_IMPLEMENTATION_ROUTE_",
            "IPFS_ACCELERATE_AGENT_IMPLEMENTATION_FALLBACK_",
            "IPFS_ACCELERATE_AGENT_PRODUCTION_PROVIDER_",
            "IPFS_ACCELERATE_AGENT_STATE_", "IPFS_ACCELERATE_AGENT_QUACK_",
            "IPFS_ACCELERATE_AGENT_DATABASE_PROGRAM_",
        )) or (key.startswith(("IPFS_ACCELERATE_", "ipfs_accelerate_py_", "TODO_DAEMON_"))
                and any(part in key.upper() for part in ("FALLBACK", "PROVIDER_POLICY"))):
            env.pop(key, None)
    env.update({
        "IPFS_ACCELERATE_AGENT_IMPLEMENTATION_PROVIDER": "grok",
        AUTOMATIC_RETRY_REARM_ENV: "0",
        "IPFS_ACCELERATE_AGENT_WORKTREE_SUBMODULE_PATHS": "external/ipfs_datasets_py,external/ipfs_kit_py",
        # Bound retained prepared checkouts in this campaign, without reclaiming leases.
        "IPFS_ACCELERATE_AGENT_WORKTREE_POOL_MAX_ENTRIES": "1",
        # Optional Common Crawl tooling must not clone an unrelated HEAD into
        # an intentionally uninitialized, pinned dependency during validation.
        "COMMON_CRAWL_AUTO_CLONE_SOURCE": "0",
        "IPFS_ACCELERATE_AGENT_GROK_MODEL": MODEL,
        "IPFS_ACCELERATE_AGENT_GROK_MAX_TURNS": "64",
        "IPFS_ACCELERATE_AGENT_GROK_REASONING_EFFORT": "low",
        "IPFS_ACCELERATE_PY_GROK_CLI_MODEL": MODEL,
        "ipfs_accelerate_py_GROK_CLI_MODEL": MODEL,
        "GROK_CLI_MODEL": MODEL, "GROK_MODEL": MODEL,
        "IPFS_ACCELERATE_PY_LLM_PROVIDER": "grok_cli",
        "IPFS_ACCELERATE_PY_LLM_MODEL": MODEL,
        "TODO_DAEMON_LLM_BACKEND": "llm_router",
        "TODO_DAEMON_LLM_PROVIDER": "grok_cli", "TODO_DAEMON_LLM_MODEL": MODEL,
        "TODO_DAEMON_LLM_ALLOW_LOCAL_FALLBACK": "0",
        "TODO_DAEMON_LLM_ALLOW_CROSS_PROVIDER_FALLBACK": "0",
        PRIVATE_PATHS_ENV: json.dumps(_context_exclusions(context_exclude), separators=(",", ":")),
        ORCHESTRATION_DIR_ENV: str((state_dir or default_state_dir(repo_root)).resolve() / "control-plane"),
        "PYTHONUNBUFFERED": "1",
    })
    roots = [repo_root / "external/ipfs_accelerate_py", repo_root / "external/ipfs_datasets_py", repo_root]
    env["PYTHONPATH"] = os.pathsep.join(str(path) for path in roots)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", os.defpath)
    return env


def _native_modules(repo_root: Path):
    # Native modules discover repository defaults at import time.
    os.chdir(repo_root)
    from integrations.ipfs_datasets.loader import ensure_import_paths
    ensure_import_paths("ipfs_accelerate_py.agent_supervisor")
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon
    return implementation_supervisor, implementation_daemon


def _branch(repo_root: Path) -> str:
    try:
        result = subprocess.run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
                                cwd=repo_root, text=True, capture_output=True, timeout=10)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("local Git branch lookup exceeded its ten-second deadline") from exc
    if result.returncode or not result.stdout.strip():
        raise ValueError("campaign requires an explicit checked-out local Git branch")
    return result.stdout.strip()


def _private_runtime_checks(repo_root: Path, env: Mapping[str, str]) -> dict[str, Any]:
    from ipfs_accelerate_py.agent_supervisor.runtime import grok_cli_runner
    if env.get(AUTOMATIC_RETRY_REARM_ENV) == "0":
        from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
        rearm_control = getattr(native, "automatic_retry_rearm_enabled", None)
        if (getattr(native, "AUTOMATIC_RETRY_REARM_ENV", None) != AUTOMATIC_RETRY_REARM_ENV
                or not callable(rearm_control) or rearm_control(env) is not False):
            return {"ready": False, "reason": "native_retry_budget_control_unavailable"}
    supported = getattr(grok_cli_runner, "GROK_PRIVATE_PATHS_VERSION", 0) >= 1
    validator = getattr(grok_cli_runner, "validate_grok_private_path_patterns", None)
    resolver = getattr(grok_cli_runner, "_grok_private_workspace_paths", None)
    supported = supported and callable(validator) and callable(resolver)
    if not supported:
        return {"ready": False, "native_enforcement_available": False,
                "reason": "native_private_path_enforcement_unavailable"}
    if env.get(REASONING_EFFORT_ENV) and getattr(grok_cli_runner, "GROK_REASONING_EFFORT_ENV", None) != REASONING_EFFORT_ENV:
        return {"ready": False, "native_enforcement_available": True,
                "reason": "native_reasoning_effort_control_unavailable"}
    try:
        patterns = validator(env[PRIVATE_PATHS_ENV])
        resolver(base_env=dict(env), workspace=repo_root)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError):
        # No path names or exception text enter public readiness telemetry.
        return {"ready": False, "native_enforcement_available": True,
                "reason": "native_private_path_policy_invalid"}
    # Use native root-owned Docker, fixed local socket and cached image
    # qualification; a successful ambient `docker info` is insufficient.
    docker = grok_cli_runner._docker_isolation_binary()
    base_image = ordinary_image = ""
    if docker:
        with tempfile.TemporaryDirectory(prefix="complaint-improvement-docker-config-") as directory:
            config = Path(directory)
            base_image = grok_cli_runner._docker_isolation_image_id(docker, docker_config=config)
            ordinary_image = grok_cli_runner._docker_ordinary_task_toolchain_image_id(docker, docker_config=config)
    machine = platform.machine().lower()
    architecture = {"x86_64": "amd64", "aarch64": "arm64"}.get(machine, machine)
    profile = getattr(grok_cli_runner, "_ordinary_task_toolchain_image_profile", None)
    image_architecture = profile()[1] if callable(profile) else ""
    architecture_matches = architecture == image_architecture
    docker_ready = bool(docker and base_image and ordinary_image and architecture_matches)
    reason = "ready"
    if not docker:
        reason = "trusted_local_docker_or_cached_base_image_unavailable"
    elif not base_image:
        reason = "cached_base_image_unavailable"
    elif not ordinary_image:
        reason = "qualified_ordinary_task_image_unavailable"
    elif not architecture_matches:
        reason = "ordinary_task_image_architecture_mismatch"
    return {"ready": docker_ready, "native_enforcement_available": True,
            "docker_ready": docker_ready, "private_path_patterns": list(patterns),
            "base_image_id": base_image, "ordinary_task_image_id": ordinary_image,
            "host_architecture": architecture, "image_architecture": image_architecture,
            "reason": reason}


def _auth_material_present(env: Mapping[str, str]) -> bool:
    """Presence only; never read credential bytes or claim provider validation."""
    if any(bool(env.get(key)) for key in (
            "XAI_API_KEY", "ipfs_accelerate_py_XAI_API_KEY", "IPFS_ACCELERATE_PY_XAI_API_KEY",
            "IPFS_DATASETS_PY_XAI_API_KEY")):
        return True
    auth_home = Path(env.get("GROK_HOME") or str(Path(env.get("HOME") or Path.home()) / ".grok"))
    try:
        entry = (auth_home / "auth.json").lstat()
        return bool(stat.S_ISREG(entry.st_mode) and entry.st_uid == os.getuid()
                    and entry.st_nlink == 1 and not entry.st_mode & 0o022
                    and 0 < entry.st_size <= 1_048_576)
    except OSError:
        return False



def _worktree_capacity(repo_root: Path, worktree_root: Path) -> dict[str, Any]:
    """Report a local pinned tracked-byte lower bound, without fetching objects."""
    probe = worktree_root
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    result: dict[str, Any] = {"filesystem_path": str(probe), "free_bytes": shutil.disk_usage(probe).free,
                              "minimum_cold_checkout_bytes": None, "sufficient": None}
    minimum = 0
    try:
        repositories = [(repo_root, "HEAD")]
        for directory, revision in repositories:
            observed = subprocess.run(["git", "ls-tree", "-r", "-l", "-z", revision], cwd=directory,
                capture_output=True, check=False, timeout=10, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
            if observed.returncode or len(observed.stdout) > 16_000_000:
                raise ValueError("local pinned Git tree unavailable or exceeds bound")
            for entry in observed.stdout.split(b"\0"):
                if not entry:
                    continue
                header, name = entry.split(b"\t", 1)
                mode, kind, oid, size = header.split()
                if kind == b"blob":
                    minimum += int(size)
                elif kind == b"commit" and name == b"external/ipfs_datasets_py" and directory == repo_root:
                    repositories.append((repo_root / "external/ipfs_datasets_py", oid.decode("ascii")))
        if len(repositories) != 2:
            raise ValueError("pinned datasets tree is unavailable")
        result.update(minimum_cold_checkout_bytes=minimum, sufficient=result["free_bytes"] >= minimum,
                      reason="local_pinned_tracked_blob_lower_bound", includes_filesystem_overhead=False,
                      assumes_uncompressed_file_content=True)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        result["reason"] = "local_pinned_checkout_size_unavailable"
    return result


RESOURCE_MIN_FREE_BYTES = 1_073_741_824
RESOURCE_MIN_FREE_INODES = 1024


class CampaignResourceHold(RuntimeError):
    """A local admission refusal, never a task failure/refund or live wait."""
    code = "campaign_resource_hold"

    def __init__(self, observation: Mapping[str, Any]):
        self.observation = dict(observation)
        super().__init__("campaign_resource_hold:" + str(observation.get("reason", "unavailable")))


def _resource_capacity(repo_root: Path, state_dir: Path, worktree_root: Path,
                       environment: Mapping[str, str]) -> dict[str, Any]:
    """Observe each storage role without creating paths or reserving capacity.

    Free bytes/inodes and access are a point-in-time admission observation;
    other writers, quotas and subsequent IO can still fail after this check.
    """
    paths = {"repository": repo_root, "state": state_dir, "worktrees": worktree_root,
             "home": Path(environment.get("HOME") or Path.home()),
             "temporary": Path(environment.get("TMPDIR") or tempfile.gettempdir())}
    roles = {}
    timed_out = False
    for role, raw_path in paths.items():
        row: dict[str, Any] = {"path": str(raw_path), "ready": False}
        try:
            path = Path(raw_path)
            if not path.is_absolute() or path.resolve(strict=False) != path:
                raise ValueError("resource path is not canonical")
            probe = path
            while not probe.exists() and probe != probe.parent:
                probe = probe.parent
            info = probe.stat()
            if not stat.S_ISDIR(info.st_mode) or (probe != path and info.st_uid != os.getuid()):
                raise ValueError("absent resource path lacks an owned existing directory")
            available = os.statvfs(probe)
            fields = (available.f_bavail, available.f_frsize, available.f_favail, available.f_files)
            if any(type(value) is not int or value < 0 for value in fields) or fields[1] == 0 or fields[3] == 0:
                raise ValueError("resource capacity metadata is unavailable")
            free_bytes, free_inodes = fields[0] * fields[1], fields[2]
            writable = (not available.f_flag & os.ST_RDONLY
                        and os.access(probe, os.W_OK | os.X_OK, effective_ids=True))
            ready = bool(writable and free_bytes >= RESOURCE_MIN_FREE_BYTES and free_inodes >= RESOURCE_MIN_FREE_INODES)
            row.update(filesystem_path=str(probe), free_bytes=free_bytes, free_inodes=free_inodes,
                       writable_observed=bool(writable), ready=ready,
                       reason="observed_capacity_ready" if ready else "local_capacity_insufficient")
        except TimeoutError:
            # Native's hook alarm is an OSError subclass. Stop this observation
            # immediately; swallowing it and proceeding would lose its bound.
            timed_out = True
            row["reason"] = "resource_observation_timed_out"
            roles[role] = row
            break
        except (OSError, ValueError, TypeError, AttributeError):
            row["reason"] = "local_capacity_unavailable"
        roles[role] = row
    for role, raw_path in paths.items():
        if role not in roles:
            roles[role] = {"path": str(raw_path), "ready": False, "reason": "unobserved_after_timeout"}
    ready = all(row["ready"] for row in roles.values())
    return {"schema": "complaint-campaign-resource-admission@1", "ready": ready,
            "reason": "resource_observation_timed_out" if timed_out else ("observed_capacity_ready" if ready else "local_capacity_hold"),
            "minimum_free_bytes_per_filesystem": RESOURCE_MIN_FREE_BYTES,
            "minimum_free_inodes_per_filesystem": RESOURCE_MIN_FREE_INODES,
            "roles": roles, "capacity_reserved": False, "paid_dispatch": False,
            "attempt_refunded": False, "accounting_changed": False,
            "live_wait_or_lease_claimed": False}


def _require_resource_capacity(repo_root: Path, state_dir: Path, worktree_root: Path,
                               environment: Mapping[str, str], *, stage: str) -> None:
    observed = _resource_capacity(repo_root, state_dir, worktree_root, environment)
    if not observed["ready"]:
        raise CampaignResourceHold({**observed, "stage": stage})


def _resource_admission_hook(repo_root: Path, state_dir: Path, worktree_root: Path,
                             environment: Mapping[str, str]):
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon_runner import (
        DaemonLoopHook, DaemonHookTimeoutError,
    )
    # Native's generic optional hook timeout is normally logged and ignored.
    # Convert it inside the callback so this mandatory admission check refuses
    # before run_once; every other hold also propagates through the sole loop.
    def before_pass(_context):
        try:
            _require_resource_capacity(repo_root, state_dir, worktree_root, environment,
                                       stage="before_native_pass")
        except DaemonHookTimeoutError:
            raise CampaignResourceHold({"schema": "complaint-campaign-resource-admission@1",
                "ready": False, "reason": "resource_observation_timed_out", "stage": "before_native_pass",
                "paid_dispatch": False, "accounting_changed": False, "attempt_refunded": False,
                "live_wait_or_lease_claimed": False}) from None
    return DaemonLoopHook(phase="before", message="Campaign resource admission hold: %s", callback=before_pass)


def native_argv(board_path: Path, state_dir: Path, merge_target: str, *, worktree_root: Path | None = None) -> list[str]:
    """Compile only options supported by the actual native supervisor parser."""
    return [
        "--todo-path", str(board_path), "--state-dir", str(state_dir),
        "--state-prefix", STATE_PREFIX, "--board-namespace", "complaint-intake-improvement",
        "--task-prefix", TASK_PREFIX, "--task-source-kind", "legacy-markdown",
        "--authority-mode", "legacy_markdown", "--explicit-legacy-task-source", "--implement",
        "--check-interval", "5", "--daemon-interval", "10",
        "--watchdog-startup-grace-seconds", str(STARTUP_SECONDS), "--stale-seconds", "120",
        "--implementation-timeout", str(TIMEOUT_SECONDS),
        "--implementation-max-timeout", str(TIMEOUT_SECONDS),
        "--implementation-log-stall-seconds", str(STALL_SECONDS),
        "--max-task-attempts", "3", "--max-restarts", "5", "--validation-max-workers", "1",
        "--task-shard-count", "1", "--task-shard-index", "0",
        "--worktree-root", str(worktree_root if worktree_root is not None else state_dir / "worktrees"), "--merge-target-branch", merge_target,
        # Every task validation imports datasets, and shared interviews use
        # Kit's pinned WAL even when tasks edit only first-party files.
        "--worktree-submodule-path", "external/ipfs_datasets_py",
        "--worktree-submodule-path", "external/ipfs_kit_py",
        "--merge-queue-dir", str(state_dir / "merge-queue"),
        "--llm-merge-resolver-command", "",
        # Native recovers interrupted owned proposals through the measured
        # scheduler and normal merge callback before another provider starts.
        "--no-objective-task-janitor", "--no-objective-goal-refinement",
        "--no-objective-goal-completion-reconcile", "--no-objective-goal-migration",
        "--no-objective-ast-dataset", "--no-objective-todo-vector-index",
        "--no-retry-budget-guardrail", "--no-dependency-guardrail", "--no-reconciliation-guardrail",
    ]


def _board_summary(tasks: list[Any]) -> dict[str, Any]:
    completed = {task.task_id for task in tasks if task.status == "completed"}
    held = []
    ready = []
    for task in tasks:
        raw_status = str(task.metadata.get("status", task.status)).lower().replace("-", "_")
        manual = raw_status in {"paused", "waiting_user", "waiting_for_user", "on_hold", "manual_hold"}
        manual = manual or str(task.metadata.get("manual hold", "")).lower() in {"1", "true", "yes"}
        if manual:
            held.append(task.task_id)
        elif task.status in {"todo", "needed", "pending"} and set(task.depends_on) <= completed:
            ready.append(task.task_id)
    return {"count": len(tasks), "status_counts": dict(Counter(task.status for task in tasks)),
            "completed": len(completed), "ready_task_ids": ready, "manual_hold_task_ids": held}


def _validate_board(repo_root: Path, board_path: Path, spec: Mapping[str, Any]) -> dict[str, Any]:
    _, daemon = _native_modules(repo_root)
    tasks = daemon.parse_task_file(board_path, task_header_prefix=TASK_PREFIX)
    expected = {task["id"]: task for task in spec["tasks"]}
    if len(tasks) != len(expected) or {task.task_id for task in tasks} != set(expected):
        raise ValueError("native task parser did not ingest every planned task exactly once")
    for task in tasks:
        item = expected[task.task_id]
        if set(task.depends_on) != set(item["depends_on"]) or task.validation != item["validation_commands"]:
            raise ValueError(f"native task references/validation differ for {task.task_id}")
        if task.metadata.get("provider role") != "grok-only" or task.metadata.get("model") != MODEL:
            raise ValueError(f"task {task.task_id} lost its explicit Grok-only model route")
    return _board_summary(tasks)


def prepare(repo_root: Path, spec_path: Path, state_dir: Path) -> dict[str, Any]:
    os.chdir(repo_root)
    from .improvement_plan import generate, load_spec
    result = generate(spec_path, repo_root)
    result["board"] = _validate_board(repo_root, Path(result["board_path"]), load_spec(spec_path))
    result["state_dir"] = str(state_dir)
    result["execution_started"] = False
    return result


def doctor(repo_root: Path, spec_path: Path, state_dir: Path, *, merge_target: str | None = None, worktree_root: Path | None = None) -> dict[str, Any]:
    """Read-only readiness checks: never run a model, daemon, or auth command."""
    selected_root, root_binding = _select_worktree_root(repo_root, state_dir, _read_json(state_dir / "launcher.json"), worktree_root)
    resources = _resource_capacity(repo_root, state_dir, selected_root, os.environ)
    if not resources["ready"]:
        return {"status": "not_ready", "reason": CampaignResourceHold.code, "resource_capacity": resources,
                "paid_calls": 0, "native_config_validated": False, "execution_started": False}
    os.chdir(repo_root)
    from .improvement_plan import BOARD_RELATIVE, build_improvement_work_plan, load_spec
    spec = load_spec(spec_path)
    plan = build_improvement_work_plan(spec)
    branch = merge_target or _branch(repo_root)
    supervisor, _ = _native_modules(repo_root)
    args = native_argv(repo_root / BOARD_RELATIVE, state_dir, branch, worktree_root=selected_root)
    parsed = supervisor.parse_args(args)
    config = supervisor.supervisor_config_from_args(parsed, repo_root=repo_root)
    board = _validate_board(repo_root, repo_root / BOARD_RELATIVE, spec)
    env = campaign_environment(repo_root, context_exclude=spec["execution_policy"].get("context_exclude"), state_dir=state_dir)
    grok = shutil.which(env.get("IPFS_ACCELERATE_AGENT_GROK_BIN") or "grok", path=env.get("PATH"))
    auth_present = _auth_material_present(env)
    privacy = _private_runtime_checks(repo_root, env)
    capacity = _worktree_capacity(repo_root, selected_root)
    return {"status": "ready" if grok and auth_present and privacy["ready"] and capacity["sufficient"] is not False and resources["ready"] else "not_ready",
            "provider": "grok_cli", "model": MODEL, "allow_fallback": False,
            "grok_binary_present": bool(grok), "auth_material_present": bool(auth_present),
            "auth_provider_command_supported": False,
            "auth_validated": False, "paid_calls": 0, "native_plan_id": plan.plan_id,
            "native_config_validated": True, "native_task_source": parsed.task_source_kind,
            "ephemeral_worktrees": config.use_ephemeral_worktree, "merge_target": branch,
            "privacy": privacy, "worktree_capacity": capacity, "resource_capacity": resources, "worktree_root": str(selected_root), "worktree_root_binding": root_binding,
            "board": board, "native_argv": args,
            "limitations": ["Credential presence does not verify login, quota, model access or execution progress.",
                            "Native supervisor retries are bounded per task and to five daemon restarts; manual holds are never cleared.",
                            "Cross-worktree reconciliation and dynamic guardrail/refill task generation are disabled for this fixed campaign; native dependency readiness, process fencing and implementation watchdog remain enabled."]}


def start(repo_root: Path, spec_path: Path, state_dir: Path, *, worktree_root: Path | None = None) -> dict[str, Any]:
    state_dir = state_dir.resolve()
    prospective_root, _ = _select_worktree_root(repo_root, state_dir, _read_json(state_dir / "launcher.json"), worktree_root)
    resources = _resource_capacity(repo_root, state_dir, prospective_root, os.environ)
    if not resources["ready"]:
        return {"status": "not_ready", "reason": CampaignResourceHold.code, "resource_capacity": resources,
                "paid_calls": 0, "execution_started": False}
    with _lock(state_dir):
        owner_path = state_dir / "launcher.json"
        previous = _read_json(owner_path)
        if previous.get("read_error"):
            return _stop_incomplete(state_dir, "launcher_receipt_unreadable")
        selected_root, root_binding = _select_worktree_root(repo_root, state_dir, previous, worktree_root)
        full_launch = _full_launch_record(previous)
        # Compare the requested campaign before treating a live PID as this launch.
        # A matching live owner is reused; a different repo, spec, plan, or epoch is not signalled.
        if owns_process(previous):
            if full_launch and not _campaign_tuple_matches(previous, repo_root, spec_path, state_dir):
                return _stop_incomplete(state_dir, "live_campaign_mismatch")
            return {"status": "already_running", "pid": previous["identity"]["pid"], "state_dir": str(state_dir)}
        shutdown_path = state_dir / "container_shutdown.json"
        shutdown = {}
        shutdown_raw = None
        if full_launch:
            # Campaign identity is required for stopped owners as well as live
            # ones. Cached closure never grants a different campaign ownership.
            if not _campaign_tuple_matches(previous, repo_root, spec_path, state_dir):
                return _stop_incomplete(state_dir, "stopped_campaign_mismatch")
            from .improvement_shutdown import _context, _parent_closed
            from .improvement_recovery import _owned_bytes
            try:
                context = _context(state_dir, previous)
                if context is None:
                    return _stop_incomplete(state_dir, "launcher_receipt_unverified")
                _parent_closed(state_dir, previous, context, False)
                shutdown_raw = _owned_bytes(shutdown_path)
                shutdown = json.loads(shutdown_raw)
            except (OSError, ValueError, TypeError, KeyError):
                return _stop_incomplete(state_dir, "shutdown_proof_unverified")
            if not isinstance(shutdown, dict) or not _shutdown_verified(previous, shutdown, repo_root, state_dir):
                return _stop_incomplete(state_dir, "shutdown_proof_unverified")
        # A missing owner cannot hide orphaned workers. This observation has
        # no authority to call the explicit stop helper or rewrite its receipt.
        if not _observe_campaign_containers(repo_root, state_dir, selected_root, previous, shutdown):
            return _stop_incomplete(state_dir, "container_closure_unverified")
        if _read_json(owner_path) != previous:
            return _stop_incomplete(state_dir, "ownership_changed_during_observation")
        if full_launch:
            try:
                if _owned_bytes(shutdown_path) != shutdown_raw:
                    return _stop_incomplete(state_dir, "shutdown_proof_changed_during_observation")
                _parent_closed(state_dir, previous, context, False)
                recorded_worktree_root(previous, state_dir)
            except (OSError, ValueError, TypeError, KeyError):
                return _stop_incomplete(state_dir, "ownership_changed_during_observation")
        # A missing/edited owner receipt cannot authorize a duplicate runner.
        for candidate in Path("/proc").iterdir():
            if candidate.name.isdigit():
                identity = process_identity(int(candidate.name))
                argv = identity["argv"] if identity else []
                native = any("ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_" in argument for argument in argv)
                if ("_run" in argv or native) and "--state-dir" in argv and str(state_dir) in argv:
                    raise RuntimeError("campaign runner exists without a valid owner receipt; inspect its ownership before restarting")
        prepared = prepare(repo_root, spec_path, state_dir)
        check = (doctor(repo_root, spec_path, state_dir, worktree_root=selected_root) if root_binding is not None
                 else doctor(repo_root, spec_path, state_dir))
        if check["status"] != "ready":
            return {"status": "not_ready", "doctor": check}
        if root_binding is not None:
            root_binding = _validate_worktree_root(repo_root, state_dir, selected_root, claim=True)
        token = secrets.token_hex(24)
        script = repo_root / "scripts/run_complaint_improvement_supervisor.py"
        argv = [sys.executable, str(script), "_run", "--repo-root", str(repo_root),
                "--spec", str(spec_path), "--state-dir", str(state_dir),
                "--owner-token", token, "--merge-target", check["merge_target"]]
        if root_binding is not None:
            argv.extend(["--worktree-root", str(selected_root)])
        log_path = state_dir / "launcher.log"
        from .improvement_plan import load_spec
        policy = load_spec(spec_path)["execution_policy"]
        with log_path.open("ab", buffering=0) as log:
            process = subprocess.Popen(argv, cwd=repo_root, env=campaign_environment(repo_root, context_exclude=policy.get("context_exclude"), state_dir=state_dir),
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True, close_fds=True)
        identity = None
        for _ in range(20):
            identity = process_identity(process.pid)
            if identity and identity["argv"] == argv:
                break
            if process.poll() is not None:
                raise RuntimeError(f"native wrapper exited before ownership registration; inspect {log_path}")
            time.sleep(0.025)
        record = {"schema_version": "complaint-improvement-launcher@1", "identity": identity,
                  "argv": argv, "owner_token": token, "started_at": time.time(),
                  "status": "starting", "repo_root": str(repo_root), "spec_path": str(spec_path),
                  "state_dir": str(state_dir), "merge_target": check["merge_target"],
                  "board_path": prepared["board_path"], "plan_id": check["native_plan_id"],
                  "provider": "grok_cli", "model": MODEL, "allow_fallback": False}
        if root_binding is not None:
            record.update(worktree_root=str(selected_root), worktree_root_binding=root_binding)
        if not owns_process(record):
            process.terminate()
            process.wait(timeout=5)
            raise RuntimeError("spawned process did not establish exact launcher ownership")
        _atomic_json(owner_path, record)
        return {"status": "starting", "pid": process.pid, "state_dir": str(state_dir),
                "log_path": str(log_path), "provider": "grok_cli", "model": MODEL,
                "progress_verified": False,
                "next_check": "status must show native heartbeat and task/provider progress"}


def _tail(path: Path, *, lines: int = 12, maximum: int = 24_000) -> list[str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - maximum))
            return [line[:2000] for line in handle.read(maximum).decode(errors="replace").splitlines()[-lines:]]
    except OSError:
        return []


def _age(path: Path, now: float) -> float | None:
    try:
        return max(0.0, now - path.stat().st_mtime)
    except OSError:
        return None


def _timestamp_age(value: Any, now: float) -> float | None:
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return max(0.0, now - timestamp.timestamp())
    except (ValueError, TypeError):
        return None


def _native_state_reader(connection: Any, state_path: Path) -> None:
    """Read a real native projection without opening/creating a new catalog."""
    try:
        for name in ("IPFS_ACCELERATE_AGENT_QUACK_ENDPOINT", "IPFS_ACCELERATE_AGENT_CONTROL_DUCKDB",
                     "IPFS_ACCELERATE_AGENT_CONTROL_DUCKLAKE"):
            os.environ.pop(name, None)
        from integrations.ipfs_datasets.loader import ensure_import_paths
        ensure_import_paths("ipfs_accelerate_py.agent_supervisor")
        # Match the launcher's explicit native root; neither observation nor
        # execution may adopt global catalogs from unrelated campaigns.
        os.environ[ORCHESTRATION_DIR_ENV] = str(state_path.parent / "control-plane")
        from ipfs_accelerate_py.agent_supervisor.todo_daemon import portal_task_state_control_plane as plane
        payload = plane.read_task_state_payload(state_path)
        if payload is None and state_path.is_file():
            payload = _read_json(state_path)
        authority = plane.task_state_authority_file(state_path)
        if len(json.dumps(payload or {})) > 2_000_000:
            raise ValueError("native_state_size_limit")
        connection.send((payload or {}, {
            "source": "native_control_plane" if authority and authority != state_path else "legacy_json",
            "authority_path": str(authority) if authority else None,
            "completion_authority": False,
        }))
    except Exception as exc:
        connection.send(({"read_error": type(exc).__name__}, {"source": "unavailable", "completion_authority": False}))
    finally:
        connection.close()


def _read_native_state(repo_root: Path, state_path: Path, *, timeout_seconds: float = 3.0) -> tuple[dict[str, Any], dict[str, Any]]:
    _native_modules(repo_root)
    # Native file-lock/transport timeouts can be much longer than a status
    # check. Isolate this read, enforce a deadline, and never call .load(),
    # whose default create=True may initialize a catalog.
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    child = context.Process(target=_native_state_reader, args=(send, state_path), daemon=True)
    original_path = list(sys.path)
    try:
        # Editable installs can still point at the user's primary checkout.
        # The spawned observer must import this exact wrapper revision.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        child.start()
    finally:
        sys.path[:] = original_path
    send.close()
    try:
        if receive.poll(timeout_seconds):
            return receive.recv()
        return {"read_error": "native_state_read_timeout"}, {"source": "unavailable", "completion_authority": False}
    except (EOFError, OSError):
        return {"read_error": "native_state_reader_failed"}, {"source": "unavailable", "completion_authority": False}
    finally:
        receive.close()
        if child.is_alive():
            child.terminate()
        child.join(timeout=1)
        if child.is_alive():
            child.kill()
            child.join(timeout=1)


_PROVIDER_START_TYPES = {"implementation_provider_started", "provider_runner_started", "provider_runner_birth"}
_VALIDATION_EVENT_TYPES = {"validation_started", "validation_command_started", "validation_activity"}
_INTERVIEW_PHASES = {"waiting_for_user", "waiting_user", "awaiting_user", "manual_hold", "paused", "cancelled", "canceled"}
_COOLDOWN_NAME = "recovery_cooldown.json"


def _event_timestamp(event: Mapping[str, Any]) -> float | None:
    try:
        timestamp = datetime.fromisoformat(str(event.get("timestamp", "")).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.timestamp()
    except (ValueError, TypeError, AttributeError):
        return None


def _attempt_binding(native_state: Mapping[str, Any]) -> dict[str, Any]:
    attempt = native_state.get("active_attempt")
    if attempt in (None, "", 0, "0"):
        attempt = None
    elif isinstance(attempt, bool) or not isinstance(attempt, int):
        try:
            attempt = int(attempt)
        except (TypeError, ValueError):
            attempt = None
    log_path = native_state.get("active_log_path")
    execution_start = None
    if (native_state.get("active_task_id") and native_state.get("active_task_cid")
            and native_state.get("last_implementation_task_id") == native_state.get("active_task_id")
            and native_state.get("last_implementation_task_cid") == native_state.get("active_task_cid")
            and native_state.get("last_implementation_log_path") == log_path
            and native_state.get("last_implementation_worktree_path") == native_state.get("active_worktree_path")):
        execution_start = native_state.get("last_implementation_started_at")
    return {
        "execution_started_at": execution_start,
        "task_id": str(native_state.get("active_task_id") or native_state.get("last_implementation_task_id") or ""),
        "task_cid": str(native_state.get("active_task_cid") or native_state.get("last_implementation_task_cid") or ""),
        "attempt": attempt,
        "worktree": str(native_state.get("active_worktree_path") or native_state.get("last_implementation_worktree_path") or ""),
        "log_prefix": str(log_path) if isinstance(log_path, str) else "",
        "attempt_started_at": native_state.get("active_task_started_at") or native_state.get("last_implementation_started_at"),
    }


def _event_matches_attempt(event: Mapping[str, Any], binding: Mapping[str, Any], *, started_at: float,
                           require_log: bool) -> bool:
    """Bind one frame to this attempt. Task id alone never qualifies."""
    observed = _event_timestamp(event)
    if observed is None or observed < started_at:
        return False
    if binding.get("attempt_started_at"):
        started = _event_timestamp({"timestamp": binding.get("attempt_started_at")})
        if started is None or observed < started:
            return False
    task_id = binding.get("task_id") or ""
    if not task_id or event.get("task_id") != task_id:
        return False
    event_cid = event.get("canonical_task_cid") or event.get("task_cid")
    claim_cid = binding.get("task_cid") or ""
    if claim_cid:
        if event_cid != claim_cid:
            return False
    elif event_cid:
        return False
    event_attempt = event.get("attempt")
    claim_attempt = binding.get("attempt")
    if claim_attempt:
        if event_attempt != claim_attempt:
            return False
    elif event_attempt not in (None, ""):
        return False
    event_worktree = event.get("worktree_path") or event.get("worktree")
    claim_worktree = binding.get("worktree") or ""
    if claim_worktree:
        if event_worktree != claim_worktree:
            return False
    elif event_worktree:
        return False
    event_log = event.get("log_path") or event.get("log_prefix")
    claim_log = binding.get("log_prefix") or ""
    if claim_log and require_log:
        if not isinstance(event_log, str) or not (event_log == claim_log):
            return False
    elif event_log and claim_log and not (isinstance(event_log, str) and (event_log == claim_log)):
        return False
    elif event_log and not claim_log:
        return False
    invocation = event.get("invocation_started_at") or event.get("owned_invocation_started_at")
    if invocation is not None:
        invoked = _event_timestamp({"timestamp": invocation})
        if invoked is None or invoked < started_at:
            return False
    return True


def _grok_frame(event: Mapping[str, Any]) -> bool:
    model = str(event.get("model") or event.get("provider_model") or "")
    provider = str(event.get("provider") or "")
    if "grok" not in model.lower() and provider not in {"grok", "grok_cli"}:
        return False
    if event.get("type") in {"grok_usage", "grok_tool_call", "grok_tool_frame", "provider_usage", "provider_tool_frame"}:
        return True
    return any(event.get(key) for key in ("usage", "tool_calls", "tool_frames", "tool_frame"))


def _matching_event(path: Path, binding: Mapping[str, Any], *, started_at: float, kind: str) -> dict[str, Any] | None:
    for line in reversed(_tail(path, lines=80, maximum=256_000)):
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        provider_start = event.get("type") in _PROVIDER_START_TYPES
        validation = event.get("type") in _VALIDATION_EVENT_TYPES
        grok = _grok_frame(event)
        if kind == "provider" and not (provider_start or grok):
            continue
        if kind == "validation" and not validation:
            continue
        if not _event_matches_attempt(event, binding, started_at=started_at, require_log=provider_start or validation):
            continue
        evidence_kind = "grok_frame" if grok and not provider_start else str(event.get("type"))
        return {"type": evidence_kind, "timestamp": event.get("timestamp"), "task_id": binding.get("task_id"),
                "task_cid": binding.get("task_cid") or None, "attempt": binding.get("attempt"),
                "source": "native_daemon_events", "completion_authority": False}
    return None


def _owned_attempt_log_evidence(events_path: Path, state_dir: Path, binding: Mapping[str, Any],
                                *, started_at: float, now: float) -> dict[str, Any] | None:
    """Observe native Grok NDJSON through this exact attempt's start and log.

    Frames do not contain task/CID/time fields. The native start event and
    native text headers provide those bindings; frame contents grant no task
    completion or recovery authority. File freshness is an observation only.
    """
    from .improvement_recovery import _owned_bytes
    try:
        log = Path(str(binding.get("log_prefix") or ""))
        attempt_start = _event_timestamp({"timestamp": binding.get("execution_started_at")})
        selection_start = _event_timestamp({"timestamp": binding.get("attempt_started_at")})
        if (attempt_start is None or selection_start is None or attempt_start < selection_start or not log.is_absolute() or log.resolve(strict=True) != log
                or not log.is_relative_to(state_dir.resolve()) or not binding.get("task_cid")
                or type(binding.get("attempt")) is not int or binding["attempt"] <= 0):
            return None
        events = _owned_bytes(events_path, MAX_EVENT_HISTORY_BYTES, legacy_group_write=True)
        if not events.endswith(b"\n"):
            return None
        start = None
        for line in reversed(events.splitlines()):
            event = json.loads(line)
            if not isinstance(event, dict):
                return None
            if event.get("type") == "implementation_started":
                # A later attempt/selection cannot borrow an earlier log.
                if not _event_matches_attempt(event, binding, started_at=started_at, require_log=True):
                    return None
                start = event
                break
            if (event.get("type") == "implementation_finished"
                    and _event_matches_attempt(event, binding, started_at=started_at, require_log=False)):
                return None
        if (start is None or start.get("execution_mode") != "model-assisted"
                or _event_timestamp(start) < attempt_start):
            return None
        before = log.lstat()
        raw = _owned_bytes(log, 32 * 1024 * 1024)
        after = log.lstat()
        if (len(raw) != before.st_size or any(getattr(before, field) != getattr(after, field)
                for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"))):
            return None
        if (before.st_mtime < attempt_start or now - before.st_mtime > STALL_SECONDS
                or before.st_mtime > now + 2):
            return None
        lines = raw.splitlines()
        headers = {}
        for line in lines[:8]:
            name, sep, value = line.partition(b": ")
            if sep and name in {b"Task", b"Started", b"Workspace"}:
                if name in headers:
                    return None
                headers[name] = value.decode("utf-8")
        if (headers.get(b"Task", "").split(" ", 1)[0] != binding["task_id"]
                or headers.get(b"Started") != binding.get("execution_started_at")
                or headers.get(b"Workspace") != binding.get("worktree")):
            return None
        complete = raw[:raw.rfind(b"\n") + 1]
        counts = Counter()
        terminal = False
        for line in complete.splitlines():
            if not line.startswith(b"{"):
                continue
            try:
                frame = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(frame, dict):
                continue
            kind = frame.get("type")
            if type(kind) is not str:
                continue
            if kind == "usage" and isinstance(frame.get("usage"), dict):
                counts["usage"] += 1
                # A native repair round can append to this same owned log.
                terminal = False
            elif kind in {"tool_call", "tool_call_update"}:
                counts[kind] += 1
                terminal = False
            elif kind in {"end", "error", "max_turns_reached"}:
                terminal = True
        if not counts:
            return None
        return {"type": "grok_frame", "source": "owned_attempt_log", "task_id": binding["task_id"],
                "task_cid": binding["task_cid"], "attempt": binding["attempt"],
                "log_path": str(log), "log_bytes": len(raw), "log_mtime_ns": before.st_mtime_ns,
                "frame_counts": dict(counts), "provider_terminal_observed": terminal,
                "progress_fresh": not terminal, "completion_authority": False}
    except (OSError, ValueError, TypeError, KeyError, UnicodeDecodeError):
        return None


def _provider_event_evidence(path: Path, *, task_id: str, started_at: float,
                             binding: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    resolved = dict(binding or {})
    resolved.setdefault("task_id", task_id)
    return _matching_event(path, resolved, started_at=started_at, kind="provider")


def _validation_event_evidence(path: Path, binding: Mapping[str, Any], *, started_at: float) -> dict[str, Any] | None:
    return _matching_event(path, binding, started_at=started_at, kind="validation")


def _owner_liveness(birth: Any) -> str:
    if not isinstance(birth, dict) or not birth.get("pid"):
        return "missing"
    try:
        current = process_identity(int(birth["pid"]))
    except (OSError, ValueError, TypeError):
        return "unknown"
    if not isinstance(current, dict):
        return "dead"
    if current.get("unknown") or current.get("start_ticks") is None or current.get("boot_id") is None:
        return "unknown"
    if (current.get("start_ticks") != birth.get("start_ticks", birth.get("start_time_ticks"))
            or current.get("boot_id") != birth.get("boot_id")):
        return "pid_reuse"
    return "alive"


def status(repo_root: Path, spec_path: Path, state_dir: Path) -> dict[str, Any]:
    from .improvement_plan import BOARD_RELATIVE, load_spec
    record = _read_json(state_dir / "launcher.json")
    owned = owns_process(record)
    identity = record.get("identity")
    identity = identity if isinstance(identity, dict) else {}
    state_path = state_dir / f"{STATE_PREFIX}_task_state.json"
    heartbeat_path = state_dir / f"{STATE_PREFIX}_supervisor_status.json"
    strategy_path = state_dir / f"{STATE_PREFIX}_strategy.json"
    events_path = state_dir / f"{STATE_PREFIX}_events.jsonl"
    supervisor_events = state_dir / f"{STATE_PREFIX}_supervisor_events.jsonl"
    native_state, state_source = _read_native_state(repo_root, state_path)
    heartbeat, strategy = (_read_json(path) for path in (heartbeat_path, strategy_path))
    now = time.time()
    heartbeat_age = _age(heartbeat_path, now)
    try:
        board = _validate_board(repo_root, repo_root / BOARD_RELATIVE, load_spec(spec_path))
    except Exception as exc:
        board = {"read_error": str(exc), "count": 0, "completed": 0, "ready_task_ids": [], "manual_hold_task_ids": []}
    # Native selection sets active_task_id before an attempt or worker exists.
    # Only the execution flag identifies an active implementation/validation.
    active = bool(native_state.get("implementation_in_progress"))
    try:
        since_start = max(0.0, now - float(record.get("started_at", now)))
    except (TypeError, ValueError):
        since_start = 0.0
    phase = str(native_state.get("active_phase", "")).lower()
    intentional_wait = phase in _INTERVIEW_PHASES or bool(native_state.get("manual_hold") or native_state.get("manual_cancellation"))
    if state_source["source"] == "native_control_plane":
        row_ages = [age for key in ("heartbeat_at", "last_progress_at")
                    if (age := _timestamp_age(native_state.get(key), now)) is not None]
        state_age = min(row_ages) if row_ages else None
    else:
        state_age = _age(state_path, now)
    current_state = state_age is not None and state_age <= since_start
    active = active and current_state
    selected = current_state and bool(native_state.get("active_task_id")) and not active
    progress_paths = [events_path, supervisor_events]
    # A previous attempt's log is historical evidence, never this claim's
    # progress clock. Observe only a current execution's explicitly active log.
    log_name = native_state.get("active_log_path") if active else None
    if isinstance(log_name, str) and log_name:
        candidate = Path(log_name)
        if candidate.resolve().is_relative_to(state_dir.resolve()):
            progress_paths.append(candidate)
    ages = [age for path in progress_paths if (age := _age(path, now)) is not None]
    progress_age = min(ages) if ages else None
    # A previous run's task claim is never evidence this launch made progress.
    if heartbeat_age is not None and heartbeat_age > since_start:
        heartbeat_age = None
    active_age = _age(progress_paths[-1], now) if log_name and len(progress_paths) > 2 else None
    attempt_age = _timestamp_age(native_state.get("active_task_started_at"), now)
    if active_age is None:
        active_age = attempt_age
    heartbeat_status = str(heartbeat.get("status", ""))
    heartbeat_owner = heartbeat.get("supervisor_pid")
    daemon_identity = process_identity(heartbeat.get("daemon_pid"))
    daemon_alive = bool(daemon_identity and daemon_identity.get("ppid") == identity.get("pid"))
    startup_maintenance = (
        heartbeat_status in {"agentic_maintenance_started", "agentic_maintenance_completed"}
        and since_start <= STARTUP_SECONDS and not heartbeat.get("daemon_pid")
        and not heartbeat.get("last_agentic_maintenance_error")
    )
    maintenance_ready = False
    if heartbeat_status in {"agentic_maintenance_started", "agentic_maintenance_completed"} and daemon_alive:
        from ipfs_accelerate_py.agent_supervisor.todo_daemon.supervisor_activity import observe_supervisor_activity
        maintenance_ready = observe_supervisor_activity(
            heartbeat, now=datetime.fromtimestamp(now, timezone.utc), heartbeat_max_age_seconds=120,
        ).phase_ready
    last_started_age = _timestamp_age(native_state.get("last_implementation_started_at"), now)
    claim_verified = owned and current_state and bool(native_state.get("active_task_id") or
        (last_started_age is not None and last_started_age <= since_start))
    binding = _attempt_binding(native_state)
    invocation_start = now - since_start
    provider_evidence = _provider_event_evidence(
        events_path, task_id=binding["task_id"], started_at=invocation_start, binding=binding,
    ) if claim_verified else None
    if claim_verified:
        log_evidence = _owned_attempt_log_evidence(events_path, state_dir, binding, started_at=invocation_start, now=now)
        provider_evidence = log_evidence or provider_evidence
    provider_progress = bool(provider_evidence and provider_evidence.get("progress_fresh", True))
    validation_evidence = _validation_event_evidence(events_path, binding, started_at=invocation_start) if claim_verified else None
    worker_liveness = _owner_liveness(native_state.get("owner_process_birth"))
    if worker_liveness == "missing":
        worker_liveness = "alive" if daemon_alive else ("absent" if not owned else "unknown")
    shutdown = _read_json(state_dir / "container_shutdown.json")
    full_launch = record.get("schema_version") == "complaint-improvement-launcher@1"
    try:
        selected_root, root_binding = recorded_worktree_root(record, state_dir)
        worktree_error = None
    except (OSError, ValueError, TypeError) as error:
        selected_root, root_binding, worktree_error = None, None, str(error)
    shutdown_verified = _shutdown_verified(record, shutdown, repo_root, state_dir) and worktree_error is None
    if not owned:
        if identity and process_identity(identity.get("pid")):
            health = "identity_mismatch"
        else:
            health = "stop_incomplete" if full_launch and not shutdown_verified else "stopped"
    elif board.get("read_error"):
        health = "board_error"
    elif native_state.get("read_error") or heartbeat.get("read_error"):
        health = "state_error"
    elif board["count"] and board["completed"] == board["count"]:
        health = "complete"
    elif heartbeat_age is not None and heartbeat_owner != identity.get("pid"):
        health = "heartbeat_identity_mismatch"
    elif heartbeat_age is not None and heartbeat_age > 120:
        health = "stalled"
    elif active and attempt_age is not None and attempt_age > TIMEOUT_SECONDS:
        health = "stalled"
    elif heartbeat_age is not None and startup_maintenance:
        health = "starting"
    elif heartbeat_age is not None and maintenance_ready:
        health = "active" if active else "maintenance"
    elif heartbeat_age is not None and heartbeat_status not in {"running", "starting", "restarting", "recycling"}:
        health = "daemon_failed"
    elif heartbeat_age is not None and heartbeat_status == "running" and (heartbeat.get("daemon_pid_alive") is False or not daemon_alive):
        health = "daemon_failed"
    elif intentional_wait and current_state:
        health = "waiting_for_user"
    elif not board["ready_task_ids"] and not active and board["manual_hold_task_ids"]:
        health = "waiting_for_user"
    elif heartbeat_age is None and since_start <= STARTUP_SECONDS:
        health = "starting"
    elif heartbeat_age is None or heartbeat_age > TIMEOUT_SECONDS + 30:
        health = "stalled"
    elif heartbeat_owner != identity.get("pid"):
        health = "heartbeat_identity_mismatch"
    elif heartbeat_status in {"starting", "restarting", "recycling"}:
        health = heartbeat_status
    elif heartbeat_status != "running" or heartbeat.get("daemon_pid_alive") is False or not daemon_alive:
        health = "daemon_failed"
    elif heartbeat_age > 120:
        health = "stalled"
    elif active:
        hard_expired = attempt_age is not None and attempt_age > TIMEOUT_SECONDS
        log_stale = active_age is not None and active_age > STALL_SECONDS
        silent_window = attempt_age is not None and attempt_age > STALL_SECONDS
        in_validation = phase.startswith("valid")
        # Fresh generic log lines and a live PID are not provider or validation progress.
        silent = silent_window and (validation_evidence is None if in_validation else not provider_progress)
        post_provider = bool(provider_evidence and provider_evidence.get("provider_terminal_observed"))
        health = ("stalled" if hard_expired or log_stale else "post_provider" if post_provider
                  else "stalled" if silent else "active")
    elif selected:
        health = "no_progress" if (attempt_age if attempt_age is not None else since_start) > STALL_SECONDS else "selected"
    elif not current_state and since_start > STARTUP_SECONDS:
        # Supervisor heartbeats and watchdog events prove liveness only. An
        # early native deferral can otherwise look healthy indefinitely while
        # it leaves the task-state row untouched from the previous launch.
        health = "no_progress"
    elif current_state and native_state.get("blocked_task_ids") and not native_state.get("selectable_ready_task_ids"):
        health = "blocked"
    elif not board["ready_task_ids"]:
        health = "blocked"
    elif progress_age is not None and progress_age > STALL_SECONDS:
        health = "no_progress"
    else:
        health = "running"
    if worktree_error is not None:
        health = "identity_mismatch" if owned else "stop_incomplete"
    keys = ("heartbeat_at", "last_progress_at", "active_task_id", "active_task_cid", "active_task_started_at", "active_phase", "active_phase_detail",
            "implementation_in_progress", "active_attempt", "active_worktree_path", "active_log_path", "owner_process_birth",
            "last_implementation_returncode", "implementation_attempts", "implementation_attempts_by_cid",
            "recommended_task_id", "ready_task_ids", "selectable_ready_task_ids", "blocked_task_ids", "selection_idle_reason",
            "manual_hold", "manual_cancellation", "capacity_quarantine", "protected_incident", "dependency_status",
            "claim_task_cid", "claim_attempt", "proof_task_cid", "proof_stale", "stale_proof")
    interview_state = None
    if phase in {"waiting_for_user", "waiting_user", "awaiting_user"}:
        interview_state = "awaiting_user"
    elif phase == "manual_hold" or native_state.get("manual_hold") or (not active and board.get("manual_hold_task_ids")):
        interview_state = "manual_hold"
    elif phase == "paused":
        interview_state = "paused"
    elif phase in {"cancelled", "canceled"} or native_state.get("manual_cancellation"):
        interview_state = "cancelled"
    heartbeat_fresh = heartbeat_age is not None and heartbeat_age <= 120
    identity_ok = worker_liveness == "alive" and health not in {"identity_mismatch", "heartbeat_identity_mismatch", "state_error"}
    activity_ok = (not active) or bool(provider_progress or validation_evidence
        or (provider_evidence and provider_evidence.get("provider_terminal_observed"))) or not (
        attempt_age is not None and attempt_age > STALL_SECONDS
    )
    healthy = bool(identity_ok and heartbeat_fresh and activity_ok and health in {
        "active", "post_provider", "running", "maintenance", "waiting_for_user", "selected", "complete",
    })
    return {"status": health, "healthy": healthy, "owned_process_alive": owned,
            "worker_liveness": worker_liveness,
            "application_interview_state": interview_state,
            "pid": identity.get("pid"), "state_dir": str(state_dir),
            "worktree_root": str(selected_root) if selected_root is not None else None,
            "worktree_root_binding": root_binding, "worktree_root_error": worktree_error,
            "provider": "grok_cli", "model": MODEL, "allow_fallback": False,
            "native_heartbeat_age_seconds": heartbeat_age, "observed_activity_age_seconds": progress_age,
            "native_read_errors": {key: value.get("read_error") for key, value in
                                   (("launcher", record), ("state", native_state), ("heartbeat", heartbeat), ("strategy", strategy))
                                   if value.get("read_error")},
            "native_state": {key: native_state[key] for key in keys if key in native_state},
            "native_state_source": state_source,
            "container_shutdown_verified": shutdown_verified,
            "container_shutdown": {key: shutdown[key] for key in ("status", "quiesced", "reason") if key in shutdown},
            "native_heartbeat": {key: heartbeat[key] for key in ("status", "updated_at", "supervisor_pid", "daemon_pid", "supervisor_pid_alive", "daemon_pid_alive", "restart_count", "last_recycle_reason", "last_exit_code", "worker_phase", "worker_phase_age_seconds", "last_agentic_maintenance_phase", "supervisor_maintenance") if key in heartbeat},
            "native_strategy": {key: strategy[key] for key in ("blocked_tasks", "deprioritized_tasks", "focus_tracks") if key in strategy},
            "board": board, "events_tail": _tail(events_path), "supervisor_events_tail": _tail(supervisor_events),
            "launcher_log_tail": _tail(state_dir / "launcher.log"),
            "claim_progress_verified": claim_verified,
            "runner_progress_verified": bool(claim_verified and heartbeat_fresh and worker_liveness == "alive"),
            "provider_execution_verified": bool(owned and provider_evidence),
            "provider_progress_verified": bool(owned and provider_progress),
            "provider_execution_evidence": provider_evidence,
            "validation_activity_verified": bool(owned and validation_evidence),
            "validation_activity_evidence": validation_evidence,
            "progress_verified": bool(owned and provider_progress),
            "completion_authority": False}


def _refusal(reason: str, observed: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    """Recovery refusal keeps counters, evidence and holds exactly as observed."""
    return {"recovery": "blocked", "eligible": False, "reconciled": False, "reason": reason,
            "status": observed.get("status"), "healthy": observed.get("healthy"),
            "worker_liveness": observed.get("worker_liveness"),
            "application_interview_state": observed.get("application_interview_state"),
            "diagnostics": extra.get("diagnostics") or [reason],
            "observed_attempts": (observed.get("native_state") or {}).get("implementation_attempts"),
            "observed_attempts_by_cid": (observed.get("native_state") or {}).get("implementation_attempts_by_cid"),
            "selection_performed": False, "paid_dispatch": False, "attempt_refunded": False,
            "completion_authority": False, "counters_preserved": True, "progress_preserved": True,
            "manual_holds_preserved": True, "provider_execution_evidence": observed.get("provider_execution_evidence"),
            "validation_activity_evidence": observed.get("validation_activity_evidence"),
            **{key: value for key, value in extra.items() if key != "diagnostics"}}


def _arm_cooldown(state_dir: Path, reason: str, observed: Mapping[str, Any], *, now: float, scope: str,
                  diagnostics: list[Any] | None = None) -> dict[str, Any]:
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.supervisor_runtime import RestartPolicy
    path = state_dir / _COOLDOWN_NAME
    previous = _read_json(path)
    if previous.get("until") and float(previous.get("until") or 0) > now and previous.get("reason") == reason:
        return _refusal(reason, observed, recovery="cooldown", cooldown_until=previous["until"],
                        cooldown_seconds=previous.get("cooldown_seconds"), cooldown_scope=scope,
                        diagnostics=list(previous.get("diagnostics") or [reason]),
                        spinning_prevented=True)
    policy = RestartPolicy()
    try:
        object.__setattr__(policy, "_consecutive_failures", int(previous.get("attempts") or 0))
    except (TypeError, ValueError):
        object.__setattr__(policy, "_consecutive_failures", 0)
    delay = min(policy.delay_for_status("blocked"), policy.max_backoff_seconds)
    diagnostics = [reason, f"cooldown_seconds={delay}", f"scope={scope}",
                   "progress_and_attempt_counters_retained", *(diagnostics or [])]
    payload = {"reason": reason, "scope": scope, "attempts": int(policy._consecutive_failures),
               "cooldown_seconds": delay, "until": now + delay, "diagnostics": diagnostics,
               "progress_preserved": True, "attempt_refunded": False, "completion_authority": False}
    _atomic_json(path, payload)
    return _refusal(reason, observed, recovery="cooldown", cooldown_until=payload["until"],
                    cooldown_seconds=delay, cooldown_scope=scope, diagnostics=diagnostics,
                    spinning_prevented=True)


def _fence_owned_tree(record: Mapping[str, Any]) -> dict[str, Any]:
    """Observe closure only; a recovery request never signals a live parent."""
    identity = record.get("identity")
    if not isinstance(identity, dict) or _owner_liveness(identity) != "dead":
        return {"fenced": False, "signalled": False, "remaining_pids": [], "reason": "launcher_not_dead"}
    return {"fenced": True, "signalled": False, "remaining_pids": []}


def _recovery_config(repo_root: Path, state_dir: Path, record: Mapping[str, Any]):
    """Derive the native paths/options from the first-party compiler only."""
    supervisor, _ = _native_modules(repo_root)
    selected_root, _ = recorded_worktree_root(record, state_dir)
    args = native_argv(Path(record["board_path"]), state_dir, record["merge_target"], worktree_root=selected_root)
    return supervisor.supervisor_config_from_args(supervisor.parse_args(args), repo_root=repo_root)


def _open_recovery_daemon(repo_root: Path, state_dir: Path, record: Mapping[str, Any], *, merge_queue=None):
    """Native quiesced reconciliation has no implementation/selection authority."""
    _, native = _native_modules(repo_root)
    config = _recovery_config(repo_root, state_dir, record)
    return native.PortalImplementationDaemon(
        todo_path=config.todo_path, state_path=config.state_path, strategy_path=config.strategy_path,
        events_path=state_dir / f"{STATE_PREFIX}_events.jsonl", repo_root=repo_root,
        task_header_prefix=config.task_prefix, board_namespace=config.board_namespace, implement=False,
        implementation_command=config.implementation_command,
        implementation_timeout=config.implementation_timeout, max_task_attempts=config.max_task_attempts,
        use_ephemeral_worktree=False, worktree_root=config.worktree_root,
        merge_target_branch=config.merge_target_branch, merge_queue_dir=config.merge_queue_dir,
        merge_queue=merge_queue, worktree_submodule_paths=config.worktree_submodule_paths,
        implementation_protected_paths=config.implementation_protected_paths,
        objective_path=config.objective_path, objective_bundle_dir=config.objective_bundle_dir,
        generated_status_paths=config.generated_dirty_repair_paths,
        llm_merge_resolver_command=config.llm_merge_resolver_command,
        llm_merge_resolver_timeout_seconds=config.llm_merge_resolver_timeout_seconds,
        task_shard_count=config.task_shard_count, task_shard_index=config.task_shard_index,
        strict_task_sharding=config.strict_task_sharding,
    )


@contextmanager
def _recovery_checkout_lease(repo_root: Path):
    # Exclude merges/checkout mutation, while leaving the protected-path
    # reconciler free to acquire and revalidate its own crash-fence lease.
    from ipfs_accelerate_py.agent_supervisor.merge import checkout_lock as locks
    path = locks.board_scoped_checkout_mutation_lock_path(repo_root, "complaint-intake-improvement")
    metadata = locks.checkout_lock_metadata(kind="merge", repo_root=repo_root,
        owner_script="", extra={"lease_id": secrets.token_hex(16), "operation": "quiesced_stalled_worker_reconciliation"})
    lease, _, _, _ = locks.acquire_checkout_mutation_lease(path, metadata, owner_active=lambda _: True)
    if lease is None:
        raise BlockingIOError("native checkout mutation owner is present")
    try:
        yield
    finally:
        if not locks.release_checkout_mutation_lease(lease, require_exact_metadata=True):
            raise RuntimeError("native recovery checkout lease changed; retained")


def _recovery_preimage(repo_root: Path, state_dir: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    from .improvement_recovery import _owned_bytes
    files = [state_dir / name for name in ("launcher.json", "container_shutdown.json",
        f"{STATE_PREFIX}_supervisor_status.json", f"{STATE_PREFIX}_task_state.json",
        f"{STATE_PREFIX}_strategy.json", f"{STATE_PREFIX}_events.jsonl")]
    files += [Path(record["board_path"]), Path(record["spec_path"])]
    result = {}
    for path in files:
        # Current native state is a control-plane row; a JSON mirror is optional.
        if path.name == f"{STATE_PREFIX}_task_state.json" and not os.path.lexists(path):
            result[str(path)] = None
            continue
        if path.resolve(strict=True) != path:
            raise ValueError("recovery evidence path is aliased")
        raw = _owned_bytes(path, MAX_EVENT_HISTORY_BYTES if path == state_dir / f"{STATE_PREFIX}_events.jsonl" else 32 * 1024 * 1024, legacy_group_write=True)
        info = path.lstat()
        result[str(path)] = (info.st_dev, info.st_ino, info.st_mode, hashlib.sha256(raw).hexdigest())
    payload, source = _read_native_state(repo_root, state_dir / f"{STATE_PREFIX}_task_state.json")
    if payload.get("read_error") or source.get("source") == "unavailable":
        raise ValueError("native recovery state observation unavailable")
    result["native_payload"] = payload
    result["native_source"] = source
    authority = source.get("authority_path")
    if authority:
        path = Path(authority)
        if not path.is_absolute() or path.resolve(strict=True) != path or not path.is_relative_to(state_dir):
            raise ValueError("native state authority is outside this epoch")
        raw = _owned_bytes(path, 128 * 1024 * 1024, legacy_group_write=True)
        info = path.lstat()
        result["native_authority"] = (str(path), info.st_dev, info.st_ino, info.st_mode,
                                      hashlib.sha256(raw).hexdigest())
    return result


def _claim_proof_conflict(native_state: Mapping[str, Any]) -> str | None:
    claim_cid = native_state.get("claim_task_cid") or native_state.get("proof_task_cid")
    active_cid = native_state.get("active_task_cid")
    if claim_cid and active_cid and claim_cid != active_cid:
        return "stale_cid"
    claim_attempt = native_state.get("claim_attempt")
    active_attempt = native_state.get("active_attempt")
    if claim_attempt not in (None, "") and active_attempt not in (None, "", 0) and claim_attempt != active_attempt:
        return "stale_attempt_proof"
    if native_state.get("proof_stale") or native_state.get("stale_proof"):
        return "stale_proof"
    return None


def _recover_stalled_worker(repo_root: Path, spec_path: Path, state_dir: Path, *, now: float | None = None) -> dict[str, Any]:
    """Fence a proven-dead ordinary attempt and reconcile it through native APIs.

    A live PID, stale heartbeat, or missing birth is not permission to refund an
    attempt, reset a cap, release quarantine, fabricate an interview answer, or
    dispatch another paid provider call. Lock contention and a temporarily
    unavailable dependency wait on a capped cooldown.
    """
    observed = status(repo_root, spec_path, state_dir)
    moment = time.time() if now is None else now
    native_state = observed.get("native_state") if isinstance(observed.get("native_state"), dict) else {}
    errors = observed.get("native_read_errors") or {}
    if errors:
        if any(str(value) in {"native_state_read_timeout", "BlockingIOError", "TimeoutError"} for value in errors.values()):
            return _arm_cooldown(state_dir, "lock_contention", observed, now=moment, scope="runner")
        return _refusal("observation_error", observed, diagnostics=[f"{key}:{value}" for key, value in errors.items()])
    interview = observed.get("application_interview_state")
    if interview:
        return _refusal(f"interview_or_manual_{interview}", observed)
    if native_state.get("manual_hold") or native_state.get("manual_cancellation"):
        return _refusal("manual_hold", observed)
    if native_state.get("capacity_quarantine") or str(native_state.get("active_phase") or "").lower() == "capacity_quarantine":
        return _refusal("capacity_quarantine", observed)
    if native_state.get("protected_incident") or str(native_state.get("active_phase") or "").lower() == "protected_incident":
        return _refusal("protected_incident", observed)
    conflict = _claim_proof_conflict(native_state)
    if conflict:
        return _refusal(conflict, observed)
    dependency = str(native_state.get("dependency_status") or "").lower()
    if dependency in {"unavailable", "temporary_unavailable", "degraded"}:
        return _arm_cooldown(state_dir, "dependency_unavailable", observed, now=moment, scope="runner")
    liveness = _owner_liveness(native_state.get("owner_process_birth"))
    if liveness == "missing":
        liveness = observed.get("worker_liveness") or "missing"
    phase = str(native_state.get("active_phase") or "").lower()
    active = bool(native_state.get("implementation_in_progress"))
    if liveness in {"alive", "pid_reuse", "unknown"}:
        if liveness != "alive":
            return _refusal(liveness, observed)
        if observed.get("status") in {"stalled", "no_progress", "daemon_failed"}:
            scope = "validation" if phase.startswith("valid") else "provider" if active else "runner"
            if phase.startswith("complet"):
                scope = "completion"
            reason = "validation_stall" if scope == "validation" else "silent_provider" if scope == "provider" else "log_or_heartbeat_stall"
            return _arm_cooldown(state_dir, reason, observed, now=moment, scope=scope)
        return _refusal("worker_alive", observed)
    record = _read_json(state_dir / "launcher.json")
    if liveness != "dead" and not (liveness in {"absent", "missing"}
            and not owns_process(record) and _full_launch_record(record)):
        return _refusal("unknown_owner", observed)
    try:
        # Only a stopped, full campaign can enter the operator seam. A dead
        # worker never grants authority over its still-live native supervisor.
        from .improvement_shutdown import _context, _parent_closed
        if not _campaign_tuple_matches(record, repo_root, spec_path, state_dir):
            return _refusal("campaign_binding_unverified", observed)
        context = _context(state_dir, record)
        if context is None:
            return _refusal("campaign_binding_unverified", observed)
        _parent_closed(state_dir, record, context, False)
        if _owner_liveness(record.get("identity")) != "dead":
            return _refusal("launcher_not_dead", observed)
        preimage = _recovery_preimage(repo_root, state_dir, record)
        with ExitStack() as stack:
            for name in ("recovery.lock", "launcher.lock", "runner.lock"):
                stack.enter_context(_lock(state_dir, name, blocking=False))
            if _recovery_preimage(repo_root, state_dir, record) != preimage:
                return _refusal("recovery_preimage_changed", observed)
            _parent_closed(state_dir, record, context, False)
            stack.enter_context(_recovery_checkout_lease(repo_root))
            # Even preparing an existing queue can touch its schema/import
            # projection. Prove current process/container closure first.
            _parent_closed(state_dir, record, context, False)
            fence = _fence_owned_tree(record)
            containers = _read_json(state_dir / "container_shutdown.json")
            selected_root, _ = recorded_worktree_root(record, state_dir)
            if (not fence["fenced"] or not _shutdown_verified(record, containers, repo_root, state_dir)
                    or not _observe_campaign_containers(repo_root, state_dir, selected_root, record, containers)):
                return _refusal("container_or_process_closure_unverified", observed)
            if _recovery_preimage(repo_root, state_dir, record) != preimage:
                return _refusal("recovery_preimage_changed", observed)
            from ipfs_accelerate_py.agent_supervisor.merge.merge_queue import (
                MergeQueue, hold_merge_queue_settlement, read_merge_queue_settlement,
            )
            from ipfs_accelerate_py.agent_supervisor.merge.checkout_lock import checkout_repository_id
            queue_args = {"target_repository_id": checkout_repository_id(repo_root),
                          "target_branch": record["merge_target"], "lock_timeout_seconds": 0.01}
            queue_before = read_merge_queue_settlement(state_dir / "merge-queue", **queue_args)
            if not queue_before.get("settled"):
                return _refusal("merge_queue_unsettled", observed)
            # MergeQueue opens its own store during construction. Construct the
            # genuine existing queue before retaining its writer guard, then
            # inject that same instance into the non-implementing reconciler.
            _parent_closed(state_dir, record, context, False)
            queue_instance = MergeQueue(state_dir / "merge-queue")
            if read_merge_queue_settlement(state_dir / "merge-queue", **queue_args) != queue_before:
                return _refusal("merge_queue_changed_during_preparation", observed)
            queue = stack.enter_context(hold_merge_queue_settlement(state_dir / "merge-queue",
                target_repository_id=checkout_repository_id(repo_root), target_branch=record["merge_target"],
                lock_timeout_seconds=0.01))
            if not queue.get("settled"):
                return _refusal("merge_queue_unsettled", observed)
            _parent_closed(state_dir, record, context, False)
            fence = _fence_owned_tree(record)
            containers = _read_json(state_dir / "container_shutdown.json")
            selected_root, _ = recorded_worktree_root(record, state_dir)
            if (not fence["fenced"] or not _shutdown_verified(record, containers, repo_root, state_dir)
                    or not _observe_campaign_containers(repo_root, state_dir, selected_root, record, containers)):
                return _refusal("container_or_process_closure_unverified", observed)
            if _recovery_preimage(repo_root, state_dir, record) != preimage:
                return _refusal("recovery_preimage_changed", observed)
            fresh = status(repo_root, spec_path, state_dir)
            if (fresh.get("native_state") != observed.get("native_state")
                    or fresh.get("application_interview_state") or fresh.get("native_read_errors")
                    or _owner_liveness(fresh.get("native_state", {}).get("owner_process_birth")) not in {"dead", "missing"}):
                return _refusal("recovery_observation_changed", fresh)
            if _recovery_preimage(repo_root, state_dir, record) != preimage:
                return _refusal("recovery_preimage_changed", observed)
            _parent_closed(state_dir, record, context, False)
            daemon = _open_recovery_daemon(repo_root, state_dir, record, merge_queue=queue_instance)
            attempt_result = daemon.reconcile_quiesced_active_attempt()
            claim_result = None
            blocked = bool(attempt_result.get("blocked"))
            reason = str(attempt_result.get("reason") or "")
            terminal_claim_ok = (not blocked) or reason == "task_claim_reconciliation_blocked"
            unsafe = reason in {
                "implementation_worker_still_active", "implementation_lock_owner_still_active",
                "protected_path_reconciliation_blocked", "worktree_lifecycle_reconciliation_blocked",
                "implementation_lock_malformed",
            }
            if terminal_claim_ok and not unsafe:
                claim_result = daemon.reconcile_quiesced_implementation_task_claim()
            after_state, _ = _read_native_state(repo_root, state_dir / f"{STATE_PREFIX}_task_state.json")
            count_keys = ("implementation_attempts", "implementation_attempts_by_cid")
            before_state = preimage["native_payload"]
            if (after_state.get("read_error") or any(after_state.get(key) != before_state.get(key) for key in count_keys)
                    or after_state.get("completed_task_ids") != before_state.get("completed_task_ids")):
                return _refusal("native_accounting_or_completion_changed", observed,
                    counters_preserved=False, progress_preserved=False,
                    attempt_refunded=None, diagnostics=["native invariant observation changed; no rollback attempted"],
                    attempt_reconciliation=attempt_result, claim_reconciliation=claim_result)
            reconciled = bool(attempt_result.get("reconciled")) or (
                isinstance(claim_result, dict) and bool(claim_result.get("reconciled")) and not claim_result.get("blocked")
            )
            if not reconciled:
                return _refusal(reason or "native_reconciliation_blocked", observed,
                                diagnostics=[reason or "native_reconciliation_blocked"],
                                attempt_reconciliation=attempt_result, claim_reconciliation=claim_result,
                                fence=fence, container_shutdown=containers)
            return {"recovery": "reconciled", "eligible": True, "reconciled": True,
                    "reason": reason or "quiesced_active_attempt_reconciled", "status": observed.get("status"),
                    "healthy": False, "worker_liveness": "dead",
                    "application_interview_state": None,
                    "diagnostics": [reason or "quiesced_active_attempt_reconciled"],
                    "attempt_reconciliation": attempt_result, "claim_reconciliation": claim_result,
                    "fence": fence, "container_shutdown": containers,
                    "selection_performed": False, "paid_dispatch": False, "attempt_refunded": False,
                    "completion_authority": False, "counters_preserved": True, "progress_preserved": True,
                    "manual_holds_preserved": True, "provider_execution_evidence": observed.get("provider_execution_evidence"),
                    "validation_activity_evidence": observed.get("validation_activity_evidence")}
    except BlockingIOError:
        return _arm_cooldown(state_dir, "lock_contention", observed, now=moment, scope="runner")
    except (OSError, ValueError, RuntimeError) as exc:
        return _arm_cooldown(state_dir, "dependency_unavailable", observed, now=moment, scope="runner",
                             diagnostics=[type(exc).__name__, str(exc)[:500]])


def recover_stalled_worker(repo_root: Path, spec_path: Path, state_dir: Path, *, now: float | None = None) -> dict[str, Any]:
    """Explicit stopped-only operator seam; the native watchdog owns live work."""
    previous = dict(os.environ)
    try:
        effective = campaign_environment(repo_root, state_dir=state_dir)
        os.environ.clear()
        os.environ.update(effective)
        return _recover_stalled_worker(repo_root, spec_path, state_dir, now=now)
    finally:
        os.environ.clear()
        os.environ.update(previous)


def _signal_birth(identity: Mapping[str, Any], signum: int) -> bool:
    current = process_identity(identity.get("pid"))
    if not current or any(current.get(key) != identity.get(key) for key in ("pid", "start_ticks", "boot_id")):
        return False
    try:
        if hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"):
            fd = os.pidfd_open(current["pid"])
            try:
                again = process_identity(current["pid"])
                if not again or again["start_ticks"] != identity["start_ticks"]:
                    return False
                signal.pidfd_send_signal(fd, signum)
            finally:
                os.close(fd)
        else:
            os.kill(current["pid"], signum)
        return True
    except ProcessLookupError:
        return False


def _descendants(root: Mapping[str, Any]) -> list[dict[str, Any]]:
    current = process_identity(root.get("pid"))
    if not current or any(current.get(key) != root.get(key) for key in ("start_ticks", "boot_id")):
        return []
    identities = [item for path in Path("/proc").iterdir() if path.name.isdigit()
                  if (item := process_identity(int(path.name))) is not None]
    owned = {root["pid"]}
    while True:
        additions = {item["pid"] for item in identities if item["ppid"] in owned}
        if additions <= owned:
            break
        owned.update(additions)
    current = process_identity(root.get("pid"))
    if not current or any(current.get(key) != root.get(key) for key in ("start_ticks", "boot_id")):
        return []
    return [item for item in identities if item["pid"] in owned and item["pid"] != root["pid"]]


def stop(state_dir: Path, *, timeout: float = 15.0,
         retained_native_child_proof: Mapping[str, Any] | None = None) -> dict[str, Any]:
    with _lock(state_dir):
        path = state_dir / "launcher.json"
        record = _read_json(path)
        from .improvement_shutdown import close_campaign_containers
        try:
            recorded_worktree_root(record, state_dir)
        except (OSError, ValueError, TypeError) as error:
            return {"status": "stop_incomplete", "signalled": False, "reason": str(error), "manual_holds_preserved": True}
        if not owns_process(record):
            containers = close_campaign_containers(state_dir, record, retained_native_child_proof=retained_native_child_proof)
            if not containers["applicable"]:
                return {"status": "not_owned_or_stopped", "signalled": False}
            if containers["quiesced"]:
                record.update(status="stopped", stopped_at=time.time())
                _atomic_json(path, record)
            return {"status": containers["status"], "signalled": False,
                    "container_shutdown": containers, "manual_holds_preserved": True}
        if retained_native_child_proof is not None:
            return {"status": "stop_incomplete", "signalled": False,
                    "reason": "retained native observation cannot authorize live fencing", "manual_holds_preserved": True}
        identity = record["identity"]
        children = _descendants(identity)
        _signal_birth(identity, signal.SIGTERM)
        deadline = time.monotonic() + max(0.0, min(timeout, 30.0))
        while owns_process(record) and time.monotonic() < deadline:
            time.sleep(0.1)
        captured = {child["pid"]: child for child in children}
        # Include children born during graceful native cleanup only through
        # parents whose original process birth still matches our receipt.
        for parent in [identity, *children]:
            for child in _descendants(parent):
                captured.setdefault(child["pid"], child)
        children = list(captured.values())
        # Native run_forever first fences its managed daemon. Only force the
        # birth-bound descendants captured from our actual process tree.
        for child in reversed(children):
            _signal_birth(child, signal.SIGTERM)
        if owns_process(record):
            _signal_birth(identity, signal.SIGKILL)
        for child in reversed(children):
            _signal_birth(child, signal.SIGKILL)
        deadline = time.monotonic() + 1.0
        def birth_alive(item):
            current = process_identity(item["pid"])
            return bool(current and current["start_ticks"] == item["start_ticks"]
                        and current["boot_id"] == item["boot_id"])
        while any(birth_alive(item) for item in [identity, *children]) and time.monotonic() < deadline:
            time.sleep(0.05)
        remaining = [item["pid"] for item in [identity, *children] if birth_alive(item)]
        containers = close_campaign_containers(state_dir, record, parent_quiesced=not remaining)
        outcome = "stop_incomplete" if remaining or (containers["applicable"] and not containers["quiesced"]) else "stopped"
        record.update(status=outcome, stopped_at=time.time())
        _atomic_json(path, record)
        return {"status": outcome, "signalled": True, "pid": identity["pid"], "remaining_pids": remaining,
                "container_shutdown": containers, "manual_holds_preserved": True}


def _read_validation_watchdog_authority(path: Path) -> dict[str, Any] | None:
    """Read Native's ordinary lease mode with the existing legacy custody rule."""
    from .improvement_recovery import _owned_bytes

    try:
        if path.resolve(strict=True) != path:
            return None
        value = json.loads(_owned_bytes(path, 65536, legacy_group_write=True))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


def _owned_validation_window(supervisor, state, *, now_ts: float) -> bool:
    """Observe a fixed validation deadline without refreshing any task clock.

    The provider deadline starts before the proposal is returned. Validation
    has its own existing command timeout. Only the current Native dispatch
    owner, its matching task claims and its live test child can use that window.
    """
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native

    if (state.active_phase != "validating" or not state.implementation_in_progress
            or not state.active_task_id or not state.active_task_key or not state.active_task_cid
            or state.last_implementation_task_id != state.active_task_id
            or type(state.active_attempt) is not int or not 1 <= state.active_attempt <= 3):
        return False
    try:
        started = native.parse_timestamp(state.active_phase_started_at)
        provider_started = native.parse_timestamp(state.last_implementation_started_at)
        finished = native.parse_timestamp(state.last_implementation_finished_at)
        timeout = min(float(TIMEOUT_SECONDS), supervisor._implementation_watchdog_timeout_seconds())
        if (started is None or provider_started is None or started < provider_started
                or finished is not None and finished >= provider_started
                or not 0 <= now_ts - started.timestamp() <= timeout):
            return False
        worktree_root = Path(supervisor.config.worktree_root).resolve(strict=True)
        workspace = Path(state.active_worktree_path)
        if (not workspace.is_absolute() or workspace.resolve(strict=True) != workspace
                or workspace == worktree_root or not workspace.is_relative_to(worktree_root)):
            return False
        lease = _read_validation_watchdog_authority(supervisor._implementation_maintenance_lock_path())
        claim = _read_validation_watchdog_authority(supervisor._task_dispatch_claim_path(state))
        identity = native.load_supervised_child_identity(supervisor._managed_daemon_identity_path())
        if lease is None or claim is None or identity is None:
            return False
        birth = native.ProcessBirthIdentity.from_dict(claim.get("owner_process_birth"))
        expected = {"task_id": state.active_task_id,
                    "canonical_task_key": state.active_task_key,
                    "canonical_task_cid": state.active_task_cid,
                    "attempt": state.active_attempt}
        if (dict(identity.owner_scope) != supervisor._managed_daemon_owner_scope()
                or tuple(identity.command) != tuple(supervisor._build_daemon_command())
                or birth != identity.process_birth
                or native.read_process_birth(birth.pid) != birth
                or native.read_process_command_argv(birth.pid) != identity.command
                or native.supervised_child_identity_liveness(identity) is not native.OwnerLiveness.ALIVE
                or lease.get("kind") != "implementation"
                or lease.get("lease_role") == "supervisor_maintenance"
                or claim.get("kind") != native.IMPLEMENTATION_TASK_CLAIM_LOCK_KIND
                or claim.get("lease_role") != native.IMPLEMENTATION_DISPATCH_INTENT_LEASE_ROLE
                or not lease.get("lease_id") or not claim.get("lease_id")
                or int(lease.get("pid") or 0) != birth.pid
                or int(claim.get("pid") or 0) != birth.pid
                or any(lease.get(key) != value or claim.get(key) != value for key, value in expected.items())
                or Path(str(lease.get("repo_root") or "")).resolve() != supervisor.config.repo_root.resolve()
                or Path(str(lease.get("state_dir") or "")).resolve() != supervisor.config.state_dir.resolve()
                or Path(str(claim.get("state_dir") or "")).resolve() != supervisor.config.state_dir.resolve()
                or Path(str(claim.get("state_path") or "")).resolve() != supervisor.config.state_path.resolve()
                or not native.checkout_lock_repository_matches(claim, supervisor.config.repo_root)
                or claim.get("dispatch_authority_cid") != native.PortalImplementationDaemon._implementation_dispatch_authority_cid(claim)):
            return False
        return bool(supervisor._active_validation_subprocess_exists())
    except (OSError, TypeError, ValueError, AttributeError, KeyError):
        return False


def _preserve_uncommitted_reconciliation_candidates(supervisor):
    """Let Native preserve pending orphan edits before its merged-base shortcut.

    An interrupted proposal can still have the already-integrated baseline as
    HEAD. Native's ordinary reconciliation skips that HEAD before checking its
    uncommitted content. Only this owned campaign, under Native's maintenance
    lease, may ask its existing rescue helper to preserve those edits first.
    """
    config = supervisor.config
    held = getattr(supervisor, "_held_implementation_maintenance_lease", None)
    if (not getattr(config, "worktree_reconciliation_enabled", True)
            or not isinstance(held, Mapping) or held.get("lease_role") != "supervisor_maintenance"
            or held.get("pid") != os.getpid()):
        return []
    launch = _read_json(config.state_dir / "launcher.json")
    if (launch.get("status") not in {"starting", "running"}
            or launch.get("repo_root") != str(config.repo_root.resolve())
            or launch.get("state_dir") != str(config.state_dir)
            or launch.get("identity", {}).get("pid") != os.getpid()
            or not owns_process(launch)):
        return []
    root, binding = recorded_worktree_root(launch, config.state_dir)
    if binding is None or config.worktree_root != root or root.resolve(strict=True) != root:
        raise RuntimeError("owned reconciliation worktree domain is unavailable")
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import parse_task_text
    tasks = parse_task_text(config.todo_path.read_text(), path=config.todo_path, task_header_prefix=config.task_prefix)
    held_tasks = set(_board_summary(tasks)["manual_hold_task_ids"])
    pending = {task.task_id for task in tasks if task.status == "todo" and task.task_id not in held_tasks}
    records = supervisor._git_worktree_records(config.repo_root)
    if len(records) > 256:
        raise RuntimeError("owned reconciliation worktree population exceeds its bound")
    owners = supervisor._shared_active_worktree_owners(root)
    commands = supervisor._list_process_commands()
    target = config.merge_target_branch or supervisor._git_current_branch(config.repo_root) or "HEAD"
    preserved = []
    for record in records:
        path = Path(str(record.get("worktree") or ""))
        branch = str(record.get("branch") or "").removeprefix("refs/heads/")
        head = str(record.get("HEAD") or "")
        if (not path.is_absolute() or not path.is_relative_to(root) or path == root
                or not path.exists() or path.resolve(strict=True) != path or not head
                or not supervisor._worktree_branch_is_reconcilable(branch)
                or supervisor._worktree_branch_source_task_id(branch, known_task_ids=tuple(pending)) not in pending
                or not supervisor._git_ref_is_ancestor(config.repo_root, head, target)):
            continue
        dirty = supervisor._git_status_short(path)
        # An unused prepared checkout can differ only in SDK gitlinks. That
        # bootstrap state is not an uncommitted complaint-generator proposal.
        root_edits = [line for line in dirty if line[3:] not in _PRIVATE_DEPENDENCY_ROOTS]
        if (not root_edits or supervisor._active_worktree_skip_detail(path, owners) is not None
                or any(str(path) in command for command in commands)):
            continue
        result = supervisor._rescue_dirty_worktree(path, branch=branch, head=head,
            target_ref=target, status_lines=dirty, reason="reconciliation_uncommitted_integrated_base")
        if result.get("preserved") is not True:
            raise RuntimeError("uncommitted reconciliation candidate preservation is required")
        preserved.append(result)
    return preserved


def _validation_aware_supervisor_class(native_class):
    class ValidationAwareSupervisor(native_class):
        @staticmethod
        def _read_watchdog_authority(path):
            # Native uses this reader for setup and maintenance admission as
            # well as validation. Ordinary Native leases use its legacy mode.
            return _read_validation_watchdog_authority(path)

        def _run_forever_loop(self):
            self._complaint_startup_preflight_pending = True
            return super()._run_forever_loop()

        def run_once(self, *, include_refill=True):
            result = super().run_once(include_refill=include_refill)
            if getattr(self, "_complaint_startup_preflight_pending", False):
                if result.get("maintenance_blocked") is True:
                    raise RuntimeError("Native startup preflight blocked: " + str(result.get("reason") or "maintenance unavailable"))
                self._complaint_startup_preflight_pending = False
            return result

        def _implementation_attempt_is_active(self, state, *, now_ts):
            return (super()._implementation_attempt_is_active(state, now_ts=now_ts)
                    or _owned_validation_window(self, state, now_ts=now_ts))

        def _build_worktree_reconciliation_daemon(self):
            # Native owns orphan discovery, claims, validation, merge and the
            # completion callback. Recovery uses the same measured gate as a
            # newly generated proposal and dispatches no replacement provider.
            daemon = super()._build_worktree_reconciliation_daemon()
            from .improvement_plan import load_spec
            from ipfs_accelerate_py.agent_supervisor.validation.validation_scheduler import ValidationScheduler
            native_scheduler = daemon.validation_scheduler
            if isinstance(native_scheduler, ValidationScheduler):
                workers = getattr(self.config, "validation_max_workers", None) or 1
                budget = getattr(self.config, "validation_resource_budget", None) or workers
                native_scheduler = ValidationScheduler(
                    cache=native_scheduler.cache, max_workers=workers, resource_budget=budget,
                    default_timeout_seconds=getattr(self.config, "implementation_timeout", TIMEOUT_SECONDS),
                )
            scheduler = EvidenceValidationScheduler(
                native_scheduler, state_dir=self.config.state_dir,
                spec=load_spec(self.config.repo_root / SPEC_RELATIVE),
                defer_readiness=True,
            )
            daemon.validation_scheduler = scheduler
            daemon.proof_workflow = scheduler.bind_task
            return daemon

        def reconcile_backlogged_worktrees(self, *, preacquired_implementation_lock=None):
            preserved = _preserve_uncommitted_reconciliation_candidates(self)
            result = super().reconcile_backlogged_worktrees(
                preacquired_implementation_lock=preacquired_implementation_lock,
            )
            result["owned_uncommitted_candidates_preserved"] = preserved
            unresolved = [candidate for candidate in preserved if not any(
                item.get("path") == candidate.get("path") and item.get("merged") is True
                for item in result.get("processed", ())) ]
            if unresolved:
                raise RuntimeError("preserved candidate requires Native recovery before provider dispatch")
            return result
    return ValidationAwareSupervisor


def _run_native_supervisor(argv, *, repo_root, logger, daemon_script_path):
    """Use Native configuration and run loop with the bounded phase predicate."""
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_supervisor_runner as lifecycle
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon_runner import implementation_state_artifact_paths

    parsed = native.parse_args(list(argv))
    lifecycle.configure_supervisor_logging(parsed)
    config = native.supervisor_config_from_args(
        parsed, repo_root=repo_root,
        daemon_script_path=getattr(parsed, "daemon_script_path", None) or daemon_script_path,
        worktree_submodule_paths=getattr(parsed, "worktree_submodule_path", None),
    )
    paths = implementation_state_artifact_paths(parsed.state_dir, parsed.state_prefix, supervisor_events=True)
    context = lifecycle.ImplementationSupervisorRunContext(
        parsed=parsed, config=config, state_path=config.state_path,
        strategy_path=config.strategy_path, events_path=config.events_path,
        daemon_events_path=paths["daemon_events_path"],
    )
    supervisor = _validation_aware_supervisor_class(native.PortalImplementationSupervisor)(config)
    return lifecycle.run_portal_implementation_supervisor(supervisor, context, logger=logger)


def run_internal(repo_root: Path, spec_path: Path, state_dir: Path, token: str, merge_target: str, *, worktree_root: Path | None = None) -> int:
    # Refuse before creating even a lock file when storage cannot be observed.
    prospective_root, _ = recorded_worktree_root(_read_json(state_dir / "launcher.json"), state_dir)
    _require_resource_capacity(repo_root, state_dir, prospective_root, os.environ, stage="before_owned_startup_lock")
    # Serialize startup against parent receipt publication and future starts.
    with _lock(state_dir):
        record = _read_json(state_dir / "launcher.json")
        if record.get("owner_token") != token or not owns_process(record) or record["identity"]["pid"] != os.getpid():
            raise RuntimeError("internal runner lacks its exact owned launch receipt")
        selected_root, root_binding = recorded_worktree_root(record, state_dir)
        if (root_binding is not None and worktree_root != selected_root) or (root_binding is None and worktree_root is not None):
            raise RuntimeError("internal worktree root differs from its owned launch")
    with _lock(state_dir, "runner.lock", blocking=False):
        os.chdir(repo_root)
        from .improvement_plan import BOARD_RELATIVE, build_improvement_work_plan, load_spec
        spec = load_spec(spec_path)
        if build_improvement_work_plan(spec).plan_id != record.get("plan_id"):
            raise RuntimeError("specification changed after the owned launch was prepared")
        effective = campaign_environment(repo_root, context_exclude=spec["execution_policy"].get("context_exclude"), state_dir=state_dir)
        if not _auth_material_present(effective):
            raise RuntimeError("auth_material_unavailable")
        os.environ.clear()
        os.environ.update(effective)
        _validate_board(repo_root, repo_root / BOARD_RELATIVE, spec)
        privacy = _private_runtime_checks(repo_root, effective)
        if not privacy["ready"]:
            raise RuntimeError(privacy["reason"])
        _require_resource_capacity(repo_root, state_dir, selected_root, effective, stage="before_native_supervisor")
        # Recheck the bound storage directory immediately before native admission.
        if recorded_worktree_root(record, state_dir) != (selected_root, root_binding):
            raise RuntimeError("worktree root changed before native admission")
        # No --once: this is the real native run_forever watchdog and daemon.
        _run_native_supervisor(
            native_argv(repo_root / BOARD_RELATIVE, state_dir, merge_target, worktree_root=selected_root),
            repo_root=repo_root, logger=_LOGGER,
            daemon_script_path=Path(__file__).resolve(),
        )
    return 0


def _evidence_root(state_dir: Path, task_id: str) -> Path:
    if not isinstance(task_id, str) or re.fullmatch(r"CIMP-[A-Za-z0-9_.:-]+", task_id) is None:
        raise ValueError("task evidence requires a stable CIMP identifier")
    return state_dir / "evidence" / task_id


def _task_outputs(task: Mapping[str, Any]) -> list[str]:
    targets = task.get("targets", task.get("outputs"))
    if not isinstance(targets, list) or not targets:
        raise ValueError("task evidence requires declared outputs")
    return [str(item) for item in targets]


def _observed_artifacts(repo_root: Path, observation: Mapping[str, Any]) -> list[dict[str, Any]]:
    from .improvement_plan import _hash_file, _safe_relative

    raw = observation.get("artifacts", [])
    if not isinstance(raw, list):
        return [{"present": False, "sha256": "", "relative_path": ""}]
    resolved = []
    for item in raw:
        relative = item.get("relative_path") if isinstance(item, dict) else item
        path = _safe_relative(repo_root, relative)
        record: dict[str, Any] = {
            "relative_path": relative if isinstance(relative, str) else "",
            "present": bool(path and path.is_file() and path.stat().st_size > 0),
            "sha256": _hash_file(path) if path and path.is_file() and path.stat().st_size > 0 else "",
        }
        if isinstance(item, dict) and "sha256" in item:
            record["claimed_sha256"] = item.get("sha256")
        resolved.append(record)
    return resolved


def gate_task_completion(repo_root: Path, state_dir: Path, task: Mapping[str, Any],
                         observation: Mapping[str, Any], *,
                         facts: Mapping[str, Any] | None = None,
                         model_policy: Mapping[str, Any] | None = None,
                         legal_data_version: str = "",
                         spec: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Persist admission evidence; native callbacks alone publish completion."""

    from .improvement_plan import COMPLETING_LANE, EVIDENCE_LANES, assess_behavioral_evidence, bind_sources, _digest

    if not isinstance(legal_data_version, str):
        raise ValueError("legal_data_version must be a string")
    root = Path(repo_root).resolve()
    state_dir = Path(state_dir).resolve()
    binding = bind_sources(root, _task_outputs(task))
    observed = observation.copy()
    from .improvement_plan import _MeasuredEvidence
    if not isinstance(observation, _MeasuredEvidence):
        observed["artifacts"] = _observed_artifacts(root, observation)
    receipt = assess_behavioral_evidence(task, observed, source_binding=binding, model_policy=model_policy)
    receipt["host_task_contract"] = observation.get("host_task_contract")
    receipt["facts_digest"] = _digest(dict(facts or {}))
    receipt["legal_data_version"] = legal_data_version
    receipt["implementation_digest"] = binding.get("digest") or ""
    if receipt["completion"] and not legal_data_version.strip():
        receipt["admitted"] = False
        receipt["completion"] = False
        receipt["repairable"] = True
        receipt["reason"] = "missing_legal_data_version"
    directory = _evidence_root(state_dir, str(task.get("id") or ""))
    with _lock(state_dir, "evidence.lock"):
        directory.mkdir(parents=True, exist_ok=True)
        lane_name = receipt["lane"] if receipt["lane"] in EVIDENCE_LANES else "rejected"
        _atomic_json(directory / f"{lane_name}.json", receipt)
        if receipt["lane"] == COMPLETING_LANE:
            _atomic_json(directory / "completion.json", receipt)
    if spec is not None:
        receipt["readiness"] = recompute_dependent_readiness(
            root, state_dir, spec, facts=facts, model_policy=model_policy,
            legal_data_version=legal_data_version or None,
        )
    return receipt


def _invalidate(receipt: Mapping[str, Any], reason: str) -> dict[str, Any]:
    updated = dict(receipt)
    updated["admitted"] = False
    updated["completion"] = False
    updated["repairable"] = True
    updated["reason"] = reason
    return updated


def recompute_dependent_readiness(repo_root: Path, state_dir: Path, spec: Mapping[str, Any], *,
                                  facts: Mapping[str, Any] | None = None,
                                  model_policy: Mapping[str, Any] | None = None,
                                  legal_data_version: str | None = None) -> dict[str, Any]:
    """Drop completion that no longer matches source, facts, model policy or legal data.

    Dependents of a task whose evidence was rejected or invalidated are not ready.
    The stored reason stays explicit and repairable.
    """

    from .improvement_plan import READINESS_SCHEMA, bind_sources, canonical_model_policy, _digest

    if not isinstance(spec, dict) or not isinstance(spec.get("tasks"), list):
        raise ValueError("readiness requires the reviewed task list")
    root = Path(repo_root).resolve()
    state_dir = Path(state_dir).resolve()
    policy = canonical_model_policy() if model_policy is None else dict(model_policy)
    facts_digest = None if facts is None else _digest(dict(facts))
    tasks = spec["tasks"]
    identifiers = [item.get("id") for item in tasks]
    if any(not isinstance(item, str) for item in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError("readiness requires unique task identifiers")
    dependencies = {item["id"]: list(item.get("depends_on") or []) for item in tasks}
    for task_id, upstream in dependencies.items():
        if any(item not in dependencies or item == task_id for item in upstream):
            raise ValueError(f"{task_id} has an unknown or self dependency")
    visiting: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ValueError(f"task dependency cycle at {task_id}")
        visiting.add(task_id)
        for upstream in dependencies[task_id]:
            if upstream in visiting and upstream not in order:
                raise ValueError(f"task dependency cycle at {upstream}")
            if upstream not in order:
                visit(upstream)
        visiting.remove(task_id)
        order.append(task_id)

    order: list[str] = []
    for task_id in dependencies:
        if task_id not in order:
            visit(task_id)
    by_id = {item["id"]: item for item in tasks}
    reports: dict[str, Any] = {}
    with _lock(state_dir, "evidence.lock"):
        for task_id in order:
            path = state_dir / "evidence" / task_id / "completion.json"
            receipt = _read_json(path)
            reason = ""
            if not receipt or receipt.get("read_error"):
                complete = False
                reason = "missing_behavioral_evidence"
            else:
                fresh = bind_sources(root, _task_outputs(by_id[task_id]))
                if (receipt.get("implementation_digest") != fresh.get("digest")
                        or not fresh.get("digest")):
                    reason = "stale_source_hash" if fresh.get("digest") or receipt.get("implementation_digest") else "missing_output"
                    if fresh.get("missing") or fresh.get("empty"):
                        reason = "missing_output"
                elif receipt.get("host_measurement") and (receipt["host_measurement"].get("source_after") != _source_freeze(root, _task_outputs(by_id[task_id])) or any(not Path(p).is_file() or hashlib.sha256(Path(p).read_bytes()).hexdigest() != h for p, h in receipt["host_measurement"].get("imported_sources", {}).items())):
                    reason = "stale_source_hash"
                elif not isinstance(receipt.get("host_task_contract"), dict) or receipt["host_task_contract"].get("task") != by_id[task_id]:
                    reason = "task_contract_changed"
                elif receipt.get("model_policy") != policy:
                    reason = "model_policy_changed"
                elif legal_data_version is not None and receipt.get("legal_data_version") != legal_data_version:
                    reason = "legal_data_version_changed"
                elif facts_digest is not None and receipt.get("facts_digest") != facts_digest:
                    reason = "corrected_facts"
                elif receipt.get("completion") is not True or receipt.get("lane") != "local_node_integration":
                    reason = str(receipt.get("reason") or "behavioral_evidence_rejected")
                    complete = False
                else:
                    complete = True
                if reason:
                    complete = False
                    receipt = _invalidate(receipt, reason)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    _atomic_json(path, receipt)
            blocked = [item for item in dependencies[task_id] if not reports[item]["complete"]]
            if blocked:
                complete = False
                reason = "upstream_evidence_not_current"
                if receipt:
                    receipt = _invalidate(receipt, reason)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    _atomic_json(path, receipt)
            reports[task_id] = {
                "complete": complete,
                "ready": not blocked,
                "blocked_by": blocked,
                "reason": "" if complete else reason,
                "repairable": not complete,
            }
        document = {"schema_version": READINESS_SCHEMA, "tasks": reports,
                    "completion_authority": False, "native_scheduling_enforced": False,
                    "enforcement": "admission_advisory_only_no_native_ready_filter",
                    "model_policy": policy, "legal_data_version": legal_data_version,
                    "facts_digest": facts_digest}
        destination = state_dir / "evidence"
        destination.mkdir(parents=True, exist_ok=True)
        _atomic_json(destination / "readiness.json", document)
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare, run and observe the Grok-only complaint improvement campaign.")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "doctor", "start", "status", "recover", "stop", "_run"):
        child = commands.add_parser(command, help=argparse.SUPPRESS if command == "_run" else command)
        child.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
        child.add_argument("--spec", type=Path)
        child.add_argument("--state-dir", type=Path)
        if command in {"doctor", "start", "_run"}:
            child.add_argument("--worktree-root", type=Path, help="Existing dedicated canonical UID-owned0700 external directory; persisted for future starts.")
        if command == "_run":
            child.add_argument("--owner-token", required=True)
            child.add_argument("--merge-target", required=True)
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    spec = (args.spec or root / SPEC_RELATIVE).resolve()
    try:
        if args.state_dir is not None:
            state = args.state_dir.resolve()
        else:
            from .improvement_recovery import resolve_active_epoch
            state = resolve_active_epoch(root, spec, default_state_dir(root))
        os.chdir(root)
        if args.command == "_run":
            return run_internal(root, spec, state, args.owner_token, args.merge_target, worktree_root=args.worktree_root)
        if args.command == "stop":
            result = stop(state)
        else:
            keywords = {"worktree_root": args.worktree_root} if getattr(args, "worktree_root", None) is not None else {}
            result = {"prepare": prepare, "doctor": doctor, "start": start, "status": status, "recover": recover_stalled_worker}[args.command](root, spec, state, **keywords)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2 if result.get("status") in {"not_ready", "board_error", "state_error", "identity_mismatch", "stop_incomplete"} else 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2



def _source_freeze(root: Path, extra=()):
    """Bind tracked implementation inputs, explicit outputs and dependency heads.

    Generated board/status commits do not invalidate unchanged implementation
    inputs. Existing private/untracked user directories are never inventoried.
    """
    from .improvement_plan import _hash_file, _digest, _private_binding_path, _safe_relative
    result = subprocess.run(["git", "--no-optional-locks", "ls-files", "-z", "--stage"],
                            cwd=root, capture_output=True, check=True, timeout=20)
    files, dependencies = {}, {}
    for entry in result.stdout.decode().split("\0"):
        if not entry:
            continue
        metadata, relative = entry.split("\t", 1)
        if _private_binding_path(relative):
            continue
        mode, blob, stage = metadata.split()
        if stage != "0":
            raise ValueError("unmerged_source")
        path = root / relative
        if _safe_relative(root, relative) is None:
            raise ValueError("source_alias_forbidden")
        if mode == "160000":
            if not (path / ".git").exists():
                dependencies[relative] = {"gitlink": blob, "head": "unavailable"}
                continue
            head = subprocess.run(["git", "--no-optional-locks", "-C", str(path), "rev-parse", "HEAD"],
                                  capture_output=True, text=True, timeout=10)
            dependencies[relative] = {"gitlink": blob, "head": head.stdout.strip() if head.returncode == 0 else "unavailable"}
        elif (Path(relative).suffix in {".py", ".sh", ".toml", ".ini", ".cfg", ".json"}
              and not relative.startswith(("docs/", "data/", "output/", "statefiles/", "exports/", ".complaint_workspace/"))):
            if path.is_symlink() or not path.is_file():
                raise ValueError("source_unavailable")
            files[relative] = {"sha256": _hash_file(path), "mode": stat.S_IMODE(path.stat().st_mode), "git_mode": mode}
    for relative in extra:
        if _private_binding_path(relative):
            raise ValueError("private_source_binding_forbidden")
        path = _safe_relative(root, relative)
        if path is None:
            raise ValueError("source_alias_forbidden")
        if path.is_file() and not (root / relative).is_symlink():
            files[relative] = {"sha256": _hash_file(path), "mode": stat.S_IMODE(path.stat().st_mode)}
        elif not path.is_dir():
            raise ValueError("missing_output")
    value = {"files": files, "dependencies": dependencies}
    return {**value, "digest": _digest(value)}


def _pytest_instrument(command, arguments, *, pythonpath=()):
    # Keep the original shell/environment prefix and original selectors. This
    # adapter supports one explicit pytest invocation, not arbitrary scripts.
    pattern = r"(?<![\w-])(?:python(?:3(?:\.\d+)*)?\s+-m\s+pytest|pytest)(?=\s|$)"
    matches = list(re.finditer(pattern, command))
    if len(matches) != 1 or any(flag in command for flag in ("--junit", "--collect-only", "--complaint-evidence-path", " -p no:")):
        raise ValueError("unsupported_behavioral_command")
    end = matches[0].end()
    import shlex
    invocation = command[matches[0].start():end] + " " + shlex.join(arguments)
    if pythonpath:
        # A retained task prefix may export its own PYTHONPATH. Bind the owned
        # plugin roots at the actual invocation, after that prefix, while
        # retaining declared roots and the native sealed Python shell seam.
        owned = os.pathsep.join(map(str, pythonpath))
        invocation = "PYTHONPATH=" + shlex.quote(owned) + ':"${PYTHONPATH-}" ' + invocation
    return command[:matches[0].start()] + invocation + command[end:]


def _read_catalog(path, *, repo_root=None):
    import duckdb
    from .improvement_plan import _hash_file, _private_binding_path
    with duckdb.connect(str(path), read_only=True) as database:
        nodes = database.execute("SELECT nodeid, seal, file_count, completion_authority FROM pytest_ast_seal").fetchall()
        files = database.execute("SELECT path, content_hash FROM pytest_ast_file_hash").fetchall()
    if len(nodes) > 20000 or len(files) > 20000:
        raise ValueError("catalog_population_unbounded")
    hashes = {str(p): str(h) for p, h in files}
    if repo_root is not None:
        for name in hashes:
            relative = Path(name).resolve().relative_to(repo_root) if Path(name).resolve().is_relative_to(repo_root) else None
            if relative is not None and _private_binding_path(relative.as_posix()):
                raise ValueError("private_source_binding_forbidden")
    if len(hashes) != len(files) or any(_hash_file(Path(p)) != h for p, h in hashes.items()):
        raise ValueError("stale_source_hash")
    if (len({n for n, _, _, _ in nodes}) != len(nodes) or
            any(not isinstance(n, str) or not n or not isinstance(seal, str) or re.fullmatch(r"[0-9a-f]{64}", seal) is None
                or type(count) is not int or not 0 < count <= len(hashes) or authority is not False
                for n, seal, count, authority in nodes)):
        raise ValueError("catalog_seal_invalid")
    return [n for n, _, _, _ in nodes], hashes


def _preserve_existing_behavioral_definitions(root: Path, paths, *, trusted_root: Path | None = None):
    """Keep installed test/helper definitions when a task adds behavioral checks.

    The installed operator source supplies the baseline, outside the provider
    checkout. This catches accidental replacement of earlier regression suites;
    an intentional semantic migration requires separately reviewed maintenance.
    Existing classes may gain methods while their earlier methods stay intact.
    """
    import ast
    import copy

    installed = trusted_root if trusted_root is not None else Path(__file__).resolve().parents[2]
    records = []
    def definitions(body, prefix=()):
        rows = {}
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                key = prefix + (node.name,)
                if key in rows:
                    raise ValueError("existing_behavioral_definition_changed")
                rows[key] = ast.dump(node, include_attributes=False)
            elif isinstance(node, ast.ClassDef):
                key = prefix + (node.name,)
                header = copy.deepcopy(node)
                header.body = []
                if key in rows:
                    raise ValueError("existing_behavioral_definition_changed")
                rows[key] = ast.dump(header, include_attributes=False)
                rows.update(definitions(node.body, key))
        return rows
    for relative in sorted(set(map(str, paths))):
        name = Path(relative)
        if not relative.startswith("tests/") or name.suffix != ".py":
            continue
        if name.is_absolute() or ".." in name.parts:
            raise ValueError("existing_behavioral_definition_changed")
        baseline, candidate = installed / name, Path(root) / name
        if not baseline.exists() and not baseline.is_symlink():
            continue
        try:
            for path in (baseline, candidate):
                if path.is_symlink() or path.resolve(strict=True) != path or not path.is_file():
                    raise ValueError("existing_behavioral_definition_changed")
            original_bytes, candidate_bytes = baseline.read_bytes(), candidate.read_bytes()
            original = definitions(ast.parse(original_bytes).body)
            current = definitions(ast.parse(candidate_bytes).body)
        except (OSError, SyntaxError, UnicodeError):
            raise ValueError("existing_behavioral_definition_changed") from None
        if any(current.get(name) != value for name, value in original.items()):
            raise ValueError("existing_behavioral_definition_changed")
        records.append({"path": relative, "trusted_sha256": hashlib.sha256(original_bytes).hexdigest(),
                        "candidate_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
                        "preserved_definition_count": len(original)})
    return records


_PRIVATE_REPLICA_ACCEPTANCE = "tests/test_private_replica_acceptance.py"
_PRIVATE_REPLICA_CAPABILITY_NODE = _PRIVATE_REPLICA_ACCEPTANCE + "::test_replica_api_capability_is_explicit"


def _private_replica_host_file(path, *, limit, exact_mode=None):
    """Read an immutable host/operator file, never a provider success field."""
    import stat
    path = Path(path)
    if not path.is_absolute() or str(path.resolve()) != str(path):
        raise ValueError("private_replica_compatibility_unavailable")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_nlink != 1 or before.st_mode & 0o022
                or (exact_mode is not None and stat.S_IMODE(before.st_mode) != exact_mode)
                or not 0 < before.st_size <= limit):
            raise ValueError("private_replica_compatibility_unavailable")
        chunks, remaining = [], before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65536))
            if not chunk:
                raise ValueError("private_replica_compatibility_unavailable")
            chunks.append(chunk)
            remaining -= len(chunk)
        stable = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_uid,
                               item.st_gid, item.st_nlink, item.st_size,
                               item.st_mtime_ns, item.st_ctime_ns)
        if (os.read(descriptor, 1) or stable(os.fstat(descriptor)) != stable(before)
                or str(path.resolve()) != str(path) or stable(path.stat()) != stable(before)):
            raise ValueError("private_replica_compatibility_unavailable")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _private_replica_kit_qualification(root, evidence_state_dir, task, source, *, campaign_state_dir=None):
    """Require real separately measured Kit compatibility for exact DUR005.

    The 0600 binding is privileged operator configuration outside the provider
    checkout. Its reviewed pure verifier rederives the actual qualification and
    remaps current candidate Kit bytes, retaining measured origins separately.
    This function never runs Kit tests, a provider, a subprocess or Git.
    """
    if task.get("id") != "CIMP-DUR-005":
        return None
    import types
    try:
        if campaign_state_dir is None:
            raise ValueError("private_replica_compatibility_unavailable")
        campaign = Path(campaign_state_dir)
        if (not campaign.is_absolute() or str(campaign.resolve()) != str(campaign)
                or Path(evidence_state_dir) != campaign / "evidence-runs"):
            raise ValueError("private_replica_compatibility_unavailable")
        directory = campaign / "host-acceptance"
        if (directory.is_symlink() or str(directory.resolve()) != str(directory)
                or directory.stat().st_uid != os.getuid()
                or directory.stat().st_mode & 0o077):
            raise ValueError("private_replica_compatibility_unavailable")
        binding_path = directory / "private-replica-kit.json"
        binding_bytes = _private_replica_host_file(binding_path, limit=65536, exact_mode=0o600)
        binding = json.loads(binding_bytes)
        if (set(binding) != {"schema", "reader", "qualification"}
                or binding["schema"] != "complaint-private-replica-kit-host-binding@1"):
            raise ValueError("private_replica_compatibility_unavailable")
        loaded = {}
        for name, limit in (("reader", 65536), ("qualification", 64 * 1024 * 1024)):
            row = binding[name]
            if (not isinstance(row, dict) or set(row) != {"path", "sha256"}
                    or not isinstance(row["path"], str)
                    or not isinstance(row["sha256"], str)
                    or re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None
                    or Path(row["path"]).is_relative_to(root)):
                raise ValueError("private_replica_compatibility_unavailable")
            loaded[name] = _private_replica_host_file(row["path"], limit=limit)
            if hashlib.sha256(loaded[name]).hexdigest() != row["sha256"]:
                raise ValueError("private_replica_compatibility_unavailable")
        head = source["dependencies"]["external/ipfs_kit_py"]["head"]
        if re.fullmatch(r"[0-9a-f]{40}", str(head)) is None:
            raise ValueError("private_replica_compatibility_unavailable")
        name = "_complaint_replica_kit_" + binding["reader"]["sha256"]
        module = types.ModuleType(name)
        module.__file__ = binding["reader"]["path"]
        previous = sys.modules.get(name)
        sys.modules[name] = module
        try:
            exec(compile(loaded["reader"], module.__file__, "exec"), module.__dict__)
            proof = module.prove_kit_qualification(
                binding["qualification"]["path"], binding["qualification"]["sha256"],
                Path(root) / "external/ipfs_kit_py", head)
        finally:
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
        if (not isinstance(proof, dict)
                or proof.get("schema") != "complaint-kit-replica-compatibility-qualification@1"
                or proof.get("status") != "passed" or proof.get("kit_head") != head):
            raise ValueError("private_replica_compatibility_unavailable")
        # Detect a replacement during the pure reproof as well as at the later
        # post-measurement call. Raw pass flags never replace the pinned reader.
        for label, limit in (("reader", 65536), ("qualification", 64 * 1024 * 1024)):
            if _private_replica_host_file(binding[label]["path"], limit=limit) != loaded[label]:
                raise ValueError("private_replica_compatibility_unavailable")
        if _private_replica_host_file(binding_path, limit=65536, exact_mode=0o600) != binding_bytes:
            raise ValueError("private_replica_compatibility_unavailable")
        return {"binding": {"path": str(binding_path),
                            "sha256": hashlib.sha256(binding_bytes).hexdigest()},
                "reader": binding["reader"], "qualification": binding["qualification"],
                "kit_head": head, "current_kit_root": str(Path(root) / "external/ipfs_kit_py"),
                "execution_root": proof.get("execution_root"),
                "schema": proof["schema"], "separate_compatibility_evidence": True}
    except Exception:
        raise ValueError("private_replica_compatibility_unavailable") from None


def _private_replica_acceptance_binding(root, task, impacted):
    """Bind the provider checkout to the installed trusted companion bytes.

    The task plan and CID stay unchanged. An API-absent baseline may be
    characterized, but cannot satisfy the exact DUR005 task capability gate.
    """
    required = task.get("id") == "CIMP-DUR-005"
    if not required and _PRIVATE_REPLICA_ACCEPTANCE not in impacted:
        return None
    installed = Path(__file__).resolve().parents[2] / _PRIVATE_REPLICA_ACCEPTANCE
    candidate = Path(root) / _PRIVATE_REPLICA_ACCEPTANCE
    for path in (installed, candidate):
        if (path.is_symlink() or str(path.resolve()) != str(path)
                or not path.is_file() or path.stat().st_nlink != 1):
            raise ValueError("trusted_replica_acceptance_changed")
    trusted = hashlib.sha256(installed.read_bytes()).hexdigest()
    if hashlib.sha256(candidate.read_bytes()).hexdigest() != trusted:
        raise ValueError("trusted_replica_acceptance_changed")
    return {"path": _PRIVATE_REPLICA_ACCEPTANCE, "trusted_path": str(installed),
            "candidate_path": str(candidate), "sha256": trusted,
            "required_supported": required}


def _private_replica_acceptance_capability(junit, binding):
    """Consume an actual measured JUnit property; no JSON success shortcuts."""
    if binding is None:
        return None
    matches = []
    for case in junit.iter("testcase"):
        properties = case.findall("properties/property")
        identities = [p.get("value") for p in properties if p.get("name") == "complaint_nodeid"]
        if identities == [_PRIVATE_REPLICA_CAPABILITY_NODE]:
            if any(case.find(tag) is not None for tag in ("failure", "error", "skipped")):
                raise ValueError("private_replica_capability_unavailable")
            matches.append([p.get("value") for p in properties
                            if p.get("name") == "private_replica_capability"])
    if len(matches) != 1 or matches[0] not in (["supported"], ["unsupported"]):
        raise ValueError("private_replica_capability_unavailable")
    capability = matches[0][0]
    if binding["required_supported"] and capability != "supported":
        raise ValueError("private_replica_capability_unavailable")
    return capability


_IMPACTED_BEHAVIORAL_CHECKS = {
    "integrations/ipfs_datasets/legal.py": ("tests/test_explicit_legal_context.py", "tests/test_ipfs_adapter_layer.py"),
    "integrations/ipfs_datasets/storage.py": ("tests/test_private_storage_adapter.py", "tests/test_ipfs_kit_storage_adapter.py", "tests/test_proof_report_and_pinning.py", _PRIVATE_REPLICA_ACCEPTANCE),
    "integrations/private_storage.py": ("tests/test_private_workspace_crypto.py", "tests/test_private_workspace_keys.py", "tests/test_private_storage_adapter.py", _PRIVATE_REPLICA_ACCEPTANCE),
    "applications/complaint_workspace.py": ("tests/test_private_workspace_isolation.py", "tests/test_private_workspace_policy.py", "tests/test_private_workspace_keys.py"),
    "integrations/ipfs_datasets/llm.py": ("tests/test_grok47_router_contract.py", "tests/test_private_workspace_policy.py"),
    "mediator/mediator.py": ("tests/test_factual_correction_replay.py", "tests/test_tui_shared_interview.py"),
}


def _impacted_behavioral_checks(root, changed_paths):
    selected = set()
    for changed in changed_paths:
        selected.update(_IMPACTED_BEHAVIORAL_CHECKS.get(changed, ()))
    if any(not (root / path).is_file() for path in selected):
        raise ValueError("impacted_check_missing")
    return sorted(selected)


def measure_behavioral_command(root: Path, state_dir: Path, task: Mapping[str, Any], command: str, *,
                               runner, environment: dict, timeout_seconds: float = TIMEOUT_SECONDS,
                               context: Mapping[str, Any] | None = None, declared_command: str | None = None):
    """Execute and measure an owned command; never accept serialized success.

    Independent collection freezes the required population. The actual command
    runs with explicit phase and native AST plugins, a fresh catalog and JUnit.
    The caller-provided runner must be the native sealed executor or a test seam
    which delegates it. This callback is trusted host code, not an untrusted
    remote or JSON input; a sealed marker is not callback authentication. The
    consumed native path supplies the original canonical executor.
    """
    import shlex
    import xml.etree.ElementTree as ET
    from types import SimpleNamespace
    from .improvement_plan import (_MeasuredEvidence, _MEASURED, _pin_measurement, _digest, _hash_file,
                                   bind_sources, SEALED_ENVIRONMENT_POLICY, _safe_relative)
    root, state_dir = Path(root).resolve(), Path(state_dir).resolve()
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    run = Path(tempfile.mkdtemp(prefix="measured-", dir=state_dir)); run.chmod(0o700)
    observation_command = declared_command or command
    contract = {"task": dict(task), "context": dict(context or {}), "command": command, "declared_command": observation_command}
    extra = _task_outputs(task)
    start = time.monotonic()
    original_command = command
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native_source
    phase_relative = "integrations/ipfs_accelerate/improvement_plan.py"
    candidate_phase = root / phase_relative
    phase_source = (candidate_phase if candidate_phase.is_file() or candidate_phase.is_symlink()
                    else Path(__file__).resolve().parents[2] / phase_relative)
    phase_root = phase_source.parents[2]
    phase_source = _safe_relative(phase_root, phase_relative)
    if phase_source is None or not phase_source.is_file():
        raise ValueError("validation_bootstrap_source_unavailable")
    native_root = Path(native_source.__file__).resolve().parents[3]
    bootstrap_roots = tuple(dict.fromkeys((root, phase_root, native_root)))
    bootstrap_files = (phase_source, native_root / "ipfs_accelerate_py/__init__.py",
                       native_root / "ipfs_accelerate_py/testing/pytest_ast_seal.py")
    bootstrap_before = {str(path): _hash_file(path) for path in bootstrap_files}
    impacted = _impacted_behavioral_checks(root, (context or {}).get("changed_paths", ()))
    if task.get("id") == "CIMP-DUR-005" and _PRIVATE_REPLICA_ACCEPTANCE not in impacted:
        impacted.append(_PRIVATE_REPLICA_ACCEPTANCE)
        impacted.sort()
    replica_binding = _private_replica_acceptance_binding(root, task, impacted)
    replica_capability = None
    replica_kit_before = None
    preserved_behavioral_definitions = None
    release_script = (task.get("id") == "CIMP-REL-03" and
        observation_command == "python scripts/validate_complaint_intake.py --phase pre-admission" and
        task.get("validation_commands") in (
            ["python scripts/validate_complaint_intake.py --phase pre-admission"],
            ["python -m pytest -q --run-llm --run-network --run-heavy tests/test_intake_release_gate.py",
             "python scripts/validate_complaint_intake.py --phase pre-admission"],
        ) and
        "tests/test_intake_release_gate.py" in extra and
        command.rstrip().endswith("python scripts/validate_complaint_intake.py --phase pre-admission"))
    before = _source_freeze(root, extra)
    artifacts, results = [], []
    required, cases, imported = [], [], {}
    reason = ""
    def execute(mode):
        catalog, manifest = run / (mode + ".duckdb"), run / (mode + ".json")
        junit = run / "junit.xml"
        options = (["-p", str(context["pytest_guard_plugin"])] if (context or {}).get("pytest_guard_plugin") else []) + ["-p", "integrations.ipfs_accelerate.improvement_plan", "-p", "ipfs_accelerate_py.testing.pytest_ast_seal",
                   "--complaint-evidence-path=" + str(manifest)]
        options += ["--collect-only"] if mode == "collect" else ["--junitxml=" + str(junit), "-o", "junit_family=xunit2"]
        options += [p for p in impacted if p not in command.split()]
        instrumented = _pytest_instrument(command, options, pythonpath=bootstrap_roots)
        export = "export IPFS_ACCELERATE_PYTEST_SEAL_DUCKDB=" + shlex.quote(str(catalog))
        # Never depend on ambient pytest injection or a shared/reused catalog.
        export += " PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS='' PYTEST_PLUGINS=''"
        instrumented = export + " && " + instrumented
        remaining = timeout_seconds - (time.monotonic() - start)
        if remaining <= 0:
            raise TimeoutError("subprocess_timeout")
        result = runner(spec=SimpleNamespace(command=instrumented, raw_command=command),
                        workspace_path=root, timeout_seconds=remaining, environment=environment)
        _atomic_json(run / (mode + "-native-result.json"), result)
        results.append({"mode": mode, "original_command": command, "instrumented_command": instrumented, "executed_command": result.get("command"),
                        "returncode": result.get("returncode"), "timed_out": bool(result.get("timed_out")),
                        "validation_python_launcher": result.get("validation_python_launcher", {})})
        if result.get("validation_python_launcher", {}).get("sealed") is not True:
            raise ValueError("sealed_execution_unavailable")
        if result.get("timed_out") or result.get("error") == "subprocess_timeout":
            raise TimeoutError("subprocess_timeout")
        if not manifest.is_file():
            raise ValueError("missing_phase_manifest")
        guard_path = manifest.with_suffix(".guard.json")
        if (context or {}).get("require_child_guard") or guard_path.is_file():
            guard = _read_json(guard_path)
            if guard.get("network_process_dispatch_permitted") is not False or guard.get("exitstatus") != result.get("returncode"):
                raise ValueError("nested_fixture_guard_unavailable")
            artifacts.append({"path": str(guard_path), "sha256": _hash_file(guard_path)})
        observation = _read_json(manifest, limit=20_000_000)
        if observation.get("exitstatus") != result.get("returncode"):
            raise ValueError("exit_status_mismatch")
        for path in (manifest, catalog, run / (mode + "-native-result.json"), *([junit] if mode == "run" else [])):
            if not path.is_file():
                raise ValueError("missing_output")
            artifacts.append({"path": str(path), "sha256": _hash_file(path)})
        return result, observation, _read_catalog(catalog, repo_root=root)
    try:
        preserved_behavioral_definitions = _preserve_existing_behavioral_definitions(
            root, [*extra, *impacted, *(context or {}).get("changed_paths", ())])
        replica_kit_before = _private_replica_kit_qualification(root, state_dir, task, before,
            campaign_state_dir=(context or {}).get("campaign_state_dir"))
        if release_script:
            if time.monotonic() - start >= timeout_seconds:
                raise TimeoutError("subprocess_timeout")
            original = runner(spec=SimpleNamespace(command=original_command, raw_command=original_command),
                workspace_path=root, timeout_seconds=max(0.001, timeout_seconds - (time.monotonic() - start)), environment=environment)
            _atomic_json(run / "declared-script-result.json", original)
            artifacts.append({"path": str(run / "declared-script-result.json"), "sha256": _hash_file(run / "declared-script-result.json")})
            results.append({"mode": "declared_script", "original_command": original_command,
                "instrumented_command": original_command, "returncode": original.get("returncode"),
                "validation_python_launcher": original.get("validation_python_launcher", {})})
            if original.get("validation_python_launcher", {}).get("sealed") is not True:
                raise ValueError("sealed_execution_unavailable")
            if original.get("timed_out"):
                raise TimeoutError("subprocess_timeout")
            if original.get("returncode") != 0:
                raise ValueError("declared_command_failed")
            command = command[:-len("python scripts/validate_complaint_intake.py --phase pre-admission")] + "python -m pytest -q --run-llm --run-network --run-heavy tests/test_intake_release_gate.py"
        collected_result, collection, (_, collected_hashes) = execute("collect")
        required = collection.get("nodeids", [])
        if collected_result.get("returncode") != 0:
            raise ValueError("collection_failed")
        if not required:
            raise ValueError("zero_test_collection")
        if len(required) != len(set(required)) or any(not isinstance(n, str) or not n for n in required):
            raise ValueError("required_test_identity_malformed")
        if before != _source_freeze(root, extra):
            raise ValueError("stale_source_hash")
        executed, phases, (sealed_nodes, imported) = execute("run")
        if required != phases.get("nodeids"):
            raise ValueError("collection_identity_mismatch")
        by_node = {}
        for row in phases.get("reports", []):
            by_node.setdefault(row["nodeid"], []).append(row)
        for node in required:
            reports = by_node.get(node, [])
            outcomes = [r.get("outcome") for r in reports]
            outcome = "skipped" if "skipped" in outcomes else "failed" if "failed" in outcomes else "passed"
            cases.append({"nodeid": node, "outcome": outcome})
            if outcome == "skipped":
                raise ValueError("skipped_required_case")
            if outcome == "failed":
                raise ValueError("failed_assertion")
            if sorted(r.get("when") for r in reports) != ["call", "setup", "teardown"]:
                raise ValueError("missing_required_case_phase")
        if set(by_node) != set(required) or executed.get("returncode") != 0:
            raise ValueError("failed_assertion")
        junit_nodes = []
        junit_document = ET.parse(run / "junit.xml")
        replica_capability = _private_replica_acceptance_capability(junit_document, replica_binding)
        for case in junit_document.iter("testcase"):
            identity = [p.get("value") for p in case.findall("properties/property") if p.get("name") == "complaint_nodeid"]
            if len(identity) != 1 or any(case.find(tag) is not None for tag in ("failure", "error", "skipped")):
                raise ValueError("junit_required_case_mismatch")
            junit_nodes.extend(identity)
        if len(junit_nodes) != len(required) or set(junit_nodes) != set(required):
            raise ValueError("junit_required_case_mismatch")
        if len(sealed_nodes) != len(required) or set(sealed_nodes) != set(required):
            raise ValueError("missing_current_ast_seal")
        if any(imported.get(p) != h for p, h in collected_hashes.items()):
            raise ValueError("stale_source_hash")
    except (OSError, ValueError, TypeError, KeyError, TimeoutError) as exc:
        reason = str(exc) if str(exc) in {"declared_command_failed", "zero_test_collection", "collection_failed", "required_test_identity_malformed", "collection_identity_mismatch", "subprocess_timeout", "missing_output", "missing_phase_manifest", "missing_required_case_phase", "sealed_execution_unavailable", "exit_status_mismatch", "stale_source_hash", "skipped_required_case", "failed_assertion", "junit_required_case_mismatch", "missing_current_ast_seal", "unsupported_behavioral_command", "trusted_replica_acceptance_changed", "private_replica_capability_unavailable", "private_replica_compatibility_unavailable", "existing_behavioral_definition_changed"} else "host_measurement_unavailable"
    try:
        if replica_binding != _private_replica_acceptance_binding(root, task, impacted):
            reason = "trusted_replica_acceptance_changed"
    except (OSError, ValueError):
        reason = "trusted_replica_acceptance_changed"
    after = _source_freeze(root, extra)
    try:
        replica_kit_after = _private_replica_kit_qualification(root, state_dir, task, after,
            campaign_state_dir=(context or {}).get("campaign_state_dir"))
        if replica_kit_after != replica_kit_before:
            reason = "private_replica_compatibility_unavailable"
    except ValueError:
        reason = "private_replica_compatibility_unavailable"
    bootstrap_after = {str(path): _hash_file(path) for path in bootstrap_files}
    if before != after or bootstrap_before != bootstrap_after:
        reason = "stale_source_hash"
    imported.update(bootstrap_before)
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon import PortalImplementationDaemon
    measured = {"schema": "complaint-owned-behavioral-measurement@1", "reason": reason,
                "preserved_behavioral_definitions": preserved_behavioral_definitions,
                "trusted_executor": {"module": str(getattr(runner, "__module__", "")), "qualname": str(getattr(runner, "__qualname__", "")),
                    "canonical_native_identity": runner is PortalImplementationDaemon._validation_command_runner,
                    "boundary": "trusted host code; returned sealed marker alone does not authenticate arbitrary callbacks"},
                "required_nodeids": required, "cases": cases, "source_before": before, "source_after": after,
                "source_unchanged": before == after and bootstrap_before == bootstrap_after, "imported_sources": imported,
                "validation_bootstrap": {"pythonpath_roots": list(map(str, bootstrap_roots)),
                                         "before": bootstrap_before, "after": bootstrap_after},
                "task_contract_digest": _digest(contract), "results": results, "artifacts": artifacts,
                "completion_authority": False, "run_path": str(run),
                "lane_basis": "native_host_validation", "live_node_verified": False, "impacted_checks": impacted,
                "behavioral_companion": "tests/test_intake_release_gate.py" if release_script else None,
                "private_replica_acceptance": {"binding": replica_binding, "capability": replica_capability,
                                               "kit_compatibility": replica_kit_before},
                "environment_policy": {"effective_PATH": environment.get("PATH"), "python": environment.get("IPFS_ACCELERATE_VALIDATION_PYTHON_EXECUTABLE"),
                    "HOME": "fresh private native command directory; not operator home", "ambient_pytest_injection": False}}
    measured["workspace_path"] = str(root)
    measured["output_paths"] = extra
    artifact_rows = [{"relative_path": os.path.relpath(a["path"], root), "path": a["path"],
                      "present": True, "sha256": a["sha256"]} for a in artifacts]
    # These environment fields describe native policy, not access to the real home.
    observed_environment = {**SEALED_ENVIRONMENT_POLICY, "HOME": "native-managed-fresh-private-home"}
    measured["observation_binding"] = {"command": observation_command, "collected_count": len(required),
        "required_nodeids": required, "cases": cases, "source_binding": bind_sources(root, extra),
        "exit_status": 0 if not reason else 1, "timed_out": reason == "subprocess_timeout",
        "lane": "local_node_integration", "artifacts": artifact_rows, "environment": observed_environment}
    _atomic_json(run / "measurement.json", measured)
    observed = _MeasuredEvidence({"lane": "local_node_integration", "command": observation_command,
            "exit_status": 0 if not reason else 1, "timed_out": reason == "subprocess_timeout",
            "collected_count": len(required), "cases": cases, "required_nodeids": required,
            "environment": observed_environment, "source_binding": bind_sources(root, extra),
            "artifacts": artifact_rows, "host_measurement": measured, "host_task_contract": contract}, capability=_MEASURED)
    _pin_measurement(observed, run / "measurement.json", _hash_file(run / "measurement.json"))
    result_path = next((run / name for name in ("run-native-result.json", "collect-native-result.json", "declared-script-result.json") if (run / name).is_file()), run / "unavailable")
    observed.native_result = _read_json(result_path, limit=20_000_000)
    return observed


class EvidenceValidationScheduler:
    """Native scheduler decorator: preserve proposal/impact binding and sole loop."""
    def __init__(self, native_scheduler, *, state_dir, spec, defer_readiness=False):
        self.native_scheduler = native_scheduler
        self.state_dir, self.spec = Path(state_dir), spec
        self.defer_readiness = bool(defer_readiness)
        self.bound_task = None

    def bind_task(self, task, workspace):
        self.bound_task = (task, Path(workspace).resolve())
        return {}  # native proof_workflow has no invented proof/fallback options

    def _run(self, method, *args, **kwargs):
        from dataclasses import replace
        from ipfs_accelerate_py.agent_supervisor.validation.validation_runtime import sealed_validation_python_runner
        if self.bound_task is None or self.bound_task[1] != Path(kwargs["workspace_path"]).resolve():
            return {"attempted": False, "passed": False, "returncode": 78, "results": [], "reason": "task_evidence_binding_missing"}
        native_task, root = self.bound_task
        task = next((t for t in self.spec["tasks"] if t["id"] == native_task.task_id), None)
        if task is None:
            return {"attempted": False, "passed": False, "returncode": 78, "results": [], "reason": "task_evidence_contract_missing"}
        delegate = kwargs.get("runner")
        receipts = []
        @sealed_validation_python_runner
        def measured_runner(*, spec, workspace_path, timeout_seconds, environment):
            observed = measure_behavioral_command(root, self.state_dir / "evidence-runs", task, str(spec.command),
                runner=delegate, environment=environment, timeout_seconds=timeout_seconds,
                declared_command=task["validation_commands"][spec.ordinal] if spec.ordinal < len(task["validation_commands"]) else None,
                context={"campaign_state_dir": str(self.state_dir.resolve()),
                         "task_id": native_task.task_id, "task_cid": str(getattr(native_task, "canonical_task_cid", "")),
                         "proposal_id": str(getattr(getattr(args[0], "proposal", None), "proposal_id", "")) if method == "run_validated" else "",
                         "proposal_context_id": str(getattr(getattr(args[0], "proposal", None), "context_id", "")) if method == "run_validated" else "",
                         "proposal_replay_nonce_sha256": hashlib.sha256(str(getattr(getattr(args[0], "proposal", None), "replay_nonce", "")).encode()).hexdigest() if method == "run_validated" else "",
                         "changed_paths": list(getattr(getattr(args[0], "proposal", None), "changed_paths", ())) if method == "run_validated" else [],
                         "attempt_ordinal": None, "attempt_binding_status": "ordinal_unavailable_from_public_task_hook; native_proposal_context_retained",
                         "repository_tree_id": str(getattr(getattr(args[0], "proposal", None), "repository_tree_id", "")) if method == "run_validated" else "",
                         "model_policy": {"model": MODEL, "fallback": False}})
            receipt = gate_task_completion(root, self.state_dir, task, observed,
                legal_data_version=observed["host_measurement"]["source_before"]["dependencies"].get("external/ipfs_datasets_py", {}).get("head", "unavailable"))
            receipts.append(receipt)
            result = dict(observed.native_result)
            result.update(command=str(spec.command), raw_command=str(spec.raw_command or spec.command),
                          returncode=0 if receipt["admitted"] else 78, behavioral_evidence=receipt)
            return result
        kwargs["runner"] = measured_runner
        # A previous cached return code cannot stand in for current measured cases.
        command_index = 1 if method == "run_validated" else 0
        mutable = list(args)
        from ipfs_accelerate_py.agent_supervisor.validation.validation_commands import build_validation_commands
        mutable[command_index] = tuple(replace(c, cacheable=False) for c in build_validation_commands(mutable[command_index]))
        result = getattr(self.native_scheduler, method)(*mutable, **kwargs)
        if result.get("passed") and (not receipts or any(not r["admitted"] for r in receipts)):
            result.update(passed=False, returncode=78, reason="current_behavioral_evidence_required",
                          merge_eligible=False, completion_authoritative=False, authoritative=False)
        result["behavioral_evidence"] = receipts
        result["firstparty_completion_authority"] = False
        if self.defer_readiness:
            # This full-campaign observation can scan every previous evidence
            # receipt. Keep it outside Native's current validation deadline;
            # current measured admission and Native dependency checks already
            # govern this result. Explicit standalone observations retain the
            # synchronous behavior through the default constructor option.
            result["dependent_readiness"] = {
                "available": False, "reason": "deferred_outside_validation",
                "native_scheduling_enforced": False, "completion_authority": False,
            }
            return result
        from .improvement_plan import canonical_model_policy
        try:
            dependency = _source_freeze(root).get("dependencies", {}).get("external/ipfs_datasets_py", {})
            legal_version = dependency.get("head") or dependency.get("gitlink") or "unavailable"
            result["dependent_readiness"] = recompute_dependent_readiness(
                root, self.state_dir, self.spec, model_policy=canonical_model_policy(), legal_data_version=legal_version)
        except Exception:
            # Advisory observation must not replace native validation results;
            # cancellation/SystemExit remain outside this ordinary-exception fence.
            result["dependent_readiness"] = {"available": False, "reason": "advisory_observation_unavailable",
                "native_scheduling_enforced": False, "completion_authority": False}
        return result

    def run(self, *args, **kwargs):
        return self._run("run", *args, **kwargs)

    def run_validated(self, *args, **kwargs):
        return self._run("run_validated", *args, **kwargs)

def _run_evidence_daemon_adapter(argv, *, repo_root, validation_scheduler, proof_workflow=None):
    import signal
    import threading
    from pathlib import Path
    from ipfs_accelerate_py.agent_supervisor.runtime.process_security import harden_state_authority_process
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_daemon_runner import (
        ImplementationDaemonRunContext, implementation_state_paths,
        configure_daemon_logging, apply_merge_resolver_environment,
        run_portal_implementation_daemon_loop,
    )
    harden_state_authority_process()
    args = native.parse_args(list(argv))
    if validation_scheduler is None:
        raise ValueError("behavioral_evidence_scheduler_unavailable")
    # This adapter owns the ordinary Markdown route only. Do not demote any
    # richer authority mode or discard a requested maintenance operation.
    if (str(getattr(args, 'authority_mode', '') or '') not in {'', 'legacy_markdown'}
            or str(getattr(args, 'task_source_kind', '') or '') not in {'', 'legacy-markdown'}):
        raise ValueError("unsupported_evidence_daemon_authority")
    forbidden = (
        'database_path', 'coordination_path', 'quack_endpoint', 'owner_session_id',
        'state_owner_client_id', 'task_context_bundle_artifact', 'task_context_bundle_sha256',
        'production_provider_policy', 'production_provider_launch_authority_receipt_path',
        'production_provider_launch_authority_receipt_content_id',
        'manual_completion_authority_task_id', 'manual_completion_authority_required_task_id',
        'manual_completion_authority_epoch_id', 'manual_completion_authority_revalidation_only',
        'reset_manual_completion_authority_renewal_task_id', 'clear_protected_path_incident',
        'approve_protected_path_commit', 'operator_clearance_note',
        'approve_disposed_ephemeral_workspace', 'accepted_control_plane_pin_json',
        'configured_board_live_admission_json', 'plan_bound_revision_cid',
    )
    if any(getattr(args, name, None) for name in forbidden):
        raise ValueError("unsupported_evidence_daemon_authority")
    if int(getattr(args, 'state_owner_bootstrap_fd', -1)) != -1:
        raise ValueError("unsupported_evidence_daemon_owner_bootstrap")
    resource_worktrees = args.worktree_root or args.state_dir / "worktrees"
    resource_environment = dict(os.environ)
    _require_resource_capacity(Path(repo_root), args.state_dir, resource_worktrees,
                               resource_environment, stage="before_native_daemon")
    configure_daemon_logging(args)
    apply_merge_resolver_environment(args)
    # Preserve nativeA main's exact49 argument expressions. In particular this
    # includes validation workers/budget, generated paths, reservations, source
    # root expectations, slices, worktree/merge scope and all custody options.
    REPO_ROOT = Path(repo_root).resolve()
    daemon = native.PortalImplementationDaemon(
        assumed_completed_task_ids=args.assume_completed_task_id,
        board_namespace=str(getattr(args, "board_namespace", "") or ""),
        events_path=args.state_dir / f"{args.state_prefix}_events.jsonl",
        execution_slice_task_cids=args.execution_slice_task_cid,
        execution_slice_task_ids=args.execution_slice_task_id,
        expected_task_source_repository_root_id=args.expected_task_source_repository_root,
        expected_task_source_root_id=args.expected_task_source_root,
        external_reservation_manifest_paths=args.external_reservation_manifest_path,
        generated_status_paths=args.generated_status_path,
        idle_lane_work_stealing=args.idle_lane_work_stealing,
        implement=args.implement,
        implementation_command=args.implementation_command or None,
        implementation_protected_paths=args.implementation_protected_path,
        implementation_timeout=args.implementation_timeout,
        llm_merge_resolver_command=args.llm_merge_resolver_command or None,
        llm_merge_resolver_timeout_seconds=args.llm_merge_resolver_timeout_seconds,
        maintenance_interval_seconds=args.maintenance_interval_seconds,
        manual_completion_authority_epoch_id=args.manual_completion_authority_epoch_id,
        manual_completion_authority_required_task_ids=args.manual_completion_authority_required_task_id,
        manual_completion_authority_revalidation_only=args.manual_completion_authority_revalidation_only,
        manual_completion_authority_task_ids=args.manual_completion_authority_task_id,
        max_task_attempts=args.max_task_attempts,
        merge_queue_dir=args.merge_queue_dir,
        merge_reconciliation_max_merges=args.merge_reconciliation_max_merges,
        merge_target_branch=args.merge_target_branch,
        merged_worktree_cleanup_max=args.merged_worktree_cleanup_max,
        objective_bundle_dir=args.objective_bundle_dir,
        objective_path=args.objective_path,
        production_provider_context_budget_tokens=args.production_provider_context_budget_tokens,
        production_provider_launch_authority_receipt_content_id=args.production_provider_launch_authority_receipt_content_id,
        production_provider_launch_authority_receipt_path=args.production_provider_launch_authority_receipt_path,
        production_provider_policy=args.production_provider_policy,
        production_provider_review_authority_key_path=args.production_provider_review_authority_key_path,
        production_provider_timeout_seconds=args.production_provider_timeout_seconds,
        repo_root=REPO_ROOT,
        state_path=args.state_dir / f"{args.state_prefix}_task_state.json",
        strategy_path=args.state_dir / f"{args.state_prefix}_strategy.json",
        strict_task_sharding=args.strict_task_sharding,
        task_header_prefix=args.task_prefix,
        task_shard_count=args.task_shard_count,
        task_shard_index=args.task_shard_index,
        task_source=args.todo_path
                            if args.task_source_kind in {"markdown", "duckdb"}
                            else None,
        task_source_kind=args.task_source_kind
                            if args.task_source_kind in {"markdown", "duckdb"}
                            else "",
        todo_path=args.todo_path,
        use_ephemeral_worktree=args.implement and not args.no_ephemeral_worktree,
        validation_max_workers=args.validation_max_workers,
        validation_resource_budget=args.validation_resource_budget,
        worktree_root=args.worktree_root,
        worktree_submodule_paths=args.worktree_submodule_path or None,
        validation_scheduler=validation_scheduler,
        proof_workflow=proof_workflow,
    )
    context = ImplementationDaemonRunContext(parsed=args, **implementation_state_paths(args))
    handlers_installed = threading.current_thread() is threading.main_thread()
    previous_term = previous_int = None
    def request_stop(signum, _frame):
        raise SystemExit(128 + signum)
    if handlers_installed:
        previous_term = signal.signal(signal.SIGTERM, request_stop)
        previous_int = signal.signal(signal.SIGINT, request_stop)
    try:
        # The public native loop owns run_once, bounded wait and event close.
        return run_portal_implementation_daemon_loop(daemon, context, logger=native.logger,
            hooks=(_resource_admission_hook(REPO_ROOT, args.state_dir, resource_worktrees, resource_environment),))
    finally:
        if handlers_installed:
            signal.signal(signal.SIGTERM, previous_term)
            signal.signal(signal.SIGINT, previous_int)


def evidence_daemon_main(argv):
    root = Path(__file__).resolve().parents[2]
    _native_modules(root)
    from .improvement_plan import load_spec
    from ipfs_accelerate_py.agent_supervisor.todo_daemon import implementation_daemon as native
    from ipfs_accelerate_py.agent_supervisor.validation.validation_scheduler import ValidationScheduler
    args = native.parse_args(list(argv))
    scheduler = EvidenceValidationScheduler(ValidationScheduler(max_workers=args.validation_max_workers,
        resource_budget=args.validation_resource_budget, default_timeout_seconds=args.implementation_timeout),
        state_dir=args.state_dir, spec=load_spec(root / SPEC_RELATIVE), defer_readiness=True)
    return _run_evidence_daemon_adapter(argv, repo_root=root, validation_scheduler=scheduler, proof_workflow=scheduler.bind_task)


if __name__ == "__main__":
    # The native supervisor executes its public daemon_script_path directly.
    # Bootstrap before relative imports; ordinary application CLI stays intact.
    if __package__ in {None, ""}:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        __package__ = "integrations.ipfs_accelerate"
    raise SystemExit(evidence_daemon_main(sys.argv[1:]) if "--todo-path" in sys.argv[1:] else main())
