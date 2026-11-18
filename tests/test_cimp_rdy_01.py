"""CIMP-RDY-01: runtime logs and crawl-cache binaries stay untracked."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

REPO_ROOT = Path(__file__).resolve().parents[1]
_LOG_DIR = "log" + "s"
_CACHE_DIR = "data" + "sets/" + "CCINDEX_WARC_" + "CACHE_DIR"

ABSENT = (
    f"{_LOG_DIR}/UNCAUGHT_EXCEPTION.log",
    f"{_LOG_DIR}/app.log",
    f"{_LOG_DIR}/test.log",
    f"{_CACHE_DIR}/ranges/120cd4f5b5e33aaf77863e1199943e3245bc174a7ef393de54e9b34700ef7dea.bin",
    f"{_CACHE_DIR}/ranges/14ce88a48f01c45f629f7cf04ca8d8f0e496d33b94ad06b1e5ae8697c2384767.bin",
    f"{_CACHE_DIR}/ranges/e913dc0afb1c39ca04b5be97e6f6cbcc43219df2d38cc17623f363d9fb6a1dc0.bin",
)

IGNORE_LINES = (
    f"{_LOG_DIR}/*.log",
    f"{_CACHE_DIR}/",
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


def _tracked() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return set(result.stdout.splitlines())


def test_runtime_logs_and_cache_bins_are_untracked() -> None:
    tracked = _tracked()
    assert len(ABSENT) == 6
    for relative in ABSENT:
        assert relative not in tracked, relative
    ignore_lines = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    present = {line.strip() for line in ignore_lines if line.strip()}
    for pattern in IGNORE_LINES:
        assert pattern in present, pattern
    keepers = MARKDOWN + SHIMS + CONFIGS + ENTRYPOINTS
    assert len(MARKDOWN) == 5
    assert len(SHIMS) == 5
    assert len(CONFIGS) == 8
    assert len(ENTRYPOINTS) == 2
    for relative in keepers:
        assert relative in tracked, relative
