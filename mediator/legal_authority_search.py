"""Search-program helpers delegated from the legal authority hooks.

The owner methods remain on their classes and forward here.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from mediator.legal_authority_hooks import (
    LEGAL_SOURCE_AVAILABILITY,
    LegalSearchProgram,
    _AGENCY_GUIDANCE_REFERENCE_CATALOG,
    _FEDERAL_STATUTE_REFERENCE_CATALOG,
    _OREGON_STATUTE_REFERENCE_CATALOG,
    _extract_cfr_sections,
    _merge_handoff_into_provenance_record,
    _merge_intake_summary_handoff_metadata,
    _query_terms,
    _strip_html,
    _text_overlap_score,
)


def build_search_programs(
    self,
    query: str,
    claim_type: Optional[str] = None,
    claim_elements: Optional[List[Dict[str, Any]]] = None,
    jurisdiction: Optional[str] = None,
    forum: Optional[str] = None,
    time_window: Optional[Dict[str, Any]] = None,
    defense_themes: Optional[List[str]] = None,
    authority_families: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Build claim-aware legal search programs for support, procedure, and adverse authority.

    The current output is intentionally deterministic and mediator-friendly so it can
    be persisted or attached to follow-up tasks before richer search-program logic lands.
    """
    base_query = str(query or "").strip()
    if not base_query:
        return []

    normalized_claim_type = str(claim_type or "").strip()
    normalized_jurisdiction = str(jurisdiction or "").strip()
    normalized_forum = str(forum or "").strip()
    generated_terms = self._generate_search_terms(base_query)
    normalized_time_window = time_window if isinstance(time_window, dict) else {}
    time_window_start = str(
        normalized_time_window.get('start')
        or normalized_time_window.get('time_window_start')
        or normalized_time_window.get('from')
        or ''
    ).strip()
    time_window_end = str(
        normalized_time_window.get('end')
        or normalized_time_window.get('time_window_end')
        or normalized_time_window.get('to')
        or ''
    ).strip()
    time_window_terms = [
        str(term).strip()
        for term in (normalized_time_window.get('query_terms') or [])
        if str(term).strip()
    ]
    normalized_defense_themes = list(dict.fromkeys([
        str(theme).strip()
        for theme in (defense_themes or [])
        if str(theme).strip()
    ]))
    requested_authority_families = list(dict.fromkeys([
        str(family).strip()
        for family in (authority_families or [])
        if str(family).strip()
    ]))

    normalized_elements: List[Dict[str, str]] = []
    for element in claim_elements or []:
        if not isinstance(element, dict):
            continue
        element_text = str(
            element.get('claim_element_text')
            or element.get('element_text')
            or element.get('claim_element')
            or ''
        ).strip()
        if not element_text:
            continue
        normalized_elements.append(
            {
                'claim_element_id': str(element.get('claim_element_id') or element.get('element_id') or '').strip(),
                'claim_element_text': element_text,
            }
        )

    if not normalized_elements:
        normalized_elements = [
            {
                'claim_element_id': '',
                'claim_element_text': normalized_claim_type or base_query,
            }
        ]

    program_templates = [
        {
            'program_type': 'element_definition_search',
            'authority_intent': 'support',
            'authority_families': ['statute', 'regulation', 'administrative_rule'],
            'query_suffix': 'element definition statute regulation rule',
            'defense_theme': 'element_standard',
        },
        {
            'program_type': 'fact_pattern_search',
            'authority_intent': 'support',
            'authority_families': ['case_law', 'agency_guidance'],
            'query_suffix': 'fact pattern application authority',
            'defense_theme': 'fact_application',
        },
        {
            'program_type': 'procedural_search',
            'authority_intent': 'procedural',
            'authority_families': ['regulation', 'administrative_rule', 'agency_guidance'],
            'query_suffix': 'timeliness exhaustion venue notice procedure',
            'defense_theme': 'procedural_prerequisite',
        },
        {
            'program_type': 'adverse_authority_search',
            'authority_intent': 'oppose',
            'authority_families': ['case_law', 'statute', 'regulation'],
            'query_suffix': 'adverse authority defense exception limitation',
            'defense_theme': 'defense_or_exception',
        },
        {
            'program_type': 'treatment_check_search',
            'authority_intent': 'confirm_good_law',
            'authority_families': ['case_law', 'administrative_rule', 'agency_guidance'],
            'query_suffix': 'citation history later treatment good law',
            'defense_theme': 'authority_treatment',
        },
    ]

    programs: List[Dict[str, Any]] = []
    for element in normalized_elements:
        element_text = element['claim_element_text']
        for template in program_templates:
            template_families = list(template['authority_families'])
            if requested_authority_families:
                filtered_families = [
                    family for family in template_families
                    if family in requested_authority_families
                ]
                if filtered_families:
                    template_families = filtered_families
            search_terms = [
                term
                for term in [element_text, normalized_claim_type, *generated_terms]
                if term
            ]
            search_terms.extend(time_window_terms)
            program = LegalSearchProgram(
                program_type=template['program_type'],
                claim_type=normalized_claim_type or base_query,
                authority_intent=template['authority_intent'],
                query_text=' '.join(
                    part
                    for part in [
                        base_query,
                        element_text,
                        normalized_jurisdiction,
                        template['query_suffix'],
                        ' '.join(time_window_terms[:3]),
                    ]
                    if part
                ),
                claim_element_id=element['claim_element_id'],
                claim_element_text=element_text,
                jurisdiction=normalized_jurisdiction,
                forum=normalized_forum,
                time_window_start=time_window_start,
                time_window_end=time_window_end,
                authority_families=template_families,
                search_terms=search_terms[:6],
                metadata={
                    'base_query': base_query,
                    'claim_type': normalized_claim_type,
                    'jurisdiction': normalized_jurisdiction,
                    'forum': normalized_forum,
                    'time_window': dict(normalized_time_window),
                    'time_window_start': time_window_start,
                    'time_window_end': time_window_end,
                    'time_window_terms': time_window_terms[:8],
                    'defense_theme': template['defense_theme'],
                    'defense_themes': normalized_defense_themes,
                    'authority_family_focus': template_families,
                },
            )
            programs.append(program.as_dict())

    self.mediator.log(
        'legal_authority_search_programs_built',
        query=base_query,
        claim_type=normalized_claim_type,
        claim_element_count=len(normalized_elements),
        program_count=len(programs),
    )
    return programs

