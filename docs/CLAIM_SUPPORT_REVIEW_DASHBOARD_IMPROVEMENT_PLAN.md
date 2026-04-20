# Claim Support Review Dashboard Improvement Plan

This plan describes how to turn the current `/claim-support-review` surface into a stronger operator workflow for testimony capture, document intake, graph-backed evidence organization, vector retrieval, and legal sufficiency review.

The goal is not only to show coverage, but to make sure the system:

1. asks better questions,
2. captures better testimony,
3. ingests and decomposes uploaded documents into reusable evidence units,
4. builds durable knowledge-graph and vector-index representations,
5. evaluates claim facts against legal requirements using graph and logic layers, and
6. feeds those results back into the dashboard, follow-up planner, and document builder.

## Current Baseline

- [templates/claim_support_review.html](../templates/claim_support_review.html) already provides an operator dashboard with coverage summaries, follow-up execution controls, manual review resolution, and recent follow-up history.
- [docs/APPLICATIONS.md](./APPLICATIONS.md) defines `/claim-support-review` as the operator review dashboard for claim support, parse-quality signals, follow-up execution, recent history, and manual-review resolution.
- [docs/PAYLOAD_CONTRACTS.md](./PAYLOAD_CONTRACTS.md) already exposes a substantial claim-support review contract, including `claim_coverage_summary`, `claim_support_gaps`, `claim_contradiction_candidates`, `claim_reasoning_review`, `follow_up_plan_summary`, and `follow_up_history_summary`.
- [complaint_phases/denoiser.py](../complaint_phases/denoiser.py) can already generate gap-driven questions from the current knowledge graph and dependency graph.
- [complaint_phases/knowledge_graph.py](../complaint_phases/knowledge_graph.py) can detect unsupported claims, missing timeline data, isolated entities, and other graph gaps.
- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py) already persists claim requirements, support links, follow-up execution history, and support snapshots in DuckDB.
- [integrations/ipfs_datasets/documents.py](../integrations/ipfs_datasets/documents.py) already provides a real parse contract with normalization, chunking, parse quality signals, and transform lineage.
- [integrations/ipfs_datasets/graphs.py](../integrations/ipfs_datasets/graphs.py) already provides lightweight graph extraction and support clustering.
- [integrations/ipfs_datasets/logic.py](../integrations/ipfs_datasets/logic.py) is still a placeholder seam: the contract exists, but proof and contradiction execution currently returns `not_implemented` when the adapter is available.

This means the repo already has the right seams, but they are not yet composed into one full testimony-to-proof workflow.

## Desired End State

The target workflow for `/claim-support-review` should be:

1. The dashboard loads the current claim and section context.
2. The system identifies proof gaps, contradiction candidates, and low-confidence evidence.
3. The question engine asks a small number of high-value questions tailored to the unresolved legal elements.
4. The user can provide both narrative testimony and supporting documents.
5. Uploaded or referenced documents are parsed, chunked, lineage-tracked, vector-indexed, and graph-linked.
6. Facts extracted from testimony and documents are attached to claim elements and legal elements.
7. Authorities and legal rules are normalized into a law-facing graph.
8. Facts are checked against legal requirements, exceptions, and contradictions.
9. The dashboard reports what is satisfied, what is still missing, what is contradicted, what evidence is weak, and what follow-up question or acquisition step should happen next.
10. The same validated support state feeds the `/document` builder and downstream drafting logic.

## Core Principles

### 1. Keep the adapter boundary intact

As documented in [docs/IPFS_DATASETS_PY_DEPENDENCY_MAP.md](./IPFS_DATASETS_PY_DEPENDENCY_MAP.md), production integration with `ipfs_datasets_py` should continue to flow only through `integrations/ipfs_datasets/*`.

The dashboard plan should not introduce direct production imports of `ipfs_datasets_py` outside that boundary.

### 2. Treat testimony and documents as one evidence substrate

The system should not treat questionnaire answers, uploaded files, web captures, and legal authorities as separate silos. They should all become normalized evidence artifacts with:

- stable IDs,
- parse metadata,
- chunk lineage,
- graph nodes,
- vector embeddings,
- claim-element links, and
- legal sufficiency annotations.

### 3. Ask questions only when they improve proof state

Question generation should be tied to missing legal elements, contradiction resolution, timeline gaps, damages gaps, and evidentiary weakness. It should not be a generic interview loop.

### 4. Make operator review explainable

The dashboard should show why a claim element is missing, contradicted, or weak, which fact and document chunks support that conclusion, and what the next best action is.

## Capability Map

