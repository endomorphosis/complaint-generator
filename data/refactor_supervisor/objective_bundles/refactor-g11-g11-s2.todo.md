# Objective Bundle: refactor/g11/g11-s2

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [ ] Task checkbox-248: REF-248 Compile candidate diffs into typed AST proof scopes

## REF-248 Compile candidate diffs into typed AST proof scopes

- Status: todo
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-245
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/code_proof_obligations.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/conflict_graph.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_code_proof_scopes.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_code_proof_scopes.py -q
- Bundle: refactor/g11/g11-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S2
- Missing evidence: Proof planning must start from deterministic changed symbols and contracts rather than sending repository-wide source or AST records to a model.
- AST symbols: CONFLICT_RECEIPT_STATUSES, _payload, _sources, _items, _field_items, normalize_repo_path, _normalized_paths, _normalized_terms, _gitmodule_paths, _under, _looks_generated, ConflictSurface, _python_symbols, build_conflict_surface, _merge_duplicate_surfaces, _pair_key, ConflictWeightHistory, ConflictEdge, LaneAssignment, LaneDecision, TaskConflictGraph, ConflictGraph, SurfaceEvidenceEdge, SurfaceEvidenceComparison, SurfaceContradiction, SurfaceContradictionReport, _comparison_values, compare_surface_evidence, _strong_evidence_records, detect_surface_contradictions
- Merge key: refactor/g11/g11-s2
- Candidate kind: seed
- Todo vector key: ref-248-compilecandidatediffsintotypedastproofscopes
- Acceptance: Python diffs produce qualified symbols, imports, calls, state transitions, interfaces, source hashes, and changed-path scopes.; Renames, deletes, generated files, syntax failures, and non-Python changes have explicit conservative handling.; Scopes reuse existing AST and conflict-graph records by blob identity.; Equivalent cold and warm scans produce the same canonical scope identities.

- [ ] Task checkbox-249: REF-249 Build a reviewed code-invariant obligation template registry

## REF-249 Build a reviewed code-invariant obligation template registry

- Status: todo
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-247, REF-248
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_obligation_templates.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/code_proof_obligations.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_obligation_templates.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_obligation_templates.py -q
- Bundle: refactor/g11/g11-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S2
- Missing evidence: Arbitrary Python cannot be made formally verified by translating free-form model claims; enforcement needs reviewed templates with explicit semantics.
- AST symbols: 
- Merge key: refactor/g11/g11-s2
- Candidate kind: seed
- Todo vector key: ref-249-buildareviewedcode-invariantobligationtemplatere
- Acceptance: Initial templates cover legal state transitions, lease uniqueness and fencing, DAG acyclicity, merge idempotence, cache-key completeness, evidence freshness, projection equivalence, and unsupported-proof fail-closed behavior.; Every template declares a Python reference predicate, canonical statement, supported backends, assumptions, mutation cases, and fallback tests.; Template versions and semantic hashes participate in obligation and cache identity.; Unknown or ambiguous code shapes remain unsupported instead of selecting a similar template heuristically.

- [ ] Task checkbox-250: REF-250 Materialize a deterministic code and proof evidence graph in JSON and DuckDB

## REF-250 Materialize a deterministic code and proof evidence graph in JSON and DuckDB

- Status: todo
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-245, REF-248
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/code_evidence_graph.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/artifact_store.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_code_evidence_graph.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_code_evidence_graph.py -q
- Bundle: refactor/g11/g11-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S2
- Missing evidence: Goals, tasks, symbols, obligations, attempts, receipts, validations, and merges need a query plane that does not require parsing a full graph into a model context.
- AST symbols: BUNDLE_INDEX_KIND, SCHEDULER_MANIFEST_KIND, QUERY_SCHEMA, MAX_QUERY_ROWS, _IDENTIFIER, _READ_ONLY_SQL, QueryArtifactPaths, query_artifact_paths, _duckdb_module, _json_text, _json_value, _as_int, _as_bool, _as_float, _string_values, _atomic_write_text, _artifact_kind, _query_descriptor, _common_schema, _bundle_schema, _manifest_schema, _top_level_fields, _graph_mapping, _mapping_items, _populate_bundle_tables, _populate_manifest_tables, _table_descriptions, _write_duckdb, write_queryable_artifact, write_bundle_index_artifact
- Merge key: refactor/g11/g11-s2
- Candidate kind: seed
- Todo vector key: ref-250-materializeadeterministiccodeandproofevidencegra
- Acceptance: The graph uses deterministic nodes and provenance edges derived from AST, task, validation, merge, and proof records.; Paired JSON and DuckDB artifacts expose indexed task, tree, symbol, obligation, assurance, freshness, and dependency queries.; JSON and DuckDB projections round-trip to equivalent canonical graph records.; LLM or GraphRAG enrichment cannot create authoritative proof, merge, coverage, or completion edges.