def search_all_sources(self, query: str, claim_type: Optional[str] = None,
                      jurisdiction: Optional[str] = None,
                      authority_families: Optional[List[str]] = None,
                      **lookup_options: Any) -> Dict[str, Any]:
    """Actual mediator discovery path, offline unless explicitly configured.

    Retrieved candidates never choose a jurisdiction or applicability. Cases,
    dockets and web archival discovery require their separate explicit APIs.
    """
    from integrations.ipfs_datasets.legal import resolve_explicit_jurisdiction
    resolved = resolve_explicit_jurisdiction(jurisdiction)
    families = set(authority_families or ('statute', 'regulation', 'administrative_rule', 'court_rule'))
    results = {key: [] for key in ('statutes', 'state_statutes', 'regulations',
        'administrative_rules', 'court_rules', 'case_law', 'web_archives')}
    diagnostics = {'source_availability': dict(LEGAL_SOURCE_AVAILABILITY)}
    if resolved != 'unknown':
        selection = [('statutes', 'us_code', 'statute' in families and resolved == 'federal'),
            ('state_statutes', 'state_statute', 'statute' in families and resolved != 'federal'),
            ('regulations', 'federal_register', 'regulation' in families and resolved == 'federal'),
            ('administrative_rules', 'state_administrative_rule',
                'administrative_rule' in families and resolved != 'federal'),
            ('court_rules', 'court_rule', 'court_rule' in families)]
        for bucket, family, enabled in selection:
            if not enabled: continue
            options = dict(lookup_options)
            options.setdefault('retrieval_mode', 'offline')
            options.update(jurisdiction=resolved, state=None if resolved == 'federal' else resolved)
            if family == 'court_rule':
                options.setdefault('court_jurisdiction', 'federal' if resolved == 'federal' else 'state')
            envelope = self.lookup_bounded_corpus(source_family=family, query=query,
                max_results=5, **options)
            results[bucket] = list(envelope.get('results') or [])
            diagnostics[bucket] = {key: envelope.get(key) for key in
                ('status', 'capability', 'error_code', 'retrieval_mode', 'applicability')}
    results['search_diagnostics'] = diagnostics
    self.mediator.log('legal_authority_search_all', total_found=sum(len(v) for v in results.values() if isinstance(v,list)),
        context_status='unknown' if resolved == 'unknown' else 'explicit')
    return results