| Need | Current seam | Current status | Needed improvement |
|---|---|---|---|
| Gap-driven questioning | [complaint_phases/denoiser.py](../complaint_phases/denoiser.py) | baseline gap prompts exist | prioritize by legal value, evidence quality, and contradiction impact |
| Claim and evidence graphing | [complaint_phases/knowledge_graph.py](../complaint_phases/knowledge_graph.py), [complaint_phases/dependency_graph.py](../complaint_phases/dependency_graph.py) | core graph structures exist | unify testimony, document chunks, claim elements, and law elements |
| Claim support persistence | [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py) | strong review-state persistence exists | add durable fact registry and evidence-to-proof lineage |
| Document decomposition | [integrations/ipfs_datasets/documents.py](../integrations/ipfs_datasets/documents.py) | parse and chunk contract exists | route all uploaded/supporting documents through one ingestion workflow |
| Graph extraction | [integrations/ipfs_datasets/graphs.py](../integrations/ipfs_datasets/graphs.py) | lightweight graph extraction exists | persist graph snapshots and expose support-path queries |
| Vector retrieval | `integrations/ipfs_datasets/vector_store.py`, document optimization embeddings seam | available in adjacent workflow | add claim-review indexing and retrieval sessions |
| Legal logic/proof | [integrations/ipfs_datasets/logic.py](../integrations/ipfs_datasets/logic.py) | contract exists, implementation is placeholder | implement proof-gap and contradiction checking |
| GraphRAG / ontology support | `integrations/ipfs_datasets/graphrag.py`, `build_ontology`, `validate_ontology` | partially wired | apply to law-element mapping and support scoring |
| Operator dashboard | [templates/claim_support_review.html](../templates/claim_support_review.html) | coverage dashboard exists | expand into testimony/document/proof orchestration surface |

## Main Gaps

1. The dashboard is a review and follow-up surface, but not yet a guided testimony-capture surface.
2. Question generation uses graph gaps, but it does not yet optimize for legal sufficiency, contradiction resolution, or evidentiary quality.
3. The document ingestion contract exists, but the dashboard does not yet expose a first-class document upload and decomposition workflow.
4. The graph adapter can extract graph payloads, but persistent graph query and claim-element proof-path reporting are still limited.
5. The logic adapter exposes the right contract but still does not prove elements or detect contradictions.
6. The current coverage payload is rich, but it does not yet present a canonical “facts applied to law” view per element.
7. Vector search is present elsewhere in the repo, but not yet a first-class retrieval plane for dashboard evidence review and question planning.
8. There is no unified corpus object that consistently links testimony answers, document chunks, evidence facts, authority rules, and legal predicates.

## Recommended Architecture

### Layer 1: Intake and testimony capture

Extend `/claim-support-review` so the operator can enter or edit:

- witness testimony,
- claimant timeline events,
- damages descriptions,
- responsible-party identifications,
- evidence descriptions,
- document uploads or linked documents,
- confidence or certainty markers for testimony.

This should produce a normalized testimony record family, not just transient browser state.

### Layer 2: Document ingestion and decomposition

Every uploaded or linked document should go through [integrations/ipfs_datasets/documents.py](../integrations/ipfs_datasets/documents.py) to generate:

- normalized text,
- document chunks,
- parse quality summary,
- transform lineage,
- document metadata,
- OCR fallback status,
- page-aware provenance,
- chunk-level stable IDs.

The ingestion workflow should emit a stable artifact record that can be linked into claim support, graph extraction, vector indexing, and proof analysis.

### Layer 3: Fact registry and support linking

Build on [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py) to create a broader fact registry contract with:

- fact ID,
- source artifact ID,
- chunk ID or text span,
- extracted proposition text,
- claim type,
- claim element ID,
- confidence,
- provenance metadata,
- contradiction flags,
- validation state.

This should become the shared substrate used by the dashboard, graphs, vector search, proof logic, and drafting.

### Layer 4: Graph construction

Use [integrations/ipfs_datasets/graphs.py](../integrations/ipfs_datasets/graphs.py) and [complaint_phases/knowledge_graph.py](../complaint_phases/knowledge_graph.py) to build:

- testimony graph,
- document graph,
- support graph,
- law graph,
- claim-element satisfaction graph.

The graph model should include at minimum:

- parties,
- acts,
- dates,
- documents,
- factual propositions,
- claim elements,
- legal rules,
- exceptions and defenses,
- support and contradiction edges,
- provenance edges from facts to source chunks.

### Layer 5: Vector retrieval plane

Create a dashboard-facing retrieval session layer over chunk embeddings so the operator and planner can:

- retrieve top evidence chunks for a claim element,
- cluster near-duplicate evidence,
- compare testimony with document text,
- surface semantically related authorities,
- attach retrieved context to question prompts and legal validation.

