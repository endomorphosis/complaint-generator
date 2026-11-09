"""CIMP-DEP-19: consolidation map names both sibling generations."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAP = REPO_ROOT / "docs" / "architecture" / "consolidation_modules.md"
ROOT_DOCS = ("README.md", "DOCUMENTATION_INDEX.md", "CONTRIBUTING.md", "TESTING.md")
PHRASES = (
    "docs/archive/sessions",
    "docs/archive/reports",
    "mediator/claim_support_review.py",
    "complaint-generator/module-interface@1",
    "1.0.0",
)
PAIRS = (
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
)
_INLINE = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")


def test_map_names_every_sibling_and_its_owner() -> None:
    text = MAP.read_text(encoding="utf-8")
    for sibling, owner in PAIRS:
        assert f"`{sibling}`" in text, sibling
        assert f"`{owner}`" in text, owner
        assert (REPO_ROOT / sibling).is_file(), sibling


def test_root_docs_keep_the_consolidation_phrases_and_map_link() -> None:
    for name in ROOT_DOCS:
        document = REPO_ROOT / name
        text = document.read_text(encoding="utf-8")
        for phrase in PHRASES:
            assert phrase in text, f"{name} missing {phrase}"
        found = False
        for match in _INLINE.finditer(text):
            target = match.group(1).split()[0].split("#", 1)[0]
            if (document.parent / target).resolve() == MAP.resolve():
                found = True
        assert found, name
