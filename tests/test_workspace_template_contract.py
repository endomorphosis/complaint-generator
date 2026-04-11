from pathlib import Path


def test_workspace_template_exposes_gmail_import_browser_session_helpers():
    content = Path("templates/workspace.html").read_text()

    assert "gmail-import-user" in content
    assert "gmail-import-password" in content
    assert "gmail-import-use-oauth" in content
    assert "gmail-import-oauth-client-secrets" in content
    assert "gmail-import-oauth-token-cache" in content
    assert "gmail-import-oauth-open-browser" in content
    assert "gmail-import-checkpoint-name" in content
    assert "gmail-import-uid-window-size" in content
    assert "gmail-import-summary-card" in content
    assert "gmail-import-summary-chips" in content
    assert "gmail-import-summary-preview" in content
    assert "gmail-duckdb-pipeline-card" in content
    assert "gmail-pipeline-output-dir" in content
    assert "gmail-pipeline-max-batches" in content
    assert "gmail-pipeline-bm25-query" in content
    assert "gmail-pipeline-bm25-limit" in content
    assert "run-gmail-duckdb-pipeline-button" in content
    assert "gmail-pipeline-summary-chips" in content
    assert "gmail-pipeline-summary-preview" in content
    assert "email-duckdb-search-card" in content
    assert "email-duckdb-index-path" in content
    assert "email-duckdb-limit" in content
    assert "email-duckdb-query" in content
    assert "search-email-duckdb-button" in content
    assert "email-duckdb-search-chips" in content
    assert "email-duckdb-search-preview" in content
    assert "gmail-import-remember-user" in content
    assert "gmail-import-folders" in content
    assert "gmail-import-complaint-query" in content
    assert "gmail-import-complaint-keywords" in content
    assert "gmail-import-min-relevance-score" in content
    assert "Remember Gmail address for this browser session" in content
    assert "gmail-import-security-note" in content
    assert "suggest-gmail-import-addresses" in content
    assert "gmail-import-suggestion-note" in content
    assert "gmail-import-detected-label" in content
    assert "gmail-import-detected-addresses" in content
    assert "gmail-import-selected-label" in content
    assert "gmail-import-suggested-addresses" in content
    assert "Suggest Addresses From Case" in content
    assert "Detected from case" in content
    assert "Selected for import" in content
    assert "Folders To Scan" in content
    assert "Minimum Relevance Score" in content
    assert "Use Gmail OAuth for large mailbox collection" in content
    assert "OAuth Client Secrets JSON" in content
    assert "OAuth Token Cache" in content
    assert "Open browser automatically for Gmail OAuth" in content
    assert "UID Checkpoint Name" in content
    assert "UID Window Size" in content
    assert "Latest Gmail import" in content
    assert "Complaint Query" in content
    assert "Complaint Keywords" in content
    assert "broaden collection beyond a single inbox pass" in content
    assert "resumable mailbox collection" in content
    assert "UID checkpoints" in content
    assert "Describe the dispute in plain language" in content
    assert "Optional keyword phrases, one per line" in content
    assert "local-evidence-paths" in content
    assert "local-evidence-claim-element" in content
    assert "local-evidence-kind" in content
    assert "local-evidence-note" in content
    assert "import-local-evidence-button" in content
    assert "Import local evidence artifacts" in content
    assert "Build Gmail DuckDB corpus" in content
    assert "Search DuckDB email corpus" in content
    assert "Auto-suggest from content" in content
    assert "Bring local PDFs, screenshots, text exports, mailbox files, or whole directories" in content
    assert "One local path per line. Directories are scanned recursively for files." in content
    assert "Pull likely correspondents from intake answers and saved evidence" in content
    assert "The Gmail app password is never stored here and is cleared after each import." in content
    assert "prefer the CLI or MCP import path with keyring support" in content
    assert "gmail-import-cli-help" in content
    assert "copy-gmail-import-cli-command" in content
    assert "gmail-import-mcp-command" in content
    assert "copy-gmail-import-mcp-command" in content
    assert "python3 -m complaint_generator.cli import-gmail-evidence" in content
    assert "complaint.import_gmail_evidence" in content
    assert '"tool": "complaint.import_gmail_evidence"' in content
    assert "await client.importGmailEvidence({" in content
    assert "await client.runGmailDuckdbPipeline({" in content
    assert "await client.searchEmailDuckdb({" in content
    assert '"addresses": ["hr@example.com", "manager@example.com"]' in content
    assert '"use_uid_checkpoint": true' in content
    assert "copyTextToClipboard(" in content
    assert "CLI Gmail import command copied." in content
    assert "MCP Gmail import example copied." in content
    assert "currentGmailImportAddresses()" in content
    assert "currentGmailImportFolders()" in content
    assert "currentGmailImportComplaintKeywords()" in content
    assert "const useGmailOAuth = Boolean(document.getElementById('gmail-import-use-oauth').checked);" in content
    assert "const gmailOauthClientSecrets = document.getElementById('gmail-import-oauth-client-secrets').value.trim()" in content
    assert "const checkpointName = document.getElementById('gmail-import-checkpoint-name').value.trim();" in content
    assert "const uidWindowSize = String(document.getElementById('gmail-import-uid-window-size').value || '').trim();" in content
    assert "let latestGmailImportResult = null;" in content
    assert "let latestGmailDuckdbPipelineResult = null;" in content
    assert "let latestEmailDuckdbSearchResult = null;" in content
    assert "setGmailImportAddresses(addresses)" in content
    assert "extractEmailAddresses(value)" in content
    assert "recordSuggestedGmailImportAddress(metadataByAddress, address, sourceLabel)" in content
    assert "buildSuggestedGmailImportAddresses(sessionPayload)" in content
    assert "currentGmailImportUserId()" in content
    assert "currentGmailImportClaimElement()" in content
    assert "gmailImportDetectedAddresses = [];" in content
    assert "renderGmailImportDetectedAddressChips()" in content
    assert "renderGmailImportSuggestedAddressChips()" in content
    assert "renderGmailImportCommandExamples()" in content
    assert "removeGmailImportAddress(addressToRemove)" in content
    assert "toggleGmailImportDetectedAddress(address)" in content
    assert "suggestGmailImportAddresses()" in content
    assert "No case-linked email addresses were detected yet." in content
    assert "No detected case correspondents yet" in content
    assert "No suggested correspondents yet" in content
    assert 'data-gmail-detected-address-chip="${escapeHtml(address)}"' in content
    assert "evidence title" in content
    assert "evidence source" in content
    assert "evidence content" in content
    assert "intake" in content
    assert "item.address" in content
    assert "(item.sources || []).join(', ') || 'case'" in content
    assert 'data-gmail-address-chip="${escapeHtml(address)}"' in content
    assert "Added ${address} to the Gmail import list." in content
    assert "Removed ${addressToRemove} from the Gmail import list." in content
    assert "Suggested ${suggested.length} email address" in content
    assert "JSON.stringify(mcpPayload, null, 2)" in content
    assert "--scan-folder" in content
    assert "--use-gmail-oauth" in content
    assert "--gmail-oauth-client-secrets" in content
    assert "--gmail-oauth-token-cache" in content
    assert "--no-gmail-oauth-browser" in content
    assert "--use-uid-checkpoint" in content
    assert "--checkpoint-name" in content
    assert "--uid-window-size" in content
    assert "--complaint-query" in content
    assert "--complaint-keyword" in content
    assert "--min-relevance-score" in content
    assert "folders: folders.length ? folders : ['INBOX']" in content
    assert "use_gmail_oauth: useGmailOAuth || undefined" in content
    assert "gmail_oauth_client_secrets: useGmailOAuth ? gmailOauthClientSecrets : undefined" in content
    assert "use_uid_checkpoint: true" in content
    assert "checkpoint_name: checkpointName || undefined" in content
    assert "uid_window_size: uidWindowSize ? Number(uidWindowSize) : undefined" in content
    assert "complaint_query: complaintQuery || undefined" in content
    assert "complaint_keywords: complaintKeywords" in content
    assert "min_relevance_score: Number(minRelevanceScore || '0')" in content
    assert "document.getElementById('suggest-gmail-import-addresses').addEventListener('click', suggestGmailImportAddresses);" in content
    assert "document.getElementById('gmail-import-addresses').addEventListener('input', renderGmailImportCommandExamples);" in content
    assert "document.getElementById('gmail-import-folders').addEventListener('input', renderGmailImportCommandExamples);" in content
    assert "document.getElementById('gmail-import-complaint-query').addEventListener('input', renderGmailImportCommandExamples);" in content
    assert "document.getElementById('gmail-import-complaint-keywords').addEventListener('input', renderGmailImportCommandExamples);" in content
    assert "document.getElementById('gmail-import-min-relevance-score').addEventListener('input', renderGmailImportCommandExamples);" in content
    assert "const gmailDetectedAddressChip = event.target.closest('[data-gmail-detected-address-chip]');" in content
    assert "const gmailAddressChip = event.target.closest('[data-gmail-address-chip]');" in content
    assert "document.getElementById('gmail-import-claim-element').addEventListener('change', renderGmailImportCommandExamples);" in content
    assert "document.getElementById('gmail-import-user').addEventListener('input', renderGmailImportCommandExamples);" in content
    assert "document.getElementById('gmail-import-use-oauth').addEventListener('change', renderGmailImportCommandExamples);" in content
    assert "document.getElementById('gmail-import-oauth-client-secrets').addEventListener('input', renderGmailImportCommandExamples);" in content
    assert "document.getElementById('gmail-import-oauth-token-cache').addEventListener('input', renderGmailImportCommandExamples);" in content
    assert "document.getElementById('gmail-import-oauth-open-browser').addEventListener('change', renderGmailImportCommandExamples);" in content
    assert "document.getElementById('gmail-import-checkpoint-name').addEventListener('input', renderGmailImportCommandExamples);" in content
    assert "document.getElementById('gmail-import-uid-window-size').addEventListener('input', renderGmailImportCommandExamples);" in content
    assert "Enter your Gmail app password before importing Gmail evidence, or enable Gmail OAuth." in content
    assert "Add a Gmail OAuth client-secrets JSON path before using Gmail OAuth collection." in content
    assert "UID checkpoint saved at ${payload.checkpoint_path}." in content
    assert "function renderGmailImportSummary()" in content
    assert "No Gmail import has been run in this browser session yet." in content
    assert "Imported count: ${payload.imported_count || 0}" in content
    assert "Manifest path:" in content
    assert "Checkpoint path:" in content
    assert "Checkpoint state:" in content
    assert "Imported subjects:" in content
    assert "latestGmailImportResult = payload || null;" in content
    assert "latestGmailImportResult = null;" in content
    assert "renderGmailImportSummary();" in content
    assert "renderGmailDuckdbPipelineSummary();" in content
    assert "renderEmailDuckdbSearchSummary();" in content
    assert "async function runGmailDuckdbPipelineFromWorkspace()" in content
    assert "async function searchEmailDuckdbCorpusFromWorkspace()" in content
    assert "No Gmail DuckDB pipeline has been run in this browser session yet." in content
    assert "No DuckDB email search has been run in this browser session yet." in content
    assert "document.getElementById('run-gmail-duckdb-pipeline-button').addEventListener('click', runGmailDuckdbPipelineFromWorkspace);" in content
    assert "document.getElementById('search-email-duckdb-button').addEventListener('click', searchEmailDuckdbCorpusFromWorkspace);" in content
    assert "Add at least one email address before running the Gmail DuckDB pipeline." in content
    assert "Enter a DuckDB index path before searching the email corpus." in content
    assert "Enter a search query before searching the email corpus." in content
    assert "Gmail DuckDB pipeline completed with ${payload.imported_count || 0} imported message(s)." in content
    assert "DuckDB email search completed with ${payload.result_count || (Array.isArray(payload.results) ? payload.results.length : 0)} hit(s)." in content
    assert "Pipeline: ${pipelineName}" in content
    assert "DuckDB path: ${duckdbPath || 'n/a'}" in content
    assert "Top results:" in content
    assert "async function importLocalEvidence()" in content
    assert "await client.importLocalEvidence({" in content
    assert "Add at least one local file or directory path before importing local evidence." in content
    assert "Imported ${payload.imported_count || 0} local evidence artifact(s) into the evidence workspace." in content
    assert "document.getElementById('import-local-evidence-button').addEventListener('click', importLocalEvidence);" in content
    assert "gmailImportUserStorageKey()" in content
    assert "window.sessionStorage.getItem(gmailImportUserStorageKey())" in content
    assert "window.sessionStorage.setItem(gmailImportUserStorageKey(), nextValue)" in content
    assert "window.sessionStorage.removeItem(gmailImportUserStorageKey())" in content
    assert "persistGmailImportUserPreference()" in content
    assert "hydrateGmailImportUser()" in content
    assert "refresh-tooling-contract-button" in content
    assert "tooling-contract-preview" in content
    assert "refreshToolingContractPanel()" in content
    assert "Tooling contract refreshed." in content
    assert "refresh-provider-diagnostics-button" in content
    assert "provider-diagnostics-preview" in content
    assert "packaged-docket-manifest-path" in content
    assert "packaged-docket-report-format" in content
    assert "load-packaged-docket-dashboard-button" in content
    assert "load-packaged-docket-dashboard-report-button" in content
    assert "execute-packaged-docket-revalidation-button" in content
    assert "packaged-docket-dashboard-preview" in content
    assert "packaged-docket-dashboard-report-preview" in content
    assert "packaged-docket-dashboard-execution-preview" in content
    assert "packaged-docket-dashboard-source-chip" in content
    assert "packaged-docket-dashboard-review-chip" in content
    assert "packaged-docket-dashboard-run-chip" in content
    assert "packaged-docket-dashboard-scorecard" in content
    assert "packaged-docket-dashboard-pending-count" in content
    assert "packaged-docket-dashboard-high-priority-count" in content
    assert "packaged-docket-dashboard-queue-count" in content
    assert "packaged-docket-dashboard-latest-source" in content
    assert "packaged-docket-dashboard-latest-run-preview" in content
    assert "packaged-docket-dashboard-queue-preview" in content
    assert "workspaceProviderDiagnostics = null;" in content
    assert "latestPackagedDocketOperatorDashboard = null;" in content
    assert "latestPackagedDocketOperatorDashboardReport = null;" in content
    assert "latestPackagedDocketRevalidationExecution = null;" in content
    assert "latestUiReviewResult = null;" in content
    assert "normalizeUiReadinessResultForDisplay" in content
    assert "client.getProviderDiagnostics(workspaceUserId)" in content
    assert "client.getToolingContract(workspaceUserId)" in content
    assert "client.getPackagedDocketOperatorDashboard(manifestPath)" in content
    assert "client.loadPackagedDocketOperatorDashboardReport(manifestPath, reportFormat)" in content
    assert "client.executePackagedDocketProofRevalidationQueue(manifestPath, {" in content
    assert "function renderPackagedDocketOperatorDashboardPanel()" in content
    assert "async function loadPackagedDocketOperatorDashboardPanel()" in content
    assert "async function loadPackagedDocketOperatorDashboardReportPanel()" in content
    assert "async function executePackagedDocketRevalidationPanel()" in content
    assert "Packaged Docket Ops" in content
    assert "Load Packaged Legal Ops Dashboard" in content
    assert "Pending Review" in content
    assert "High Priority" in content
    assert "Queue Size" in content
    assert "Latest Revalidation Run" in content
    assert "Queue Status" in content
    assert "Loading the packaged docket operator dashboard through the shared MCP SDK…" in content
    assert "Running packaged docket proof revalidation through the shared MCP SDK…" in content
    assert "Packaged docket proof revalidation queue executed." in content
    assert "Archived packaged docket operator dashboard report loaded." in content
    assert "document.getElementById('packaged-docket-dashboard-pending-count').textContent" in content
    assert "document.getElementById('packaged-docket-dashboard-latest-run-preview').textContent" in content
    assert "document.getElementById('packaged-docket-dashboard-queue-preview').textContent" in content
    assert "document.getElementById('packaged-docket-dashboard-execution-preview').textContent" in content
    assert "document.getElementById('load-packaged-docket-dashboard-button').addEventListener('click', loadPackagedDocketOperatorDashboardPanel);" in content
    assert "document.getElementById('load-packaged-docket-dashboard-report-button').addEventListener('click', loadPackagedDocketOperatorDashboardReportPanel);" in content
    assert "document.getElementById('execute-packaged-docket-revalidation-button').addEventListener('click', executePackagedDocketRevalidationPanel);" in content
    assert "refreshProviderDiagnosticsPanel()" in content
    assert "Provider diagnostics refreshed." in content
    assert "Router provider diagnostics" in content
    assert "Complaint draft default:" in content
    assert "Complaint draft fallback chain:" in content
    assert "Effective default:" in content
    assert "Preference order:" in content
    assert "UI review default:" in content
    assert "UI review rate-limit fallback chain:" in content
    assert "UI review HF fallback model:" in content
    assert "multimodal ui review:" in content
    assert "Screenshot-driven optimization target" in content
    assert "Carry-forward assessment" in content
    assert "unresolved prior findings:" in content
    assert "continuity-gating-summary" in content
    assert "continuity-session-chip" in content
    assert "continuity-phase-chip" in content
    assert "continuity-phase-note" in content
    assert "handoff-review-gating-note" in content
    assert "handoff-builder-gating-note" in content
    assert "integrations-operations-lane" in content
    assert "integrations-operations-guidance" in content
    assert "integrations-operations-preview" in content
    assert "operations-tool-readiness-button" in content
    assert "operations-mediator-tool-button" in content
    assert "operations-export-tool-button" in content
    assert "operations-ui-audit-tool-button" in content
    assert "tool-list-summary" in content
    assert "tool-list-phase-chips" in content
    assert "classifyToolFamily" in content
    assert "session-sync-summary" in content
    assert "session-sync-did-chip" in content
    assert "session-sync-phase-chip" in content
    assert "session-sync-draft-chip" in content
    assert "session-tool-activity-summary" in content
    assert "session-tool-activity-tool-chip" in content
    assert "session-tool-activity-status-chip" in content
    assert "session-tool-activity-ledger" in content
    assert "renderSessionSyncStatus" in content
    assert "latestSdkToolActivity" in content
    assert "loadLastSdkToolActivity" in content
    assert "loadSdkToolActivityLedger" in content
    assert "complaintGenerator.sdkToolLedger" in content
    assert "Invocation ledger is waiting for SDK activity." in content
    assert "complaint-mcp-sdk-call" in content
    assert "resolveDraftState" in content
    assert "draftStatusCopy" in content
    assert "hydrateResolvedDraftState" in content
    assert "tooling-parity-preview" in content
    assert "sdkToMcpParityMap" in content
    assert "runGmailDuckdbPipeline: 'complaint.run_gmail_duckdb_pipeline'" in content
    assert "searchEmailDuckdb: 'complaint.search_email_duckdb_corpus'" in content
    assert "Browser SDK parity summary" in content
    assert "buildSessionBoundParityExamples" in content
    assert "Session-bound tooling handoff" in content
    assert "Run the same live session through package, CLI, MCP, or SDK without rewriting the user id by hand." in content
    assert "Inspect this session" in content
    assert "Review current support posture" in content
    assert "Export this complaint packet" in content
    assert "complaint.export_complaint_packet" in content
    assert "renderOperationalToolLane" in content
    assert "runOperationalToolReadiness" in content
    assert "runOperationalMediatorHandoff" in content
    assert "runOperationalExportReview" in content
    assert "setButtonGateState" in content
    assert "setLinkGateState" in content
    assert "deriveWorkflowState" in content
    assert "workspace-nav-builder" in content
    assert "workspace-nav-review" in content
    assert "workspace-advanced-nav" in content
    assert "Developer tools and linked surfaces" in content
    assert "What is complete" in content
    assert "Exactly what to do next" in content
    assert "What still needs support" in content
    assert "readiness: intake underway" in content
    assert "readiness: support gaps open" in content
    assert "readiness: first draft available soon" in content
    assert "readiness: ${sidebarCanonicalReadiness.formAssessment.label} form / ${sidebarCanonicalReadiness.supportAssessment.label} support" in content
    assert "% of workflow mapped" in content
    assert "draft-export-integrity-preview" in content
    assert "complaintSectionChecks" in content
    assert "complaintPlaceholderWarnings" in content
    assert "renderDraftExportIntegrity" in content
    assert "Required section checks:" in content
    assert "Civil Action No. is still a placeholder." in content
    assert "formatGapActionLabel" in content
    assert "activeWorkspaceTab" in content
    assert "focusRailStateForTab" in content
    assert "activeStageLabelForTab" in content
    assert "humanizeCasePhaseLabel" in content
    assert "supportStrengthAssessment" in content
    assert "pleadingFormAssessment" in content
    assert "buildCanonicalFilingReadiness" in content
    assert "buildCanonicalActionQueue" in content
    assert "Canonical action queue loading" in content
    assert "Canonical Next Move" in content
    assert "Complete" in content
    assert "Do next" in content
    assert "Watch for" in content
    assert "support-strength-map" in content
    assert "describeSupportStrength" in content
    assert "Per-element proof map" in content
    assert "Counts alone can be misleading." in content
    assert "grounded" in content
    assert "thin" in content
    assert "unsupported" in content
    assert "sdk: complaint.submit_intake" in content
    assert "sdk: complaint.save_evidence" in content
    assert "sdk: complaint.review_case" in content
    assert "sdk: complaint.generate_complaint" in content
    assert "sdk: complaint.get_tooling_contract" in content
    assert "sdk: complaint.review_ui" in content
    assert "case phase:" in content
    assert "Current stage: ${activeStageLabel.toLowerCase()}" in content
    assert "active stage: ${activeStageLabel.toLowerCase()}" in content
    assert "Case phase: ${casePhaseLabel}." in content
    assert "You are in Intake." in content
    assert "You are in Evidence." in content
    assert "You are in Review." in content
    assert "You are in Draft." in content
    assert "You are in CLI + MCP." in content
    assert "You are in UX Audit." in content
    assert "What name should we use for the person harmed?" in content
    assert "What did they report, oppose, or ask for help about?" in content
    assert "What happened after that?" in content
    assert "How did this affect them?" in content
    assert "You can save and return anytime. Share only what you can right now." in content
    assert "The workspace will guide one calm step at a time." in content
    assert "Add testimony for ${escapeHtml(item.label)}" in content
    assert "Upload document for ${escapeHtml(item.label)}" in content
    assert "formatGapActionLabel('Attach document', weakestGap)" in content
    assert "surface-link.is-disabled" in content
    assert "Screenshot-linked critic lanes" in content
    assert "evidence-add-testimony-button" in content
    assert "evidence-add-document-button" in content
    assert "evidence-shortcut-action" in content
    assert "openEvidenceForGap" in content
    assert "resolveSupportGap" in content
    assert 'data-evidence-kind="${escapeHtml(action.kind || \'testimony\')}"' in content
    assert 'data-evidence-kind="testimony"' in content
    assert 'data-evidence-kind="document"' in content
    assert "draft-export-safety-preview" in content
    assert "Open readiness check" in content
    assert "Readiness check:" in content
    assert "Canonical filing readiness" in content
    assert "Pleading form quality:" in content
    assert "Evidence support strength:" in content
    assert "Download complaint files:" in content
    assert "activateEvidenceComposer" in content
    assert "screenshot findings:" in content
    assert "optimization targets:" in content
    assert "item.criticisms" in content
    assert "document.getElementById('refresh-provider-diagnostics-button').addEventListener('click', refreshProviderDiagnosticsPanel);" in content
