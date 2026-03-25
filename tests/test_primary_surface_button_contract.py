from pathlib import Path


def _assert_click_handler(template_path: str, button_id: str) -> None:
    content = Path(template_path).read_text(encoding="utf-8")
    assert f'id="{button_id}"' in content
    assert (
        f"document.getElementById('{button_id}').addEventListener('click'," in content
        or f'document.getElementById("{button_id}").addEventListener("click",' in content
    ), f"{button_id} is rendered in {template_path} without a click handler contract."


def test_workspace_primary_buttons_are_wired():
    for button_id in (
        "save-synopsis-button",
        "refresh-synopsis-button",
        "save-intake-button",
        "refresh-session-button",
        "save-evidence-button",
        "import-gmail-evidence-button",
        "import-local-evidence-button",
        "generate-draft-button",
        "save-draft-button",
        "export-packet-button",
        "refresh-tooling-contract-button",
        "refresh-provider-diagnostics-button",
        "analyze-complaint-output-button",
        "review-generated-exports-button",
        "run-ux-review-button",
        "run-ux-closed-loop-button",
        "run-browser-audit-button",
    ):
        _assert_click_handler("templates/workspace.html", button_id)


def test_review_dashboard_primary_buttons_are_wired():
    for button_id in (
        "review-button",
        "execute-button",
        "confirm-intake-summary-button",
        "resolve-button",
        "clear-resolution-button",
        "save-testimony-button",
        "clear-testimony-button",
        "save-document-button",
        "clear-document-button",
    ):
        _assert_click_handler("templates/claim_support_review.html", button_id)


def test_document_builder_primary_buttons_are_wired():
    content = Path("templates/document.html").read_text(encoding="utf-8")
    assert 'id="generateButton"' in content
    assert "document.getElementById('documentForm').addEventListener('submit', generateDocument);" in content
    _assert_click_handler("templates/document.html", "resetButton")


def test_trace_and_editor_buttons_are_wired():
    for template_path, button_ids in (
        ("templates/optimization_trace.html", ("loadTraceButton", "exportTraceButton")),
        ("templates/MLWYSIWYG.html", ("refresh-preview", "reset-editor")),
    ):
        for button_id in button_ids:
            _assert_click_handler(template_path, button_id)
