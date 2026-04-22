# Layperson Docket Workspace UI/UX Plan

## Evidence From Current Audit

Fresh Playwright screenshots were captured at:

- `artifacts/ui-audit-layperson-docket-plan-20260420-rerun/screenshots/workspace-homepage.png`
- `artifacts/ui-audit-layperson-docket-plan-20260420-rerun/screenshots/workspace-intake.png`
- `artifacts/ui-audit-layperson-docket-plan-20260420-rerun/screenshots/workspace-evidence.png`
- `artifacts/ui-audit-layperson-docket-plan-20260420-rerun/screenshots/workspace-review.png`
- `artifacts/ui-audit-layperson-docket-plan-20260420-rerun/screenshots/workspace-draft.png`
- `artifacts/ui-audit-layperson-docket-plan-20260420-rerun/screenshots/workspace-integrations.png`

The bounded router smoke report is at:

- `artifacts/ui-audit-layperson-docket-plan-20260420-rerun/reviews/bounded-router-review.json`

The current complaint journey can complete end to end through Playwright, including intake, evidence capture, support review, draft generation, export analysis, UX audit affordances, filing provenance, and markdown/PDF/DOCX packet export.

## Reliability Fixes Completed First

- Provider diagnostics are now lightweight and do not import the heavy router stack just to render browser status.
- Provider diagnostics normalize the public preference order to `codex_cli -> copilot_cli -> openai -> hf_inference_api`.
- Screenshot review now honors `COMPLAINT_GENERATOR_UI_REVIEW_TIMEOUT_SECONDS` and `COMPLAINT_GENERATOR_UI_REVIEW_TIMEOUT_SECONDS_<PROVIDER>`.
- Screenshot review can emit heartbeat lines with `COMPLAINT_GENERATOR_UI_REVIEW_HEARTBEAT_SECONDS`.
- Multimodal and text fallback timeouts now identify the page or router stage that is waiting.

## Main UX Findings

The existing UI has a strong staged mental model, but it is still dense for non-lawyers. The current surfaces explain a lot, often helpfully, but the page length and number of advanced panels can make the safe next action hard to find.

The most important change is to split the experience into two layers:

- A layperson-safe task path that always answers: `Where am I? What should I do next? Why does it matter?`
- An operator/advanced layer for CLI, MCP, Gmail, datasets, provenance, router diagnostics, and audit tooling.

The current bottom stage rail is useful, but it should become a persistent task rail with completion state, blockers, and one primary next action. The rail should work across complaint creation, response creation, and docket review.

## Docket Workspace Target Experience

The docket workspace should be a first-class mode, not only evidence inside a complaint form.

Core surfaces:

- `Docket Overview`: case caption, court, parties, filings count, retrieved documents count, OCR/indexing status, and missing documents.
- `Documents`: searchable table of filings, exhibits, attachments, orders, motions, transcripts, emails, and imported evidence.
- `Document Viewer`: PDF/page viewer with extracted text, page thumbnails, OCR confidence, citations, entities, events, and annotations.
- `Labels`: user and model-generated tags such as `supports claim`, `supports defense`, `needs OCR`, `contains deadline`, `contains admission`, `privilege review`, `key exhibit`.
- `Ask`: chatbot grounded in the docket bundle through `llm_router`, with visible citations and retrieval method.
- `Analysis`: knowledge graph, timeline, claim/defense matrix, Bluebook citations, contradiction candidates, and formal-logic audit outputs.
- `Package`: parquet export status, BM25/vector/KG readiness, IPFS/IPLD identifiers, and Hugging Face upload provenance.

## Document Review Requirements

Each document card should show:

- Human label and filing number.
- Source URL or CourtListener/PACER/RECAP provenance.
- Download status and content hash.
- Page count, OCR status, extracted text status, and vector count.
- BM25 indexed status, KG extracted status, citation extraction status, and formal-logic status.
- Tags, annotations, and claim/defense links.
- Last enrichment timestamp and any failed enrichment stage.

Each document viewer should support:

- Page-level annotation.
- Text span annotation.
- Label application.
- "Connect to fact" and "Connect to claim/defense" actions.
- "Ask about this page/document" chat handoff.
- "Show retrieval trace" for any chatbot answer that cites it.

## Chatbot/RAG Requirements

The chatbot should never answer like a free-floating legal oracle. It should answer from the indexed workspace and show grounding.