This should use the same adapter boundary as the existing embeddings router usage in [document_optimization.py](../document_optimization.py).

### Layer 6: Law evaluation and proof

Implement the currently placeholder functions in [integrations/ipfs_datasets/logic.py](../integrations/ipfs_datasets/logic.py) so each claim element can produce:

- provable facts,
- missing predicates,
- contradiction candidates,
- exception or defense triggers,
- uncertain facts,
- proof explanation.

This is the critical layer that turns “coverage” into “facts as applied to law fulfills legal requirements.”

### Layer 7: Dashboard explanation and actioning

The dashboard should present, for each claim element:

- status: supported, partially supported, missing, contradicted, uncertain,
- governing legal rule or element,
- supporting testimony facts,
- supporting document chunks,
- supporting authorities,
- contradiction sources,
- proof-gap explanation,
- recommended next question,
- recommended next acquisition action,
- recommended drafting impact.

## Delivery Workstreams

## Screenshot And Router Review Addendum: Layperson Docket UX

Date: 2026-04-20

This addendum records a pre-implementation UI/UX review pass using Playwright screenshot artifacts from the unified workspace:

- `artifacts/ui-audit-layperson/screenshots/workspace-homepage.png`
- `artifacts/ui-audit-layperson/screenshots/workspace-intake.png`
- `artifacts/ui-audit-layperson/screenshots/workspace-evidence.png`
- `artifacts/ui-audit-layperson/screenshots/workspace-review.png`
- `artifacts/ui-audit-layperson/screenshots/workspace-draft.png`

The screenshot workflow did attempt to route those images through `MultimodalRouterBackend`. The multimodal review and text fallback both timed out, so the saved router artifact at `artifacts/ui-audit-layperson/reviews/iteration-01-review.json` is the deterministic fallback. That timeout is itself a P0 reliability finding: the review/optimizer path must return a bounded artifact and show the fallback reason in the workspace instead of leaving an operator guessing whether visual review actually occurred.

The visual review also expands the product target. The dashboard should not only help an operator review claim support. It should help a layperson create or respond to legal complaints while managing a docket of documents, inspecting and labeling those documents, annotating evidence spans, and asking grounded questions about the docket through `llm_router` and `multimodal_router`.

### Observed UX Risks

1. The current workspace is capability-rich but too dense for a stressed layperson. Intake, evidence, review, draft, Gmail import, MCP examples, release-gate metadata, and generated pleadings appear as long technical panels rather than a small set of obvious next actions.
2. The sticky bottom navigation can cover content in full-page screenshots, especially on intake, evidence, review, and draft. It should reserve layout space or collapse into a safer mobile/action-bar pattern.
3. Evidence intake exposes advanced Gmail, DuckDB, CLI, MCP, OAuth, checkpoint, and JSON-example controls directly in the main layperson path. These should move behind an "Advanced import" or operator mode while the default path stays document/task focused.
4. Review repeats similar proof maps and support cards. Counts are useful, but the user needs one clear answer per element: "what proves this, what is still thin, and what should I do next?"
5. Draft is visually overloaded. The release gate, checklist, composer, recommendations, and full pleading preview compete for attention. The layperson path should show one filing-readiness decision and one primary next action before exposing full document text.
6. Docket management is not yet visible as a primary workflow. There is no first-class list of docket documents, document status, due dates, required response type, annotation progress, or unanswered document questions.
7. Document analysis is not yet anchored in a viewer. A layperson needs to see the actual PDF/image/text page, select a span, apply a label, and ask a question with citations back to that page or span.
8. The chatbot is not presented as a document-grounded assistant. It needs visible scope, cited answers, confidence/fallback state, and a way to turn an answer into a saved annotation, issue, timeline event, or response draft note.
9. Router and optimizer failures are too invisible. If `multimodal_router` times out or falls back to `llm_router`, the UI should say so plainly and preserve a review artifact.
10. Browser regression currently has two pre-implementation blockers: the unified workspace flow tried to click a hidden `#chat-open-profile` link, and the homepage flow expected a stale provider order string. Screenshot review should not depend on brittle hidden controls or outdated provider-order assertions.

### Revised Product Shape

The next UI iteration should treat the workspace as four visible layperson lanes:

1. **Intake**: Tell the story and capture structured facts.
2. **Docket**: Add, triage, inspect, label, and annotate court and evidence documents.
3. **Review**: See what each claim or response issue is supported by, what is thin, and what to do next.
4. **Draft**: Generate or revise a complaint, answer, response, motion, or filing packet only after the record has an explicit readiness posture.

