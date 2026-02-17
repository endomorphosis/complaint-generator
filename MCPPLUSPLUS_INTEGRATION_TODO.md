# MCP++ → ipfs_datasets_py/mcp_server integration TODO (living doc)

Source (innovations):
- ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/mcplusplus_module

Target:
- ipfs_datasets_py/ipfs_datasets_py/mcp_server

This is intentionally a **living, effectively-infinite TODO list**: keep appending as we discover more parity gaps.

---

## 0) Current status (what already works)

- [x] In-process libp2p TaskQueue service can be started from `mcp_server` (Trio runs in a background thread).
- [x] P2P `call_tool` routes into host MCP tools via `P2PMCPRegistryAdapter`.
- [x] P2P auth mode `mcp_token` is enforced via host `validate_p2p_message`.
- [x] AnyIO↔Trio bridge helper exists (`mcp_server/trio_bridge.py`) for Trio-native client calls.
- [x] Remote P2P wrapper tools exist (`p2p_remote_*`) for status/call_tool/cache/task submit.
- [x] Workflow scheduler tools exist (in-process) and have deterministic unit tests.
- [x] End-to-end test: bring up embedded P2P service and call host MCP tools over libp2p.
- [x] Suite hygiene fixes: embedded service restores env vars on stop; subprocess scripts self-bootstrap sys.path; P2P service call routing supports lightweight `accelerate_instance.call_tool()` providers.

---

## 1) Inventory: what `mcplusplus_module` actually provides today

Concrete code we can reuse/refactor into `mcp_server`:

- [x] Trio bridge utility pattern: `mcplusplus_module.trio.bridge.run_in_trio()`
  - Implemented as `mcp_server/trio_bridge.py`.

- [ ] Trio-native MCP server/client (ASGI + Hypercorn): `mcplusplus_module.trio.server` / `client`
  - Note: `mcp_server` is currently AnyIO/FastMCP stdio-first. We likely **do not replace** it with Trio server.
  - We should borrow patterns (structured concurrency, shutdown hygiene), not wholesale swap runtimes.

- [ ] P2P client tool wrappers:
  - `mcplusplus_module.tools.taskqueue_tools` → wrappers around `ipfs_accelerate_py.p2p_tasks.client`
  - `mcplusplus_module.tools.workflow_tools` → wrappers around workflow scheduler

- [ ] Optional peer discovery helpers:
  - `mcplusplus_module.p2p.bootstrap.SimplePeerBootstrap` (file-based registry + env)
  - `mcplusplus_module.p2p.peer_registry.P2PPeerRegistry` (GitHub Issue comment registry)
  - `mcplusplus_module.p2p.connectivity.UniversalConnectivity` (mDNS/DHT/rendezvous/relay scaffolding)

Docs/aspirational (present in README/init but not implemented in code here):

- [ ] Content-addressed contracts (CID-native MCP-IDL)
- [ ] Immutable execution envelopes/receipts
- [ ] UCAN capability delegation + policy evaluation
- [ ] Event DAG provenance and ordering

---

## 2) Refactor goals in `mcp_server` (make integration maintainable)

### 2.1 Eliminate brittle importability issues

- [ ] Decide one canonical import strategy for nested submodules:
  - Option A: keep runtime sys.path shims (today)
  - Option B: add editable installs (preferred for dev) + document it
  - Option C: vendor the minimal P2P client/service code into `mcp_server`

- [x] Subprocess entrypoints that are invoked by tests bootstrap `sys.path` to find `ipfs_accelerate_py`.
- [ ] Ensure tests always have correct `sys.path` via `tests/conftest.py` (still desirable to reduce per-script shims).

### 2.2 Normalize tool registry shape

- [ ] Create/standardize a single "tool registry adapter" interface so both:
  - FastMCP tools
  - `self.tools` flat dict
  - hierarchical meta-tools
  …are exposed consistently to P2P `call_tool` and to any future remote-exec layer.

### 2.3 Make P2P lifecycle explicit and observable

- [ ] Add health metrics counters for:
  - start/stop success
  - connections
  - call_tool latency/outcome
  - auth failures

- [ ] Add log-level knobs for noisy tool registration.

---

## 3) Integrate MCP++ tool-wrapper surface into `mcp_server`

### 3.1 Remote TaskQueue client tools (discovery + call_tool)

