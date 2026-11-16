"""CIMP-RLS-11: refresh the module map after the release layout."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = REPO_ROOT / "docs" / "architecture" / "repository_module_map.json"
ARCHITECTURE = REPO_ROOT / "docs" / "ARCHITECTURE.md"
BOUNDARIES = REPO_ROOT / "docs" / "architecture" / "module_boundaries.md"
SCHEMA = "complaint-generator/repository-module-map@1"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
TASK_ID = "CIMP-MOD-01"
LARGEST_PATH = "applications/complaint_workspace.py"
LARGEST_LIMIT = 15
WALK_SKIP_DIRECTORIES = (
    ".git",
    ".venv",
    "__pycache__",
    "artifacts",
    "complaint_generator.egg-info",
    "data",
    "external",
    "node_modules",
    "output",
    "statefiles",
    "workspace",
)
EXTRACTION_PATHS = (
    "mediator/mediator.py",
    "applications/complaint_workspace.py",
    "scripts/synthesize_hacc_complaint.py",
    "complaint_phases/denoiser.py",
    "applications/dashboard_ui.py",
    "applications/dashboard_hub.py",
    "mediator/claim_support_hooks.py",
)
ABSENT_ARCHITECTURE_STRINGS = (
    "10,852 lines",
    "7,881 lines",
    "6,933 lines",
    "5,691 lines",
    "5,562 lines",
    "5,309 lines",
    "Browser-based UI (future)",
    "RESTful API for integrations (future)",
    "docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
)
LINE_FLOORS = (
    ("applications/document_review.py", 921),
    ("complaint_phases/dependency_graph_timeline.py", 504),
    ("complaint_phases/document_pipeline_chronology.py", 800),
    ("adversarial_harness/optimizer_workflow.py", 800),
    ("mediator/claim_support_retrieval.py", 650),
    ("complaint_phases/intake_case_temporal.py", 540),
    ("integrations/ipfs_datasets/canonical_formalization.py", 700),
    ("complaint_phases/document_optimization_guidance.py", 720),
)
LOCKED_DOCUMENTS = {
    "docs/architecture/consolidation_modules.md": "0fe1e10d04ffe3949eac0266ba30675535b9ff8a438c3351bd9d4c4a82878e2e",
    "docs/architecture/module_boundaries.md": "ea85b8f33fa2214e464ebbec700c715c3f9274b58677395141bc90f70815dea8",
    "docs/architecture/module_seams.md": "3d811e249073b56928553e16ce25a41b1385072993d952dab582ccb58cd06256",
}
ROOT_MARKDOWN = {
    "README.md",
    "DOCUMENTATION_INDEX.md",
    "CONTRIBUTING.md",
    "TESTING.md",
    "TODO.md",
}
ROOT_SHIMS = (
    "intake_status.py",
    "workflow_phase_guidance.py",
    "document_pipeline.py",
    "document_optimization.py",
    "claim_support_review.py",
)
ROOT_CONFIGS = {
    "config.adversarial_autopatch_demo.json",
    "config.adversarial_autopatch_live.json",
    "config.adversarial_autopatch_live_batch.json",
    "config.adversarial_autopatch_live_multibackend.json",
    "config.huggingface_router.json",
    "config.llm_router.json",
    "config.review_surface.huggingface_router.json",
    "config.review_surface.json",
}
RELEASE_NOTE = "docs" + "/" + "RELEASE.md"
ROOT_RELEASE = "docs/architecture/root_release.md"
CURRENT_LAYOUT = "docs/architecture/current_layout.md"
OWNER_CURRENCY = "docs/architecture/owner_currency.md"
COHESIVE_MOVES = "docs/architecture/cohesive_moves.md"
ABSENT_GENERATED = (
    "drift_report_mcp.json",
    "complaint_generator.egg-info/PKG-INFO",
)
GITIGNORE_MARKERS = (
    "drift_report_mcp.json",
    "*.egg-info/",
)
FACADE_STEM = "ipfs_" + "accel" + "erate"
_ROW = re.compile(r"^\| `([^`]+)` \| (\d+) lines \|", re.MULTILINE)
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_HEADING = "### Current Extraction Priorities"


def _line_count(relative: str) -> int:
    return len((REPO_ROOT / relative).read_text(encoding="utf-8").splitlines())


def _require_line_floor(count: int, floor: int, label: str) -> None:
    if count < floor:
        raise AssertionError(f"{label} slipped below floor {floor}: {count}")


def _require_locked_digest(path: Path, expected: str) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise AssertionError(f"locked document changed: {path}")


def _discover_packages(root: Path) -> list[dict]:
    packages = []
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if not child.is_dir() or child.name.startswith("."):
            continue
        init = child / "__init__.py"
        try:
            is_package = init.is_file()
        except OSError:
            continue
        if not is_package:
            continue
        packages.append(
            {
                "name": child.name,
                "path": child.name,
                "init_path": f"{child.name}/__init__.py",
                "init_byte_size": init.stat().st_size,
            }
        )
    return packages


def _discover_largest(root: Path, limit: int = LARGEST_LIMIT) -> list[dict]:
    skip = set(WALK_SKIP_DIRECTORIES)
    found: list[tuple[int, str]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        relative = Path(dirpath).relative_to(root)
        parts = relative.parts
        if parts and (parts[0] in skip or parts[0].startswith(".")):
            dirnames[:] = []
            continue
        dirnames[:] = [name for name in dirnames if name not in skip and not name.startswith(".")]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            file_path = Path(dirpath) / filename
            try:
                size = file_path.stat().st_size
            except OSError:
                continue
            found.append((size, file_path.relative_to(root).as_posix()))
    found.sort(key=lambda item: (-item[0], item[1]))
    return [
        {"rank": index, "path": path, "byte_size": size}
        for index, (size, path) in enumerate(found[:limit], start=1)
    ]


def _walk_size_records(node: object, records: list[dict]) -> None:
    if isinstance(node, dict):
        if "path" in node and "byte_size" in node:
            records.append(node)
        if "init_path" in node and "init_byte_size" in node:
            records.append({"path": node["init_path"], "byte_size": node["init_byte_size"]})
        for value in node.values():
            _walk_size_records(value, records)
    elif isinstance(node, list):
        for item in node:
            _walk_size_records(item, records)


def _extraction_rows(text: str) -> list[tuple[str, int]]:
    start = text.index(_HEADING)
    body = text[start:]
    next_heading = body.find("\n### ", 1)
    section = body if next_heading < 0 else body[:next_heading]
    return [(match.group(1), int(match.group(2))) for match in _ROW.finditer(section)]


def _link_targets(text: str) -> list[str]:
    return [match.group(1) for match in _LINK.finditer(text)]


def _discover_interfaces() -> list[Path]:
    skip = set(WALK_SKIP_DIRECTORIES)
    found = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT, followlinks=False):
        relative = Path(dirpath).relative_to(REPO_ROOT)
        parts = relative.parts
        if parts and (parts[0] in skip or parts[0].startswith(".")):
            dirnames[:] = []
            continue
        dirnames[:] = [name for name in dirnames if name not in skip and not name.startswith(".")]
        if "interface.py" in filenames:
            found.append(Path(dirpath) / "interface.py")
    return sorted(found, key=lambda item: item.relative_to(REPO_ROOT).as_posix())


def _assigned_constant(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{path} does not assign {name}")


def _boundary_sections(text: str) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    heading = None
    bullets: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading is not None:
                sections.append((heading, bullets))
            heading = line[3:].strip()
            bullets = []
            continue
        if heading is not None and line.startswith("- `") and line.endswith("`"):
            bullets.append(line[3:-1])
    if heading is not None:
        sections.append((heading, bullets))
    return sections


def _defines_function_or_class(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for node in ast.walk(tree))


def test_module_map_matches_the_tree() -> None:
    document = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    assert document["schema"] == SCHEMA
    assert document["task_id"] == TASK_ID
    assert document["source_files_moved"] is True
    assert document["source_files_rewritten"] is False
    assert document["inventory_policy"]["walk_skip_directories"] == list(WALK_SKIP_DIRECTORIES)
    assert document["packages"] == _discover_packages(REPO_ROOT)
    largest = _discover_largest(REPO_ROOT)
    assert document["largest_python_modules"] == largest
    assert largest[0]["path"] == LARGEST_PATH
    assert len(largest) == LARGEST_LIMIT
    records: list[dict] = []
    _walk_size_records(document, records)
    mismatches = []
    for record in records:
        path = REPO_ROOT / record["path"]
        if not path.is_file():
            mismatches.append(f"{record['path']} missing")
            continue
        actual = path.stat().st_size
        if actual != record["byte_size"]:
            mismatches.append(f"{record['path']} map={record['byte_size']} tree={actual}")
    assert mismatches == []


def test_architecture_size_column_matches_splitlines() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    rows = _extraction_rows(text)
    assert [path for path, _count in rows] == list(EXTRACTION_PATHS)
    assert "applications/dashboard_hub.py" in EXTRACTION_PATHS
    for path, recorded in rows:
        assert recorded == _line_count(path), path
    for absent in ABSENT_ARCHITECTURE_STRINGS:
        assert absent not in text


def test_sibling_floors_hold() -> None:
    for relative, floor in LINE_FLOORS:
        _require_line_floor(_line_count(relative), floor, relative)


def test_floor_slip_fails() -> None:
    with pytest.raises(AssertionError, match="slipped below floor"):
        _require_line_floor(920, 921, "document_review.py")


def test_locked_architecture_documents_keep_their_digests() -> None:
    for relative, digest in LOCKED_DOCUMENTS.items():
        _require_locked_digest(REPO_ROOT / relative, digest)


def test_release_notes_and_generated_root_files() -> None:
    readme_targets = _link_targets((REPO_ROOT / "README.md").read_text(encoding="utf-8"))
    assert RELEASE_NOTE in readme_targets
    assert CURRENT_LAYOUT in readme_targets
    assert (REPO_ROOT / RELEASE_NOTE).is_file()
    assert (REPO_ROOT / CURRENT_LAYOUT).is_file()
    index_targets = _link_targets((REPO_ROOT / "DOCUMENTATION_INDEX.md").read_text(encoding="utf-8"))
    for link in (ROOT_RELEASE, RELEASE_NOTE, OWNER_CURRENCY, COHESIVE_MOVES):
        assert link in index_targets
        assert (REPO_ROOT / link).is_file()
    for relative in ABSENT_GENERATED:
        assert not (REPO_ROOT / relative).exists()
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for marker in GITIGNORE_MARKERS:
        assert marker in gitignore
    found = {path.name for path in REPO_ROOT.glob("*.md") if path.is_file()}
    assert found == ROOT_MARKDOWN
    for name in ROOT_SHIMS:
        path = REPO_ROOT / name
        assert path.is_file()
        assert _line_count(name) <= 40
        assert _defines_function_or_class(path) is False
    configs = {path.name for path in REPO_ROOT.glob("config*.json") if path.is_file()}
    assert configs == ROOT_CONFIGS
    deployment = (REPO_ROOT / "docs" / "DEPLOYMENT.md").read_text(encoding="utf-8")
    assert "/home/complaint-app" not in deployment


def test_product_interfaces_match_boundary_headings() -> None:
    discovered = _discover_interfaces()
    relative = [path.relative_to(REPO_ROOT).as_posix() for path in discovered]
    facade = "integrations/" + FACADE_STEM + "/interface.py"
    assert facade in relative
    sections = _boundary_sections(BOUNDARIES.read_text(encoding="utf-8"))
    assert [heading for heading, _bullets in sections] == relative
    for path, (heading, bullets) in zip(discovered, sections):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert isinstance(tree, ast.Module)
        owners = [str(item) for item in _assigned_constant(path, "OWNER_MODULES")]
        assert heading == path.relative_to(REPO_ROOT).as_posix()
        assert bullets == owners
        assert _assigned_constant(path, "INTERFACE_SCHEMA") == INTERFACE_SCHEMA
        assert _assigned_constant(path, "INTERFACE_VERSION") == INTERFACE_VERSION
