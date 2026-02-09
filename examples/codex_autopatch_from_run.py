import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

# Allow running via: python examples/codex_autopatch_from_run.py
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backends import LLMRouterBackend


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


def _find_session_jsons(run_dir: str) -> List[str]:
    out: List[str] = []
    if not os.path.isdir(run_dir):
        return out
    for name in os.listdir(run_dir):
        if not name.startswith("session_"):
            continue
        p = os.path.join(run_dir, name, "session.json")
        if os.path.isfile(p):
            out.append(p)
    return sorted(out)


def _session_brief(doc: Dict[str, Any]) -> Dict[str, Any]:
    critic = doc.get("critic_score") or {}
    art = doc.get("artifacts") or {}
    return {
        "session_id": doc.get("session_id"),
        "success": doc.get("success"),
        "num_turns": doc.get("num_turns"),
        "overall_score": critic.get("overall_score"),
        "feedback": critic.get("feedback"),
        "artifacts": {
            "knowledge_graph_json": art.get("knowledge_graph_json"),
            "dependency_graph_json": art.get("dependency_graph_json"),
            "evidence_duckdb_exists": art.get("evidence_duckdb_exists"),
            "legal_authorities_duckdb_exists": art.get("legal_authorities_duckdb_exists"),
        },
    }


def _pick_worst_sessions(session_docs: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    def key(d: Dict[str, Any]) -> float:
        try:
            critic = d.get("critic_score") or {}
            v = critic.get("overall_score")
            return float(v) if v is not None else 1e9
        except Exception:
            return 1e9

    sorted_docs = sorted(session_docs, key=key)
    return sorted_docs[: max(0, int(k))]


def _build_prompt(
    *,
    run_dir: str,
    cycle_summary: Dict[str, Any],
    sgd_report: Dict[str, Any],
    worst_sessions: List[Dict[str, Any]],
) -> str:
    optimizer = cycle_summary.get("optimizer_report") or {}
    priority = optimizer.get("priority_improvements") or []
    recs = (sgd_report.get("recommendations") or [])[:10]

    worst_briefs = [_session_brief(d) for d in worst_sessions]

    # We include the key snippet that likely causes repetition.
    session_snippet_path = os.path.join(PROJECT_ROOT, "adversarial_harness", "session.py")
    try:
        with open(session_snippet_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        # Grab the question selection section if possible.
        snippet = "\n".join(lines[90:170])
    except Exception:
        snippet = "(unable to load adversarial_harness/session.py snippet)"

    abs_session_path = os.path.abspath(session_snippet_path)

    return f"""You are Codex CLI.

You must output a REAL patch in apply_patch format, not a template.

Target file to change (absolute path):
- {abs_session_path}

Context:
- We just ran an adversarial harness batch from: {os.path.abspath(run_dir)}
- The critic repeatedly notes the mediator asks the same question multiple times.
- Priority improvements from optimizer: {json.dumps(priority, ensure_ascii=False)}
- SGD recommendations: {json.dumps(recs, ensure_ascii=False)}
- Worst session briefs (from this run):\n{json.dumps(worst_briefs, ensure_ascii=False, indent=2)}

Goal:
- Reduce repeated identical mediator questions in adversarial sessions (improve efficiency + info extraction).
- Keep changes minimal and localized.
- Do NOT add dependencies.
- Ensure existing tests keep passing.

Implementation constraints:
- Only modify Python files.
- Prefer changing adversarial harness behavior (e.g., question selection logic) rather than core mediator logic.

Output requirements:
- Output MUST start with the exact line: *** Begin Patch
- Use the exact absolute file path shown above in the *** Update File line.
- Patch MUST include a non-trivial change (not placeholders like /abs/path/to/file.py or 'old'/'new').
- Output MUST end with the exact line: *** End Patch
- No markdown fences. No extra commentary.

Helpful code snippet from adversarial_harness/session.py (current):
{snippet}

Now produce the patch."""


def _looks_like_apply_patch(text: str) -> bool:
    text = text.strip("\n")
    return text.startswith("*** Begin Patch") and text.endswith("*** End Patch") and "*** Update File:" in text


def _normalize_patch_text(text: str) -> str:
    """Normalize common near-miss formats into apply_patch text."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop opening fence line
        if lines:
            lines = lines[1:]
        # Drop closing fence line if present
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    if text.startswith("Begin Patch"):
        text = "*** " + text

    # Some outputs omit the space: "***Begin Patch"
    if text.startswith("***Begin Patch"):
        text = text.replace("***Begin Patch", "*** Begin Patch", 1)

    return text


def _reprompt_for_real_patch(*, previous_output: str, original_prompt: str) -> str:
    return (
        original_prompt
        + "\n\n"
        + "Your previous output was invalid (not a real apply_patch patch)."
        + " Specifically: it must start with the exact line '*** Begin Patch' (3 asterisks)."
        + "\nHere is what you output last time:\n"
        + previous_output
        + "\n\nReturn ONLY a corrected apply_patch patch."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Use Codex CLI via llm-router to propose an apply_patch patch from a persisted run"
    )
    parser.add_argument("--config", default="config.llm_router.json")
    parser.add_argument("--backend-id", default="llm-router-codex")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--max-worst-sessions", type=int, default=3)
    args = parser.parse_args()

    run_dir = args.run_dir
    cycle_summary_path = os.path.join(run_dir, "cycle_summary.json")
    if not os.path.isfile(cycle_summary_path):
        raise SystemExit(f"Missing cycle_summary.json: {cycle_summary_path}")

    cycle_summary = _load_json(cycle_summary_path)
    sgd_report_path = cycle_summary.get("sgd_report_path")
    if not sgd_report_path or not os.path.isfile(sgd_report_path):
        raise SystemExit(
            f"Missing sgd_report_path from cycle_summary or file not found: {sgd_report_path}"
        )
    sgd_report = _load_json(sgd_report_path)

    session_jsons = _find_session_jsons(run_dir)
    session_docs = [_load_json(p) for p in session_jsons]
    worst = _pick_worst_sessions(session_docs, args.max_worst_sessions)

    config = _load_config(args.config)
    backend_kwargs = _get_llm_router_backend_config(config, args.backend_id)
    backend = LLMRouterBackend(**backend_kwargs)

    prompt = _build_prompt(
        run_dir=run_dir,
        cycle_summary=cycle_summary,
        sgd_report=sgd_report,
        worst_sessions=worst,
    )

    patch_text = backend(prompt)
    patch_text = _normalize_patch_text(patch_text)
    if not _looks_like_apply_patch(patch_text):
        patch_text = backend(
            _reprompt_for_real_patch(previous_output=patch_text, original_prompt=prompt)
        )
        patch_text = _normalize_patch_text(patch_text)
    if not _looks_like_apply_patch(patch_text):
        raise SystemExit(
            "Codex did not return a valid apply_patch patch after retry. "
            "See the saved output in your terminal or re-run with a different prompt."
        )

    out_dir = os.path.join(run_dir, "_patches")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(
        out_dir,
        f"codex_patch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.patch",
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(patch_text)

    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