Add wrappers similar to `mcplusplus_module.tools.taskqueue_tools`, but hosted under:
- `ipfs_datasets_py/ipfs_datasets_py/mcp_server/tools/p2p_tools/`

Tasks:

- [x] Add tools for *remote* service operations:
  - [x] `p2p_remote_status(remote_multiaddr="", peer_id="", timeout_s=..., detail=...)`
  - [x] `p2p_remote_submit_task(task_type, model_name, payload, remote_multiaddr="", peer_id="")`
  - [x] `p2p_remote_call_tool(tool_name, args, remote_multiaddr="", remote_peer_id="", timeout_s=...)`
  - [x] `p2p_remote_cache_get/set/has/delete(key, ...)`

- [x] Use a shared `run_in_trio` helper so these work regardless of anyio/asyncio context.

- [x] Tests:
  - [x] Spin up embedded service and test calling it using the remote wrappers.

### 3.2 Workflow scheduler tools

- [x] Confirm `ipfs_accelerate_py.p2p_workflow_scheduler` is importable and stable.
- [x] Add a minimal tool surface in `mcp_server`:
  - [x] `p2p_scheduler_init(...)`
  - [x] `p2p_scheduler_status()`
  - [x] `p2p_scheduler_submit_task(...)`
  - [x] `p2p_scheduler_get_next_task()`
  - [x] `p2p_scheduler_mark_complete(...)`

- [x] Tests:
  - [x] unit tests for scheduler instance lifecycle
  - [x] P2P E2E call_tool invokes scheduler tools over libp2p (via host registry adapter)

- [ ] Optional (future): add explicit *remote* convenience wrappers
  - e.g. `p2p_remote_scheduler_init/status/submit/get_next/mark_complete` that call `p2p_remote_call_tool` with those tool names.

---

## 4) Discovery and peer registry (optional; stage behind config)

- [ ] Add `Configs` toggles for peer discovery backends:
  - [ ] announce-file dialing (already used)
  - [ ] bootstrap peer list
  - [ ] GitHub issue registry
  - [ ] local file registry

- [ ] Implement as a small `PeerDiscoveryProvider` abstraction that feeds:
  - the P2P client dialing helpers
  - and/or the service announce file

- [ ] Tools (optional, dev-only):
  - [ ] register local peer info
  - [ ] list discovered peers

---

## 5) Security hardening

- [ ] Define and document supported auth modes clearly:
  - [ ] `shared_token` (simple interop)
  - [ ] `mcp_token` (unified with MCP auth/session)

- [ ] Add rate limiting / replay protection for P2P RPC messages.
- [ ] Add audit logging hooks for remote tool calls.

---

## 6) Migration path away from submodule coupling

- [ ] Decide what gets vendored vs imported.
- [ ] If vendoring:
  - [ ] copy minimal `p2p_tasks` subset into `mcp_server/p2p/`
  - [ ] keep API stable
  - [ ] add conformance tests (client/service parity)

---

## 7) Testing matrix ("as feasibly as possible")

- [ ] Unit tests:
  - [ ] auth mode enforcement
  - [ ] adapter exposes hierarchical tools
  - [ ] env var propagation

- [ ] Integration tests:
  - [ ] embedded service start/stop
  - [ ] remote call_tool → host tool
  - [ ] remote cache ops
  - [ ] remote task submit/claim flow

- [ ] Regression tests (targeted):
  - [ ] env var restore on embedded service shutdown (prevents cross-test contamination)
  - [ ] subprocess script importability without installation
  - [ ] accelerate_instance routing matrix: MCP-like registry vs lightweight call_tool provider

- [ ] Smoke tests/manual:
  - [ ] run stdio MCP server with `p2p_enabled=True`
  - [ ] use `ipfs_accelerate_py.p2p_tasks.client.call_tool_sync` to invoke `tools_dispatch`

---

## 8) Backlog (future: doc-only items)

These are mentioned by MCP++ docs but are **not present as code** in `mcplusplus_module` right now.
Track them here so we can implement intentionally (or pull from other submodules if they exist elsewhere):

- [ ] CID-native interface contracts (MCP-IDL)
- [ ] execution envelopes + receipts
- [ ] UCAN capability chains
- [ ] temporal deontic policy evaluation
- [ ] event DAG provenance


---

# 9) Never-finish master backlog: refactor `mcp_server` + wire *everything* (import + CLI + MCP tools)

