from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lib.document_render import (
    HAS_REPORTLAB,
    build_case_caption_text_lines,
    build_caption_party_block_html,
    build_caption_party_block_lines,
    build_case_caption_table,
    build_case_detail_lines,
    make_page_footer_renderer,
)


def test_build_caption_party_block_html_uses_default_fallbacks() -> None:
    assert build_caption_party_block_html({}) == "Plaintiff, Plaintiff,<br/>v.<br/>Defendant, Defendant."


def test_build_caption_party_block_lines_uses_default_fallbacks() -> None:
    assert build_caption_party_block_lines({}) == [
        "Plaintiff, Plaintiff,",
        "v.",
        "Defendant, Defendant.",
    ]


def test_build_caption_party_block_html_joins_party_names() -> None:
    html = build_caption_party_block_html(
        {
            "plaintiffs": ["Jane Doe", "John Roe"],
            "defendants": ["Acme Corporation", "Beta LLC"],
        }
    )

    assert html == (
        "Jane Doe, John Roe, Plaintiff,<br/>"
        "v.<br/>"
        "Acme Corporation, Beta LLC, Defendant."
    )


def test_build_case_detail_lines_includes_optional_caption_metadata() -> None:
    lines = build_case_detail_lines(
        {
            "case_number": "1:26-cv-12345",
            "lead_case_number": "1:25-cv-00001",
            "related_case_number": "1:25-cv-00002",
            "assigned_judge": "Hon. Maria Valdez",
            "courtroom": "Courtroom 4A",
        }
    )

    assert lines == [
        "Case No.: 1:26-cv-12345",
        "Lead Case No.: 1:25-cv-00001",
        "Related Case No.: 1:25-cv-00002",
        "Judge: Hon. Maria Valdez",
        "Courtroom: Courtroom 4A",
    ]


def test_build_case_caption_text_lines_supports_text_export_labels() -> None:
    lines = build_case_caption_text_lines(
        {"plaintiffs": ["Jane Doe"], "defendants": ["Acme Corporation"]},
        {
            "case_number": "1:26-cv-12345",
            "assigned_judge": "Hon. Maria Valdez",
            "courtroom": "Courtroom 4A",
        },
        assigned_judge_label="Assigned to:",
    )

    assert lines == [
        "Jane Doe, Plaintiff,",
        "v.",
        "Acme Corporation, Defendant.",
        "Case No.: 1:26-cv-12345",
        "Assigned to: Hon. Maria Valdez",
        "Courtroom: Courtroom 4A",
    ]


def test_make_page_footer_renderer_draws_left_and_right_footer_text() -> None:
    canvas_obj = Mock()
    canvas_obj.getPageNumber.return_value = 3
    doc = SimpleNamespace(leftMargin=72, rightMargin=72, pagesize=(612, 792))

    footer = make_page_footer_renderer("Complaint")
    footer(canvas_obj, doc)

    canvas_obj.drawString.assert_called_once_with(72, 36.0, "Complaint")
    canvas_obj.drawRightString.assert_called_once_with(540, 36.0, "Page 3")


@pytest.mark.skipif(not HAS_REPORTLAB, reason="reportlab not installed")
def test_build_case_caption_table_creates_two_column_table() -> None:
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch

    body_style = getSampleStyleSheet()["BodyText"]
    table = build_case_caption_table(
        {"plaintiffs": ["Jane Doe"], "defendants": ["Acme Corporation"]},
        {"case_number": "1:26-cv-12345"},
        body_style,
        left_width=4.5 * inch,
        right_width=2.0 * inch,
    )

    assert len(table._cellvalues) == 1
    assert len(table._cellvalues[0]) == 2
    assert table._cellvalues[0][0].getPlainText() == "Jane Doe, Plaintiff,v.Acme Corporation, Defendant."
    assert table._cellvalues[0][1].getPlainText() == "Case No.: 1:26-cv-12345"