"""CIMP-SEA-19: seam sibling table, architecture sizes, and root documentation links."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SEAM_MAP = REPO_ROOT / "docs/architecture/module_seams.md"
SIBLING_MAP = REPO_ROOT / "docs/architecture/consolidation_modules.md"
ARCHITECTURE = REPO_ROOT / "docs/ARCHITECTURE.md"
ROOT_DOCS = (
    "README.md",
    "DOCUMENTATION_INDEX.md",
    "CONTRIBUTING.md",
    "TESTING.md",
)
ROOT_MARKDOWN = {
    "README.md",
    "DOCUMENTATION_INDEX.md",
    "CONTRIBUTING.md",
    "TESTING.md",
    "TODO.md",
}
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
STALE_SIZES = (
    "10,852 lines",
    "7,881 lines",
    "6,933 lines",
    "5,691 lines",
    "5,562 lines",
    "5,309 lines",
)
_ROW = re.compile(r"^\| `([^`]+)` \| `([^`]+)` \|$")
_SIZE = re.compile(r"^\| `([^`]+)` \| (\d+) lines \|")
_INLINE = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
_DEFINITION = re.compile(r"(?m)^\s{0,3}\[[^\]\n]+\]:[ \t]+(\S+)")
_AUTOLINK = re.compile(r"(?<![A-Za-z0-9_])<([^>\s]+)>")


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


def _lines(relative: str) -> int:
    return len((REPO_ROOT / relative).read_text(encoding="utf-8").splitlines())


def test_seam_table_lists_the_thirteen_siblings() -> None:
    assert _table_rows(SEAM_MAP) == SEAM_ROWS


def test_consolidation_table_is_unchanged() -> None:
    assert _table_rows(SIBLING_MAP) == CONSOLIDATION_ROWS


def test_architecture_sizes_match_splitlines() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    for stale in STALE_SIZES:
        assert stale not in text
    start = text.index("### Current Extraction Priorities")
    end = text.index("### ", start + 3)
    section = text[start:end]
    rows = [match.groups() for match in (_SIZE.match(line) for line in section.splitlines()) if match]
    found = {path: int(count) for path, count in rows}
    assert "applications/dashboard_hub.py" in found
    assert found
    for path, count in found.items():
        assert count == _lines(path), path


def test_root_docs_link_to_the_seam_document() -> None:
    found = {path.name for path in REPO_ROOT.glob("*.md") if path.is_file()}
    assert found == ROOT_MARKDOWN
    for name in ROOT_DOCS:
        document = REPO_ROOT / name
        text = document.read_text(encoding="utf-8")
        assert "docs/archive/sessions" in text
        assert "docs/archive/reports" in text
        assert "root shims" in text
        assert "complaint-generator/module-interface@1" in text
        assert "1.0.0" in text
        targets = _targets(text)
        for target in (
            "docs/architecture/consolidation_modules.md",
            "docs/architecture/module_boundaries.md",
            "docs/architecture/module_seams.md",
        ):
            assert target in targets, name
            assert (document.parent / target).resolve().is_file(), f"{name} -> {target}"
