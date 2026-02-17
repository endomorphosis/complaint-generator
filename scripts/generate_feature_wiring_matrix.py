#!/usr/bin/env python3
"""Generate a static feature wiring matrix for ipfs_datasets_py.

This script intentionally avoids importing ipfs_datasets_py (and its optional
heavy dependencies). It uses filesystem heuristics to build an inventory of
"features" (top-level modules/packages) and their wiring surfaces:

- import: stable Python import path (module/package exists)
- cli: presence of CLI modules (cli.py, cli/ package, __main__.py)
- mcp: presence of MCP tool categories that likely correspond to the feature

Outputs:
- docs/FEATURE_WIRING_MATRIX.json
- docs/FEATURE_WIRING_MATRIX.md

Usage:
  ./scripts/generate_feature_wiring_matrix.py

Notes:
- This is a Tier-0 artifact to guide refactors; it is not authoritative.
- A future dynamic validator can import modules in a guarded sandbox.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Iterable, Set
import ast


REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_ROOT = REPO_ROOT / "ipfs_datasets_py" / "ipfs_datasets_py"
MCP_TOOLS_ROOT = PKG_ROOT / "mcp_server" / "tools"
DOCS_ROOT = REPO_ROOT / "docs"
SETUP_PY = REPO_ROOT / "ipfs_datasets_py" / "setup.py"


@dataclass(frozen=True)
class WiringSurface:
    import_module: str
    import_exists: bool
    public_exports: List[str]
    public_exports_source: str
    likely_extras: List[str]
    cli_modules: List[str]
    cli_commands: List[str]
    mcp_tool_categories: List[str]
    mcp_tool_functions: List[str]
    notes: List[str]


@dataclass(frozen=True)
class FeatureRow:
    feature_id: str
    kind: str  # package|module|dir
    path: str
    surfaces: WiringSurface
    status: str  # wired|partial|missing


def _is_python_package(path: Path) -> bool:
    return path.is_dir() and (path / "__init__.py").exists()


def _is_python_module(path: Path) -> bool:
    return path.is_file() and path.suffix == ".py" and path.name != "__init__.py"


def _iter_top_level_features(pkg_root: Path) -> List[Tuple[str, str, Path]]:
    """Return [(feature_id, kind, path)] for top-level entries.

    We include:
    - Python packages (dir with __init__.py)
    - Python modules (*.py)
    - Feature directories that contain Python code but are not importable packages
      (dir without __init__.py). These are important for wiring work.
    """

    out: List[Tuple[str, str, Path]] = []
    for child in sorted(pkg_root.iterdir(), key=lambda p: p.name):
        if child.name.startswith("__"):
            continue
        if child.name.startswith("."):
            continue
        if child.name in {"mcp_server", "static", "templates", "__pycache__"}:
            # Still real code, but treat separately (mcp_server is its own domain).
            continue

        if _is_python_package(child):
            out.append((child.name, "package", child))
        elif _is_python_module(child):
            out.append((child.stem, "module", child))
        elif child.is_dir():
            # Non-package dir: include it if it contains any Python files.
            has_py = any(p.is_file() and p.suffix == ".py" for p in child.rglob("*.py"))
            if has_py:
                out.append((child.name, "dir", child))

    return out


def _detect_cli_modules(feature_id: str, kind: str, feature_path: Path, pkg_root: Path) -> List[str]:
    """Heuristic CLI detection.

    Returns strings prefixed with:
    - module:ipfs_datasets_py....  (best-effort import path)
    - path:ipfs_datasets_py/...    (filesystem fallback)
    """

    modules: List[str] = []

    # Conventional: ipfs_datasets_py.<feature>.cli or cli.py
    if kind in {"package", "dir"}:
        cli_py = feature_path / "cli.py"
        if cli_py.exists():
            if kind == "package":
                modules.append(f"module:ipfs_datasets_py.{feature_id}.cli")
            modules.append(f"path:{cli_py.relative_to(REPO_ROOT).as_posix()}")

        cli_pkg = feature_path / "cli"
        if _is_python_package(cli_pkg):
            modules.append(f"module:ipfs_datasets_py.{feature_id}.cli")
        elif cli_pkg.is_dir() and any(p.suffix == ".py" for p in cli_pkg.rglob("*.py")):
            modules.append(f"path:{cli_pkg.relative_to(REPO_ROOT).as_posix()}")

        main_py = feature_path / "__main__.py"
        if main_py.exists():
            if kind == "package":
                modules.append(f"module:ipfs_datasets_py.{feature_id}.__main__")
            modules.append(f"path:{main_py.relative_to(REPO_ROOT).as_posix()}")

    # Special case: the package-level CLI surface.
    if feature_id == "cli" and kind == "package":
        modules.append("module:ipfs_datasets_py.cli")

    # Cross-cutting CLI package: ipfs_datasets_py.cli
    # (Record it once on the first feature row that needs it)
    # Caller will add global CLI separately.

    return sorted(set(modules))


def _list_mcp_tool_categories(mcp_tools_root: Path) -> List[str]:
    if not mcp_tools_root.exists():
        return []

    out: List[str] = []
    for child in sorted(mcp_tools_root.iterdir(), key=lambda p: p.name):
        if child.name.startswith("_") or child.name.startswith("."):
            continue
        if not child.is_dir():
            continue
        if child.name == "__pycache__":
            continue
        # Tools categories are often packages, but sometimes they are plain
        # directories containing .py modules. Treat both as categories.
        has_py = any(
            p.is_file() and p.suffix == ".py" and p.name != "__init__.py" and not p.name.startswith("_")
            for p in child.rglob("*.py")
        )
        if _is_python_package(child) or has_py:
            out.append(child.name)
    return out


def _extract_str_seq(node: ast.AST) -> List[str]:
    """Extract a list of strings from a literal list/tuple AST node."""

    if not isinstance(node, (ast.List, ast.Tuple)):
        return []

    out: List[str] = []
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            out.append(elt.value)
    return out


def _detect_public_exports_for_package(pkg_dir: Path) -> Tuple[List[str], str]:
    """Detect public exports for a package by parsing __init__.py.

    Returns (public_exports, source) where source is one of:
    - "__all__" (preferred)
    - "reexports" (explicit re-export via from ... import ...)
    - "none" (no clear signals)

    This is a heuristic and intentionally avoids importing the package.
    """

    init_py = pkg_dir / "__init__.py"
    if not init_py.exists():
        return ([], "none")

    try:
        text = init_py.read_text("utf-8")
    except Exception:
        return ([], "none")

    try:
        tree = ast.parse(text, filename=str(init_py))
    except Exception:
        return ([], "none")

    # 1) Prefer __all__ if defined as a simple literal list/tuple.
    all_names: List[str] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets or []):
            continue
        all_names = _extract_str_seq(node.value)
        if all_names:
            break

    if all_names:
        return (sorted({n for n in all_names if n and not n.startswith("_")}), "__all__")

    # 2) Otherwise, collect explicit re-exported names.
    reexports: List[str] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            # from .foo import Bar as Baz
            for alias in node.names or []:
                name = alias.asname or alias.name
                if name and name != "*" and not name.startswith("_"):
                    reexports.append(name)

    reexports = sorted(set(reexports))
    if reexports:
        return (reexports, "reexports")

    return ([], "none")


def _safe_parse_tool_module_functions(py_file: Path) -> List[str]:
    """Return public top-level function names for a tool module (AST-based).

    This intentionally does not import the module.
    """

    try:
        text = py_file.read_text("utf-8")
    except Exception:
        return []

    try:
        tree = ast.parse(text, filename=str(py_file))
    except Exception:
        return []

    names: List[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                names.append(node.name)

    return sorted(set(names))


def _is_testish_python_file(py_file: Path) -> bool:
    """Return True for files that should not be treated as MCP tool modules."""

    name = py_file.name
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    if "tests" in py_file.parts or "test" in py_file.parts:
        # Conservative: tool modules should never live under these.
        return True
    return False


def _index_mcp_tool_functions(mcp_tools_root: Path) -> Dict[str, Dict[str, List[str]]]:
    """Index tool functions by category and module path (AST-based).

    Returns: {category: {module_key: [function_names...]}}
    - module_key is a best-effort dotted path relative to the category dir.
      Example: "workflow_scheduler_tools" or "logic_utils.helpers".
    """

    out: Dict[str, Dict[str, List[str]]] = {}
    if not mcp_tools_root.exists():
        return out

    for cat_dir in sorted(mcp_tools_root.iterdir(), key=lambda p: p.name):
        if cat_dir.name.startswith("_") or cat_dir.name.startswith("."):
            continue
        if not cat_dir.is_dir() or cat_dir.name == "__pycache__":
            continue

        cat_map: Dict[str, List[str]] = {}
        for py_file in sorted(cat_dir.rglob("*.py"), key=lambda p: p.as_posix()):
            if "__pycache__" in py_file.parts:
                continue
            if py_file.name in {"__init__.py"} or py_file.name.startswith("_"):
                continue
            if _is_testish_python_file(py_file):
                continue
            funcs = _safe_parse_tool_module_functions(py_file)
            if not funcs:
                continue

            rel = py_file.relative_to(cat_dir).with_suffix("")
            module_key = ".".join(rel.parts)
            cat_map[module_key] = funcs

        out[cat_dir.name] = cat_map

    return out


def _flatten_tool_index_for_categories(
    tool_index: Dict[str, Dict[str, List[str]]],
    categories: List[str],
) -> List[str]:
    """Return a sorted unique list of tool function names for categories.

    This uses the AST-derived tool_index (no imports).
    """

    names: set[str] = set()
    for category in categories:
        modules = tool_index.get(category) or {}
        for fns in modules.values():
            for fn in fns or []:
                if fn and not fn.startswith("_"):
                    names.add(fn)
    return sorted(names)


def _tokenize(text: str) -> List[str]:
    text = (text or "").lower()
    out: List[str] = []
    buf: List[str] = []
    for ch in text:
        if ch.isalnum():
            buf.append(ch)
        else:
            if buf:
                out.append("".join(buf))
                buf = []
    if buf:
        out.append("".join(buf))
    # Drop very short tokens that are noisy.
    stop = {
        "tool",
        "tools",
        "mcp",
        "server",
        "client",
        "data",
        "dataset",
        "datasets",
        "manager",
        "utils",
        "utility",
        "helper",
        "helpers",
        "integration",
        "advanced",
        "enhanced",
    }
    return [t for t in out if len(t) >= 3 and t not in stop]


def _score_category_for_feature(
    feature_tokens: Set[str],
    category: str,
    tool_index: Dict[str, Dict[str, List[str]]],
) -> int:
    """Heuristic score for mapping feature → category.

    Score is based on overlapping tokens between the feature id and:
    - category name
    - module keys within that category (relative paths)

    We intentionally do NOT use function names for scoring because they can be
    very generic and explode false positives.
    """

    cat_tokens = set(_tokenize(category))
    overlap = len(feature_tokens & cat_tokens)
    if overlap <= 0:
        return 0

    # Strongly prefer direct semantic overlap with the category name.
    score = 10 * overlap

    # Mildly boost when a category has a module key that overlaps too.
    modules = tool_index.get(category) or {}
    for module_key in list(modules.keys())[:30]:
        mod_tokens = set(_tokenize(module_key))
        score += 1 * len(feature_tokens & mod_tokens)

    return score


def _map_feature_to_tool_categories(
    feature_id: str,
    tool_categories: List[str],
    tool_index: Dict[str, Dict[str, List[str]]],
) -> List[str]:
    """Best-effort mapping from feature id to MCP tool categories.

    Strategy:
    - preserve manual seeds
    - otherwise pick top-scoring categories based on token overlap
    - drop categories with zero indexed functions (avoids noisy placeholders)
    """

    fid = (feature_id or "").lower()

    manual: Dict[str, List[str]] = {
        "processors": ["data_processing_tools", "file_converter_tools", "file_detection_tools"],
        "web_archiving": ["web_archive_tools", "web_scraping_tools"],
        "legal_scrapers": ["web_scraping_tools", "legal_dataset_tools"],
        # The bulk of "logic" tools live under dataset_tools (logic_utils.*).
        "logic": ["dataset_tools", "logic_tools"],
        "audit": ["audit_tools"],
        "alerts": ["alert_tools"],
        "security": ["security_tools", "auth_tools", "session_tools"],
        "ml": ["embedding_tools", "vector_tools", "sparse_embedding_tools"],
        "vector_stores": ["vector_store_tools"],
        "pdf_processing": ["pdf_tools"],
        "multimedia": ["media_tools"],
        "p2p_networking": ["p2p_tools", "p2p_workflow_tools"],
        "knowledge_graphs": ["graph_tools"],
        # Current search implementations are primarily medical research scrapers.
        "search": ["medical_research_scrapers", "search_tools"],
        "dashboards": ["dashboard_tools"],
        "monitoring": ["monitoring_tools"],
        "error_reporting": ["investigation_tools"],
        "analytics": ["analysis_tools"],
        "ipfs": ["ipfs_tools", "ipfs_cluster_tools"],
    }

    selected: List[str] = []

    # 0) Simple substring match is the most reliable heuristic.
    for cat in tool_categories:
        c = cat.lower()
        if fid in c or c in fid:
            selected.append(cat)

    # 1) Manual seeds first.
    for cat in manual.get(fid, []):
        if cat in tool_categories:
            selected.append(cat)

    # 2) Token-based scoring for additional categories.
    feature_tokens = set(_tokenize(fid))
    scored: List[Tuple[int, str]] = []
    for cat in tool_categories:
        score = _score_category_for_feature(feature_tokens, cat, tool_index)
        if score >= 10:
            scored.append((score, cat))

    scored.sort(reverse=True)
    for score, cat in scored:
        if cat in selected:
            continue
        selected.append(cat)
        if len(selected) >= 3:
            break

    # 3) Filter out categories with no indexed functions.
    filtered: List[str] = []
    for cat in selected:
        if _flatten_tool_index_for_categories(tool_index, [cat]):
            filtered.append(cat)
    return sorted(set(filtered))


def _extract_requirement_strs(node: ast.AST) -> List[str]:
    """Recursively extract requirement spec strings from a setup.py AST node."""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple)):
        out: List[str] = []
        for elt in node.elts:
            out.extend(_extract_requirement_strs(elt))
        return out
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _extract_requirement_strs(node.left) + _extract_requirement_strs(node.right)
    if isinstance(node, ast.IfExp):
        # Static scan: include both branches.
        return _extract_requirement_strs(node.body) + _extract_requirement_strs(node.orelse)
    return []


def _normalize_dist_name(req: str) -> str:
    """Extract a best-effort distribution name from a requirement string."""

    s = (req or "").strip()
    if not s:
        return ""

    # Handle PEP 508 direct references: "name @ url"
    if " @ " in s:
        name = s.split(" @ ", 1)[0].strip()
        return name

    # Drop environment markers
    if ";" in s:
        s = s.split(";", 1)[0].strip()

    # Keep leading name until first version/operator/whitespace.
    for sep in ["==", ">=", "<=", "!=", "~=", ">", "<", "["]:
        if sep in s:
            s = s.split(sep, 1)[0].strip()
    s = s.split()[0].strip()
    return s


def _safe_parse_setup_extras_require(setup_py: Path) -> Dict[str, List[str]]:
    """Parse setup.py AST to extract extras_require mapping (best-effort, no exec)."""

    if not setup_py.exists():
        return {}

    try:
        tree = ast.parse(setup_py.read_text("utf-8"), filename=str(setup_py))
    except Exception:
        return {}

    out: Dict[str, List[str]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "setup":
            continue
        for kw in node.keywords or []:
            if kw.arg != "extras_require":
                continue
            if not isinstance(kw.value, ast.Dict):
                continue
            for k_node, v_node in zip(kw.value.keys or [], kw.value.values or []):
                if not isinstance(k_node, ast.Constant) or not isinstance(k_node.value, str):
                    continue
                extra_name = k_node.value
                reqs = _extract_requirement_strs(v_node)
                dist_names = sorted({n for n in (_normalize_dist_name(r) for r in reqs) if n})
                out[extra_name] = dist_names

    return out


def _iter_python_files_for_feature(feature_path: Path, kind: str, max_files: int = 200) -> Iterable[Path]:
    if kind == "module":
        yield feature_path
        return
    if kind not in {"package", "dir"}:
        return

    count = 0
    for py_file in sorted(feature_path.rglob("*.py"), key=lambda p: p.as_posix()):
        if "__pycache__" in py_file.parts:
            continue
        if py_file.name.startswith("_"):
            continue
        yield py_file
        count += 1
        if count >= max_files:
            return


def _safe_collect_import_toplevels(py_file: Path) -> Set[str]:
    """Return a set of imported top-level module names from a Python file."""

    try:
        text = py_file.read_text("utf-8")
    except Exception:
        return set()

    try:
        tree = ast.parse(text, filename=str(py_file))
    except Exception:
        return set()

    out: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names or []:
                name = (alias.name or "").split(".", 1)[0].strip()
                if name and not name.startswith("_"):
                    out.add(name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            mod = (node.module or "").split(".", 1)[0].strip()
            if mod and not mod.startswith("_"):
                out.add(mod)

    return out


def _build_extra_import_candidates(extras_require: Dict[str, List[str]]) -> Dict[str, Set[str]]:
    """Map extra name -> candidate import top-level module names."""

    known_import_map = {
        "beautifulsoup4": {"bs4"},
        "pillow": {"PIL"},
        "PyYAML": {"yaml"},
        "discord.py": {"discord"},
        "symbolicai": {"symai"},
        "sentence-transformers": {"sentence_transformers"},
        "llama-index": {"llama_index"},
        "yt-dlp": {"yt_dlp"},
        "ffmpeg-python": {"ffmpeg"},
        "pymupdf": {"fitz"},
        "python-docx": {"docx"},
        "python-pptx": {"pptx"},
        "faiss-cpu": {"faiss"},
    }

    out: Dict[str, Set[str]] = {}
    for extra, dists in extras_require.items():
        candidates: Set[str] = set()
        for dist in dists or []:
            dist_norm = dist.strip()
            if not dist_norm:
                continue
            candidates.add(dist_norm)
            candidates.add(dist_norm.replace("-", "_"))
            candidates.add(dist_norm.replace("_", "-"))
            mapped = known_import_map.get(dist_norm)
            if mapped:
                candidates |= {m.lower() for m in mapped}
        out[extra] = {c.lower() for c in candidates if c}
    return out


def _compute_weighted_extra_matches(
    imported_toplevels: Set[str],
    extras_import_candidates: Dict[str, Set[str]],
) -> List[str]:
    """Pick likely extras using weighted matches.

    We down-weight imports that appear in many extras (e.g., aiohttp).
    Score(extra) = sum(1 / freq(import)) for each matched import.

    This keeps Tier-0 behavior deterministic and reduces false positives.
    """

    imported = {m.lower() for m in imported_toplevels if m}
    ignore_extras = {"all", "dev", "test", "windows", "linux", "macos"}

    # Build inverse map: import -> number of extras that include it.
    freq: Dict[str, int] = {}
    for extra, candidates in extras_import_candidates.items():
        if extra in ignore_extras:
            continue
        for c in candidates:
            freq[c] = freq.get(c, 0) + 1

    scores: Dict[str, float] = {}
    match_counts: Dict[str, int] = {}
    for extra, candidates in extras_import_candidates.items():
        if extra in ignore_extras:
            continue
        matched = imported & candidates
        if not matched:
            continue
        score = 0.0
        for m in matched:
            score += 1.0 / float(freq.get(m, 1))
        scores[extra] = score
        match_counts[extra] = len(matched)

    # Thresholds:
    # - one strong unique-ish match is enough (score >= 0.75)
    # - or multiple weak matches
    likely = [
        extra
        for extra, score in scores.items()
        if score >= 0.75 or match_counts.get(extra, 0) >= 2
    ]

    # Deterministic order: best score first, then name.
    likely.sort(key=lambda e: (-scores.get(e, 0.0), e))
    return likely


def _detect_likely_extras_for_feature(
    feature_path: Path,
    kind: str,
    extras_import_candidates: Dict[str, Set[str]],
) -> List[str]:
    """Guess which extras may be required for a feature based on import AST."""

    imported: Set[str] = set()
    for py_file in _iter_python_files_for_feature(feature_path, kind=kind):
        imported |= _safe_collect_import_toplevels(py_file)

    return _compute_weighted_extra_matches(imported, extras_import_candidates)


def _safe_parse_setup_console_scripts(setup_py: Path) -> Dict[str, str]:
    """Parse setup.py AST to extract entry_points['console_scripts'].

    Returns mapping: command -> "module:function".

    This avoids executing setup.py (which could have side effects).
    Limitations:
    - Only supports literal dict/list/str AST forms.
    """

    if not setup_py.exists():
        return {}

    try:
        tree = ast.parse(setup_py.read_text("utf-8"), filename=str(setup_py))
    except Exception:
        return {}

    command_map: Dict[str, str] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "setup":
            continue

        for kw in node.keywords or []:
            if not kw.arg or kw.arg != "entry_points":
                continue
            entry_points = kw.value
            if not isinstance(entry_points, ast.Dict):
                continue

            for k_node, v_node in zip(entry_points.keys or [], entry_points.values or []):
                if not isinstance(k_node, ast.Constant) or k_node.value != "console_scripts":
                    continue
                if not isinstance(v_node, ast.List):
                    continue

                for elt in v_node.elts:
                    if not isinstance(elt, ast.Constant) or not isinstance(elt.value, str):
                        continue
                    s = elt.value
                    if "=" not in s:
                        continue
                    cmd, target = s.split("=", 1)
                    cmd = cmd.strip()
                    target = target.strip()
                    if cmd and target:
                        command_map[cmd] = target

    return command_map


def _module_exists_from_target(target: str, pkg_root: Path) -> bool:
    """Return True if the module portion of a console_script target exists.

    target is expected like "some.module:func".
    """

    if not target or ":" not in target:
        return False

    module_part = target.split(":", 1)[0].strip()
    if not module_part:
        return False

    # setup.py declares a py_module "ipfs_datasets_cli" at repo/ipfs_datasets_py/ipfs_datasets_cli.py
    if module_part == "ipfs_datasets_cli":
        return (REPO_ROOT / "ipfs_datasets_py" / "ipfs_datasets_cli.py").exists()

    if not module_part.startswith("ipfs_datasets_py."):
        return False

    rel = module_part.removeprefix("ipfs_datasets_py.")
    mod_path = pkg_root / (rel.replace(".", os.sep) + ".py")
    pkg_path = pkg_root / rel.replace(".", os.sep) / "__init__.py"
    return mod_path.exists() or pkg_path.exists()


def _compute_status(import_exists: bool, cli_modules: List[str], mcp_categories: List[str]) -> str:
    if import_exists and cli_modules and mcp_categories:
        return "wired"
    if import_exists and (cli_modules or mcp_categories):
        return "partial"
    return "missing"


def generate_matrix() -> Dict[str, object]:
    if not PKG_ROOT.exists():
        raise SystemExit(f"Package root not found: {PKG_ROOT}")

    tool_categories = _list_mcp_tool_categories(MCP_TOOLS_ROOT)
    tool_index = _index_mcp_tool_functions(MCP_TOOLS_ROOT)
    features = _iter_top_level_features(PKG_ROOT)

    extras_require = _safe_parse_setup_extras_require(SETUP_PY)
    extras_import_candidates = _build_extra_import_candidates(extras_require)

    console_scripts = _safe_parse_setup_console_scripts(SETUP_PY)
    console_script_report = [
        {
            "command": cmd,
            "target": target,
            "module_exists": _module_exists_from_target(target, PKG_ROOT),
        }
        for cmd, target in sorted(console_scripts.items())
    ]
    console_script_orphans = [x for x in console_script_report if not x.get("module_exists")]

    # Detect name collisions (e.g., audit/ package + audit.py module).
    counts: Dict[str, int] = {}
    for fid, _, _ in features:
        counts[fid] = counts.get(fid, 0) + 1

    rows: List[FeatureRow] = []
    for feature_id, kind, feature_path in features:
        display_id = feature_id if counts.get(feature_id, 0) == 1 else f"{feature_id}#{kind}"

        import_module = f"ipfs_datasets_py.{feature_id}"
        import_exists = bool(kind in {"package", "module"})

        public_exports: List[str] = []
        public_exports_source = "none"
        if kind == "package":
            public_exports, public_exports_source = _detect_public_exports_for_package(feature_path)

        likely_extras = _detect_likely_extras_for_feature(
            feature_path=feature_path,
            kind=kind,
            extras_import_candidates=extras_import_candidates,
        )

        cli_modules = _detect_cli_modules(feature_id, kind, feature_path, PKG_ROOT)
        cli_commands: List[str] = []
        for cmd, target in console_scripts.items():
            if target.startswith(f"ipfs_datasets_py.{feature_id}.") or target.startswith(f"ipfs_datasets_py.{feature_id}:"):
                cli_commands.append(cmd)
            # Special case: top-level CLI shim module.
            if feature_id == "cli" and target.startswith("ipfs_datasets_cli:"):
                cli_commands.append(cmd)

        cli_commands = sorted(set(cli_commands))
        mcp_cats = _map_feature_to_tool_categories(feature_id, tool_categories, tool_index)
        mcp_tool_functions = _flatten_tool_index_for_categories(tool_index, mcp_cats)

        notes: List[str] = []
        if kind == "dir":
            notes.append("not_importable_package")
        if not cli_modules:
            notes.append("no_cli_detected")
        if not mcp_cats:
            notes.append("no_mcp_tools_mapped")
        elif not mcp_tool_functions:
            notes.append("no_mcp_tool_functions_indexed")

        surfaces = WiringSurface(
            import_module=import_module,
            import_exists=import_exists,
            public_exports=public_exports,
            public_exports_source=public_exports_source,
            likely_extras=likely_extras,
            cli_modules=cli_modules,
            cli_commands=cli_commands,
            mcp_tool_categories=mcp_cats,
            mcp_tool_functions=mcp_tool_functions,
            notes=notes,
        )
        status = _compute_status(import_exists, cli_modules, mcp_cats)
        rows.append(
            FeatureRow(
                feature_id=display_id,
                kind=kind,
                path=str(feature_path.relative_to(REPO_ROOT).as_posix()),
                surfaces=surfaces,
                status=status,
            )
        )

    # Add a synthetic row for mcp_server itself.
    mcp_status = _compute_status(
        import_exists=(PKG_ROOT / "mcp_server" / "__init__.py").exists(),
        cli_modules=["ipfs_datasets_py.mcp_server.__main__"] if (PKG_ROOT / "mcp_server" / "__main__.py").exists() else [],
        mcp_categories=_list_mcp_tool_categories(MCP_TOOLS_ROOT),
    )
    rows.append(
        FeatureRow(
            feature_id="mcp_server",
            kind="package",
            path=str((PKG_ROOT / "mcp_server").relative_to(REPO_ROOT).as_posix()),
            surfaces=WiringSurface(
                import_module="ipfs_datasets_py.mcp_server",
                import_exists=(PKG_ROOT / "mcp_server" / "__init__.py").exists(),
                public_exports=_detect_public_exports_for_package(PKG_ROOT / "mcp_server")[0],
                public_exports_source=_detect_public_exports_for_package(PKG_ROOT / "mcp_server")[1],
                likely_extras=[],
                cli_modules=["ipfs_datasets_py.mcp_server.__main__"] if (PKG_ROOT / "mcp_server" / "__main__.py").exists() else [],
                cli_commands=[],
                mcp_tool_categories=_list_mcp_tool_categories(MCP_TOOLS_ROOT),
                mcp_tool_functions=_flatten_tool_index_for_categories(
                    tool_index,
                    _list_mcp_tool_categories(MCP_TOOLS_ROOT),
                ),
                notes=[],
            ),
            status=mcp_status,
        )
    )

    summary = {
        "repo_root": str(REPO_ROOT),
        "package_root": str(PKG_ROOT),
        "counts": {
            "total": len(rows),
            "wired": sum(1 for r in rows if r.status == "wired"),
            "partial": sum(1 for r in rows if r.status == "partial"),
            "missing": sum(1 for r in rows if r.status == "missing"),
        },
        "tool_categories": tool_categories,
        "tool_index": tool_index,
        "console_scripts": console_script_report,
        "console_scripts_orphaned": console_script_orphans,
        "extras_available": sorted(extras_require.keys()),
        "extras_index": {k: sorted(v) for k, v in sorted(extras_require.items())},
    }

    return {
        "summary": summary,
        "rows": [asdict(r) for r in rows],
    }


def _write_json(path: Path, data: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, data: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    summary = data.get("summary", {})
    counts = summary.get("counts", {})
    rows = data.get("rows", [])

    lines: List[str] = []
    lines.append("# IPFS Datasets Py – Feature Wiring Matrix (static scan)")
    lines.append("")
    lines.append("This report is generated by `scripts/generate_feature_wiring_matrix.py`.")
    lines.append("It is a static filesystem scan (no imports), intended to guide refactors.")
    lines.append("")
    lines.append(f"- Total: {counts.get('total', 0)}")
    lines.append(f"- Wired: {counts.get('wired', 0)}")
    lines.append(f"- Partial: {counts.get('partial', 0)}")
    lines.append(f"- Missing: {counts.get('missing', 0)}")
    lines.append("")

    scripts = summary.get("console_scripts", []) or []
    orphans = summary.get("console_scripts_orphaned", []) or []
    tool_index = summary.get("tool_index", {}) or {}
    extras_available = summary.get("extras_available", []) or []

    lines.append("## Console Scripts")
    lines.append("")
    lines.append("Console entrypoints parsed from `ipfs_datasets_py/setup.py` without executing it.")
    lines.append("")
    lines.append(f"- Total: {len(scripts)}")
    lines.append(f"- Orphaned (target module missing): {len(orphans)}")
    lines.append("")
    lines.append("| command | target | module exists |")
    lines.append("|---|---|---|")
    for row in scripts:
        cmd = str(row.get("command", ""))
        target = str(row.get("target", ""))
        exists = "yes" if bool(row.get("module_exists")) else "no"
        lines.append(f"| {cmd} | {target} | {exists} |")
    lines.append("")

    # Compact MCP tool index (category → function counts)
    lines.append("## MCP Tool Index (static)")
    lines.append("")
    lines.append("This is an AST-based scan of `mcp_server/tools/**.py` (no imports).")
    lines.append("")
    lines.append("| category | modules | functions | example functions |")
    lines.append("|---|---:|---:|---|")
    for category in sorted(tool_index.keys()):
        modules = tool_index.get(category, {}) or {}
        module_count = len(modules)
        func_count = sum(len(v or []) for v in modules.values())
        examples: List[str] = []
        for mod_name in sorted(modules.keys()):
            for fn in modules.get(mod_name, [])[:3]:
                examples.append(fn)
            if len(examples) >= 6:
                break
        ex_s = ", ".join(examples[:6])
        lines.append(f"| {category} | {module_count} | {func_count} | {ex_s} |")
    lines.append("")

    lines.append("## Extras (from setup.py)")
    lines.append("")
    lines.append("Parsed from `ipfs_datasets_py/setup.py` without executing it.")
    lines.append("")
    lines.append(f"- Extras available: {len(extras_available)}")
    if extras_available:
        lines.append("- " + ", ".join(str(x) for x in extras_available))
    lines.append("")

    lines.append("## Rows")
    lines.append("")
    lines.append("| feature | kind | path | import | public exports | extras | mcp tool functions | cli commands | cli modules | mcp tool categories | status | notes |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")

    for r in rows:
        feature_id = str(r.get("feature_id", ""))
        kind = str(r.get("kind", ""))
        path_s = str(r.get("path", ""))
        surfaces = r.get("surfaces", {}) or {}
        import_module = str(surfaces.get("import_module", ""))
        public_exports = surfaces.get("public_exports", []) or []
        public_exports_source = str(surfaces.get("public_exports_source", "none"))
        likely_extras = surfaces.get("likely_extras", []) or []
        mcp_tool_functions = surfaces.get("mcp_tool_functions", []) or []
        cli_commands = surfaces.get("cli_commands", []) or []
        cli_modules = surfaces.get("cli_modules", []) or []
        mcp_cats = surfaces.get("mcp_tool_categories", []) or []
        status = str(r.get("status", ""))
        notes = surfaces.get("notes", []) or []

        exports_preview = ""
        if public_exports:
            preview = ", ".join(str(x) for x in public_exports[:6])
            suffix = "" if len(public_exports) <= 6 else f" (+{len(public_exports) - 6})"
            exports_preview = f"{public_exports_source}:{preview}{suffix}"

        mcp_funcs_preview = ""
        if mcp_tool_functions:
            preview = ", ".join(str(x) for x in mcp_tool_functions[:6])
            suffix = "" if len(mcp_tool_functions) <= 6 else f" (+{len(mcp_tool_functions) - 6})"
            mcp_funcs_preview = f"{preview}{suffix}"

        extras_preview = ""
        if likely_extras:
            preview = ", ".join(str(x) for x in likely_extras[:6])
            suffix = "" if len(likely_extras) <= 6 else f" (+{len(likely_extras) - 6})"
            extras_preview = f"{preview}{suffix}"

        cli_cmd_s = "<br>".join(cli_commands) if cli_commands else ""
        cli_s = "<br>".join(cli_modules) if cli_modules else ""
        mcp_s = "<br>".join(mcp_cats) if mcp_cats else ""
        notes_s = "<br>".join(str(n) for n in notes) if notes else ""

        lines.append(
            "| "
            + " | ".join(
                [
                    feature_id,
                    kind,
                    path_s,
                    import_module,
                    exports_preview,
                    extras_preview,
                    mcp_funcs_preview,
                    cli_cmd_s,
                    cli_s,
                    mcp_s,
                    status,
                    notes_s,
                ]
            )
            + " |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    data = generate_matrix()

    out_json = DOCS_ROOT / "FEATURE_WIRING_MATRIX.json"
    out_md = DOCS_ROOT / "FEATURE_WIRING_MATRIX.md"

    _write_json(out_json, data)
    _write_markdown(out_md, data)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
