import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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

    def _count_kg(path: Any) -> Dict[str, Any]:
        if not isinstance(path, str) or not path or not os.path.isfile(path):
            return {"path": path, "total_entities": None, "total_relationships": None}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entities = data.get("entities") if isinstance(data, dict) else None
            rels = data.get("relationships") if isinstance(data, dict) else None
            return {
                "path": path,
                "total_entities": (len(entities) if isinstance(entities, dict) else None),
                "total_relationships": (len(rels) if isinstance(rels, dict) else None),
            }
        except Exception:
            return {"path": path, "total_entities": None, "total_relationships": None}

    def _count_dg(path: Any) -> Dict[str, Any]:
        if not isinstance(path, str) or not path or not os.path.isfile(path):
            return {"path": path, "total_nodes": None, "total_dependencies": None, "satisfaction_rate": None}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            nodes = data.get("nodes") if isinstance(data, dict) else None
            deps = data.get("dependencies") if isinstance(data, dict) else None
            satisfied = 0
            if isinstance(nodes, dict):
                for n in nodes.values():
                    if isinstance(n, dict) and n.get("satisfied") is True:
                        satisfied += 1
            rate = (satisfied / len(nodes)) if isinstance(nodes, dict) and nodes else (0.0 if isinstance(nodes, dict) else None)
            return {
                "path": path,
                "total_nodes": (len(nodes) if isinstance(nodes, dict) else None),
                "total_dependencies": (len(deps) if isinstance(deps, dict) else None),
                "satisfaction_rate": rate,
            }
        except Exception:
            return {"path": path, "total_nodes": None, "total_dependencies": None, "satisfaction_rate": None}

    kg_path = art.get("knowledge_graph_json")
    dg_path = art.get("dependency_graph_json")
    return {
        "session_id": doc.get("session_id"),
        "success": doc.get("success"),
        "num_turns": doc.get("num_turns"),
        "overall_score": critic.get("overall_score"),
        "feedback": critic.get("feedback"),
        "artifacts": {
            "knowledge_graph": _count_kg(kg_path),
            "dependency_graph": _count_dg(dg_path),
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
    cycle_summary_path: str,
    cycle_summary: Dict[str, Any],
    sgd_report_path: str,
    sgd_report: Dict[str, Any],
    worst_sessions: List[Dict[str, Any]],
    worst_session_json_paths: List[str],
    context_mode: str = "rich",
) -> str:
    optimizer = cycle_summary.get("optimizer_report") or {}
    priority = optimizer.get("priority_improvements") or []
    recs = (sgd_report.get("recommendations") or [])[:10]

    session_snippet_path = os.path.join(PROJECT_ROOT, "adversarial_harness", "session.py")
    abs_session_path = os.path.abspath(session_snippet_path)
    abs_kg_path = os.path.abspath(os.path.join(PROJECT_ROOT, "complaint_phases", "knowledge_graph.py"))
    abs_dg_path = os.path.abspath(os.path.join(PROJECT_ROOT, "complaint_phases", "dependency_graph.py"))
    abs_denoiser_path = os.path.abspath(os.path.join(PROJECT_ROOT, "complaint_phases", "denoiser.py"))
    abs_mediator_path = os.path.abspath(os.path.join(PROJECT_ROOT, "mediator", "mediator.py"))

    optimizer_graph_diag = {
        k: optimizer.get(k)
        for k in [
            "kg_sessions_with_data",
            "dg_sessions_with_data",
            "kg_sessions_empty",
            "dg_sessions_empty",
            "kg_avg_total_entities",
            "kg_avg_total_relationships",
            "kg_avg_gaps",
            "dg_avg_total_nodes",
            "dg_avg_total_dependencies",
            "dg_avg_satisfaction_rate",
        ]
        if k in optimizer
    }
    sgd_graphs = sgd_report.get("graphs") if isinstance(sgd_report, dict) else None
    graphs_health = cycle_summary.get("graphs_health")
    graphs_dynamics_health = cycle_summary.get("graphs_dynamics_health")

    focus: List[str] = []
    try:
        kg_with = int(optimizer.get("kg_sessions_with_data") or 0)
        dg_with = int(optimizer.get("dg_sessions_with_data") or 0)
        kg_empty = int(optimizer.get("kg_sessions_empty") or 0)
        dg_empty = int(optimizer.get("dg_sessions_empty") or 0)
        kg_avg_entities = optimizer.get("kg_avg_total_entities")
        dg_avg_nodes = optimizer.get("dg_avg_total_nodes")
        kg_d_entities = optimizer.get("kg_avg_entities_delta_per_iter")
        kg_d_rels = optimizer.get("kg_avg_relationships_delta_per_iter")
        kg_d_gaps = optimizer.get("kg_avg_gaps_delta_per_iter")
        kg_not_reducing = int(optimizer.get("kg_sessions_gaps_not_reducing") or 0)

        if kg_with > 0 and kg_empty == kg_with:
            focus.append("Knowledge graphs are empty across analyzed sessions")
        elif kg_avg_entities is not None:
            try:
                if float(kg_avg_entities) < 2.0:
                    focus.append("Knowledge graphs are very small on average")
            except Exception:
                pass

        # Dynamics: if gaps aren't shrinking or graphs aren't growing, steer to denoiser answer processing.
        if kg_not_reducing > 0:
            focus.append("Knowledge graph gaps are not reducing across iterations")
        if kg_d_gaps is not None:
            try:
                if float(kg_d_gaps) >= 0.0:
                    focus.append("Knowledge graph gaps are flat/increasing per iteration")
            except Exception:
                pass
        if kg_d_entities is not None:
            try:
                if float(kg_d_entities) < 0.1:
                    focus.append("Knowledge graph is not growing per iteration")
            except Exception:
                pass
        if kg_d_rels is not None:
            try:
                if float(kg_d_rels) < 0.05:
                    focus.append("Knowledge graph relationships are not growing per iteration")
            except Exception:
                pass

        if dg_with > 0 and dg_empty == dg_with:
            focus.append("Dependency graphs are empty across analyzed sessions")
        elif dg_avg_nodes is not None:
            try:
                if float(dg_avg_nodes) < 2.0:
                    focus.append("Dependency graphs are very small on average")
            except Exception:
                pass
    except Exception:
        focus = focus

    suspected_files: List[str] = []
    if any("Knowledge graph" in f for f in focus):
        suspected_files.append(abs_kg_path)
        # When gaps aren't shrinking, the best starting point is answer processing.
        if any("gaps" in f.lower() for f in focus) or any("not growing per iteration" in f for f in focus):
            suspected_files.append(abs_denoiser_path)
    if any("Dependency graph" in f for f in focus):
        suspected_files.append(abs_dg_path)
    if focus:
        suspected_files.append(abs_mediator_path)
    else:
        suspected_files.append(abs_session_path)

    context_mode = (context_mode or "rich").strip().lower()
    if context_mode not in {"rich", "lean"}:
        context_mode = "rich"

    worst_briefs = [_session_brief(d) for d in worst_sessions]

    # We include a helpful snippet (question selection logic) but allow patches across
    # the key files that affect question selection and graph population.
    # In lean mode, omit the snippet to avoid resending ~80 lines of code every step.
    snippet = "(omitted in lean mode)"
    if context_mode == "rich":
        try:
            with open(session_snippet_path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
            # Grab the question selection section if possible.
            snippet = "\n".join(lines[90:170])
        except Exception:
            snippet = "(unable to load adversarial_harness/session.py snippet)"

    # To reduce prompt tokens, lean mode points Codex at the persisted JSON artifacts
    # and relies on tool calls (cat/grep) to pull only what it needs.
    if context_mode == "lean":
        return f"""You are Codex CLI.

Tool-mode is ENABLED. You may take multiple turns by requesting a tool call, then using its result to decide on a better patch.

On each turn, output exactly ONE of the following:

1) A single JSON object requesting a tool:
{{
  "type": "tool",
    "tool": "ls" | "cat" | "grep" | "patch",
  "args": {{ ... }}
}}

2) A single JSON object returning the final patch:
{{
  "type": "final",
  "patch": "*** Begin Patch\n...\n*** End Patch"
}}

3) (Backward compatible) Output a raw apply_patch patch starting with '*** Begin Patch' and ending with '*** End Patch'.

Tool specs (paths must be within the repository root; keep outputs small):
- ls:    args={{"path": "."}}  -> list directory entries
- cat:   args={{"path": "path/to/file.py", "start_line": 1, "end_line": 200}} -> read a line range
- grep:  args={{"pattern": "string or regex", "path": "path/or/dir", "max_matches": 50}} -> search text
- patch: args={{"patch": "*** Begin Patch\\n...\\n*** End Patch"}} -> validate patch formatting + file targets (does NOT apply)

Before returning a final patch (type=final or raw patch), you SHOULD call the patch tool on your candidate patch and fix any errors it reports.

You must output a REAL patch in apply_patch format, not a template.

Patch formatting rules (important):
- Do NOT output unified-diff style prefixes (no leading ' ' marker on unchanged lines).
- Do NOT use '...' or '@@' as an ellipsis to omit lines inside a hunk.
- Each hunk must contain exact, contiguous lines copied from the current file content.
- Use '@@' only to start a new hunk (or include a scope hint like '@@ class Foo'), never as a placeholder.

Scope:
- You MAY change any *.py file under the repository root: {os.path.abspath(PROJECT_ROOT)}
- Use ONLY absolute paths in *** Update File lines.
- Suggested starting points (not exclusive):
    - {abs_session_path}
    - {abs_kg_path}
    - {abs_dg_path}
    - {abs_denoiser_path}
    - {abs_mediator_path}

Context files (use tools to read only what you need):
- cycle_summary.json: {os.path.abspath(cycle_summary_path)}
- sgd_report.json:    {os.path.abspath(sgd_report_path)}
- worst sessions (session.json):\n{json.dumps([os.path.abspath(p) for p in worst_session_json_paths], ensure_ascii=False, indent=2)}

Primary focus (computed from diagnostics):
{json.dumps(focus, ensure_ascii=False)}

Suspected files to start with:
{json.dumps(suspected_files, ensure_ascii=False, indent=2)}

Goal:
- Address the highest-impact items in Priority improvements and SGD recommendations.
- If graphs are empty/tiny: improve knowledge graph and dependency graph population/reduction so downstream denoising has structure.
- If question repetition is flagged: reduce repeated identical mediator questions in adversarial sessions (improve efficiency + info extraction).
- Keep changes minimal and localized.
- Do NOT add dependencies.
- Ensure existing tests keep passing.

Implementation constraints:
- Only modify Python files.
- Prefer changing adversarial harness behavior (e.g., question selection logic) rather than core mediator logic.

Strong suggestion for step 1:
- Use cat/grep to inspect the relevant portions of the suspected files and the context JSONs, then propose a patch.

Output requirements:
- Output MUST start with the exact line: *** Begin Patch
- Use absolute file paths (within the repository root) in each *** Update File line.
- Patch MUST include a non-trivial change (not placeholders like /abs/path/to/file.py or 'old'/'new').
- Output MUST end with the exact line: *** End Patch
- No markdown fences. No extra commentary.

Now begin."""

    return f"""You are Codex CLI.

Tool-mode is ENABLED. You may take multiple turns by requesting a tool call, then using its result to decide on a better patch.

On each turn, output exactly ONE of the following:

1) A single JSON object requesting a tool:
{{
  "type": "tool",
    "tool": "ls" | "cat" | "grep" | "patch",
  "args": {{ ... }}
}}

2) A single JSON object returning the final patch:
{{
  "type": "final",
  "patch": "*** Begin Patch\n...\n*** End Patch"
}}

3) (Backward compatible) Output a raw apply_patch patch starting with '*** Begin Patch' and ending with '*** End Patch'.

Tool specs (paths must be within the repository root; keep outputs small):
- ls:    args={{"path": "."}}  -> list directory entries
- cat:   args={{"path": "path/to/file.py", "start_line": 1, "end_line": 200}} -> read a line range
- grep:  args={{"pattern": "string or regex", "path": "path/or/dir", "max_matches": 50}} -> search text
- patch: args={{"patch": "*** Begin Patch\\n...\\n*** End Patch"}} -> validate patch formatting + file targets (does NOT apply)

Before returning a final patch (type=final or raw patch), you SHOULD call the patch tool on your candidate patch and fix any errors it reports.

You must output a REAL patch in apply_patch format, not a template.

Patch formatting rules (important):
- Do NOT output unified-diff style prefixes (no leading ' ' marker on unchanged lines).
- Do NOT use '...' or '@@' as an ellipsis to omit lines inside a hunk.
- Each hunk must contain exact, contiguous lines copied from the current file content.
- Use '@@' only to start a new hunk (or include a scope hint like '@@ class Foo'), never as a placeholder.

Scope:
- You MAY change any *.py file under the repository root: {os.path.abspath(PROJECT_ROOT)}
- Use ONLY absolute paths in *** Update File lines.
- Suggested starting points (not exclusive):
    - {abs_session_path}
    - {abs_kg_path}
    - {abs_dg_path}
    - {abs_denoiser_path}
    - {abs_mediator_path}

Context:
- We just ran an adversarial harness batch from: {os.path.abspath(run_dir)}
- Priority improvements from optimizer: {json.dumps(priority, ensure_ascii=False)}
- Optimizer graph diagnostics: {json.dumps(optimizer_graph_diag, ensure_ascii=False)}
- Graphs health (static): {json.dumps(graphs_health, ensure_ascii=False)}
- Graphs health (dynamics): {json.dumps(graphs_dynamics_health, ensure_ascii=False)}
- SGD recommendations: {json.dumps(recs, ensure_ascii=False)}
- SGD graph summary: {json.dumps(sgd_graphs, ensure_ascii=False)}
- Worst session briefs (from this run):\n{json.dumps(worst_briefs, ensure_ascii=False, indent=2)}

Primary focus (computed from diagnostics):
{json.dumps(focus, ensure_ascii=False)}

Suspected files to start with:
{json.dumps(suspected_files, ensure_ascii=False, indent=2)}

Goal:
- Address the highest-impact items in Priority improvements and SGD recommendations.
- If graphs are empty/tiny: improve knowledge graph and dependency graph population/reduction so downstream denoising has structure.
- If question repetition is flagged: reduce repeated identical mediator questions in adversarial sessions (improve efficiency + info extraction).
- Keep changes minimal and localized.
- Do NOT add dependencies.
- Ensure existing tests keep passing.

Implementation constraints:
- Only modify Python files.
- Prefer changing adversarial harness behavior (e.g., question selection logic) rather than core mediator logic.

Output requirements:
- Output MUST start with the exact line: *** Begin Patch
- Use absolute file paths (within the repository root) in each *** Update File line.
- Patch MUST include a non-trivial change (not placeholders like /abs/path/to/file.py or 'old'/'new').
- Output MUST end with the exact line: *** End Patch
- No markdown fences. No extra commentary.

Helpful code snippet from adversarial_harness/session.py (current):
{snippet}

Now produce the patch."""


_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}\s*$")


def _safe_abs_path(path: str) -> str:
    if not isinstance(path, str) or not path:
        raise ValueError("path is required")
    candidate = os.path.abspath(os.path.join(PROJECT_ROOT, path)) if not os.path.isabs(path) else os.path.abspath(path)
    root = os.path.abspath(PROJECT_ROOT)
    if candidate == root or candidate.startswith(root + os.sep):
        return candidate
    raise ValueError(f"Path is outside repository root: {path}")


def _tool_ls(*, path: str) -> str:
    p = _safe_abs_path(path)
    if not os.path.isdir(p):
        return f"ERROR: not a directory: {path}"
    try:
        names = sorted(os.listdir(p))
    except Exception as e:
        return f"ERROR: ls failed: {e}"
    # Keep outputs small.
    if len(names) > 200:
        names = names[:200] + ["...(truncated)"]
    return "\n".join(names)


def _tool_cat(*, path: str, start_line: int = 1, end_line: int = 200) -> str:
    p = _safe_abs_path(path)
    if not os.path.isfile(p):
        return f"ERROR: not a file: {path}"
    start = max(1, int(start_line or 1))
    end = max(start, int(end_line or start))
    max_span = 400
    if (end - start + 1) > max_span:
        end = start + max_span - 1
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except Exception as e:
        return f"ERROR: cat failed: {e}"
    total = len(lines)
    sel = lines[start - 1 : min(end, total)]
    header = f"FILE: {os.path.relpath(p, PROJECT_ROOT)} ({start}-{min(end, total)} of {total})"
    body = "\n".join(f"{i+start}: {line}" for i, line in enumerate(sel))
    suffix = "\n...(truncated)" if end < total else ""
    return header + "\n" + body + suffix


def _tool_grep(*, pattern: str, path: str, max_matches: int = 50) -> str:
    p = _safe_abs_path(path)
    try:
        rx = re.compile(pattern)
    except re.error:
        rx = None
    max_m = max(1, min(int(max_matches or 50), 200))

    matches: List[str] = []

    def scan_file(fp: str) -> None:
        nonlocal matches
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f, start=1):
                    ok = (rx.search(line) is not None) if rx else (pattern in line)
                    if ok:
                        rel = os.path.relpath(fp, PROJECT_ROOT)
                        matches.append(f"{rel}:{i}:{line.rstrip()}"[:500])
                        if len(matches) >= max_m:
                            return
        except Exception:
            return

    if os.path.isfile(p):
        scan_file(p)
    elif os.path.isdir(p):
        for root, _dirs, files in os.walk(p):
            for name in files:
                if len(matches) >= max_m:
                    break
                fp = os.path.join(root, name)
                # Skip huge/binary-ish files by extension heuristic.
                if name.endswith((".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".gz", ".db", ".duckdb")):
                    continue
                scan_file(fp)
            if len(matches) >= max_m:
                break
    else:
        return f"ERROR: path not found: {path}"

    if not matches:
        return "(no matches)"
    out = "\n".join(matches)
    if len(matches) >= max_m:
        out += "\n...(truncated)"
    return out


class PatchApplyError(Exception):
    def __init__(
        self,
        message: str,
        *,
        file_path: Optional[str] = None,
        hunk_index: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.file_path = file_path
        self.hunk_index = hunk_index
        self.details = details or None


def _validate_python_syntax(file_path: str, file_lines: List[str]) -> None:
    if not file_path.endswith(".py"):
        return
    src = "\n".join(file_lines) + "\n"
    try:
        compile(src, file_path, "exec")
    except SyntaxError as e:
        detail = (e.msg or "SyntaxError").strip()
        loc = f"line {e.lineno}" if e.lineno else "unknown line"
        raise PatchApplyError(f"Python syntax error after patch: {detail} ({loc})", file_path=file_path) from e


def _parse_apply_patch(text: str) -> List[Tuple[str, List[List[str]]]]:
    """Parse apply_patch formatted text into [(file_path, [hunk_lines...])]."""
    text = _normalize_patch_text(text)
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    if not lines or lines[0].strip() != "*** Begin Patch" or lines[-1].strip() != "*** End Patch":
        raise PatchApplyError("Not in apply_patch format")

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
        def leading_space_count(s: str) -> int:
            n = 0
            for ch in s:
                if ch == " ":
                    n += 1
                else:
                    break
            return n

        def looks_like_unified_diff_prefix(ln: str) -> bool:
            """Detect common unified-diff prefixes that Codex sometimes emits.

            apply_patch format expects raw file lines (optionally prefixed with + / -).
            Unified diffs often prefix unchanged lines with a single leading space.
            For Python, that produces leading whitespace counts of 5, 9, 13, ... which
            won't match the underlying file. We strip that prefix when detected.
            """
            if not ln:
                return False
            if ln.startswith(("*** ", "@@")):
                return False
            if ln[0] in "+-":
                # Some diffs include an extra space after +/- before the actual line.
                if len(ln) > 1 and ln[1] == " ":
                    return leading_space_count(ln[1:]) % 4 == 1
                return False
            if ln.startswith(" "):
                return leading_space_count(ln) % 4 == 1
            return False

        strip_global_prefix = global_prefix_hint or any(
            looks_like_unified_diff_prefix(ln) for ln in raw_lines
        )

        out: List[str] = []
        for ln in raw_lines:
            if not strip_global_prefix:
                out.append(ln)
                continue

            if ln.startswith(("+", "-")) and len(ln) > 1 and ln[1] == " ":
                if leading_space_count(ln[1:]) % 4 == 1:
                    out.append(ln[0] + ln[2:])
                    continue

            if ln.startswith(" "):
                if leading_space_count(ln) % 4 == 1:
                    out.append(ln[1:])
                    continue

            out.append(ln)

        return out

    def flush_file() -> None:
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
            raise PatchApplyError("Only '*** Update File' patches are supported")
        if line.startswith("@@"):
            if current_file is None:
                i += 1
                continue
            if current_hunk is not None and current_hunk:
                current_hunks.append(normalize_hunk_lines(current_hunk))
            current_hunk = []
            i += 1
            continue

        if current_file is not None:
            if current_hunk is None:
                current_hunk = []
            current_hunk.append(line)
        i += 1

    flush_file()
    return file_blocks


def _find_subsequence(haystack: List[str], needle: List[str]) -> Optional[int]:
    if not needle:
        return None
    max_i = len(haystack) - len(needle)
    for i in range(max_i + 1):
        if haystack[i : i + len(needle)] == needle:
            return i
    return None


def _find_subsequence_rstrip(haystack: List[str], needle: List[str]) -> Optional[int]:
    if not needle:
        return None
    hay = [h.rstrip() for h in haystack]
    ned = [n.rstrip() for n in needle]
    max_i = len(hay) - len(ned)
    for i in range(max_i + 1):
        if hay[i : i + len(ned)] == ned:
            return i
    return None


def _find_subsequence_relaxed_indent(haystack: List[str], needle: List[str]) -> Optional[int]:
    """Fallback matching that ignores leading indentation differences.

    This is intentionally conservative: it only succeeds when there is exactly ONE
    matching location, to avoid applying hunks to the wrong region.
    """

    if not needle:
        return None

    hay = [h.strip() for h in haystack]
    ned = [n.strip() for n in needle]
    max_i = len(hay) - len(ned)
    matches: List[int] = []
    for i in range(max_i + 1):
        if hay[i : i + len(ned)] == ned:
            matches.append(i)
            if len(matches) > 1:
                return None
    return matches[0] if matches else None


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
        pos = _find_subsequence_relaxed_indent(file_lines, old_block)
    if pos is None:
        def clip(lines: List[str], limit: int = 80) -> List[str]:
            return lines if len(lines) <= limit else (lines[:limit] + ["...<clipped>..."])

        raise PatchApplyError(
            "Hunk context not found",
            details={
                "old_block": clip(old_block),
                "new_block": clip(new_block),
                "hunk_lines": clip(list(hunk_lines)),
            },
        )

    return file_lines[:pos] + new_block + file_lines[pos + len(old_block) :]


def _dry_run_apply_patch_text(patch_text: str) -> List[str]:
    """Return list of files that would be updated, or raise PatchApplyError."""
    patch_text = _normalize_patch_text(patch_text)
    file_blocks = _parse_apply_patch(patch_text)
    if not file_blocks:
        return []

    updated_files: List[str] = []
    for file_path, hunks in file_blocks:
        if not os.path.isabs(file_path):
            raise PatchApplyError("Patch paths must be absolute", file_path=file_path)
        try:
            _safe_abs_path(file_path)
        except Exception as e:
            raise PatchApplyError("Patch path not allowed", file_path=file_path, details={"error": str(e)}) from e
        if not os.path.isfile(file_path):
            raise PatchApplyError("Target file does not exist", file_path=file_path)

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            file_lines = f.read().splitlines()

        for hunk_index, hunk_lines in enumerate(hunks):
            try:
                file_lines = _apply_hunk_to_lines(file_lines, hunk_lines)
            except PatchApplyError as e:
                raise PatchApplyError(e.message, file_path=file_path, hunk_index=hunk_index, details=e.details) from e

        _validate_python_syntax(file_path, file_lines)
        if file_path not in updated_files:
            updated_files.append(file_path)

    return updated_files


def _tool_patch(*, patch: str) -> str:
    text = _normalize_patch_text(patch or "")
    looks_like = _looks_like_apply_patch(text)
    update_files: List[str] = []

    try:
        update_files = _dry_run_apply_patch_text(text)
        result = {
            "ok": True,
            "looks_like_apply_patch": looks_like,
            "would_update_files": update_files,
            "note": ("no-op patch" if not update_files else None),
        }
        return json.dumps(result, ensure_ascii=False, indent=2)
    except PatchApplyError as e:
        result = {
            "ok": False,
            "looks_like_apply_patch": looks_like,
            "error": {
                "message": e.message,
                "file_path": e.file_path,
                "hunk_index": e.hunk_index,
                "details": e.details,
            },
        }
        return json.dumps(result, ensure_ascii=False, indent=2)


def _try_parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not isinstance(text, str):
        return None
    s = text.strip()
    if not s.startswith("{"):
        # Try to recover a trailing JSON object.
        m = _JSON_OBJECT_RE.search(s)
        if not m:
            return None
        s = m.group(0)
    try:
        obj = json.loads(s)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _run_codex_with_tools(*, backend: LLMRouterBackend, base_prompt: str, max_steps: int = 8) -> str:
    raise RuntimeError("Use _run_codex_with_tools_logged")


def _append_jsonl(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_codex_with_tools_logged(
    *,
    backend: LLMRouterBackend,
    base_prompt: str,
    max_steps: int = 8,
    chat_jsonl_path: Optional[str] = None,
) -> str:
    tool_log: List[str] = []
    last_output = ""

    def _compact_for_prompt(text: str, *, max_chars: int = 2200, max_lines: int = 80) -> str:
        """Compact tool results/validation before re-injecting into the rolling prompt.

        We still persist full results in the JSONL transcript, but keeping the
        rolling prompt compact materially reduces prompt tokens on later turns.
        """

        if not isinstance(text, str):
            text = str(text)
        lines = text.splitlines()
        if len(lines) > max_lines:
            head = lines[: max_lines // 2]
            tail = lines[-(max_lines - len(head)) :]
            omitted = len(lines) - len(head) - len(tail)
            lines = head + [f"...(omitted {omitted} lines)..."] + tail
        out = "\n".join(lines)
        if len(out) > max_chars:
            keep = max(200, max_chars // 2)
            out = out[:keep] + "\n...(omitted chars)...\n" + out[-keep:]
        return out

    if chat_jsonl_path:
        _append_jsonl(
            chat_jsonl_path,
            {
                "event": "session_start",
                "ts": _utc_iso(),
                "tool_protocol": "v1",
                "max_steps": int(max_steps),
                "base_prompt": base_prompt,
            },
        )

    for step in range(max(1, int(max_steps))):
        transcript = base_prompt
        if tool_log:
            transcript += "\n\n" + "\n\n".join(tool_log[-8:])

        if chat_jsonl_path:
            _append_jsonl(
                chat_jsonl_path,
                {
                    "event": "prompt",
                    "ts": _utc_iso(),
                    "step": step + 1,
                    "tool_log_tail": tool_log[-8:],
                },
            )

        out = backend(transcript)
        last_output = out or ""

        if chat_jsonl_path:
            _append_jsonl(
                chat_jsonl_path,
                {
                    "event": "model_output",
                    "ts": _utc_iso(),
                    "step": step + 1,
                    "text": last_output,
                },
            )

        norm = _normalize_patch_text(last_output)
        if _looks_like_apply_patch(norm):
            try:
                updated = _dry_run_apply_patch_text(norm)
                if chat_jsonl_path:
                    _append_jsonl(
                        chat_jsonl_path,
                        {
                            "event": "patch_candidate",
                            "ts": _utc_iso(),
                            "step": step + 1,
                            "kind": "raw",
                            "ok": True,
                            "would_update_files": updated,
                        },
                    )
                return norm
            except PatchApplyError:
                if chat_jsonl_path:
                    _append_jsonl(
                        chat_jsonl_path,
                        {
                            "event": "patch_candidate",
                            "ts": _utc_iso(),
                            "step": step + 1,
                            "kind": "raw",
                            "ok": False,
                            "validation": json.loads(_tool_patch(patch=norm)),
                        },
                    )
                tool_log.append(
                    "SYSTEM: Candidate patch failed dry-run validation. Fix the patch, and consider calling the patch tool before finalizing."
                )
                tool_log.append("PATCH_VALIDATION:\n" + _compact_for_prompt(_tool_patch(patch=norm)))
                continue

        obj = _try_parse_json_object(last_output)
        if not obj:
            # Try one nudge toward valid output formats.
            tool_log.append(
                "SYSTEM: Your previous output was not valid JSON or an apply_patch patch. "
                "Return either a JSON tool request or a JSON final patch."
            )
            continue

        typ = obj.get("type")
        if typ == "final":
            patch = obj.get("patch")
            if isinstance(patch, str):
                patch = _normalize_patch_text(patch)
                if _looks_like_apply_patch(patch):
                    try:
                        updated = _dry_run_apply_patch_text(patch)
                        if chat_jsonl_path:
                            _append_jsonl(
                                chat_jsonl_path,
                                {
                                    "event": "patch_candidate",
                                    "ts": _utc_iso(),
                                    "step": step + 1,
                                    "kind": "json_final",
                                    "ok": True,
                                    "would_update_files": updated,
                                },
                            )
                        return patch
                    except PatchApplyError:
                        if chat_jsonl_path:
                            _append_jsonl(
                                chat_jsonl_path,
                                {
                                    "event": "patch_candidate",
                                    "ts": _utc_iso(),
                                    "step": step + 1,
                                    "kind": "json_final",
                                    "ok": False,
                                    "validation": json.loads(_tool_patch(patch=patch)),
                                },
                            )
                        tool_log.append(
                            "SYSTEM: Your JSON final patch failed dry-run validation. Fix it, and consider calling the patch tool before finalizing."
                        )
                        tool_log.append("PATCH_VALIDATION:\n" + _compact_for_prompt(_tool_patch(patch=patch)))
                        continue
            tool_log.append(
                "SYSTEM: Your previous JSON final did not include a valid apply_patch patch. Return ONLY a corrected final patch."
            )
            continue

        if typ != "tool":
            tool_log.append("SYSTEM: Invalid JSON. 'type' must be 'tool' or 'final'.")
            continue

        tool = obj.get("tool")
        args = obj.get("args")
        if not isinstance(tool, str) or not isinstance(args, dict):
            tool_log.append("SYSTEM: Invalid tool request. Must include string 'tool' and object 'args'.")
            continue

        try:
            if tool == "ls":
                result = _tool_ls(path=str(args.get("path", ".")))
            elif tool == "cat":
                result = _tool_cat(
                    path=str(args.get("path", "")),
                    start_line=int(args.get("start_line", 1) or 1),
                    end_line=int(args.get("end_line", 200) or 200),
                )
            elif tool == "grep":
                result = _tool_grep(
                    pattern=str(args.get("pattern", "")),
                    path=str(args.get("path", ".")),
                    max_matches=int(args.get("max_matches", 50) or 50),
                )
            elif tool == "patch":
                result = _tool_patch(patch=str(args.get("patch", "")))
            else:
                result = f"ERROR: unknown tool: {tool}"
        except Exception as e:
            result = f"ERROR: tool execution failed: {e}"

        if chat_jsonl_path:
            _append_jsonl(
                chat_jsonl_path,
                {
                    "event": "tool_call",
                    "ts": _utc_iso(),
                    "step": step + 1,
                    "tool": tool,
                    "args": args,
                },
            )
            _append_jsonl(
                chat_jsonl_path,
                {
                    "event": "tool_result",
                    "ts": _utc_iso(),
                    "step": step + 1,
                    "tool": tool,
                    "result": result,
                },
            )

        tool_log.append(
            f"TOOL_CALL(step={step+1}): {json.dumps(obj, ensure_ascii=False)}\nTOOL_RESULT:\n{_compact_for_prompt(result)}".strip()
        )

    # Final forced attempt
    final_prompt = base_prompt + "\n\nTool budget exhausted. Return a JSON {type:'final', patch:'...'} with a valid apply_patch patch."
    if chat_jsonl_path:
        _append_jsonl(
            chat_jsonl_path,
            {
                "event": "final_prompt",
                "ts": _utc_iso(),
                "tool_log_tail": tool_log[-8:],
            },
        )
    out = backend(final_prompt)
    norm = _normalize_patch_text(out or "")
    if _looks_like_apply_patch(norm):
        try:
            _dry_run_apply_patch_text(norm)
            return norm
        except PatchApplyError:
            validation = _tool_patch(patch=norm)
            repair_prompt = (
                base_prompt
                + "\n\nYour candidate patch failed dry-run validation. Fix it."
                + "\nPATCH_VALIDATION:\n"
                + validation
                + "\n\nReturn ONLY a JSON {type:'final', patch:'...'} with a corrected patch."
            )
            if chat_jsonl_path:
                _append_jsonl(
                    chat_jsonl_path,
                    {
                        "event": "forced_patch_failed",
                        "ts": _utc_iso(),
                        "validation": json.loads(validation),
                    },
                )
            out2 = backend(repair_prompt)
            obj2 = _try_parse_json_object(out2 or "")
            if obj2 and obj2.get("type") == "final" and isinstance(obj2.get("patch"), str):
                patch2 = _normalize_patch_text(obj2["patch"])
                if _looks_like_apply_patch(patch2):
                    _dry_run_apply_patch_text(patch2)
                    return patch2
    obj = _try_parse_json_object(out or "")
    if obj and obj.get("type") == "final" and isinstance(obj.get("patch"), str):
        patch = _normalize_patch_text(obj["patch"])
        if _looks_like_apply_patch(patch):
            try:
                _dry_run_apply_patch_text(patch)
                return patch
            except PatchApplyError:
                validation = _tool_patch(patch=patch)
                repair_prompt = (
                    base_prompt
                    + "\n\nYour candidate patch failed dry-run validation. Fix it."
                    + "\nPATCH_VALIDATION:\n"
                    + validation
                    + "\n\nReturn ONLY a JSON {type:'final', patch:'...'} with a corrected patch."
                )
                if chat_jsonl_path:
                    _append_jsonl(
                        chat_jsonl_path,
                        {
                            "event": "forced_patch_failed",
                            "ts": _utc_iso(),
                            "validation": json.loads(validation),
                        },
                    )
                out2 = backend(repair_prompt)
                obj2 = _try_parse_json_object(out2 or "")
                if obj2 and obj2.get("type") == "final" and isinstance(obj2.get("patch"), str):
                    patch2 = _normalize_patch_text(obj2["patch"])
                    if _looks_like_apply_patch(patch2):
                        _dry_run_apply_patch_text(patch2)
                        return patch2
    raise SystemExit(
        "Codex did not return a valid apply_patch patch after tool loop. "
        "Re-run with different prompt or increase max steps."
    )


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
    parser.add_argument(
        "--context-mode",
        choices=["rich", "lean"],
        default="rich",
        help="rich inlines JSON context into the prompt; lean points Codex at JSON artifacts and relies on tool calls to fetch context",
    )
    parser.add_argument("--max-steps", type=int, default=8)
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
    worst_session_paths = session_jsons[:]
    try:
        worst_ids = {d.get("session_id") for d in worst}
        worst_session_paths = [p for p, d in zip(session_jsons, session_docs) if d.get("session_id") in worst_ids]
    except Exception:
        worst_session_paths = session_jsons[: args.max_worst_sessions]

    config = _load_config(args.config)
    backend_kwargs = _get_llm_router_backend_config(config, args.backend_id)
    # Keep Codex CLI session/event logs inside the run artifacts (statefiles is git-ignored).
    # This relies on ipfs_datasets_py.llm_router trace options.
    try:
        provider = str(backend_kwargs.get("provider") or "")
    except Exception:
        provider = ""
    if provider.strip() == "codex_cli":
        # Best-effort: codex exec stdout JSONL (thread_id, usage incl cached_input_tokens).
        backend_kwargs.setdefault("trace", True)
        backend_kwargs.setdefault("trace_dir", os.path.join(run_dir, "_patches"))

    backend = LLMRouterBackend(**backend_kwargs)

    prompt = _build_prompt(
        run_dir=run_dir,
        cycle_summary_path=cycle_summary_path,
        cycle_summary=cycle_summary,
        sgd_report_path=str(sgd_report_path),
        sgd_report=sgd_report,
        worst_sessions=worst,
        worst_session_json_paths=worst_session_paths[: args.max_worst_sessions],
        context_mode=str(args.context_mode),
    )

    out_dir = os.path.join(run_dir, "_patches")
    os.makedirs(out_dir, exist_ok=True)
    chat_jsonl_path = os.path.join(
        out_dir,
        f"codex_chat_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.jsonl",
    )

    patch_text = _run_codex_with_tools_logged(
        backend=backend,
        base_prompt=prompt,
        max_steps=int(args.max_steps),
        chat_jsonl_path=chat_jsonl_path,
    )

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