This section intentionally expands scope beyond MCP++ parity. The goal is:

- Every core business logic lives in a stable **core** module (pure-ish functions/classes, minimal side effects).
- Every feature is wired in three consistent surfaces:
  1) Package import API (Python)
  2) CLI tool(s)
  3) MCP server tool(s)
- `pytest` stays green throughout (use small, reversible steps).

Keep appending; do not delete items—mark done and add follow-ups.

## 9.1 Define the architectural target

- [ ] Define a small set of “core layers” and enforce dependencies:
  - `ipfs_datasets_py/core/*` (pure domain logic, dataclasses, protocols)
  - `ipfs_datasets_py/infrastructure/*` (IO: FS, network, DB, IPFS, auth)
  - `ipfs_datasets_py/adapters/*` (MCP tools, CLI commands, web handlers)
  - `ipfs_datasets_py/apps/*` (entrypoints: CLI, server runners)

- [ ] Decide what remains “feature packages” (e.g. `processors/`, `web_archiving/`, `legal_scrapers/`) vs what gets migrated to `core/`.

- [ ] Add an explicit “allowed import graph” document (simple rules) and a linter check later.

## 9.2 Single source-of-truth feature registry (the wiring problem)

Goal: define each feature once, then generate/register:
- package exports
- CLI subcommands
- MCP tools

Backlog:

- [ ] Create a `FeatureSpec` schema (name, description, deps, CLI hooks, MCP hooks, import path).
- [ ] Implement `FeatureRegistry` with:
  - [ ] lazy loading
  - [ ] optional-dependency guards
  - [ ] capability metadata (tags/categories)
  - [ ] health checks

- [ ] Add adapters:
  - [ ] `feature_to_mcp_tools()` → registers tool functions safely
  - [ ] `feature_to_cli_subcommand()` → adds argparse/click commands
  - [ ] `feature_to_import_exports()` → stable import path (re-export)

- [ ] Add a “registry audit” tool/command:
  - [ ] list features and whether they are wired for import/CLI/MCP
  - [ ] list missing optional deps and which features are disabled

## 9.3 Refactor `mcp_server` into composition (thin server, thick core)

- [ ] Split `mcp_server/server.py` responsibilities:
  - [ ] protocol transport (stdio/http)
  - [ ] tool registration
  - [ ] auth/session
  - [ ] P2P lifecycle
  - [ ] configuration

- [ ] Move tool discovery and import mechanics into a dedicated module:
  - [ ] deterministic ordering
  - [ ] dependency error isolation (optional deps)
  - [ ] avoid scanning directories at runtime where possible

- [ ] Normalize tool metadata (name/category/tags/input schema) across:
  - wrapped functions
  - class-based tools
  - hierarchical/meta tools

## 9.4 CLI: unify entrypoints and make them import-safe

The codebase currently has multiple CLI surfaces (top-level app CLI, feature CLIs, scripts). Goal: a coherent, testable CLI.

- [ ] Choose CLI framework and standard (argparse vs click/typer). Keep it stable.
- [ ] Create a single canonical `ipfs-datasets` entrypoint with subcommands:
  - [ ] `ipfs-datasets mcp-server ...`
  - [ ] `ipfs-datasets tools list ...`
  - [ ] `ipfs-datasets processors ...`
  - [ ] `ipfs-datasets workflows ...`

- [ ] Ensure every CLI module is import-safe:
  - no side-effectful imports
  - optional deps gated
  - can run under `python -m ...` reliably

## 9.5 Package import surface: make stable APIs and deprecation shims intentional

- [ ] Create “public API” modules per area (e.g. `ipfs_datasets_py.public.*`).
- [ ] Replace ad-hoc re-exports with controlled facades.
- [ ] For deprecations already present, add:
  - [ ] explicit migration docs links
  - [ ] sunset dates
  - [ ] tests verifying deprecation shims still work until removal

## 9.6 Optional dependency boundaries (make missing deps non-fatal)

- [ ] Audit all top-level imports that trigger optional dependency imports.
- [ ] Standardize “optional import” helper:
  - [ ] returns a structured error (missing package, extra name, install hint)
  - [ ] used by both CLI and MCP tools

