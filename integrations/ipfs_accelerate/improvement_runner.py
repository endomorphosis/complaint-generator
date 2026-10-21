"""Own and observe one Grok-only native implementation supervisor campaign.

This wrapper does not implement a second task scheduler. The native supervisor
owns its daemon, implementation deadlines, retries and task completion evidence.
Launcher records only establish process ownership; a PID is not progress proof.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import logging
import multiprocessing
import os
from pathlib import Path
import platform
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
_LOGGER = logging.getLogger(__name__)
PRIVATE_PATHS_ENV = "IPFS_ACCELERATE_AGENT_GROK_PRIVATE_PATHS_JSON"
REASONING_EFFORT_ENV = "IPFS_ACCELERATE_AGENT_GROK_REASONING_EFFORT"
ORCHESTRATION_DIR_ENV = "IPFS_ACCELERATE_AGENT_ORCHESTRATION_DIR"
AUTOMATIC_RETRY_REARM_ENV = "IPFS_ACCELERATE_AGENT_AUTOMATIC_RETRY_REARM"
WORKTREE_MARKER = ".complaint-worktree-root.json"
_PRIVATE_PATHS = (".complaint_workspace", "data", "output", "statefiles", "exports", "secrets",
                  ".env*", "*.key", "*.pem")


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
        if any(value == item or value.startswith(item + "/") for item in _PRIVATE_PATHS[:6]):
            continue
        if value not in result:
            result.append(value)
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
        "IPFS_ACCELERATE_AGENT_WORKTREE_SUBMODULE_PATHS": "external/ipfs_datasets_py",
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
    patterns = validator(env[PRIVATE_PATHS_ENV])
    resolver(base_env=dict(env), workspace=repo_root)
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
        # The workspace imports datasets during pytest collection. This pinned
        # source is required even for tasks that edit only first-party files.
        "--worktree-submodule-path", "external/ipfs_datasets_py",
        "--merge-queue-dir", str(state_dir / "merge-queue"),
        "--llm-merge-resolver-command", "",
        "--no-worktree-reconciliation", "--no-worktree-reconciliation-preflight",
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
    os.chdir(repo_root)
    from .improvement_plan import BOARD_RELATIVE, build_improvement_work_plan, load_spec
    spec = load_spec(spec_path)
    plan = build_improvement_work_plan(spec)
    branch = merge_target or _branch(repo_root)
    supervisor, _ = _native_modules(repo_root)
    selected_root, root_binding = _select_worktree_root(repo_root, state_dir, _read_json(state_dir / "launcher.json"), worktree_root)
    args = native_argv(repo_root / BOARD_RELATIVE, state_dir, branch, worktree_root=selected_root)
    parsed = supervisor.parse_args(args)
    config = supervisor.supervisor_config_from_args(parsed, repo_root=repo_root)
    board = _validate_board(repo_root, repo_root / BOARD_RELATIVE, spec)
    env = campaign_environment(repo_root, context_exclude=spec["execution_policy"].get("context_exclude"), state_dir=state_dir)
    grok = shutil.which(env.get("IPFS_ACCELERATE_AGENT_GROK_BIN") or "grok", path=env.get("PATH"))
    auth_home = Path(env.get("GROK_HOME") or str(Path.home() / ".grok"))
    auth_file = auth_home / "auth.json"
    auth_present = any(bool(env.get(key)) for key in (
        "XAI_API_KEY", "ipfs_accelerate_py_XAI_API_KEY", "IPFS_ACCELERATE_PY_XAI_API_KEY",
        "IPFS_DATASETS_PY_XAI_API_KEY"))
    try:
        auth_present = auth_present or (auth_file.is_file() and auth_file.stat().st_size > 0)
    except OSError:
        pass
    privacy = _private_runtime_checks(repo_root, env)
    capacity = _worktree_capacity(repo_root, selected_root)
    return {"status": "ready" if grok and auth_present and privacy["ready"] and capacity["sufficient"] is not False else "not_ready",
            "provider": "grok_cli", "model": MODEL, "allow_fallback": False,
            "grok_binary_present": bool(grok), "auth_material_present": bool(auth_present),
            "auth_provider_command_supported": False,
            "auth_validated": False, "paid_calls": 0, "native_plan_id": plan.plan_id,
            "native_config_validated": True, "native_task_source": parsed.task_source_kind,
            "ephemeral_worktrees": config.use_ephemeral_worktree, "merge_target": branch,
            "privacy": privacy, "worktree_capacity": capacity, "worktree_root": str(selected_root), "worktree_root_binding": root_binding,
            "board": board, "native_argv": args,
            "limitations": ["Credential presence does not verify login, quota, model access or execution progress.",
                            "Native supervisor retries are bounded per task and to five daemon restarts; manual holds are never cleared.",
                            "Cross-worktree reconciliation and dynamic guardrail/refill task generation are disabled for this fixed campaign; native dependency readiness, process fencing and implementation watchdog remain enabled."]}


def start(repo_root: Path, spec_path: Path, state_dir: Path, *, worktree_root: Path | None = None) -> dict[str, Any]:
    state_dir = state_dir.resolve()
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
        if full_launch:
            # A dead PID is not evidence that private Docker workers are gone.
            # Keep the retained receipt until the same proof status uses is current
            # and a fresh bounded closure observation agrees.
            if not _shutdown_verified(previous, _read_json(state_dir / "container_shutdown.json"), repo_root, state_dir):
                return _stop_incomplete(state_dir, "shutdown_proof_unverified")
            from .improvement_shutdown import close_campaign_containers
            containers = close_campaign_containers(state_dir, previous)
            current = _read_json(owner_path)
            if current != previous or current.get("read_error"):
                return _stop_incomplete(state_dir, "ownership_changed_during_closure")
            if owns_process(current):
                if not _campaign_tuple_matches(current, repo_root, spec_path, state_dir):
                    return _stop_incomplete(state_dir, "live_campaign_mismatch")
                return {"status": "already_running", "pid": current["identity"]["pid"], "state_dir": str(state_dir)}
            shutdown = _read_json(state_dir / "container_shutdown.json")
            if (not containers.get("applicable") or not containers.get("quiesced")
                    or containers.get("status") != "stopped"
                    or not _shutdown_verified(current, shutdown, repo_root, state_dir)):
                return _stop_incomplete(state_dir, "container_closure_unverified")
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


def _provider_event_evidence(path: Path, *, task_id: str, started_at: float) -> dict[str, Any] | None:
    for line in reversed(_tail(path, lines=40, maximum=64_000)):
        try:
            event = json.loads(line)
            timestamp = datetime.fromisoformat(str(event.get("timestamp", "")).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            if timestamp.timestamp() < started_at or event.get("task_id") != task_id:
                continue
            if event.get("type") in {"implementation_provider_started", "provider_runner_started", "provider_runner_birth"}:
                return {"type": event["type"], "timestamp": event["timestamp"], "task_id": task_id,
                        "source": "native_daemon_events", "completion_authority": False}
        except (ValueError, TypeError, AttributeError):
            continue
    return None


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
    intentional_wait = str(native_state.get("active_phase", "")).lower() in {
        "waiting_for_user", "waiting_user", "awaiting_user", "manual_hold", "paused",
    }
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
    provider_evidence = _provider_event_evidence(events_path, task_id=str(native_state.get("active_task_id") or native_state.get("last_implementation_task_id") or ""),
                                               started_at=now - since_start) if claim_verified else None
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
        health = "stalled" if hard_expired or (active_age is not None and active_age > STALL_SECONDS) else "active"
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
    keys = ("heartbeat_at", "last_progress_at", "active_task_id", "active_task_started_at", "active_phase", "active_phase_detail",
            "implementation_in_progress", "active_attempt", "last_implementation_returncode",
            "recommended_task_id", "ready_task_ids", "selectable_ready_task_ids", "blocked_task_ids", "selection_idle_reason")
    return {"status": health, "owned_process_alive": owned,
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
            "provider_execution_verified": bool(owned and provider_evidence),
            "provider_execution_evidence": provider_evidence,
            "progress_verified": bool(owned and provider_evidence),
            "completion_authority": False}


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


def stop(state_dir: Path, *, timeout: float = 15.0) -> dict[str, Any]:
    with _lock(state_dir):
        path = state_dir / "launcher.json"
        record = _read_json(path)
        from .improvement_shutdown import close_campaign_containers
        try:
            recorded_worktree_root(record, state_dir)
        except (OSError, ValueError, TypeError) as error:
            return {"status": "stop_incomplete", "signalled": False, "reason": str(error), "manual_holds_preserved": True}
        if not owns_process(record):
            containers = close_campaign_containers(state_dir, record)
            if not containers["applicable"]:
                return {"status": "not_owned_or_stopped", "signalled": False}
            if containers["quiesced"]:
                record.update(status="stopped", stopped_at=time.time())
                _atomic_json(path, record)
            return {"status": containers["status"], "signalled": False,
                    "container_shutdown": containers, "manual_holds_preserved": True}
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


def run_internal(repo_root: Path, spec_path: Path, state_dir: Path, token: str, merge_target: str, *, worktree_root: Path | None = None) -> int:
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
        os.environ.clear()
        os.environ.update(effective)
        _validate_board(repo_root, repo_root / BOARD_RELATIVE, spec)
        privacy = _private_runtime_checks(repo_root, effective)
        if not privacy["ready"]:
            raise RuntimeError(privacy["reason"])
        from ipfs_accelerate_py.agent_supervisor.todo_daemon.implementation_supervisor_runner import (
            run_configured_portal_implementation_supervisor,
        )
        # Recheck the bound storage directory immediately before native admission.
        if recorded_worktree_root(record, state_dir) != (selected_root, root_binding):
            raise RuntimeError("worktree root changed before native admission")
        # No --once: this is the real native run_forever watchdog and daemon.
        run_configured_portal_implementation_supervisor(
            native_argv(repo_root / BOARD_RELATIVE, state_dir, merge_target, worktree_root=selected_root),
            repo_root=repo_root, logger=_LOGGER,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare, run and observe the Grok-only complaint improvement campaign.")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "doctor", "start", "status", "stop", "_run"):
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
            result = {"prepare": prepare, "doctor": doctor, "start": start, "status": status}[args.command](root, spec, state, **keywords)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2 if result.get("status") in {"not_ready", "board_error", "state_error", "identity_mismatch", "stop_incomplete"} else 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2

