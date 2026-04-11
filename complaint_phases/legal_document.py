"""Compatibility exports for reusable legal document helpers."""

from lib.legal_document import (
    DocumentSection,
    ParsedLegalDocument,
    PleadingCaption,
    PleadingHeader,
    build_pleading_caption,
    extract_pleading_header,
    paginate_pleading_lines,
    parse_legal_document,
    render_pleading_caption_block,
)

__all__ = [
    "DocumentSection",
    "ParsedLegalDocument",
    "PleadingCaption",
    "PleadingHeader",
    "build_pleading_caption",
    "extract_pleading_header",
    "paginate_pleading_lines",
    "parse_legal_document",
    "render_pleading_caption_block",
]
