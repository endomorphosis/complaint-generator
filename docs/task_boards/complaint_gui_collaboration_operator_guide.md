# GUI collaboration operations

This guide is the operator surface for the `complaint-gui-collaboration` campaign. It documents user, lawyer, and admin authorization, key and grant recovery, consent, private messaging, graph provenance, finite stopping, and authenticated watchdog operation. It is not completion authority, provider authority, campaign-state authority, or publication authority.

Validation of this document does not complete `CIMP-GUI-60`. That task stays self-pending until a Root post-Native-callback audit, outside this task, accepts an actual Native member receipt, an actual Native callback, the current canonical task identity, and a settled merge queue. A passing focused test is not that callback and does not manufacture completion.

The new plan is `docs/task_boards/complaint_gui_collaboration_spec.json`, `docs/task_boards/complaint_gui_collaboration_formal_work_plan.json`, and `docs/task_boards/complaint_gui_collaboration_task_board.md`. Its namespace is `complaint-gui-collaboration` and its task ids are `CIMP-GUI-01` through `CIMP-GUI-60`. Source baseline `2c1439a7029eb9035338133210d8b43319add8a4` identifies the program that was specified. Packet shape and ingestion of that plan do not complete any task. Completion of the old 58-task intake program and completion of the old 44-task mediator program do not complete this new program. Preserve those boards, histories, and qualification artifacts as historical scoped evidence. Do not remap them onto `CIMP-GUI-*` ids.

## Authorization

Keep the actual actor distinct from the canonical encrypted owner. A matching owner binding, a body-supplied role, `trusted_local=True`, or a captured mediator does not authorize a different person.

| Actor | Default access |
| --- | --- |
| case owner | Own authorized case, collaborators, and processing choices |
| assigned lawyer | Case content only after the recipient accepts the membership and the key grant |
| operational admin | Minimal account, role, assignment, and operational metadata |
| unassigned lawyer or stranger | No case content |

A lawyer role alone grants no case access. Owners invite participants. Recipients accept scopes and key access. Administrative authority does not supply an ambient decryption key and does not permit inspection of every complaint. Case-content analysis requires a separate case grant. Notifications, operational logs, browser caches, and error reports must not disclose complaint text, evidence, messages, credentials, or keys.

## Key and grant recovery

Shared content opens only through a recipient-bound key grant that records scope, expiry, revocation, and rotation. A missing key does not mint a replacement key and does not create an empty case. A locked store stays locked. Revocation denies future access. Revocation cannot erase previously downloaded content. An expired or revoked grant is denied on the next read, including a late result that arrives after revocation.

## Consent

Local processing is the default. Omitting a privacy flag preserves a saved choice and never creates consent. Encryption unlock is not consent.

```bash
python -m complaint_generator.cli chat --user-id USER_ID --privacy-mode local
python -m complaint_generator.cli chat --user-id USER_ID --privacy-mode grok
```

`--privacy-mode local` keeps generation on the machine. `--privacy-mode grok` is explicit per-case egress consent and can send the generation prompt, including complaint text placed in that prompt, to the configured Grok route. The development authorization for Grok 4.7 through `ipfs_accelerate_py.llm_router` provider `grok_cli` is not egress consent and never authorizes sending a real complaint. Purpose, minimization, and the current consent and grants are checked again before a late result is accepted. A synthetic test transport is not live provider qualification.

## Private messaging

Users and assigned lawyers receive encrypted case conversations, attachments, review tasks, and in-app notifications. Sends and reads are authorized and idempotent. A message remains a conversation until an explicit accepted action adopts it as evidence, an intake answer, or an allowed model input. Shared edits carry the expected revision and the actual actor. The qualified transport for this campaign is http polling. WebSocket, SSE, and streaming are not claimed. Email, SMS, and court filing are outside this campaign.

## Graph provenance

The factual graph records user assertions and evidence revisions with source ids, corrections, contradictions, and hypothesis status. The legal dependency graph records an admitted authority passage, jurisdiction, effective date, and version. A factual answer can affect support for a rule. It does not rewrite the rule.

Search snippets, LLM text, a parsed IR, training metrics, and an unexecuted proof are not governing law and are not verified support. A structurally consistent graph, a filled form, or a generated draft is not legal sufficiency. This guide does not give legal advice.

## Finite stopping

The interview stops when no actionable question remains, or when a declared limit, pause, cancellation, unavailable capability, or user quit applies. It retains research, factual, and evidentiary gaps. Saturation, a completed software taskboard, and a parsed IR are not legal sufficiency.

`awaiting_user` means the product is waiting for a person. It is not a stalled worker and it does not extend a development-task deadline. Development work keeps a three-attempt cap, a 900-second implementation limit, and a 64-turn limit. A missing capability is an honest failure or an explicit unavailable state. It is not a successful fallback.

## Authenticated watchdog

Run `prepare`, `doctor`, and `start` with this campaign's explicit specification and a fresh private state. Install this campaign's own persistent progress watchdog and the expected plan and spec pins. A doctor report or a PID alone does not establish startup. Authenticated watchdog operation observes the actual Grok route (`grok_cli`, model `grok-4.7`, fallback disabled), the canonical active task and attempt, fresh owned activity, measured validation, merge, and the normal completion callback. The watchdog preserves holds and attempts and uses verified bounded reconciliation. Legitimate user-input waits stay distinct from development workers stalled without progress.

## What closes this campaign

The completion contract in `docs/task_boards/complaint_gui_collaboration_completion_contract.json` defines two audits:

- Pre-completion. Focused validation may pass while `CIMP-GUI-60` remains self-pending. This task never manufactures its own completion.
- Post-Native-callback. Root, outside this task, requires the new plan's actual task id, canonical task CID, goal id, and subgoal id, plus an actual Native member receipt, an actual Native callback from Root, and a settled merge queue whose pending count is zero. Missing evidence is `unavailable`. Work that cannot proceed is `blocked`. Neither result is success.

These do not complete the new program:

- A packet shape that merely resembles a receipt.
- Ingestion of the specification, formal plan, or task board.
- Completion receipts from the old 58-task intake program.
- Completion receipts from the old 44-task mediator program.

Local synthetic GUI acceptance stays separate from optional future live model, corpus, prover, or remote-replica qualification. Unexecuted groups never count as passing. This guide does not start a campaign, read private cases, or publish artifacts.

## Known limitations

Browser qualification belongs to the Task 02 harness: actual Chromium DOM, pipe transport, and same-origin HTTP dispatched into actual ASGI handlers. This operations document does not rerun that harness and does not claim WebSocket, SSE, or streaming support. Encrypted local storage is not remote durability. Historical Native completions of other programs remain historical.
