(function (globalScope) {
class ComplaintMcpClient {
    constructor(options = {}) {
        this.baseUrl = options.baseUrl || '/api/complaint-workspace';
        this.mcpBaseUrl = options.mcpBaseUrl || `${this.baseUrl}/mcp`;
        this.origin = options.origin || (typeof window !== 'undefined' && window.location ? window.location.origin : 'http://localhost');
        this.fetchImpl = options.fetchImpl || (typeof fetch === 'function' ? fetch.bind(globalThis) : null);
        this._requestId = 1;
        this.didStorageKey = options.didStorageKey || 'complaintGenerator.did';
        this.lastToolCallStorageKey = options.lastToolCallStorageKey || 'complaintGenerator.sdkLastToolCall';
        this.toolCallLedgerStorageKey = options.toolCallLedgerStorageKey || 'complaintGenerator.sdkToolLedger';
        this.maxToolLedgerEntries = Number(options.maxToolLedgerEntries || 8);
    }

    initialize() {
        return this.callJsonRpc('initialize', {
            clientInfo: {
                name: 'complaint-generator-browser-sdk',
                version: '0.1.0',
            },
        });
    }

    async _request(path, options = {}) {
        if (typeof this.fetchImpl !== 'function') {
            throw new Error('ComplaintMcpClient requires a fetch implementation.');
        }
        const response = await this.fetchImpl(path, Object.assign({
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin',
        }, options));
        if (!response.ok) {
            const text = await response.text();
            throw new Error(text || (`Request failed with status ${response.status}`));
        }
        return response.json();
    }

    async _rpc(method, params) {
        const payload = await this._request(`${this.mcpBaseUrl}/rpc`, {
            method: 'POST',
            body: JSON.stringify({
                jsonrpc: '2.0',
                id: this._requestId++,
                method,
                params: params || {},
            }),
        });
        if (payload.error) {
            throw new Error(payload.error.message || 'JSON-RPC request failed');
        }
        return payload.result;
    }

    callJsonRpc(method, params) {
        return this._rpc(method, params);
    }

    _cacheLastToolCall(detail) {
        if (typeof localStorage === 'undefined') {
            return detail;
        }
        try {
            localStorage.setItem(this.lastToolCallStorageKey, JSON.stringify(detail));
            const existing = this.getToolCallLedger();
            const ledger = [detail].concat(existing).slice(0, this.maxToolLedgerEntries);
            localStorage.setItem(this.toolCallLedgerStorageKey, JSON.stringify(ledger));
        } catch (error) {
            return detail;
        }
        return detail;
    }

    _publishLastToolCall(detail) {
        this._cacheLastToolCall(detail);
        if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function' && typeof CustomEvent === 'function') {
            window.dispatchEvent(new CustomEvent('complaint-mcp-sdk-call', { detail }));
        }
        return detail;
    }

    getLastToolCall() {
        if (typeof localStorage === 'undefined') {
            return null;
        }
        try {
            const raw = localStorage.getItem(this.lastToolCallStorageKey);
            return raw ? JSON.parse(raw) : null;
        } catch (error) {
            return null;
        }
    }

    getToolCallLedger() {
        if (typeof localStorage === 'undefined') {
            return [];
        }
        try {
            const raw = localStorage.getItem(this.toolCallLedgerStorageKey);
            const parsed = raw ? JSON.parse(raw) : [];
            return Array.isArray(parsed) ? parsed : [];
        } catch (error) {
            return [];
        }
    }

    getToolImpactSummary() {
        const ledger = this.getToolCallLedger();
        const latest = ledger[0] || null;
        const successCount = ledger.filter((item) => String((item && item.status) || '').toLowerCase() === 'success').length;
        const errorCount = ledger.filter((item) => String((item && item.status) || '').toLowerCase() === 'error').length;
        return {
            total_calls: ledger.length,
            success_count: successCount,
            error_count: errorCount,
            latest_tool_name: latest ? String(latest.tool_name || '').trim() : '',
            latest_status: latest ? String(latest.status || '').trim() : '',
            latest_finished_at: latest ? String(latest.finished_at || '').trim() : '',
        };
    }

    async getWorkflowOperationSnapshot(userId) {
        const [releaseGate, workflowCapabilities, toolingContract] = await Promise.all([
            this.getCanonicalReleaseGate(userId),
            this.getWorkflowCapabilities(userId),
            this.getToolingContract(userId),
        ]);
        return {
            tool_impact_summary: this.getToolImpactSummary(),
            canonical_release_gate: releaseGate,
            workflow_capabilities: workflowCapabilities,
            tooling_contract: toolingContract,
        };
    }

    ping() {
        return this.callJsonRpc('ping', {});
    }

    async listTools() {
        const result = await this._rpc('tools/list', {});
        return result.tools || [];
    }

    _extractToolDiagnostics(payload) {
        const structured = payload && typeof payload === 'object' ? payload : {};
        const diagnostics = [];
        const directSearchDiagnostics = structured.search_diagnostics && typeof structured.search_diagnostics === 'object'
            ? structured.search_diagnostics
            : null;
        const authorityDiagnostics = structured.authorities_diagnostics && typeof structured.authorities_diagnostics === 'object'
            ? structured.authorities_diagnostics
            : null;

        const appendDiagnosticEntries = (scope, container) => {
            if (!container || typeof container !== 'object') {
                return;
            }
            Object.entries(container).forEach(([key, value]) => {
                if (!value || typeof value !== 'object' || !value.warning_code) {
                    return;
                }
                diagnostics.push({
                    scope: scope,
                    family: key,
                    warning_code: String(value.warning_code || '').trim(),
                    warning_message: String(value.warning_message || '').trim(),
                    state_code: String(value.state_code || '').trim(),
                    hf_dataset_id: String(value.hf_dataset_id || '').trim(),
                });
            });
        };

        appendDiagnosticEntries('search', directSearchDiagnostics);
        if (authorityDiagnostics) {
            Object.entries(authorityDiagnostics).forEach(([claimType, value]) => {
                if (!value || typeof value !== 'object') {
                    return;
                }
                const claimScope = 'claim:' + String(claimType || '').trim();
                appendDiagnosticEntries(claimScope, value);
            });
        }

        return diagnostics;
    }

    _buildToolDiagnosticSummary(payload) {
        const diagnostics = this._extractToolDiagnostics(payload);
        const warningCount = diagnostics.length;
        const primary = diagnostics[0] || null;
        return {
            warning_count: warningCount,
            warnings: diagnostics,
            primary_warning: primary,
            summary_text: primary && primary.warning_message
                ? primary.warning_message
                : '',
        };
    }

    async callTool(toolName, argumentsPayload) {
        const startedAt = new Date().toISOString();
        try {
            const result = await this._rpc('tools/call', {
                name: toolName,
                arguments: argumentsPayload || {},
            });
            const structuredContent = result && result.structuredContent ? result.structuredContent : result;
            const diagnosticSummary = this._buildToolDiagnosticSummary(structuredContent);
            this._publishLastToolCall({
                tool_name: toolName,
                status: 'success',
                started_at: startedAt,
                finished_at: new Date().toISOString(),
                diagnostic_summary: diagnosticSummary,
            });
            if (result && result.structuredContent) {
                return result.structuredContent;
            }
            return result;
        } catch (error) {
            this._publishLastToolCall({
                tool_name: toolName,
                status: 'error',
                started_at: startedAt,
                finished_at: new Date().toISOString(),
                error_message: error && error.message ? error.message : String(error),
            });
            throw error;
        }
    }

    startSession(userId) {
        return this.callTool('complaint.start_session', {
            user_id: userId,
        });
    }

    createIdentity() {
        return this._request(`${this.baseUrl}/identity`, {
            method: 'POST',
            body: JSON.stringify({}),
        });
    }

    listIntakeQuestions() {
        return this.callTool('complaint.list_intake_questions', {});
    }

    listClaimElements() {
        return this.callTool('complaint.list_claim_elements', {});
    }

    getCachedDid() {
        if (typeof localStorage === 'undefined') {
            return null;
        }
        return localStorage.getItem(this.didStorageKey);
    }

    cacheDid(did) {
        if (typeof localStorage !== 'undefined') {
            localStorage.setItem(this.didStorageKey, did);
        }
        return did;
    }

    async getOrCreateDid() {
        const cachedDid = this.getCachedDid();
        if (cachedDid) {
            return cachedDid;
        }
        const identity = await this.createIdentity();
        if (!identity || !identity.did) {
            throw new Error('Identity endpoint did not return a DID.');
        }
        return this.cacheDid(identity.did);
    }

    async bootstrapWorkspace(userId) {
        const did = userId || await this.getOrCreateDid();
        const [initialization, tools, session] = await Promise.all([
            this.initialize(),
            this.listTools(),
            this.startSession(did),
        ]);
        return {
            did,
            initialization,
            tools,
            session,
        };
    }

    getSession(userId) {
        const url = new URL(`${this.baseUrl}/session`, this.origin);
        if (userId) {
            url.searchParams.set('user_id', userId);
        }
        return this._request(url.toString());
    }

    submitIntake(userId, answers) {
        return this.callTool('complaint.submit_intake', {
            user_id: userId,
            answers: answers || {},
        });
    }

    runIntakeChatTurn(userId, message, questionId) {
        return this.callTool('complaint.run_intake_chat_turn', {
            user_id: userId,
            message: message || undefined,
            question_id: questionId || undefined,
        });
    }

    saveEvidence(userId, payload) {
        return this.callTool('complaint.save_evidence', Object.assign({
            user_id: userId,
        }, payload || {}));
    }

    importGmailEvidence(payload) {
        return this.callTool('complaint.import_gmail_evidence', payload || {});
    }

    importLocalEvidence(payload) {
        return this.callTool('complaint.import_local_evidence', payload || {});
    }

    runGmailDuckdbPipeline(payload) {
        return this.callTool('complaint.run_gmail_duckdb_pipeline', payload || {});
    }

    searchEmailDuckdb(payload) {
        return this.callTool('complaint.search_email_duckdb_corpus', payload || {});
    }

    reviewCase(userId) {
        return this.callTool('complaint.review_case', {
            user_id: userId,
        });
    }

    buildMediatorPrompt(userId) {
        return this.callTool('complaint.build_mediator_prompt', {
            user_id: userId,
        });
    }

    getComplaintReadiness(userId) {
        return this.callTool('complaint.get_complaint_readiness', {
            user_id: userId,
        });
    }

    getUiReadiness(userId) {
        return this.callTool('complaint.get_ui_readiness', {
            user_id: userId,
        });
    }

    getClientReleaseGate(userId) {
        return this.callTool('complaint.get_client_release_gate', {
            user_id: userId,
        });
    }

    toCanonicalReleaseGate(payload) {
        const source = (payload && typeof payload === 'object') ? payload : {};
        const gate = source.complaint_output_release_gate || source.release_gate || source;
        const verdict = String((gate && (gate.verdict || gate.status)) || 'unknown').trim().toLowerCase() || 'unknown';
        const blockers = Array.isArray(gate && gate.blockers)
            ? gate.blockers
            : Array.isArray(gate && gate.blocking_reasons)
                ? gate.blocking_reasons
                : String((gate && gate.reason) || '').trim()
                    ? [String(gate.reason).trim()]
                    : [];
        const updatedAt = String((gate && gate.updated_at) || (source && source.updated_at) || '').trim() || new Date().toISOString();
        const gateSource = String((gate && gate.source) || (source && source.source) || 'complaint.get_client_release_gate').trim();
        const version = String((gate && (gate.version || gate.state_version)) || (source && (source.version || source.state_version)) || 'workspace-gate-v1').trim();
        const reason = String((gate && gate.reason) || '').trim() || (blockers[0] || '');
        const unblockAction = String((gate && (gate.next_best_action || gate.unblock_action)) || '').trim();
        const status = String((gate && gate.status) || verdict || 'unknown').trim().toUpperCase();
        return {
            verdict,
            status,
            blockers,
            blocking_reasons: blockers,
            updated_at: updatedAt,
            source: gateSource,
            version,
            state_version: version,
            next_best_action: unblockAction,
            canonical_gate: {
                verdict,
                status,
                reason,
                unblock_action: unblockAction,
                next_best_action: unblockAction,
                source: gateSource,
                timestamp: updatedAt,
                version,
                state_version: version,
                blocking_reasons: blockers,
            },
            reason,
            unblock_action: unblockAction,
            claim_type_label: String((gate && gate.claim_type_label) || '').trim() || 'Unknown',
            draft_strategy: String((gate && gate.draft_strategy) || '').trim() || 'template',
            filing_shape_score: Number((gate && gate.filing_shape_score) || 0),
            claim_type_alignment_score: Number((gate && gate.claim_type_alignment_score) || 0),
        };
    }

    async getCanonicalReleaseGate(userId) {
        const payload = await this.getClientReleaseGate(userId);
        return this.toCanonicalReleaseGate(payload);
    }

    getWorkflowCapabilities(userId) {
        return this.callTool('complaint.get_workflow_capabilities', {
            user_id: userId,
        });
    }

    getToolingContract(userId) {
        return this.callTool('complaint.get_tooling_contract', {
            user_id: userId,
        });
    }

    getWorkspaceDataSchema(userId, options = {}) {
        return this.callTool('complaint.get_workspace_data_schema', Object.assign({
            user_id: userId,
        }, options || {}));
    }

    migrateLegacyWorkspaceData(userId, outputDir, options = {}) {
        return this.callTool('complaint.migrate_legacy_workspace_data', Object.assign({
            user_id: userId,
            output_dir: outputDir,
        }, options || {}));
    }

    searchWorkspaceDataset(inputPath, query, options = {}) {
        return this.callTool('complaint.search_workspace_dataset', Object.assign({
            input_path: inputPath,
            query: query,
        }, options || {}));
    }

    viewWorkspaceDataset(inputPath, options = {}) {
        return this.callTool('complaint.view_workspace_dataset', Object.assign({
            input_path: inputPath,
        }, options || {}));
    }

    getPackagedDocketOperatorDashboard(manifestPath) {
        return this.callTool('complaint.get_packaged_docket_operator_dashboard', {
            manifest_path: manifestPath,
        });
    }

    loadPackagedDocketOperatorDashboardReport(manifestPath, reportFormat = 'parsed') {
        return this.callTool('complaint.load_packaged_docket_operator_dashboard_report', {
            manifest_path: manifestPath,
            report_format: reportFormat || 'parsed',
        });
    }

    executePackagedDocketProofRevalidationQueue(manifestPath, options = {}) {
        return this.callTool('complaint.execute_packaged_docket_proof_revalidation_queue', Object.assign({
            manifest_path: manifestPath,
        }, options || {}));
    }

    persistPackagedDocketProofRevalidationQueue(manifestPath, outputDir, options = {}) {
        return this.callTool('complaint.persist_packaged_docket_proof_revalidation_queue', Object.assign({
            manifest_path: manifestPath,
            output_dir: outputDir,
        }, options || {}));
    }

    generateComplaint(userId, payload) {
        return this.callTool('complaint.generate_complaint', Object.assign({
            user_id: userId,
        }, payload || {}));
    }

    updateDraft(userId, payload) {
        return this.callTool('complaint.update_draft', Object.assign({
            user_id: userId,
        }, payload || {}));
    }

    exportComplaintPacket(userId) {
        return this.callTool('complaint.export_complaint_packet', {
            user_id: userId,
        });
    }

    exportComplaintMarkdown(userId) {
        return this.callTool('complaint.export_complaint_markdown', {
            user_id: userId,
        });
    }

    exportComplaintDocx(userId) {
        return this.callTool('complaint.export_complaint_docx', {
            user_id: userId,
        });
    }

    exportComplaintPdf(userId) {
        return this.callTool('complaint.export_complaint_pdf', {
            user_id: userId,
        });
    }

    analyzeComplaintOutput(userId) {
        return this.callTool('complaint.analyze_complaint_output', {
            user_id: userId,
        });
    }

    getFormalDiagnostics(userId) {
        return this.callTool('complaint.get_formal_diagnostics', {
            user_id: userId,
        });
    }

    getFilingProvenance(userId) {
        return this.callTool('complaint.get_filing_provenance', {
            user_id: userId,
        });
    }

    getProviderDiagnostics(userId) {
        return this.callTool('complaint.get_provider_diagnostics', {
            user_id: userId,
        });
    }

    reviewGeneratedExports(payload) {
        return this.callTool('complaint.review_generated_exports', payload || {});
    }

    updateClaimType(userId, claimType) {
        return this.callTool('complaint.update_claim_type', {
            user_id: userId,
            claim_type: claimType,
        });
    }

    downloadComplaintPacketUrl(userId, outputFormat) {
        const url = new URL(`${this.baseUrl}/export/download`, this.origin);
        if (userId) {
            url.searchParams.set('user_id', userId);
        }
        if (outputFormat) {
            url.searchParams.set('output_format', outputFormat);
        }
        return url.toString();
    }

    updateCaseSynopsis(userId, synopsis) {
        return this.callTool('complaint.update_case_synopsis', {
            user_id: userId,
            synopsis: synopsis || '',
        });
    }

    resetSession(userId) {
        return this.callTool('complaint.reset_session', {
            user_id: userId,
        });
    }

    reviewUiArtifacts(payload) {
        return this.callTool('complaint.review_ui', payload || {});
    }

    optimizeUiArtifacts(payload) {
        return this.callTool('complaint.optimize_ui', payload || {});
    }

    runUiUxWorkflow(payload) {
        return this.reviewUiArtifacts(payload);
    }

    runClosedLoopUiUxWorkflow(payload) {
        return this.optimizeUiArtifacts(payload);
    }

    runBrowserAudit(payload) {
        return this.callTool('complaint.run_browser_audit', payload || {});
    }
}


const ComplaintMcpSdk = { ComplaintMcpClient, default: ComplaintMcpClient };

  if (globalScope) {
    globalScope.ComplaintMcpSdk = Object.assign({}, globalScope.ComplaintMcpSdk || {}, ComplaintMcpSdk);
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = ComplaintMcpSdk;
  }
})(typeof globalThis !== 'undefined' ? globalThis : (typeof window !== 'undefined' ? window : this));