def _search_courtlistener_fallback(self, query: str, jurisdiction: Optional[str] = None,
                                   *, max_results: int = 10) -> List[Dict[str, Any]]:
    normalized: List[tuple[bool, Dict[str, Any]]] = []
    jurisdiction_text = str(jurisdiction or '').lower().strip()
    query_tokens = set(_query_terms(query))
    simplified_parts: List[str] = []
    if 'housing' in query_tokens and 'authority' in query_tokens:
        simplified_parts.append('housing authority')
    if 'voucher' in query_tokens:
        simplified_parts.append('voucher')
    if 'termination' in query_tokens:
        simplified_parts.append('termination')
    if 'family' in query_tokens and 'obligations' in query_tokens:
        simplified_parts.append('family obligations')
    if 'informal' in query_tokens or 'hearing' in query_tokens or 'review' in query_tokens:
        simplified_parts.append('informal hearing')
    if 'reasonable' in query_tokens or 'accommodation' in query_tokens:
        simplified_parts.append('reasonable accommodation')
    if 'retaliation' in query_tokens:
        simplified_parts.append('retaliation')
    search_queries = [query]
    simplified_query = ' '.join(simplified_parts).strip()
    if simplified_query and simplified_query.lower() != query.lower():
        search_queries.append(simplified_query)
    if 'housing authority' in simplified_query and 'voucher' in query_tokens:
        search_queries.append('housing authority voucher termination')

    for search_query in search_queries[:3]:
        params: Dict[str, Any] = {
            'q': search_query,
            'page_size': max_results,
            'type': 'o',
        }
        try:
            payload = self._http_get_json(
                'https://www.courtlistener.com/api/rest/v4/search/',
                params=params,
            )
        except Exception as exc:
            self.mediator.log(
                'legal_authority_search_error',
                search_type='courtlistener_fallback',
                query=search_query,
                error=str(exc),
            )
            continue

        items = payload.get('results')
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            row = self._normalize_courtlistener_result(item, query=query)
            court_blob = ' '.join(
                [
                    str(item.get('court') or ''),
                    str(item.get('court_citation_string') or ''),
                    str(item.get('court_id') or ''),
                ]
            ).lower()
            if _text_overlap_score(query, row.get('title', ''), row.get('content', ''), row.get('citation', '')) < 0.12:
                continue
            jurisdiction_match = (
                not jurisdiction_text
                or jurisdiction_text in court_blob
                or jurisdiction_text in row['content'].lower()
                or (
                    jurisdiction_text in {'or', 'oregon'}
                    and ('oregon' in court_blob or 'or.' in court_blob)
                )
                or (
                    jurisdiction_text in {'9th', 'ninth circuit'}
                    and ('9th' in court_blob or 'ninth' in court_blob)
                )
            )
            normalized.append((jurisdiction_match, row))
    normalized.sort(
        key=lambda item: (
            1 if item[0] else 0,
            float(item[1].get('relevance_score') or 0.0),
        ),
        reverse=True,
    )
    return self._dedupe_authority_rows([row for _, row in normalized], max_results=max_results)