Advanced import, MCP, CLI, DuckDB, provider diagnostics, and optimizer controls should remain discoverable, but they should be secondary operator tools rather than default layperson surface area.

### New Workstream 0: Audit Reliability And Screenshot Review

Priority: P0

Goal: make visual UX review reliable before implementation starts.

Primary files:

- `complaint_generator/ui_ux_workflow.py`
- `playwright/tests/complaint-flow.spec.js`
- `templates/workspace.html`
- `static/complaint_app_shell.js`

Work:

- keep the deterministic fallback, but show fallback status in the workspace UX Audit panel,
- ensure router calls are truly bounded and cannot leave progress stuck at `running_router_review`,
- fix the hidden profile-link browser failure or make the test navigate by URL when the link is intentionally hidden,
- update provider-order expectations so test assertions match the actual configured router order,
- add a screenshot-review test that succeeds with existing screenshots even when the full journey has unrelated failures.

Acceptance criteria:

1. Playwright can capture homepage, intake, evidence, review, draft, docket, document viewer, and chat screenshots in one reliable command.
2. Router review returns either a multimodal result or a deterministic fallback artifact within the configured timeout.
3. The workspace shows whether the latest UX review used `multimodal_router`, `llm_router`, or deterministic fallback.

### New Workstream 1: Docket Command Center

Priority: P0

Goal: make docket documents the organizing object for complaints and responses.

Work:

- add a docket list with document type, source, filing date, response due date, status, and assigned claim/issue labels,
- distinguish court filings, notices, exhibits, correspondence, agency records, and user-uploaded evidence,
- show a primary next action per docket item: inspect, label, annotate, ask, respond, attach to claim, or mark complete,
- let users create a response task from a docket document, including answer/denial/admission, affirmative defense, objection, motion, or records request paths,
- persist docket item state separately from generic evidence records while linking both to the same artifact/chunk provenance.

Acceptance criteria:

1. A layperson can answer "what document needs my attention next?"
2. Each docket document has a clear status and next action.
3. Complaint and response drafting can start from a selected docket item.

### New Workstream 2: Document Viewer, Annotation, And Labeling

Priority: P0

Goal: make document analysis visible, page-aware, and reusable.

Work:

- add a document viewer with page thumbnails, OCR/text layer status, parse quality, and source provenance,
- support span or page annotations with label taxonomy: party, date, deadline, allegation, denial, admission, exhibit, harm, remedy, contradiction, missing proof, legal authority, service issue, and follow-up,
- let users convert an annotation into a timeline event, claim fact, response issue, evidence link, or chatbot question,
- expose confidence and source type on every annotation,
- preserve annotation revisions and reviewer notes.

Acceptance criteria:

1. Users can select a document span and label why it matters.
2. Labels become durable fact/evidence records rather than browser-only notes.
3. Review and Draft can cite annotations by document, page, and span.

### New Workstream 3: Grounded Docket Chat

Priority: P0

Goal: make the chatbot a grounded document assistant, not a generic conversation box.

Work:

- add a chat panel scoped to the selected docket, selected document, selected page, or selected annotation,
- route text questions through `llm_router` and image/page questions through `multimodal_router`,
- require cited answers with document/page/span references whenever source material is available,
- show router state, fallback state, and "not enough evidence" answers plainly,
- let a chat answer become a saved annotation, issue label, timeline event, evidence task, or draft note,
- add suggested prompts for laypeople: "What is this document asking me to do?", "What deadline does this create?", "What allegations do I need to admit, deny, or explain?", "Which pages support my complaint?", and "What should I ask the court for?"

Acceptance criteria:

1. Chat answers cite docket documents and pages.
2. Users can save useful answers into the proof/drafting workflow.
3. Router fallback does not silently change the evidentiary confidence of an answer.

### New Workstream 4: Complaint And Response Drafting

Priority: P0

Goal: support both starting a complaint and responding to documents already in the docket.

Work:

- add a first decision: "I need to start a complaint" vs. "I need to respond to a document",
- for responses, bind the draft to a docket item and extract response obligations, deadlines, allegations, requested relief, and service requirements,
- provide answer/denial/admission and motion/objection-oriented drafting paths,
- keep release-gate checks tied to both legal sufficiency and procedural completeness,
- keep export blocked or warning-gated when required parties, captions, deadlines, signatures, service details, or cited source support are missing.

Acceptance criteria:

1. The user can draft a complaint or a response from the same workspace.
2. Response drafting shows the source docket document and the exact allegations or requests being answered.
3. Export guidance explains procedural blockers in plain language.

### New Workstream 5: Layperson Information Architecture

Priority: P1

Goal: reduce cognitive load without hiding power-user tools.

Work:

