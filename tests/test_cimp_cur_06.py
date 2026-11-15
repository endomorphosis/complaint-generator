"""CIMP-CUR-06: three-phase guide names current phase modules."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUIDE = REPO_ROOT / "docs/THREE_PHASE_SYSTEM.md"
pytestmark = [pytest.mark.no_auto_llm, pytest.mark.no_auto_network, pytest.mark.no_auto_heavy]

INTERFACE_MODULE = "complaint_phases.interface"
OWNERS = (
    "complaint_phases.phase_manager",
    "complaint_phases.knowledge_graph",
    "complaint_phases.intake_case_file",
)
INTERFACE_SCHEMA = "complaint-generator/module-interface@1"
INTERFACE_VERSION = "1.0.0"
SIBLINGS = (
    "complaint_phases/denoiser_questions.py",
    "complaint_phases/denoiser_bindings.py",
    "complaint_phases/denoiser_question_disposition.py",
    "complaint_phases/document_pipeline_email.py",
)
PHASE_MANAGER_HEADING = "### 4. Phase Manager (`complaint_phases/phase_manager.py`)"


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text[start + len(heading):]
    marker = "\n## "
    end = rest.find(marker)
    body = rest if end < 0 else rest[:end]
    return heading + body


def test_current_modules_names_interface_owners_schema_and_siblings() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    section = _section(text, "## Current modules")
    plain = section.replace("`", "")
    assert "new code imports complaint_phases.interface" in plain.casefold()
    assert INTERFACE_MODULE in section
    for owner in OWNERS:
        assert owner in section
    assert "INTERFACE_SCHEMA" in section
    assert INTERFACE_SCHEMA in section
    assert "INTERFACE_VERSION" in section
    assert INTERFACE_VERSION in section
    for sibling in SIBLINGS:
        assert sibling in section
        assert (REPO_ROOT / sibling).is_file()
    assert (REPO_ROOT / "complaint_phases/interface.py").is_file()


def test_phase_manager_section_remains() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    assert PHASE_MANAGER_HEADING in text
    start = text.index(PHASE_MANAGER_HEADING)
    window = text[start:start + 800]
    assert "PhaseManager" in window
    assert "ComplaintPhase" in window
