"""Reusable document-render helpers for complaint-generator."""

from .reportlab_helpers import (
    HAS_REPORTLAB,
    build_case_caption_table,
    build_case_caption_text_lines,
    build_caption_party_block_html,
    build_caption_party_block_lines,
    build_case_detail_lines,
    make_page_footer_renderer,
)

__all__ = [
    "HAS_REPORTLAB",
    "build_case_caption_table",
    "build_case_caption_text_lines",
    "build_caption_party_block_html",
    "build_caption_party_block_lines",
    "build_case_detail_lines",
    "make_page_footer_renderer",
]