- add a mode distinction: Client, Advocate/Operator, and Advanced Tools,
- keep CLI, MCP, DuckDB, provider diagnostics, and optimizer controls in Advanced Tools,
- replace repeated cards with one next-action strip and one proof/readiness summary per lane,
- reserve space for sticky navigation so it does not cover page content,
- simplify copy by removing self-referential workflow language where a direct task label would work,
- make "why this matters legally" available inline for questions, evidence items, and annotations.

Acceptance criteria:

1. A first-time user can identify the next action within five seconds on each lane.
2. Advanced tools remain available without dominating the default task flow.
3. Mobile and narrow desktop screenshots have no sticky-nav overlap.

### Updated Implementation Order

1. Stabilize Playwright screenshot review and router fallback reporting.
2. Add the Docket lane and document-status model.
3. Add the page-aware document viewer with annotation and labeling primitives.
4. Add grounded docket chat with cited answers and save-to-workflow actions.
5. Rework Evidence and Review around a single "what proves this / what is thin / what next" model.
6. Split Draft into complaint-start and response-to-document flows.
7. Move advanced imports and MCP/CLI diagnostics into a secondary advanced-tools lane.

### Second Targeted Screenshot Pass: Docket, Document, Chat

Date: 2026-04-20

A narrower Playwright pass captured the current docket-adjacent surfaces:

- `artifacts/ui-audit-docket-pass/screenshots/workspace-evidence-current.png`
- `artifacts/ui-audit-docket-pass/screenshots/workspace-review-current.png`
- `artifacts/ui-audit-docket-pass/screenshots/workspace-packaged-docket-hidden-in-tools.png`
- `artifacts/ui-audit-docket-pass/screenshots/claim-review-document-intake.png`
- `artifacts/ui-audit-docket-pass/screenshots/document-builder-current.png`
- `artifacts/ui-audit-docket-pass/screenshots/chat-docket-context-current.png`

Those screenshots were sent through `MultimodalRouterBackend` with a tighter docket/document/chat prompt. The multimodal call and text fallback again timed out; the saved artifact is `artifacts/ui-audit-docket-pass/reviews/iteration-02-review.json` with `strategy: deterministic_fallback`. This confirms that the first implementation slice should include visual-audit reliability before using router critique as an automated gate.

The direct visual review from this second pass adds more specific product requirements:

1. **Docket is present but misplaced.** The only explicit packaged-docket UI appears inside `CLI + MCP` as "Packaged Docket Ops." It asks for a bundle manifest path and exposes revalidation/persistence controls. That is useful for an operator, but it is not the layperson docket view. The layperson needs "Documents in my case" first, not "Load packaged legal ops dashboard."
2. **Docket controls are blocked by sticky navigation overlap.** In the packaged-docket screenshot, the stage navigation bar overlays the card content. The layout must reserve space for sticky controls or use a compact action rail that does not cover forms.
3. **Document intake is buried below operator review scaffolding.** The `/claim-support-review` screenshot shows document intake after a long operator sidebar, empty metrics, follow-up controls, and "Review request failed: Not found." A layperson looking for a document would not know whether to load review, fill claim IDs, or upload first.
4. **Chat has a promising filing context but lacks source grounding.** The chat screenshot shows "Ready to answer questions with the selected filing context attached" and labels such as deadline, adverse action, and response needed. It still does not show the actual document page, selected span, citation target, or save buttons for "turn this answer into an annotation / deadline / response issue."
5. **The builder is complaint-first, not docket-response-first.** `/document` describes turning a complaint record into a formal complaint. It does not yet ask whether the user is starting a complaint or responding to a docket document, nor does it bind draft sections to a selected pleading, notice, motion, summons, or agency letter.
6. **Evidence intake and review are close to the right proof model but not a docket model.** They ask what claim element an item strengthens, which is good. They do not yet provide a docket table, document status, response deadline, annotation progress, or per-document unresolved questions.

### Refined UX Target For Layperson Docket Work

The default layperson flow should use this object model and language:

1. **Docket Item**: a document in the case, such as a complaint, summons, notice, exhibit, email, agency letter, court order, motion, or response.
2. **Document Status**: needs review, needs labeling, has deadline, needs response, ready to cite, low-quality OCR, duplicate, or archived.
3. **Annotation**: a page or text span labeled as allegation, admission, denial, deadline, party, date, harm, remedy, exhibit, contradiction, authority, service issue, or follow-up.
4. **Question**: a grounded question asked about one docket item, page, selected span, or group of documents.
5. **Draft Task**: start complaint, answer complaint, respond to motion, object, request records, prepare declaration, or assemble exhibit packet.

