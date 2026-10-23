# CIMP-TUI-12 terminal evidence note

This note describes the supervisor completion gate in
`integrations/ipfs_accelerate/supervisor_terminal_acceptance.py`. It does not
mark CIMP-TUI-12 complete. Completion stays with the validation gate.

The supervisor runs bounded synthetic PTY, graph, and privacy acceptance and
attaches each lane receipt plus the source-file digest. A source substring,
including the text "Status: completed", is recorded and is never completion
authority.

`passed`, `skipped`, and `live_canary` are separate fields. A skipped required
lane is not listed as passed. A live canary result does not move into `passed`.

An end-user interview in `awaiting_user` is a legitimate wait. A development
worker with a missing or stale heartbeat is a stalled worker. Neither path
fabricates a user answer or forces legal completion.

Development continues on a synthetic fixture when one exists. An irreducible
external dependency returns a named diagnostic, increments a bounded retry, and
keeps the prior checkpoint. Product-session legal and user issues stay on the
session and are copied onto the receipt.
