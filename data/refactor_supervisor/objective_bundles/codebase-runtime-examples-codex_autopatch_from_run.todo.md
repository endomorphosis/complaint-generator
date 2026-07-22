# Codebase Bundle: codebase/runtime/examples-codex_autopatch_from_run

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: group generated codebase findings by source file and AST locality.
Conflict policy: serialize edits to one file; allow independent file bundles to run concurrently.

## REF-098 Review swallowed exception path in examples/codex_autopatch_from_run.py:60

- Status: completed
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/agent_supervisor/discovery, examples/codex_autopatch_from_run.py
- Validation: python3 -m py_compile examples/codex_autopatch_from_run.py
- Bundle: codebase/runtime/examples-codex_autopatch_from_run
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-examples-codex_autopatch_from_run.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/examples-codex_autopatch_from_run
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: examples/codex_autopatch_from_run.py
- AST symbols: __init__, _append_jsonl, _apply_hunk_to_lines, _apply_patch_transaction, _build_failure_excerpt_from_file_lines, _build_prompt, _combine_apply_patch_blocks, _compact_for_prompt, _count_dg, _count_kg, _debug_extract_reset_info_from_message, _dry_run_apply_patch_text, _extract_apply_patch_blocks, _extract_first_error_message_from_exec_jsonl, _extract_json_block_after_header, _extract_rate_limit_reset_info, _extract_rate_limit_reset_info_with_exec_fallback, _extract_update_files_from_patch_text, _find_session_jsons, _find_subsequence, _find_subsequence_relaxed_indent, _find_subsequence_rstrip, _get_llm_router_backend_config, _load_config, _load_json, _looks_like_apply_patch, _make_task_reminder, _maybe_sleep_from_previous_rate_limit, _multi_file_excerpts_for_prompt, _normalize_patch_text, _parse_apply_patch, _parse_codex_human_reset_at, _parse_iso_dt, _pick_best_valid_patch_with_report, _pick_first_valid_patch, _pick_first_valid_patch_with_report, _pick_reset_at_raw_from_rate_limit_artifact, _pick_worst_sessions, _rate_limit_hint, _reprompt_for_real_patch, _restore_original_text, _run_codex_with_tools, _run_codex_with_tools_logged, _run_post_apply_checks, _safe_abs_path, _session_brief, _tool_cat, _tool_grep, _tool_ls, _tool_patch, _truncate_for_log, _try_parse_json_object, _utc_iso, _validate_python_syntax, _write_rate_limit_artifact, append jsonl, apply hunk to lines, apply patch transaction, argparse, backends, backends llmrouterbackend, backends.llmrouterbackend, build failure excerpt from file lines, build prompt, clip, combine apply patch blocks, compact for prompt, count dg, count kg, datetime, datetime datetime, datetime timedelta, datetime timezone, datetime.datetime, datetime.timedelta, datetime.timezone, debug extract reset info from message, dry run apply patch text, excerpt for file, excerpt_for_file
- AST symbol scope: file
- Goal id: codebase/runtime/examples-codex_autopatch_from_run
- Missing evidence: Review swallowed exception path in examples/codex_autopatch_from_run.py:60
- Merge key: codebase/runtime/examples-codex_autopatch_from_run
- Merge family: examples/codex_autopatch_from_run.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: e398f8e3d3b4f5f5
- Acceptance: Codebase scan filed this finding from examples/codex_autopatch_from_run.py:60. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-098-codebase-scan-e398f8e3d3b4.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.

## REF-099 Review swallowed exception path in examples/codex_autopatch_from_run.py:83

- Status: todo
- Completion: manual
- Priority: P1
- Track: runtime
- Depends on: 
- Outputs: data/agent_supervisor/discovery, examples/codex_autopatch_from_run.py
- Validation: python3 -m py_compile examples/codex_autopatch_from_run.py
- Bundle: codebase/runtime/examples-codex_autopatch_from_run
- Bundle shard: data/refactor_supervisor/objective_bundles/codebase-runtime-examples-codex_autopatch_from_run.todo.md
- Bundle strategy: codebase_file_ast
- Graph parents: codebase/runtime
- Graph depth: 1
- Parallel lane: codebase/runtime/examples-codex_autopatch_from_run
- Conflict policy: serialize findings for the same file; allow independent file bundles to run concurrently
- Predicted files: examples/codex_autopatch_from_run.py
- AST symbols: __init__, _append_jsonl, _apply_hunk_to_lines, _apply_patch_transaction, _build_failure_excerpt_from_file_lines, _build_prompt, _combine_apply_patch_blocks, _compact_for_prompt, _count_dg, _count_kg, _debug_extract_reset_info_from_message, _dry_run_apply_patch_text, _extract_apply_patch_blocks, _extract_first_error_message_from_exec_jsonl, _extract_json_block_after_header, _extract_rate_limit_reset_info, _extract_rate_limit_reset_info_with_exec_fallback, _extract_update_files_from_patch_text, _find_session_jsons, _find_subsequence, _find_subsequence_relaxed_indent, _find_subsequence_rstrip, _get_llm_router_backend_config, _load_config, _load_json, _looks_like_apply_patch, _make_task_reminder, _maybe_sleep_from_previous_rate_limit, _multi_file_excerpts_for_prompt, _normalize_patch_text, _parse_apply_patch, _parse_codex_human_reset_at, _parse_iso_dt, _pick_best_valid_patch_with_report, _pick_first_valid_patch, _pick_first_valid_patch_with_report, _pick_reset_at_raw_from_rate_limit_artifact, _pick_worst_sessions, _rate_limit_hint, _reprompt_for_real_patch, _restore_original_text, _run_codex_with_tools, _run_codex_with_tools_logged, _run_post_apply_checks, _safe_abs_path, _session_brief, _tool_cat, _tool_grep, _tool_ls, _tool_patch, _truncate_for_log, _try_parse_json_object, _utc_iso, _validate_python_syntax, _write_rate_limit_artifact, append jsonl, apply hunk to lines, apply patch transaction, argparse, backends, backends llmrouterbackend, backends.llmrouterbackend, build failure excerpt from file lines, build prompt, clip, combine apply patch blocks, compact for prompt, count dg, count kg, datetime, datetime datetime, datetime timedelta, datetime timezone, datetime.datetime, datetime.timedelta, datetime.timezone, debug extract reset info from message, dry run apply patch text, excerpt for file, excerpt_for_file
- AST symbol scope: file
- Goal id: codebase/runtime/examples-codex_autopatch_from_run
- Missing evidence: Review swallowed exception path in examples/codex_autopatch_from_run.py:83
- Merge key: codebase/runtime/examples-codex_autopatch_from_run
- Merge family: examples/codex_autopatch_from_run.py
- Merge role: codebase_scan
- Work item count: 1
- Work scope: codebase_file_ast
- Candidate kind: codebase_scan
- Goal registration: dynamic
- Todo vector key: 24ed648c404ce112
- Acceptance: Codebase scan filed this finding from examples/codex_autopatch_from_run.py:83. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/discovery/2026-07-22-ref-099-codebase-scan-24ed648c404c.md, fix the bug or improvement, add or update focused validation when appropriate, and keep the supervisor-fed backlog parseable.