The UI should avoid making laypeople work with manifest paths, claim element IDs, execution lanes, queue priority, provider diagnostics, or MCP examples unless they explicitly open Advanced Tools.

### Refined Implementation Slices Before Coding

Slice A: Make the screenshot/router review path dependable.

- Add a small deterministic screenshot-capture target for only Docket, Document Viewer, Chat, Review, and Draft.
- Make router fallback visible in the UX Audit panel and in the generated review artifact.
- Treat router timeout as a warning, not a blocker to saving visual evidence.

Slice B: Promote a Docket tab into the main workspace.

- Add a visible Docket lane between Intake and Evidence/Review.
- Seed it from uploaded documents, review documents, imported local evidence, Gmail documents, and packaged docket manifests.
- Show each docket item with title, type, date, deadline, source, status, labels, annotation count, unanswered questions, and primary next action.

Slice C: Add the document viewer and annotation shell.

- Display the selected document next to its metadata and labels.
- Support page/span annotation records even before advanced PDF rendering is complete.
- Make "Add label," "Ask about this page," "Attach to claim/response," and "Create deadline" the primary actions.

Slice D: Make chat document-scoped.

- Keep the current selected-filing context, but add visible source cards and citation targets.
- Add save actions: save as annotation, save as deadline, save as timeline event, save as response issue, save as evidence task, or save as draft note.
- Require `llm_router` / `multimodal_router` status and fallback messages beside each answer.

Slice E: Split drafting by user intent.

- First ask: "Start a complaint" or "Respond to a document."
- If responding, force selection of a docket item and show the exact document being answered.
- Map extracted allegations, deadlines, requests, defenses, and service requirements into the draft checklist.

## Workstream 1: Better questions

Primary files:

- [complaint_phases/denoiser.py](../complaint_phases/denoiser.py)
- [complaint_phases/knowledge_graph.py](../complaint_phases/knowledge_graph.py)
- [complaint_phases/dependency_graph.py](../complaint_phases/dependency_graph.py)
- [templates/claim_support_review.html](../templates/claim_support_review.html)

Work:

- replace generic missing-info prompts with claim-element-targeted questions,
- rank questions by expected proof gain,
- distinguish testimony questions from document-request questions,
- ask one contradiction-resolution question before broad retrieval when contradictions are blocking,
- add timeline-specific, damages-specific, and actor-identification question types,
- attach a “why this question matters” explanation to each prompt,
- suppress redundant questions when the graph or vector plane already has sufficient support.

Acceptance criteria:

1. Each suggested question maps to at least one unresolved claim element or contradiction.
2. Each question exposes the target legal element and expected benefit.
3. Repeated semantically similar questions are clustered or suppressed.

## Workstream 2: Testimony capture quality

Primary files:

- [templates/claim_support_review.html](../templates/claim_support_review.html)
- mediator review APIs
- future testimony persistence hooks under `mediator/`

Work:

- add a structured testimony composer to the dashboard,
- capture event date, actor, act, target, harm, and source confidence,
- support freeform narrative plus structured extraction preview,
- let the operator mark whether testimony is firsthand, hearsay, or uncertain,
- generate claim-element candidate links before saving,
- persist testimony revisions and review audit history.

Acceptance criteria:

1. Testimony can be stored as structured facts plus raw narrative.
2. Testimony entries can be linked to specific claim elements.
3. The dashboard can show which legal elements each testimony item supports.

## Workstream 3: Document ingestion and decomposition

Primary files:

- [integrations/ipfs_datasets/documents.py](../integrations/ipfs_datasets/documents.py)
- `mediator/evidence_hooks.py`
- `mediator/web_evidence_hooks.py`
- [templates/claim_support_review.html](../templates/claim_support_review.html)

Work:

- add dashboard upload and document-link intake,
- route every document through the shared parse contract,
- persist parse quality flags and transform lineage,
- generate chunk IDs and chunk-level metadata,
- flag low-quality parses for operator remediation,
- expose chunk previews and source-page references in the dashboard,
- support reparsing and OCR retry workflows.

Acceptance criteria:

1. Uploaded documents produce normalized parse records and chunks.
2. Every chunk has stable provenance back to artifact and source span.
3. Low-quality parses surface explicit remediation recommendations in the dashboard.

## Workstream 4: Fact registry and support matrix

Primary files:

- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)
- [docs/PAYLOAD_CONTRACTS.md](./PAYLOAD_CONTRACTS.md)

Work:

- expand the persisted claim support schema into a broader fact registry,
- store fact-to-chunk, fact-to-claim-element, and fact-to-authority links,
- add durable support packet IDs and proof-path references,
- normalize contradiction and uncertainty states on facts,
- expose a canonical “element support ledger” in the review payload.

