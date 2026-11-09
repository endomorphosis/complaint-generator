"""CIMP-DEP-20: standalone module-depth ratchet."""

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_MARKDOWN = {
    "README.md",
    "DOCUMENTATION_INDEX.md",
    "CONTRIBUTING.md",
    "TESTING.md",
    "TODO.md",
}
LINE_FLOORS = (
    ("applications/complaint_workspace.py", 17600, None),
    ("applications/complaint_workspace_research.py", None, 850),
    ("mediator/mediator.py", 12600, None),
    ("mediator/claim_follow_up_flow.py", None, 1100),
    ("complaint_phases/document_pipeline.py", 9600, None),
    ("complaint_phases/document_pipeline_render.py", None, 600),
    ("mediator/claim_support_hooks.py", 8900, None),
    ("mediator/claim_support_recommendations.py", None, 700),
    ("complaint_phases/denoiser.py", 7400, None),
    ("complaint_phases/denoiser_bindings.py", None, 500),
    ("applications/dashboard_ui.py", 1200, None),
    ("applications/dashboard_hub.py", None, 4500),
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
    ("applications/complaint_workspace_drafting.py", None, 1250),
    ("mediator/intake_question_flow.py", None, 1450),
    ("complaint_phases/document_pipeline_readiness.py", None, 950),
    ("complaint_phases/document_pipeline_guidance.py", None, 800),
    ("complaint_phases/document_optimization_summaries.py", None, 650),
    ("mediator/claim_support_review_sections.py", None, 1600),
    ("complaint_phases/denoiser_questions.py", None, 1000),
    ("mediator/claim_support_diagnostics.py", None, 1050),
)
ROOT_SHIMS = (
    "intake_status.py",
    "workflow_phase_guidance.py",
    "document_pipeline.py",
    "document_optimization.py",
    "claim_support_review.py",
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
_INLINE = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
_DEFINITION = re.compile(r"(?m)^\s{0,3}\[[^\]\n]+\]:[ \t]+(\S+)")
_AUTOLINK = re.compile(r"(?<![A-Za-z0-9_])<([^>\s]+)>")


def _lines(relative: str) -> int:
    return len((REPO_ROOT / relative).read_text(encoding="utf-8").splitlines())


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


def test_root_markdown_is_exactly_the_five_keepers() -> None:
    found = {path.name for path in REPO_ROOT.glob("*.md") if path.is_file()}
    assert found == ROOT_MARKDOWN


def test_line_floors_hold_for_both_generations() -> None:
    for relative, maximum, minimum in LINE_FLOORS:
        count = _lines(relative)
        if maximum is not None:
            assert count <= maximum, f"{relative} has {count} lines"
        if minimum is not None:
            assert count >= minimum, f"{relative} has {count} lines"


def test_root_shims_stay_short_and_define_no_function_or_class() -> None:
    for name in ROOT_SHIMS:
        path = REPO_ROOT / name
        text = path.read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 30, name
        tree = ast.parse(text, filename=str(path))
        defined = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        assert defined == [], name


def test_new_interfaces_are_the_owner_surfaces() -> None:
    import adversarial_harness.harness as harness
    import adversarial_harness.interface as harness_interface
    import backends.interface as backend_interface
    import backends.llm_router_backend as backend_owner
    import complaint_analysis.analyzer as analyzer
    import complaint_analysis.interface as analysis_interface
    import integrations.interface as integration_interface

    assert harness_interface.INTERFACE_SCHEMA == "complaint-generator/module-interface@1"
    assert harness_interface.AdversarialHarness is harness.AdversarialHarness
    assert analysis_interface.INTERFACE_SCHEMA == "complaint-generator/module-interface@1"
    assert analysis_interface.ComplaintAnalyzer is analyzer.ComplaintAnalyzer
    assert backend_interface.INTERFACE_SCHEMA == "complaint-generator/module-interface@1"
    assert backend_interface.LLMRouterBackend is backend_owner.LLMRouterBackend
    assert integration_interface.INTERFACE_SCHEMA == "complaint-generator/module-interface@1"
    assert integration_interface.INTERFACE_VERSION == "1.0.0"
    owners = tuple(integration_interface.OWNER_MODULES)
    assert "integrations.ipfs_datasets.interface" in owners
    assert "integrations.mike.interface" in owners
    assert len(owners) == 3
    third = [
        name
        for name in owners
        if name not in {"integrations.ipfs_datasets.interface", "integrations.mike.interface"}
    ]
    assert len(third) == 1
    assert ("accel" + "erate") in third[0]
    assert third[0].endswith(".interface")
    for module_name in owners:
        attr = module_name.split(".")[-2]
        loaded = getattr(integration_interface, attr)
        assert loaded.__name__ == module_name


def test_sixteen_docs_still_resolve_at_their_minimums() -> None:
    for relative, minimum in DOC_MINIMUMS.items():
        document = REPO_ROOT / relative
        targets = _targets(document.read_text(encoding="utf-8"))
        assert len(targets) >= minimum, relative
        missing = [
            target
            for target in targets
            if not (document.parent / target).resolve().exists()
        ]
        assert missing == [], f"{relative} -> {missing}"