def _normalize_courtlistener_result(self, item: Dict[str, Any], *, query: str) -> Dict[str, Any]:
    citations = item.get('citation')
    citation_text = ''
    if isinstance(citations, list) and citations:
        first = citations[0]
        if isinstance(first, dict):
            citation_text = str(first.get('cite') or first.get('volume') or '').strip()
        else:
            citation_text = str(first).strip()
    if not citation_text:
        citation_text = str(item.get('caseName') or item.get('caseNameFull') or item.get('docketNumber') or '').strip()
    absolute_url = str(item.get('absolute_url') or '').strip()
    if absolute_url and absolute_url.startswith('/'):
        absolute_url = f"https://www.courtlistener.com{absolute_url}"
    title = str(item.get('caseNameFull') or item.get('caseName') or citation_text or 'Case law result').strip()
    court = str(item.get('court') or item.get('court_citation_string') or '').strip()
    date_filed = str(item.get('dateFiled') or '').strip()
    content = ' '.join(part for part in [court, date_filed, str(item.get('snippet') or '').strip()] if part).strip()
    score = 0.0
    meta = item.get('meta') if isinstance(item.get('meta'), dict) else {}
    meta_score = meta.get('score') if isinstance(meta.get('score'), dict) else {}
    try:
        score = float(meta_score.get('bm25') or 0.0)
    except Exception:
        score = 0.0
    if score <= 0:
        score = max(_text_overlap_score(query, title, content, citation_text), 0.25)
    return {
        'type': 'case_law',
        'source': 'courtlistener',
        'citation': citation_text or title,
        'title': title,
        'content': content,
        'url': absolute_url,
        'metadata': {
            'court': court,
            'court_id': item.get('court_id'),
            'date_filed': date_filed,
            'cluster_id': item.get('cluster_id'),
            'search_backend': 'courtlistener_api',
        },
        'relevance_score': score,
    }

def _search_oregon_statutes_fallback(self, query: str, *, max_results: int = 10) -> List[Dict[str, Any]]:
    query_lower = str(query or '').lower()
    if 'oregon' not in query_lower and 'ors' not in query_lower and 'clackamas' not in query_lower:
        return []
    rows: List[Dict[str, Any]] = []
    for item in _OREGON_STATUTE_REFERENCE_CATALOG:
        overlap = _text_overlap_score(query, item.get('citation', ''), item.get('title', ''), ' '.join(item.get('topics') or []))
        if overlap < 0.12:
            continue
        content = ''
        try:
            text = self._http_get_text(item['url'])
            title_match = re.search(r'<title>(.*?)</title>', text, flags=re.IGNORECASE | re.DOTALL)
            meta_match = re.search(r'<meta[^>]+name=[\'"]description[\'"][^>]+content=[\'"]([^\'"]+)[\'"]', text, flags=re.IGNORECASE)
            title = _strip_html(title_match.group(1)) if title_match else str(item.get('title') or '')
            content = _strip_html(meta_match.group(1)) if meta_match else ''
        except Exception as exc:
            self.mediator.log(
                'legal_authority_search_error',
                search_type='oregon_statute_fallback',
                query=query,
                citation=item.get('citation'),
                error=str(exc),
            )
            title = str(item.get('title') or '')
        rows.append(
            {
                'type': 'state_statute',
                'source': 'oregon_public_law' if 'public.law' in item['url'] else 'oregon_legislature',
                'citation': str(item.get('citation') or ''),
                'title': title,
                'content': content,
                'url': item['url'],
                'metadata': {
                    'topics': list(item.get('topics') or []),
                    'search_backend': 'oregon_statute_fallback',
                },
                'relevance_score': max(overlap, 0.2),
            }
        )
    rows.sort(key=lambda item: float(item.get('relevance_score') or 0.0), reverse=True)
    return self._dedupe_authority_rows(rows, max_results=max_results)