Acceptance criteria:

1. The review API can explain every element status using concrete fact IDs.
2. Facts can be traced back to testimony or document chunks.
3. Dashboard summaries can be regenerated from stored data without re-parsing the world.

## Workstream 5: Graph enrichment and persistence

Primary files:

- [integrations/ipfs_datasets/graphs.py](../integrations/ipfs_datasets/graphs.py)
- [complaint_phases/knowledge_graph.py](../complaint_phases/knowledge_graph.py)
- [complaint_phases/dependency_graph.py](../complaint_phases/dependency_graph.py)

Work:

- persist graph snapshots for testimony, evidence, and legal elements,
- add query functions for “show support path to this element”,
- add entity resolution between testimony actors and document entities,
- attach law nodes and rule nodes to claim elements,
- make graph snapshots reusable by review, follow-up, and drafting workflows.

Acceptance criteria:

1. Each claim element can show a graph-backed support path.
2. Graph snapshots can be reused instead of recomputed for every review request.
3. Entity resolution reduces duplicate party/evidence nodes across testimony and documents.

## Workstream 6: Vector indexing and retrieval

Primary files:

- `integrations/ipfs_datasets/vector_store.py`
- [integrations/ipfs_datasets/documents.py](../integrations/ipfs_datasets/documents.py)
- review/follow-up mediator hooks

Work:

- index testimony and document chunks in one retrieval plane,
- add claim-element-scoped retrieval,
- add retrieval explanations in the dashboard,
- store retrieval sessions for repeatability,
- use retrieval results to improve follow-up prompts and proof analysis,
- use vector similarity to detect duplicate or conflicting evidence narratives.

Acceptance criteria:

1. Operators can view the top retrieved chunks for an element.
2. Retrieval sessions are stable enough to debug and replay.
3. The question engine can cite retrieved context when asking follow-up questions.

## Workstream 7: Legal rule graph and logic validation

Primary files:

- [integrations/ipfs_datasets/logic.py](../integrations/ipfs_datasets/logic.py)
- `integrations/ipfs_datasets/graphrag.py`
- [mediator/claim_support_hooks.py](../mediator/claim_support_hooks.py)

Work:

- implement `prove_claim_elements`, `check_contradictions`, and related logic adapter behavior,
- normalize legal authorities into rule or predicate structures,
- map legal elements and exceptions into graph nodes,
- run proof-gap detection per claim element,
- expose contradiction explanations and legal-rule explanations,
- distinguish “missing evidence” from “legal rule not satisfied” from “factual contradiction”.

Acceptance criteria:

1. The review payload can state whether an element is unproved, contradicted, or exception-barred.
2. Each result includes a concise explanation of the legal rule or predicate failure.
3. The dashboard can show “facts applied to law” rather than only support counts.

## Workstream 8: Dashboard experience redesign

Primary files:

- [templates/claim_support_review.html](../templates/claim_support_review.html)
- [docs/APPLICATIONS.md](./APPLICATIONS.md)
- [docs/PAYLOAD_CONTRACTS.md](./PAYLOAD_CONTRACTS.md)

Work:

- add separate tabs or sections for Questions, Testimony, Documents, Facts, Graph, Law, and Actions,
- add per-element proof cards with evidence, authority, contradiction, and next-action sections,
- add document-ingestion status and parse-quality panels,
- add graph and retrieval drilldowns without overwhelming the default view,
- preserve deep-link navigation from `/document` into claim and section context,
- keep the current manual-resolution surface but attach it to proof explanations.

Acceptance criteria:

1. Operators can move from question to testimony to proof review without leaving the dashboard.
2. Each unresolved element has a visible next action.
3. The dashboard remains usable for both narrow single-claim review and broad filing readiness review.

## Suggested Milestones

### Milestone 0: Question and testimony foundation

Scope:

- stronger question ranking,
- structured testimony capture,
- question-to-element mapping,
- testimony persistence.

Primary outcome:

The dashboard becomes a guided intake and clarification surface instead of only a post-hoc review screen.

### Milestone 1: Document ingestion plane

Scope:

- dashboard document upload,
- parse contract adoption,
- chunk persistence,
- parse quality remediation.

Primary outcome:

Documents become normalized evidence artifacts rather than opaque attachments.

### Milestone 2: Unified fact and graph substrate

Scope:

- fact registry,
- graph snapshot persistence,
- claim-element support paths,
- testimony/document entity resolution.

Primary outcome:

All support can be traced through one reusable graph-backed corpus.

### Milestone 3: Vector retrieval and review explainability

Scope:

- chunk embeddings,
- element-scoped retrieval,
- retrieval drilldowns,
- duplicate/conflict detection.

