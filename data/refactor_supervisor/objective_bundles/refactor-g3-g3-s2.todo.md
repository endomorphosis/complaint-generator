# Objective Bundle: refactor/g3/g3-s2

Source todo: data/refactor_supervisor/refactor_todo.md
Purpose: automatically parallelized refactor lane generated from goal/subgoal/AST scan metadata.
Conflict policy: keep edits inside this bundle when possible; rely on supervisor merge reconciliation.

- [x] Task checkbox-11: REF-011 Define graph persistence and query interfaces before moving support scoring

## REF-011 Define graph persistence and query interfaces before moving support scoring

- Status: completed
- Completion: manual
- Priority: P1
- Track: G3
- Depends on: 
- Outputs: integrations/ipfs_datasets/graphs.py, complaint_phases/knowledge_graph.py
- Validation: python -m pytest tests/test_complaint_phases.py tests/test_ipfs_adapter_layer.py -q
- Bundle: refactor/g3/g3-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G3.S2
- Missing evidence: Graph support currently lacks a durable query plane.
- AST symbols: KNOWLEDGE_GRAPHS_AVAILABLE, GRAPHS_ERROR, _stable_identifier, _split_sentences, _tokenize, _normalize_semantic_token, _semantic_token_set, _score_fact_match, _fact_dedup_key, _texts_semantically_similar, _cluster_semantically_similar_results, extract_graph_from_text, query_graph_support, persist_graph_snapshot, __all__, normalized, digest, cleaned, parts, canonical_map, stopwords, score, fact_tokens, target_tokens, text, claim_element_id, claim_element_text, left_normalized, right_normalized, left_tokens
- Merge key: refactor/g3/g3-s2
- Candidate kind: seed
- Todo vector key: ref-011-definegraphpersistenceandqueryinterfacesbeforemo
- Acceptance: Interfaces specify persistence, query, and provenance fields.; Fallback graph behavior remains covered.

- [ ] Task checkbox-12: REF-012 Turn not_implemented logic paths into explicit capability-gated contracts

## REF-012 Turn not_implemented logic paths into explicit capability-gated contracts

- Status: todo
- Completion: manual
- Priority: P1
- Track: G3
- Depends on: 
- Outputs: integrations/ipfs_datasets/logic.py, lib/formal_logic
- Validation: python -m pytest tests/test_symbolicai_logic_dependency.py tests/test_ipld_logic_storage_dependency.py -q
- Bundle: refactor/g3/g3-s2
- Bundle strategy: goal/subgoal bundle with AST-symbol locality
- Goal id: G3.S2
- Missing evidence: Formal validation should fail predictably when unavailable.
- AST symbols: LOGIC_AVAILABLE, LOGIC_ERROR, REASONER_BRIDGE_AVAILABLE, REASONER_BRIDGE_ERROR, REASONER_BRIDGE_PATH, LOCAL_FORMAL_LOGIC_AVAILABLE, LOCAL_FORMAL_LOGIC_PATH, _normalize_logic_symbol, _normalize_time_symbol, _build_temporal_formula_for_fact, _normalize_claim_support_temporal_handoff, _normalize_claim_reasoning_review, _normalize_logic_payload, _build_theorem_export_metadata, _build_temporal_reasoning_payload, _derive_reasoner_sentence, _build_reasoner_proof_artifact, _summarize_predicates, _build_local_logic_snapshot, text_to_fol, legal_text_to_deontic, prove_claim_elements, check_contradictions, run_hybrid_reasoning, __all__, text, normalized, start_date, end_date, is_range
- Merge key: refactor/g3/g3-s2
- Candidate kind: seed
- Todo vector key: ref-012-turnnot-implementedlogicpathsintoexplicitcapabil
- Acceptance: Logic status distinguishes unavailable, degraded, and implemented.; Callers do not branch on fragile strings.

## REF-013 Resolve dirty main checkout blocking 1 worktree merges

- Status: completed
- Completion: manual
- Priority: P1
- Track: ops
- Fingerprint: cc1e5dd33337df0314b663f8b3c8d9296a322fec
- Dedupe key: reconciliation_guardrail:main_checkout_dirty
- Depends on:
- Outputs: data/refactor_supervisor/bundle_lanes/refactor-g3-g3-s2/discovery, data/refactor_supervisor/objective_bundles/refactor-g3-g3-s2.todo.md
- Validation: test -f /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g3-g3-s2/discovery/2026-07-22-ref-013-reconciliation-cc1e5dd33337.md
- Acceptance: Reconciliation guardrail filed this because 1 branch or worktree cleanup candidates are blocked by main_checkout_dirty. Use evidence and the machine-readable reconciliation plan in /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g3-g3-s2/discovery/2026-07-22-ref-013-reconciliation-cc1e5dd33337.md, reconcile the dirty checkout or dirty worktree group deliberately, then rerun the supervisor cleanup/reconciliation pass and confirm that the blocked candidate count decreases.

## REF-014 Resolve validation retry-budget failure for REF-012

- Status: todo
- Completion: manual
- Priority: P1
- Track: ops
- Depends on: 
- Outputs: integrations/ipfs_datasets/logic.py, lib/formal_logic, data/refactor_supervisor/bundle_lanes/refactor-g3-g3-s2/discovery
- Validation: python -m pytest tests/test_symbolicai_logic_dependency.py tests/test_ipld_logic_storage_dependency.py -q
- Acceptance: Retry-budget guardrail filed this from repeated validation failures in REF-012. Use evidence in /home/barberb/complaint-generator/data/refactor_supervisor/bundle_lanes/refactor-g3-g3-s2/discovery/2026-07-22-ref-014-ref-012-retry-budget.md to fix the validation blocker, then mark this repair task completed so the supervisor can release REF-012 from strategy blocked_tasks.
