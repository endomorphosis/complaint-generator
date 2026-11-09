"""Binding and review-question methods delegated from ComplaintDenoiser."""

from __future__ import annotations

from complaint_phases.denoiser import (
    build_claim_element_question_intent,
    build_claim_element_question_text,
    normalize_claim_type,
)


def _build_claim_element_questions(
    self,
    intake_case_file: Optional[Dict[str, Any]],
    max_questions: int,
) -> List[Dict[str, Any]]:
    """Build questions from missing registry-backed claim elements in the intake case file."""
    if not isinstance(intake_case_file, dict):
        return []

    questions: List[Dict[str, Any]] = []
    seen_keys: Set[str] = set()
    exhibit_ready_documents = self._needs_exhibit_ready_document_questions()
    candidate_claims = intake_case_file.get('candidate_claims', [])
    if not isinstance(candidate_claims, list):
        return []

    def _expected_modalities(evidence_classes: List[str]) -> List[str]:
        values = [str(item or '').strip().lower() for item in evidence_classes if str(item or '').strip()]
        modalities: List[str] = []
        if any(token in values for token in ('policy', 'handbook')):
            modalities.append('policy_document')
        if any(
            token in values
            for token in (
                'lease', 'denial_notice', 'termination_notice', 'eviction_notice', 'application_record',
                'inspection_record', 'maintenance_record', 'rent_record', 'personnel_record',
            )
        ):
            modalities.append('file_evidence')
        if any(token in values for token in ('email', 'text_message', 'landlord_message', 'denial_message')):
            if 'file_evidence' not in modalities:
                modalities.append('file_evidence')
        return modalities

    def _targets_for_element(element_id: str, modalities: List[str]) -> List[str]:
        normalized_element = str(element_id or '').strip().lower()
        targets: List[str] = ['actor_name', 'actor_role']
        element_target_map = {
            'protected_trait': ['harm_type'],
            'housing_context': ['actor_name', 'actor_role', 'decision_maker'],
            'employment_relationship': ['actor_name', 'actor_role', 'decision_maker'],
            'adverse_action': ['adverse_action', 'exact_dates', 'event_order'],
            'discriminatory_motive': ['causation_link', 'event_order'],
            'causation': ['protected_activity', 'adverse_action', 'causation_link', 'exact_dates', 'event_order'],
        }
        targets.extend(element_target_map.get(normalized_element, []))
        if 'policy_document' in modalities:
            targets.extend(['document_type', 'document_owner'])
        if 'file_evidence' in modalities:
            targets.extend(['document_type', 'document_date', 'document_owner'])
        deduped: List[str] = []
        for item in targets:
            if item and item not in deduped:
                deduped.append(item)
        return deduped

    def _patchability_for_element(element_id: str, modalities: List[str]) -> List[str]:
        normalized_element = str(element_id or '').strip().lower()
        markers = ['claim_element_patch_anchor', 'support_patch_anchor']
        if normalized_element in {'housing_context', 'employment_relationship'}:
            markers.append('actor_link_patch_anchor')
        if normalized_element in {'adverse_action', 'causation'}:
            markers.append('chronology_patch_anchor')
        if 'policy_document' in modalities:
            markers.append('policy_document_patch_anchor')
        if 'file_evidence' in modalities:
            markers.append('documentary_artifact_patch_anchor')
        deduped: List[str] = []
        for item in markers:
            if item and item not in deduped:
                deduped.append(item)
        return deduped

    for claim in candidate_claims:
        if not isinstance(claim, dict):
            continue
        claim_type = normalize_claim_type(str(claim.get('claim_type') or '').strip())
        claim_label = str(claim.get('label') or claim_type or 'this claim').strip()
        weak_claim_focus = claim_type in {'housing_discrimination', 'hacc_research_engine'}
        for element in claim.get('required_elements', []) or []:
            if not isinstance(element, dict):
                continue
            element_status = str(element.get('status') or '').strip().lower()
            if element_status in {'present', 'satisfied', 'complete'}:
                continue
            element_id = str(element.get('element_id') or '').strip()
            element_label = str(element.get('label') or element_id or 'this missing element').strip()
            question_key = f"{claim_type}:{element_id}:{element_label}".lower()
            if question_key in seen_keys:
                continue
            seen_keys.add(question_key)
            evidence_classes = list(element.get('evidence_classes', []) or [])
            actor_roles = list(element.get('actor_roles', []) or [])
            expected_modalities = _expected_modalities(evidence_classes)
            extraction_targets = _targets_for_element(element_id, expected_modalities)
            patchability_markers = _patchability_for_element(element_id, expected_modalities)
            gap_id = f"{claim_type}:{element_id}".lower()
            question_intent = build_claim_element_question_intent(
                claim_type,
                claim_label,
                {
                    'element_id': element_id,
                    'label': element_label,
                    'blocking': bool(element.get('blocking', False)),
                    'actor_roles': actor_roles,
                    'evidence_classes': evidence_classes,
                },
            )
            question_text = build_claim_element_question_text(
                claim_type,
                claim_label,
                element_id,
                element_label,
            )
            if exhibit_ready_documents and (
                'policy_document' in expected_modalities or 'file_evidence' in expected_modalities
            ):
                question_text = self._build_exhibit_ready_document_prompt(
                    claim_label=claim_label,
                    include_policy_document='policy_document' in expected_modalities,
                    include_file_evidence='file_evidence' in expected_modalities,
                    base_question=question_text,
                )
            elif 'policy_document' in expected_modalities and 'file_evidence' in expected_modalities:
                question_text = (
                    f"{question_text} If available, identify one policy document and one file record "
                    "(notice, lease, email, or upload) with date and sender."
                )
            elif 'policy_document' in expected_modalities:
                question_text = (
                    f"{question_text} If available, identify the policy document (name/section) and who issued it."
                )
            elif 'file_evidence' in expected_modalities:
                question_text = (
                    f"{question_text} If available, identify one file record (notice, lease, email, or upload) with date and sender."
                )
            if not self._already_asked(question_text):
                questions.append(self._question_candidate(
                    source='intake_claim_element_gap',
                    question_type='requirement',
                    question_text=question_text,
                    context={
                        'claim_type': claim_type,
                        'claim_name': claim_label,
                        'requirement_id': element_id,
                        'requirement_name': element_label,
                        'target_element_id': element_id,
                        'gap_id': gap_id,
                        'gap_type': 'missing_claim_element',
                        'requirement_key': element_id,
                        'actor_roles': actor_roles,
                        'evidence_classes': evidence_classes,
                        'expected_evidence_modalities': expected_modalities,
                        'deterministic_update_key': gap_id,
                        'workflow_phase': 'graph_analysis' if (bool(element.get('blocking', False)) or weak_claim_focus) else 'intake_questioning',
                        'recommended_resolution_lane': 'structured_requirement_capture',
                        'extraction_targets': extraction_targets,
                        'patchability_markers': patchability_markers,
                    },
                    priority='high' if (bool(element.get('blocking', False)) or weak_claim_focus) else 'medium',
                    question_intent=question_intent,
                ))
            if len(questions) >= max_questions:
                return questions[:max_questions]

    return questions
