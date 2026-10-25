/* Law-derived dependency graph view.

   Legal rules render only from admitted-authority fields. Factual support,
   contradiction, and missing-evidence links render in a separate section.
   User narratives and model output are not copied into a legal rule.
   This file does not open a WebSocket or SSE stream.
*/
"use strict";

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function asList(value) {
  return Array.isArray(value) ? value : [];
}

function lawDerivedDependencyMarkup(payload) {
  var body = payload && typeof payload === "object" ? payload : {};
  var requirements = asList(body.requirements);
  var links = asList(body.factual_links);
  var rejected = asList(body.rejected_narratives);
  var rules = requirements.map(function (rule) {
    var exceptions = asList(rule.exceptions).map(function (item) {
      return "<li data-role=\"exception\">" + escapeHtml(item) + "</li>";
    }).join("");
    return [
      "<article data-role=\"legal-rule\" data-content-hash=\"" + escapeHtml(rule.content_hash) + "\" data-source=\"admitted_authority\">",
      "<h3 data-role=\"authority-identity\">" + escapeHtml(rule.authority_identity) + "</h3>",
      "<p data-role=\"requirement\">" + escapeHtml(rule.requirement) + "</p>",
      "<p data-role=\"burden\" data-burden-status=\"" + escapeHtml(rule.burden_status) + "\">" + escapeHtml(rule.burden) + "</p>",
      "<p data-role=\"applicability\">" + escapeHtml(rule.applicability) + "</p>",
      "<p data-role=\"jurisdiction\">" + escapeHtml(rule.jurisdiction) + "</p>",
      "<p data-role=\"effective-date\">" + escapeHtml(rule.effective_date) + "</p>",
      "<ul data-role=\"exceptions\">" + exceptions + "</ul>",
      "</article>",
    ].join("");
  }).join("");
  var factItems = links.map(function (link) {
    return [
      "<li data-role=\"factual-link\" data-link-kind=\"" + escapeHtml(link.link_kind) + "\" data-content-hash=\"" + escapeHtml(link.content_hash) + "\" data-rewrites-legal-rule=\"false\">",
      "<span data-role=\"fact-text\">" + escapeHtml(link.fact_text) + "</span>",
      "<span data-role=\"fact-source-id\">" + escapeHtml(link.fact_source_id) + "</span>",
      "<span data-role=\"fact-reason\">" + escapeHtml(link.reason) + "</span>",
      "</li>",
    ].join("");
  }).join("");
  var rejectedItems = rejected.map(function (item) {
    return "<li data-role=\"rejected-narrative\" data-reason=\"" + escapeHtml(item.reason) + "\">" + escapeHtml(item.text) + "</li>";
  }).join("");
  return [
    "<section data-role=\"law-derived-dependency-graph\" data-task-id=\"CIMP-GUI-27\" data-proof=\"false\" data-rules-rewritten=\"false\">",
    "<section data-role=\"legal-rules\">" + rules + "</section>",
    "<section data-role=\"factual-links\"><ul>" + factItems + "</ul></section>",
    "<section data-role=\"rejected-narratives\"><ul>" + rejectedItems + "</ul></section>",
    "</section>",
  ].join("");
}

function renderLawDerivedDependencyGraph(container, payload) {
  var html = lawDerivedDependencyMarkup(payload);
  if (container && typeof container === "object") {
    container.innerHTML = html;
  }
  return html;
}

var complaintGraphView = {
  escapeHtml: escapeHtml,
  lawDerivedDependencyMarkup: lawDerivedDependencyMarkup,
  renderLawDerivedDependencyGraph: renderLawDerivedDependencyGraph,
};

if (typeof module !== "undefined" && module.exports) {
  module.exports = complaintGraphView;
}
if (typeof window !== "undefined") {
  window.complaintGraphView = complaintGraphView;
}
