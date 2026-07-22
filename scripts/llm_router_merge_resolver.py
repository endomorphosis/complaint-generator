#!/usr/bin/env python3
"""Resolve supervisor merge prompts through complaint-generator's llm_router."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.llm_router.json"


def _run(command: list[str], *, cwd: Path, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def _load_backend_config(config_path: Path, backend_id: str) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    for backend in config.get("BACKENDS", []):
        if backend.get("id") == backend_id:
            if backend.get("type") != "llm_router":
                raise ValueError(f"backend {backend_id!r} is not type llm_router")
            payload = dict(backend)
            payload.pop("type", None)
            return payload
    raise ValueError(f"llm_router backend {backend_id!r} was not found in {config_path}")


def _router_response(prompt: str) -> str:
    from backends import LLMRouterBackend

    config_path = Path(os.environ.get("AGENT_MERGE_LLM_ROUTER_CONFIG", str(DEFAULT_CONFIG_PATH))).resolve()
    backend_id = os.environ.get("AGENT_MERGE_LLM_ROUTER_BACKEND_ID", "llm-router-codex")
    backend_config = _load_backend_config(config_path, backend_id)
    max_tokens = int(os.environ.get("AGENT_MERGE_LLM_ROUTER_MAX_TOKENS", "4096"))
    if max_tokens > int(backend_config.get("max_tokens") or 0):
        backend_config["max_tokens"] = max_tokens
    backend_config.setdefault("temperature", 0)
    backend = LLMRouterBackend(**backend_config)
    return str(backend(_router_prompt(prompt)))


def _router_prompt(prompt: str) -> str:
    return "\n".join(
        [
            "You are resolving a Git merge or dirty-worktree blocker for an autonomous refactor supervisor.",
            "Return either a single unified diff that can be applied with git apply, or JSON with an 'explanation' field only if no safe patch is possible.",
            "Do not include markdown fences. Do not include shell commands.",
            "The patch must remove conflict markers, preserve both sides where semantically compatible, and keep changes scoped.",
            "If the prompt describes only dirty generated supervisor outputs, prefer leaving that to the supervisor auto-commit repair and return JSON explaining no semantic patch is needed.",
            "",
            prompt,
        ]
    )


def _extract_unified_diff(text: str) -> str:
    stripped = text.strip()
    fence = re.search(r"```(?:diff|patch)?\s*(.*?)```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        stripped = fence.group(1).strip()
    start = stripped.find("diff --git ")
    if start < 0:
        start = stripped.find("--- ")
    return stripped[start:].strip() if start >= 0 else ""


def _unmerged_paths(workspace: Path) -> list[str]:
    result = _run(["git", "diff", "--name-only", "--diff-filter=U"], cwd=workspace)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _files_with_conflict_markers(workspace: Path) -> list[str]:
    result = _run(["git", "grep", "-n", r"^<<<<<<< "], cwd=workspace)
    if result.returncode not in (0, 1):
        return []
    paths: list[str] = []
    for line in result.stdout.splitlines():
        path = line.split(":", 1)[0].strip()
        if path and path not in paths:
            paths.append(path)
    return paths


def _patch_paths(diff: str) -> list[str]:
    paths: list[str] = []
    for line in diff.splitlines():
        if not line.startswith("diff --git "):
            continue
        try:
            parts = shlex.split(line)
        except ValueError:
            continue
        for value in parts[2:4]:
            path = value[2:] if value.startswith(("a/", "b/")) else value
            if path and path != "/dev/null" and path not in paths:
                paths.append(path)
    return paths


def _merge_in_progress(workspace: Path) -> bool:
    result = _run(["git", "rev-parse", "--git-path", "MERGE_HEAD"], cwd=workspace)
    if result.returncode != 0 or not result.stdout.strip():
        return False
    merge_head = Path(result.stdout.strip())
    if not merge_head.is_absolute():
        merge_head = workspace / merge_head
    return merge_head.exists()


def _stage_and_commit_if_resolved(workspace: Path, *, paths_to_stage: list[str]) -> bool:
    if _unmerged_paths(workspace) or _files_with_conflict_markers(workspace):
        return False
    paths = list(dict.fromkeys(path for path in paths_to_stage if path))
    if not paths:
        return False
    add = _run(["git", "add", "-A", "--", *paths], cwd=workspace)
    if add.returncode != 0:
        print(add.stderr[-2000:], file=sys.stderr)
        return False
    diff_cached = _run(["git", "diff", "--cached", "--quiet"], cwd=workspace)
    if diff_cached.returncode == 0:
        return True
    subject = os.environ.get("AGENT_MERGE_LLM_ROUTER_COMMIT_SUBJECT", "Agent: resolve supervisor merge conflict")
    commit = _run(["git", "commit", "-m", subject], cwd=workspace)
    if commit.returncode != 0:
        print(commit.stderr[-4000:], file=sys.stderr)
        return False
    return True


def _fallback(prompt: str, workspace: Path) -> int:
    accelerate_repo = PROJECT_ROOT / "ipfs_datasets_py" / "ipfs_accelerate_py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(accelerate_repo) + os.pathsep + str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    command = [
        sys.executable,
        "-m",
        "ipfs_accelerate_py.agent_supervisor.llm_merge_resolver_fallback",
        str(workspace),
    ]
    result = subprocess.run(command, cwd=workspace, input=prompt, text=True, env=env, check=False)
    return int(result.returncode)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    workspace = Path(args[0] if args else os.environ.get("IPFS_ACCELERATE_AGENT_MERGE_WORKSPACE", os.getcwd())).resolve()
    prompt = sys.stdin.read()
    initial_conflict_paths = list(
        dict.fromkeys([*_unmerged_paths(workspace), *_files_with_conflict_markers(workspace)])
    )
    merge_was_in_progress = _merge_in_progress(workspace)
    try:
        response = _router_response(prompt)
    except Exception as exc:
        print(f"llm_router merge resolver unavailable: {exc}; falling back", file=sys.stderr)
        return _fallback(prompt, workspace)

    diff = _extract_unified_diff(response)
    diff_applied = False
    if diff:
        check = _run(["git", "apply", "--check", "-"], cwd=workspace, input_text=diff)
        if check.returncode == 0:
            apply = _run(["git", "apply", "-"], cwd=workspace, input_text=diff)
            if apply.returncode != 0:
                print(apply.stderr[-4000:], file=sys.stderr)
            else:
                diff_applied = True
        else:
            print(check.stderr[-4000:], file=sys.stderr)

    stage_paths = list(initial_conflict_paths)
    if diff_applied:
        stage_paths.extend(_patch_paths(diff))
    if (merge_was_in_progress or diff_applied) and _stage_and_commit_if_resolved(
        workspace,
        paths_to_stage=stage_paths,
    ):
        return 0

    print("llm_router response did not fully resolve the worktree; falling back to tool-backed resolver", file=sys.stderr)
    return _fallback(prompt + "\n\nllm_router guidance:\n" + response, workspace)


if __name__ == "__main__":
    raise SystemExit(main())
