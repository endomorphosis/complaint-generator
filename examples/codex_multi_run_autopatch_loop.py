import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _run(cmd: list[str], *, cwd: Optional[str] = None, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        text=True,
    )


def _git_has_changes() -> bool:
    proc = _run(["git", "status", "--porcelain"], cwd=PROJECT_ROOT, capture=True)
    return bool((proc.stdout or "").strip())


def _extract_summary_path(output: str) -> Optional[str]:
    lines = (output or "").splitlines()
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("[done] summary="):
            return line.split("=", 1)[1].strip()
    return None


def _load_orchestrator_id(summary_path: str) -> Optional[str]:
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("orchestrator_id")
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Loop: run 10×10 Codex multi-run autopatch repeatedly, and commit local changes after each loop."
        )
    )
    parser.add_argument("--config", default="config.llm_router.json")
    parser.add_argument("--state-dir", default="statefiles")
    parser.add_argument("--batch-backend-id", default=None)
    parser.add_argument("--codex-backend-id", default="llm-router-codex")

    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--sessions-per-run", type=int, default=10)
    parser.add_argument("--max-turns", type=int, default=8)
    parser.add_argument("--max-parallel", type=int, default=2)

    parser.add_argument("--generate-fix-max-attempts", type=int, default=2)
    parser.add_argument("--apply-fix-max-attempts", type=int, default=2)

    parser.add_argument(
        "--loops",
        type=int,
        default=0,
        help="Number of loops to run. 0 means infinite until interrupted.",
    )
    parser.add_argument("--sleep-s", type=float, default=0.0)

    parser.add_argument(
        "--commit",
        action="store_true",
        help="Commit changes after each loop (default).",
    )
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Do not commit changes after each loop.",
    )

    args = parser.parse_args()

    do_commit = True
    if args.commit:
        do_commit = True
    if args.no_commit:
        do_commit = False

    python_exe = sys.executable
    loop_index = 0

    try:
        while True:
            loop_index += 1
            if args.loops and loop_index > args.loops:
                break

            print(f"[loop] {loop_index} starting")

            cmd = [
                python_exe,
                os.path.join(PROJECT_ROOT, "examples", "codex_multi_run_autopatch.py"),
                "--config",
                args.config,
                "--state-dir",
                args.state_dir,
                "--codex-backend-id",
                args.codex_backend_id,
                "--runs",
                str(args.runs),
                "--sessions-per-run",
                str(args.sessions_per_run),
                "--max-turns",
                str(args.max_turns),
                "--max-parallel",
                str(args.max_parallel),
                "--generate-fix-max-attempts",
                str(args.generate_fix_max_attempts),
                "--apply-fix-max-attempts",
                str(args.apply_fix_max_attempts),
                "--undo-on-test-failure",
            ]
            if args.batch_backend_id:
                cmd += ["--batch-backend-id", args.batch_backend_id]

            proc = _run(cmd, cwd=PROJECT_ROOT, capture=True)
            if proc.stdout:
                print(proc.stdout)

            summary_path = _extract_summary_path(proc.stdout or "")
            orchestrator_id = _load_orchestrator_id(summary_path) if summary_path else None

            if proc.returncode != 0:
                print(f"[loop] orchestrator failed exit={proc.returncode}")
                # Do not auto-commit on a failed loop.
            else:
                print(f"[loop] ok orchestrator_id={orchestrator_id or 'unknown'}")

                if do_commit:
                    if _git_has_changes():
                        msg_id = orchestrator_id or _utc_stamp()
                        msg = f"autopatch loop {msg_id}"
                        add = _run(["git", "add", "-A"], cwd=PROJECT_ROOT)
                        if add.returncode != 0:
                            print("[git] add failed")
                        else:
                            commit = _run(["git", "commit", "-m", msg], cwd=PROJECT_ROOT, capture=True)
                            if commit.returncode != 0:
                                out = (commit.stdout or "").strip()
                                print(f"[git] commit failed: {out}")
                            else:
                                print(f"[git] committed: {msg}")
                    else:
                        print("[git] no changes to commit")

            if args.sleep_s > 0:
                time.sleep(args.sleep_s)

    except KeyboardInterrupt:
        print("[loop] interrupted")
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
