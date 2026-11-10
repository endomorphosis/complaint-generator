"""CIMP-SEA-20: independent ratchet for the module-seam campaign."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = REPO_ROOT / "docs" / "architecture" / "repository_module_map.json"
SEAM_MAP = REPO_ROOT / "docs" / "architecture" / "module_seams.md"
SIBLING_MAP = REPO_ROOT / "docs" / "architecture" / "consolidation_modules.md"
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
ROOT_MARKDOWN = {
    "README.md",
    "DOCUMENTATION_INDEX.md",
    "CONTRIBUTING.md",
    "TESTING.md",
    "TODO.md",
}
ROOT_DOCS = (
    "README.md",
    "DOCUMENTATION_INDEX.md",
    "CONTRIBUTING.md",
    "TESTING.md",
)
ROOT_SHIMS = (
    "intake_status.py",
    "workflow_phase_guidance.py",
    "document_pipeline.py",
    "document_optimization.py",
    "claim_support_review.py",
)
SEAM_ROWS = (
    ("applications/complaint_workspace_mike.py", "applications/complaint_workspace.py"),
    ("mediator/mediator_follow_up_queries.py", "mediator/mediator.py"),
    ("complaint_phases/document_pipeline_email.py", "complaint_phases/document_pipeline.py"),
    ("mediator/claim_support_testimony.py", "mediator/claim_support_hooks.py"),
    ("complaint_phases/denoiser_question_disposition.py", "complaint_phases/denoiser.py"),
    ("adversarial_harness/optimizer_ui_feedback.py", "adversarial_harness/optimizer.py"),
    ("mediator/evidence_scraper_queue.py", "mediator/evidence_hooks.py"),
    ("adversarial_harness/session_document_fallback.py", "adversarial_harness/session.py"),
    ("integrations/ipfs_datasets/canonical_legal_ir.py", "integrations/ipfs_datasets/logic.py"),
    ("integrations/ipfs_datasets/legal_corpus.py", "integrations/ipfs_datasets/legal.py"),
    ("mediator/hook_runtime_remote.py", "mediator/hook_runtime.py"),
    ("mediator/formal_document_chronology.py", "mediator/formal_document.py"),
    ("integrations/private_workspace_transfer.py", "integrations/private_storage.py"),
)
CONSOLIDATION_ROWS = (
    ("complaint_phases/intake_status.py", "intake_status.py"),
    ("complaint_phases/workflow_phase_guidance.py", "workflow_phase_guidance.py"),
    ("complaint_phases/document_pipeline.py", "document_pipeline.py"),
    ("complaint_phases/document_optimization.py", "document_optimization.py"),
    ("mediator/claim_support_review.py", "claim_support_review.py"),
    ("complaint_phases/document_pipeline_guidance.py", "complaint_phases/document_pipeline.py"),
    ("mediator/claim_support_review_sections.py", "mediator/claim_support_review.py"),
    ("complaint_phases/document_pipeline_readiness.py", "complaint_phases/document_pipeline.py"),
    ("complaint_phases/document_optimization_summaries.py", "complaint_phases/document_optimization.py"),
    ("applications/complaint_workspace_drafting.py", "applications/complaint_workspace.py"),
    ("mediator/intake_question_flow.py", "mediator/mediator.py"),
    ("complaint_phases/denoiser_questions.py", "complaint_phases/denoiser.py"),
    ("mediator/claim_support_diagnostics.py", "mediator/claim_support_hooks.py"),
    ("applications/complaint_workspace_research.py", "applications/complaint_workspace.py"),
    ("mediator/claim_follow_up_flow.py", "mediator/mediator.py"),
    ("complaint_phases/document_pipeline_render.py", "complaint_phases/document_pipeline.py"),
    ("mediator/claim_support_recommendations.py", "mediator/claim_support_hooks.py"),
    ("complaint_phases/denoiser_bindings.py", "complaint_phases/denoiser.py"),
    ("applications/dashboard_hub.py", "applications/dashboard_ui.py"),
    ("adversarial_harness/optimizer_fallback.py", "adversarial_harness/optimizer.py"),
    ("complaint_phases/knowledge_graph_extraction.py", "complaint_phases/knowledge_graph.py"),
    ("complaint_phases/intake_case_open_items.py", "complaint_phases/intake_case_file.py"),
    ("complaint_phases/document_optimization_support.py", "complaint_phases/document_optimization.py"),
    ("mediator/claim_support_review_followups.py", "mediator/claim_support_review.py"),
    ("mediator/hook_runtime_dispatch.py", "mediator/hook_runtime.py"),
    ("mediator/legal_authority_storage.py", "mediator/legal_authority_hooks.py"),
    ("complaint_phases/dependency_graph_readiness.py", "complaint_phases/dependency_graph.py"),
    ("adversarial_harness/session_intake.py", "adversarial_harness/session.py"),
    ("mediator/evidence_record_store.py", "mediator/evidence_hooks.py"),
    ("mediator/formal_document_render.py", "mediator/formal_document.py"),
    ("mediator/workflow_action_steps.py", "mediator/workflow_service.py"),
    ("integrations/ipfs_datasets/graph_queries.py", "integrations/ipfs_datasets/graphs.py"),
    ("applications/complaint_workspace_handlers.py", "applications/complaint_workspace.py"),
    ("mediator/mediator_gap_packets.py", "mediator/mediator.py"),
    ("complaint_phases/document_pipeline_legacy.py", "complaint_phases/document_pipeline.py"),
)
NEW_FLOORS = (
    ("applications/complaint_workspace.py", 16750, None),
    ("applications/complaint_workspace_mike.py", None, 450),
    ("mediator/mediator.py", 11550, None),
    ("mediator/mediator_follow_up_queries.py", None, 320),
    ("complaint_phases/document_pipeline.py", 9050, None),
    ("complaint_phases/document_pipeline_email.py", None, 300),
    ("mediator/claim_support_hooks.py", 8900, None),
    ("mediator/claim_support_testimony.py", None, 400),
    ("complaint_phases/denoiser.py", 7450, None),
    ("complaint_phases/denoiser_question_disposition.py", None, 320),
    ("adversarial_harness/optimizer.py", 5850, None),
    ("adversarial_harness/optimizer_ui_feedback.py", None, 700),
    ("mediator/evidence_hooks.py", 3400, None),
    ("mediator/evidence_scraper_queue.py", None, 280),
    ("adversarial_harness/session.py", 3450, None),
    ("adversarial_harness/session_document_fallback.py", None, 320),
    ("integrations/ipfs_datasets/logic.py", 8850, None),
    ("integrations/ipfs_datasets/canonical_legal_ir.py", None, 800),
    ("integrations/ipfs_datasets/legal.py", 5100, None),
    ("integrations/ipfs_datasets/legal_corpus.py", None, 800),
    ("mediator/hook_runtime.py", 4000, None),
    ("mediator/hook_runtime_remote.py", None, 450),
    ("mediator/formal_document.py", 2200, None),
    ("mediator/formal_document_chronology.py", None, 280),
    ("integrations/private_storage.py", 9200, None),
    ("integrations/private_workspace_transfer.py", None, 400),
)
EARLIER_FLOORS = (
    ("applications/complaint_workspace_research.py", None, 850),
    ("mediator/claim_follow_up_flow.py", None, 1100),
    ("complaint_phases/document_pipeline_render.py", None, 600),
    ("mediator/claim_support_recommendations.py", None, 700),
    ("complaint_phases/denoiser_bindings.py", None, 500),
    ("applications/dashboard_hub.py", None, 4500),
    ("applications/dashboard_ui.py", 1200, None),
    ("adversarial_harness/optimizer_fallback.py", None, 700),
    ("complaint_phases/knowledge_graph_extraction.py", None, 900),
    ("complaint_phases/intake_case_open_items.py", None, 950),
    ("complaint_phases/document_optimization_support.py", None, 550),
    ("mediator/claim_support_review_followups.py", None, 600),
    ("mediator/hook_runtime_dispatch.py", None, 500),
    ("mediator/legal_authority_storage.py", None, 500),
    ("complaint_phases/dependency_graph_readiness.py", None, 1800),
    ("adversarial_harness/session_intake.py", None, 1600),
    ("mediator/evidence_record_store.py", None, 700),
    ("mediator/formal_document_render.py", None, 700),
    ("mediator/workflow_action_steps.py", None, 500),
    ("integrations/ipfs_datasets/graph_queries.py", None, 650),
    ("applications/complaint_workspace_handlers.py", None, 700),
    ("mediator/mediator_gap_packets.py", None, 750),
    ("complaint_phases/document_pipeline_legacy.py", None, 500),
)
_ROW = re.compile(r"^\| `([^`]+)` \| `([^`]+)` \|$")
_INLINE = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
_DEFINITION = re.compile(r"(?m)^\s{0,3}\[[^\]\n]+\]:[ \t]+(\S+)")
_AUTOLINK = re.compile(r"(?<![A-Za-z0-9_])<([^>\s]+)>")
_LAZY_PROBE = r"""
import importlib
import json
import sys

