/* Projects the canonical workspace session into a mediator conversation.
   It does not start an interview, store the complaint, or adopt model text. */
(function () {
    var MAX_RETRIES = 3;
    var BLOCKED = { "missing-key": true, denied: true, unavailable: true, locked: true, revoked: true };
    var root = null;
    var generation = 0;
    var retryCount = 0;
    var lifecycle = "idle";
    var controller = null;
    var lastPayload = null;

    function $(id) { return document.getElementById(id); }

    function text(value) {
        if (value === undefined || value === null) return "";
        return String(value).replace(/\s+/g, " ").trim();
    }

    function escapeHtml(value) {
        return text(value).replace(/[&<>"']/g, function (ch) {
            return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch];
        });
    }

    function shellState() {
        var shell = $("complaint-case-shell");
        var entry = $("complaint-entry");
        return {
            shell: shell ? (shell.dataset.state || "") : "",
            entry: entry ? (entry.dataset.entry || "") : "",
            caseLabel: text(($("complaint-case-shell-case") || {}).textContent),
            caseId: shell ? (($("complaint-case-shell-case") || {}).dataset || {}).caseId || "" : ""
        };
    }

    function blocked() {
        var state = shellState();
        return BLOCKED[state.shell] || BLOCKED[state.entry] || state.entry === "missing-key";
    }

    function sessionOf(payload) {
        if (!payload || typeof payload !== "object") return {};
        if (payload.session && typeof payload.session === "object") return payload.session;
        return {};
    }

    function documentsOf(session, payload) {
        var evidence = session.evidence && typeof session.evidence === "object" ? session.evidence : {};
        var review = payload && payload.review && typeof payload.review === "object" ? payload.review : {};
        var documents = [].concat(Array.isArray(evidence.documents) ? evidence.documents : [], Array.isArray(review.documents) ? review.documents : []);
        var testimony = [].concat(Array.isArray(evidence.testimony) ? evidence.testimony : [], Array.isArray(review.testimony) ? review.testimony : []);
        var seen = {};
        return documents.concat(testimony).filter(function (item) {
            if (!item || typeof item !== "object") return false;
            var key = text(item.id) || text(item.title);
            if (!key || seen[key]) return false;
            seen[key] = true;
            return true;
        });
    }

    function selectedEvidenceTitle(items) {
        var list = $("evidence-list");
        var selected = list ? text(list.dataset.selectedId) : "";
        var match = null;
        items.forEach(function (item) {
            if (!item || typeof item !== "object") return;
            if (selected && text(item.id) === selected) match = item;
        });
        var chosen = match || items[0];
        if (!chosen) return "";
        return text(chosen.title || chosen.label || chosen.name);
    }

    function suggestionsOf(session) {
        var found = [];
        var interview = session.shared_interview && typeof session.shared_interview === "object" ? session.shared_interview : {};
        var pending = interview.pending_inquiry && typeof interview.pending_inquiry === "object" ? interview.pending_inquiry : {};
        var proposal = pending.model_proposal && typeof pending.model_proposal === "object" ? pending.model_proposal : null;
        if (proposal && proposal.record_type === "model_suggestion" && text(proposal.wording)) {
            found.push(text(proposal.wording));
        }
        var graph = interview.knowledge_graph && typeof interview.knowledge_graph === "object" ? interview.knowledge_graph : {};
        var rows = [].concat(Array.isArray(graph.entities) ? graph.entities : [], Array.isArray(graph.nodes) ? graph.nodes : []);
        rows.forEach(function (row) {
            if (!row || row.record_type !== "model_suggestion") return;
            var wording = text(row.name || row.text || (row.attributes && row.attributes.wording));
            if (wording) found.push(wording);
        });
        return found;
    }

    function messagesFrom(payload) {
        var session = sessionOf(payload);
        var interview = session.shared_interview && typeof session.shared_interview === "object" ? session.shared_interview : {};
        var pending = interview.pending_inquiry && typeof interview.pending_inquiry === "object" ? interview.pending_inquiry : null;
        var complaint = session.original_complaint && typeof session.original_complaint === "object" ? session.original_complaint : {};
        var narrative = text(complaint.text);
        var messages = [];
        if (narrative) {
            messages.push({
                type: "user-statement",
                kind: "Your statement",
                body: narrative,
                why: "You entered this for the current case. It is not a legal conclusion."
            });
        }
        var history = Array.isArray(session.intake_history) ? session.intake_history : [];
        history.forEach(function (item) {
            if (!item || typeof item !== "object") return;
            var answer = text(item.answer);
            if (!answer || answer === narrative) return;
            messages.push({
                type: "user-statement",
                kind: "Your statement",
                body: answer,
                why: "This is a recorded answer on the case. It stays separate from evidence and from model text."
            });
        });
        if (pending && text(pending.question)) {
            var explanation = pending.inquiry_explanation && typeof pending.inquiry_explanation === "object" ? pending.inquiry_explanation : {};
            messages.push({
                type: "ai-question",
                kind: "Mediator question",
                body: text(pending.question),
                why: text(explanation.why_asked) || "This is the current question from the shared mediator."
            });
        }
        var suggestions = suggestionsOf(session);
        if (!suggestions.length) {
            messages.push({
                type: "model-suggestion",
                kind: "Model suggestion",
                body: "No model suggestion is available for this case.",
                why: "A missing suggestion is not a fact, evidence, or legal requirement.",
                availability: "unavailable"
            });
        } else {
            suggestions.forEach(function (wording) {
                messages.push({
                    type: "model-suggestion",
                    kind: "Model suggestion",
                    body: wording,
                    why: "This is a model suggestion. It is not adopted as a fact, as evidence, or as law.",
                    availability: "available"
                });
            });
        }
        var outcome = payload.finite_interview_outcome && typeof payload.finite_interview_outcome === "object" ? payload.finite_interview_outcome : {};
        var stop = text(outcome.stop);
        var waiting = pending && text(pending.question);
        messages.push({
            type: "system-outcome",
            kind: "System outcome",
            body: waiting
                ? "The mediator is waiting for your answer. Answer the current question to continue."
                : (stop && stop !== "unresolved"
                    ? "The interview recorded this outcome: " + stop + ". That outcome is not legal sufficiency."
                    : "No system outcome is recorded yet."),
            why: "System text reports the interview state. It does not adopt an answer."
        });
        return messages;
    }

    function paintControls() {
        if (!root) return;
        root.dataset.lifecycle = lifecycle;
        root.dataset.retryCount = String(retryCount);
        root.setAttribute("aria-busy", lifecycle === "pending" ? "true" : "false");
        var refresh = $("mediator-conversation-refresh");
        var cancel = $("mediator-conversation-cancel");
        var retry = $("mediator-conversation-retry");
        if (refresh) refresh.disabled = lifecycle === "pending" || lifecycle === "retry-exhausted" || blocked();
        if (cancel) cancel.disabled = lifecycle !== "pending";
        if (retry) retry.disabled = !((lifecycle === "error" || lifecycle === "cancelled") && retryCount < MAX_RETRIES);
        var status = $("mediator-conversation-status");
        if (!status) return;
        var copy = {
            idle: "The conversation has not been loaded.",
            settled: "The conversation matches the latest confirmed case session.",
            pending: "Reading the case session. You can cancel this refresh.",
            cancelled: "Refresh cancelled. The conversation still shows the last confirmed case.",
            error: "The case session could not be read. Retry is available until the limit.",
            "retry-exhausted": "The retry limit was reached. The conversation was not read again.",
            blocked: "This case cannot be shown. No conversation text is available."
        };
        status.textContent = copy[lifecycle] || copy.idle;
    }

    function render(payload) {
        root = $("mediator-conversation");
        if (!root) return;
        var log = $("mediator-conversation-log");
        var context = $("mediator-conversation-context");
        var actions = $("mediator-conversation-actions");
        if (!log || !context || !actions) return;
        if (blocked()) {
            log.replaceChildren();
            context.textContent = "Case access does not allow this conversation to be shown.";
            actions.replaceChildren();
            lifecycle = "blocked";
            paintControls();
            return;
        }
        var session = sessionOf(payload);
        var items = documentsOf(session, payload);
        var evidenceTitle = selectedEvidenceTitle(items);
        var label = shellState().caseLabel;
        if (!label || label === "No case selected") label = "the open case";
        context.textContent = "Case: " + label + ". Evidence: " + (evidenceTitle || "none attached yet") + ".";
        var messages = messagesFrom(payload || {});
        log.innerHTML = messages.map(function (message, index) {
            var id = "mediator-conversation-kind-" + index;
            return '<li class="mediator-conversation__message" data-message-type="' + message.type + '" data-availability="' + escapeHtml(message.availability || "shown") + '" role="article">'
                + '<p class="mediator-conversation__kind" id="' + id + '">' + escapeHtml(message.kind) + "</p>"
                + '<p class="mediator-conversation__body">' + escapeHtml(message.body) + "</p>"
                + '<p class="mediator-conversation__why">Why this is here: ' + escapeHtml(message.why) + "</p>"
                + "</li>";
        }).join("");
        var buttons = [];
        var pending = session.shared_interview && session.shared_interview.pending_inquiry;
        if (pending && text(pending.question)) {
            buttons.push('<button type="button" data-conversation-action="answer">Answer the current question</button>');
        } else if (!text((session.original_complaint || {}).text)) {
            buttons.push('<button type="button" data-conversation-action="narrative">Enter what happened</button>');
        }
        if (items.length) buttons.push('<button type="button" data-conversation-action="evidence">Review the case evidence</button>');
        actions.innerHTML = buttons.join("");
        if (lifecycle !== "pending" && lifecycle !== "error" && lifecycle !== "cancelled" && lifecycle !== "retry-exhausted") {
            lifecycle = messages.length ? "settled" : "idle";
        }
        paintControls();
    }

    function focusAction(action) {
        if (action === "answer") {
            var answer = $("adaptive-answer");
            if (answer) answer.focus();
            return;
        }
        if (action === "narrative") {
            var narrative = $("adaptive-narrative");
            if (narrative) narrative.focus();
            return;
        }
        if (action === "evidence") {
            var tab = document.querySelector('.tab-button[data-tab-target="evidence"]');
            if (tab) tab.click();
            var list = $("evidence-list");
            var button = list && list.querySelector("button");
            if (button) button.focus();
            else if (list) list.focus();
        }
    }

    function clear() {
        generation += 1;
        if (controller) controller.abort();
        controller = null;
        lastPayload = null;
        retryCount = 0;
        lifecycle = "idle";
        root = $("mediator-conversation");
        if (!root) return;
        var log = $("mediator-conversation-log");
        var context = $("mediator-conversation-context");
        var actions = $("mediator-conversation-actions");
        if (log) log.replaceChildren();
        if (context) context.textContent = "";
        if (actions) actions.replaceChildren();
        paintControls();
        var status = $("mediator-conversation-status");
        if (status) status.textContent = "Conversation text was cleared because this case is no longer open.";
    }

    function project(payload) {
        if (generation < 0) return;
        if (blocked()) {
            clear();
            lifecycle = "blocked";
            paintControls();
            return;
        }
        lastPayload = payload;
        if (lifecycle === "pending") return;
        render(payload);
    }

    async function refresh() {
        root = $("mediator-conversation");
        if (!root || lifecycle === "pending" || lifecycle === "retry-exhausted" || blocked()) return;
        var client = window.workspaceClient;
        var binding = window.complaintCaseShell && window.complaintCaseShell.binding ? window.complaintCaseShell.binding() : null;
        if (!client || typeof client._request !== "function" || !binding || !binding.case_id) {
            lifecycle = "error";
            paintControls();
            return;
        }
        var token = ++generation;
        var caseId = binding.case_id;
        lifecycle = "pending";
        paintControls();
        controller = new AbortController();
        var url = "/api/complaint-workspace/session?case_id=" + encodeURIComponent(caseId);
        try {
            var payload = await client._request(url, { method: "GET", signal: controller.signal });
            if (token !== generation) return;
            var current = window.complaintCaseShell.binding();
            if (!current || current.case_id !== caseId || blocked()) {
                clear();
                return;
            }
            lastPayload = payload;
            retryCount = 0;
            lifecycle = "settled";
            render(payload);
        } catch (error) {
            if (token !== generation) return;
            lifecycle = error && error.code === "cancelled" ? "cancelled" : "error";
            if (lastPayload) render(lastPayload);
            else paintControls();
            if (lifecycle === "cancelled" || lifecycle === "error") paintControls();
        } finally {
            if (token === generation) controller = null;
        }
    }

    function cancel() {
        if (lifecycle !== "pending") return;
        generation += 1;
        if (controller) controller.abort();
        controller = null;
        lifecycle = "cancelled";
        if (lastPayload && !blocked()) render(lastPayload);
        paintControls();
    }

    function retry() {
        if (lifecycle !== "error" && lifecycle !== "cancelled") return;
        if (retryCount >= MAX_RETRIES) {
            lifecycle = "retry-exhausted";
            paintControls();
            return;
        }
        retryCount += 1;
        lifecycle = "idle";
        refresh();
    }

    function bind() {
        root = $("mediator-conversation");
        if (!root || root.dataset.bound === "true") return;
        root.dataset.bound = "true";
        root.addEventListener("click", function (event) {
            var button = event.target.closest("button");
            if (!button || !root.contains(button)) return;
            if (button.id === "mediator-conversation-refresh") refresh();
            else if (button.id === "mediator-conversation-cancel") cancel();
            else if (button.id === "mediator-conversation-retry") retry();
            else if (button.dataset.conversationAction) focusAction(button.dataset.conversationAction);
        });
        if (window.MutationObserver) {
            var shell = $("complaint-case-shell");
            if (shell) {
                var observer = new MutationObserver(function () {
                    if (blocked()) clear();
                    else if (lastPayload && lifecycle !== "pending") render(lastPayload);
                });
                observer.observe(shell, { attributes: true, attributeFilter: ["data-state"] });
            }
            var caseNode = $("complaint-case-shell-case");
            if (caseNode) {
                var caseObserver = new MutationObserver(function () {
                    if (blocked()) clear();
                    else if (lastPayload && lifecycle !== "pending") render(lastPayload);
                });
                caseObserver.observe(caseNode, { childList: true, characterData: true, subtree: true });
            }
        }
        paintControls();
    }

    window.complaintConversation = {
        project: project,
        clear: clear,
        refresh: refresh,
        cancel: cancel,
        retry: retry
    };

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
    else bind();
})();