def _build_claim_temporal_gap_questions(
    self,
    intake_case_file: Optional[Dict[str, Any]],
    max_questions: int,
) -> List[Dict[str, Any]]:
    if not isinstance(intake_case_file, dict) or max_questions <= 0:
        return []

    temporal_issue_registry = intake_case_file.get('temporal_issue_registry', [])
    if not isinstance(temporal_issue_registry, list) or not temporal_issue_registry:
        return []

    claim_label_map: Dict[str, str] = {}
    for claim in intake_case_file.get('candidate_claims', []) or []:
        if not isinstance(claim, dict):
            continue
        claim_type = normalize_claim_type(str(claim.get('claim_type') or '').strip())
        if not claim_type:
            continue
        claim_label_map[claim_type] = str(claim.get('label') or claim_type).strip()

    questions: List[Dict[str, Any]] = []
    seen_keys: Set[str] = set()
    exhibit_ready_documents = self._needs_exhibit_ready_document_questions()
    for issue in temporal_issue_registry:
        if len(questions) >= max_questions:
            break
        if not isinstance(issue, dict):
            continue
        status = str(issue.get('status') or '').strip().lower()
        if status in {'resolved', 'closed', 'fixed'}:
            continue
        claim_types = [
            normalize_claim_type(str(value or '').strip())
            for value in (issue.get('claim_types') or issue.get('affected_claim_types') or [])
            if str(value or '').strip()
        ]
        claim_types = [claim_type for claim_type in claim_types if claim_type]
        claim_type = claim_types[0] if claim_types else ''
        claim_label = claim_label_map.get(claim_type) or (claim_type.replace('_', ' ') if claim_type else 'this claim')
        issue_id = str(issue.get('issue_id') or issue.get('source_ref') or issue.get('issue_type') or '').strip()
        issue_type = str(issue.get('issue_type') or issue.get('category') or '').strip().lower()
        element_tags = [str(tag or '').strip() for tag in (issue.get('element_tags') or issue.get('affected_element_ids') or []) if str(tag or '').strip()]
        target_element_id = str(element_tags[0] or '').strip().lower() if element_tags else ''
        question_key = '|'.join(filter(None, [issue_id.lower(), claim_type, issue_type, target_element_id]))
        if question_key in seen_keys:
            continue
        seen_keys.add(question_key)
        question_type = self._temporal_issue_question_type(issue_type)
        relative_markers = [str(marker or '').strip().lower() for marker in (issue.get('relative_markers') or []) if str(marker or '').strip()]
        question_text = self._build_claim_temporal_gap_question_text(
            issue_type,
            claim_label=claim_label,
            summary=self._short_description(str(issue.get('summary') or '').strip(), limit=120),
            left_node_name=str(issue.get('left_node_name') or '').strip(),
            right_node_name=str(issue.get('right_node_name') or '').strip(),
            relative_markers=relative_markers,
        )
        if exhibit_ready_documents and issue_type in {
            'missing_hearing_request_date',
            'missing_hearing_timing',
            'missing_response_dates',
            'missing_decision_timeline',
            'missing_written_notice',
        }:
            question_text = self._build_exhibit_ready_temporal_prompt(
                issue_type,
                claim_label=claim_label,
                base_question=question_text,
            )
        if self._already_asked(question_text):
            continue
        extraction_targets = self._temporal_issue_extraction_targets(
            issue_type,
            element_tags=element_tags,
            question_type=question_type,
        )
        patchability_markers = self._temporal_issue_patchability_markers(
            issue_type,
            element_tags=element_tags,
            question_type=question_type,
        )
        question = self._question_candidate(
            source='intake_claim_temporal_gap',
            question_type=question_type,
            question_text=question_text,
            context={
                'claim_type': claim_type,
                'claim_name': claim_label,
                'gap_id': issue_id or f'{claim_type}:{issue_type}',
                'gap_type': issue_type,
                'requirement_id': target_element_id,
                'target_element_id': target_element_id,
                'temporal_issue_id': issue_id,
                'temporal_issue_category': str(issue.get('category') or issue_type),
                'temporal_issue_summary': str(issue.get('summary') or ''),
                'temporal_issue_status': status or 'open',
                'left_node_name': str(issue.get('left_node_name') or ''),
                'right_node_name': str(issue.get('right_node_name') or ''),
                'fact_ids': list(issue.get('fact_ids') or []),
                'relative_markers': list(relative_markers),
                'deterministic_update_key': issue_id or f'{claim_type}:{issue_type}:{target_element_id}',
                'workflow_phase': 'document_generation' if question_type == 'evidence' else 'graph_analysis',
                'recommended_resolution_lane': str(issue.get('recommended_resolution_lane') or 'clarify_with_complainant'),
                'extraction_targets': extraction_targets,
                'patchability_markers': patchability_markers,
            },
            priority='high' if bool(issue.get('blocking')) or str(issue.get('severity') or '').strip().lower() == 'blocking' else 'medium',
        )
        question_objective = 'identify_supporting_proof' if question_type == 'evidence' else 'establish_chronology'
        question_goal = 'identify_supporting_proof' if question_type == 'evidence' else 'establish_element'
        if issue_type in {
            'retaliation_missing_causation',
            'retaliation_missing_causation_link',
            'retaliation_missing_sequence',
            'retaliation_missing_sequencing_dates',
        }:
            question_objective = 'establish_causation'
        elif question_type == 'responsible_party':
            question_objective = 'identify_responsible_actor'
        question['question_objective'] = question_objective
        question['question_goal'] = question_goal
        ranking_explanation = question.get('ranking_explanation') if isinstance(question.get('ranking_explanation'), dict) else {}
        ranking_explanation['question_objective'] = question_objective
        ranking_explanation['question_goal'] = question_goal
        question['ranking_explanation'] = ranking_explanation
        questions.append(question)

    return questions[:max_questions]
