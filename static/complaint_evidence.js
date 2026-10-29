/* Private evidence upload. Progress comes from the case upload API.
   The browser does not treat a local file selection as ingestion. */
(function () {
    var CHUNK = 32 * 1024;

    function panel() {
        return document.getElementById("evidence-private-upload");
    }

    function text(id, value) {
        var node = document.getElementById(id);
        if (node) node.textContent = value;
    }

    function caseContext() {
        var client = window.workspaceClient;
        return client && client.caseContext ? client.caseContext : null;
    }

    function headers() {
        var client = window.workspaceClient;
        var context = caseContext();
        var result = {"Content-Type": "application/json", "Accept": "application/json"};
        if (context) {
            result["x-tenant-id"] = context.tenant_id;
            result["x-case-id"] = context.case_id;
            result["x-resource-id"] = context.resource_id;
            if (context.expected_revision) result["x-expected-revision"] = String(context.expected_revision);
        }
        if (client && client.csrfToken) result["x-csrf-token"] = client.csrfToken;
        return result;
    }

    function identity(extra) {
        var context = caseContext();
        var body = {
            tenant_id: context.tenant_id,
            case_id: context.case_id,
            resource_id: context.resource_id,
            expected_revision: context.expected_revision
        };
        Object.keys(extra || {}).forEach(function (key) { body[key] = extra[key]; });
        return body;
    }

    function paint(state, status, ingestion, percent) {
        var root = panel();
        if (!root) return;
        var bounded = Math.max(0, Math.min(100, Number(percent) || 0));
        if (state !== "sealed") bounded = Math.min(bounded, 99);
        root.dataset.state = state;
        root.dataset.progress = String(bounded);
        if (state === "pending") {
            var prior = Number(root.dataset.maxPending || "0");
            if (bounded > prior) root.dataset.maxPending = String(bounded);
        }
        text("evidence-upload-status", status);
        var ingestionNode = document.getElementById("evidence-upload-ingestion");
        if (ingestionNode) {
            ingestionNode.dataset.ingestion = ingestion || "";
            ingestionNode.textContent = ingestion ? ("Ingestion status: " + ingestion) : "Ingestion has not started.";
        }
        var progress = document.getElementById("evidence-upload-progress");
        if (progress) {
            progress.value = bounded;
            progress.textContent = bounded + "%";
        }
    }

    function classify(error) {
        if (error === "key_unavailable") return "locked";
        if (error === "operation_revoked" || error === "unauthenticated") return "revoked";
        if (error === "revision_conflict" || error === "upload_stale") return "stale";
        if (error === "not_owner" || error === "tenant_mismatch" || error === "media_rejected" || error === "oversized" || error === "selector_rejected") return "denied";
        return "error";
    }

    function bytesToBase64(bytes) {
        var binary = "";
        var step = 0x8000;
        for (var index = 0; index < bytes.length; index += step) {
            binary += String.fromCharCode.apply(null, bytes.subarray(index, index + step));
        }
        return btoa(binary);
    }

    async function sha256(bytes) {
        var digest = await crypto.subtle.digest("SHA-256", bytes);
        return Array.from(new Uint8Array(digest)).map(function (part) {
            return part.toString(16).padStart(2, "0");
        }).join("");
    }

    function mediaFor(file) {
        var name = String(file.name || "").toLowerCase();
        if (name.endsWith(".html") || name.endsWith(".htm") || name.endsWith(".svg") || name.endsWith(".js") || name.endsWith(".exe")) {
            return file.type || "text/html";
        }
        if (file.type && file.type.indexOf("/") > 0) return file.type;
        if (name.endsWith(".pdf")) return "application/pdf";
        if (name.endsWith(".png")) return "image/png";
        if (name.endsWith(".jpg") || name.endsWith(".jpeg")) return "image/jpeg";
        if (name.endsWith(".tif") || name.endsWith(".tiff")) return "image/tiff";
        if (name.endsWith(".csv")) return "text/csv";
        if (name.endsWith(".txt")) return "text/plain";
        return file.type || "application/octet-stream";
    }

    async function post(path, body, signal) {
        var response = await fetch(path, {
            method: "POST",
            credentials: "same-origin",
            headers: headers(),
            body: JSON.stringify(body),
            signal: signal
        });
        var payload = null;
        try { payload = await response.json(); } catch (error) { payload = null; }
        return {ok: response.ok, status: response.status, payload: payload || {}};
    }

    function remember(payload) {
        var root = panel();
        if (!root || !payload) return;
        if (payload.upload_id) root.dataset.uploadId = payload.upload_id;
        if (payload.upload_generation) root.dataset.uploadGeneration = String(payload.upload_generation);
        if (payload.evidence_id) root.dataset.evidenceId = payload.evidence_id;
        root.dataset.uploadState = payload.upload_state || "";
    }

    function fail(payload) {
        var error = payload && payload.error ? payload.error : "upload_failed";
        var root = panel();
        if (root) {
            root.dataset.error = error;
            root.dataset.evidenceId = "";
        }
        paint(classify(error), "Upload stopped: " + error + ".", payload && payload.ingestion_status, 0);
        return payload;
    }

    async function selectedFile() {
        var input = document.getElementById("evidence-attachment");
        if (!input || !input.files || !input.files[0]) return null;
        return input.files[0];
    }

    async function begin(file) {
        var root = panel();
        var signature = [file.name, file.size, file.lastModified].join(":");
        if (!root.dataset.idempotencyKey || root.dataset.fileSignature !== signature) {
            root.dataset.idempotencyKey = "ev-upload-" + signature.replace(/[^A-Za-z0-9._-]+/g, "-").slice(0, 80);
            root.dataset.fileSignature = signature;
            root.dataset.evidenceId = "";
        }
        var bytes = new Uint8Array(await file.arrayBuffer());
        root._fileBytes = bytes;
        var opened = await post("/api/cases/evidence/uploads", identity({
            source_filename: file.name,
            original_filename: file.name,
            media_type: mediaFor(file),
            byte_length: bytes.length,
            content_sha256: await sha256(bytes),
            idempotency_key: root.dataset.idempotencyKey
        }));
        if (!opened.ok) return fail(opened.payload);
        remember(opened.payload);
        paint(opened.payload.upload_state === "sealed" ? "sealed" : "pending", "Private upload started.", opened.payload.ingestion_status, opened.payload.progress_percent);
        return opened.payload;
    }

    async function sendChunks(signal) {
        var root = panel();
        var bytes = root._fileBytes;
        var offset = 0;
        while (bytes && offset < bytes.length) {
            if (signal.aborted) throw new DOMException("aborted", "AbortError");
            var slice = bytes.subarray(offset, offset + CHUNK);
            var sent = await post("/api/cases/evidence/uploads/chunk", identity({
                upload_id: root.dataset.uploadId,
                upload_generation: Number(root.dataset.uploadGeneration),
                offset: offset,
                content_base64: bytesToBase64(slice)
            }), signal);
            if (!sent.ok) return fail(sent.payload);
            remember(sent.payload);
            paint("pending", "Uploading through the private case store.", "", sent.payload.progress_percent);
            offset += slice.length;
        }
        return true;
    }

    async function complete() {
        var root = panel();
        var done = await post("/api/cases/evidence/uploads/complete", identity({
            upload_id: root.dataset.uploadId,
            upload_generation: Number(root.dataset.uploadGeneration)
        }));
        if (!done.ok) return fail(done.payload);
        remember(done.payload);
        root._fileBytes = null;
        paint("sealed", "Upload sealed in the private case store.", done.payload.ingestion_status, 100);
        if (window.complaintEvidenceLibrary) window.complaintEvidenceLibrary.refresh();
        return done.payload;
    }

    async function start() {
        var root = panel();
        if (!root) return;
        if (!caseContext() || !caseContext().expected_revision) {
            paint("denied", "Select the case before uploading evidence.", "", 0);
            return;
        }
        var file = await selectedFile();
        if (!file) {
            paint("empty", "Choose a file to upload through the private case store.", "", 0);
            return;
        }
        root._controller = new AbortController();
        paint("pending", "Opening a private upload.", "", 0);
        var opened = await begin(file);
        if (!opened || opened.error || opened.upload_state === "sealed") return opened;
        var streamed = await sendChunks(root._controller.signal).catch(function (error) {
            if (error && error.name === "AbortError") return null;
            throw error;
        });
        if (streamed == null) return null;
        if (streamed !== true) return streamed;
        return complete();
    }

    async function cancel() {
        var root = panel();
        if (!root || !root.dataset.uploadId) {
            paint("empty", "There is no private upload to cancel.", "", 0);
            return;
        }
        if (root._controller) root._controller.abort();
        var stopped = await post("/api/cases/evidence/uploads/cancel", identity({
            upload_id: root.dataset.uploadId,
            upload_generation: Number(root.dataset.uploadGeneration)
        }));
        root._fileBytes = null;
        if (!stopped.ok && !(stopped.payload && stopped.payload.error === "operation_revoked")) {
            if (stopped.payload && stopped.payload.error) return fail(stopped.payload);
        }
        remember(stopped.payload);
        root.dataset.evidenceId = "";
        paint("revoked", "Upload cancelled. The file was not ingested.", "", 0);
        return stopped.payload;
    }

    async function retry() {
        var root = panel();
        if (!root || !root.dataset.uploadId) {
            paint("empty", "There is no private upload to retry.", "", 0);
            return;
        }
        if (root.dataset.uploadState === "sealed") {
            var again = await post("/api/cases/evidence/uploads/retry", identity({
                upload_id: root.dataset.uploadId,
                upload_generation: Number(root.dataset.uploadGeneration)
            }));
            if (!again.ok) return fail(again.payload);
            remember(again.payload);
            paint("sealed", "Idempotent retry returned the sealed upload.", again.payload.ingestion_status, 100);
            if (window.complaintEvidenceLibrary) window.complaintEvidenceLibrary.refresh();
            return again.payload;
        }
        var resumed = await post("/api/cases/evidence/uploads/retry", identity({
            upload_id: root.dataset.uploadId,
            upload_generation: Number(root.dataset.uploadGeneration)
        }));
        if (!resumed.ok) return fail(resumed.payload);
        remember(resumed.payload);
        var file = await selectedFile();
        if (!file) {
            paint("error", "Choose the same file again before retrying the upload.", "", 0);
            return resumed.payload;
        }
        root._controller = new AbortController();
        root._fileBytes = new Uint8Array(await file.arrayBuffer());
        paint("pending", "Retrying the private upload.", "", 0);
        var streamed = await sendChunks(root._controller.signal);
        if (streamed !== true) return streamed;
        return complete();
    }

    function bind() {
        var startButton = document.getElementById("evidence-upload-start");
        var cancelButton = document.getElementById("evidence-upload-cancel");
        var retryButton = document.getElementById("evidence-upload-retry");
        if (startButton) startButton.addEventListener("click", function () { start().catch(function () { paint("error", "Upload failed before the private store responded.", "", 0); }); });
        if (cancelButton) cancelButton.addEventListener("click", function () { cancel().catch(function () { paint("error", "Cancel failed before the private store responded.", "", 0); }); });
        if (retryButton) retryButton.addEventListener("click", function () { retry().catch(function () { paint("error", "Retry failed before the private store responded.", "", 0); }); });
    }

    window.complaintEvidenceUpload = {start: start, cancel: cancel, retry: retry};
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
    else bind();
}());

