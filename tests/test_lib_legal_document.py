from lib.legal_document import (
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
```text
appendix
```
"""


def test_extract_pleading_header_from_lib_module() -> None:
    header, body_start = extract_pleading_header(SAMPLE_PLEADING)

    assert header is not None
    assert header.case_number == "Case No. 26PR00641"
    assert header.title_lines == ["MOTION TO SHOW CAUSE"]
    assert body_start > 0


def test_parse_legal_document_from_lib_module_reports_structure() -> None:
    parsed = parse_legal_document(SAMPLE_PLEADING)

    assert parsed.header is not None
    assert parsed.numbered_paragraph_count == 2
    assert parsed.bullet_count == 1
    assert parsed.code_block_count == 1
    assert parsed.title == "MOTION TO SHOW CAUSE"
    assert parsed.summary()["section_count"] >= 1
    assert parsed.summary()["title"] == "MOTION TO SHOW CAUSE"


def test_render_and_paginate_pleading_caption_from_lib_module() -> None:
    caption = build_pleading_caption(
        court_lines=["IN THE CIRCUIT COURT OF THE STATE OF OREGON"],
        case_number="Case No. 26PR00641",
        party_lines=["Benjamin Barber,", "Petitioner,"],
        filing_title_lines=["MOTION TO SHOW CAUSE"],
        right_title="Probate Department",
    )

    rendered = render_pleading_caption_block(caption)
    pages = paginate_pleading_lines(["Line 1", "Line 2", "Line 3"], page_size=2, footer_label="Exhibit A")

    assert "Case No. 26PR00641" in rendered
    assert "MOTION TO SHOW CAUSE" in rendered
    assert pages[0][-1] == "Exhibit A  Page 1 of 2"
    assert pages[1][-1] == "Exhibit A  Page 2 of 2"