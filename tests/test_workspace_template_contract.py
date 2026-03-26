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
    assert "workspaceProviderDiagnostics = null;" in content
    assert "latestUiReviewResult = null;" in content
    assert "normalizeUiReadinessResultForDisplay" in content
    assert "client.getProviderDiagnostics(workspaceUserId)" in content
    assert "client.getToolingContract(workspaceUserId)" in content
    assert "refreshProviderDiagnosticsPanel()" in content
    assert "Provider diagnostics refreshed." in content
    assert "Router provider diagnostics" in content
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
    assert "renderSessionSyncStatus" in content
    assert "latestSdkToolActivity" in content
    assert "loadLastSdkToolActivity" in content
    assert "complaint-mcp-sdk-call" in content
    assert "resolveDraftState" in content
    assert "draftStatusCopy" in content
    assert "hydrateResolvedDraftState" in content
    assert "tooling-parity-preview" in content
    assert "sdkToMcpParityMap" in content
    assert "Browser SDK parity summary" in content
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
    assert "record: materially supported" in content
    assert "record: thin corroboration" in content
    assert "record: developing" in content
    assert "record: early intake" in content
    assert "% of workflow mapped" in content
    assert "draft-export-integrity-preview" in content
    assert "complaintSectionChecks" in content
    assert "complaintPlaceholderWarnings" in content
    assert "renderDraftExportIntegrity" in content
    assert "Required section checks:" in content
    assert "Civil Action No. is still a placeholder." in content
    assert "formatGapActionLabel" in content
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
    assert "activateEvidenceComposer" in content
    assert "screenshot findings:" in content
    assert "optimization targets:" in content
    assert "item.criticisms" in content
    assert "document.getElementById('refresh-provider-diagnostics-button').addEventListener('click', refreshProviderDiagnosticsPanel);" in content
