"""Generic reportlab-oriented rendering helpers.

These helpers extract reusable caption and footer primitives from the HACC
rendering scripts without carrying over case-specific paths or formatting
assumptions.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, Table, TableStyle

    HAS_REPORTLAB = True
except ImportError:  # pragma: no cover - optional dependency
    colors = None
    letter = None
    inch = None
    Paragraph = None
    Table = None
    TableStyle = None
    HAS_REPORTLAB = False


def _clean_entries(values: Any, default: str) -> list[str]:
    if isinstance(values, (list, tuple)):
        entries = [str(value).strip() for value in values if str(value or "").strip()]
        return entries or [default]
    text = str(values or "").strip()
    return [text] if text else [default]


def build_caption_party_block_html(parties: Mapping[str, Sequence[str]] | None) -> str:
    """Build the left-side HTML caption block used in reportlab tables."""

    return "<br/>".join(build_caption_party_block_lines(parties))


def build_caption_party_block_lines(parties: Mapping[str, Sequence[str]] | None) -> list[str]:
    """Build the left-side caption block as plain text lines."""

    parties = parties or {}
    plaintiffs = ", ".join(_clean_entries(parties.get("plaintiffs"), "Plaintiff"))
    defendants = ", ".join(_clean_entries(parties.get("defendants"), "Defendant"))
    return [f"{plaintiffs}, Plaintiff,", "v.", f"{defendants}, Defendant."]


def build_case_detail_lines(
    caption: Mapping[str, Any] | None,
    *,
    assigned_judge_label: str = "Judge:",
) -> list[str]:
    """Build the right-side case metadata lines for a case caption."""

    caption = caption or {}
    case_number = str(caption.get("case_number") or "________________").strip() or "________________"
    lines = [f"Case No.: {case_number}"]
    optional_lines = (
        ("lead_case_number", "Lead Case No.:"),
        ("related_case_number", "Related Case No.:"),
        ("assigned_judge", assigned_judge_label),
        ("courtroom", "Courtroom:"),
    )
    for key, label in optional_lines:
        value = str(caption.get(key) or "").strip()
        if value:
            lines.append(f"{label} {value}")
    return lines


def build_case_caption_text_lines(
    parties: Mapping[str, Sequence[str]] | None,
    caption: Mapping[str, Any] | None,
    *,
    assigned_judge_label: str = "Assigned to:",
) -> list[str]:
    """Build the caption block as plain text lines for text and docx export."""

    return [
        *build_caption_party_block_lines(parties),
        *build_case_detail_lines(caption, assigned_judge_label=assigned_judge_label),
    ]


def build_case_caption_table(
    parties: Mapping[str, Sequence[str]] | None,
    caption: Mapping[str, Any] | None,
    body_style: Any,
    *,
    left_width: Any,
    right_width: Any,
) -> Any:
    """Create a standard two-column reportlab case caption table."""

    if not HAS_REPORTLAB:
        raise RuntimeError("Case caption rendering requires reportlab to be installed")

    left_caption = build_caption_party_block_html(parties)
    right_caption = "<br/>".join(build_case_detail_lines(caption))
    caption_table = Table(
        [[Paragraph(left_caption, body_style), Paragraph(right_caption, body_style)]],
        colWidths=[left_width, right_width],
    )
    caption_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return caption_table


def make_page_footer_renderer(left_text: str) -> Callable[[Any, Any], None]:
    """Create a page footer callback compatible with reportlab doc builds."""

    def _footer(canvas_obj: Any, doc: Any) -> None:
        canvas_obj.saveState()
        canvas_obj.setFont("Times-Roman", 10)
        page_width = getattr(doc, "pagesize", letter)[0] if letter is not None else 612
        left_margin = getattr(doc, "leftMargin", 72)
        right_margin = getattr(doc, "rightMargin", 72)
        baseline = 0.5 * inch if inch is not None else 36
        canvas_obj.drawString(left_margin, baseline, left_text)
        canvas_obj.drawRightString(page_width - right_margin, baseline, f"Page {getattr(canvas_obj, 'getPageNumber', lambda: 1)()}")
        canvas_obj.restoreState()

    return _footer