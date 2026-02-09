import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Allow running via: python examples/codex_multi_run_autopatch.py
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from adversarial_harness import AdversarialHarness, Optimizer
from backends import LLMRouterBackend
from mediator import Mediator


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_config(path: str) -> Dict[str, Any]:
    return _load_json(path)


def _get_llm_router_backend_config(config: Dict[str, Any], backend_id: str | None) -> Dict[str, Any]:
    backend_ids = config.get("MEDIATOR", {}).get("backends", [])
    if not backend_id:
        backend_id = backend_ids[0] if backend_ids else None
    if not backend_id:
        raise ValueError("No backend id specified and config.MEDIATOR.backends is empty")

    backends = config.get("BACKENDS", [])
    backend_config = next((b for b in backends if b.get("id") == backend_id), None)
    if not backend_config:
        raise ValueError(f"Backend id not found in config.BACKENDS: {backend_id}")
    if backend_config.get("type") != "llm_router":
        raise ValueError(f"Backend {backend_id} must have type 'llm_router'")

    backend_kwargs = dict(backend_config)
    backend_kwargs.pop("type", None)
    return backend_kwargs


def _load_session_sgd_report_module():
    path = os.path.join(PROJECT_ROOT, "examples", "session_sgd_report.py")
    spec = importlib.util.spec_from_file_location("session_sgd_report", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Unable to load session_sgd_report.py from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


_sgd = _load_session_sgd_report_module()
_find_session_json_files = _sgd._find_session_json_files
_summarize_session = _sgd._summarize_session
_write_report = _sgd._write_report


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _run_batch_and_persist(
    *,
    config_path: str,
    backend_id: str,
    state_dir: str,
    run_id: str,
    num_sessions: int,
    max_turns: int,
    max_parallel: int,
    personalities: Optional[List[str]],
    retry_max_attempts: int,
    retry_backoff_base_s: float,
    retry_backoff_max_s: float,
    retry_jitter_s: float,
) -> str:
    config = _load_config(config_path)
    backend_kwargs = _get_llm_router_backend_config(config, backend_id)

    run_dir = os.path.join(state_dir, "_runs", run_id)
    _ensure_dir(run_dir)

    # Retry/backoff settings are passed through as kwargs.
    backend_kwargs = {
        **backend_kwargs,
        "retry_max_attempts": retry_max_attempts,
        "retry_backoff_base_s": retry_backoff_base_s,
        "retry_backoff_max_s": retry_backoff_max_s,
        "retry_jitter_s": retry_jitter_s,
    }

    llm_backend_complainant = LLMRouterBackend(**backend_kwargs)
    llm_backend_critic = LLMRouterBackend(**backend_kwargs)

    def mediator_factory(**kwargs) -> Mediator:
        return Mediator(backends=[LLMRouterBackend(**backend_kwargs)], **kwargs)

    harness = AdversarialHarness(
        llm_backend_complainant=llm_backend_complainant,
        llm_backend_critic=llm_backend_critic,
        mediator_factory=mediator_factory,
        max_parallel=max_parallel,
        session_state_dir=run_dir,
    )

    start = time.time()
    results = harness.run_batch(
        num_sessions=num_sessions,
        max_turns_per_session=max_turns,
        personalities=personalities,
    )
    duration_s = time.time() - start

    opt_report = Optimizer().analyze(results)

    session_json_files = _find_session_json_files(run_dir)
    summaries = [_summarize_session(p) for p in session_json_files]
    sgd_report_path = _write_report(run_dir, os.path.join(run_dir, "_reports"), summaries)

    payload = {
        "run_id": run_id,
        "run_dir": os.path.abspath(run_dir),
        "config": {
            "backend_id": backend_id,
            "num_sessions": num_sessions,
            "max_turns": max_turns,
            "max_parallel": max_parallel,
            "personalities": personalities,
            "retry_max_attempts": retry_max_attempts,
            "retry_backoff_base_s": retry_backoff_base_s,
            "retry_backoff_max_s": retry_backoff_max_s,
            "retry_jitter_s": retry_jitter_s,
        },
        "timing": {
            "batch_duration_seconds": duration_s,
        },
        "optimizer_report": opt_report.to_dict(),
        "sgd_report_path": os.path.abspath(sgd_report_path),
        "retry_stats": {
            "complainant": llm_backend_complainant.get_retry_stats(),
            "critic": llm_backend_critic.get_retry_stats(),
        },
    }

    out_path = os.path.join(run_dir, "cycle_summary.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return run_dir


def _generate_codex_patch_for_run(
    *,
    python_exe: str,
    run_dir: str,
    config_path: str,
    backend_id: str,
) -> str:
    cmd = [
        python_exe,
        os.path.join(PROJECT_ROOT, "examples", "codex_autopatch_from_run.py"),
        "--config",
        config_path,
        "--backend-id",
        backend_id,
        "--run-dir",
        run_dir,
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"codex_autopatch_from_run failed (exit={proc.returncode}):\n{proc.stdout}")
    out = (proc.stdout or "").strip().splitlines()
    patch_path = out[-1].strip() if out else ""
    if not patch_path or not os.path.isfile(patch_path):
        raise RuntimeError(f"codex_autopatch_from_run did not output a valid patch path. Output:\n{proc.stdout}")
    return patch_path


@dataclass
class PatchApplyError(Exception):
    message: str
    file_path: Optional[str] = None
    hunk_index: Optional[int] = None

    def __str__(self) -> str:
        msg = self.message or ""
        extra: List[str] = []
        if self.file_path:
            extra.append(f"file={self.file_path}")
        if self.hunk_index is not None:
            extra.append(f"hunk={self.hunk_index}")
        if extra:
            return f"{msg} ({', '.join(extra)})".strip()
        return msg


def _normalize_patch_text(text: str) -> str:
    """Normalize common Codex near-miss formats into apply_patch text."""
    text = (text or "").strip()
    if not text:
        return text

    # Drop fenced blocks like ```diff ... ```
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:] if lines else []
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Normalize Begin Patch -> *** Begin Patch
    if text.startswith("Begin Patch"):
        text = "*** " + text

    # Normalize missing space: ***Begin Patch
    if text.startswith("***Begin Patch"):
        text = text.replace("***Begin Patch", "*** Begin Patch", 1)

    return text


def _parse_apply_patch(text: str) -> List[Tuple[str, List[List[str]]]]:
    """Parse apply_patch formatted text into [(file_path, [hunk_lines...])]."""
    text = _normalize_patch_text(text)
    lines = text.splitlines()
    # tolerate leading/trailing whitespace
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    if not lines or lines[0].strip() != "*** Begin Patch" or lines[-1].strip() != "*** End Patch":
        raise PatchApplyError("Not in apply_patch format")

    # Detect a common model formatting issue: every line is prefixed with exactly one extra space.
    # If present anywhere in the patch, we treat it as global for all hunks.
    global_prefix_hint = False
    for ln in lines:
        if ln.startswith("*** ") or ln.startswith("@@"):
            continue
        if ln.startswith(("+", "-")):
            if len(ln) >= 3 and ln[1] == " " and ln[2] != " ":
                global_prefix_hint = True
                break
        if ln.startswith(" ") and (len(ln) == 1 or ln[1] != " "):
            global_prefix_hint = True
            break

    i = 1
    file_blocks: List[Tuple[str, List[List[str]]]] = []
    current_file: Optional[str] = None
    current_hunks: List[List[str]] = []
    current_hunk: Optional[List[str]] = None

    def normalize_hunk_lines(raw_lines: List[str]) -> List[str]:
        # If the model prefixed *every* patch line with one extra space, we'll see patterns like:
        #  ' import logging' or '- import logging' or '+ import logging'
        # In that case we need to strip one leading space (or one space after +/-) on *all* lines,
        # including indented lines.
        strip_global_prefix = global_prefix_hint or any(
            (
                (ln.startswith(("+ ", "- ")) and len(ln) >= 3 and ln[2] != " ")
                or (ln.startswith(" ") and (len(ln) == 1 or ln[1] != " "))
            )
            for ln in raw_lines
        )

        def leading_space_count(s: str) -> int:
            n = 0
            for ch in s:
                if ch == " ":
                    n += 1
                else:
                    break
            return n

        out: List[str] = []
        for ln in raw_lines:
            if not strip_global_prefix:
                out.append(ln)
                continue

            if ln.startswith(("+", "-")) and len(ln) > 1 and ln[1] == " ":
                spaces = leading_space_count(ln[1:])
                # If indentation after +/- is off-by-one relative to 4-space blocks, strip one.
                if spaces % 4 == 1:
                    out.append(ln[0] + ln[2:])
                else:
                    out.append(ln)
                continue

            if ln.startswith(" "):
                spaces = leading_space_count(ln)
                if spaces % 4 == 1:
                    out.append(ln[1:])
                else:
                    out.append(ln)
                continue

            out.append(ln)

        return out

    def flush_file():
        nonlocal current_file, current_hunks, current_hunk
        if current_file is None:
            return
        if current_hunk is not None and current_hunk:
            current_hunks.append(normalize_hunk_lines(current_hunk))
        file_blocks.append((current_file, current_hunks))
        current_file = None
        current_hunks = []
        current_hunk = None

    while i < len(lines) - 1:
        line = lines[i]
        if line.startswith("*** Update File:"):
            flush_file()
            current_file = line.split(":", 1)[1].strip()
            current_hunks = []
            current_hunk = None
            i += 1
            continue
        if line.startswith("*** Add File:") or line.startswith("*** Delete File:"):
            raise PatchApplyError("Only '*** Update File' patches are supported by this script")
        if line.startswith("@@"):
            if current_file is None:
                i += 1
                continue
            if current_hunk is not None and current_hunk:
                current_hunks.append(normalize_hunk_lines(current_hunk))
            current_hunk = []
            i += 1
            continue

        # normal patch/content line
        if current_file is not None:
            if current_hunk is None:
                current_hunk = []
            # skip purely blank separators between hunks
            current_hunk.append(line)
        i += 1

    flush_file()
    if not file_blocks:
        raise PatchApplyError("No file blocks found")
    return file_blocks


def _find_subsequence(haystack: Sequence[str], needle: Sequence[str], start_at: int = 0) -> Optional[int]:
    if not needle:
        return None
    max_i = len(haystack) - len(needle)
    for i in range(start_at, max_i + 1):
        if list(haystack[i : i + len(needle)]) == list(needle):
            return i
    return None


def _find_subsequence_rstrip(haystack: Sequence[str], needle: Sequence[str], start_at: int = 0) -> Optional[int]:
    """Fallback matching that ignores trailing whitespace differences."""
    if not needle:
        return None
    hay = [h.rstrip() for h in haystack]
    ned = [n.rstrip() for n in needle]
    max_i = len(hay) - len(ned)
    for i in range(start_at, max_i + 1):
        if hay[i : i + len(ned)] == ned:
            return i
    return None


def _apply_hunk_to_lines(file_lines: List[str], hunk_lines: List[str]) -> List[str]:
    old_block: List[str] = []
    new_block: List[str] = []

    for raw in hunk_lines:
        if raw.startswith("-"):
            old_block.append(raw[1:])
        elif raw.startswith("+"):
            new_block.append(raw[1:])
        else:
            old_block.append(raw)
            new_block.append(raw)

    pos = _find_subsequence(file_lines, old_block)
    if pos is None:
        pos = _find_subsequence_rstrip(file_lines, old_block)
    if pos is None:
        raise PatchApplyError("Hunk context not found")

    return file_lines[:pos] + new_block + file_lines[pos + len(old_block) :]


def _dry_run_apply_patch_text(patch_text: str) -> None:
    """Validate that a patch can apply cleanly to current working tree.

    Raises PatchApplyError if it cannot be applied.
    """
    patch_text = _normalize_patch_text(patch_text)
    file_blocks = _parse_apply_patch(patch_text)

    for file_path, hunks in file_blocks:
        if not os.path.isabs(file_path):
            raise PatchApplyError("Patch paths must be absolute", file_path=file_path)
        if not os.path.isfile(file_path):
            raise PatchApplyError("Target file does not exist", file_path=file_path)

        with open(file_path, "r", encoding="utf-8") as f:
            file_lines = f.read().splitlines()

        for hunk_index, hunk_lines in enumerate(hunks):
            try:
                file_lines = _apply_hunk_to_lines(file_lines, hunk_lines)
            except PatchApplyError as e:
                raise PatchApplyError(e.message, file_path=file_path, hunk_index=hunk_index) from e


def apply_apply_patch_text(patch_text: str) -> List[str]:
    """Apply an apply_patch formatted patch to the working tree.

    Returns list of updated file paths.
    """
    patch_text = _normalize_patch_text(patch_text)
    file_blocks = _parse_apply_patch(patch_text)
    updated_files: List[str] = []

    for file_path, hunks in file_blocks:
        if not os.path.isabs(file_path):
            raise PatchApplyError("Patch paths must be absolute", file_path=file_path)
        if not os.path.isfile(file_path):
            raise PatchApplyError("Target file does not exist", file_path=file_path)

        with open(file_path, "r", encoding="utf-8") as f:
            file_lines = f.read().splitlines()

        for hunk_index, hunk_lines in enumerate(hunks):
            try:
                file_lines = _apply_hunk_to_lines(file_lines, hunk_lines)
            except PatchApplyError as e:
                raise PatchApplyError(e.message, file_path=file_path, hunk_index=hunk_index) from e

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(file_lines) + "\n")

        updated_files.append(file_path)

    return updated_files


