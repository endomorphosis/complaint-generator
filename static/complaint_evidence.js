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