def _search_federal_statutes_fallback(self, query: str, *, max_results: int = 10) -> List[Dict[str, Any]]:
    query_lower = str(query or '').lower()
    if not any(token in query_lower for token in ('fair housing', 'reasonable accommodation', 'voucher', 'section 8', 'housing', 'termination', 'hearing', 'grievance', '1437', '3604')):
        return []
    rows: List[Dict[str, Any]] = []
    for item in _FEDERAL_STATUTE_REFERENCE_CATALOG:
        overlap = _text_overlap_score(query, item.get('citation', ''), item.get('title', ''), ' '.join(item.get('topics') or []))
        if overlap < 0.12:
            continue
        content = ''
        title = str(item.get('title') or '')
        try:
            text = self._http_get_text(item['url'])
            title_match = re.search(r'<title>(.*?)</title>', text, flags=re.IGNORECASE | re.DOTALL)
            if title_match:
                title = _strip_html(title_match.group(1))
        except Exception as exc:
            self.mediator.log(
                'legal_authority_search_error',
                search_type='federal_statute_fallback',
                query=query,
                citation=item.get('citation'),
                error=str(exc),
            )
        rows.append(
            {
                'type': 'statute',
                'source': 'uscode_house',
                'citation': str(item.get('citation') or ''),
                'title': title,
                'content': content,
                'url': item['url'],
                'metadata': {
                    'topics': list(item.get('topics') or []),
                    'search_backend': 'federal_statute_fallback',
                },
                'relevance_score': max(overlap, 0.2),
            }
        )
    rows.sort(key=lambda item: float(item.get('relevance_score') or 0.0), reverse=True)
    return self._dedupe_authority_rows(rows, max_results=max_results)

def _search_ecfr_fallback(self, query: str, *, max_results: int = 10) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    search_queries = _extract_cfr_sections(query) or [query]
    if query not in search_queries:
        search_queries.append(query)
    for search_query in search_queries[:3]:
        try:
            payload = self._http_get_json(
                'https://www.ecfr.gov/api/search/v1/results',
                params={
                    'query': search_query,
                    'per_page': max_results,
                    'order': 'relevance',
                },
            )
        except Exception as exc:
            self.mediator.log(
                'legal_authority_search_error',
                search_type='ecfr_fallback',
                query=search_query,
                error=str(exc),
            )
            continue

        items = payload.get('results')
        if not isinstance(items, list):
            continue
        rows.extend(
            self._normalize_ecfr_result(item, query=query)
            for item in items
            if isinstance(item, dict)
        )
    rows = [row for row in rows if _text_overlap_score(query, row.get('title', ''), row.get('content', ''), row.get('citation', '')) >= 0.18]
    return self._dedupe_authority_rows(sorted(rows, key=lambda item: float(item.get('relevance_score') or 0.0), reverse=True), max_results=max_results)

def _search_agency_guidance_fallback(self, domain: str, query: Optional[str] = None,
                                     *, max_results: int = 20) -> List[Dict[str, Any]]:
    domain_text = str(domain or '').strip().lower()
    query_text = str(query or '').strip()
    rows: List[Dict[str, Any]] = []
    for item in _AGENCY_GUIDANCE_REFERENCE_CATALOG:
        if str(item.get('domain') or '').strip().lower() != domain_text:
            continue
        overlap = _text_overlap_score(
            query_text,
            item.get('title', ''),
            item.get('summary', ''),
            ' '.join(item.get('topics') or []),
        ) if query_text else 0.25
        if query_text and overlap < 0.10:
            continue
        rows.append(
            {
                'type': 'agency_guidance',
                'source': str(item.get('source') or 'agency_guidance_fallback'),
                'citation': str(item.get('title') or ''),
                'title': str(item.get('title') or ''),
                'content': str(item.get('summary') or ''),
                'url': str(item.get('url') or ''),
                'metadata': {
                    'domain': domain_text,
                    'topics': list(item.get('topics') or []),
                    'search_backend': 'agency_guidance_fallback',
                },
                'relevance_score': max(overlap, 0.2),
            }
        )
    rows.sort(key=lambda item: float(item.get('relevance_score') or 0.0), reverse=True)
    return self._dedupe_authority_rows(rows, max_results=max_results)

def _collect_search_diagnostics(
    self,
    *,
    query: str,
    state: Optional[str],
) -> Dict[str, Any]:
    diagnostics: Dict[str, Any] = {
        'source_availability': dict(LEGAL_SOURCE_AVAILABILITY),
    }

    # Default Mediator list-returning calls publish only this query's
    # actual bounded outcomes, never stale module-global legacy diagnostics.
    if getattr(self, '_bounded_diagnostic_query', None) == query:
        diagnostics.update(getattr(self, '_bounded_diagnostics', {}))

    return diagnostics