sys.path.insert(0, sys.argv[1])
for case in json.loads(sys.argv[2]):
    package = case["package"]
    mod = importlib.import_module(package)
    for stem in case["unloaded"]:
        qualified = package + "." + stem
        assert qualified not in sys.modules, qualified
    assert list(mod.__all__) == case["names"]
    for name, owner_stem in case["owners"].items():
        value = getattr(mod, name)
        owner = sys.modules[package + "." + owner_stem]
        assert getattr(owner, name) is value
    for name, owner_stem in case["identity"]:
        value = getattr(mod, name)
        assert value is getattr(sys.modules[package + "." + owner_stem], name)
    for name, kind in case["kinds"]:
        value = getattr(mod, name)
        if kind == "type":
            assert isinstance(value, type)
        elif kind == "callable":
            assert callable(value)
        else:
            raise AssertionError(kind)
    for name, suffix in case["suffixes"]:
        value = getattr(mod, name)
        assert value.__module__.endswith(suffix), name
"""


def _lines(relative: str) -> int:
    text = (REPO_ROOT / relative).read_text(encoding="utf-8")
    ast.parse(text, filename=relative)
    return len(text.splitlines())


def _require_floor(relative: str, maximum: int | None, minimum: int | None) -> None:
    count = _lines(relative)
    if maximum is not None:
        assert count <= maximum, f"{relative} has {count} lines"
    if minimum is not None:
        assert count >= minimum, f"{relative} has {count} lines"


def _packages(root: Path) -> list[dict]:
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


def _largest(root: Path, skip: set[str], limit: int) -> list[dict]:
    found: list[tuple[int, str]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        relative = Path(dirpath).relative_to(root)
        parts = relative.parts
        if parts and (parts[0] in skip or parts[0].startswith(".")):
            dirnames[:] = []
            continue
        dirnames[:] = [
            name
            for name in dirnames
            if name not in skip and not name.startswith(".") and name != "__pycache__"
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


def _recorded_sizes(node) -> list[tuple[str, int]]:
    found = []
    if isinstance(node, dict):
        if "path" in node and "byte_size" in node:
            found.append((node["path"], node["byte_size"]))
        if "init_path" in node and "init_byte_size" in node:
            found.append((node["init_path"], node["init_byte_size"]))
        for value in node.values():
            found.extend(_recorded_sizes(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_recorded_sizes(item))
    return found


def _load_map() -> dict:
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def _percent_decode(text: str) -> str:
    parts = text.split("%")
    decoded = [parts[0]]
    for part in parts[1:]:
        if len(part) >= 2:
            try:
                decoded.append(bytes.fromhex(part[:2]).decode("utf-8") + part[2:])
                continue
            except ValueError:
                pass
        decoded.append("%" + part)
    return "".join(decoded)


def _destination(raw: str) -> str | None:
    text = raw.strip()
    if text.startswith("<") and ">" in text:
        text = text[1 : text.find(">")].strip()
    elif " " in text:
        text = text.split()[0]
    if not text or text.startswith("#") or "://" in text or text.startswith("mailto:"):
        return None
    text = _percent_decode(text.split("#", 1)[0].split("?", 1)[0].strip())
    return text or None


def _targets(text: str) -> list[str]:
    raws = [match.group(1) for match in _INLINE.finditer(text)]
    raws.extend(match.group(1) for match in _DEFINITION.finditer(text))
    for match in _AUTOLINK.finditer(text):
        candidate = match.group(1)
        if "://" in candidate or "@" in candidate:
            continue
        if "/" in candidate or candidate.endswith((".md", ".py", ".json", ".yml")):
            raws.append(candidate)
    return [target for raw in raws if (target := _destination(raw)) is not None]


def _table_rows(path: Path) -> tuple[tuple[str, str], ...]:
    text = path.read_text(encoding="utf-8")
    separators = [line for line in text.splitlines() if line.startswith("| ---")]
    assert separators == ["| --- | --- |"]
    rows = [match.groups() for match in (_ROW.match(line) for line in text.splitlines()) if match]
    return tuple(rows)


def _assigned_constant(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{path} does not assign {name}")


def _product_interfaces() -> list[Path]:
    found = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT, followlinks=False):
        relative = Path(dirpath).relative_to(REPO_ROOT)
        parts = relative.parts
        if parts and (parts[0] in WALK_SKIP_DIRECTORIES or parts[0].startswith(".")):
            dirnames[:] = []
            continue
        dirnames[:] = [
            name
            for name in dirnames
            if name not in WALK_SKIP_DIRECTORIES and not name.startswith(".")
        ]
        if "interface.py" in filenames:
            found.append(Path(dirpath) / "interface.py")
    return sorted(found, key=lambda item: item.relative_to(REPO_ROOT).as_posix())


def _facade_stem() -> str:
    return "ipfs_" + "accel" + "erate"


def _lazy_cases() -> list[dict]:
    stem = _facade_stem()
    facade_names = [
        "COMPLAINT_PROVIDER_ALIASES",
        "accel" + "erate_provider_name",
        "load_embedding_symbols",
        "load_llm_symbols",
        "load_multimodal_symbols",
        "normalize_" + "accel" + "erate_provider",
    ]
    mike_owners = {
        "apply_mike_llm_router_patch": "llm_patch",
        "MIKE_LLM_PATCH_VERSION": "llm_patch",
        "load_skill": "skills",
        "list_skill_ids": "skills",
        "SKILLS_DIR": "skills",
    }
    logic_names = [
        "Action",
        "Conjunction",
        "DeonticKnowledgeBase",
        "DeonticModality",
        "DeonticStatement",
        "Disjunction",
        "Frame",
        "FrameKnowledgeBase",
        "FrameSlotEvidence",
        "CANONICAL_COMPILER_CAPABILITY_SCHEMA",
        "CanonicalCompilerCapability",
        "CanonicalCompilerSupport",
        "FormalLogicCapability",
        "FormalLogicCapabilityError",
        "FormalLogicDegradedError",
        "FormalLogicOperation",
        "FormalLogicUnavailableError",
        "Implication",
        "LogicalOperator",
        "LogicCapabilityState",
        "LogicCapabilityStatus",
        "capability_state_from_payload",
        "classify_canonical_compiler_capability",
        "Negation",
        "Party",
        "Predicate",
        "Proposition",
        "TemporalOperator",
        "TimeInterval",
    ]
    logic_owners = {
        name: (
            "frames"
            if name.startswith("Frame")
            else "core"
            if name[:1].isupper() and name not in {
                "CANONICAL_COMPILER_CAPABILITY_SCHEMA",
                "CanonicalCompilerCapability",
                "CanonicalCompilerSupport",
                "FormalLogicCapability",
                "FormalLogicCapabilityError",
                "FormalLogicDegradedError",
                "FormalLogicOperation",
                "FormalLogicUnavailableError",
                "LogicCapabilityState",
                "LogicCapabilityStatus",
            }
            else "capabilities"
        )
        for name in logic_names
    }
    render_names = [
        "HAS_REPORTLAB",
        "build_case_caption_table",
        "build_case_caption_text_lines",
        "build_caption_party_block_html",
        "build_caption_party_block_lines",
        "build_case_detail_lines",
        "make_page_footer_renderer",
    ]
    integration_owners = {
        "IPFSDatasetsAdapter": "adapter",
        "detect_ipfs_datasets_capabilities": "adapter",
        "CapabilityCatalog": "contracts",
        "CapabilityStatus": "contracts",
        "NormalizedRetrievalBundle": "contracts",
        "NormalizedRetrievalRecord": "contracts",
        "IntegrationFeatureFlags": "settings",
        "RetrievalOrchestrator": "retrieval_orchestrator",
        "ProvenanceRecord": "provenance",
        "build_provenance_record": "provenance",
        "TTLCache": "caching",
        "VectorRetrievalAugmentor": "vector_tools",
        "GraphRetrievalAugmentor": "graph_tools",
        "GraphAwareRetrievalReranker": "graph_tools",
    }
    return [
        {
            "package": "integrations." + stem,
            "unloaded": ["routers"],
            "names": facade_names,
            "owners": {name: "routers" for name in facade_names},
            "identity": [],
            "kinds": [],
            "suffixes": [],
        },
        {
            "package": "integrations.mike",
            "unloaded": ["llm_patch", "skills"],
            "names": list(mike_owners),
            "owners": mike_owners,
            "identity": [],
            "kinds": [],
            "suffixes": [
                ["apply_mike_llm_router_patch", ".llm_patch"],
                ["load_skill", ".skills"],
            ],
        },
        {
            "package": "lib.formal_logic",
            "unloaded": ["capabilities", "core", "frames"],
            "names": logic_names,
            "owners": logic_owners,
            "identity": [["Action", "core"], ["Frame", "frames"]],
            "kinds": [],
            "suffixes": [],
        },
        {
            "package": "lib.document_render",
            "unloaded": ["reportlab_helpers"],
            "names": render_names,
            "owners": {name: "reportlab_helpers" for name in render_names},
            "identity": [["build_case_caption_text_lines", "reportlab_helpers"]],
            "kinds": [["build_case_caption_text_lines", "callable"]],
            "suffixes": [],
        },
        {
            "package": "mediator.integrations",
            "unloaded": ["adapter", "retrieval_orchestrator", "vector_tools", "graph_tools"],
            "names": list(integration_owners),
            "owners": integration_owners,
            "identity": [
                ["IPFSDatasetsAdapter", "adapter"],
                ["RetrievalOrchestrator", "retrieval_orchestrator"],
            ],
            "kinds": [
                ["IPFSDatasetsAdapter", "type"],
                ["RetrievalOrchestrator", "type"],
            ],
            "suffixes": [],
        },
    ]


def test_module_map_matches_the_tree() -> None:
    document = _load_map()
    assert document["schema"] == SCHEMA
    assert document["task_id"] == "CIMP-MOD-01"
    assert document["source_files_moved"] is True
    assert document["source_files_rewritten"] is False
    assert document["packages"] == _packages(REPO_ROOT)
    skip = set(document["inventory_policy"]["walk_skip_directories"])
    limit = document["inventory_policy"]["largest_python_module_limit"]
    assert limit == LARGEST_LIMIT
    largest = _largest(REPO_ROOT, skip, limit)
    assert document["largest_python_modules"] == largest
    assert len(largest) == LARGEST_LIMIT
    assert largest[0]["path"] == "applications/complaint_workspace.py"
    mismatches = []
    for relative, recorded in _recorded_sizes(document):
        path = REPO_ROOT / relative
        if not path.is_file():
            mismatches.append(f"{relative} missing")
            continue
        actual = path.stat().st_size
        if actual != recorded:
            mismatches.append(f"{relative} map={recorded} tree={actual}")
    assert mismatches == []


def test_new_seam_floors_hold() -> None:
    assert len(SEAM_ROWS) == 13
    for sibling, owner in SEAM_ROWS:
        for relative, maximum, minimum in NEW_FLOORS:
            if Path(relative).name in {Path(sibling).name, Path(owner).name} and relative in {sibling, owner}:
                _require_floor(relative, maximum, minimum)
    covered = {relative for relative, _maximum, _minimum in NEW_FLOORS}
    assert covered == {path for pair in SEAM_ROWS for path in pair}


def test_earlier_floors_and_root_shims_hold() -> None:
    for relative, maximum, minimum in EARLIER_FLOORS:
        _require_floor(relative, maximum, minimum)
    for name in ROOT_SHIMS:
        path = REPO_ROOT / name
        text = path.read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 40, name
        tree = ast.parse(text, filename=str(path))
        defined = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        assert defined == [], name
        delegated = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                delegated = True
            elif isinstance(node, ast.Call):
                func = node.func
                called = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
                if called in {"import_module", "spec_from_file_location", "module_from_spec", "exec_module"}:
                    delegated = True
        assert delegated, name


def test_five_package_imports_leave_owners_unloaded() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", _LAZY_PROBE, str(REPO_ROOT), json.dumps(_lazy_cases())],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout


def test_seam_and_consolidation_tables_match_source() -> None:
    assert _table_rows(SEAM_MAP) == SEAM_ROWS
    assert _table_rows(SIBLING_MAP) == CONSOLIDATION_ROWS


def test_root_docs_link_to_architecture_maps() -> None:
    found = {path.name for path in REPO_ROOT.glob("*.md") if path.is_file()}
    assert found == ROOT_MARKDOWN
    for name in ROOT_DOCS:
        document = REPO_ROOT / name
        targets = _targets(document.read_text(encoding="utf-8"))
        for target in (
            "docs/architecture/consolidation_modules.md",
            "docs/architecture/module_boundaries.md",
            "docs/architecture/module_seams.md",
        ):
            assert target in targets, name
            assert (document.parent / target).resolve().is_file(), f"{name} -> {target}"


def test_interface_schema_and_version_stay_assigned() -> None:
    discovered = _product_interfaces()
    assert discovered
    for path in discovered:
        assert _assigned_constant(path, "INTERFACE_SCHEMA") == INTERFACE_SCHEMA
        assert _assigned_constant(path, "INTERFACE_VERSION") == INTERFACE_VERSION
