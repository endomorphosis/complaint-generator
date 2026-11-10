"""Document-generation fallback delegated from AdversarialSession."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set

logger = logging.getLogger("adversarial_harness.session")


def _build_fallback_probe(
    self,
    seed_complaint: Dict[str, Any] | None = None,
    asked_question_counts: Dict[str, int] | None = None,
    asked_intent_counts: Dict[str, int] | None = None,
    need_timeline: bool = False,
    need_harm_remedy: bool = False,
    need_actor_decisionmaker: bool = False,
    need_causation: bool = False,
    need_documentary_evidence: bool = False,
    need_witness: bool = False,
    need_exact_dates: bool = False,
    need_staff_names_titles: bool = False,
    need_hearing_request_timing: bool = False,
    need_response_dates: bool = False,
    need_causation_sequence: bool = False,
    last_question_key: str | None = None,
    last_question_intent_key: str | None = None,
    recent_intent_keys: Set[str] | None = None,
    missing_anchor_sections: Set[str] | None = None,
) -> Dict[str, Any] | None:
    seed_complaint = seed_complaint or {}
    asked_question_counts = dict(asked_question_counts or {})
    asked_intent_counts = dict(asked_intent_counts or {})
    recent_intent_keys = set(recent_intent_keys or set())
    missing_anchor_sections = set(missing_anchor_sections or set())
    probe_candidates: List[tuple[str, str]] = []
    intake_prompt_candidates = self._extract_intake_prompt_candidates(seed_complaint)
    for probe_text, probe_type in intake_prompt_candidates:
        if probe_type == 'timeline' and not need_timeline:
            continue
        if probe_type == 'harm_remedy' and not need_harm_remedy:
            continue
        if probe_type == 'actors' and not need_actor_decisionmaker:
            continue
        if probe_type == 'causation' and not need_causation:
            continue
        if probe_type == 'documents' and not need_documentary_evidence:
            continue
        if probe_type == 'witnesses' and not need_witness:
            continue
        if probe_type == 'anchor_appeal_rights' and 'appeal_rights' not in missing_anchor_sections:
            continue
        if probe_type == 'anchor_grievance_hearing' and 'grievance_hearing' not in missing_anchor_sections:
            continue
        if probe_type == 'anchor_reasonable_accommodation' and 'reasonable_accommodation' not in missing_anchor_sections:
            continue
        if probe_type == 'anchor_adverse_action' and 'adverse_action' not in missing_anchor_sections:
            continue
        if probe_type == 'anchor_selection_criteria' and 'selection_criteria' not in missing_anchor_sections:
            continue
        probe_candidates.append((probe_text, probe_type))
    for section in sorted(missing_anchor_sections):
        probe = self._anchor_probe_map().get(section)
        if probe:
            probe_candidates.append(probe)
    if need_exact_dates:
        probe_candidates.append((
            "What exact dates or best month/year anchors do you have for each key event, including notices and decisions?",
            "exact_dates",
        ))
    if need_staff_names_titles:
        probe_candidates.append((
            "Which HACC staff members were involved at each step, and what were their names and titles or roles?",
            "staff_names_titles",
        ))
    if need_hearing_request_timing:
        probe_candidates.append((
            "When did you request a grievance hearing or appeal, how did you request it, and what was the timing relative to the adverse action?",
            "hearing_request_timing",
        ))
    if need_response_dates:
        probe_candidates.append((
            "What response dates did you receive for notices, hearing or appeal requests, and the final decision?",
            "response_dates",
        ))
    if need_actor_decisionmaker:
        probe_candidates.append((
            "For each adverse action or notice, who made or communicated it, what were their names and titles, and what exactly did they say or do?",
            "adverse_action_details",
        ))
    if need_harm_remedy:
        probe_candidates.append((
            "What concrete harms did this cause you, and what specific remedy are you requesting?",
            "harm_remedy",
        ))
    if need_timeline:
        probe_candidates.append((
            "What are the most precise dates or date ranges for each key event, starting with the first incident?",
            "timeline",
        ))
    if need_actor_decisionmaker:
        probe_candidates.append((
            "Who specifically made each decision or statement, what were their names and titles, and what exactly was said or done?",
            "actors",
        ))
    if need_causation:
        probe_candidates.append((
            "What protected activity happened first, what adverse action followed, who made each decision, and what facts show the adverse action happened because of that protected activity?",
            "causation",
        ))
    if need_causation_sequence:
        probe_candidates.append((
            "Please walk through the sequence step by step: protected activity, who learned about it, adverse action, and how timing or statements link them.",
            "causation_sequence",
        ))
    if need_documentary_evidence:
        chronology_priority_hints = self._extract_document_chronology_priority_hints(seed_complaint)
        if bool(chronology_priority_hints.get('needs_exhibit_grounding')):
            probe_candidates.append((
                "Which uploaded or uploadable documents should be treated as exhibits for each key event, and for each one what are the date, sender or source, subject or label, and the fact it proves?",
                "documents",
            ))
        else:
            probe_candidates.append((
                "Do you have any supporting records such as dated notices, emails, messages, letters, screenshots, or other written documents that match each key event?",
                "documents",
            ))
    if need_witness:
        probe_candidates.append((
            "Were there any witnesses who saw or heard these events, and how can they be identified?",
            "witnesses",
        ))

    if not probe_candidates:
        return None

    seen_question_keys = [k for k, count in asked_question_counts.items() if count > 0]
    for probe_text, probe_type in probe_candidates:
        key = self._question_dedupe_key(probe_text)
        intent_key = self._question_intent_key(probe_text)
        asked_count = asked_question_counts.get(key, 0)
        intent_count = asked_intent_counts.get(intent_key, 0)
        similarity_to_seen = 0.0
        if seen_question_keys:
            similarity_to_seen = max(
                self._question_similarity(probe_text, seen_key)
                for seen_key in seen_question_keys
            )
        if self._is_redundant_candidate(
            key=key,
            intent_key=intent_key,
            asked_count=asked_count,
            intent_count=intent_count,
            similarity_to_seen=similarity_to_seen,
            last_question_key=last_question_key,
            last_question_intent_key=last_question_intent_key,
            recent_intent_keys=recent_intent_keys,
        ):
            continue
        return {
            "question": probe_text,
            "type": probe_type,
            "question_objective": probe_type,
            "question_reason": "Harness fallback probe to cover a missing intake objective.",
            "source": "harness_fallback",
        }
    return None


def _compact_document_generation_result(result: Any) -> Dict[str, Any]:
    payload = result if isinstance(result, dict) else {}
    draft = payload.get('draft') if isinstance(payload.get('draft'), dict) else {}
    draft_readiness = payload.get('drafting_readiness') if isinstance(payload.get('drafting_readiness'), dict) else {}
    document_optimization = payload.get('document_optimization') if isinstance(payload.get('document_optimization'), dict) else {}
    workflow_guidance = payload.get('workflow_optimization_guidance') if isinstance(payload.get('workflow_optimization_guidance'), dict) else {}
    claims_for_relief = [
        claim
        for claim in list(draft.get('claims_for_relief') or [])
        if isinstance(claim, dict)
    ]
    requested_relief = [
        str(item).strip()
        for item in list(draft.get('requested_relief') or [])
        if str(item).strip()
    ]
    return {
        'status': 'completed' if payload else 'unavailable',
        'ready_to_file': bool(payload.get('ready_to_file', False)),
        'claim_count': len(claims_for_relief),
        'factual_allegation_count': len(list(draft.get('factual_allegations') or [])),
        'exhibit_count': len(list(draft.get('exhibits') or [])),
        'requested_relief_count': len(requested_relief),
        'draft_text_available': bool(str(draft.get('draft_text') or '').strip()),
        'document_optimization_available': bool(document_optimization),
        'document_optimization_method': str(document_optimization.get('optimization_method') or ''),
        'workflow_recommended_order': list(workflow_guidance.get('recommended_order') or []),
        'claim_types': [
            str(claim.get('claim_type') or '').strip()
            for claim in claims_for_relief
            if str(claim.get('claim_type') or '').strip()
        ],
        'count_titles': [
            str(claim.get('count_title') or '').strip()
            for claim in claims_for_relief
            if str(claim.get('count_title') or '').strip()
        ],
        'requested_relief_preview': requested_relief[:5],
        'blocker_codes': [
            str(item.get('code') or '')
            for item in list(draft_readiness.get('blockers') or [])
            if isinstance(item, dict) and str(item.get('code') or '').strip()
        ],
    }


def _build_document_generation_fallback(
    self,
    seed_complaint: Dict[str, Any],
    *,
    builder_error: str = '',
) -> Dict[str, Any]:
    key_facts = seed_complaint.get('key_facts') if isinstance(seed_complaint.get('key_facts'), dict) else {}
    uploaded_evidence_summary: Dict[str, Any] = {}
    claim_support_packet_summary: Dict[str, Any] = {}
    intake_case_file: Dict[str, Any] = {}
    try:
        from complaint_phases import ComplaintPhase
    except Exception:
        logger.warning(
            "Could not load complaint phase definitions for fallback document generation "
            "in adversarial session %s; continuing with seed and conversation data only",
            self.session_id,
            exc_info=True,
        )
    else:
        phase_manager = None
        get_phase_data = None
        try:
            phase_manager = getattr(self.mediator, 'phase_manager', None)
            get_phase_data = getattr(phase_manager, 'get_phase_data', None)
        except Exception:
            logger.warning(
                "Could not access the phase manager for fallback document generation "
                "in adversarial session %s; continuing with seed and conversation data only",
                self.session_id,
                exc_info=True,
            )

        def read_fallback_phase_data(phase: Any, key: str) -> Dict[str, Any]:
            try:
                value = get_phase_data(phase, key)
            except Exception:
                logger.warning(
                    "Could not read %s phase data for fallback document generation "
                    "in adversarial session %s; continuing without that input",
                    key,
                    self.session_id,
                    exc_info=True,
                )
                return {}
            if value is None:
                return {}
            if not isinstance(value, dict):
                logger.warning(
                    "Ignoring non-mapping %s phase data for fallback document generation "
                    "in adversarial session %s (received %s)",
                    key,
                    self.session_id,
                    type(value).__name__,
                )
                return {}
            return value

        if callable(get_phase_data):
            uploaded_evidence_summary = read_fallback_phase_data(
                ComplaintPhase.EVIDENCE,
                'uploaded_evidence_summary',
            )
            claim_support_packet_summary = read_fallback_phase_data(
                ComplaintPhase.EVIDENCE,
                'claim_support_packet_summary',
            )
            intake_case_file = read_fallback_phase_data(
                ComplaintPhase.INTAKE,
                'intake_case_file',
            )
        elif phase_manager is not None:
            logger.warning(
                "Could not read phase data for fallback document generation in adversarial "
                "session %s because the phase manager has no callable get_phase_data",
                self.session_id,
            )

    claim_type = str(seed_complaint.get('type') or 'civil_action').strip() or 'civil_action'
    claim_title = claim_type.replace('_', ' ').title()
    theory_labels = [
        str(item).replace('_', ' ').strip().title()
        for item in list(key_facts.get('theory_labels') or [])
        if str(item).strip()
    ]
    if theory_labels:
        claim_title = f"{claim_title} ({', '.join(theory_labels[:2])})"

    factual_allegations: List[str] = []
    initial_complaint = str(seed_complaint.get('summary') or '').strip()
    if initial_complaint:
        factual_allegations.append(initial_complaint)
    for message in list(self.conversation_history or []):
        if not isinstance(message, dict) or str(message.get('role') or '').strip().lower() != 'complainant':
            continue
        content = " ".join(str(message.get('content') or '').split()).strip()
        if content and content not in factual_allegations:
            factual_allegations.append(content)
    for fact in list(intake_case_file.get('canonical_facts') or []):
        if not isinstance(fact, dict):
            continue
        text = " ".join(
            str(
                fact.get('fact_text')
                or fact.get('text')
                or fact.get('summary')
                or fact.get('description')
                or ''
            ).split()
        ).strip()
        if text and text not in factual_allegations:
            factual_allegations.append(text)
    factual_allegations = factual_allegations[:8]

    exhibits: List[Dict[str, Any]] = []
    for index, item in enumerate(list(uploaded_evidence_summary.get('items') or []), start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get('filename') or item.get('description') or f'Uploaded Evidence {index}').strip()
        summary_parts = [
            str(item.get('description') or '').strip(),
            str(item.get('claim_element_text') or '').strip(),
        ]
        summary = " ".join(part for part in summary_parts if part).strip()
        exhibits.append(
            {
                'label': f'Exhibit {chr(64 + min(index, 26))}',
                'title': title or f'Uploaded Evidence {index}',
                'summary': summary,
                'claim_type': str(item.get('claim_type') or claim_type).strip(),
                'link': str(item.get('source_url') or item.get('cid') or '').strip(),
            }
        )
    requested_relief = self._default_relief_for_seed(seed_complaint)
    claims_for_relief = [
        {
            'claim_type': claim_type,
            'count_title': f'Count I - {claim_title}',
            'supporting_facts': factual_allegations[:4],
            'supporting_exhibits': [
                {
                    'label': exhibit.get('label'),
                    'title': exhibit.get('title'),
                    'link': exhibit.get('link'),
                }
                for exhibit in exhibits[:4]
            ],
            'support_summary': {
                'uploaded_evidence_count': int(uploaded_evidence_summary.get('count') or 0),
                'claim_support_claim_count': int(claim_support_packet_summary.get('claim_count') or 0),
            },
        }
    ]
    draft_text_lines = [
        'COMPLAINT',
        '',
        f'Claim: {claim_title}',
        '',
        'Factual Allegations:',
    ]
    draft_text_lines.extend(f'{idx}. {text}' for idx, text in enumerate(factual_allegations, start=1))
    draft_text_lines.append('')
    draft_text_lines.append('Requested Relief:')
    draft_text_lines.extend(f'- {text}' for text in requested_relief)
    if exhibits:
        draft_text_lines.append('')
        draft_text_lines.append('Exhibits:')
        draft_text_lines.extend(
            f"- {exhibit.get('label')}: {exhibit.get('title')}"
            for exhibit in exhibits
        )

    blocker_codes = ['document_builder_dependencies_unavailable'] if builder_error else ['formalization_support_incomplete']
    return {
        'ready_to_file': False,
        'draft': {
            'claims_for_relief': claims_for_relief,
            'factual_allegations': factual_allegations,
            'requested_relief': requested_relief,
            'exhibits': exhibits,
            'draft_text': "\n".join(line for line in draft_text_lines if line is not None).strip(),
        },
        'drafting_readiness': {
            'blockers': [{'code': code} for code in blocker_codes],
        },
        'workflow_optimization_guidance': {
            'recommended_order': ['intake_questioning', 'evidence_upload', 'graph_analysis', 'document_generation'],
        },
        'fallback_document_generation': True,
        'builder_error': builder_error,
    }


def _run_document_generation(self, seed_complaint: Dict[str, Any]) -> Dict[str, Any]:
    confirm = getattr(self.mediator, 'confirm_intake_summary', None)
    if callable(confirm):
        try:
            confirm(
                confirmation_note='Adversarial optimizer handoff to evidence and document generation.',
                confirmation_source='adversarial_optimizer',
            )
        except Exception:
            logger.warning(
                "Could not confirm the intake summary for adversarial session %s; "
                "continuing with the direct document-generation handoff",
                self.session_id,
                exc_info=True,
            )

    advance_to_evidence = getattr(self.mediator, 'advance_to_evidence_phase', None)
    if callable(advance_to_evidence):
        try:
            advance_to_evidence()
        except Exception:
            logger.warning(
                "Could not advance adversarial session %s to evidence; "
                "continuing with the direct document-generation handoff",
                self.session_id,
                exc_info=True,
            )

    advance_to_formalization = getattr(self.mediator, 'advance_to_formalization_phase', None)
    if callable(advance_to_formalization):
        try:
            advance_to_formalization()
        except Exception:
            logger.warning(
                "Could not advance adversarial session %s to formalization; "
                "continuing with the direct document-generation handoff",
                self.session_id,
                exc_info=True,
            )

    try:
        from complaint_phases import ComplaintPhase

        phase_manager = getattr(self.mediator, 'phase_manager', None)
        if phase_manager is not None:
            kg = phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
            dg = phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
            intake_case_file = phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {}
            legal_graph = phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, 'legal_graph')
            if (
                kg is not None
                and dg is not None
                and (legal_graph is None or not getattr(legal_graph, 'elements', {}))
            ):
                selector_builder = getattr(self.mediator, '_build_intake_selector_legal_graph', None)
                matcher = getattr(self.mediator, 'neurosymbolic_matcher', None)
                if callable(selector_builder) and matcher is not None:
                    legal_graph = selector_builder(intake_case_file)
                    phase_manager.current_phase = ComplaintPhase.FORMALIZATION
                    phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'legal_graph', legal_graph)
                    matching_results = matcher.match_claims_to_law(kg, dg, legal_graph)
                    phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'matching_results', matching_results)
                    phase_manager.update_phase_data(ComplaintPhase.FORMALIZATION, 'matching_complete', True)
    except Exception:
        logger.warning(
            "Could not prepare formalization graphs for adversarial session %s; "
            "continuing with the document-generation handoff",
            self.session_id,
            exc_info=True,
        )

    builder = getattr(self.mediator, 'build_formal_complaint_document_package', None)
    if not callable(builder):
        return self._build_document_generation_fallback(seed_complaint, builder_error='builder_unavailable')
    try:
        result = builder(
            user_id=self.session_id,
            enable_agentic_optimization=False,
            output_formats=['packet'],
        )
        compact = self._compact_document_generation_result(result)
        if (
            not compact.get('draft_text_available')
            and int(compact.get('claim_count') or 0) <= 0
            and int(compact.get('factual_allegation_count') or 0) <= 0
            and int(compact.get('exhibit_count') or 0) <= 0
        ):
            return self._build_document_generation_fallback(seed_complaint)
        return result
    except Exception as exc:
        logger.warning("Document-generation handoff failed during adversarial session %s: %s", self.session_id, exc)
        return self._build_document_generation_fallback(seed_complaint, builder_error=str(exc))
