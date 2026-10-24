# Complaint supervisor progress watchdog

The `watchdog` command checks one explicit repository, plan and campaign state.
It uses `ipfs_accelerate_py.agent_supervisor.rescue.campaign_watchdog` and Native's
persisted programmatic recovery controller. It makes no direct model calls,
manufactures no task completion, and never resets implementation attempts or
answers complaint questions. A normal Native restart can resume authorized
Grok work within the existing implementation budget.

The older `watch` command observes a single launcher for at most six hours and
closes its orphan after exit. Use the new progress watchdog for recurring checks
and recovery. Avoid running competing recovery controllers for the same campaign.

## Run or install

Use the checkout with its pinned submodules and the Python environment used by
the Native supervisor. Keep the explicit paths from the campaign's launcher.

```bash
python scripts/run_complaint_improvement_supervisor.py watchdog \
  --repo-root "$REPO_ROOT" --spec "$SPEC" --state-dir "$CAMPAIGN_STATE" \
  --once --stop-completed

python scripts/run_complaint_improvement_supervisor.py watchdog \
  --repo-root "$REPO_ROOT" --spec "$SPEC" --state-dir "$CAMPAIGN_STATE" \
  --install-user-timer
```

Without `--once`, the command checks every 60 seconds until it verifies completion.
The installer creates only this campaign's dedicated user service and minutely
calendar timer, verifies the units, enables the timer and runs its first check.
It refuses conflicting existing unit files. The timer persists across user
manager restarts; unattended boot operation requires an existing lingering user
manager. The installed service binds the expected plan ID and specification hash.

The service intentionally uses `KillMode=process`: Native's public `start`
detaches its successor, but detachment does not escape a systemd cgroup. Ending
a watchdog check must not kill the newly started supervisor. Native's verified
public `stop` remains responsible for its process tree and container cleanup.
The service timeout allows bounded Native reconciliation and startup work;
implementation attempts retain their existing 900-second deadline and caps.

Inspect `CAMPAIGN_STATE/watchdog/latest.json` for the last result, reason,
completion evidence and recovery stage. The command prints a compact summary.
Use `systemctl --user status UNIT.timer` and `journalctl --user -u UNIT.service`,
with the unit name returned by installation, to inspect scheduling and execution.
Disable it with `systemctl --user disable --now UNIT.timer`.

## Recovery decisions

Healthy provider or validation progress is observed without restarting. A
heartbeat or PID alone does not count as work. Startup grace derives from the
actual launch or task-selection time; polling cannot extend it.
An idle selector or blocked queue with logically ready tasks and no active
worker is treated as lack of progress after the stall threshold. A board with
unmet dependencies or an explicit hold remains held.

A recoverable failure must be observed twice, at least 30 seconds apart, with
the same task and progress identity. Changing the owner resets confirmation,
but does not refund the incident's recovery budget. The ledger survives process
restarts and permits at most two recovery actions per incident with a cooldown.

Each action rechecks the campaign, owner, task, progress, holds and attempt maps.
It uses public `stop`, stopped-only `recover`, `doctor`, and `start` in order.
The stop and start compare the exact observed launcher under the launcher lock.
Only verified Native reconciliation permits restarting, and fresh provider or
validation work establishes recovery. Native retains task selection, paid
attempt accounting, validation, merging and its normal completion callback.

An automatic stop is recorded only after Native verifies closure. The record
binds the exact stopped launcher and shutdown proof, allowing a later check to
resume a known automatic stop. An operator stop changes that binding and is
held. Temporary preflight unavailability waits without consuming another repair.
Unknown or interrupted effects remain recorded as uncertain rather than being
repeated blindly.

Place `HOLD` or `OPERATOR_STOP` in `CAMPAIGN_STATE/watchdog/` to prevent automatic
recovery. Existing manual holds, cancellation, user-input waits, quarantine,
protected incidents and retry limits remain authoritative. Missing credentials,
legal authority or user answers are reported; the watchdog cannot invent them.

## Completion evidence

All-completed checkboxes alone are insufficient. Completion verification reads
the current canonical Native task identities, authenticates the Native journal,
validates member and callback receipts and historical validation records, checks
commit ancestry, and requires a settled target-bound merge queue with no active
implementation. Input custody is checked before and after the read.

Verified completion creates no recovery incident or new provider work. With
`--stop-completed`, the check closes only the still-matching owned launcher.
Later timer checks continue reporting completed work without restarting it.
Historical execution evidence is explicitly separate from a fresh qualification
of every current source file, live legal corpus, remote model, proof engine or
storage replica.
