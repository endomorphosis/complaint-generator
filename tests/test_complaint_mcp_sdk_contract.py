from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_browser_sdk_surfaces_legal_search_diagnostics_contract():
    commonjs_sdk = (REPO_ROOT / "static" / "complaint_mcp_sdk.js").read_text(encoding="utf-8")
    esm_sdk = (REPO_ROOT / "static" / "complaint_mcp_sdk.mjs").read_text(encoding="utf-8")
    shell_js = (REPO_ROOT / "static" / "complaint_app_shell.js").read_text(encoding="utf-8")

    for content in (commonjs_sdk, esm_sdk):
        assert "runIntakeChatTurn(userId, message, questionId)" in content
        assert "complaint.run_intake_chat_turn" in content
        assert "getPackagedDocketOperatorDashboard(manifestPath)" in content
        assert "loadPackagedDocketOperatorDashboardReport(manifestPath, reportFormat = 'parsed')" in content
        assert "executePackagedDocketProofRevalidationQueue(manifestPath, options = {})" in content
        assert "persistPackagedDocketProofRevalidationQueue(manifestPath, outputDir, options = {})" in content
        assert "complaint.get_packaged_docket_operator_dashboard" in content
        assert "complaint.load_packaged_docket_operator_dashboard_report" in content
        assert "complaint.execute_packaged_docket_proof_revalidation_queue" in content
        assert "complaint.persist_packaged_docket_proof_revalidation_queue" in content
        assert "_extractToolDiagnostics(payload)" in content
        assert "_buildToolDiagnosticSummary(payload)" in content
        assert "diagnostic_summary: diagnosticSummary" in content
        assert "search_diagnostics" in content
        assert "authorities_diagnostics" in content

    assert "Latest retrieval warning:" in shell_js
    assert "Retrieval warning details:" in shell_js
    assert "diagnostic_summary" in shell_js
    assert "latestToolDiagnosticSummary" in shell_js
    assert "formatToolDiagnosticMeta" in shell_js