Every answer should expose:

- Source documents and page/snippet references.
- Whether retrieval used BM25, vector search, graph traversal, full text, citation resolver, or fallback search.
- Confidence and uncertainty.
- Missing documents or unindexed documents that could change the answer.
- A safe next action, such as "review document 14 attachment 2" or "OCR is missing for this exhibit."

The chatbot should support scoped modes:

- `Ask the whole docket`
- `Ask selected documents`
- `Ask this page`
- `Find evidence for a claim`
- `Find evidence for a defense`
- `Find contradictions`
- `Find deadlines`
- `Find cited legal authorities`

## Implementation Order

1. Add a docket/workspace mode switch and a lightweight docket overview panel.
2. Add document inventory UI backed by the existing packaged docket/operator dashboard data.
3. Add per-document enrichment status fields for OCR, text extraction, BM25, vector count, KG, citation extraction, and formal logic.
4. Add labels and annotations as first-class workspace records, not just display-only UI state.
5. Add document viewer handoffs into chatbot prompts with source scope preserved.
6. Add chat answer provenance cards for source snippets, retrieval method, and missing-index warnings.
7. Add Playwright coverage for docket overview, document selection, annotation, label assignment, and scoped chat handoff.
8. Add multimodal screenshot review as a non-blocking audit lane with heartbeat and deterministic fallback.

## Next Slice Contract

The latest Docket-to-chat screenshot review narrows the next implementation slice to source-grounded document chat and first-class annotations. The Docket lane is now visible enough to anchor the workflow, so the next slice should not expand the dashboard broadly. It should make one selected document trustworthy and reusable.

Must build next:

- A persistent chat scope banner that says whether the assistant is answering from the whole docket, selected documents, one document, one page, or one annotation.
- A selected-document source panel beside chat with title, document type, source/provenance, labels, extracted text preview, and citation targets.
- Assistant answer cards with router path, retrieval method, confidence/source-support state, and citation chips.
- Save actions on answer cards: Save Annotation, Save Deadline, Save Issue, Save Evidence Task, Save Draft Note.
- A real Add Label / Add Annotation flow in the Docket lane that persists at least lightweight browser/workspace records and updates the visible annotation count.
- Deadline extraction or manual deadline capture surfaced as a Docket chip and a Draft/Review blocker when relevant.

Defer for later:

- Full PDF editing.
- Perfect OCR correction.
- Complete knowledge-graph visualization.
- Full formal-logic audit UI.
- CAR/IPLD/Hugging Face package management in the layperson path.
- Complex multi-document answer synthesis until single-document citations and save actions are reliable.

The first acceptance test should follow one document end to end:

1. Select a docket document.
2. Add a label.
3. Ask a scoped chat question.
4. See an answer with router path and citation/source state.
5. Save the answer as an annotation or deadline.
6. Return to Docket and see the annotation/deadline reflected on the document.
7. Open Draft or Review and see the saved item available as source support.

## Screenshot Review Notes

The most recent Playwright review artifacts are:

- `artifacts/ui-audit-docket-plan-review-20260420/screenshots/01-workspace-docket.png`
- `artifacts/ui-audit-docket-plan-review-20260420/screenshots/02-document-chat-context.png`
- `artifacts/ui-audit-docket-plan-review-20260420/screenshots/03-review-support.png`
- `artifacts/ui-audit-docket-plan-review-20260420/screenshots/04-draft-response-context.png`
- `artifacts/ui-audit-docket-plan-review-20260420/reviews/iteration-02-chat-single-review.json`

The four-image bundle review hung, while the single-screen document-chat review completed through `multimodal_router` using `codex_cli`. The audit harness should therefore default to one-surface-at-a-time review until bundle execution has reliable timeouts and partial-artifact reporting.

## Acceptance Criteria

- A layperson can identify the next safest action within five seconds on every main surface.
- A docket operator can see whether every document has been downloaded, OCRed, text extracted, indexed, and enriched.
- Selecting a document makes its provenance, text, labels, annotations, and analysis status visible without leaving the workspace.
- A chatbot answer always includes source references or clearly states that no indexed source supports the answer.
- Playwright captures homepage, complaint workspace, docket overview, document viewer, annotations, labels, chat, and package/export surfaces.
- Router review failures produce heartbeat output and a fallback artifact instead of hanging.
