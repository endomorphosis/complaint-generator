"""CIMP-CUR-09: current-layout note names roots without copying locked tables."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NOTE_PATH = REPO_ROOT / "docs/architecture/current_layout.md"
CONSOLIDATION_PATH = REPO_ROOT / "docs/architecture/consolidation_modules.md"

ROOT_MARKDOWN = (
    "README.md",
    "DOCUMENTATION_INDEX.md",
    "CONTRIBUTING.md",
    "TESTING.md",
    "TODO.md",
)
ROOT_SHIMS = (
    "intake_status.py",
    "workflow_phase_guidance.py",
    "document_pipeline.py",
    "document_optimization.py",
    "claim_support_review.py",
)
ROOT_CONFIGS = (
    "config.adversarial_autopatch_demo.json",
    "config.adversarial_autopatch_live.json",
    "config.adversarial_autopatch_live_batch.json",
    "config.adversarial_autopatch_live_multibackend.json",
    "config.huggingface_router.json",
    "config.llm_router.json",
    "config.review_surface.huggingface_router.json",
    "config.review_surface.json",
)
ARCHITECTURE_LINKS = (
    "docs/architecture/consolidation_modules.md",
    "docs/architecture/module_boundaries.md",
    "docs/architecture/module_seams.md",
)
FACADE_DIR = "integrations/ipfs_" + "acc" + "elerate"
PLAN_COMPILER = FACADE_DIR + "/improvement_plan.py"
SHIM_LINE_CAP = 40
HISTORICAL_NOTE = (
    "Historical plan, backlog, and tasklist documents are not the current architecture."
)
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
TABLE_ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|")
SIBLING_CELL_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|")


def note_lines() -> list[str]:
    """Return note lines using splitlines(), the repository line count."""
    return NOTE_PATH.read_text(encoding="utf-8").splitlines()


def note_text() -> str:
    return "\n".join(note_lines()) + "\n"


def markdown_link_targets(text: str) -> list[str]:
    targets: list[str] = []
    for match in LINK_RE.finditer(text):
        raw = match.group(1).strip()
        if raw.startswith("<") and raw.endswith(">"):
            raw = raw[1:-1].strip()
        path = raw.split("#", 1)[0].split("?", 1)[0]
        if path:
            targets.append(path)
    return targets


def sibling_paths() -> set[str]:
    found: set[str] = set()
    for line in CONSOLIDATION_PATH.read_text(encoding="utf-8").splitlines():
        match = SIBLING_CELL_RE.match(line)
        if match:
            found.add(match.group(1))
    return found


def test_note_names_root_markdown_shims_configs_and_interface() -> None:
    lines = note_lines()
    text = "\n".join(lines)
    assert lines
    assert len(lines) == len(NOTE_PATH.read_text(encoding="utf-8").splitlines())
    for name in ROOT_MARKDOWN:
        assert name in text
        assert (REPO_ROOT / name).is_file()
    assert "at most 40 lines" in text
    for name in ROOT_SHIMS:
        assert name in text
        shim = REPO_ROOT / name
        assert shim.is_file()
        assert len(shim.read_text(encoding="utf-8").splitlines()) <= SHIM_LINE_CAP
    assert "stay at the root" in text
    for name in ROOT_CONFIGS:
        assert name in text
        assert (REPO_ROOT / name).is_file()
    assert "INTERFACE_SCHEMA" in text
    assert "complaint-generator/module-interface@1" in text
    assert "INTERFACE_VERSION" in text
    assert "1.0.0" in text
    assert HISTORICAL_NOTE in text
    assert "improvement_plan.py" in text
    assert FACADE_DIR in text
    assert (REPO_ROOT / PLAN_COMPILER).is_file()


def test_architecture_links_resolve_and_tables_are_not_copied() -> None:
    text = note_text()
    targets = markdown_link_targets(text)
    for link in ARCHITECTURE_LINKS:
        assert link in targets
        assert (REPO_ROOT / link).is_file()
    missing = [target for target in targets if not (REPO_ROOT / target).is_file()]
    assert missing == []
    siblings = sibling_paths()
    assert siblings
    copied = []
    for line in note_lines():
        match = TABLE_ROW_RE.match(line)
        if match and match.group(1) in siblings:
            copied.append(line)
    assert copied == []