def _bind_unresolved_target(self, candidate: Dict[str, Any], *,
                            legal_context_targets: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    if not isinstance(candidate, dict):
        return candidate
    enriched = dict(candidate)
    if str(enriched.get('type') or enriched.get('question_type') or '').strip().lower() == 'legal_context':
        return self._bind_legal_context_question(enriched, legal_context_targets)
    context = dict(enriched.get('context') or {}) if isinstance(enriched.get('context'), dict) else {}
    enriched['question'] = self._neutralize_question_text(str(enriched.get('question') or ''))
    if self._is_operator_source_gap(enriched):
        enriched['user_answerability'] = 'operator_only'
        enriched['target_kind'] = 'source_diagnostic'
        enriched['unresolved_target'] = None
        return enriched

    question_type = str(enriched.get('type') or enriched.get('question_type') or '').strip().lower()
    source = str(enriched.get('candidate_source') or context.get('candidate_source') or '').strip()
    standard_slot = self._standard_intake_slot(enriched)
    left_id = str(context.get('left_node_id') or '').strip()
    right_id = str(context.get('right_node_id') or '').strip()
    raw_id = str(
        context.get('requirement_id')
        or enriched.get('target_element_id')
        or context.get('target_element_id')
        or context.get('claim_element_id')
        or context.get('entity_id')
        or context.get('issue_id')
        or context.get('gap_id')
        or context.get('deterministic_update_key')
        or context.get('node_id')
        or context.get('claim_id')
        or ''
    ).strip()
    if not raw_id and source == 'knowledge_graph_gap':
        raw_id = 'kg:' + str(context.get('gap_type') or question_type or 'gap')
    if standard_slot:
        target_kind = 'proof' if standard_slot == 'notice' else 'factual'
        target_id = f"{target_kind}:standard-intake:{standard_slot}"
    elif question_type == 'contradiction' or (left_id and right_id and 'contradict' in source):
        target_kind = 'contradiction'
        pair = tuple(sorted([left_id or raw_id or 'left', right_id or 'right']))
        target_id = f"contradiction:{pair[0]}:{pair[1]}"
    elif question_type == 'requirement' or source in {'dependency_graph_requirement', 'intake_claim_element_gap'}:
        target_kind = 'requirement'
        target_id = f"requirement:{raw_id}" if raw_id else ''
    elif question_type == 'evidence' or source in {'intake_proof_gap', 'history_follow_up'}:
        target_kind = 'proof' if source == 'intake_proof_gap' or question_type == 'evidence' else 'factual'
        if source == 'history_follow_up' and question_type != 'evidence':
            target_kind = 'factual'
        target_id = f"{target_kind}:{raw_id}" if raw_id else ''
    elif raw_id:
        target_kind = 'factual'
        target_id = f"factual:{raw_id}"
    else:
        existing = enriched.get('unresolved_target') if isinstance(enriched.get('unresolved_target'), dict) else None
        if not existing or not str(existing.get('target_id') or '').strip():
            enriched['unresolved_target'] = None
            return enriched
        target_kind = str(existing.get('target_kind') or 'factual')
        target_id = str(existing.get('target_id'))

    if not target_id:
        enriched['unresolved_target'] = None
        return enriched

    revision = str(
        context.get('target_revision')
        or context.get('revision')
        or enriched.get('target_revision')
        or 'unresolved'
    ).strip() or 'unresolved'
    priority = str(enriched.get('priority') or 'medium').strip().lower()
    blocking = str(enriched.get('blocking_level') or context.get('blocking_level') or '').strip().lower()
    dependency_impact = 3 if blocking == 'blocking' or priority == 'critical' else 2 if priority == 'high' else 1 if priority == 'medium' else 0
    if target_kind == 'contradiction':
        dependency_impact = max(dependency_impact, 3)
    uncertainty = 3 if target_kind == 'contradiction' else 2 if priority in {'high', 'critical'} else 1
    explicit_impact = context.get('dependency_impact', enriched.get('dependency_impact'))
    explicit_uncertainty = context.get('uncertainty', enriched.get('uncertainty'))
    if explicit_impact is not None:
        try:
            dependency_impact = int(explicit_impact)
        except (TypeError, ValueError):
            pass
    if explicit_uncertainty is not None:
        try:
            uncertainty = int(explicit_uncertainty)
        except (TypeError, ValueError):
            pass
    expected_information = str(
        enriched.get('expected_information')
        or context.get('expected_information')
        or enriched.get('expected_proof_gain')
        or 'Observed events, dates, people, or documents the user can recall or provide.'
    ).strip()
    why_answer_helps = str(
        enriched.get('why_answer_helps')
        or enriched.get('question_reason')
        or context.get('why_answer_helps')
        or 'The answer addresses an unresolved factual, requirement, or contradiction target without treating it as already proved.'
    ).strip()
    provenance = {
        'candidate_source': source,
        'requirement_id': str(context.get('requirement_id') or '') or None,
        'proof_objective_id': str(enriched.get('proof_objective_id') or '') or None,
        'entity_id': str(context.get('entity_id') or '') or None,
        'claim_id': str(context.get('claim_id') or '') or None,
        'left_node_id': left_id or None,
        'right_node_id': right_id or None,
        'node_id': str(context.get('node_id') or '') or None,
    }
    user_answerability = 'user_observable'
    lowered = str(enriched.get('question') or '').lower()
    if any(token in lowered for token in ('statute', 'case law', 'legal conclusion', 'liable', 'violation of law')):
        user_answerability = 'not_answerable'
    target = {
        'target_id': target_id,
        'target_revision': revision,
        'target_kind': target_kind,
        'provenance': provenance,
        'why_answer_helps': why_answer_helps,
        'expected_information': expected_information,
        'user_answerability': user_answerability,
        'dependency_impact': dependency_impact,
        'uncertainty': uncertainty,
    }
    enriched['unresolved_target'] = target
    enriched['target_id'] = target_id
    enriched['target_revision'] = revision
    enriched['target_kind'] = target_kind
    enriched['why_answer_helps'] = why_answer_helps
    enriched['expected_information'] = expected_information
    enriched['user_answerability'] = user_answerability
    enriched['dependency_impact'] = dependency_impact
    enriched['uncertainty'] = uncertainty
    explanation = dict(enriched.get('ranking_explanation') or {}) if isinstance(enriched.get('ranking_explanation'), dict) else {}
    explanation['unresolved_target'] = target
    explanation['dependency_impact'] = dependency_impact
    explanation['uncertainty'] = uncertainty
    explanation['user_answerability'] = user_answerability
    enriched['ranking_explanation'] = explanation
    return enriched
def generate_review_question_recommendations(
    self,
    claim_type: str,
    gap_claim: Optional[Dict[str, Any]] = None,
    contradiction_claim: Optional[Dict[str, Any]] = None,
    max_questions: int = 6,
) -> List[Dict[str, Any]]:
    recommendations: List[Dict[str, Any]] = []
    seen_keys: Set[str] = set()
    normalized_claim_type = (claim_type or 'claim').strip() or 'claim'

    contradiction_candidates = []
    if isinstance(contradiction_claim, dict):
        contradiction_candidates = contradiction_claim.get('candidates', []) or []
    for candidate in contradiction_candidates:
        if not isinstance(candidate, dict):
            continue
        element_id = str(candidate.get('claim_element_id') or '')
        element_text = str(candidate.get('claim_element_text') or element_id or 'this element')
        overlap_terms = list(candidate.get('overlap_terms', []) or [])
        overlap_snippet = ', '.join(overlap_terms[:3]) if overlap_terms else 'the current support record'
        recommendation = self._build_review_question_recommendation(
            claim_type=normalized_claim_type,
            lane='contradiction_resolution',
            target_claim_element_id=element_id,
            target_claim_element_text=element_text,
            question_text=(
                f"The current support for {element_text} conflicts. "
                "What do you recall about each account, and what dates, documents, or records can you provide?"
            ),
            question_reason=(
                f"Resolve a contradiction before collecting more support for {element_text}. "
                f"The conflicting records overlap on {overlap_snippet}."
            ),
            expected_proof_gain='high',
            supporting_evidence_summary=(
                f"Conflicting facts: {len(candidate.get('fact_ids', []) or [])}"
            ),
            current_status='contradicted',
            contradiction_fact_ids=candidate.get('fact_ids', []),
        )
        if recommendation['suppression_key'] in seen_keys:
            continue
        seen_keys.add(recommendation['suppression_key'])
        recommendations.append(recommendation)
        if len(recommendations) >= max_questions:
            return recommendations[:max_questions]

    unresolved_elements = []
    if isinstance(gap_claim, dict):
        unresolved_elements = gap_claim.get('unresolved_elements', []) or []
    for element in unresolved_elements:
        if not isinstance(element, dict):
            continue
        element_id = str(element.get('element_id') or '')
        element_text = str(element.get('element_text') or element_id or 'this element')
        status = str(element.get('status') or 'missing')
        missing_support_kinds = [
            str(kind) for kind in (element.get('missing_support_kinds', []) or []) if kind
        ]
        total_links = int(element.get('total_links', 0) or 0)
        fact_count = int(element.get('fact_count', 0) or 0)
        recommended_action = str(element.get('recommended_action') or '')
        support_quality_summary = (
            element.get('support_quality_summary', {})
            if isinstance(element.get('support_quality_summary'), dict)
            else {}
        )
        quality_signal_counts = (
            support_quality_summary.get('quality_signal_counts', {})
            if isinstance(support_quality_summary.get('quality_signal_counts'), dict)
            else {}
        )

        lane = 'testimony'
        if recommended_action == 'improve_parse_quality':
            lane = 'document_request'
        elif int(quality_signal_counts.get('weak_source_quality', 0) or 0) > 0:
            lane = 'document_request'
        elif int(quality_signal_counts.get('duplicate_support', 0) or 0) > 0:
            lane = 'document_request'
        elif (
            recommended_action in {'strengthen_support_path', 'review_support_quality'}
            or int(quality_signal_counts.get('weak_graph_connectivity', 0) or 0) > 0
        ):
            lane = 'testimony'
        elif missing_support_kinds == ['authority']:
            lane = 'authority_clarification'
        elif 'evidence' in missing_support_kinds or total_links == 0 or fact_count == 0:
            lane = 'testimony'
        elif 'authority' in missing_support_kinds:
            lane = 'authority_clarification'

        if lane == 'document_request':
            if int(quality_signal_counts.get('duplicate_support', 0) or 0) > 0:
                question_text = f"Do you have an independent document, message, witness, or record that separately supports {element_text}?"
                question_reason = (
                    f"{element_text} appears to rely on duplicate or non-independent support, so a distinct source would strengthen the proof path."
                )
            else:
                question_text = f"Do you have a clearer document, message, timeline, or record that supports {element_text}?"
                question_reason = (
                    f"{element_text} has some support, but the current records indicate a parse, source-quality, or document-quality gap."
                )
        elif lane == 'authority_clarification':
            question_text = f"Is there a rule, policy, statute, or case that clearly supports {element_text}?"
            question_reason = (
                f"{element_text} is still missing authority support needed for legal review."
            )
        elif (
            recommended_action in {'strengthen_support_path', 'review_support_quality'}
            or int(quality_signal_counts.get('weak_graph_connectivity', 0) or 0) > 0
        ):
            question_text = (
                f"What additional facts, source details, or relationships connect the current support "
                f"more directly to {element_text}?"
            )
            question_reason = (
                f"{element_text} has support, but GraphRAG support-path scoring found a structural quality gap "
                "such as weak graph connectivity or an indirect support path."
            )
        else:
            question_text = f"What specific facts can you provide to support {element_text}?"
            question_reason = (
                f"{element_text} is unresolved and needs clearer testimony or factual detail."
            )

        recommendation = self._build_review_question_recommendation(
            claim_type=normalized_claim_type,
            lane=lane,
            target_claim_element_id=element_id,
            target_claim_element_text=element_text,
            question_text=question_text,
            question_reason=question_reason,
            expected_proof_gain='high' if status == 'missing' else 'medium',
            supporting_evidence_summary=(
                f"Current support: {total_links} links, {fact_count} facts"
                + (f"; missing {', '.join(missing_support_kinds)}" if missing_support_kinds else '')
            ),
            current_status=status,
            missing_support_kinds=missing_support_kinds,
        )
        recommendation['support_quality_summary'] = support_quality_summary
        recommendation['quality_signal_counts'] = dict(quality_signal_counts)
        primary_quality_signal = self._primary_quality_signal_for_summary(support_quality_summary)
        recommendation['primary_quality_signal'] = primary_quality_signal
        recommendation['quality_follow_up_action'] = primary_quality_signal.get('follow_up_action', '')
        if recommendation['suppression_key'] in seen_keys:
            continue
        seen_keys.add(recommendation['suppression_key'])
        recommendations.append(recommendation)
        if len(recommendations) >= max_questions:
            break

    return recommendations[:max_questions]