def _build_search_program_records(
    self,
    authority_id: int,
    authority_data: Dict[str, Any],
    provenance,
    claim_type: Optional[str],
) -> List[LegalSearchProgram]:
    program_records: List[LegalSearchProgram] = []
    for program in self._normalize_search_programs(authority_data):
        program_type = str(program.get('program_type') or '').strip()
        query_text = str(program.get('query_text') or '').strip()
        if not program_type or not query_text:
            continue
        metadata = _merge_intake_summary_handoff_metadata(
            {
                **(program.get('metadata', {}) if isinstance(program.get('metadata'), dict) else {}),
                'authority_id': authority_id,
                'authority_citation': str(authority_data.get('citation') or ''),
                'authority_title': str(authority_data.get('title') or ''),
                'authority_source': str(authority_data.get('source') or ''),
                'authority_type': str(authority_data.get('type') or ''),
            },
            self.mediator,
        )
        program_records.append(
            LegalSearchProgram(
                program_id=str(program.get('program_id') or ''),
                program_type=program_type,
                claim_type=str(program.get('claim_type') or claim_type or ''),
                authority_intent=str(program.get('authority_intent') or ''),
                query_text=query_text,
                claim_element_id=str(program.get('claim_element_id') or ''),
                claim_element_text=str(program.get('claim_element_text') or ''),
                jurisdiction=str(program.get('jurisdiction') or getattr(provenance, 'jurisdiction', '') or ''),
                forum=str(program.get('forum') or ''),
                authority_families=list(program.get('authority_families') or []),
                search_terms=list(program.get('search_terms') or []),
                metadata=metadata,
                provenance=_merge_handoff_into_provenance_record(provenance, self.mediator),
            )
        )
    return program_records

def _normalize_search_programs(self, authority_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_programs = authority_data.get('search_programs')
    if raw_programs is None:
        metadata = authority_data.get('metadata', {}) if isinstance(authority_data.get('metadata'), dict) else {}
        raw_programs = metadata.get('search_programs')

    if isinstance(raw_programs, dict):
        raw_programs = [raw_programs]
    if not isinstance(raw_programs, list):
        return []

    normalized_programs: List[Dict[str, Any]] = []
    for program in raw_programs:
        if not isinstance(program, dict):
            continue
        normalized_programs.append(
            {
                'program_id': str(program.get('program_id') or ''),
                'program_type': str(program.get('program_type') or ''),
                'claim_type': str(program.get('claim_type') or ''),
                'authority_intent': str(program.get('authority_intent') or ''),
                'query_text': str(program.get('query_text') or ''),
                'claim_element_id': str(program.get('claim_element_id') or ''),
                'claim_element_text': str(program.get('claim_element_text') or ''),
                'jurisdiction': str(program.get('jurisdiction') or ''),
                'forum': str(program.get('forum') or ''),
                'authority_families': list(program.get('authority_families', []) or []),
                'search_terms': list(program.get('search_terms', []) or []),
                'metadata': dict(program.get('metadata', {}) or {}),
                'provenance': dict(program.get('provenance', {}) or {}),
            }
        )
    return normalized_programs

def _build_search_program_summary(self, search_programs: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_type: Dict[str, int] = {}
    by_intent: Dict[str, int] = {}
    claim_element_ids = set()
    for record in search_programs:
        program_type = str(record.get('program_type') or '')
        if program_type:
            by_type[program_type] = by_type.get(program_type, 0) + 1
        authority_intent = str(record.get('authority_intent') or '')
        if authority_intent:
            by_intent[authority_intent] = by_intent.get(authority_intent, 0) + 1
        claim_element_id = str(record.get('claim_element_id') or '')
        if claim_element_id:
            claim_element_ids.add(claim_element_id)
    return {
        'record_count': len(search_programs),
        'by_type': by_type,
        'by_intent': by_intent,
        'claim_element_count': len(claim_element_ids),
    }
