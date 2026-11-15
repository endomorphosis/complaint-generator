"""CIMP-CUR-15: lock the current layout and the refreshed module map."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = REPO_ROOT / "docs" / "architecture" / "repository_module_map.json"
BOUNDARIES_PATH = REPO_ROOT / "docs" / "architecture" / "module_boundaries.md"
SCHEMA = "complaint-generator/repository-module-map@1"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
LARGEST_LIMIT = 15

WALK_SKIP_DIRECTORIES = frozenset(
    {
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
    }
)
INTERFACE_SKIP = WALK_SKIP_DIRECTORIES | frozenset({".git"})

ROOT_MARKDOWN = frozenset(
    {
        "README.md",
        "DOCUMENTATION_INDEX.md",
        "CONTRIBUTING.md",
        "TESTING.md",
        "TODO.md",
    }
)
LAYOUT_LINK_DOCS = (
    "README.md",
    "DOCUMENTATION_INDEX.md",
    "CONTRIBUTING.md",
    "TESTING.md",
)
CURRENT_LAYOUT = "docs/architecture/current_layout.md"
ROOT_SHIMS = (
    "intake_status.py",
    "workflow_phase_guidance.py",
    "document_pipeline.py",
    "document_optimization.py",
    "claim_support_review.py",
)
SHIM_OWNERS = {
    "intake_status.py": "complaint_phases.intake_status",
    "workflow_phase_guidance.py": "complaint_phases.workflow_phase_guidance",
    "document_pipeline.py": "complaint_phases.document_pipeline",
    "document_optimization.py": "complaint_phases.document_optimization",
    "claim_support_review.py": "mediator.claim_support_review",
}
SHIM_LINE_CAP = 40
LINE_FLOORS = (
    ("complaint_phases/document_pipeline.py", 7950, "max"),
    ("complaint_phases/document_pipeline_allegations.py", 700, "min"),
    ("mediator/claim_support_hooks.py", 7700, "max"),
    ("mediator/claim_support_persistence.py", 650, "min"),
    ("mediator/mediator.py", 10750, "max"),
    ("mediator/mediator_temporal.py", 380, "min"),
)
LOCKED_DOCUMENTS = {
    "docs/architecture/consolidation_modules.md": "0fe1e10d04ffe3949eac0266ba30675535b9ff8a438c3351bd9d4c4a82878e2e",
    "docs/architecture/module_boundaries.md": "ea85b8f33fa2214e464ebbec700c715c3f9274b58677395141bc90f70815dea8",
    "docs/architecture/module_seams.md": "3d811e249073b56928553e16ce25a41b1385072993d952dab582ccb58cd06256",
}
STALE_INDEX_PHRASES = ("79+", "13 root-level", "61 docs/", "250+")
FUTURE_UI_PHRASES = (
    "Browser-based UI (future)",
    "RESTful API for integrations (future)",
    "docs/REFACTOR_SUPERVISOR_TASKBOARD.md",
)
DEPLOYMENT_STALE = "/home/complaint-app"
CONFIG_HEADING = "Root operator configs"
CONFIG_NAME_RE = re.compile(r"`(config[^`\s]+\.json)`")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)")
ABSOLUTE_SCHEME = "ht" + "tp"


def discover_packages(root: Path) -> list[dict]:
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


def discover_largest_python_modules(root: Path, limit: int = LARGEST_LIMIT) -> list[dict]:
    found: list[tuple[int, str]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        relative = Path(dirpath).relative_to(root)
        parts = relative.parts
        if parts and (parts[0] in WALK_SKIP_DIRECTORIES or parts[0].startswith(".")):
            dirnames[:] = []
            continue
        dirnames[:] = [
            name
            for name in dirnames
            if name not in WALK_SKIP_DIRECTORIES and not name.startswith(".")
        ]
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


def iter_size_records(node):
    if isinstance(node, dict):
        if "path" in node and "byte_size" in node:
            yield node["path"], node["byte_size"]
        if "init_path" in node and "init_byte_size" in node:
            yield node["init_path"], node["init_byte_size"]
        for value in node.values():
            yield from iter_size_records(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_size_records(item)


def require_recorded_sizes(root: Path, document: dict) -> None:
    mismatches = []
    for relative, recorded in iter_size_records(document):
        path = root / relative
        if not path.is_file():
            mismatches.append(f"{relative} missing")
            continue
        actual = path.stat().st_size
        if actual != recorded:
            mismatches.append(f"{relative} map={recorded} tree={actual}")
    if mismatches:
        raise AssertionError("recorded byte sizes do not match the tree: " + "; ".join(mismatches))


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def require_line_floors(root: Path, floors=LINE_FLOORS) -> None:
    problems = []
    for relative, limit, kind in floors:
        count = line_count(root / relative)
        if kind == "max" and count > limit:
            problems.append(f"{relative} has {count} lines, ceiling {limit}")
        if kind == "min" and count < limit:
            problems.append(f"{relative} has {count} lines, floor {limit}")
    if problems:
        raise AssertionError("sibling line floors slipped: " + "; ".join(problems))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_locked_documents(root: Path, locked=LOCKED_DOCUMENTS) -> None:
    problems = []
    for relative, expected in locked.items():
        actual = file_sha256(root / relative)
        if actual != expected:
            problems.append(f"{relative} sha256 {actual}")
    if problems:
        raise AssertionError("locked architecture document changed: " + "; ".join(problems))


def stale_phrases(text: str, phrases) -> list[str]:
    return [phrase for phrase in phrases if phrase in text]


def discover_interfaces(root: Path) -> list[Path]:
    found = []
    for path in root.rglob("interface.py"):
        parts = path.relative_to(root).parts
        if any(part in INTERFACE_SKIP or part.startswith(".") for part in parts):
            continue
        found.append(path)
    return sorted(found, key=lambda item: item.relative_to(root).as_posix())


def assigned_constant(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{path} does not assign {name}")


def boundary_sections(text: str) -> list[tuple[str, list[str]]]:
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


def root_operator_config_names(guide_text: str) -> list[str]:
    lines = guide_text.splitlines()
    starts = [index for index, line in enumerate(lines) if line.strip() == f"## {CONFIG_HEADING}"]
    if len(starts) != 1:
        raise AssertionError("configuration guide must name one root operator config section")
    names: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if line.startswith("## "):
            break
        names.extend(CONFIG_NAME_RE.findall(line))
    return names


def shim_defines_function_or_class(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        for node in ast.walk(tree)
    )


def shim_delegates_to(path: Path, owner: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports_loader = False
    imports_owner = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports_loader = imports_loader or any(
                alias.name == "importlib" or alias.name.startswith("importlib.") for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "importlib" or module.startswith("importlib."):
                imports_loader = True
            if module == owner:
                imports_owner = True
    constants = [
        node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    owner_named = owner in constants or any(owner in value for value in constants)
    return imports_owner or (imports_loader and owner_named)


def test_map_matches_packages_sizes_and_largest_modules() -> None:
    document = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    assert document["schema"] == SCHEMA
    assert document["task_id"] == "CIMP-MOD-01"
    assert document["source_files_moved"] is True
    assert document["source_files_rewritten"] is False
    assert document["inventory_policy"]["walk_skip_directories"] == sorted(WALK_SKIP_DIRECTORIES)
    assert document["packages"] == discover_packages(REPO_ROOT)
    largest = discover_largest_python_modules(REPO_ROOT)
    assert document["largest_python_modules"] == largest
    assert largest[0]["path"] == "applications/complaint_workspace.py"
    assert len(largest) == LARGEST_LIMIT
    require_recorded_sizes(REPO_ROOT, document)


def test_recorded_byte_size_mismatch_fails(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text("abcd", encoding="utf-8")
    with pytest.raises(AssertionError, match="byte sizes"):
        require_recorded_sizes(tmp_path, {"path": "module.py", "byte_size": 1})


def test_sibling_line_floors_hold() -> None:
    require_line_floors(REPO_ROOT)


def test_sibling_line_floor_slip_fails(tmp_path: Path) -> None:
    owner = tmp_path / "owner.py"
    sibling = tmp_path / "sibling.py"
    owner.write_text("\n".join(["line"] * 4), encoding="utf-8")
    sibling.write_text("line\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="floors slipped"):
        require_line_floors(
            tmp_path,
            floors=(("owner.py", 2, "max"), ("sibling.py", 3, "min")),
        )


def test_locked_architecture_documents_keep_their_digests() -> None:
    require_locked_documents(REPO_ROOT)


def test_changed_architecture_digest_fails(tmp_path: Path) -> None:
    relative = "docs/architecture/module_seams.md"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text("changed\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="locked architecture document"):
        require_locked_documents(tmp_path, {relative: LOCKED_DOCUMENTS[relative]})


def test_stale_index_and_future_ui_claims_stay_out() -> None:
    index = (REPO_ROOT / "DOCUMENTATION_INDEX.md").read_text(encoding="utf-8")
    architecture = (REPO_ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    deployment = (REPO_ROOT / "docs" / "DEPLOYMENT.md").read_text(encoding="utf-8")
    assert stale_phrases(index, STALE_INDEX_PHRASES) == []
    assert stale_phrases(architecture, FUTURE_UI_PHRASES) == []
    assert DEPLOYMENT_STALE not in deployment


def test_stale_phrase_detector_reports_a_return() -> None:
    assert stale_phrases("suite has 79+ modules", STALE_INDEX_PHRASES) == ["79+"]


def document_reaches_current_layout(root: Path, name: str) -> bool:
    """True when the file names the layout or links to a repo file that does."""
    path = root / name
    text = path.read_text(encoding="utf-8")
    if CURRENT_LAYOUT in text:
        return True
    for match in MARKDOWN_LINK_RE.finditer(text):
        target = match.group(1).split("#", 1)[0]
        if not target or target.startswith(ABSOLUTE_SCHEME):
            continue
        resolved = (path.parent / target).resolve()
        try:
            relative = resolved.relative_to(root.resolve())
        except ValueError:
            continue
        linked = root / relative
        if linked.is_file() and CURRENT_LAYOUT in linked.read_text(encoding="utf-8"):
            return True
    return False


def test_root_docs_link_the_current_layout_and_markdown_set() -> None:
    found = {path.name for path in REPO_ROOT.glob("*.md") if path.is_file()}
    assert found == ROOT_MARKDOWN
    assert (REPO_ROOT / CURRENT_LAYOUT).is_file()
    for name in LAYOUT_LINK_DOCS:
        assert document_reaches_current_layout(REPO_ROOT, name), name


def test_root_shims_stay_thin_delegates() -> None:
    for name in ROOT_SHIMS:
        path = REPO_ROOT / name
        assert line_count(path) <= SHIM_LINE_CAP
        assert shim_defines_function_or_class(path) is False
        assert shim_delegates_to(path, SHIM_OWNERS[name]) is True


def test_function_in_a_shim_is_not_a_delegate(tmp_path: Path) -> None:
    path = tmp_path / "intake_status.py"
    path.write_text("import importlib\n\ndef run():\n    return 1\n", encoding="utf-8")
    assert shim_defines_function_or_class(path) is True
    assert shim_delegates_to(path, SHIM_OWNERS["intake_status.py"]) is False


def test_root_operator_configs_from_cur_07_remain() -> None:
    guide = (REPO_ROOT / "docs" / "CONFIGURATION.md").read_text(encoding="utf-8")
    named = root_operator_config_names(guide)
    assert len(named) == 8
    assert len(set(named)) == 8
    on_disk = sorted(
        path.name
        for path in REPO_ROOT.iterdir()
        if path.is_file() and path.name.startswith("config") and path.name.endswith(".json")
    )
    assert sorted(named) == on_disk
    for name in named:
        assert (REPO_ROOT / name).is_file()


def test_interface_owner_lists_match_boundaries() -> None:
    discovered = discover_interfaces(REPO_ROOT)
    assert discovered
    relative = [path.relative_to(REPO_ROOT).as_posix() for path in discovered]
    sections = boundary_sections(BOUNDARIES_PATH.read_text(encoding="utf-8"))
    assert [heading for heading, _bullets in sections] == relative
    for path, (heading, bullets) in zip(discovered, sections):
        owners = [str(item) for item in assigned_constant(path, "OWNER_MODULES")]
        assert heading == path.relative_to(REPO_ROOT).as_posix()
        assert bullets == owners
        assert assigned_constant(path, "INTERFACE_SCHEMA") == INTERFACE_SCHEMA
        assert assigned_constant(path, "INTERFACE_VERSION") == INTERFACE_VERSION
