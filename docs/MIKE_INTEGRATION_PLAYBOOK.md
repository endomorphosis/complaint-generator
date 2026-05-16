# Mike Integration Operator Playbook

This playbook defines the current end-to-end complaint drafting workflow between `complaint-generator` and the `mike` editor submodule.

## 1) Prepare the complaint workspace record

1. Start or resume a complaint workspace session (`/api/complaint-workspace/session`).
2. Complete intake and capture evidence until support review has enough signal for draft work.
3. Generate an initial draft if desired (`complaint.generate_complaint`), or allow automatic draft generation during handoff.

## 2) Hand off to Mike

Use one of the aligned surfaces below:

- MCP tool: `complaint.build_mike_handoff`
- HTTP route: `POST /api/complaint-workspace/mike/handoff`
- Browser SDK: `client.buildMikeHandoff(payload)`
- CLI: `complaint-generator build-mike-handoff`

### Required handoff inputs

- `user_id`

### Optional handoff inputs

- `mike_base_url` (defaults to `COMPLAINT_MIKE_BASE_URL` or `http://localhost:3000`)
- `project_id`
- `workspace_id`
- `generate_draft_if_missing` (default `true`)

### Handoff outputs

- `handoff_id` (stable correlation key for roundtrip sync)
- `mike.launch_url` (ready-to-open editor URL with query params)
- `handoff_payload` containing:
  - current case synopsis
  - claim type
  - draft body/title/relief
  - support review
  - summarized evidence context by claim element

## 2.5) Check integration status and next action

Use one of the aligned surfaces below:

- MCP tool: `complaint.get_mike_integration_status`
- HTTP route: `GET /api/complaint-workspace/mike/status?user_id=...`
- Browser SDK: `client.getMikeIntegrationStatus(userId)`
- CLI: `complaint-generator mike-status`

The status payload reports:

- `latest_handoff_id`, `latest_sync_handoff_id`
- `pending_sync`
- `has_mike_synced_draft`
- `recommended_action`

## 3) Edit and refine in Mike

Use `handoff_payload` as the source-of-truth seed for Mike editing.

Suggested operator behavior:

1. Keep claim framing aligned to the complaint claim type.
2. Preserve evidence-linked statements and citation anchors.
3. Track major redlines so they can be summarized on sync.

## 4) Sync finalized Mike draft back into complaint-generator

Use one of the aligned surfaces below:

- MCP tool: `complaint.sync_mike_final_draft`
- HTTP route: `POST /api/complaint-workspace/mike/sync`
- Browser SDK: `client.syncMikeFinalDraft(payload)`
- CLI: `complaint-generator sync-mike-draft`

### Required sync inputs

- `user_id`
- `body` (final draft text)

### Optional sync inputs

- `title`
- `requested_relief`
- `handoff_id`
- `project_id`
- `workspace_id`
- `mike_document_id`
- `citation_links`
- `redline_summary`
- `source_updated_at`

### Sync behavior

- Persists draft text into the complaint workspace session.
- Marks `draft.sync_source = "mike"` with `draft.sync_metadata`.
- Runs citation-link integrity checks and returns conflict metadata (`citation_link_check`) in the sync response.
- Updates Mike integration history (`last_handoff`, `last_sync`).
- Returns refreshed session/review payload for downstream release-gate checks.

## 5) Post-sync quality gate

After sync, run the normal complaint QA lane:

1. `complaint.review_case`
2. `complaint.analyze_complaint_output`
3. `complaint.get_client_release_gate`

If blocked, iterate in Mike and sync again using the same `handoff_id`.

## 6) Improvement backlog (next increments)

1. Add live evidence side-panel linking in Mike using `evidence_context.elements`.
2. Add explicit citation-link conflict checks at sync time.
3. Add redline-aware acceptance checks in release-gate scoring.
4. Add signed webhooks for push-based sync from Mike to complaint-generator.