- [ ] Task checkbox-251: REF-251 Index proof scopes and invalidate stale dependent evidence incrementally

## REF-251 Index proof scopes and invalidate stale dependent evidence incrementally

- Status: todo
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-248, REF-250
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_scope_index.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/dataset_store.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_scope_index.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_scope_index.py -q
- Bundle: refactor/g11/g11-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S2
- Missing evidence: Proof reuse is useful only when every changed semantic input invalidates the affected obligations and receipts.
- AST symbols: SCAN_DETAILS_ARTIFACT_SCHEMA_VERSION, AUDIT_SNAPSHOT_SCHEMA_VERSION, EXHAUSTION_QUORUM_STORE_SCHEMA_VERSION, DatasetArtifact, DatasetScanDetailsArtifact, DatasetAuditSnapshotArtifact, ObjectiveDatasetStore, _atomic_write_text, _atomic_write_bytes, _json_compatible, _nonnegative_int, _nonnegative_float, _normalized_paths, _safe_dataset_id, _import_dataset_cls, _import_dataset_manager_cls, cache_hit_ratio, to_dict, row_count, __init__, persist_records, load_records, load_manifest, persist_scan_details, load_scan_details, load_scan_details_manifest, persist_audit_snapshot, load_audit_snapshot, load_audit_snapshot_manifest, persist_exhaustion_quorum
- Merge key: refactor/g11/g11-s2
- Candidate kind: seed
- Todo vector key: ref-251-indexproofscopesandinvalidatestaledependentevide
- Acceptance: Scope indexes map files, qualified symbols, interfaces, assumptions, templates, toolchains, and policies to dependent obligations and receipts.; Blob reuse avoids reparsing unchanged scopes while deletes and renames invalidate stale records.; Invalidation is transitive across proof-plan dependencies and records a bounded reason chain.; Incremental and exhaustive rebuilds produce equivalent active evidence sets.

- [ ] Task checkbox-252: REF-252 Generate bounded proof context capsules for Codex and Leanstral

## REF-252 Generate bounded proof context capsules for Codex and Leanstral

- Status: todo
- Completion: manual
- Priority: P0
- Track: G11
- Depends on: REF-249, REF-250, REF-251
- Outputs: ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/proof_context.py, ipfs_datasets_py/ipfs_accelerate_py/ipfs_accelerate_py/agent_supervisor/artifact_store.py, ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_context.py
- Validation: PYTHONPATH=ipfs_datasets_py/ipfs_accelerate_py python -m pytest ipfs_datasets_py/ipfs_accelerate_py/test/api/test_agent_supervisor_proof_context.py -q
- Bundle: refactor/g11/g11-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G11.S2
- Missing evidence: Models should receive only task-relevant invariants, trusted prior evidence, counterexamples, and source excerpts.
- AST symbols: BUNDLE_INDEX_KIND, SCHEDULER_MANIFEST_KIND, QUERY_SCHEMA, MAX_QUERY_ROWS, _IDENTIFIER, _READ_ONLY_SQL, QueryArtifactPaths, query_artifact_paths, _duckdb_module, _json_text, _json_value, _as_int, _as_bool, _as_float, _string_values, _atomic_write_text, _artifact_kind, _query_descriptor, _common_schema, _bundle_schema, _manifest_schema, _top_level_fields, _graph_mapping, _mapping_items, _populate_bundle_tables, _populate_manifest_tables, _table_descriptions, _write_duckdb, write_queryable_artifact, write_bundle_index_artifact
- Merge key: refactor/g11/g11-s2
- Candidate kind: seed
- Todo vector key: ref-252-generateboundedproofcontextcapsulesforcodexandle
- Acceptance: Context queries select exact task, symbol, dependency, obligation, receipt, and contradiction neighborhoods.; Row, byte, token, graph-hop, source-excerpt, and proof-transcript limits are enforced before prompt assembly.; Capsules distinguish trusted facts, untrusted suggestions, unsupported semantics, and required fallback checks.; Repository-wide AST records, full graphs, hidden witnesses, and unrelated transcripts never enter a capsule.
