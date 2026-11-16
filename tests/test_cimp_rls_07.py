"""CIMP-RLS-07: root keepers and removed generated files."""

import re
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.no_auto_llm,
    pytest.mark.no_auto_network,
    pytest.mark.no_auto_heavy,
]

REPO_ROOT = Path(__file__).resolve().parents[1]
NOTE = REPO_ROOT / "docs" / "architecture" / "root_release.md"
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
ROOT_MARKDOWN = (
    "README.md",
    "DOCUMENTATION_INDEX.md",
    "CONTRIBUTING.md",
    "TESTING.md",
    "TODO.md",
)
ROOT_SHIMS = (
    "intake_" + "status.py",
    "workflow_" + "phase_" + "guidance.py",
    "document_" + "pipeline.py",
    "document_" + "optimization.py",
    "claim_" + "support_" + "review.py",
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
ENTRYPOINTS = ("main.py", "run.py")
GENERATED = (
    "drift_report_mcp.json",
    "complaint_generator.egg-info",
    ".tmp-demo-output-sessions",
)
LINKED_MAPS = (
    "docs/architecture/current_layout.md",
    "docs/architecture/owner_currency.md",
    "docs/architecture/cohesive_moves.md",
    "docs/architecture/consolidation_modules.md",
    "docs/architecture/module_boundaries.md",
    "docs/architecture/module_seams.md",
)
_BULLET = re.compile(r"^- `([^`]+)`$")
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _section(text: str, heading: str) -> str:
    lines = text.splitlines()
    start = lines.index(heading)
    body = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body)


def _bullets(section: str) -> tuple[str, ...]:
    return tuple(match.group(1) for match in (_BULLET.match(line) for line in section.splitlines()) if match)


def test_root_release_names_keepers_and_generated_paths() -> None:
    text = NOTE.read_text(encoding="utf-8")
    assert len(text.splitlines()) > 0
    assert _bullets(_section(text, "## Root markdown keepers")) == ROOT_MARKDOWN
    assert _bullets(_section(text, "## Root shims")) == ROOT_SHIMS
    assert _bullets(_section(text, "## Root config files")) == ROOT_CONFIGS
    entrypoints = _section(text, "## Compatibility entrypoints")
    for name in ENTRYPOINTS:
        assert f"`{name}`" in entrypoints
    assert "compatibility entrypoints" in entrypoints
    assert "keepers" in entrypoints
    generated = _section(text, "## Generated files")
    for name in GENERATED:
        assert f"`{name}`" in generated
    assert "egg-info" in generated
    assert "are generated and are not product modules" in generated
    assert "INTERFACE_SCHEMA" in text
    assert INTERFACE_SCHEMA in text
    assert "INTERFACE_VERSION" in text
    assert INTERFACE_VERSION in text
    assert "does not copy their tables" in text
    targets = [match.group(1) for match in _LINK.finditer(text)]
    assert targets == list(LINKED_MAPS)
    for target in LINKED_MAPS:
        assert (REPO_ROOT / target).is_file()
