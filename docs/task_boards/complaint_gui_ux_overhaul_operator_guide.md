# Screenshot-led UX campaign operations

The separately scoped `complaint-gui-ux-overhaul` program contains9goals,22subgoals and68tasks, `CIMP-UX-01` through `CIMP-UX-68`. Its human plan is [implementation_plan.md](../ux/complaint_ux_overhaul/implementation_plan.md); the experience contract and13source-bound synthetic baseline screenshots accompany it. The earlier GUI60 program remains completed historical evidence and is not rewritten.

## Configuration

The exact implementation route is `ipfs_accelerate_py.llm_router`, provider `grok_cli`, model `grok-4.7`, fallback disabled. The campaign initially uses one worktree/worker, three attempts,64turns,90-second startup grace,180-second stall limit and900-second implementation/validation budgets. The dedicated watchdog is limited to two recoveries per incident and preserves holds, uncertainty and paid attempts.

Development-provider permission does not authorize a real complaint's egress. Tests use new synthetic data, actual pinned SDKs/Chromium/Node, private HOME/TMP/XDG/orchestration roots and inherited denial of non-Unix sockets. No real external messages, filing, deployments, dependency installation or recursive SDK/CommonCrawl operations are authorized by the plan.

Keep the SDK pins and active specification stable during execution. A capability gap requires a bounded measured compatibility decision, not silent fallback or a floating update. Admins have operations metadata only by default; complaint analysis requires a separate case/key grant. Notes, labels, conversations and model suggestions require explicit adoption before becoming evidence or accepted answers. A user-marked deadline is an attributed reminder, not a derived legal deadline.

The qualified supervisor repair promotes only the Accelerate pin from its initial baseline at a verified stopped boundary. See [watchdog recovery qualification](complaint_gui_ux_overhaul_watchdog_recovery.md) for the exact revision, measured defects, validation and preserved accounting. Report this promoted pin in subsequent SDK inventories; keep the specification and historical baseline unchanged.

## Author, ingest and start

Use a new canonical UID-owned0700state directory and an empty dedicated0700worktree root outside both source and state. Prefer a filesystem with space for the observed cold-checkout estimate plus overhead; the runtime checks capacity again before execution. Use a named local integration branch and commit the specification, generated plan/board, screenshots, contracts and required source before launch. Native workers check out `HEAD`.

Set `UX_ROOT`, `UX_STATE`, `UX_WORKTREES` and `UX_PYTHON` to the actual operator-selected locations. The shared public entry point is:

```bash
"$UX_PYTHON" -I -B "$UX_ROOT/scripts/run_complaint_improvement_supervisor.py" prepare \
  --repo-root "$UX_ROOT" --spec "$UX_ROOT/docs/task_boards/complaint_gui_ux_overhaul_spec.json" --state-dir "$UX_STATE"
"$UX_PYTHON" -I -B "$UX_ROOT/scripts/run_complaint_improvement_supervisor.py" doctor \
  --repo-root "$UX_ROOT" --spec "$UX_ROOT/docs/task_boards/complaint_gui_ux_overhaul_spec.json" --state-dir "$UX_STATE" --worktree-root "$UX_WORKTREES"
"$UX_PYTHON" -I -B "$UX_ROOT/scripts/run_complaint_improvement_supervisor.py" start \
  --repo-root "$UX_ROOT" --spec "$UX_ROOT/docs/task_boards/complaint_gui_ux_overhaul_spec.json" --state-dir "$UX_STATE" --worktree-root "$UX_WORKTREES"
```

`prepare` validates and round-trips the Native formal contract and preserves an existing matching board. It starts no model and completes no task. `doctor` validates current privacy/resources/configuration and credential presence; it does not verify login, quota or actual execution. `start` publishes actual owned process identity, canonical plan/spec generation and worktree binding through normal code. Do not add fields to saved launcher JSON by hand.

## Observe actual work

```bash
"$UX_PYTHON" -I -B "$UX_ROOT/scripts/run_complaint_improvement_supervisor.py" status \
  --repo-root "$UX_ROOT" --spec "$UX_ROOT/docs/task_boards/complaint_gui_ux_overhaul_spec.json" --state-dir "$UX_STATE"
"$UX_PYTHON" -I -B "$UX_ROOT/scripts/run_complaint_improvement_supervisor.py" watchdog \
  --install-user-timer --repo-root "$UX_ROOT" --spec "$UX_ROOT/docs/task_boards/complaint_gui_ux_overhaul_spec.json" --state-dir "$UX_STATE"
```

Use the installed campaign-specific unit name returned by the installer. Confirm it is enabled/active and that its observations bind the expected plan ID and exact spec SHA. Require the actual owned launcher and daemon, fresh heartbeat, current canonical task CID/attempt, and Grok work/tool activity or genuine validation. A PID, status label, screenshot, doctor result or saved packet alone is not progress evidence.

Normal `recover` uses the same explicit root/spec/state. Never replace state to obtain a clean result, delete claims/leases by hand, synthesize events/callbacks, reset a budget, signal unrelated processes, or reinterpret application `awaiting_user` as a development worker allowed to wait indefinitely.

## Acceptance and completion

Every task has one focused behavioural module, meaningful positive/negative checks and zero required skips. Screenshot tasks need real DOM/API/cryptographic-state assertions and owned process cleanup. Old132-case GUI acceptance remains historical regression coverage, not the new program's closure. The new grouped UX acceptance controller is delivered by task68; do not treat an unimplemented command as a passing test.

Task68 validates its controller while self-pending. After its actual Native callback and settled queue, the operator runs the full current-source acceptance outside any individual900-second worker. Then invoke the production read-only `campaign_completion.verify_campaign_completion` using this explicit specification and actual state. It must authenticate all68canonical tasks and actual integration/history. No callback or task status is manufactured by this guide or the completion contract.

Preserve unresolved legal/factual/evidentiary gaps and optional live-model/corpus/prover/replica limitations. No actionable interview question, parsed IR, screenshot comparison, successful storage write or completed software campaign establishes legal sufficiency or successful filing.
