(function () {
    "use strict";

    var csrf = "";
    var currentCursor = 0;
    var nextCursor = null;
    var pollTimer = 0;
    var pollGeneration = 0;
    var viewToken = 0;
    var chain = Promise.resolve();

    function enqueue(work) {
        var run = chain.then(work, work);
        chain = run.then(function () {}, function () {});
        return run;
    }
    var READ_PREFIX = "cimp-gui-44-read:";

    function $(id) { return document.getElementById(id); }

    function setStatus(text) { $("inbox-status").textContent = text || ""; }
    function setError(text) { $("inbox-error").textContent = text || ""; }

    function caseId() { return $("case-id").value.trim(); }
    function threadId() { return $("thread-id").value.trim(); }

    function membershipFields() {
        var fields = {};
        var grant = $("membership-grant-id").value.trim();
        var version = $("membership-version").value.trim();
        if (grant) fields.membership_grant_id = grant;
        if (version) fields.expected_membership_version = Number(version);
        return fields;
    }

    function pageLimit() {
        var value = Number($("page-limit").value);
        if (!Number.isInteger(value) || value < 1) return 10;
        return Math.min(value, 20);
    }

    function pollMs() {
        var value = Number($("poll-ms").value);
        if (!Number.isFinite(value) || value < 200) return 4000;
        return value;
    }

    function readCursor(id) {
        var raw = sessionStorage.getItem(READ_PREFIX + id);
        if (raw === null || !/^[0-9]+$/.test(raw)) return 0;
        return Number(raw);
    }

    function rememberRead(id, sequence) {
        sessionStorage.setItem(READ_PREFIX + id, String(sequence));
    }

    async function api(path, options) {
        var headers = { "accept": "application/json" };
        var method = (options && options.method) || "GET";
        if (method !== "GET") {
            headers["content-type"] = "application/json";
            headers["x-csrf-token"] = csrf;
        }
        var response = await fetch(path, {
            method: method,
            headers: headers,
            body: options && options.body ? JSON.stringify(options.body) : undefined,
            credentials: "same-origin",
            cache: "no-store"
        });
        var payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "request_failed");
        return payload;
    }

    function query(path, extra) {
        var params = new URLSearchParams();
        params.set("case_id", caseId());
        var fields = membershipFields();
        Object.keys(fields).forEach(function (key) { params.set(key, String(fields[key])); });
        Object.keys(extra || {}).forEach(function (key) {
            if (extra[key] !== undefined && extra[key] !== null) params.set(key, String(extra[key]));
        });
        return path + "?" + params.toString();
    }

    function showLimitations(payload) {
        var items = payload && payload.limitations;
        $("inbox-limitations").textContent = Array.isArray(items) ? items.join(" ") : "";
    }

    function renderMessages(messages, mode) {
        var list = $("message-list");
        if (mode !== "append") list.replaceChildren();
        var known = {};
        list.querySelectorAll("[data-message-id]").forEach(function (node) {
            known[node.getAttribute("data-message-id")] = true;
        });
        var cursor = readCursor(threadId());
        messages.forEach(function (message) {
            if (known[message.message_id]) return;
            var item = document.createElement("li");
            item.setAttribute("data-message-id", message.message_id);
            item.setAttribute("data-sequence", String(message.sequence));
            var unread = Number(message.sequence) > cursor;
            item.setAttribute("data-unread", unread ? "true" : "false");
            if (unread) item.className = "unread";
            var sender = document.createElement("span");
            sender.textContent = message.sender_principal_id + " #" + message.sequence + " ";
            var body = document.createElement("span");
            body.className = "message-text";
            body.textContent = message.text;
            item.appendChild(sender);
            item.appendChild(body);
            list.appendChild(item);
        });
        updateUnreadCount();
    }

    function updateUnreadCount() {
        var count = document.querySelectorAll("#message-list [data-unread='true']").length;
        $("unread-count").textContent = "Unread " + count;
    }

    function applyReadState() {
        var cursor = readCursor(threadId());
        document.querySelectorAll("#message-list [data-sequence]").forEach(function (item) {
            var unread = Number(item.getAttribute("data-sequence")) > cursor;
            item.setAttribute("data-unread", unread ? "true" : "false");
            item.className = unread ? "unread" : "";
        });
        updateUnreadCount();
    }

    function highestSequence() {
        var max = 0;
        document.querySelectorAll("#message-list [data-sequence]").forEach(function (item) {
            max = Math.max(max, Number(item.getAttribute("data-sequence")));
        });
        return max;
    }

    async function loadPage(cursor, mode) {
        var token = viewToken;
        var payload = await api(query("/api/cases/messages/threads/" + encodeURIComponent(threadId()) + "/messages", {
            cursor: cursor,
            limit: pageLimit()
        }));
        if (token !== viewToken) return null;
        showLimitations(payload);
        currentCursor = cursor;
        nextCursor = payload.next_cursor === undefined ? null : payload.next_cursor;
        $("page-meta").textContent = "cursor " + payload.cursor + " next " + (nextCursor === null ? "none" : nextCursor);
        $("next-page").disabled = nextCursor === null;
        renderMessages(payload.messages || [], mode);
        return payload;
    }

    async function poll() {
        if (!csrf || !threadId() || !caseId()) return;
        var generation = pollGeneration;
        try {
            if (nextCursor === null && highestSequence() > 0) await loadPage(highestSequence(), "append");
            else await loadPage(currentCursor, "replace");
            if (generation === pollGeneration) setStatus("Polled messages over HTTP");
            setError("");
        } catch (error) {
            if (generation === pollGeneration) setError(error.message || "poll_failed");
        }
    }

    function startPolling() {
        pollGeneration += 1;
        if (pollTimer) window.clearInterval(pollTimer);
        pollTimer = window.setInterval(function () { enqueue(poll); }, pollMs());
    }

    async function loadThreads() {
        var payload = await api(query("/api/cases/messages/threads"));
        showLimitations(payload);
        var list = $("thread-list");
        list.replaceChildren();
        (payload.threads || []).forEach(function (thread) {
            var item = document.createElement("li");
            var button = document.createElement("button");
            button.type = "button";
            button.textContent = thread.thread_id + " (" + thread.message_count + ")";
            button.addEventListener("click", function () {
                $("thread-id").value = thread.thread_id;
            });
            item.appendChild(button);
            list.appendChild(item);
        });
        setStatus("Loaded " + (payload.threads || []).length + " threads");
    }

    async function refreshCases() {
        var payload = await api("/api/cases");
        var select = $("case-select");
        select.replaceChildren();
        var blank = document.createElement("option");
        blank.value = "";
        blank.textContent = "Select a case";
        select.appendChild(blank);
        (payload.cases || []).forEach(function (item) {
            var option = document.createElement("option");
            option.value = item.case_id;
            option.textContent = item.label || item.case_id;
            select.appendChild(option);
        });
    }

    $("case-select").addEventListener("change", function () {
        if ($("case-select").value) $("case-id").value = $("case-select").value;
    });

    $("inbox-login").addEventListener("submit", async function (event) {
        event.preventDefault();
        setError("");
        try {
            var response = await fetch("/api/complaint-workspace/auth/login", {
                method: "POST",
                credentials: "same-origin",
                headers: { "content-type": "application/json", "accept": "application/json" },
                body: JSON.stringify({ credential: $("inbox-credential").value })
            });
            var payload = await response.json();
            if (!response.ok) throw new Error(payload.error || "login_failed");
            csrf = payload.csrf_token || "";
            $("inbox-credential").value = "";
            $("inbox-auth-status").textContent = "Signed in";
            await refreshCases();
            setStatus("Signed in");
        } catch (error) {
            csrf = "";
            $("inbox-auth-status").textContent = "Sign in required";
            setError(error.message || "login_failed");
        }
    });

    $("load-threads").addEventListener("click", function () {
        enqueue(loadThreads).catch(function (error) { setError(error.message || "request_failed"); });
    });

    $("create-thread").addEventListener("click", function () {
        enqueue(async function () {
            setError("");
            var payload = await api("/api/cases/messages/threads", {
                method: "POST",
                body: Object.assign({
                    case_id: caseId(),
                    idempotency_key: "thread-" + Date.now()
                }, membershipFields())
            });
            $("thread-id").value = payload.thread_id;
            await loadThreads();
            setStatus("Created thread");
        }).catch(function (error) { setError(error.message || "request_failed"); });
    });

    $("open-thread").addEventListener("click", function () {
        enqueue(async function () {
            setError("");
            pollGeneration += 1;
            viewToken += 1;
            currentCursor = 0;
            await loadPage(0, "replace");
            startPolling();
            setStatus("Opened thread");
        }).catch(function (error) {
            $("message-list").replaceChildren();
            setError(error.message || "request_failed");
        });
    });

    $("next-page").addEventListener("click", function () {
        enqueue(async function () {
            if (nextCursor === null) return;
            setError("");
            viewToken += 1;
            await loadPage(nextCursor, "replace");
            setStatus("Loaded next page");
        }).catch(function (error) { setError(error.message || "request_failed"); });
    });

    $("refresh-messages").addEventListener("click", function () { enqueue(poll); });

    $("mark-read").addEventListener("click", function () {
        if (!threadId()) return;
        rememberRead(threadId(), highestSequence());
        applyReadState();
        setStatus("Marked visible messages read");
    });

    $("send-message").addEventListener("submit", function (event) {
        event.preventDefault();
        var text = $("message-text").value;
        enqueue(async function () {
            setError("");
            await api("/api/cases/messages/threads/" + encodeURIComponent(threadId()) + "/messages", {
                method: "POST",
                body: Object.assign({
                    case_id: caseId(),
                    text: text,
                    idempotency_key: "send-" + Date.now()
                }, membershipFields())
            });
            $("message-text").value = "";
            if (nextCursor === null) await loadPage(highestSequence(), "append");
            else await loadPage(currentCursor, "replace");
            setStatus("Sent message");
        }).catch(function (error) { setError(error.message || "request_failed"); });
    });

    window.addEventListener("pagehide", function () {
        if (pollTimer) window.clearInterval(pollTimer);
    });
})();