Primary outcome:

Operators can see the best evidence chunks and how they were selected.

### Milestone 4: Legal proof and contradiction engine

Scope:

- logic adapter implementation,
- legal rule normalization,
- proof-gap outputs,
- contradiction explanations.

Primary outcome:

The system can explain whether facts satisfy legal elements, not just whether support exists.

### Milestone 5: Full operator productization

Scope:

- redesigned dashboard,
- stable payload contracts,
- evaluation suite,
- `/document` integration,
- queue-backed heavy processing where needed.

Primary outcome:

`/claim-support-review` becomes the canonical operator workflow for evidence sufficiency and legal readiness.

## Data Contracts To Add

The following new payload families are recommended.

### 1. Question Recommendation Contract

Fields:

- question ID,
- question text,
- target claim type,
- target claim element ID,
- question reason,
- expected proof gain,
- question lane (`testimony`, `document_request`, `contradiction_resolution`, `authority_clarification`),
- supporting evidence summary,
- suppression or dedup metadata.

### 2. Testimony Fact Contract

Fields:

- testimony record ID,
- raw narrative,
- extracted structured facts,
- source confidence,
- firsthand status,
- linked claim elements,
- linked artifact IDs,
- contradiction notes,
- created and updated timestamps.

### 3. Evidence Artifact Contract

Fields:

- artifact ID,
- source type,
- filename or URL,
- parse summary,
- transform lineage,
- chunk list or chunk references,
- graph snapshot ID,
- vector index status,
- parse remediation status.

### 4. Element Proof Card Contract

Fields:

- claim element ID,
- legal rule text,
- validation status,
- required predicates,
- satisfied predicates,
- missing predicates,
- contradiction list,
- supporting fact IDs,
- supporting document chunk IDs,
- supporting authority IDs,
- next recommended action.

## Evaluation Plan

The plan should be measured with explicit quality loops.

### Question quality metrics

- percent of questions tied to unresolved legal elements,
- percent of questions answered with usable structured facts,
- duplicate-question suppression rate,
- average proof-gain after each answered question.

### Testimony quality metrics

- fraction of testimony records that produce extractable facts,
- fraction of testimony records linked to at least one claim element,
- contradiction rate between testimony and documents,
- operator correction rate.

### Document pipeline metrics

- parse success rate by format,
- chunk generation rate,
- parse quality tier distribution,
- remediation rate for low-quality parses.

### Proof and sufficiency metrics

- percent of elements with graph-backed support,
- percent of elements with vector-backed retrieval context,
- percent of elements with executable proof status,
- contradiction detection precision on curated fixtures,
- claim-level readiness improvement over baseline.

### Operator experience metrics

- time from review load to first high-value action,
- number of clicks to resolve one missing element,
- percent of unresolved elements with visible next action,
- percent of draft warnings that link to actionable dashboard proof cards.

## Testing Strategy

### Unit tests

- question ranking,
- testimony extraction,
- document parse normalization,
- chunk lineage,
- fact registry linking,
- graph support-path generation,
- proof-gap classification,
- contradiction detection.

### Integration tests

- upload document -> parse -> chunk -> graph -> vector -> review payload,
- answer testimony question -> create fact -> update element proof card,
- authority acquisition -> rule extraction -> proof evaluation,
- `/claim-support-review` -> `/document` context preservation.

### Browser tests

- dashboard question workflow,
- testimony entry and save,
- document upload and parse-quality feedback,
- proof card drilldowns,
- manual resolution with proof explanation.

### Regression tests

- degraded-mode behavior when graphs, logic, or embeddings are unavailable,
- adapter-boundary correctness,
- payload compatibility for existing dashboard clients,
- replayable retrieval and proof snapshots.

## Recommended First Implementation Slice

Implement Milestone 0 first, with one narrow vertical slice:

1. add element-targeted question recommendations,
2. add structured testimony capture to `/claim-support-review`,
3. persist testimony as fact-like records linked to claim elements,
4. show those facts in existing claim-element cards,
5. update `claim_coverage_summary` with testimony-backed support counts.

That slice is the highest leverage because it immediately improves question quality and evidence quality without waiting for full legal-proof implementation.

## Success Criteria

This plan should be considered successful when:

1. `/claim-support-review` can guide operators through testimony and document collection for unresolved legal elements.
2. Uploaded documents are decomposed into reusable chunks with lineage, graph nodes, and vector index entries.
3. The review payload can trace each claim-element decision back to facts, documents, and authorities.
4. The logic layer can distinguish missing support from contradictions and rule failures.
5. `/document` consumes the same validated support state to improve drafting readiness and final complaint quality.
