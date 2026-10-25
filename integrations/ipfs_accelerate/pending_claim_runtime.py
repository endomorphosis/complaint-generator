"""Load a reviewed Native recovery companion without replacing the live SDK.

The optional private configuration selects source, never an adjudication or
completion receipt. The Native public API still derives and checks all custody.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

MODULE = "ipfs_accelerate_py.agent_supervisor.todo_daemon.pending_task_claim_recovery"
RELATIVE = MODULE.replace(".", "/") + ".py"
CONFIG_NAME = "pending-task-claim-runtime.json"
SCHEMA = "complaint.pending-task-claim-runtime.v1"


def _need(condition, reason):
    if not condition:
        raise ValueError(reason)


def _canonical(path):
    path = Path(path)
    _need(path.is_absolute() and path.resolve(strict=True) == path, "pending_claim_runtime_aliased_path")
    return path


def _read(path, *, private=False):
    path = _canonical(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        _need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1,
              "pending_claim_runtime_unowned_file")
        _need(not private or stat.S_IMODE(info.st_mode) == 0o600,
              "pending_claim_runtime_unsafe_config")
        limit = 65536 if private else 8_000_000
        _need(info.st_size <= limit, "pending_claim_runtime_source_too_large")
        raw = b""
        while len(raw) <= limit:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            raw += chunk
        def identity(value):
            return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
                    value.st_uid, value.st_gid, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        _need(len(raw) == info.st_size and identity(os.fstat(fd)) == identity(info)
              and identity(path.lstat()) == identity(info) and path.resolve(strict=True) == path,
              "pending_claim_runtime_file_changed")
        return raw
    finally:
        os.close(fd)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _git(root, *args):
    result = subprocess.run(["git", "--no-replace-objects", "-c", "core.hooksPath=/dev/null", *args],
                            cwd=root, capture_output=True, timeout=15, check=False)
    _need(result.returncode == 0, "pending_claim_runtime_git_binding_unavailable")
    return result.stdout


def _source(root, commit, relative):
    root = _canonical(root)
    _need(root.stat().st_uid == os.getuid() and root.is_dir(), "pending_claim_runtime_unowned_root")
    _need(re.fullmatch(r"[a-f0-9]{40}", commit or "") is not None,
          "pending_claim_runtime_commit_required")
    _need(_git(root, "rev-parse", "--show-toplevel").decode().strip() == str(root)
          and _git(root, "rev-parse", "HEAD").decode().strip() == commit,
          "pending_claim_runtime_checkout_changed")
    raw = _read(root / relative)
    _need(_git(root, "show", commit + ":" + relative) == raw,
          "pending_claim_runtime_working_source_changed")
    oid = _git(root, "rev-parse", commit + ":" + relative).decode().strip()
    return root / relative, raw, oid


def _verified_module(path, raw, *, native_facade=False):
    parent_name, name = MODULE.rsplit(".", 1)
    parent = importlib.import_module(parent_name)
    if native_facade:
        # An upgraded SDK owns its normal module import and public facades.
        # A preimported genuine module does not carry our companion marker.
        module = importlib.import_module(MODULE)
        _need(Path(getattr(module, "__file__", "")).absolute() == path
              and getattr(getattr(module, "__spec__", None), "origin", None) == str(path)
              and getattr(module, "__package__", None) == parent_name
              and getattr(parent, name, None) is module
              and callable(getattr(module, "review", None)) and callable(getattr(module, "reconcile", None)),
              "pending_claim_runtime_native_facade_origin_changed")
        return module
    present = sys.modules.get(MODULE)
    if present is not None:
        _need(Path(getattr(present, "__file__", "")).absolute() == path
              and getattr(present, "__complaint_source_sha256__", None) == _sha(raw)
              and getattr(getattr(present, "__spec__", None), "origin", None) == str(path)
              and getattr(present, "__package__", None) == parent_name
              and getattr(parent, name, None) is present,
              "pending_claim_runtime_module_identity_conflict")
        return present
    _need(not hasattr(parent, name), "pending_claim_runtime_module_identity_conflict")
    spec = importlib.util.spec_from_file_location(MODULE, path)
    _need(spec is not None and spec.loader is not None, "pending_claim_runtime_source_spec_unavailable")
    module = importlib.util.module_from_spec(spec)
    # Execute the already verified bytes, not a later path read or a pyc.
    sys.modules[MODULE] = module
    try:
        exec(compile(raw, str(path), "exec", dont_inherit=True), module.__dict__)
        _need(callable(getattr(module, "review", None)) and callable(getattr(module, "reconcile", None)),
              "pending_claim_runtime_public_api_unavailable")
        module.__complaint_source_sha256__ = _sha(raw)
        setattr(parent, name, module)
        return module
    except BaseException as exc:
        sys.modules.pop(MODULE, None)
        if isinstance(exc, Exception):
            raise ValueError("pending_claim_runtime_load_failed:" + type(exc).__name__) from exc
        raise


def load_runtime(repo_root, spec_path, state_dir, record, native):
    """Return a verified Native module and its source/config custody binding."""
    root, spec_path, state = map(_canonical, (repo_root, spec_path, state_dir))
    info = state.stat()
    _need(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
          "pending_claim_runtime_private_state_required")
    actual = _canonical(Path(native.__file__))
    suffix = "ipfs_accelerate_py/agent_supervisor/todo_daemon/implementation_daemon.py"
    _need(str(actual).endswith("/" + suffix), "pending_claim_runtime_native_origin_unverified")
    runtime_root = actual.parents[3]
    parent = importlib.import_module(MODULE.rsplit(".", 1)[0])
    _need(_canonical(Path(parent.__file__)).parent == actual.parent
          and list(parent.__path__) == [str(actual.parent)], "pending_claim_runtime_package_origin_changed")
    runtime_commit = _git(runtime_root, "rev-parse", "HEAD").decode().strip()
    _, native_raw, _ = _source(runtime_root, runtime_commit, suffix)
    native_sources = {native.__name__: {"path": str(actual), "sha256": _sha(native_raw), "commit": runtime_commit}}
    for name in (".current_incident_adjudication", ".portal_task_state_control_plane",
                 "..merge.worktree_lifecycle", "..merge.checkout_lock", "..merge.merge_queue",
                 "..merge.workspace_quarantine", "..runtime.grok_cli_runner"):
        support = importlib.import_module(name, MODULE.rsplit(".", 1)[0])
        support_path = _canonical(Path(support.__file__))
        _need(support_path.is_relative_to(runtime_root), "pending_claim_runtime_support_origin_changed")
        _, support_raw, _ = _source(runtime_root, runtime_commit, support_path.relative_to(runtime_root).as_posix())
        native_sources[support.__name__] = {"path": str(support_path), "sha256": _sha(support_raw), "commit": runtime_commit}
    config_path = state / CONFIG_NAME
    if os.path.lexists(runtime_root / RELATIVE):
        path, raw, oid = _source(runtime_root, runtime_commit, RELATIVE)
        binding = {"mode": "native", "path": str(path), "sha256": _sha(raw),
                   "commit": runtime_commit, "blob_oid": oid}
    else:
        _need(os.path.lexists(config_path), "pending_claim_runtime_unavailable")
        config_raw = _read(config_path, private=True)
        def unique(pairs):
            value = {}
            for key, item in pairs:
                _need(key not in value, "pending_claim_runtime_duplicate_config_key")
                value[key] = item
            return value
        config = json.loads(config_raw, object_pairs_hook=unique)
        fields = {"schema", "repo_root", "state_dir", "spec_path", "spec_sha256", "plan_id",
                  "plan_path", "plan_sha256", "runtime_sdk_root", "runtime_sdk_commit",
                  "helper_sdk_root", "helper_sdk_commit", "helper_blob_oid", "helper_sha256"}
        _need(type(config) is dict and set(config) == fields and all(type(v) is str for v in config.values())
              and config["schema"] == SCHEMA,
              "pending_claim_runtime_config_shape")
        from .improvement_plan import build_improvement_work_plan, load_spec
        from .campaign import campaign_artifacts
        source_spec = load_spec(spec_path)
        plan_path = root / campaign_artifacts(source_spec).plan_relative
        _need(config["repo_root"] == str(root) and config["state_dir"] == str(state)
              and config["spec_path"] == str(spec_path) and config["spec_sha256"] == _sha(_read(spec_path))
              and config["plan_path"] == str(plan_path) and config["plan_sha256"] == _sha(_read(plan_path))
              and config["plan_id"] == record.get("plan_id") == build_improvement_work_plan(source_spec).plan_id,
              "pending_claim_runtime_campaign_binding_changed")
        _need(config["runtime_sdk_root"] == str(runtime_root)
              and config["runtime_sdk_commit"] == runtime_commit,
              "pending_claim_runtime_native_binding_changed")
        path, raw, oid = _source(Path(config["helper_sdk_root"]), config["helper_sdk_commit"], RELATIVE)
        _need(config["helper_blob_oid"] == oid and config["helper_sha256"] == _sha(raw),
              "pending_claim_runtime_helper_digest_changed")
        binding = {"mode": "pinned_companion", "path": str(path), "sha256": _sha(raw),
                   "commit": config["helper_sdk_commit"], "blob_oid": oid,
                   "config_sha256": _sha(config_raw)}
    binding["native_sources"] = native_sources
    module = _verified_module(path, raw, native_facade=binding["mode"] == "native")
    return module, binding


def reconcile_pending_claim(repo_root, spec_path, state_dir, record, native, daemon, task_id):
    """Use the SDK API under caller-held campaign/checkout/queue guards."""
    from .improvement_runner import _read_native_state
    try:
        module, binding = load_runtime(repo_root, spec_path, state_dir, record, native)
    except ValueError as exc:
        if str(exc) != "pending_claim_runtime_unavailable":
            raise
        return {"reconciled": False, "blocked": True, "reason": str(exc),
                "completion_authority": False, "attempt_refunded": False,
                "provider_callback_settled": False, "new_attempt_authority": False}
    before, source = _read_native_state(repo_root, daemon.state_path)
    _need(not before.get("read_error") and source.get("source") != "unavailable",
          "pending_claim_runtime_state_unavailable")
    native_facades = binding.get("mode") == "native" and all(callable(getattr(daemon, name, None)) for name in (
        "review_quiesced_pending_task_claim", "reconcile_quiesced_pending_task_claim"))
    request = (daemon.review_quiesced_pending_task_claim(task_id=task_id) if native_facades
               else module.review(daemon, task_id=task_id))
    _, fresh = load_runtime(repo_root, spec_path, state_dir, record, native)
    _need(fresh == binding, "pending_claim_runtime_binding_changed")
    result = (daemon.reconcile_quiesced_pending_task_claim(request=request) if native_facades
              else module.reconcile(daemon, request=request))
    _, final_binding = load_runtime(repo_root, spec_path, state_dir, record, native)
    _need(final_binding == binding, "pending_claim_runtime_binding_changed")
    after, source = _read_native_state(repo_root, daemon.state_path)
    _need(after == before and source.get("source") != "unavailable",
          "pending_claim_runtime_native_state_changed")
    _need(isinstance(result, dict) and result.get("reconciled") is True
          and result.get("blocked") is False and result.get("counters_preserved") is True
          and result.get("task_status_unchanged") is True
          and result.get("reason") in {"quiesced_pending_task_claim_released", "pending_claim_already_released"}
          and all(result.get(key) is False for key in ("completion_authority", "attempt_refunded",
                  "provider_callback_settled", "new_attempt_authority")),
          "pending_claim_runtime_reconciliation_unverified")
    return {**result, "host_runtime_binding": binding}