(function () {
    var QUALITIES = ["authenticity", "relevance", "admissibility", "claim_support"];
    var generation = 0;
    var previewGeneration = 0;
    var items = [];
    var itemsScope = null;
    var selectedId = "";
    var readAt = "";
    var previewBlobs = [];
    var previewController = null;

    function root() {
        return document.getElementById("evidence-library");
    }

    function caseContext() {
        var client = window.workspaceClient;
        return client && client.caseContext ? client.caseContext : null;
    }

    function captureScope() {
        var client = window.workspaceClient;
        var context = caseContext();
        if (!client || !context || client._privacyActive === false) return null;
        return {
            client: client,
            epoch: client._privacyEpoch,
            principal: client.activePrincipalId,
            caseKey: JSON.stringify([context.tenant_id, context.case_id, context.resource_id])
        };
    }

    function currentScope(scope) {
        var current = captureScope();
        return sameIdentity(scope, current) && scope.epoch === current.epoch;
    }

    function sameIdentity(scope, current) {
        return Boolean(scope && current && scope.client === current.client
            && scope.principal === current.principal && scope.caseKey === current.caseKey);
    }

    function clearPrivateState() {
        generation += 1;
        items = [];
        itemsScope = null;
        selectedId = "";
        readAt = "";
        var host = root();
        if (host) {
            host.dataset.selectedId = "";
            delete host.dataset.catalogRead;
        }
        var list = document.getElementById("evidence-library-list");
        if (list) list.textContent = "";
        clearPreview();
        paintDetail(null);
        setState("locked", "Private evidence was cleared. Open an authorized case to read its catalog again.");
    }

    function revokePreviewBlobs() {
        previewBlobs.splice(0).forEach(function (url) {
            try { URL.revokeObjectURL(url); } catch (error) { /* already revoked */ }
        });
    }

    function clearPreview() {
        previewGeneration += 1;
        if (previewController) {
            previewController.abort();
            previewController = null;
        }
        revokePreviewBlobs();
        var host = document.getElementById("evidence-preview");
        if (!host) return;
        host.dataset.kind = "";
        host.dataset.supported = "";
        host.dataset.scope = "";
        host.dataset.evidenceId = "";
        host.dataset.version = "";
        text("evidence-preview-status", "");
        text("evidence-preview-zoom-value", "100%");
        host.dataset.zoom = "100";
        var anchors = document.getElementById("evidence-preview-anchors");
        var stage = document.getElementById("evidence-preview-stage");
        var alternative = document.getElementById("evidence-preview-alternative");
        if (anchors) anchors.textContent = "";
        if (stage) {
            stage.textContent = "";
            stage.style.fontSize = "16px";
            stage.style.transform = "scale(1)";
        }
        if (alternative) {
            alternative.hidden = true;
            alternative.textContent = "";
        }
    }

    function ensurePreview() {
        var detail = document.getElementById("evidence-library-detail");
        if (!detail || document.getElementById("evidence-preview")) return;
        var section = document.createElement("section");
        section.id = "evidence-preview";
        section.dataset.kind = "";
        section.dataset.zoom = "100";
        section.dataset.supported = "";
        section.style.overflow = "auto";
        section.style.maxWidth = "100%";
        var heading = document.createElement("h4");
        heading.textContent = "Preview";
        var status = document.createElement("p");
        status.id = "evidence-preview-status";
        var controls = document.createElement("div");
        controls.id = "evidence-preview-zoom";
        controls.style.display = "flex";
        controls.style.flexWrap = "wrap";
        controls.style.gap = "8px";
        function zoomButton(id, label, delta) {
            var button = document.createElement("button");
            button.type = "button";
            button.className = "secondary";
            button.id = id;
            button.textContent = label;
            button.addEventListener("click", function () { setZoom(delta); });
            return button;
        }
        controls.appendChild(zoomButton("evidence-preview-zoom-out", "Zoom out", -25));
        controls.appendChild(zoomButton("evidence-preview-zoom-in", "Zoom in", 25));
        var reset = document.createElement("button");
        reset.type = "button";
        reset.className = "secondary";
        reset.id = "evidence-preview-zoom-reset";
        reset.textContent = "Reset zoom";
        reset.addEventListener("click", function () { applyZoom(100); });
        controls.appendChild(reset);
        var value = document.createElement("span");
        value.id = "evidence-preview-zoom-value";
        value.textContent = "100%";
        controls.appendChild(value);
        var versionLabel = document.createElement("label");
        versionLabel.htmlFor = "evidence-preview-version";
        versionLabel.textContent = "Artifact version";
        var version = document.createElement("select");
        version.id = "evidence-preview-version";
        version.addEventListener("change", function () {
            var current = items.filter(function (item) { return item.evidence_id === selectedId; })[0];
            if (current) loadPreview(current);
        });
        var anchors = document.createElement("nav");
        anchors.id = "evidence-preview-anchors";
        anchors.setAttribute("aria-label", "Preview pages and spans");
        var viewport = document.createElement("div");
        viewport.id = "evidence-preview-viewport";
        viewport.style.overflow = "auto";
        viewport.style.maxWidth = "100%";
        viewport.style.maxHeight = "320px";
        var stage = document.createElement("div");
        stage.id = "evidence-preview-stage";
        stage.style.transformOrigin = "top left";
        stage.style.fontSize = "16px";
        viewport.appendChild(stage);
        var alternative = document.createElement("p");
        alternative.id = "evidence-preview-alternative";
        alternative.hidden = true;
        section.appendChild(heading);
        section.appendChild(status);
        section.appendChild(controls);
        section.appendChild(versionLabel);
        section.appendChild(version);
        section.appendChild(anchors);
        section.appendChild(viewport);
        section.appendChild(alternative);
        detail.appendChild(section);
    }

    function applyZoom(next) {
        var zoom = Math.max(50, Math.min(200, next));
        var host = document.getElementById("evidence-preview");
        var stage = document.getElementById("evidence-preview-stage");
        if (host) host.dataset.zoom = String(zoom);
        if (stage) {
            stage.style.fontSize = (16 * zoom / 100) + "px";
            stage.style.transform = "scale(" + (zoom / 100) + ")";
        }
        text("evidence-preview-zoom-value", zoom + "%");
    }

    function setZoom(delta) {
        var host = document.getElementById("evidence-preview");
        var current = host ? Number(host.dataset.zoom || "100") : 100;
        applyZoom((Number.isFinite(current) ? current : 100) + delta);
    }

    function fillVersions(item) {
        var select = document.getElementById("evidence-preview-version");
        if (!select) return "";
        var versions = (item && item.artifact_versions) || [];
        var wanted = select.value;
        select.textContent = "";
        versions.forEach(function (version) {
            var option = document.createElement("option");
            option.value = String(version.version);
            option.textContent = "Version " + version.version + (version.kind ? " (" + version.kind + ")" : "");
            select.appendChild(option);
        });
        if (wanted && Array.prototype.some.call(select.options, function (option) { return option.value === wanted; })) {
            select.value = wanted;
        } else if (versions.length) {
            select.value = String(versions[versions.length - 1].version);
        }
        return select.value;
    }

    function renderPreview(body, scope, token) {
        if (token !== previewGeneration || !currentScope(scope)) return;
        if (!body || body.case_id !== caseContext().case_id || body.tenant_id !== caseContext().tenant_id) return;
        if (body.evidence_id !== selectedId) return;
        ensurePreview();
        var host = document.getElementById("evidence-preview");
        var stage = document.getElementById("evidence-preview-stage");
        var anchors = document.getElementById("evidence-preview-anchors");
        var alternative = document.getElementById("evidence-preview-alternative");
        if (!host || !stage || !anchors || !alternative) return;
        revokePreviewBlobs();
        stage.textContent = "";
        anchors.textContent = "";
        alternative.hidden = true;
        alternative.textContent = "";
        host.dataset.kind = body.preview_kind || "";
        host.dataset.supported = body.supported ? "true" : "false";
        host.dataset.scope = body.cache_scope || "";
        host.dataset.evidenceId = body.evidence_id || "";
        host.dataset.version = String(body.version || "");
        host.dataset.modelInvoked = "false";
        if (!body.supported) {
            var note = (body.alternative && body.alternative.message) || "This format cannot be previewed safely inside the workspace.";
            var safeText = (body.alternative && body.alternative.safe_text) || "";
            alternative.hidden = false;
            alternative.textContent = note + (safeText ? "\nReadable excerpt:\n" + safeText : "\nNo readable text is available.");
            text("evidence-preview-status", "Safe alternative. The original file was not executed.");
            return;
        }
        (body.pages || []).forEach(function (page) {
            var pageAnchor = document.createElement("a");
            pageAnchor.href = "#evidence-preview-" + page.anchor;
            pageAnchor.textContent = "Page " + page.page;
            pageAnchor.addEventListener("click", function (event) {
                event.preventDefault();
                var target = document.getElementById("evidence-preview-" + page.anchor);
                if (target) target.focus();
            });
            anchors.appendChild(pageAnchor);
            anchors.appendChild(document.createTextNode(" "));
            var block = document.createElement("section");
            block.id = "evidence-preview-" + page.anchor;
            block.tabIndex = -1;
            var pageLabel = document.createElement("h5");
            pageLabel.textContent = "Page " + page.page;
            block.appendChild(pageLabel);
            (page.spans || []).forEach(function (span) {
                var link = document.createElement("a");
                link.href = "#evidence-preview-" + span.anchor;
                link.textContent = "Span " + span.span;
                link.addEventListener("click", function (event) {
                    event.preventDefault();
                    var target = document.getElementById("evidence-preview-" + span.anchor);
                    if (target) target.focus();
                });
                anchors.appendChild(link);
                anchors.appendChild(document.createTextNode(" "));
                var row = document.createElement("p");
                row.id = "evidence-preview-" + span.anchor;
                row.tabIndex = 0;
                row.textContent = span.text || "";
                block.appendChild(row);
            });
            stage.appendChild(block);
        });
        if (body.preview_kind === "image" && body.image && body.image.content_base64) {
            var media = body.image.media_type;
            if (media !== "image/png" && media !== "image/jpeg" && media !== "image/webp") return;
            var binary = atob(body.image.content_base64);
            var bytes = new Uint8Array(binary.length);
            for (var index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
            var blob = new Blob([bytes], {type: media});
            var url = URL.createObjectURL(blob);
            previewBlobs.push(url);
            var image = document.createElement("img");
            image.id = "evidence-preview-image";
            image.alt = body.accessible_text || "Evidence image preview";
            image.src = url;
            image.style.maxWidth = "100%";
            image.style.height = "auto";
            stage.appendChild(image);
        }
        text("evidence-preview-status", body.preview_kind === "image"
            ? "Image preview. Zoom changes the display size. The image is not sent to a model."
            : "Text preview. Choose a page or span. Zoom changes the display size.");
        applyZoom(Number(host.dataset.zoom || "100"));
    }

    function loadPreview(item) {
        ensurePreview();
        var scope = captureScope();
        var context = caseContext();
        if (!item || !scope || !context) {
            clearPreview();
            return;
        }
        var token = ++previewGeneration;
        if (previewController) previewController.abort();
        previewController = new AbortController();
        var signal = previewController.signal;
        var version = fillVersions(item);
        var params = new URLSearchParams({
            tenant_id: context.tenant_id,
            case_id: context.case_id,
            resource_id: context.resource_id,
            evidence_id: item.evidence_id
        });
        if (version) params.set("version", version);
        text("evidence-preview-status", "Opening the encrypted preview…");
        fetch("/api/cases/evidence/preview?" + params.toString(), {
            credentials: "same-origin",
            headers: {"Accept": "application/json"},
            signal: signal
        }).then(function (response) {
            return response.json().then(function (body) { return {ok: response.ok, status: response.status, body: body}; });
        }).then(function (result) {
            if (token !== previewGeneration || !currentScope(scope)) return;
            if (!result.ok || !result.body || result.body.error) {
                ensurePreview();
                text("evidence-preview-status", result.status === 401 || result.status === 403
                    ? "This preview is not available for the current case."
                    : "The preview could not be opened. The encrypted artifact is unchanged.");
                var stage = document.getElementById("evidence-preview-stage");
                if (stage) stage.textContent = "";
                revokePreviewBlobs();
                return;
            }
            renderPreview(result.body, scope, token);
        }).catch(function (error) {
            if (error && error.name === "AbortError") return;
            if (token !== previewGeneration || !currentScope(scope)) return;
            text("evidence-preview-status", "The preview could not be opened. The encrypted artifact is unchanged.");
        });
    }

    function currentRead(token, scope, rescopeCount) {
        if (token !== generation) return false;
        if (currentScope(scope)) return true;
        var current = captureScope();
        var requestedSelection = selectedId;
        clearPrivateState();
        // A same-case SDK rebind also retires pending reads. Obtain a new
        // authorized catalog once; never reuse the response from its old epoch.
        if (rescopeCount < 1 && sameIdentity(scope, current)) {
            selectedId = requestedSelection;
            load(rescopeCount + 1);
        }
        return false;
    }

    function text(id, value) {
        var node = document.getElementById(id);
        if (node) node.textContent = value;
    }

    function show(id, visible) {
        var node = document.getElementById(id);
        if (node) node.hidden = !visible;
    }

    function layout() {
        var host = root();
        if (!host) return;
        var mobile = window.matchMedia("(max-width: 767px)").matches;
        host.dataset.layout = mobile ? "list-detail" : "master-detail";
        if (!mobile) host.dataset.pane = "both";
        else if (host.dataset.pane !== "detail") host.dataset.pane = "list";
    }

    function recorded(value) {
        return typeof value === "string" && value.trim() ? value.trim() : "Not recorded";
    }

    function notesFor(item) {
        var notes = item.notes || item.attributed_notes || [];
        if (!Array.isArray(notes)) return [];
        return notes.filter(function (note) { return note && typeof note === "object"; });
    }

    function linksFor(item) {
        var links = [];
        if (item.complaint_link_id) links.push(String(item.complaint_link_id));
        if (Array.isArray(item.complaint_links)) {
            item.complaint_links.forEach(function (link) {
                var value = typeof link === "string" ? link : (link && (link.complaint_link_id || link.id));
                if (value) links.push(String(value));
            });
        }
        return links;
    }

    function haystack(item) {
        var notes = notesFor(item).map(function (note) {
            return [note.note, note.text, note.author, note.actor_principal_id].join(" ");
        }).join(" ");
        return [
            item.source_filename, item.original_filename, item.evidence_id,
            item.ingestion_status, item.complaint_link_id, item.failure_code,
            item.actor_principal_id, notes
        ].join(" ").toLowerCase();
    }

    function visibleItems() {
        var query = (document.getElementById("evidence-library-search").value || "").trim().toLowerCase();
        var status = document.getElementById("evidence-library-status-filter").value;
        return items.filter(function (item) {
            if (status && item.ingestion_status !== status) return false;
            if (query && haystack(item).indexOf(query) === -1) return false;
            return true;
        });
    }

    function paintDetail(item) {
        var detail = document.getElementById("evidence-library-detail");
        if (!item) {
            if (detail) detail.dataset.evidenceId = "";
            text("evidence-detail-title", "No artifact selected");
            text("evidence-detail-status", "Select an artifact from the library.");
            text("evidence-detail-source", "");
            text("evidence-detail-dates", "");
            text("evidence-detail-notes", "");
            text("evidence-detail-classification", "");
            text("evidence-detail-links", "");
            clearPreview();
            return;
        }
        var version = (item.artifact_versions || [])[item.artifact_versions.length - 1] || {};
        var notes = notesFor(item);
        text("evidence-detail-title", item.original_filename || item.source_filename || item.evidence_id);
        text("evidence-detail-status", [
            "Status: " + (item.ingestion_status || "unknown"),
            item.prior_ingestion_status ? "Previous status: " + item.prior_ingestion_status : "",
            item.failure_code ? "Failure: " + item.failure_code : "",
            "Version: " + String(item.current_version || version.version || ""),
            "Integrity verified: " + (item.integrity_verified === true ? "yes" : "no"),
            "Recorded by: " + (item.actor_principal_id || "Not recorded")
        ].filter(Boolean).join("\n"));
        text("evidence-detail-source", [
            "Source file: " + (item.source_filename || "Not recorded"),
            "Original file: " + (item.original_filename || "Not recorded"),
            "Media type: " + (item.media_type || "Not recorded")
        ].join("\n"));
        text("evidence-detail-dates", [
            "Source date: " + recorded(item.source_date || item.received_at),
            "Version date: " + recorded(version.recorded_at || item.version_date),
            "Catalog read: " + (readAt || "Not recorded")
        ].join("\n"));
        text("evidence-detail-notes", notes.length ? notes.map(function (note) {
            var author = note.actor_principal_id || note.author || "unattributed";
            return author + ": " + (note.note || note.text || "");
        }).join("\n") : "No attributed note is stored for this artifact.");
        text("evidence-detail-classification", QUALITIES.map(function (name) {
            var value = item[name] || (item.legal && item.legal[name]) || "not_recorded";
            return name + ": " + value;
        }).join("\n") + "\nClassification is not verified support or governing law.");
        var links = linksFor(item);
        text("evidence-detail-links", links.length ? links.join("\n") : "No current complaint link.");
        if (detail) detail.dataset.evidenceId = item.evidence_id || "";
        loadPreview(item);
    }

    function render() {
        var host = root();
        var list = document.getElementById("evidence-library-list");
        if (!host || !list || host.dataset.state !== "ready") return;
        if (!currentScope(itemsScope)) {
            var current = captureScope();
            var previous = itemsScope;
            var requestedSelection = selectedId;
            clearPrivateState();
            if (sameIdentity(previous, current)) {
                selectedId = requestedSelection;
                load(1);
            }
            return;
        }
        layout();
        var shown = visibleItems();
        list.textContent = "";
        if (!shown.length) {
            var empty = document.createElement("p");
            empty.id = "evidence-library-filter-empty";
            empty.textContent = items.length
                ? "No artifacts match this search or status. Clear filters to see the catalog again."
                : "The catalog has no artifacts.";
            list.appendChild(empty);
        }
        shown.forEach(function (item) {
            var button = document.createElement("button");
            button.type = "button";
            button.className = "evidence-library-item";
            button.setAttribute("role", "option");
            button.setAttribute("data-evidence-id", item.evidence_id || "");
            button.setAttribute("aria-pressed", item.evidence_id === selectedId ? "true" : "false");
            var title = document.createElement("strong");
            title.textContent = item.original_filename || item.source_filename || item.evidence_id;
            var meta = document.createElement("small");
            meta.textContent = (item.ingestion_status || "unknown") + " · " + (item.source_filename || "source not recorded");
            button.appendChild(title);
            button.appendChild(meta);
            button.addEventListener("click", function () {
                selectedId = item.evidence_id || "";
                host.dataset.selectedId = selectedId;
                if (host.dataset.layout === "list-detail") host.dataset.pane = "detail";
                render();
            });
            list.appendChild(button);
        });
        var selected = items.filter(function (item) { return item.evidence_id === selectedId; })[0] || null;
        if (!selected && shown[0] && !selectedId) {
            selected = shown[0];
            selectedId = selected.evidence_id || "";
            host.dataset.selectedId = selectedId;
            var first = list.querySelector("[data-evidence-id]");
            if (first) first.setAttribute("aria-pressed", "true");
        }
        host.dataset.selectedId = selected ? selected.evidence_id : "";
        paintDetail(selected);
        text("evidence-library-summary", items.length
            ? (shown.length + " of " + items.length + " artifacts shown.")
            : "No artifacts are in this case catalog.");
    }

    function setState(state, detail) {
        var host = root();
        if (!host) return;
        host.dataset.state = state;
        show("evidence-library-empty", state === "empty");
        show("evidence-library-error", state === "error");
        show("evidence-library-locked", state === "locked");
        show("evidence-library-body", state === "ready");
        if (state === "error") text("evidence-library-error-detail", detail || "The catalog request failed. The previous selection is kept.");
        if (state === "locked") text("evidence-library-locked-detail", detail || "Unlock the case key or open an authorized case, then refresh. Locked evidence is not shown.");
        if (state !== "ready" && detail) text("evidence-library-summary", detail);
    }

    async function load(rescopeCount) {
        var host = root();
        if (!host) return;
        rescopeCount = rescopeCount === 1 ? 1 : 0;
        var scope = captureScope();
        if (itemsScope && !currentScope(itemsScope)) {
            var previous = itemsScope;
            var requestedSelection = selectedId;
            clearPrivateState();
            if (sameIdentity(previous, scope)) selectedId = requestedSelection;
        }
        var token = ++generation;
        var context = caseContext();
        if (!scope || !context) {
            clearPrivateState();
            setState("locked", "Select an authorized case before opening its evidence library.");
            return;
        }
        itemsScope = scope;
        var params = new URLSearchParams({
            tenant_id: context.tenant_id,
            case_id: context.case_id,
            resource_id: context.resource_id
        });
        var response;
        try {
            response = await fetch("/api/cases/evidence?" + params.toString(), {
                credentials: "same-origin",
                headers: {"Accept": "application/json"}
            });
        } catch (error) {
            if (!currentRead(token, scope, rescopeCount)) return;
            setState("error", "The catalog request did not reach the server. Try again.");
            return;
        }
        if (!currentRead(token, scope, rescopeCount)) return;
        var body = {};
        try { body = await response.json(); } catch (error) { body = {}; }
        if (!currentRead(token, scope, rescopeCount)) return;
        if (response.status === 401 || response.status === 403 || body.error === "key_unavailable" || body.error === "not_owner" || body.error === "unauthenticated") {
            items = [];
            selectedId = host.dataset.selectedId || selectedId;
            var list = document.getElementById("evidence-library-list");
            if (list) list.textContent = "";
            setState("locked", response.status === 403
                ? "This account cannot open the evidence catalog for the selected case."
                : "The case key or session cannot open the evidence catalog. Refresh after access returns.");
            clearPreview();
            paintDetail(null);
            return;
        }
        if (!response.ok || body.error) {
            setState("error", "The catalog returned " + (body.error || response.status) + ". Try the catalog again.");
            return;
        }
        items = Array.isArray(body.items) ? body.items : [];
        readAt = new Date().toISOString();
        host.dataset.catalogRead = readAt;
        if (selectedId && !items.some(function (item) { return item.evidence_id === selectedId; })) selectedId = "";
        if (!items.length) {
            selectedId = "";
            host.dataset.selectedId = "";
            setState("empty");
            text("evidence-library-summary", "No artifacts are in this case catalog.");
            paintDetail(null);
            return;
        }
        setState("ready");
        render();
    }

    function bind() {
        var host = root();
        if (!host || host.dataset.bound === "true") return;
        host.dataset.bound = "true";
        ensurePreview();
        layout();
        document.getElementById("evidence-library-search").addEventListener("input", render);
        document.getElementById("evidence-library-status-filter").addEventListener("change", render);
        document.getElementById("evidence-library-refresh").addEventListener("click", function () { load(); });
        document.getElementById("evidence-library-retry").addEventListener("click", function () { load(); });
        document.getElementById("evidence-library-unlock").addEventListener("click", function () { load(); });
        document.getElementById("evidence-library-clear").addEventListener("click", function () {
            document.getElementById("evidence-library-search").value = "";
            document.getElementById("evidence-library-status-filter").value = "";
            render();
        });
        document.getElementById("evidence-library-add").addEventListener("click", function () {
            var input = document.getElementById("evidence-attachment");
            if (input) input.focus();
        });
        document.getElementById("evidence-library-show-list").addEventListener("click", function () {
            layout();
            host.dataset.pane = "list";
        });
        document.getElementById("evidence-library-show-detail").addEventListener("click", function () {
            layout();
            if (host.dataset.layout === "list-detail") host.dataset.pane = "detail";
        });
        window.addEventListener("resize", layout);
        var tab = document.querySelector("[data-tab-target='evidence']");
        if (tab) tab.addEventListener("click", function () { load(); });
    }

    window.complaintEvidenceLibrary = {
        refresh: load,
        clearPrivateState: clearPrivateState,
        selectedId: function () { return selectedId; }
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
    else bind();
}());

