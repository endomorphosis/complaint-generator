"""CIMP-RLS-03: generated root artifacts stay out of the worktree."""

from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
_EGG = "egg-" + "info"
_DEMO = ".tmp-demo-output-" + "sessions"
_USER = "demo-output-" + "user.json"

GENERATED = (
    "drift_report_mcp.json",
    f"complaint_generator.{_EGG}/PKG-INFO",
    f"complaint_generator.{_EGG}/SOURCES.txt",
    f"complaint_generator.{_EGG}/dependency_links.txt",
    f"complaint_generator.{_EGG}/entry_points.txt",
    f"complaint_generator.{_EGG}/requires.txt",
    f"complaint_generator.{_EGG}/top_level.txt",
    f"{_DEMO}/{_USER}",
    f"{_DEMO}-fast/{_USER}",
    *(f"{_DEMO}-fast-{index}/{_USER}" for index in range(2, 8)),
)

IGNORE_PATTERNS = (
    "drift_report_mcp.json",
    f"*.{_EGG}/",
    f"{_DEMO}*",
)

MARKDOWN = (
    "README.md",
    "DOCUMENTATION_INDEX.md",
    "CONTRIBUTING.md",
    "TESTING.md",
    "TODO.md",
)
SHIMS = (
    "intake_status.py",
    "workflow_phase_guidance.py",
    "document_pipeline.py",
    "document_optimization.py",
    "claim_support_review.py",
)
CONFIGS = (
    "config.adversarial_autopatch_demo.json",
    "config.adversarial_autopatch_live.json",
    "config.adversarial_autopatch_live_batch.json",
    "config.adversarial_autopatch_live_multibackend.json",
    "config.huggingface_router.json",
    "config.llm_router.json",
    "config.review_surface.huggingface_router.json",
    "config.review_surface.json",
)
ENTRYPOINTS = ("main.py", "run.py")


def test_generated_root_artifacts_are_absent() -> None:
    assert len(GENERATED) == 15
    for relative in GENERATED:
        path = REPO_ROOT / relative
        assert not path.exists(), relative
        assert not path.is_symlink(), relative


def test_gitignore_covers_generated_root_artifacts() -> None:
    lines = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    present = {line.strip() for line in lines if line.strip()}
    for pattern in IGNORE_PATTERNS:
        assert pattern in present, pattern


def test_root_keepers_remain() -> None:
    keepers = MARKDOWN + SHIMS + CONFIGS + ENTRYPOINTS
    assert len(MARKDOWN) == 5
    assert len(SHIMS) == 5
    assert len(CONFIGS) == 8
    assert len(ENTRYPOINTS) == 2
    for relative in keepers:
        path = REPO_ROOT / relative
        assert path.is_file(), relative
        assert len(path.read_text(encoding="utf-8").splitlines()) >= 1
