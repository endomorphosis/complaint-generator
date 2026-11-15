"""Retrieval sessions and proof cards delegated from ClaimSupportHook."""

from __future__ import annotations

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    duckdb = None

from mediator.claim_support_hooks import (
    Counter,
    datetime,
    json,
    re,
    timezone,
)


def _build_validation_decision_trace(
    self,
    element: Dict[str, Any],
    contradiction_candidates: List[Dict[str, Any]],
    reasoning_diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    reasoning = reasoning_diagnostics if isinstance(reasoning_diagnostics, dict) else {}
    adapter_statuses = reasoning.get('adapter_statuses', {}) if isinstance(reasoning.get('adapter_statuses'), dict) else {}
    heuristic_contradiction_count = len(contradiction_candidates)
    logic_contradiction_count = self._extract_logic_contradiction_count(reasoning)
    logic_proof_counts = self._extract_logic_proof_counts(reasoning)
    provable_count = logic_proof_counts['provable_count']
    unprovable_count = logic_proof_counts['unprovable_count']
    ontology_validation_signal = self._extract_ontology_validation_signal(reasoning)
    temporal_rule_profile = self._extract_temporal_rule_profile(reasoning)
    temporal_rule_status = str(temporal_rule_profile.get('status') or '')
    graphrag_quality_signal = self._extract_graphrag_quality_signal(reasoning)
    graphrag_has_blocking_gaps = bool(
        reasoning.get('graphrag_quality_enforces_proof_gaps', True)
        and graphrag_quality_signal.get('has_blocking_gaps', False)
    )
    missing_support_kind_count = len(element.get('missing_support_kinds', []) or [])
    total_links = int(element.get('total_links', 0) or 0)
    coverage_status = str(element.get('status') or '')

    if heuristic_contradiction_count:
        decision_source = 'heuristic_contradictions'
        validation_status = 'contradicted'
    elif logic_contradiction_count:
        decision_source = 'logic_contradictions'
        validation_status = 'contradicted'
    elif temporal_rule_status == 'failed':
        decision_source = 'temporal_rule_failed'
        validation_status = 'incomplete'
    elif temporal_rule_status == 'partial' and total_links > 0:
        decision_source = 'temporal_rule_partial'
        validation_status = 'incomplete'
    elif unprovable_count and total_links > 0:
        decision_source = 'logic_unprovable'
        validation_status = 'incomplete'
    elif provable_count and missing_support_kind_count == 0 and ontology_validation_signal != 'invalid':
        decision_source = 'logic_proof_supported'
        validation_status = 'supported'
    elif provable_count:
        decision_source = 'logic_proof_partial'
        validation_status = 'incomplete'
    elif ontology_validation_signal == 'invalid' and total_links > 0:
        decision_source = 'ontology_validation_failed'
        validation_status = 'incomplete'
    elif coverage_status == 'covered' and total_links > 0 and self._element_has_parse_quality_gap(element):
        decision_source = 'low_quality_parse'
        validation_status = 'incomplete'
    elif graphrag_has_blocking_gaps and total_links > 0:
        decision_source = 'graphrag_quality_gap'
        validation_status = 'incomplete'
    elif ontology_validation_signal == 'valid' and coverage_status == 'covered' and missing_support_kind_count == 0:
        decision_source = 'ontology_validation_supported'
        validation_status = 'supported'
    elif coverage_status == 'covered':
        decision_source = 'covered_support'
        validation_status = 'supported'
    elif total_links > 0:
        decision_source = 'partial_support'
        validation_status = 'incomplete'
    else:
        decision_source = 'missing_support'
        validation_status = 'missing'

    notes: List[str] = []
    if heuristic_contradiction_count:
        notes.append('Heuristic contradiction candidates were found for this element.')
    if logic_contradiction_count:
        notes.append('Logic adapter reported contradiction output for this element.')
    if provable_count:
        notes.append('Logic adapter reported provable claim-element output for this element.')
    if unprovable_count:
        notes.append('Logic adapter reported unprovable claim-element output for this element.')
    if temporal_rule_status == 'failed':
        notes.append('Temporal rule evaluation found chronology that is legally insufficient for this element.')
    elif temporal_rule_status == 'partial':
        notes.append('Temporal rule evaluation found chronology that is present but still incomplete for this element.')
    if ontology_validation_signal == 'invalid':
        notes.append('Ontology validation returned an invalid or inconsistent result for this element.')
    elif ontology_validation_signal == 'valid':
        notes.append('Ontology validation reported a valid or consistent result for this element.')
    if validation_status == 'incomplete' and decision_source == 'low_quality_parse':
        notes.append('Available support was parsed with low extraction quality and should be refreshed from a better source copy.')
    if decision_source == 'graphrag_quality_gap':
        notes.append('GraphRAG ontology has blocking quality gaps that need to be resolved before this element can be fully validated.')
    if missing_support_kind_count:
        notes.append('Required support kinds are still missing for this element.')
    if reasoning.get('used_fallback_ontology'):
        notes.append('Fallback ontology was used because adapter ontology output was unavailable or empty.')

    return {
        'validation_status': validation_status,
        'decision_source': decision_source,
        'coverage_status': coverage_status,
        'heuristic_contradiction_count': heuristic_contradiction_count,
        'logic_contradiction_count': logic_contradiction_count,
        'logic_provable_count': provable_count,
        'logic_unprovable_count': unprovable_count,
        'ontology_validation_signal': ontology_validation_signal,
        'temporal_rule_profile_id': str(temporal_rule_profile.get('profile_id') or ''),
        'temporal_rule_status': temporal_rule_status,
        'temporal_rule_blocking_reason_count': len(temporal_rule_profile.get('blocking_reasons', []) or []),
        'temporal_rule_follow_up_count': len(temporal_rule_profile.get('recommended_follow_ups', []) or []),
        'graphrag_quality_signal': graphrag_quality_signal,
        'graphrag_has_blocking_gaps': graphrag_has_blocking_gaps,
        'missing_support_kind_count': missing_support_kind_count,
        'total_links': total_links,
        'used_fallback_ontology': bool(reasoning.get('used_fallback_ontology')),
        'adapter_statuses': {
            name: {
                'status': str(summary.get('status') or ''),
                'implementation_status': str(summary.get('implementation_status') or ''),
                'backend_available': bool(summary.get('backend_available', False)),
            }
            for name, summary in adapter_statuses.items()
            if isinstance(summary, dict)
        },
        'notes': notes,
    }


def get_formal_validation_report(
    self,
    user_id: str,
    claim_type: Optional[str] = None,
    required_support_kinds: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Return a draft-generation-ready formal validation report by claim."""
    validation = self.get_claim_support_validation(
        user_id,
        claim_type=claim_type,
        required_support_kinds=required_support_kinds,
    )
    validation_claims = validation.get('claims', {}) if isinstance(validation, dict) else {}
    report_claims: Dict[str, Any] = {}
    formal_status_counts: Counter[str] = Counter()
    total_elements = 0
    total_predicates = 0
    total_proof_gaps = 0
    theorem_ready_count = 0
    support_quality_signal_counts: Counter[str] = Counter()
    primary_quality_signal_counts: Counter[str] = Counter()
    quality_follow_up_action_counts: Counter[str] = Counter()

    for current_claim, claim_validation in validation_claims.items():
        if not isinstance(claim_validation, dict):
            continue
        element_reports = [
            self._build_formal_validation_element_report(element)
            for element in claim_validation.get('elements', []) or []
            if isinstance(element, dict)
        ]
        claim_status_counts: Counter[str] = Counter()
        claim_predicate_count = 0
        claim_proof_gap_count = 0
        claim_theorem_ready_count = 0
        claim_support_quality_signal_counts: Counter[str] = Counter()
        claim_primary_quality_signal_counts: Counter[str] = Counter()
        claim_quality_follow_up_action_counts: Counter[str] = Counter()
        for element_report in element_reports:
            status = str(element_report.get('formal_status') or 'needs_review')
            claim_status_counts[status] += 1
            formal_status_counts[status] += 1
            claim_predicate_count += int(element_report.get('predicate_count', 0) or 0)
            claim_proof_gap_count += int(element_report.get('proof_gap_count', 0) or 0)
            if element_report.get('formalization_ready'):
                claim_theorem_ready_count += 1
            quality_summary = (
                element_report.get('support_quality_summary', {})
                if isinstance(element_report.get('support_quality_summary'), dict)
                else {}
            )
            raw_signal_counts = (
                quality_summary.get('quality_signal_counts', {})
                if isinstance(quality_summary.get('quality_signal_counts'), dict)
                else {}
            )
            for signal_type, signal_count in raw_signal_counts.items():
                normalized_signal = str(signal_type or '').strip()
                if not normalized_signal:
                    continue
                try:
                    normalized_count = int(signal_count or 0)
                except (TypeError, ValueError):
                    normalized_count = 0
                if normalized_count <= 0:
                    continue
                claim_support_quality_signal_counts[normalized_signal] += normalized_count
                support_quality_signal_counts[normalized_signal] += normalized_count
            primary_quality_signal = (
                element_report.get('primary_quality_signal')
                if isinstance(element_report.get('primary_quality_signal'), dict)
                else {}
            )
            primary_signal_type = str(primary_quality_signal.get('signal_type') or '').strip()
            if primary_signal_type:
                claim_primary_quality_signal_counts[primary_signal_type] += 1
                primary_quality_signal_counts[primary_signal_type] += 1
            follow_up_action = str(element_report.get('quality_follow_up_action') or '').strip()
            if follow_up_action:
                claim_quality_follow_up_action_counts[follow_up_action] += 1
                quality_follow_up_action_counts[follow_up_action] += 1

        total_elements += len(element_reports)
        total_predicates += claim_predicate_count
        total_proof_gaps += claim_proof_gap_count
        theorem_ready_count += claim_theorem_ready_count
        if claim_status_counts.get('contradicted', 0):
            formal_status = 'blocked'
        elif claim_status_counts.get('missing_premises', 0):
            formal_status = 'missing_premises'
        elif claim_status_counts.get('unprovable', 0) or claim_status_counts.get('invalid_ontology', 0):
            formal_status = 'needs_review'
        elif element_reports and claim_status_counts.get('passed', 0) == len(element_reports):
            formal_status = 'passed'
        else:
            formal_status = 'needs_review'

        report_claims[current_claim] = {
            'claim_type': current_claim,
            'validation_status': claim_validation.get('validation_status', ''),
            'formal_status': formal_status,
            'formal_status_counts': dict(sorted(claim_status_counts.items())),
            'element_count': len(element_reports),
            'predicate_count': claim_predicate_count,
            'proof_gap_count': claim_proof_gap_count,
            'formalization_ready_element_count': claim_theorem_ready_count,
            'theorem_export_ready': claim_theorem_ready_count > 0,
            'support_quality_summary': dict(claim_validation.get('support_quality_summary') or {}),
            'support_quality_signal_counts': dict(sorted(claim_support_quality_signal_counts.items())),
            'primary_quality_signal_counts': dict(sorted(claim_primary_quality_signal_counts.items())),
            'quality_follow_up_action_counts': dict(sorted(claim_quality_follow_up_action_counts.items())),
            'elements': element_reports,
        }

    if formal_status_counts.get('contradicted', 0):
        overall_status = 'blocked'
    elif formal_status_counts.get('missing_premises', 0):
        overall_status = 'missing_premises'
    elif formal_status_counts.get('unprovable', 0) or formal_status_counts.get('invalid_ontology', 0):
        overall_status = 'needs_review'
    elif total_elements and formal_status_counts.get('passed', 0) == total_elements:
        overall_status = 'passed'
    else:
        overall_status = 'needs_review' if total_elements else 'unavailable'

    return self._with_intake_summary_handoff({
        'available': True,
        'user_id': user_id,
        'claim_type': claim_type,
        'required_support_kinds': validation.get('required_support_kinds', required_support_kinds or ['evidence', 'authority'])
        if isinstance(validation, dict) else (required_support_kinds or ['evidence', 'authority']),
        'overall_status': overall_status,
        'claim_count': len(report_claims),
        'element_count': total_elements,
        'predicate_count': total_predicates,
        'proof_gap_count': total_proof_gaps,
        'formalization_ready_element_count': theorem_ready_count,
        'formal_status_counts': dict(sorted(formal_status_counts.items())),
        'support_quality_signal_counts': dict(sorted(support_quality_signal_counts.items())),
        'primary_quality_signal_counts': dict(sorted(primary_quality_signal_counts.items())),
        'quality_follow_up_action_counts': dict(sorted(quality_follow_up_action_counts.items())),
        'claims': report_claims,
    })


def get_element_proof_card(
    self,
    user_id: str,
    claim_type: str,
    *,
    claim_element_id: Optional[str] = None,
    claim_element_text: Optional[str] = None,
    coverage_status: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a proof card for a single claim element.

    The proof card includes:
    - ``proof_state`` — one of supported / partially_supported / missing /
      contradicted / uncertain / exception_barred / unvalidated
    - ``required_predicates`` — FOL/DCEC predicate names from the claim template
    - ``satisfied_predicates`` — predicates satisfied by confirmed facts
    - ``missing_predicates`` — required predicates not yet satisfied
    - ``supporting_facts`` — confirmed/unvalidated fact records from the ledger
    - ``contradiction_sources`` — contradiction dicts from check_contradictions
    - ``next_action`` — recommended operator action
    - ``explanation`` — concise human-readable explanation

    Degrades gracefully when logic tooling or DuckDB are unavailable.
    """
    from integrations.ipfs_datasets.logic import (
        map_claim_elements_to_predicates,
        prove_claim_elements,
        check_contradictions,
    )

    element_text = str(claim_element_text or claim_element_id or '')
    resolved_element_id = claim_element_id

    # Resolve element ID from text when not supplied
    if not resolved_element_id and claim_element_text:
        try:
            resolved = self.resolve_claim_element(
                user_id,
                claim_type,
                claim_element_text=claim_element_text,
            )
            resolved_element_id = resolved.get('claim_element_id', '')
        except Exception:
            pass

    # 1. Fetch the support ledger for this element
    ledger = self.get_element_support_ledger(
        user_id,
        claim_type,
        claim_element_id=resolved_element_id or None,
        claim_element_text=claim_element_text or None,
    )
    total_facts = int(ledger.get('total_facts') or 0)
    confirmed_count = int(ledger.get('confirmed_count') or 0)
    supporting_facts = list(ledger.get('facts', {}).values())

    # 2. Map element to predicates using the claim template
    element_dict = {
        'element_id': resolved_element_id or '',
        'element_text': element_text,
        'coverage_status': coverage_status or ledger.get('overall_status') or 'missing',
    }
    predicate_map = map_claim_elements_to_predicates(claim_type, [element_dict])
    predicates = list(predicate_map.get('predicates') or [])
    predicate = predicates[0] if predicates else element_dict

    # Extract template fields — when a FOL template exists use it directly as
    # the single required predicate; fall back to expected_predicate_types otherwise.
    fol_template = str(predicate.get('fol_template') or '')
    dcec_template = str(predicate.get('dcec_template') or '')
    grounded_facts = list(predicate.get('grounded_facts') or [])
    if fol_template:
        required_predicates: List[str] = [fol_template]
    else:
        required_predicates = [
            str(pt) for pt in (predicate.get('expected_predicate_types') or ['claim_element'])
        ]

    # 3. Run prove_claim_elements on this element's predicates
    prove_result: Dict[str, Any] = {}
    try:
        prove_result = prove_claim_elements(predicates)
    except Exception as exc:
        self.mediator.log('get_element_proof_card_prove_error', error=str(exc))

    # 4. Run check_contradictions against the element's predicate payload
    contradiction_result: Dict[str, Any] = {}
    try:
        contradiction_result = check_contradictions(predicates)
    except Exception as exc:
        self.mediator.log('get_element_proof_card_contradiction_error', error=str(exc))
    contradiction_sources = list(contradiction_result.get('contradictions') or [])

    # 5. Classify proof state
    proof_state = self._derive_element_proof_state(
        ledger, prove_result, contradiction_result, predicate
    )

    # 6. Derive satisfied vs. missing predicates.
    # An element is fully satisfied when the reasoner flagged it as provable
    # OR all its ledger facts are confirmed.  Otherwise all required predicates
    # are treated as missing to avoid misleading partial mappings.
    provable_element_ids = {
        str(p.get('claim_element_id') or '') for p in (prove_result.get('provable_elements') or [])
    }
    elem_id = resolved_element_id or ''
    is_fully_satisfied = (
        (elem_id and elem_id in provable_element_ids)
        or (confirmed_count > 0 and confirmed_count >= total_facts and total_facts > 0)
    )
    satisfied_predicates: List[str] = required_predicates if is_fully_satisfied else []
    missing_predicates: List[str] = [
        p for p in required_predicates if p not in satisfied_predicates
    ]

    # 7. Build explanation
    explanation = self._build_element_proof_explanation(
        element_text,
        proof_state,
        missing_predicates,
        contradiction_sources,
        confirmed_count if confirmed_count > 0 else total_facts,
    )

    next_action = self._PROOF_STATE_NEXT_ACTIONS.get(proof_state, 'validate_facts')

    return {
        'claim_type': claim_type,
        'claim_element_id': resolved_element_id or '',
        'claim_element_text': element_text,
        'proof_state': proof_state,
        'required_predicates': required_predicates,
        'satisfied_predicates': satisfied_predicates,
        'missing_predicates': missing_predicates,
        'supporting_facts': supporting_facts,
        'supporting_fact_count': total_facts,
        'confirmed_fact_count': confirmed_count,
        'contradiction_sources': contradiction_sources,
        'contradiction_count': len(contradiction_sources),
        'next_action': next_action,
        'explanation': explanation,
        'fol_template': fol_template,
        'dcec_template': dcec_template,
        'grounded_facts': grounded_facts,
        'template_matched': bool(predicate.get('template_matched')),
        'ledger_overall_status': ledger.get('overall_status', 'missing'),
        'proof_engine_status': str(prove_result.get('proof_status') or 'skipped'),
        'logic_available': True,
    }


def _build_retrieval_ranking_payload(
    self,
    chunk: Dict[str, Any],
    query_tokens: List[str],
    element_text: str,
) -> Dict[str, Any]:
    text = ' '.join([
        str(chunk.get('text') or chunk.get('chunk_text') or ''),
        str(chunk.get('label') or chunk.get('source_label') or ''),
        str(chunk.get('title') or ''),
    ]).lower()
    chunk_tokens = set(re.findall(r'[a-z0-9]+', text))
    q_tokens = set(str(t).lower() for t in query_tokens)
    element_tokens = set(re.findall(r'[a-z0-9]+', str(element_text or '').lower()))
    metadata = dict(chunk.get('metadata') or {})

    overlap = len(q_tokens & chunk_tokens)
    element_overlap = len(element_tokens & chunk_tokens)
    denom = max(1, len(q_tokens) + len(element_tokens) // 2)
    query_fit_score = (overlap + element_overlap * 0.5) / denom
    existing = float(chunk.get('score') or chunk.get('retrieval_score') or 0.0)
    base_score = max(existing, query_fit_score)

    source_kind = str(chunk.get('source_kind') or chunk.get('kind') or 'chunk').strip().lower()
    source_kind_weight_map = {
        'authority': 0.10,
        'statute': 0.12,
        'regulation': 0.11,
        'case_law': 0.09,
        'evidence': 0.08,
        'document': 0.07,
        'testimony': 0.06,
        'web_archive': 0.05,
        'web': 0.03,
    }
    authority_class = str(
        metadata.get('authority_class')
        or metadata.get('authority_family')
        or metadata.get('authority_type')
        or ''
    ).strip().lower()
    authority_class_weight = 0.0
    if authority_class in {'statute', 'regulation', 'primary', 'mandatory_authority'}:
        authority_class_weight = 0.08
    elif authority_class in {'case_law', 'binding_case', 'precedent'}:
        authority_class_weight = 0.06
    elif authority_class in {'guidance', 'secondary', 'persuasive_authority'}:
        authority_class_weight = 0.03

    source_quality = metadata.get('quality_score', metadata.get('data_quality_score', metadata.get('source_quality_score', 0.0)))
    try:
        source_quality_weight = max(0.0, min(1.0, float(source_quality or 0.0))) * 0.10
    except (TypeError, ValueError):
        source_quality_weight = 0.0
    quality_tier = str(metadata.get('quality_tier') or '').strip().lower()
    if quality_tier in {'high', 'strong', 'excellent', 'verified'}:
        source_quality_weight = max(source_quality_weight, 0.08)
    elif quality_tier in {'low', 'weak'}:
        source_quality_weight = min(source_quality_weight, 0.025)

    temporal_terms = {
        token for token in q_tokens
        if token.isdigit() or token in {'before', 'after', 'during', 'within', 'deadline', 'notice', 'date'}
    }
    temporal_text = ' '.join([
        text,
        str(metadata.get('effective_date') or ''),
        str(metadata.get('published_date') or ''),
        str(metadata.get('temporal_scope') or ''),
        str(metadata.get('date') or ''),
    ]).lower()
    temporal_overlap = len(temporal_terms & set(re.findall(r'[a-z0-9]+', temporal_text)))
    temporal_relevance_weight = min(0.08, temporal_overlap * 0.025)
    if re.search(r'\b(19|20)\d{2}\b', ' '.join(q_tokens)) and re.search(r'\b(19|20)\d{2}\b', temporal_text):
        temporal_relevance_weight = max(temporal_relevance_weight, 0.04)

    graph_signal_weight = 0.0
    graph_summary = metadata.get('graph_trace_summary', {}) if isinstance(metadata.get('graph_trace_summary'), dict) else {}
    support_quality = metadata.get('support_quality_summary', {}) if isinstance(metadata.get('support_quality_summary'), dict) else {}
    if graph_summary:
        graph_signal_weight += min(0.05, int(graph_summary.get('traced_link_count', 0) or graph_summary.get('graph_count', 0) or 1) * 0.02)
    quality_tier_signal = str(metadata.get('path_quality_tier') or support_quality.get('dominant_quality_tier') or '').strip().lower()
    if quality_tier_signal in {'strong_support', 'strong', 'high'}:
        graph_signal_weight += 0.06
    elif quality_tier_signal in {'moderate_support', 'moderate'}:
        graph_signal_weight += 0.03
    elif quality_tier_signal in {'weak_support', 'structurally_missing'}:
        graph_signal_weight -= 0.025
    graph_signal_weight = max(-0.025, min(0.10, graph_signal_weight))

    content_origin = str(metadata.get('content_origin') or '').strip().lower()
    artifact_family = str(metadata.get('artifact_family') or '').strip().lower()
    archive_signal_weight = 0.0
    if source_kind == 'web_archive' or content_origin == 'historical_archive_capture' or artifact_family == 'archived_web_page':
        archive_signal_weight = 0.06
    elif content_origin == 'live_web_capture':
        archive_signal_weight = 0.025

    factors = {
        'query_fit_score': round(query_fit_score, 6),
        'base_score': round(base_score, 6),
        'source_kind_weight': round(source_kind_weight_map.get(source_kind, 0.0), 6),
        'claim_element_fit_weight': round(min(0.14, element_overlap * 0.03), 6),
        'source_quality_weight': round(source_quality_weight, 6),
        'authority_class_weight': round(authority_class_weight, 6),
        'temporal_relevance_weight': round(temporal_relevance_weight, 6),
        'graph_signal_weight': round(graph_signal_weight, 6),
        'archive_signal_weight': round(archive_signal_weight, 6),
    }
    final_score = min(1.0, base_score + sum(
        value for key, value in factors.items()
        if key not in {'query_fit_score', 'base_score'}
    ))
    explanation_parts = []
    if overlap:
        explanation_parts.append(f'matched {overlap} query term(s)')
    if element_overlap:
        explanation_parts.append(f'matched {element_overlap} claim-element term(s)')
    for key in (
        'source_kind_weight',
        'source_quality_weight',
        'authority_class_weight',
        'temporal_relevance_weight',
        'graph_signal_weight',
        'archive_signal_weight',
    ):
        value = factors.get(key, 0.0)
        if value:
            explanation_parts.append(f'{key.replace("_", " ")} {value:+.2f}')
    return {
        'score': round(final_score, 4),
        'factors': factors,
        'matched_query_terms': sorted(q_tokens & chunk_tokens),
        'matched_element_terms': sorted(element_tokens & chunk_tokens),
        'explanation_parts': explanation_parts,
    }


def run_retrieval_session(
    self,
    user_id: str,
    claim_type: str,
    *,
    claim_element_id: str = '',
    claim_element_text: str = '',
    query_text: str = '',
    chunks: Optional[List[Dict[str, Any]]] = None,
    max_results: int = 20,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a retrieval session, score/rank provided chunks, and persist results.

    This is the main entry point for M4 retrieval.  It:
    1. Creates a stable session record.
    2. Scores each chunk against *query_text* and *claim_element_text*.
    3. Annotates duplicate-cluster hints.
    4. Generates a concise explanation for each ranked result.
    5. Persists all results for later replay or drilldown.

    Returns the session metadata and the ranked result list.
    """
    if not DUCKDB_AVAILABLE:
        return {
            'available': False,
            'error': 'duckdb unavailable',
            'session_id': '',
            'results': [],
            'result_count': 0,
        }
    session = self.create_retrieval_session(
        user_id,
        claim_type,
        claim_element_id=claim_element_id,
        claim_element_text=claim_element_text,
        query_text=query_text,
        retrieval_plane='unified',
        metadata=metadata,
    )
    if not session.get('created'):
        return {
            'available': False,
            'error': session.get('error', 'session creation failed'),
            'session_id': '',
            'results': [],
            'result_count': 0,
        }
    session_id = session['session_id']
    query_tokens = re.findall(r'[a-z0-9]+', str(query_text or '').lower())
    safe_chunks = list(chunks or [])[:max_results * 2]
    # Score and annotate
    scored: List[Dict[str, Any]] = []
    cluster_map: Dict[str, str] = {}
    for chunk in safe_chunks:
        normalized = self._normalize_chunk_for_indexing(chunk, 'chunk')
        if not normalized.get('source_ref') and not normalized.get('chunk_text'):
            continue
        ranking_payload = self._build_retrieval_ranking_payload(normalized, query_tokens, claim_element_text)
        score = ranking_payload['score']
        explanation = self._explain_retrieval_result(normalized, query_tokens, score, claim_element_text)
        cluster_id = self._make_duplicate_cluster_id(normalized['chunk_text'])
        is_representative = cluster_id not in cluster_map
        if is_representative:
            cluster_map[cluster_id] = normalized['source_ref']
        result_metadata = dict(normalized['metadata'])
        result_metadata.update({
            'retrieval_ranking_factors': ranking_payload['factors'],
            'retrieval_ranking_explanation': ranking_payload['explanation_parts'],
            'matched_query_terms': ranking_payload['matched_query_terms'],
            'matched_claim_element_terms': ranking_payload['matched_element_terms'],
        })
        scored.append({
            'source_kind': normalized['source_kind'],
            'source_ref': normalized['source_ref'],
            'source_label': normalized['source_label'],
            'chunk_text': normalized['chunk_text'],
            'retrieval_score': score,
            'confidence': normalized['confidence'],
            'explanation': explanation,
            'duplicate_cluster_id': cluster_id,
            'is_duplicate_representative': is_representative,
            'metadata': result_metadata,
        })
    # Rank by retrieval_score descending, representatives before duplicates
    scored.sort(key=lambda r: (-r['retrieval_score'], not r['is_duplicate_representative']))
    top_results = scored[:max_results]
    # Persist ranked results
    try:
        self._prepare_duckdb_path()
        conn = duckdb.connect(self.db_path)
        self._ensure_retrieval_schema(conn)
        now = datetime.now(timezone.utc).isoformat()
        for rank, result in enumerate(top_results):
            conn.execute(
                """
                INSERT INTO claim_retrieval_results
                    (session_id, user_id, claim_type, claim_element_id, rank,
                     source_kind, source_ref, source_label, chunk_text,
                     retrieval_score, confidence, explanation,
                     duplicate_cluster_id, is_duplicate_representative,
                     metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    session_id, user_id, claim_type, claim_element_id, rank,
                    result['source_kind'], result['source_ref'], result['source_label'],
                    result['chunk_text'], result['retrieval_score'], result['confidence'],
                    result['explanation'], result['duplicate_cluster_id'],
                    result['is_duplicate_representative'],
                    json.dumps(result['metadata']), now,
                ],
            )
        conn.execute(
            "UPDATE claim_retrieval_sessions SET result_count = ?, status = ?, updated_at = ? WHERE session_id = ?",
            [len(top_results), 'complete', now, session_id],
        )
        conn.close()
    except Exception as exc:
        self.mediator.log('run_retrieval_session_persist_error', error=str(exc))

    duplicate_count = sum(1 for r in top_results if not r['is_duplicate_representative'])
    cluster_ids = list({r['duplicate_cluster_id'] for r in top_results})
    return {
        'available': True,
        'session_id': session_id,
        'user_id': user_id,
        'claim_type': claim_type,
        'claim_element_id': claim_element_id,
        'claim_element_text': claim_element_text,
        'query_text': query_text,
        'status': 'complete',
        'result_count': len(top_results),
        'duplicate_count': duplicate_count,
        'duplicate_cluster_count': len(cluster_ids),
        'results': top_results,
    }
