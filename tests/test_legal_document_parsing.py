from complaint_phases import (
    build_pleading_caption,
    extract_pleading_header,
    paginate_pleading_lines,
    parse_legal_document,
    render_pleading_caption_block,
)


SAMPLE_PLEADING = """IN THE CIRCUIT COURT OF THE STATE OF OREGON
FOR THE COUNTY OF CLACKAMAS
PROBATE DEPARTMENT

Case No. 26PR00641

Benjamin Barber,
Petitioner,
v.
Housing Authority of Clackamas County,
Respondent.

MOTION TO SHOW CAUSE

## Overview
1. Petitioner requested an informal review on March 4, 2026.
2. Respondent denied the request on March 8, 2026.

III. ARGUMENT
A. NOTICE FAILURES
(1) The written notice omitted hearing instructions.
- Exhibit A
- Exhibit B
```text
Sample appendix
```
"""


def test_extract_pleading_header_parses_court_case_and_title_blocks():
    header, body_start = extract_pleading_header(SAMPLE_PLEADING)

    assert header is not None
    assert header.court_lines == [
        "IN THE CIRCUIT COURT OF THE STATE OF OREGON",
        "FOR THE COUNTY OF CLACKAMAS",
        "PROBATE DEPARTMENT",
    ]
    assert header.case_number == "Case No. 26PR00641"
    assert "Benjamin Barber," in header.party_lines
    assert header.title_lines == ["MOTION TO SHOW CAUSE"]
    assert body_start > 0


def test_parse_legal_document_reports_structural_signals():
    parsed = parse_legal_document(SAMPLE_PLEADING)
    section_kinds = [section.kind for section in parsed.sections]
    section_headings = [section.heading for section in parsed.sections]

    assert parsed.header is not None
    assert parsed.numbered_paragraph_count == 2
    assert parsed.bullet_count == 2
    assert parsed.code_block_count == 1
    assert parsed.all_caps_heading_count >= 1
    assert "markdown_h2" in section_kinds
    assert "roman_heading" in section_kinds
    assert "letter_heading" in section_kinds
    assert "subheading" in section_kinds
    assert "MOTION TO SHOW CAUSE" in section_headings
    assert parsed.title == "MOTION TO SHOW CAUSE"


def test_render_pleading_caption_block_formats_court_case_and_title_columns():
    caption = build_pleading_caption(
        court_lines=[
            "IN THE CIRCUIT COURT OF THE STATE OF OREGON",
            "FOR THE COUNTY OF CLACKAMAS",
        ],
        case_number="Case No. 26PR00641",
        party_lines=[
            "In the Matter of Jane Cortez, Protected Person,",
            "Petitioner,",
            "v.",
            "Housing Authority of Clackamas County,",
            "Respondent.",
        ],
        filing_title_lines=["EVIDENCE BINDER"],
        right_title="Probate Department",
    )

    rendered = render_pleading_caption_block(caption)

    assert "IN THE CIRCUIT COURT OF THE STATE OF OREGON" in rendered
    assert "Case No. 26PR00641" in rendered
    assert "EVIDENCE BINDER" in rendered
    assert "Housing Authority of Clackamas County," in rendered


def test_paginate_pleading_lines_appends_footer_labels():
    pages = paginate_pleading_lines(
        [f"Line {index}" for index in range(1, 6)],
        page_size=2,
        footer_label="Exhibit A",
    )

    assert len(pages) == 3
    assert pages[0][-1] == "Exhibit A  Page 1 of 3"
    assert pages[-1][-1] == "Exhibit A  Page 3 of 3"
