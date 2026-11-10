"""Reusable document-render helpers for complaint-generator."""

from importlib import import_module

_LAZY_EXPORTS = {
    "HAS_REPORTLAB": (".reportlab_helpers", "HAS_REPORTLAB"),
    "build_case_caption_table": (".reportlab_helpers", "build_case_caption_table"),
    "build_case_caption_text_lines": (".reportlab_helpers", "build_case_caption_text_lines"),
    "build_caption_party_block_html": (".reportlab_helpers", "build_caption_party_block_html"),
    "build_caption_party_block_lines": (".reportlab_helpers", "build_caption_party_block_lines"),
    "build_case_detail_lines": (".reportlab_helpers", "build_case_detail_lines"),
    "make_page_footer_renderer": (".reportlab_helpers", "make_page_footer_renderer"),
}

__all__ = [
    "HAS_REPORTLAB",
    "build_case_caption_table",
    "build_case_caption_text_lines",
    "build_caption_party_block_html",
    "build_caption_party_block_lines",
    "build_case_detail_lines",
    "make_page_footer_renderer",
]


def __getattr__(name: str):
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(module_name, __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