def _extract_update_files(patch_text: str) -> List[str]:
    files: List[str] = []
    for line in patch_text.splitlines():
        if line.startswith("*** Update File:"):
            files.append(line.split(":", 1)[1].strip())
    return files


def _codex_fix_patch(
    *,
    codex_backend: LLMRouterBackend,
    failing_patch_text: str,
    error_message: str,
    file_contents: Dict[str, str],
) -> str:
    context = {
        "error": error_message,
        "files": {path: contents for path, contents in file_contents.items()},
        "previous_patch": failing_patch_text,
    }

    prompt = (
        "You are Codex CLI. You must output ONLY an apply_patch formatted patch.\n\n"
        "Task: Fix the patch so it applies cleanly to the CURRENT file contents provided.\n"
        "Rules:\n"
        "- Output MUST start with: *** Begin Patch\n"
        "- Output MUST end with: *** End Patch\n"
        "- Use only: *** Update File: <absolute path>\n"
        "- Do not use placeholder paths or template lines.\n"
        "- Keep the change minimal; preserve intent of the previous patch.\n\n"
        "Patch quality requirements:\n"
        "- Do not truncate or corrupt lines (no partial tokens).\n"
        "- Ensure every changed region includes enough exact context lines to apply.\n"
        "- Keep hunks small and focused; avoid huge hunks spanning multiple functions.\n\n"
        "Here is the failure context as JSON (includes current file contents):\n"
        + json.dumps(context, ensure_ascii=False)
    )

    fixed = codex_backend(prompt)
    return _normalize_patch_text(str(fixed))


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run multiple adversarial batches, generate Codex patches per run, then apply all patches with auto-fix retries"
        )
    )
    parser.add_argument("--config", default="config.llm_router.json")
    parser.add_argument("--state-dir", default="statefiles")
    parser.add_argument("--batch-backend-id", default=None, help="Backend id for running sessions (defaults to config.MEDIATOR.backends[0])")
    parser.add_argument("--codex-backend-id", default="llm-router-codex")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--sessions-per-run", type=int, default=10)
    parser.add_argument("--max-turns", type=int, default=8)
    parser.add_argument("--max-parallel", type=int, default=2)
    parser.add_argument("--personalities", default=None)

    parser.add_argument("--retry-max-attempts", type=int, default=1)
    parser.add_argument("--retry-backoff-base-s", type=float, default=0.5)
    parser.add_argument("--retry-backoff-max-s", type=float, default=20.0)
    parser.add_argument("--retry-jitter-s", type=float, default=0.1)

    parser.add_argument("--apply-fix-max-attempts", type=int, default=2)
    parser.add_argument(
        "--generate-fix-max-attempts",
        type=int,
        default=2,
        help="If Codex generates a patch that can't apply to the current tree, ask Codex to fix it up to this many times.",
    )
    args = parser.parse_args()

    personalities = None
    if args.personalities:
        personalities = [p.strip() for p in args.personalities.split(",") if p.strip()]

    config = _load_config(args.config)
    batch_backend_id = args.batch_backend_id
    if not batch_backend_id:
        backend_ids = config.get("MEDIATOR", {}).get("backends", [])
        batch_backend_id = backend_ids[0] if backend_ids else None
    if not batch_backend_id:
        raise SystemExit("No batch backend id available")

    orchestrator_id = f"autopatch_{_utc_stamp()}"
    orchestrator_dir = os.path.join(args.state_dir, "_runs", orchestrator_id)
    _ensure_dir(orchestrator_dir)

    patches_dir = os.path.join(orchestrator_dir, "patches")
    fixed_dir = os.path.join(orchestrator_dir, "patches_fixed")
    _ensure_dir(patches_dir)
    _ensure_dir(fixed_dir)

    python_exe = sys.executable

    # Codex backend used for patch-fix retries (uses llm-router config for codex backend).
    codex_backend_kwargs = _get_llm_router_backend_config(config, args.codex_backend_id)
    codex_backend = LLMRouterBackend(**codex_backend_kwargs)

    run_records: List[Dict[str, Any]] = []

    for i in range(args.runs):
        run_id = f"{orchestrator_id}_run_{i:02d}"
        print(f"[batch] {i+1}/{args.runs} run_id={run_id}")
        run_dir = _run_batch_and_persist(
            config_path=args.config,
            backend_id=batch_backend_id,
            state_dir=args.state_dir,
            run_id=run_id,
            num_sessions=args.sessions_per_run,
            max_turns=args.max_turns,
            max_parallel=args.max_parallel,
            personalities=personalities,
            retry_max_attempts=args.retry_max_attempts,
            retry_backoff_base_s=args.retry_backoff_base_s,
            retry_backoff_max_s=args.retry_backoff_max_s,
            retry_jitter_s=args.retry_jitter_s,
        )

        patch_path = _generate_codex_patch_for_run(
            python_exe=python_exe,
            run_dir=run_dir,
            config_path=args.config,
            backend_id=args.codex_backend_id,
        )
        patch_text = _read_text(patch_path)
        patch_text = _normalize_patch_text(patch_text)

        # Validate (dry-run apply) immediately; if Codex produced a broken patch, repair it now.
        gen_attempt = 0
        while True:
            gen_attempt += 1
            try:
                _dry_run_apply_patch_text(patch_text)
                break
            except PatchApplyError as e:
                if gen_attempt > args.generate_fix_max_attempts:
                    raise SystemExit(
                        f"Generated patch for run {run_id} could not be applied after fixes: {e}"
                    )

                update_files = _extract_update_files(patch_text)
                file_contents: Dict[str, str] = {}
                for fp in update_files:
                    if os.path.isfile(fp):
                        file_contents[fp] = _read_text(fp)

                patch_text = _codex_fix_patch(
                    codex_backend=codex_backend,
                    failing_patch_text=patch_text,
                    error_message=f"Generated patch failed dry-run apply: {e}",
                    file_contents=file_contents,
                )

        # Copy patch into orchestrator folder for later application
        # Ensure directories exist even if state_dir is changed mid-run.
        _ensure_dir(patches_dir)
        local_patch_path = os.path.join(patches_dir, f"patch_{i:02d}.patch")
        with open(local_patch_path, "w", encoding="utf-8") as f:
            f.write(patch_text)

        run_records.append(
            {
                "i": i,
                "run_id": run_id,
                "run_dir": os.path.abspath(run_dir),
                "patch_path": os.path.abspath(local_patch_path),
            }
        )

    print(f"[apply] applying {len(run_records)} patches")

    applied: List[Dict[str, Any]] = []
    for rec in run_records:
        patch_path = rec["patch_path"]
        patch_text = _read_text(patch_path)

        attempt = 0
        while True:
            attempt += 1
            try:
                updated = apply_apply_patch_text(patch_text)
                applied.append(
                    {
                        "patch_path": patch_path,
                        "attempt": attempt,
                        "updated_files": updated,
                        "fixed": attempt > 1,
                    }
                )
                print(f"[apply] ok patch={os.path.basename(patch_path)} updated={len(updated)}")
                break
            except PatchApplyError as e:
                if attempt > args.apply_fix_max_attempts + 1:
                    applied.append(
                        {
                            "patch_path": patch_path,
                            "attempt": attempt,
                            "error": str(e),
                            "fixed": True,
                            "failed": True,
                        }
                    )
                    print(f"[apply] FAIL patch={os.path.basename(patch_path)} error={e}")
                    break

                # Ask Codex to fix patch based on current contents of impacted files.
                update_files = _extract_update_files(patch_text)
                file_contents: Dict[str, str] = {}
                for fp in update_files:
                    if os.path.isfile(fp):
                        file_contents[fp] = _read_text(fp)

                fixed_patch_text = _codex_fix_patch(
                    codex_backend=codex_backend,
                    failing_patch_text=patch_text,
                    error_message=str(e),
                    file_contents=file_contents,
                )

                fixed_out_path = os.path.join(
                    fixed_dir,
                    f"fixed_{os.path.basename(patch_path).replace('.patch','')}_attempt_{attempt}.patch",
                )
                with open(fixed_out_path, "w", encoding="utf-8") as f:
                    f.write(fixed_patch_text)

                patch_text = fixed_patch_text

    print("[test] running pytest -q")
    test_proc = subprocess.run(
        [python_exe, "-m", "pytest", "-q"],
        cwd=PROJECT_ROOT,
    )

    summary = {
        "orchestrator_id": orchestrator_id,
        "orchestrator_dir": os.path.abspath(orchestrator_dir),
        "config": {
            "batch_backend_id": batch_backend_id,
            "codex_backend_id": args.codex_backend_id,
            "runs": args.runs,
            "sessions_per_run": args.sessions_per_run,
            "max_turns": args.max_turns,
            "max_parallel": args.max_parallel,
            "personalities": personalities,
            "apply_fix_max_attempts": args.apply_fix_max_attempts,
        },
        "runs": run_records,
        "applied": applied,
        "tests": {
            "exit_code": test_proc.returncode,
        },
    }

    summary_path = os.path.join(orchestrator_dir, "autopatch_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"[done] summary={summary_path}")
    return int(test_proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
