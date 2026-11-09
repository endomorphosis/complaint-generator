"""Recommendation methods delegated from ClaimSupportHook."""

from __future__ import annotations

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    duckdb = None

from mediator.claim_support_hooks import (
    hashlib,
    json,
)


def _build_reasoning_predicates(
    self,
    claim_type: str,
    element: Dict[str, Any],
    contradiction_candidates: List[Dict[str, Any]],
    temporal_context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    predicates: List[Dict[str, Any]] = [
        {
            'predicate_id': str(element.get('element_id') or element.get('element_text') or claim_type),
            'predicate_type': 'claim_element',
            'claim_type': claim_type,
            'claim_element_id': element.get('element_id'),
            'claim_element_text': element.get('element_text'),
            'coverage_status': element.get('status'),
            'support_by_kind': element.get('support_by_kind', {}),
            'missing_support_kinds': element.get('missing_support_kinds', []),
        }
    ]

    for trace in element.get('support_traces', []) or []:
        if not isinstance(trace, dict):
            continue
        predicates.append(
            {
                'predicate_id': str(trace.get('fact_id') or trace.get('support_ref') or ''),
                'predicate_type': 'support_trace',
                'claim_type': claim_type,
                'claim_element_id': element.get('element_id'),
                'claim_element_text': element.get('element_text'),
                'support_kind': trace.get('support_kind'),
                'support_ref': trace.get('support_ref'),
                'source_table': trace.get('source_table'),
                'text': trace.get('fact_text') or trace.get('support_label') or '',
                'confidence': trace.get('confidence', 0.0),
                'source_proof': self._support_trace_source_proof(trace),
            }
        )

    reasoning_temporal_context = temporal_context if isinstance(temporal_context, dict) else self._get_temporal_reasoning_context(claim_type, element)
    for fact in reasoning_temporal_context.get('temporal_facts', []) or []:
        if not isinstance(fact, dict):
            continue
        temporal_details = fact.get('temporal_context', {}) if isinstance(fact.get('temporal_context'), dict) else {}
        predicates.append(
            {
                'predicate_id': f"temporal_fact:{fact.get('fact_id') or fact.get('text') or ''}",
                'predicate_type': 'temporal_fact',
                'claim_type': claim_type,
                'claim_element_id': element.get('element_id'),
                'claim_element_text': element.get('element_text'),
                'fact_id': fact.get('fact_id'),
                'text': fact.get('text') or '',
                'fact_type': fact.get('fact_type'),
                'event_label': fact.get('event_label') or fact.get('text') or fact.get('fact_id'),
                'predicate_family': fact.get('predicate_family') or fact.get('fact_type') or 'timeline',
                'claim_types': list(fact.get('claim_types', []) or []),
                'element_tags': list(fact.get('element_tags', []) or []),
                'actor_ids': list(fact.get('actor_ids', []) or []),
                'target_ids': list(fact.get('target_ids', []) or []),
                'start_date': temporal_details.get('start_date'),
                'end_date': temporal_details.get('end_date'),
                'granularity': temporal_details.get('granularity'),
                'is_approximate': bool(temporal_details.get('is_approximate', False)),
                'is_range': bool(temporal_details.get('is_range', False)),
                'relative_markers': list(temporal_details.get('relative_markers', []) or []),
                'timeline_anchor_ids': list(fact.get('timeline_anchor_ids', []) or []),
                'source_artifact_ids': list(fact.get('source_artifact_ids', []) or []),
                'testimony_record_ids': list(fact.get('testimony_record_ids', []) or []),
                'source_span_refs': list(fact.get('source_span_refs', []) or []),
                'validation_status': fact.get('validation_status'),
            }
        )

    for lead in reasoning_temporal_context.get('temporal_proof_leads', []) or []:
        if not isinstance(lead, dict):
            continue
        temporal_details = lead.get('temporal_context', {}) if isinstance(lead.get('temporal_context'), dict) else {}
        predicates.append(
            {
                'predicate_id': f"temporal_proof_lead:{lead.get('lead_id') or lead.get('description') or ''}",
                'predicate_type': 'temporal_proof_lead',
                'claim_type': claim_type,
                'claim_element_id': element.get('element_id'),
                'claim_element_text': element.get('element_text'),
                'lead_id': lead.get('lead_id'),
                'description': lead.get('description') or '',
                'related_fact_ids': list(lead.get('related_fact_ids', []) or []),
                'element_targets': list(lead.get('element_targets', []) or []),
                'temporal_scope': lead.get('temporal_scope'),
                'start_date': temporal_details.get('start_date'),
                'end_date': temporal_details.get('end_date'),
                'granularity': temporal_details.get('granularity'),
                'is_approximate': bool(temporal_details.get('is_approximate', False)),
                'is_range': bool(temporal_details.get('is_range', False)),
            }
        )

    for relation in reasoning_temporal_context.get('temporal_relations', []) or []:
        if not isinstance(relation, dict):
            continue
        predicates.append(
            {
                'predicate_id': str(relation.get('relation_id') or ''),
                'predicate_type': 'temporal_relation',
                'claim_type': claim_type,
                'claim_element_id': element.get('element_id'),
                'claim_element_text': element.get('element_text'),
                'relation_type': relation.get('relation_type'),
                'inference_mode': relation.get('inference_mode') or 'derived_from_temporal_context',
                'inference_basis': relation.get('inference_basis') or 'normalized_temporal_context',
                'explanation': relation.get('explanation') or (
                    f"{relation.get('source_fact_id') or 'unknown_fact'} {relation.get('relation_type') or 'related_to'} "
                    f"{relation.get('target_fact_id') or 'unknown_fact'} based on normalized temporal context."
                ),
                'source_fact_id': relation.get('source_fact_id'),
                'target_fact_id': relation.get('target_fact_id'),
                'source_start_date': relation.get('source_start_date'),
                'source_end_date': relation.get('source_end_date'),
                'target_start_date': relation.get('target_start_date'),
                'target_end_date': relation.get('target_end_date'),
                'confidence': relation.get('confidence'),
                'source_artifact_ids': list(relation.get('source_artifact_ids', []) or []),
                'testimony_record_ids': list(relation.get('testimony_record_ids', []) or []),
                'source_span_refs': list(relation.get('source_span_refs', []) or []),
            }
        )

    consistency_summary = reasoning_temporal_context.get('consistency_summary', {})
    if isinstance(consistency_summary, dict) and consistency_summary:
        predicates.append(
            {
                'predicate_id': f"temporal_consistency:{element.get('element_id') or element.get('element_text') or claim_type}",
                'predicate_type': 'temporal_consistency',
                'claim_type': claim_type,
                'claim_element_id': element.get('element_id'),
                'claim_element_text': element.get('element_text'),
                'event_count': consistency_summary.get('event_count', 0),
                'proof_lead_count': consistency_summary.get('proof_lead_count', 0),
                'relation_count': consistency_summary.get('relation_count', 0),
                'issue_count': consistency_summary.get('issue_count', 0),
                'partial_order_ready': bool(consistency_summary.get('partial_order_ready', False)),
                'warning_count': consistency_summary.get('warning_count', 0),
                'warnings': list(consistency_summary.get('warnings', []) or []),
                'relation_type_counts': dict(consistency_summary.get('relation_type_counts', {}) or {}),
                'timeline_anchor_ids': list(consistency_summary.get('timeline_anchor_ids', []) or []),
                'missing_temporal_predicates': list(consistency_summary.get('missing_temporal_predicates', []) or []),
                'required_provenance_kinds': list(consistency_summary.get('required_provenance_kinds', []) or []),
            }
        )

    for issue in reasoning_temporal_context.get('temporal_issues', []) or []:
        if not isinstance(issue, dict):
            continue
        predicates.append(
            {
                'predicate_id': str(issue.get('contradiction_id') or issue.get('dependency_id') or issue.get('issue_id') or ''),
                'predicate_type': 'temporal_issue',
                'claim_type': claim_type,
                'claim_element_id': element.get('element_id'),
                'claim_element_text': element.get('element_text'),
                'issue_type': issue.get('category') or issue.get('issue_type'),
                'summary': issue.get('summary') or issue.get('label') or '',
                'severity': issue.get('severity'),
                'left_node_name': issue.get('left_node_name'),
                'right_node_name': issue.get('right_node_name'),
                'recommended_resolution_lane': issue.get('recommended_resolution_lane'),
                'source_kind': issue.get('source_kind') or 'contradiction_queue',
                'source_ref': issue.get('source_ref'),
                'inference_mode': issue.get('inference_mode') or 'imported_temporal_contradiction',
            }
        )

    for index, candidate in enumerate(contradiction_candidates):
        if not isinstance(candidate, dict):
            continue
        predicates.append(
            {
                'predicate_id': f"contradiction:{element.get('element_id') or element.get('element_text') or claim_type}:{index}",
                'predicate_type': 'contradiction_candidate',
                'claim_type': claim_type,
                'claim_element_id': element.get('element_id'),
                'claim_element_text': element.get('element_text'),
                'support_refs': candidate.get('support_refs', []),
                'overlap_terms': candidate.get('overlap_terms', []),
                'texts': candidate.get('texts', []),
                'polarity': candidate.get('polarity', []),
            }
        )

    return predicates
def _build_claim_validation(
    self,
    claim_type: str,
    claim_matrix: Dict[str, Any],
    gap_claim: Dict[str, Any],
    contradiction_claim: Dict[str, Any],
) -> Dict[str, Any]:
    contradiction_by_element: Dict[str, List[Dict[str, Any]]] = {}
    for candidate in contradiction_claim.get('candidates', []) or []:
        if not isinstance(candidate, dict):
            continue
        element_key = candidate.get('claim_element_id') or candidate.get('claim_element_text')
        if not element_key:
            continue
        contradiction_by_element.setdefault(str(element_key), []).append(candidate)

    gap_by_element: Dict[str, Dict[str, Any]] = {}
    for gap in gap_claim.get('unresolved_elements', []) or []:
        if not isinstance(gap, dict):
            continue
        element_key = gap.get('element_id') or gap.get('element_text')
        if element_key:
            gap_by_element[str(element_key)] = gap

    elements: List[Dict[str, Any]] = []
    validation_status_counts = {
        'supported': 0,
        'incomplete': 0,
        'missing': 0,
        'contradicted': 0,
    }
    claim_proof_gaps: List[Dict[str, Any]] = []
    elements_requiring_follow_up: List[str] = []

    for element in claim_matrix.get('elements', []) or []:
        if not isinstance(element, dict):
            continue
        element_key = element.get('element_id') or element.get('element_text') or ''
        contradiction_candidates = contradiction_by_element.get(str(element_key), [])
        if not contradiction_candidates and element.get('element_text'):
            contradiction_candidates = contradiction_by_element.get(str(element.get('element_text')), [])
        gap_element = gap_by_element.get(str(element_key), {})
        if not gap_element and element.get('element_text'):
            gap_element = gap_by_element.get(str(element.get('element_text')), {})

        proof_diagnostics = {
            'support_trace_count': int((element.get('support_trace_summary') or {}).get('trace_count', 0) or 0),
            'fact_trace_count': int((element.get('support_trace_summary') or {}).get('fact_trace_count', 0) or 0),
            'graph_traced_link_count': int(self._summarize_graph_traces(element.get('links', [])).get('traced_link_count', 0) or 0),
            'missing_support_kind_count': len(element.get('missing_support_kinds', []) or []),
            'contradiction_candidate_count': len(contradiction_candidates),
            'total_links': int(element.get('total_links', 0) or 0),
            'fact_count': int(element.get('fact_count', 0) or 0),
        }
        reasoning_diagnostics = self._run_element_reasoning_diagnostics(
            claim_type,
            element,
            contradiction_candidates,
        )
        if isinstance(reasoning_diagnostics, dict) and 'graphrag_quality_enforces_proof_gaps' not in reasoning_diagnostics:
            reasoning_diagnostics = {
                **reasoning_diagnostics,
                'graphrag_quality_enforces_proof_gaps': False,
            }
        decision_trace = self._build_validation_decision_trace(
            element,
            contradiction_candidates,
            reasoning_diagnostics,
        )
        validation_status = decision_trace.get('validation_status', 'missing')
        proof_gaps = self._proof_gaps_for_element(
            element,
            contradiction_candidates,
            reasoning_diagnostics,
        )
        recommended_action = self._recommended_validation_action(
            validation_status,
            element,
            proof_gaps=proof_gaps,
        )
        proof_diagnostics.update(
            {
                'reasoning_backend_available_count': int(reasoning_diagnostics.get('backend_available_count', 0) or 0),
                'reasoning_predicate_count': int(reasoning_diagnostics.get('predicate_count', 0) or 0),
                'reasoning_ontology_entity_count': int(reasoning_diagnostics.get('ontology_entity_count', 0) or 0),
                'reasoning_ontology_relationship_count': int(reasoning_diagnostics.get('ontology_relationship_count', 0) or 0),
                'reasoning_adapter_statuses': reasoning_diagnostics.get('adapter_statuses', {}),
                'decision_source': decision_trace.get('decision_source', ''),
                'logic_contradiction_count': int(decision_trace.get('logic_contradiction_count', 0) or 0),
                'logic_provable_count': int(decision_trace.get('logic_provable_count', 0) or 0),
                'logic_unprovable_count': int(decision_trace.get('logic_unprovable_count', 0) or 0),
                'ontology_validation_signal': decision_trace.get('ontology_validation_signal', 'unknown'),
            }
        )
        validation_status_counts[validation_status] += 1
        if validation_status != 'supported' and element.get('element_text'):
            elements_requiring_follow_up.append(element.get('element_text'))

        support_quality_summary = (
            element.get('support_quality_summary', {})
            if isinstance(element.get('support_quality_summary'), dict)
            else {}
        )
        temporal_proof_bundle = (
            reasoning_diagnostics.get('temporal_proof_bundle')
            if isinstance(reasoning_diagnostics.get('temporal_proof_bundle'), dict)
            else {}
        )
        claim_support_temporal_handoff = (
            reasoning_diagnostics.get('claim_support_temporal_handoff')
            if isinstance(reasoning_diagnostics.get('claim_support_temporal_handoff'), dict)
            else {}
        )
        temporal_next_actions = [
            dict(action)
            for action in (
                temporal_proof_bundle.get('temporal_next_actions')
                or claim_support_temporal_handoff.get('temporal_next_actions')
                or []
            )
            if isinstance(action, dict)
        ]
        element_validation = {
            'element_id': element.get('element_id'),
            'element_text': element.get('element_text'),
            'coverage_status': element.get('status'),
            'validation_status': validation_status,
            'recommended_action': recommended_action,
            'missing_support_kinds': element.get('missing_support_kinds', []),
            'total_links': element.get('total_links', 0),
            'fact_count': element.get('fact_count', 0),
            'support_by_kind': element.get('support_by_kind', {}),
            'authority_treatment_summary': element.get('authority_treatment_summary', {}),
            'authority_rule_candidate_summary': element.get('authority_rule_candidate_summary', {}),
            'support_trace_summary': element.get('support_trace_summary', {}),
            'graph_trace_summary': self._summarize_graph_traces(element.get('links', [])),
            'support_quality_summary': support_quality_summary,
            'primary_quality_signal': self._primary_quality_signal_for_summary(support_quality_summary),
            'contradiction_candidate_count': len(contradiction_candidates),
            'contradiction_candidates': contradiction_candidates,
            'proof_gap_count': len(proof_gaps),
            'proof_gaps': proof_gaps,
            'proof_diagnostics': proof_diagnostics,
            'proof_decision_trace': decision_trace,
            'reasoning_diagnostics': reasoning_diagnostics,
            'temporal_next_actions': temporal_next_actions,
            'temporal_next_action_count': len(temporal_next_actions),
            'temporal_missingness_kind': 'temporal_gap' if temporal_next_actions else '',
            'gap_context': gap_element,
        }
        elements.append(element_validation)

        for proof_gap in proof_gaps:
            claim_proof_gaps.append(
                {
                    'element_id': element.get('element_id'),
                    'element_text': element.get('element_text'),
                    'validation_status': validation_status,
                    'recommended_action': recommended_action,
                    **proof_gap,
                }
            )

    if validation_status_counts['contradicted']:
        claim_validation_status = 'contradicted'
    elif claim_matrix.get('total_elements', 0) and validation_status_counts['supported'] == claim_matrix.get('total_elements', 0):
        claim_validation_status = 'supported'
    elif validation_status_counts['incomplete'] or validation_status_counts['supported']:
        claim_validation_status = 'incomplete'
    else:
        claim_validation_status = 'missing'

    graph_traced_link_count = sum(
        int((element.get('graph_trace_summary') or {}).get('traced_link_count', 0) or 0)
        for element in elements
        if isinstance(element, dict)
    )

    return {
        'claim_type': claim_type,
        'required_support_kinds': claim_matrix.get('required_support_kinds', []),
        'validation_status': claim_validation_status,
        'validation_status_counts': validation_status_counts,
        'total_elements': claim_matrix.get('total_elements', 0),
        'supported_element_count': validation_status_counts['supported'],
        'incomplete_element_count': validation_status_counts['incomplete'],
        'missing_element_count': validation_status_counts['missing'],
        'contradicted_element_count': validation_status_counts['contradicted'],
        'elements_requiring_follow_up': elements_requiring_follow_up,
        'unresolved_element_count': int(gap_claim.get('unresolved_count', 0) or 0),
        'contradiction_candidate_count': int(contradiction_claim.get('candidate_count', 0) or 0),
        'proof_gap_count': len(claim_proof_gaps),
        'proof_gaps': claim_proof_gaps,
        'proof_diagnostics': {
            'support_trace_count': int((claim_matrix.get('support_trace_summary') or {}).get('trace_count', 0) or 0),
            'fact_trace_count': int((claim_matrix.get('support_trace_summary') or {}).get('fact_trace_count', 0) or 0),
            'total_links': int(claim_matrix.get('total_links', 0) or 0),
            'total_facts': int(claim_matrix.get('total_facts', 0) or 0),
            'graph_traced_link_count': graph_traced_link_count,
            'reasoning': self._summarize_claim_reasoning_diagnostics(elements),
            'decision': self._summarize_claim_validation_decisions(elements),
        },
        'support_quality_summary': dict(claim_matrix.get('support_quality_summary') or {}),
        'elements': elements,
    }
def get_support_paths_for_element(
    self,
    user_id: str,
    claim_type: str,
    *,
    claim_element_id: Optional[str] = None,
    path_kind: Optional[str] = None,
    limit: int = 50,
    include_current_traces: bool = True,
    required_support_kinds: Optional[List[str]] = None,
    ontology: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return persisted support-path records for a claim element.

    Queries ``claim_support_paths`` and returns a structured summary
    with all matching proof-path records sorted by timestamp descending.
    Falls back gracefully when DuckDB is unavailable.
    """
    if not DUCKDB_AVAILABLE:
        return {
            'available': False,
            'user_id': user_id,
            'claim_type': claim_type,
            'claim_element_id': claim_element_id,
            'path_kind': path_kind,
            'paths': [],
            'path_count': 0,
            'quality_summary': self._summarize_support_path_quality([]),
        }

    paths: List[Dict[str, Any]] = []
    try:
        conn = duckdb.connect(self.db_path)
        # where_clauses contains only static column-name strings; all user
        # values are passed as parameterized bind arguments in `params`.
        where_clauses = ['user_id = ?', 'claim_type = ?']
        params: List[Any] = [user_id, claim_type]
        if claim_element_id:
            where_clauses.append('claim_element_id = ?')
            params.append(claim_element_id)
        if path_kind:
            where_clauses.append('path_kind = ?')
            params.append(path_kind)
        where_sql = ' AND '.join(where_clauses)
        rows = conn.execute(
            f"""
            SELECT proof_path_id, claim_element_id, fact_ids, path_kind, metadata, timestamp
            FROM claim_support_paths
            WHERE {where_sql}
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            params + [limit],
        ).fetchall()
        conn.close()
        for row in rows:
            proof_path_id, elem_id, fact_ids_json, pk, meta_json, ts = row
            try:
                fact_ids = json.loads(fact_ids_json) if fact_ids_json else []
            except Exception:
                fact_ids = []
            try:
                path_meta = json.loads(meta_json) if meta_json else {}
            except Exception:
                path_meta = {}
            support_fact_registry_summary = (
                path_meta.get('support_fact_registry_summary')
                if isinstance(path_meta.get('support_fact_registry_summary'), dict)
                else {}
            )
            path_drilldown = (
                path_meta.get('path_drilldown')
                if isinstance(path_meta.get('path_drilldown'), dict)
                else {}
            )

            def _path_list(key: str) -> List[str]:
                value = path_drilldown.get(key)
                if not isinstance(value, list):
                    value = path_meta.get(key)
                if not isinstance(value, list):
                    return []
                normalized: List[str] = []
                for item in value:
                    text = str(item or '').strip()
                    if text and text not in normalized:
                        normalized.append(text)
                return normalized

            support_refs = _path_list('support_refs')
            support_kinds = _path_list('support_kinds')
            source_families = _path_list('source_families')
            graph_ids = _path_list('graph_ids')
            graph_trace_summary = (
                path_drilldown.get('graph_trace_summary')
                if isinstance(path_drilldown.get('graph_trace_summary'), dict)
                else path_meta.get('graph_trace_summary')
            )
            graph_trace_summary = graph_trace_summary if isinstance(graph_trace_summary, dict) else {}
            graph_trace_count = int(
                path_drilldown.get(
                    'graph_trace_count',
                    path_meta.get(
                        'graph_trace_count',
                        graph_trace_summary.get('traced_link_count', 0),
                    ),
                )
                or 0
            )
            paths.append({
                'proof_path_id': proof_path_id or '',
                'claim_element_id': elem_id or '',
                'fact_ids': fact_ids,
                'fact_count': len(fact_ids),
                'support_refs': support_refs,
                'support_ref_count': int(
                    path_drilldown.get('support_ref_count', path_meta.get('support_ref_count', len(support_refs)))
                    or 0
                ),
                'support_kinds': support_kinds,
                'source_families': source_families,
                'graph_ids': graph_ids,
                'graph_id_count': int(
                    path_drilldown.get('graph_id_count', path_meta.get('graph_id_count', len(graph_ids)))
                    or 0
                ),
                'graph_trace_count': graph_trace_count,
                'path_kind': pk or 'support',
                'support_fact_registry_summary': support_fact_registry_summary,
                'metadata': path_meta,
                'timestamp': ts.isoformat() if hasattr(ts, 'isoformat') else str(ts or ''),
                'source': 'persisted',
                'persisted': True,
            })
    except Exception as exc:
        self.mediator.log('get_support_paths_error', error=str(exc), claim_type=claim_type)
        return {
            'available': False,
            'user_id': user_id,
            'claim_type': claim_type,
            'claim_element_id': claim_element_id,
            'path_kind': path_kind,
            'paths': [],
            'path_count': 0,
            'quality_summary': self._summarize_support_path_quality([]),
            'error': str(exc),
        }

    if include_current_traces and (path_kind is None or path_kind == 'support'):
        try:
            links = self._get_enriched_claim_support_links(user_id, claim_type)
            if claim_element_id:
                links = [link for link in links if link.get('claim_element_id') == claim_element_id]
            current_traces = self._collect_support_traces_from_links(links)
            seen_fact_ids = {
                str(trace.get('fact_id') or '')
                for trace in current_traces
                if isinstance(trace, dict) and str(trace.get('fact_id') or '')
            }
            fact_records = self.get_fact_records(
                user_id,
                claim_type,
                claim_element_id=claim_element_id,
                include_links=True,
            )
            for fact in fact_records:
                fact_id = str(fact.get('fact_id') or '')
                if not fact_id or fact_id in seen_fact_ids:
                    continue
                current_traces.append(self._build_fact_record_trace(fact))
                seen_fact_ids.add(fact_id)
            if current_traces:
                current_path = self._build_trace_path_detail(
                    user_id=user_id,
                    claim_type=claim_type,
                    claim_element_id=claim_element_id,
                    traces=current_traces,
                    path_kind='support',
                )
                if current_path['proof_path_id'] not in {path.get('proof_path_id') for path in paths}:
                    paths.insert(0, current_path)
        except Exception as exc:
            self.mediator.log('get_current_support_paths_error', error=str(exc), claim_type=claim_type)

    if limit:
        paths = paths[:limit]

    paths = [
        self._score_support_path_detail(
            path,
            required_support_kinds=required_support_kinds,
            ontology=ontology,
        )
        for path in paths
        if isinstance(path, dict)
    ]
    quality_summary = self._summarize_support_path_quality(paths)

    return {
        'available': True,
        'user_id': user_id,
        'claim_type': claim_type,
        'claim_element_id': claim_element_id,
        'path_kind': path_kind,
        'paths': paths,
        'path_count': len(paths),
        'quality_summary': quality_summary,
    }
def get_question_recommendations(
    self,
    user_id: str,
    claim_type: Optional[str] = None,
    *,
    required_support_kinds: Optional[List[str]] = None,
    max_recommendations: int = 20,
) -> Dict[str, Any]:
    """Return ranked question recommendations for *user_id* based on proof gaps.

    Each recommendation includes:
    - ``question_id`` — stable deterministic identifier
    - ``target_claim_element_id`` — element the question targets
    - ``question_lane`` — category of question (e.g. ``missing_element``, ``testimony_gap``)
    - ``question_type`` — ``testimony`` or ``document_request``
    - ``question_reason`` — human-readable explanation of why the question is recommended
    - ``expected_proof_gain`` — estimated improvement in proof readiness (0–1)
    - ``question_text`` — draft question text the operator can use directly
    - ``retrieval_context`` — best available retrieval results for this element (M4)
    - ``proof_state`` — current element proof state from M5 proof card
    """
    gaps = self.get_claim_support_gaps(
        user_id,
        claim_type=claim_type,
        required_support_kinds=required_support_kinds,
    )
    contradictions = self.get_claim_contradiction_candidates(user_id, claim_type=claim_type)

    # Collect element IDs that have active contradictions
    contradiction_element_ids: List[str] = []
    for claim_contradictions in (contradictions.get('claims') or {}).values():
        for candidate in (claim_contradictions.get('candidates') or []):
            for ref_id in (candidate.get('element_ids') or []):
                contradiction_element_ids.append(str(ref_id))

    recommendations: List[Dict[str, Any]] = []
    max_int = max_recommendations if isinstance(max_recommendations, int) and max_recommendations > 0 else 20

    for current_claim, claim_gaps in (gaps.get('claims') or {}).items():
        seen_element_lanes: set[tuple[str, str]] = set()
        for element in (claim_gaps.get('unresolved_elements') or []):
            if not isinstance(element, dict):
                continue
            element_id = str(element.get('element_id') or '')
            element_text = str(element.get('element_text') or '')
            if not element_text:
                continue

            is_contradicted = element_id in contradiction_element_ids
            lane = 'contradiction_resolution' if is_contradicted else self._question_lane_for_element(element)
            seen_element_lanes.add((element_id, lane))
            question_type = self._question_type_for_lane(lane)
            reason = self._question_reason_for_element(element, lane, contradiction_element_ids)
            gain = self._expected_proof_gain_for_element(element, lane)

            # Build a draft question text appropriate for the lane
            question_text = self._draft_question_text(element_text, lane, element)

            # Deterministic ID from user, claim, element, and lane
            qid_src = f'{user_id}:{current_claim}:{element_id}:{lane}'
            question_id = 'qrec:' + hashlib.sha1(qid_src.encode()).hexdigest()[:12]

            # M4: Enrich with retrieval context when available
            retrieval_context = self.get_retrieval_context_for_element(
                user_id,
                current_claim,
                element_id,
                max_results=3,
            )
            has_retrieval_context = retrieval_context.get('has_retrieval_context', False)
            top_retrieval_results = retrieval_context.get('top_results', [])
            if has_retrieval_context and gain > 0:
                # Dampen gain: existing retrieval context means some evidence is already
                # present, so the incremental value of a new question is lower (15% reduction).
                _RETRIEVAL_CONTEXT_GAIN_DAMPENING = 0.85
                gain = round(gain * _RETRIEVAL_CONTEXT_GAIN_DAMPENING, 3)

            # M5: Attach proof state from element proof card
            proof_state_context: Dict[str, Any] = {}
            try:
                proof_card = self.get_element_proof_card(
                    user_id,
                    current_claim,
                    claim_element_id=element_id or None,
                    claim_element_text=element_text or None,
                    coverage_status=element.get('status') or None,
                )
                proof_state_context = {
                    'proof_state': proof_card.get('proof_state', 'missing'),
                    'missing_predicates': proof_card.get('missing_predicates', []),
                    'contradiction_count': proof_card.get('contradiction_count', 0),
                    'next_action': proof_card.get('next_action', 'gather_evidence'),
                    'proof_explanation': proof_card.get('explanation', ''),
                }
            except Exception:
                proof_state_context = {
                    'proof_state': 'missing',
                    'missing_predicates': [],
                    'contradiction_count': 0,
                    'next_action': 'gather_evidence',
                    'proof_explanation': '',
                }

            quality_summary = element.get('support_quality_summary', {}) if isinstance(element.get('support_quality_summary'), dict) else {}
            primary_quality_signal = self._primary_quality_signal_for_summary(quality_summary)
            recommendations.append({
                'question_id': question_id,
                'claim_type': current_claim,
                'target_claim_element_id': element_id,
                'target_claim_element_text': element_text,
                'question_lane': lane,
                'question_type': question_type,
                'question_reason': reason,
                'expected_proof_gain': gain,
                'question_text': question_text,
                'element_status': element.get('status', ''),
                'element_total_links': int(element.get('total_links', 0) or 0),
                'element_missing_support_kinds': list(element.get('missing_support_kinds', []) or []),
                'support_quality_summary': quality_summary,
                'quality_signal_counts': (
                    quality_summary.get('quality_signal_counts', {})
                    if isinstance(quality_summary.get('quality_signal_counts'), dict)
                    else {}
                ),
                'primary_quality_signal': primary_quality_signal,
                'quality_follow_up_action': primary_quality_signal.get('follow_up_action', ''),
                'retrieval_context': {
                    'has_retrieval_context': has_retrieval_context,
                    'result_count': retrieval_context.get('result_count', 0),
                    'top_score': retrieval_context.get('top_score', 0.0),
                    'duplicate_cluster_count': retrieval_context.get('duplicate_cluster_count', 0),
                    'top_results': top_retrieval_results,
                },
                'proof_state_context': proof_state_context,
            })

        claim_matrix = self.get_claim_coverage_matrix(
            user_id,
            claim_type=current_claim,
            required_support_kinds=required_support_kinds,
        ).get('claims', {}).get(current_claim, {})
        for element in (claim_matrix.get('elements') or []):
            if not isinstance(element, dict):
                continue
            element_id = str(element.get('element_id') or '')
            element_text = str(element.get('element_text') or '')
            if not element_text:
                continue
            lane = self._quality_gap_lane_for_element(element)
            if not lane or lane == 'missing_element' or (element_id, lane) in seen_element_lanes:
                continue
            quality_summary = element.get('support_quality_summary', {}) if isinstance(element.get('support_quality_summary'), dict) else {}
            if str(quality_summary.get('recommended_quality_action') or '') == 'review_support_quality' and lane != 'graph_quality_gap':
                continue
            question_type = self._question_type_for_lane(lane)
            reason = self._question_reason_for_element(element, lane, contradiction_element_ids)
            gain = self._expected_proof_gain_for_element(element, lane)
            question_text = self._draft_question_text(element_text, lane, element)
            qid_src = f'{user_id}:{current_claim}:{element_id}:{lane}'
            primary_quality_signal = self._primary_quality_signal_for_summary(quality_summary)
            recommendations.append({
                'question_id': 'qrec:' + hashlib.sha1(qid_src.encode()).hexdigest()[:12],
                'claim_type': current_claim,
                'target_claim_element_id': element_id,
                'target_claim_element_text': element_text,
                'question_lane': lane,
                'question_type': question_type,
                'question_reason': reason,
                'expected_proof_gain': gain,
                'question_text': question_text,
                'element_status': element.get('status', ''),
                'element_total_links': int(element.get('total_links', 0) or 0),
                'element_missing_support_kinds': list(element.get('missing_support_kinds', []) or []),
                'support_quality_summary': quality_summary,
                'quality_signal_counts': (
                    quality_summary.get('quality_signal_counts', {})
                    if isinstance(quality_summary.get('quality_signal_counts'), dict)
                    else {}
                ),
                'primary_quality_signal': primary_quality_signal,
                'quality_follow_up_action': primary_quality_signal.get('follow_up_action', ''),
                'retrieval_context': {
                    'has_retrieval_context': False,
                    'result_count': 0,
                    'top_score': 0.0,
                    'duplicate_cluster_count': 0,
                    'top_results': [],
                },
                'proof_state_context': {
                    'proof_state': 'quality_gap',
                    'missing_predicates': [],
                    'contradiction_count': 0,
                    'next_action': str(quality_summary.get('recommended_quality_action') or 'strengthen_support_path'),
                    'proof_explanation': reason,
                },
            })
            seen_element_lanes.add((element_id, lane))

    # Rank by expected_proof_gain descending, then by lane priority
    recommendations.sort(key=lambda r: (-r['expected_proof_gain'], r['question_lane']))
    recommendations = recommendations[:max_int]

    return self._with_intake_summary_handoff({
        'available': True,
        'user_id': user_id,
        'claim_type': claim_type,
        'total_recommendations': len(recommendations),
        'testimony_recommendations': sum(1 for r in recommendations if r['question_type'] == 'testimony'),
        'document_request_recommendations': sum(
            1 for r in recommendations if r['question_type'] == 'document_request'
        ),
        'contradiction_resolution_count': sum(
            1 for r in recommendations if r['question_lane'] == 'contradiction_resolution'
        ),
        'recommendations': recommendations,
    })