- [ ] Add `pip extras` plan:
  - [ ] `ipfs_datasets_py[mcp]`
  - [ ] `ipfs_datasets_py[processors]`
  - [ ] `ipfs_datasets_py[web]`
  - [ ] `ipfs_datasets_py[p2p]`

## 9.7 Testing gates: prevent regressions while refactoring

- [ ] Add “feature wiring” tests:
  - [ ] every enabled feature appears in registry
  - [ ] every enabled feature has at least one MCP tool
  - [ ] every enabled feature has a CLI command (or explicitly marked N/A)
  - [ ] import surface exposes stable symbols

- [ ] Add “import safety” tests:
  - [ ] importing `ipfs_datasets_py` does not require optional deps
  - [ ] importing `ipfs_datasets_py.mcp_server` does not start threads or servers
  - [ ] CLI `--help` works without optional deps

- [ ] Add “contract tests” for tools:
  - [ ] tool schemas are JSON-serializable
  - [ ] tool call results follow `{ok, result|error}` conventions where intended

## 9.8 P2P + MCP integration hardening (beyond what exists)

- [ ] Add a routing matrix test suite for `call_tool`:
  - [ ] host MCP tool
  - [ ] hierarchical/meta tool
  - [ ] lightweight provider (`call_tool` only)
  - [ ] remote wrapper calling remote wrapper (avoid recursion bugs)

- [ ] Add an “auth modes” matrix test suite:
  - [ ] `mcp_token`
  - [ ] `shared_token`
  - [ ] no token (should fail)
  - [ ] expired/invalid token (should fail)

- [ ] Add explicit env-hygiene regression tests:
  - [ ] embedded service start/stop restores env
  - [ ] tests can run in any order

## 9.9 Feature-by-feature migration playbook (repeatable)

For each feature area (processors, web_archiving, legal_scrapers, workflows, vector stores, etc.):

- [ ] Identify “core logic” vs IO.
- [ ] Move core logic into `core/*` with typed interfaces.
- [ ] Build adapters:
  - [ ] Python facade import
  - [ ] CLI command
  - [ ] MCP tools
- [ ] Add unit tests at the core layer.
- [ ] Add one integration test through MCP tools.

## 9.10 Observability and maintainability

- [ ] Standardize logging (structured fields, request/session ids).
- [ ] Add tracing spans around tool calls (esp. P2P).
- [ ] Add lightweight metrics counters (in-memory export OK).
- [ ] Add a “self-check” tool: `system_diagnostics`.

## 9.11 Cleanup backlog (append-only)

- [ ] Consolidate/replace duplicate registries (`mcp_server/tool_registry.py` vs FastMCP vs adapters).
- [ ] Remove sys.path shims where possible; prefer editable installs for dev.
- [ ] Normalize `__main__.py` / module runners across the repo.
- [ ] Reduce warning noise (DeprecationWarnings in core paths) as separate, safe PRs.


## 9.12 Feature inventory + wiring matrix (the “never done” checklist)

Goal: explicitly enumerate **every feature area** in `ipfs_datasets_py` and track three wiring surfaces:

- Import: stable Python API (module + public symbols)
- CLI: a subcommand/entrypoint that exposes the feature
- MCP: tool(s) that expose the feature

Backlog:

- [ ] Create an authoritative inventory list sourced from the package tree (not docs):
  - [ ] `accelerate_integration/`
  - [ ] `alerts/`
  - [ ] `analytics/`
  - [ ] `audit/`
  - [ ] `auto_installer.py`
  - [ ] `caching/`
  - [ ] `cli/`
  - [ ] `config/`
  - [ ] `content_discovery.py`
  - [ ] `core_operations/`
  - [ ] `dashboards/`
  - [ ] `data_transformation/`
  - [ ] `dataset_manager.py`
  - [ ] `embeddings_router.py`
  - [ ] `error_reporting/`
  - [ ] `graphrag/`
  - [ ] `install/`
  - [ ] `ipfs_backend_router.py`
  - [ ] `knowledge_graphs/`
  - [ ] `legal_scrapers/`
  - [ ] `llm_router.py`
  - [ ] `logic/`
  - [ ] `ml/`
  - [ ] `multimedia/`
  - [ ] `optimizers/`
  - [ ] `p2p_networking/`
  - [ ] `pdf_processing/`
  - [ ] `processors/`
  - [ ] `search/`
  - [ ] `security.py`
  - [ ] `static/` + `templates/`
  - [ ] `utils/`
  - [ ] `vector_stores/`
  - [ ] `web_archiving/`

