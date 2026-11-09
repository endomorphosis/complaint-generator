"""CIMP-BND-20: independent ratchet for the module-boundary campaign."""

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = REPO_ROOT / "docs/architecture/repository_module_map.json"
BOUNDARIES = REPO_ROOT / "docs/architecture/module_boundaries.md"
SIBLING_MAP = REPO_ROOT / "docs/architecture/consolidation_modules.md"
SCHEMA = "complaint-generator/repository-module-map@1"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
SKIP_PARTS = {
    "external",
    ".git",
    "data",
    "artifacts",
    "output",
    "statefiles",
    "workspace",
    "node_modules",
}
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
REQUIRED_ROWS = (
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
METHOD_MOVES = (
    {
        "owner": "complaint_phases/dependency_graph.py",
        "sibling": "complaint_phases/dependency_graph_readiness.py",
        "qualifier": "dependency_graph_readiness",
        "owner_max": 2900,
        "sibling_min": 1800,
        "extracted": (
            ("DependencyGraph", "get_claim_readiness"),
            ("DependencyGraph", "get_blocker_follow_up_issues"),
            ("DependencyGraphBuilder", "build_from_claims"),
            ("DependencyGraphBuilder", "refresh_affected_dependencies"),
        ),
        "sentinel_class": "DependencyGraphBuilder",
        "sentinels": ("sync_intake_timeline_to_graph",),
    },
    {
        "owner": "adversarial_harness/session.py",
        "sibling": "adversarial_harness/session_intake.py",
        "qualifier": "session_intake",
        "owner_max": 3600,
        "sibling_min": 1600,
        "extracted": (
            ("AdversarialSession", "_inject_intake_prompt_questions"),
            ("AdversarialSession", "_reprioritize_candidates_for_intake_objectives"),
            ("AdversarialSession", "_summarize_intake_priority_coverage"),
            ("AdversarialSession", "_select_next_question"),
        ),
        "sentinel_class": "AdversarialSession",
        "sentinels": ("run",),
    },
    {
        "owner": "mediator/evidence_hooks.py",
        "sibling": "mediator/evidence_record_store.py",
        "qualifier": "evidence_record_store",
        "owner_max": 3500,
        "sibling_min": 700,
        "extracted": (
            ("EvidenceStateHook", "upsert_evidence_record"),
            ("EvidenceStateHook", "_initialize_schema"),
            ("EvidenceStateHook", "persist_scraper_run"),
            ("EvidenceStorageHook", "store_evidence"),
        ),
        "sentinel_class": "EvidenceStateHook",
        "sentinels": ("get_scraper_queue_state",),
    },
    {
        "owner": "mediator/formal_document.py",
        "sibling": "mediator/formal_document_render.py",
        "qualifier": "formal_document_render",
        "owner_max": 2300,
        "sibling_min": 700,
        "extracted": (
            ("ComplaintDocumentBuilder", "render_text"),
            ("ComplaintDocumentBuilder", "build"),
            ("ComplaintDocumentBuilder", "_write_docx"),
            ("ComplaintDocumentBuilder", "_write_pdf"),
        ),
        "sentinel_class": "ComplaintDocumentBuilder",
        "sentinels": ("_build_claims",),
    },
    {
        "owner": "mediator/workflow_service.py",
        "sibling": "mediator/workflow_action_steps.py",
        "qualifier": "workflow_action_steps",
        "owner_max": 2500,
        "sibling_min": 500,
        "extracted": (
            ("WorkflowActionService", "refresh_legal_dependency_graph"),
            ("WorkflowActionService", "apply_factual_correction"),
            ("WorkflowActionService", "_build_evidence_workflow_action_queue"),
            ("WorkflowActionService", "research_legal_source_gap"),
        ),
        "sentinel_class": "WorkflowActionService",
        "sentinels": ("apply_authorized_review_transition",),
    },
    {
        "owner": "applications/complaint_workspace.py",
        "sibling": "applications/complaint_workspace_handlers.py",
        "qualifier": "complaint_workspace_handlers",
        "owner_max": 16800,
        "sibling_min": 700,
        "extracted": (
            ("ComplaintWorkspaceRequestHandlers", "apply_terminal_graph_edit"),
            ("ComplaintWorkspaceRequestHandlers", "run_intake_chat_turn"),
            ("ComplaintWorkspaceService", "commit_factual_graph_revision"),
            ("ComplaintWorkspaceService", "resume_encrypted_interview"),
        ),
        "sentinel_class": "ComplaintWorkspaceService",
        "sentinels": ("_dispatch_mcp_tool",),
    },
    {
        "owner": "mediator/mediator.py",
        "sibling": "mediator/mediator_gap_packets.py",
        "qualifier": "mediator_gap_packets",
        "owner_max": 11650,
        "sibling_min": 750,
        "extracted": (
            ("Mediator", "build_inquiry_gap_context"),
            ("Mediator", "_build_alignment_evidence_tasks"),
            ("Mediator", "_build_authority_search_programs_for_task"),
            ("Mediator", "_build_claim_support_packets"),
        ),
        "sentinel_class": "Mediator",
        "sentinels": ("research_case_automatically",),
    },
    {
        "owner": "complaint_phases/document_pipeline.py",
        "sibling": "complaint_phases/document_pipeline_legacy.py",
        "qualifier": "document_pipeline_legacy",
        "owner_max": 9100,
        "sibling_min": 500,
        "extracted": (
            ("FormalComplaintDocumentBuilder", "_build_legacy_draft"),
            ("FormalComplaintDocumentBuilder", "_build_claim_support_temporal_handoff"),
            ("FormalComplaintDocumentBuilder", "_adapt_formal_complaint_to_package_draft"),
            ("FormalComplaintDocumentBuilder", "_render_draft_text"),
        ),
        "sentinel_class": "FormalComplaintDocumentBuilder",
        "sentinels": ("build_package",),
    },
)
FUNCTION_MOVE = {
    "owner": "integrations/ipfs_datasets/graphs.py",
    "sibling": "integrations/ipfs_datasets/graph_queries.py",
    "stem": "graph_queries",
    "owner_max": 3000,
    "sibling_min": 650,
    "extracted": (
        "query_graph_support",
        "persist_graph_snapshot",
        "extract_graph_from_text",
        "publish_private_graph_case_manifest",
    ),
    "sentinel": "attach_provenance_edges",
}
EARLIER_FLOORS = (
    ("applications/complaint_workspace_research.py", None, 850),
    ("mediator/claim_follow_up_flow.py", None, 1100),
    ("complaint_phases/document_pipeline_render.py", None, 600),
    ("mediator/claim_support_recommendations.py", None, 700),
    ("complaint_phases/denoiser_bindings.py", None, 500),
    ("applications/dashboard_hub.py", None, 4500),
    ("applications/dashboard_ui.py", 1200, None),
    ("adversarial_harness/optimizer.py", 5900, None),
    ("adversarial_harness/optimizer_fallback.py", None, 700),
    ("complaint_phases/knowledge_graph.py", 3900, None),
    ("complaint_phases/knowledge_graph_extraction.py", None, 900),
    ("complaint_phases/intake_case_file.py", 3700, None),
    ("complaint_phases/intake_case_open_items.py", None, 950),
    ("complaint_phases/document_optimization.py", 3600, None),
    ("complaint_phases/document_optimization_support.py", None, 550),
    ("mediator/claim_support_review.py", 4000, None),
    ("mediator/claim_support_review_followups.py", None, 600),
    ("mediator/hook_runtime.py", 4000, None),
    ("mediator/hook_runtime_dispatch.py", None, 500),
    ("mediator/legal_authority_hooks.py", 3700, None),
    ("mediator/legal_authority_storage.py", None, 500),
    ("complaint_phases/denoiser.py", 7400, None),
    ("mediator/claim_support_hooks.py", 8900, None),
)
DOC_MINIMUMS = {
    "docs/OBSERVABILITY_INDEX.md": 65,
    "docs/IPFS_DATASETS_PY_INTEGRATION.md": 9,
    "docs/REFINEMENT_STRATEGY_GUIDE.md": 7,
    "docs/PERFORMANCE_TUNING.md": 6,
    "docs/GRAPHRAG_REFACTORING_ROADMAP.md": 8,
    "docs/migration/LOGGING_MIGRATION_GUIDE.md": 5,
    "docs/optimizers/API_TYPE_CONTRACTS.md": 5,
    "docs/optimizers/PERFORMANCE_TUNING_GUIDE.md": 5,
    "docs/integration/CIRCUIT_BREAKER_GUIDE.md": 4,
    "docs/PRODUCTION_DEPLOYMENT_GUIDE.md": 3,
    "docs/metrics/PROMETHEUS_GUIDE.md": 3,
    "docs/tracing/OTEL_GUIDE.md": 3,
    "docs/optimizers/TROUBLESHOOTING_GUIDE.md": 5,
    "docs/COMPLAINT_ANALYSIS_EXAMPLES.md": 1,
    "docs/optimizers/DISTRIBUTED_ONTOLOGY_REFINEMENT.md": 2,
    "docs/optimizers/INTEGRATION_EXAMPLES.md": 8,
}
_ROW = re.compile(r"^\| `([^`]+)` \| `([^`]+)` \|$")
_INLINE = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
_DEFINITION = re.compile(r"(?m)^\s{0,3}\[[^\]\n]+\]:[ \t]+(\S+)")
_AUTOLINK = re.compile(r"(?<![A-Za-z0-9_])<([^>\s]+)>")


def _load_map() -> dict:
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def _lines(relative: str) -> int:
    return len((REPO_ROOT / relative).read_text(encoding="utf-8").splitlines())


def _parse(relative: str) -> ast.AST:
    path = REPO_ROOT / relative
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _methods(tree: ast.AST, class_name: str) -> dict:
    klass = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    return {
        node.name: node
        for node in klass.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _defined(tree: ast.AST) -> dict:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


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


def _discover_interfaces() -> list[Path]:
    found = []
    for path in REPO_ROOT.rglob("interface.py"):
        parts = path.relative_to(REPO_ROOT).parts
        if any(part in SKIP_PARTS or part.startswith(".") for part in parts):
            continue
        found.append(path)
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


def test_module_map_matches_the_tree() -> None:
    document = _load_map()
    assert document["schema"] == SCHEMA
    assert document["task_id"] == "CIMP-MOD-01"
    assert document["source_files_moved"] is True
    assert document["source_files_rewritten"] is False
    assert document["packages"] == _packages(REPO_ROOT)
    skip = set(document["inventory_policy"]["walk_skip_directories"])
    limit = document["inventory_policy"]["largest_python_module_limit"]
    largest = _largest(REPO_ROOT, skip, limit)
    assert document["largest_python_modules"] == largest
    assert len(largest) == 15
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


def test_new_method_moves_stay_delegated() -> None:
    for move in METHOD_MOVES:
        owner = _parse(move["owner"])
        sibling = _parse(move["sibling"])
        defined = _defined(sibling)
        assert _lines(move["owner"]) <= move["owner_max"]
        assert _lines(move["sibling"]) >= move["sibling_min"]
        imported = False
        for node in ast.walk(owner):
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                if node.module == move["qualifier"] or any(
                    alias.name == move["qualifier"] for alias in node.names
                ):
                    imported = True
        assert imported, move["owner"]
        for class_name, name in move["extracted"]:
            method = _methods(owner, class_name)[name]
            function = defined[name]
            assert len(function.body) > 1, name
            assert function.decorator_list == [], name
            assert len(method.body) == 1, name
            statement = method.body[0]
            assert isinstance(statement, ast.Return), name
            call = statement.value
            assert isinstance(call, ast.Call), name
            assert isinstance(call.func, ast.Attribute) and call.func.attr == name
            assert isinstance(call.func.value, ast.Name) and call.func.value.id == move["qualifier"]
            assert call.args and isinstance(call.args[0], ast.Name)
            assert call.args[0].id == method.args.args[0].arg
        methods = _methods(owner, move["sentinel_class"])
        for name in move["sentinels"]:
            assert name in methods and name not in defined
            assert len(methods[name].body) > 1, name


def test_graph_functions_stay_reexported() -> None:
    move = FUNCTION_MOVE
    owner = _parse(move["owner"])
    sibling = _parse(move["sibling"])
    owner_defined = _defined(owner)
    sibling_defined = _defined(sibling)
    imported = set()
    for node in owner.body:
        if isinstance(node, ast.ImportFrom) and node.module == move["stem"]:
            imported.update(alias.name for alias in node.names)
    assert _lines(move["owner"]) <= move["owner_max"]
    assert _lines(move["sibling"]) >= move["sibling_min"]
    for name in move["extracted"]:
        assert name not in owner_defined
        assert name in sibling_defined and name in imported
        assert len(sibling_defined[name].body) > 1
    sentinel = move["sentinel"]
    assert sentinel in owner_defined and sentinel not in sibling_defined
    assert len(owner_defined[sentinel].body) > 1


def test_earlier_floors_and_root_shims_hold() -> None:
    for relative, maximum, minimum in EARLIER_FLOORS:
        count = _lines(relative)
        if maximum is not None:
            assert count <= maximum, f"{relative} has {count} lines"
        if minimum is not None:
            assert count >= minimum, f"{relative} has {count} lines"
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


def test_lazy_packages_leave_owners_unloaded() -> None:
    script = r"""
import importlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
provider = "backends." + "open" + "ai"
stem = "ipfs_" + "accel" + "erate"

import adversarial_harness
for name in ("adversarial_harness.optimizer", "adversarial_harness.session", "adversarial_harness.harness"):
    assert name not in sys.modules, name

import complaint_analysis
for name in ("complaint_analysis.analyzer", "complaint_analysis.legal_patterns", "complaint_analysis.response_parsers"):
    assert name not in sys.modules, name

import complaint_phases
for name in ("complaint_phases.denoiser", "complaint_phases.dependency_graph", "complaint_phases.knowledge_graph"):
    assert name not in sys.modules, name

import lib
for name in (
    "lib.deontic_logic", "lib.document_render", "lib.formal_logic",
    "lib.legal_document", "lib.runtime_ownership", "lib.support_map",
):
    assert name not in sys.modules, name

import backends
for name in ("backends.llm_router_backend", "backends.workstation", "backends.multimodal_router_backend", provider):
    assert name not in sys.modules, name

import mediator
for name in (
    "mediator.mediator", "mediator.workflow_service", "mediator.evidence_hooks",
    "mediator.claim_support_hooks", "mediator.formal_document",
):
    assert name not in sys.modules, name

import complaint_generator
assert "complaint_generator.workspace" not in sys.modules
assert len(complaint_generator.__all__) == 89

import integrations
for name in (
    "integrations.private_storage",
    "integrations.ipfs_datasets.logic",
    "integrations.mike",
    "integrations." + stem,
):
    assert name not in sys.modules, name

package = integrations.ipfs_datasets
assert package.__name__ == "integrations.ipfs_datasets"
assert "integrations.ipfs_datasets.logic" not in sys.modules
assert "integrations.private_storage" not in sys.modules
mike = integrations.mike
assert mike.MODULE == "integrations.mike.interface"
assert "integrations.mike.llm_patch" not in sys.modules
assert "integrations.mike" not in sys.modules
facade = getattr(integrations, stem)
assert facade.MODULE == "integrations." + stem + ".interface"
assert ("integrations." + stem) not in sys.modules
assert ("integrations." + stem + ".routers") not in sys.modules
assert integrations.__all__ == ["ipfs_datasets", "mike", stem]

optimizer = importlib.import_module("adversarial_harness.optimizer")
session = importlib.import_module("adversarial_harness.session")
harness = importlib.import_module("adversarial_harness.harness")
assert adversarial_harness.Optimizer is optimizer.Optimizer
assert adversarial_harness.AdversarialSession is session.AdversarialSession
assert adversarial_harness.AdversarialHarness is harness.AdversarialHarness

analyzer = importlib.import_module("complaint_analysis.analyzer")
patterns = importlib.import_module("complaint_analysis.legal_patterns")
parsers = importlib.import_module("complaint_analysis.response_parsers")
scoring = importlib.import_module("complaint_analysis.risk_scoring")
assert complaint_analysis.ComplaintAnalyzer is analyzer.ComplaintAnalyzer
assert complaint_analysis.LegalPatternExtractor is patterns.LegalPatternExtractor
assert complaint_analysis.ResponseParserFactory is parsers.ResponseParserFactory
assert complaint_analysis.RiskScorer is scoring.ComplaintRiskScorer
assert complaint_analysis.ComplaintLegalPatternExtractor is patterns.LegalPatternExtractor

denoiser = importlib.import_module("complaint_phases.denoiser")
graph = importlib.import_module("complaint_phases.dependency_graph")
knowledge = importlib.import_module("complaint_phases.knowledge_graph")
assert complaint_phases.ComplaintDenoiser is denoiser.ComplaintDenoiser
assert complaint_phases.DependencyGraph is graph.DependencyGraph
assert complaint_phases.KnowledgeGraph is knowledge.KnowledgeGraph

logic = importlib.import_module("lib.deontic_logic")
assert lib.deontic_logic is logic

router = importlib.import_module("backends.llm_router_backend")
multi = importlib.import_module("backends.multimodal_router_backend")
assert backends.LLMRouterBackend is router.LLMRouterBackend
assert backends.LLMRouter is router.LLMRouter
assert backends.MultimodalRouter is multi.MultimodalRouter
assert provider not in sys.modules
assert backends.WorkstationBackendModels.__name__ == "WorkstationBackendModels"

owner = importlib.import_module("mediator.mediator")
workflow = importlib.import_module("mediator.workflow_service")
hooks = importlib.import_module("mediator.claim_support_hooks")
document = importlib.import_module("mediator.formal_document")
assert mediator.Mediator is owner.Mediator
assert mediator.MODULE_OWNERSHIP is owner.MODULE_OWNERSHIP
assert mediator.WorkflowService is workflow.WorkflowService
assert mediator.ClaimSupportHook is hooks.ClaimSupportHook
assert mediator.ComplaintDocumentBuilder is document.ComplaintDocumentBuilder

workspace = importlib.import_module("complaint_generator.workspace")
assert complaint_generator.ComplaintWorkspaceService is workspace.ComplaintWorkspaceService
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(REPO_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout


def test_boundaries_sibling_rows_and_root_links() -> None:
    facade = "integrations/" + ("ipfs_" + "accel" + "erate") + "/interface.py"
    discovered = _discover_interfaces()
    relative = [path.relative_to(REPO_ROOT).as_posix() for path in discovered]
    assert facade in relative
    text = BOUNDARIES.read_text(encoding="utf-8")
    assert "Callers import the interface modules rather than the owner modules." in text
    assert "package initializers are lazy" not in text
    assert "already lazy" not in text
    sections = _boundary_sections(text)
    assert [heading for heading, _bullets in sections] == relative
    for path, (heading, bullets) in zip(discovered, sections):
        owners = [str(item) for item in _assigned_constant(path, "OWNER_MODULES")]
        assert heading == path.relative_to(REPO_ROOT).as_posix()
        assert bullets == owners
    rows = [
        match.groups()
        for match in (_ROW.match(line) for line in SIBLING_MAP.read_text(encoding="utf-8").splitlines())
        if match
    ]
    assert tuple(rows) == REQUIRED_ROWS
    found = {path.name for path in REPO_ROOT.glob("*.md") if path.is_file()}
    assert found == ROOT_MARKDOWN
    for name in ROOT_DOCS:
        document = REPO_ROOT / name
        targets = _targets(document.read_text(encoding="utf-8"))
        for target in (
            "docs/architecture/consolidation_modules.md",
            "docs/architecture/module_boundaries.md",
        ):
            assert target in targets, name
            assert (document.parent / target).resolve().is_file()


def test_retargeted_docs_keep_their_link_minimums() -> None:
    assert not (REPO_ROOT / "docs/GRAPHRAG_REFACTORING_GUIDE.md").exists()
    for relative, minimum in DOC_MINIMUMS.items():
        document = REPO_ROOT / relative
        assert document.is_file(), relative
        targets = _targets(document.read_text(encoding="utf-8"))
        assert len(targets) >= minimum, relative


def test_interface_schema_and_version_stay_assigned() -> None:
    discovered = _discover_interfaces()
    assert discovered
    for path in discovered:
        assert _assigned_constant(path, "INTERFACE_SCHEMA") == INTERFACE_SCHEMA
        assert _assigned_constant(path, "INTERFACE_VERSION") == INTERFACE_VERSION