- [ ] Create a generated wiring report (machine-readable + markdown):
  - [x] `docs/FEATURE_WIRING_MATRIX.json`
  - [x] `docs/FEATURE_WIRING_MATRIX.md`
  - [ ] Each row includes:
    - feature id
    - import module
    - CLI command(s)
    - MCP tool names
    - optional dependency extras required
    - status: wired / partial / missing

- [x] Implement a *static* “wiring scanner” (no imports) that uses filesystem heuristics:
  - [x] detect CLI modules (`cli.py`, `__main__.py`, `console_scripts`)
  - [x] detect MCP tool categories (`mcp_server/tools/*`), including non-package dirs
  - [x] index MCP tool function names recursively (AST scan; no imports)
  - [x] detect import surface (exports in `__init__.py`)
  - [x] map MCP tool function candidates onto feature rows (category → functions)
  - [x] detect *likely* optional-dependency extras (AST import scan + `setup.py` `extras_require` mapping; heuristic)

- [x] Provide a generator script:
  - [x] `scripts/generate_feature_wiring_matrix.py`

- [ ] Implement a *dynamic* “wiring validator” (imports in a sandboxed way):
  - [ ] imports each feature module with optional-dep guards
  - [ ] enumerates symbols exposed
  - [ ] enumerates tools registered (via adapter)
  - [ ] records failures as structured diagnostics

## 9.13 MCP tool taxonomy normalization (consistency across tool categories)

There are many tool subpackages under `mcp_server/tools/`. Normalize naming, categories, tags, and schemas.

- [ ] Define naming conventions:
  - [ ] snake_case tool names
  - [ ] tool prefixes per domain (`ipfs_*`, `dataset_*`, `workflow_*`, `p2p_*`, etc.)
  - [ ] stable category list (no duplicates: `analysis` vs `analytics`, etc.)

- [ ] Unify tool registration paths:
  - [ ] avoid having multiple registries (`tool_registry.py`, `tool_registration.py`, FastMCP)
  - [ ] define a canonical “tool descriptor” structure

- [ ] Create a “tool linter” that checks:
  - [ ] docstring present
  - [ ] JSON schema serializable
  - [ ] no heavy imports at module import time
  - [ ] errors are structured (`{ok: False, error: ...}`) where applicable

## 9.14 Packaging + entrypoints (import/CLI/MCP must match)

- [ ] Audit `setup.py` and ensure entrypoints exist for:
  - [ ] canonical `ipfs-datasets` CLI
  - [ ] `python -m ipfs_datasets_py.mcp_server` runner
  - [ ] optional domain CLIs mapped as subcommands, not scattered scripts

- [ ] Move ad-hoc `sys.path` manipulation into a single, documented dev-only helper.
- [ ] Ensure editable install (`pip install -e ipfs_datasets_py`) gives all entrypoints.

## 9.15 OOM-safe test strategy (tests deferred, but architecture must support it)

Constraint: full-suite runs can OOM on some machines.

- [ ] Split test execution into tiers:
  - [ ] Tier 0: import-safety + wiring scanner (fast, low memory)
  - [ ] Tier 1: unit tests for `core/*` (fast)
  - [ ] Tier 2: MCP tool contract tests (moderate)
  - [ ] Tier 3: P2P integration tests (heavy)

- [ ] Provide a documented “safe default” test command that avoids OOM.
- [ ] Add markers (`@pytest.mark.heavy`, `@pytest.mark.integration`) consistently.

## 9.16 Core extraction waves (repeat until everything is core)

Define repeatable migration waves that move logic inward without breaking APIs.

- [ ] Wave A: tool-adjacent business logic
  - [ ] move validation, parsing, schema building into `core/*`
  - [ ] keep MCP tools as thin wrappers

- [ ] Wave B: CLI-adjacent business logic
  - [ ] move CLI command implementations into `core/*`
  - [ ] CLI becomes argument parsing + formatting only

- [ ] Wave C: feature packages
  - [ ] for each feature package, create `core/<feature>` equivalents
  - [ ] leave shims + deprecations

- [ ] Wave D: eliminate duplicate routers/registries
  - [ ] unify any “router” layers into a single orchestration API
  - [ ] adapters call the same orchestration functions
