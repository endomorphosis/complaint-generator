"""Answer processing delegated from ComplaintDenoiser.

The function keeps the original method body. The class method forwards here
so answer handling stays behavior-compatible.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .dependency_graph import DependencyGraph
from .knowledge_graph import Entity, KnowledgeGraph
from .denoiser import logger, normalize_claim_type


def process_answer(self, question: Dict[str, Any], answer: str,
                  knowledge_graph: KnowledgeGraph,
                  dependency_graph: Optional[DependencyGraph] = None,
                  *,
                  answer_event_id: Optional[str] = None,
                  source_context: Optional[Dict[str, Any]] = None,
                  factual_action: Optional[str] = None,
                  supersedes_stable_id: Optional[str] = None,
                  retracts_stable_id: Optional[str] = None,
                  contradicts_stable_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Process an answer to a denoising question.

    Args:
        question: The question that was asked
        answer: The user's answer
        knowledge_graph: Knowledge graph to update
        dependency_graph: Optional dependency graph to update

    Returns:
        Information about what was updated
    """
    from complaint_phases.knowledge_graph import answer_event_payload

    event_payload = answer_event_payload(
        question=question,
        answer=answer,
        source_context=source_context,
        factual_action=factual_action,
        supersedes_stable_id=supersedes_stable_id,
        retracts_stable_id=retracts_stable_id,
        contradicts_stable_id=contradicts_stable_id,
    )
    if answer_event_id and knowledge_graph is not None:
        prior = knowledge_graph.begin_answer_event(answer_event_id, event_payload)
        if prior is not None and prior.get("denoiser_updates") is not None:
            return dict(prior["denoiser_updates"])
    explicit_disposition = None
    if isinstance(question, dict):
        explicit_disposition = question.get("disposition") or question.get("answer_disposition")
    if explicit_disposition in (None, "") and isinstance(source_context, dict):
        explicit_disposition = source_context.get("disposition") or source_context.get("answer_disposition")
    # A stored question label cannot turn "I don't know" or a refusal into a fact.
    answer_disposition = self.classify_answer_disposition(answer)
    if answer_disposition in self._NON_FACT_DISPOSITIONS:
        classified_disposition = answer_disposition
    else:
        classified_disposition = self.classify_answer_disposition(answer, explicit=explicit_disposition)
    if isinstance(question, dict) and str(question.get('type') or '').strip().lower() == 'legal_context':
        updates = self._process_legal_context_answer(
            question, answer, knowledge_graph, source_context,
            classified_disposition, factual_action=factual_action,
        )
        self.questions_asked.append({'question': question, 'answer': answer,
                                     'answer_event_id': answer_event_id,
                                     'disposition': updates['disposition'],
                                     'creates_fact': False, 'satisfies_requirement': False})
        if answer_event_id and knowledge_graph is not None:
            knowledge_graph.finish_answer_event(answer_event_id, event_payload,
                                                denoiser_updates=dict(updates))
        return updates
    if classified_disposition in self._NON_FACT_DISPOSITIONS:
        record = self.record_question_disposition(
            question if isinstance(question, dict) else {},
            answer,
            disposition=classified_disposition,
            intake_case_file=(source_context or {}).get("intake_case_file") if isinstance(source_context, dict) else None,
        )
        updates = self._non_fact_answer_updates(classified_disposition, record)
        self.questions_asked.append({
            'question': question,
            'answer': answer,
            'answer_event_id': answer_event_id,
            'disposition': classified_disposition,
            'creates_fact': False,
            'satisfies_requirement': False,
            'contradictory_conclusion': False,
        })
        if answer_event_id and knowledge_graph is not None:
            knowledge_graph.finish_answer_event(
                answer_event_id,
                event_payload,
                denoiser_updates=dict(updates),
            )
        return updates
    if factual_action:
        updates = self._process_factual_revision(
            question,
            answer,
            knowledge_graph,
            dependency_graph=dependency_graph,
            factual_action=factual_action,
            source_context=source_context,
            supersedes_stable_id=supersedes_stable_id,
            retracts_stable_id=retracts_stable_id,
            contradicts_stable_id=contradicts_stable_id,
            answer_event_id=answer_event_id,
        )
        self.questions_asked.append({
            'question': question,
            'answer': answer,
            'answer_event_id': answer_event_id,
            'factual_action': factual_action,
        })
        if answer_event_id and knowledge_graph is not None:
            knowledge_graph.finish_answer_event(
                answer_event_id,
                event_payload,
                denoiser_updates=dict(updates),
            )
        return updates

    self.questions_asked.append({
        'question': question,
        'answer': answer
    })

    updates = {
        'entities_updated': 0,
        'relationships_added': 0,
        'requirements_satisfied': 0
    }

    question_type = str(question.get('type') or '').strip().lower()
    context = question.get('context', {})
    context = context if isinstance(context, dict) else {}
    answer_text = str(answer or '').strip()
    workflow_phase = str(
        context.get('workflow_phase')
        or question.get('workflow_phase')
        or self._workflow_phase_for_question(question_type, context, str(question.get('candidate_source') or ''))
    ).strip().lower()
    question_objective = str(
        question.get('question_objective')
        or context.get('question_objective')
        or ''
    ).strip().lower()
    expected_update_kind = str(
        question.get('expected_update_kind')
        or context.get('expected_update_kind')
        or ''
    ).strip().lower()
    target_element_id = str(
        question.get('target_element_id')
        or context.get('target_element_id')
        or context.get('requirement_id')
        or ''
    ).strip().lower()
    extraction_targets = {
        str(item).strip().lower()
        for item in (
            context.get('extraction_targets')
            or question.get('extraction_targets')
            or []
        )
        if str(item).strip()
    }
    patchability_markers = {
        str(item).strip().lower()
        for item in (
            context.get('patchability_markers')
            or question.get('patchability_markers')
            or []
        )
        if str(item).strip()
    }
    timeline_enrichment_types = {'clarification', 'evidence', 'impact', 'relationship', 'remedy', 'requirement', 'responsible_party', 'timeline'}
    responsible_party_enrichment_types = {'clarification', 'evidence', 'relationship', 'requirement', 'responsible_party', 'timeline'}
    fallback_timeline_fact_types = {'clarification', 'evidence', 'relationship', 'requirement', 'responsible_party', 'timeline'}
    low_information_tokens = {
        '', 'n/a', 'na', 'none', 'unknown', 'not sure', 'unsure', 'no idea', 'i do not know', "i don't know",
    }
    gap_type = str(context.get('gap_type') or '').strip().lower()
    answer_contract = context.get('answer_contract') if isinstance(context.get('answer_contract'), dict) else {}
    contract_required_fields = [
        str(field).strip().lower()
        for field in (
            answer_contract.get('required_fields')
            or context.get('required_fields')
            or []
        )
        if str(field).strip()
    ]
    contract_required_fields = list(dict.fromkeys(contract_required_fields))
    contract_missing_required_fields = {
        str(field).strip().lower()
        for field in (
            answer_contract.get('missing_required_fields')
            or context.get('missing_required_fields')
            or []
        )
        if str(field).strip()
    }
    contract_requirement_updates = {
        str(field).strip().lower()
        for field in (
            answer_contract.get('requirement_updates')
            or context.get('requirement_updates')
            or []
        )
        if str(field).strip()
    }
    contract_entity_updates = {
        str(field).strip().lower()
        for field in (
            answer_contract.get('entity_updates')
            or context.get('entity_updates')
            or []
        )
        if str(field).strip()
    }
    contract_relationship_updates = {
        str(field).strip().lower()
        for field in (
            answer_contract.get('relationship_updates')
            or context.get('relationship_updates')
            or []
        )
        if str(field).strip()
    }
    contract_single_turn_closable = bool(
        answer_contract.get('single_turn_closable')
        or context.get('single_turn_closable')
    )
    contract_single_field_closable = bool(
        answer_contract.get('single_field_closable')
        or context.get('single_field_closable')
    )
    contract_deterministically_closable = bool(
        answer_contract.get('deterministically_closable')
        or context.get('deterministically_closable')
    )
    deterministic_requirement_tokens_updated: Set[str] = set()
    deterministic_relationship_tokens_updated: Set[str] = set()
    deterministic_entity_tokens_updated: Set[str] = set()
    deterministic_plan_fields_captured: Set[str] = set()
    expected_modalities = {
        str(item).strip().lower()
        for item in (context.get('expected_evidence_modalities') or [])
        if str(item).strip()
    }
    weak_modalities = {
        str(item).strip().lower()
        for item in (context.get('weak_evidence_modalities') or [])
        if str(item).strip()
    }
    answer_lower = answer_text.lower()
    extracted_dates = self._extract_date_strings(answer_text)
    response_timing_phrases = self._extract_response_timing_phrases(answer_text)
    document_mentions = self._extract_document_mentions(answer_text)
    named_role_people = self._extract_named_role_people(answer_text)
    named_title_people = self._extract_named_people_with_titles(answer_text)
    org_candidates = self._extract_org_candidates(answer_text)
    generic_roles = self._extract_generic_roles(answer_text)
    has_sequence_signal = self._contains_sequence_signal(answer_text)
    has_causation_signal = self._contains_causation_signal(answer_text)
    has_adverse_action_signal = self._contains_adverse_action_signal(answer_text)
    has_document_precision_signal = self._contains_document_precision_signal(answer_text)
    deterministic_fields_updated: Set[str] = set()

    def _extract_contextual_dates(text_value: str) -> Dict[str, List[str]]:
        buckets: Dict[str, List[str]] = {
            'hearing_request_dates': [],
            'response_dates': [],
            'adverse_action_dates': [],
            'protected_activity_dates': [],
            'decision_dates': [],
            'document_dates': [],
        }
        if not text_value:
            return buckets
        segments = re.split(r'(?<=[.!?;])\s+|\n+', text_value)
        for segment in segments:
            snippet = str(segment or '').strip()
            if not snippet:
                continue
            dates_in_segment = self._extract_date_strings(snippet)
            if not dates_in_segment:
                continue
            lower_segment = snippet.lower()
            for date_value in dates_in_segment:
                if any(token in lower_segment for token in ('hearing', 'appeal', 'requested hearing', 'request hearing', 'grievance hearing')):
                    buckets['hearing_request_dates'] = self._append_unique_text_item(
                        buckets.get('hearing_request_dates'),
                        date_value,
                    )
                if any(token in lower_segment for token in ('responded', 'response', 'replied', 'reply', 'ignored', 'no response', 'never responded')):
                    buckets['response_dates'] = self._append_unique_text_item(
                        buckets.get('response_dates'),
                        date_value,
                    )
                if any(token in lower_segment for token in ('denied', 'evicted', 'terminated', 'fired', 'adverse action', 'decision', 'notice', 'rejected')):
                    buckets['adverse_action_dates'] = self._append_unique_text_item(
                        buckets.get('adverse_action_dates'),
                        date_value,
                    )
                if any(token in lower_segment for token in ('complained', 'reported', 'protected activity', 'grievance', 'accommodation', 'discrimination complaint')):
                    buckets['protected_activity_dates'] = self._append_unique_text_item(
                        buckets.get('protected_activity_dates'),
                        date_value,
                    )
                if any(token in lower_segment for token in ('decision', 'determination', 'final decision', 'ruling')):
                    buckets['decision_dates'] = self._append_unique_text_item(
                        buckets.get('decision_dates'),
                        date_value,
                    )
                if any(token in lower_segment for token in ('notice', 'letter', 'email', 'message', 'memo', 'policy', 'document')):
                    buckets['document_dates'] = self._append_unique_text_item(
                        buckets.get('document_dates'),
                        date_value,
                    )
        return buckets

    contextual_dates = _extract_contextual_dates(answer_text)

    def _single_claim_id() -> Optional[str]:
        claims = knowledge_graph.get_entities_by_type('claim')
        return claims[0].id if len(claims) == 1 else None

    def _single_claim_entity() -> Optional[Entity]:
        claim_id = _single_claim_id()
        return knowledge_graph.get_entity(claim_id) if claim_id else None

    def _answer_is_substantive(text_value: str) -> bool:
        normalized = " ".join(str(text_value or '').strip().lower().split())
        if not normalized:
            return False
        if normalized in low_information_tokens:
            return False
        if len(normalized) < 8:
            return False
        if self._contains_confirmation_placeholder(normalized):
            return False
        return True

    def _extract_file_references(text_value: str) -> List[str]:
        if not text_value:
            return []
        refs: List[str] = []
        for pattern in (
            r"\b[\w\-./]+\.(?:pdf|docx?|xlsx?|csv|txt|jpg|jpeg|png|gif|msg|eml)\b",
            r"\"([^\"]+\.(?:pdf|docx?|xlsx?|csv|txt|jpg|jpeg|png|gif|msg|eml))\"",
            r"'([^']+\.(?:pdf|docx?|xlsx?|csv|txt|jpg|jpeg|png|gif|msg|eml))'",
        ):
            for match in re.findall(pattern, text_value, flags=re.IGNORECASE):
                candidate = str(match or "").strip()
                if candidate and candidate not in refs:
                    refs.append(candidate)
        return refs[:6]

    def _extract_policy_references(text_value: str) -> List[str]:
        if not text_value:
            return []
        refs: List[str] = []
        for match in re.findall(
            r"\b([A-Z][A-Za-z0-9/&\-\s]{2,80}(?:Policy|Handbook|Manual|Rule|Procedure|Guideline|Code))\b",
            text_value,
        ):
            candidate = str(match or "").strip()
            if candidate and candidate not in refs:
                refs.append(candidate)
        for match in re.findall(r"\b(section\s+\d+(?:\.\d+)*)\b", text_value, flags=re.IGNORECASE):
            candidate = str(match or "").strip()
            if candidate and candidate not in refs:
                refs.append(candidate)
        return refs[:6]

    extracted_file_refs = _extract_file_references(answer_text)
    extracted_policy_refs = _extract_policy_references(answer_text)
    contract_missing_field_plan = [
        plan
        for plan in (answer_contract.get('missing_field_update_plan') or context.get('missing_field_update_plan') or [])
        if isinstance(plan, dict)
    ]
    policy_signal = any(token in answer_lower for token in ('policy', 'handbook', 'rule', 'criteria', 'section', 'guideline')) or bool(extracted_policy_refs)
    file_signal = bool(extracted_file_refs) or bool(document_mentions) or any(token in answer_lower for token in ('file', 'upload', 'attachment', 'exhibit', 'pdf', 'screenshot', 'scan'))
    staff_signal = bool(named_role_people or named_title_people or generic_roles)

    def _has_structured_signal() -> bool:
        return bool(
            extracted_dates
            or response_timing_phrases
            or staff_signal
            or has_sequence_signal
            or has_causation_signal
            or has_adverse_action_signal
            or policy_signal
            or file_signal
        )

    def _find_claim_entity_from_context() -> Optional[Entity]:
        for key in ('claim_entity_id', 'claim_id'):
            candidate_id = str(context.get(key) or '').strip()
            if not candidate_id:
                continue
            entity = knowledge_graph.get_entity(candidate_id)
            if entity and entity.type == 'claim':
                return entity
        claim_name = str(context.get('claim_name') or '').strip().lower()
        if claim_name:
            for entity in knowledge_graph.get_entities_by_type('claim'):
                entity_name = str(entity.name or '').strip().lower()
                if entity_name == claim_name or claim_name in entity_name or entity_name in claim_name:
                    return entity
        return _single_claim_entity()

    def _append_attr_list(entity: Optional[Entity], key: str, value: str) -> bool:
        if not entity:
            return False
        updated = self._append_unique_text_item((entity.attributes or {}).get(key), value)
        previous = (entity.attributes or {}).get(key)
        if previous != updated:
            entity.attributes[key] = updated
            return True
        return False

    def _mark_resolved_gap(claim_entity: Optional[Entity]) -> None:
        nonlocal updates
        if not claim_entity:
            return
        deterministic_key = str(context.get('deterministic_update_key') or '').strip().lower()
        gap_id = str(context.get('gap_id') or '').strip().lower()
        requirement_id = str(context.get('requirement_id') or context.get('target_element_id') or '').strip().lower()
        resolution_key = deterministic_key or gap_id or requirement_id
        if not resolution_key:
            return
        changed = _append_attr_list(claim_entity, 'resolved_gaps', resolution_key)
        if changed:
            updates['entities_updated'] += 1

    def _append_claim_signal(claim_entity: Optional[Entity], key: str, value: str) -> None:
        nonlocal updates
        if not value:
            return
        if _append_attr_list(claim_entity, key, value):
            updates['entities_updated'] += 1

    def _required_fields_for_gap(current_gap_type: str) -> List[str]:
        mapping = {
            'missing_exact_action_dates': ['event_date', 'adverse_action'],
            'missing_hearing_request_date': ['hearing_request_date', 'hearing_request_actor'],
            'missing_response_dates': ['response_date', 'response_actor'],
            'missing_hearing_timing': ['adverse_action_date', 'hearing_request_date'],
            'missing_staff_identity': ['staff_name', 'staff_role'],
            'missing_staff_title': ['staff_name', 'staff_title'],
            'retaliation_missing_causation': ['protected_activity', 'adverse_action', 'causation_link'],
            'retaliation_missing_causation_link': ['protected_activity', 'adverse_action', 'causation_link'],
            'retaliation_missing_sequence': ['protected_activity_date', 'adverse_action_date'],
            'retaliation_missing_sequencing_dates': ['protected_activity_date', 'adverse_action_date'],
            'missing_written_notice': ['document_name', 'document_date', 'issuing_actor'],
            'missing_decision_timeline': ['decision_date', 'decision_actor'],
            'missing_claim_element': ['supporting_fact'],
            'missing_proof_leads': ['supporting_fact'],
        }
        fields: List[str] = list(mapping.get(str(current_gap_type or '').strip().lower(), []))
        for contract_field in contract_required_fields:
            if contract_field not in fields:
                fields.append(contract_field)
        return fields

    def _store_required_field_value(claim_entity: Optional[Entity], field_name: str, value: str) -> None:
        nonlocal updates
        if not claim_entity:
            return
        normalized_field = str(field_name or '').strip().lower()
        normalized_value = str(value or '').strip()
        if not normalized_field or not normalized_value:
            return
        attrs = claim_entity.attributes if isinstance(claim_entity.attributes, dict) else {}
        field_values = attrs.get('required_field_values')
        field_values = dict(field_values) if isinstance(field_values, dict) else {}
        existing_values = field_values.get(normalized_field)
        updated_values = self._append_unique_text_item(existing_values, normalized_value)
        if existing_values != updated_values:
            field_values[normalized_field] = updated_values
            attrs['required_field_values'] = field_values
            claim_entity.attributes = attrs
            updates['entities_updated'] += 1
            deterministic_fields_updated.add(normalized_field)
            _append_claim_signal(claim_entity, 'satisfied_requirements', normalized_field)

    def _link_claim_to_entity(claim_entity: Optional[Entity], target_entity: Optional[Entity], relation_type: str, confidence: float = 0.62) -> None:
        nonlocal updates
        if not claim_entity or not target_entity or not relation_type:
            return
        _, rel_created = self._add_relationship_if_missing(
            knowledge_graph,
            claim_entity.id,
            target_entity.id,
            relation_type,
            confidence,
        )
        if rel_created:
            updates['relationships_added'] += 1

    def _required_field_has_value(claim_entity: Optional[Entity], field_name: str) -> bool:
        if not claim_entity or not field_name:
            return False
        attrs = claim_entity.attributes if isinstance(claim_entity.attributes, dict) else {}
        field_values = attrs.get('required_field_values')
        field_values = field_values if isinstance(field_values, dict) else {}
        value = field_values.get(str(field_name or '').strip().lower())
        if isinstance(value, list):
            return any(str(item).strip() for item in value)
        return bool(str(value or '').strip())

    def _candidate_value_for_required_field(field_name: str) -> str:
        normalized = str(field_name or '').strip().lower()
        if not normalized:
            return ''
        if normalized in {'event_date', 'hearing_request_date', 'response_date', 'adverse_action_date', 'decision_date', 'protected_activity_date', 'document_date'}:
            if normalized == 'hearing_request_date' and contextual_dates.get('hearing_request_dates'):
                return str((contextual_dates.get('hearing_request_dates') or [''])[0]).strip()
            if normalized == 'response_date' and contextual_dates.get('response_dates'):
                return str((contextual_dates.get('response_dates') or [''])[0]).strip()
            if normalized == 'adverse_action_date' and contextual_dates.get('adverse_action_dates'):
                return str((contextual_dates.get('adverse_action_dates') or [''])[0]).strip()
            if normalized == 'decision_date' and contextual_dates.get('decision_dates'):
                return str((contextual_dates.get('decision_dates') or [''])[0]).strip()
            if normalized == 'protected_activity_date' and contextual_dates.get('protected_activity_dates'):
                return str((contextual_dates.get('protected_activity_dates') or [''])[0]).strip()
            if normalized == 'document_date' and contextual_dates.get('document_dates'):
                return str((contextual_dates.get('document_dates') or [''])[0]).strip()
            return str((extracted_dates or [''])[0]).strip()
        if normalized in {'staff_name', 'decision_actor', 'response_actor', 'hearing_request_actor', 'issuing_actor'}:
            if named_role_people:
                name, role = named_role_people[0]
                if normalized == 'staff_name':
                    return str(name or '').strip()
                return f"{name} ({role})".strip()
            if named_title_people:
                name, role = named_title_people[0]
                if normalized == 'staff_name':
                    return str(name or '').strip()
                return f"{name} ({role})".strip()
            return str((org_candidates or [''])[0]).strip()
        if normalized in {'staff_role', 'staff_title'}:
            if named_role_people:
                return str(named_role_people[0][1] or '').strip()
            if named_title_people:
                return str(named_title_people[0][1] or '').strip()
            return str((generic_roles or [''])[0]).strip()
        if normalized == 'document_name':
            if document_mentions:
                return str(document_mentions[0]).strip()
            if extracted_file_refs:
                return str(extracted_file_refs[0]).strip()
            if extracted_policy_refs:
                return str(extracted_policy_refs[0]).strip()
            return ''
        if normalized == 'protected_activity' and has_causation_signal:
            return self._short_description(answer_text, 160)
        if normalized == 'adverse_action' and (has_adverse_action_signal or has_causation_signal):
            return self._short_description(answer_text, 160)
        if normalized == 'causation_link' and has_causation_signal:
            return self._short_description(answer_text, 160)
        if normalized == 'supporting_fact' and _has_structured_signal():
            return self._short_description(answer_text, 180)
        return ''

    def _apply_contract_gap_updates(claim_entity: Optional[Entity]) -> None:
        if not claim_entity or not _answer_is_substantive(answer_text):
            return

        # Force deterministic closure attempts for contract-identified missing fields.
        for field_name in contract_required_fields:
            if field_name in deterministic_fields_updated:
                continue
            if field_name in contract_missing_required_fields or not _required_field_has_value(claim_entity, field_name):
                candidate_value = _candidate_value_for_required_field(field_name)
                if candidate_value:
                    _store_required_field_value(claim_entity, field_name, candidate_value)

        for plan in contract_missing_field_plan:
            field_name = str(plan.get('field_name') or '').strip().lower()
            if not field_name:
                continue
            # Only execute deterministic field-level updates when this turn captured the field.
            if field_name not in deterministic_fields_updated:
                continue
            deterministic_plan_fields_captured.add(field_name)
            for req_key in plan.get('requirement_updates') or []:
                normalized_req = str(req_key or '').strip().lower()
                if not normalized_req:
                    continue
                deterministic_requirement_tokens_updated.add(normalized_req)
                _append_claim_signal(claim_entity, 'satisfied_requirements', normalized_req)
            for rel_key in plan.get('relationship_updates') or []:
                normalized_rel = str(rel_key or '').strip().lower()
                if normalized_rel:
                    deterministic_relationship_tokens_updated.add(normalized_rel)
            for entity_key in plan.get('entity_updates') or []:
                normalized_entity = str(entity_key or '').strip().lower()
                if normalized_entity:
                    deterministic_entity_tokens_updated.add(normalized_entity)

        captured_contract_fields = deterministic_fields_updated.intersection(contract_missing_required_fields)
        if captured_contract_fields or (not contract_missing_required_fields and deterministic_fields_updated):
            deterministic_requirement_tokens_updated.update(contract_requirement_updates)
            deterministic_relationship_tokens_updated.update(contract_relationship_updates)
            deterministic_entity_tokens_updated.update(contract_entity_updates)

    def _deterministic_gap_field_updates(claim_entity: Optional[Entity]) -> None:
        if not claim_entity or not _answer_is_substantive(answer_text):
            return

        required_fields = _required_fields_for_gap(gap_type)
        if not required_fields:
            # Fall back to extraction targets to keep updates deterministic for registry-driven gaps.
            target_map = {
                'exact_dates': 'event_date',
                'event_order': 'supporting_fact',
                'actor_name': 'staff_name',
                'actor_role': 'staff_role',
                'decision_maker': 'decision_actor',
                'document_type': 'document_name',
                'document_date': 'document_date',
                'document_owner': 'issuing_actor',
                'protected_activity': 'protected_activity',
                'adverse_action': 'adverse_action',
                'causation_link': 'causation_link',
                'response_timing': 'response_date',
            }
            required_fields = [
                target_map[target]
                for target in extraction_targets
                if target in target_map
            ]
            deduped_fields: List[str] = []
            for field_name in required_fields:
                if field_name not in deduped_fields:
                    deduped_fields.append(field_name)
            required_fields = deduped_fields

        if extracted_dates:
            primary_date = extracted_dates[0]
            hearing_date = (contextual_dates.get('hearing_request_dates') or [primary_date])[0]
            response_date = (contextual_dates.get('response_dates') or [primary_date])[0]
            adverse_date = (contextual_dates.get('adverse_action_dates') or [primary_date])[0]
            decision_date = (contextual_dates.get('decision_dates') or [adverse_date])[0]
            protected_activity_date = (
                (contextual_dates.get('protected_activity_dates') or [primary_date])[0]
            )
            if 'event_date' in required_fields:
                _store_required_field_value(claim_entity, 'event_date', primary_date)
            if 'hearing_request_date' in required_fields:
                _store_required_field_value(claim_entity, 'hearing_request_date', hearing_date)
            if 'response_date' in required_fields:
                _store_required_field_value(claim_entity, 'response_date', response_date)
            if 'adverse_action_date' in required_fields:
                _store_required_field_value(claim_entity, 'adverse_action_date', adverse_date)
            if 'decision_date' in required_fields:
                _store_required_field_value(claim_entity, 'decision_date', decision_date)
            if 'protected_activity_date' in required_fields:
                _store_required_field_value(claim_entity, 'protected_activity_date', protected_activity_date)

        staff_pairs: List[Tuple[str, str]] = []
        staff_pairs.extend(named_role_people)
        staff_pairs.extend(named_title_people)
        if staff_pairs:
            if 'staff_name' in required_fields:
                _store_required_field_value(claim_entity, 'staff_name', staff_pairs[0][0])
            if 'staff_role' in required_fields:
                _store_required_field_value(claim_entity, 'staff_role', staff_pairs[0][1])
            if 'staff_title' in required_fields:
                _store_required_field_value(claim_entity, 'staff_title', staff_pairs[0][1])
            if 'decision_actor' in required_fields:
                _store_required_field_value(claim_entity, 'decision_actor', f"{staff_pairs[0][0]} ({staff_pairs[0][1]})")
            if 'issuing_actor' in required_fields:
                _store_required_field_value(claim_entity, 'issuing_actor', f"{staff_pairs[0][0]} ({staff_pairs[0][1]})")
            for person_name, person_role in staff_pairs[:4]:
                person_entity, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'person',
                    person_name,
                    {
                        'role': person_role,
                        'title': person_role,
                        'source': 'deterministic_gap_update',
                        'gap_type': gap_type,
                    },
                    0.78,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, person_entity, 'involves', 0.67)
                if any(token in person_role for token in ('manager', 'director', 'officer', 'landlord', 'owner', 'supervisor', 'agent')):
                    _link_claim_to_entity(claim_entity, person_entity, 'has_decision_maker', 0.66)
        elif org_candidates and ('decision_actor' in required_fields or 'issuing_actor' in required_fields):
            if 'decision_actor' in required_fields:
                _store_required_field_value(claim_entity, 'decision_actor', org_candidates[0])
            if 'issuing_actor' in required_fields:
                _store_required_field_value(claim_entity, 'issuing_actor', org_candidates[0])
            org_entity, created = self._add_entity_if_missing(
                knowledge_graph,
                'organization',
                org_candidates[0],
                {
                    'role': 'respondent',
                    'source': 'deterministic_gap_update',
                    'gap_type': gap_type,
                },
                0.72,
            )
            if created:
                updates['entities_updated'] += 1
            _link_claim_to_entity(claim_entity, org_entity, 'involves', 0.65)

        if ('document_name' in required_fields or 'supporting_fact' in required_fields) and (document_mentions or extracted_file_refs or extracted_policy_refs):
            document_value = (
                document_mentions[0]
                if document_mentions
                else extracted_file_refs[0]
                if extracted_file_refs
                else extracted_policy_refs[0]
            )
            if 'document_name' in required_fields:
                _store_required_field_value(claim_entity, 'document_name', document_value)
            if 'supporting_fact' in required_fields:
                _store_required_field_value(claim_entity, 'supporting_fact', self._short_description(answer_text, 160))

        if 'document_date' in required_fields and extracted_dates:
            document_date = (
                (contextual_dates.get('document_dates') or extracted_dates)[0]
            )
            _store_required_field_value(claim_entity, 'document_date', document_date)

        if 'response_actor' in required_fields and (staff_pairs or org_candidates):
            if staff_pairs:
                _store_required_field_value(claim_entity, 'response_actor', f"{staff_pairs[0][0]} ({staff_pairs[0][1]})")
            elif org_candidates:
                _store_required_field_value(claim_entity, 'response_actor', org_candidates[0])

        if 'hearing_request_actor' in required_fields and (staff_pairs or org_candidates):
            if staff_pairs:
                _store_required_field_value(claim_entity, 'hearing_request_actor', f"{staff_pairs[0][0]} ({staff_pairs[0][1]})")
            elif org_candidates:
                _store_required_field_value(claim_entity, 'hearing_request_actor', org_candidates[0])

        if 'protected_activity' in required_fields and has_causation_signal:
            _store_required_field_value(claim_entity, 'protected_activity', self._short_description(answer_text, 160))
        if 'adverse_action' in required_fields and (has_adverse_action_signal or has_causation_signal):
            _store_required_field_value(claim_entity, 'adverse_action', self._short_description(answer_text, 160))
        if 'causation_link' in required_fields and has_causation_signal:
            _store_required_field_value(claim_entity, 'causation_link', self._short_description(answer_text, 160))

        if 'supporting_fact' in required_fields and _has_structured_signal():
            _store_required_field_value(claim_entity, 'supporting_fact', self._short_description(answer_text, 180))

        # Promote concrete hearing/response/causation sequencing fields even when not explicitly required.
        if gap_type in {'missing_hearing_request_date', 'missing_hearing_timing'} and extracted_dates:
            hearing_candidate = (
                (contextual_dates.get('hearing_request_dates') or extracted_dates)[0]
            )
            _store_required_field_value(claim_entity, 'hearing_request_date', hearing_candidate)
        if gap_type in {'missing_response_dates', 'missing_decision_timeline'} and (extracted_dates or response_timing_phrases):
            if extracted_dates:
                response_candidate = (
                    (contextual_dates.get('response_dates') or extracted_dates)[0]
                )
                _store_required_field_value(claim_entity, 'response_date', response_candidate)
            elif response_timing_phrases:
                _store_required_field_value(claim_entity, 'response_date', response_timing_phrases[0])
        if gap_type in {'retaliation_missing_causation', 'retaliation_missing_causation_link', 'retaliation_missing_sequence', 'retaliation_missing_sequencing_dates'}:
            if has_causation_signal:
                _store_required_field_value(claim_entity, 'causation_link', self._short_description(answer_text, 160))
            if extracted_dates:
                protected_candidate = (
                    (contextual_dates.get('protected_activity_dates') or extracted_dates)[0]
                )
                adverse_candidates = contextual_dates.get('adverse_action_dates') or extracted_dates
                _store_required_field_value(claim_entity, 'protected_activity_date', protected_candidate)
                if len(adverse_candidates) > 1 and adverse_candidates[0] == protected_candidate:
                    _store_required_field_value(claim_entity, 'adverse_action_date', adverse_candidates[1])
                else:
                    _store_required_field_value(claim_entity, 'adverse_action_date', adverse_candidates[0])

    def _deterministic_requirement_fact(claim_entity: Optional[Entity]) -> None:
        nonlocal updates
        if not claim_entity or not _answer_is_substantive(answer_text):
            return
        requirement_id = str(context.get('requirement_id') or context.get('target_element_id') or '').strip()
        requirement_name = str(context.get('requirement_name') or requirement_id or 'claim element').strip()
        claim_type = normalize_claim_type(str(context.get('claim_type') or claim_entity.attributes.get('claim_type') or '').strip())
        snippet = self._short_description(answer_text, 140)
        fact_name = f"Requirement {requirement_name}: {self._short_description(answer_text, 72)}"
        fact_entity, created = self._add_entity_if_missing(
            knowledge_graph,
            'fact',
            fact_name,
            {
                'fact_type': 'requirement_support',
                'description': snippet,
                'requirement_id': requirement_id,
                'requirement_name': requirement_name,
                'claim_type': claim_type,
                'source_question_type': question_type,
                'gap_id': str(context.get('gap_id') or ''),
            },
            0.68,
        )
        if created:
            updates['entities_updated'] += 1
        _link_claim_to_entity(claim_entity, fact_entity, 'has_requirement_fact', 0.64)

        if requirement_id:
            changed = _append_attr_list(claim_entity, 'satisfied_requirements', requirement_id.lower())
            if changed:
                updates['entities_updated'] += 1
        if str(context.get('requirement_name') or '').strip():
            changed = _append_attr_list(claim_entity, 'satisfied_requirement_labels', requirement_name)
            if changed:
                updates['entities_updated'] += 1

    def _upsert_structured_evidence(claim_entity: Optional[Entity],
                                    claim_id: Optional[str],
                                    evidence_type: str,
                                    confidence: float,
                                    extra_attrs: Optional[Dict[str, Any]] = None) -> None:
        nonlocal updates
        if not claim_id or not _answer_is_substantive(answer_text):
            return
        snippet = self._short_description(answer_text, 140)
        prefix = "Policy document" if evidence_type == 'policy_document' else "File evidence"
        evidence_name = f"{prefix}: {self._short_description(answer_text, 80)}"
        attrs = {
            'description': snippet,
            'evidence_type': evidence_type,
            'gap_type': gap_type,
            'gap_id': str(context.get('gap_id') or ''),
        }
        if extra_attrs:
            attrs.update(extra_attrs)
        evidence_entity, created = self._add_entity_if_missing(
            knowledge_graph,
            'evidence',
            evidence_name,
            attrs,
            confidence,
        )
        if created:
            updates['entities_updated'] += 1
        if evidence_entity:
            _, rel_created = self._add_relationship_if_missing(
                knowledge_graph,
                claim_id,
                evidence_entity.id,
                'supported_by',
                max(0.6, confidence - 0.01),
            )
            if rel_created:
                updates['relationships_added'] += 1
        _append_claim_signal(claim_entity, 'satisfied_evidence_modalities', evidence_type)
        if evidence_type == 'policy_document':
            for ref in extracted_policy_refs[:3]:
                _append_claim_signal(claim_entity, 'policy_document_refs', ref)
        if evidence_type == 'file_evidence':
            for ref in extracted_file_refs[:3]:
                _append_claim_signal(claim_entity, 'file_evidence_refs', ref)

    def _mark_dependency_requirement_satisfied() -> None:
        nonlocal updates
        if not dependency_graph or not _answer_is_substantive(answer_text):
            return
        required_fields = _required_fields_for_gap(gap_type)
        captured_missing_required = deterministic_fields_updated.intersection(contract_missing_required_fields)
        if (
            required_fields
            and not deterministic_fields_updated.intersection(set(required_fields))
            and not deterministic_requirement_tokens_updated
        ):
            return
        if (
            workflow_phase == 'graph_analysis'
            and contract_missing_required_fields
            and not captured_missing_required
            and not deterministic_plan_fields_captured
        ):
            return
        candidate_ids = {
            str(context.get('requirement_id') or '').strip(),
            str(context.get('node_id') or '').strip(),
            str(context.get('target_element_id') or '').strip(),
        }
        requirement_name = str(context.get('requirement_name') or context.get('node_name') or '').strip().lower()
        requirement_key = str(context.get('requirement_key') or context.get('target_element_id') or '').strip().lower()
        requirement_aliases = {
            token
            for token in (
                [requirement_key]
                + list(deterministic_requirement_tokens_updated)
                + list(contract_requirement_updates)
            )
            if str(token or '').strip()
        }

        matched_nodes = []
        for node_id in [item for item in candidate_ids if item]:
            node = dependency_graph.get_node(node_id)
            if node:
                matched_nodes.append(node)
        if not matched_nodes:
            for node in dependency_graph.nodes.values():
                node_name = str(node.name or '').strip().lower()
                attrs = node.attributes if isinstance(node.attributes, dict) else {}
                node_requirement_key = str(attrs.get('requirement_key') or '').strip().lower()
                if requirement_name and node_name == requirement_name:
                    matched_nodes.append(node)
                elif requirement_aliases and node_requirement_key and node_requirement_key in requirement_aliases:
                    matched_nodes.append(node)

        seen_node_ids: Set[str] = set()
        for node in matched_nodes:
            if not node or node.id in seen_node_ids:
                continue
            seen_node_ids.add(node.id)
            if not node.satisfied:
                node.satisfied = True
                updates['requirements_satisfied'] += 1
            node.confidence = max(float(node.confidence or 0.0), 0.78)
            attrs = node.attributes if isinstance(node.attributes, dict) else {}
            attrs['satisfied_via_denoiser'] = True
            attrs['satisfied_answer_text'] = self._short_description(answer_text, 180)
            if str(context.get('gap_id') or '').strip():
                attrs['satisfied_gap_id'] = str(context.get('gap_id'))
            if requirement_key:
                attrs['requirement_key'] = requirement_key
            node.attributes = attrs

    def _mark_dependency_gap_satisfied() -> None:
        nonlocal updates
        if not dependency_graph or not _answer_is_substantive(answer_text):
            return
        required_fields = _required_fields_for_gap(gap_type)
        relevant_required = set(contract_missing_required_fields or required_fields)
        captured_required = deterministic_fields_updated.intersection(relevant_required)
        if (
            workflow_phase == 'graph_analysis'
            and relevant_required
            and not captured_required
            and not deterministic_requirement_tokens_updated
            and not deterministic_plan_fields_captured
        ):
            return
        gap_id = str(context.get('gap_id') or '').strip().lower()
        deterministic_key = str(context.get('deterministic_update_key') or '').strip().lower()
        target_keys = {
            item
            for item in [
                gap_id,
                deterministic_key,
                str(context.get('target_element_id') or '').strip().lower(),
                str(context.get('requirement_key') or '').strip().lower(),
            ]
            if item
        }
        if not target_keys and not gap_type:
            return
        for node in dependency_graph.nodes.values():
            attrs = node.attributes if isinstance(node.attributes, dict) else {}
            node_keys = {
                str(node.id or '').strip().lower(),
                str(node.name or '').strip().lower(),
                str(attrs.get('gap_id') or '').strip().lower(),
                str(attrs.get('gap_key') or '').strip().lower(),
                str(attrs.get('requirement_key') or '').strip().lower(),
                str(attrs.get('target_element_id') or '').strip().lower(),
            }
            node_gap_type = str(attrs.get('gap_type') or '').strip().lower()
            matched = bool(target_keys.intersection({item for item in node_keys if item}))
            if not matched and gap_type and node_gap_type == gap_type:
                matched = True
            if not matched:
                continue
            if not node.satisfied:
                node.satisfied = True
                updates['requirements_satisfied'] += 1
            node.confidence = max(float(node.confidence or 0.0), 0.8)
            attrs['satisfied_via_denoiser'] = True
            attrs['satisfied_answer_text'] = self._short_description(answer_text, 180)
            if gap_id:
                attrs['satisfied_gap_id'] = gap_id
            if gap_type:
                attrs['gap_type'] = gap_type
            node.attributes = attrs

    def _add_structured_graph_analysis_updates(claim_entity: Optional[Entity]) -> None:
        nonlocal updates
        if not claim_entity or not _answer_is_substantive(answer_text):
            return
        claim_id = claim_entity.id
        structured_timeline_events = self._extract_structured_timeline_events(answer_text)

        for event in structured_timeline_events[:10]:
            fact_entity, created = self._add_entity_if_missing(
                knowledge_graph,
                'fact',
                f"{event['event_label']}: {self._short_description(event['description'], 72)}",
                {
                    'fact_type': 'timeline',
                    'predicate_family': event['predicate_family'],
                    'event_label': event['event_label'],
                    'event_id': event['event_id'],
                    'sequence_index': event['sequence_index'],
                    'structured_timeline_group': event['structured_timeline_group'],
                    'description': event['description'],
                    'event_date_or_range': event['event_date_or_range'],
                    'fact_participants': {'actor_label': event['actor_text']},
                    'event_support_refs': [event['artifact_text']] if event['artifact_text'] else [],
                    'source_artifact_ids': [event['artifact_text']] if event['artifact_text'] else [],
                    'source_span_refs': [{'kind': 'structured_answer_line', 'text': event['source_line']}],
                    'source': 'structured_timeline_answer',
                },
                0.77,
            )
            if created:
                updates['entities_updated'] += 1
            _link_claim_to_entity(claim_entity, fact_entity, 'has_timeline_detail', 0.68)
            if event['artifact_text']:
                _append_claim_signal(claim_entity, 'documentary_artifact_refs', event['artifact_text'])
            if event['predicate_family'] == 'protected_activity':
                _append_claim_signal(claim_entity, 'protected_activity', event['description'])
                if event['event_date_or_range']:
                    _append_claim_signal(claim_entity, 'protected_activity_dates', event['event_date_or_range'])
            elif event['predicate_family'] == 'adverse_action':
                _append_claim_signal(claim_entity, 'adverse_action', event['description'])
                if event['event_date_or_range']:
                    _append_claim_signal(claim_entity, 'adverse_action_dates', event['event_date_or_range'])
            elif event['predicate_family'] == 'hearing_process':
                _append_claim_signal(claim_entity, 'hearing_request_timing', event['description'])
            elif event['predicate_family'] == 'response_timeline':
                _append_claim_signal(claim_entity, 'response_dates', event['description'])
            elif event['predicate_family'] == 'causation':
                _append_claim_signal(claim_entity, 'causation_sequences', event['description'])

        if extracted_dates:
            for date_str in extracted_dates[:5]:
                date_entity, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'date',
                    date_str,
                    {
                        'date_context_gap_type': gap_type,
                        'source_question_type': question_type,
                    },
                    0.74,
                )
                if created:
                    updates['entities_updated'] += 1
                if date_entity:
                    _, rel_created = self._add_relationship_if_missing(
                        knowledge_graph,
                        claim_id,
                        date_entity.id,
                        'occurred_on',
                        0.66,
                    )
                    if rel_created:
                        updates['relationships_added'] += 1
            _append_claim_signal(claim_entity, 'exact_dates', ", ".join(extracted_dates[:5]))

        if response_timing_phrases:
            timing_fact, created = self._add_entity_if_missing(
                knowledge_graph,
                'fact',
                f"Response timing: {self._short_description(answer_text, 72)}",
                {
                    'fact_type': 'response_timing',
                    'timing_phrases': list(response_timing_phrases[:4]),
                    'gap_type': gap_type,
                    'target_element_id': target_element_id,
                    'description': self._short_description(answer_text, 160),
                },
                0.72,
            )
            if created:
                updates['entities_updated'] += 1
            _link_claim_to_entity(claim_entity, timing_fact, 'has_timeline_detail', 0.64)
            for phrase in response_timing_phrases[:4]:
                _append_claim_signal(claim_entity, 'response_timing_phrases', phrase)

        people_with_roles: List[Tuple[str, str]] = []
        seen_people_roles: Set[Tuple[str, str]] = set()
        for pair in named_title_people + named_role_people:
            key = (str(pair[0] or '').strip().lower(), str(pair[1] or '').strip().lower())
            if not key[0] or not key[1]:
                continue
            if key not in seen_people_roles:
                seen_people_roles.add(key)
                people_with_roles.append((pair[0], pair[1]))

        for name, title in people_with_roles[:8]:
            person, created = self._add_entity_if_missing(
                knowledge_graph,
                'person',
                name,
                {'role': title, 'title': title, 'source': 'denoiser_answer'},
                0.74,
            )
            if created:
                updates['entities_updated'] += 1
            elif person:
                previous_title = str((person.attributes or {}).get('title') or '').strip().lower()
                if not previous_title and title:
                    person.attributes['title'] = title
                    updates['entities_updated'] += 1
            _link_claim_to_entity(claim_entity, person, 'involves', 0.64)
            if person and any(token in title for token in ('manager', 'director', 'officer', 'landlord', 'owner', 'supervisor', 'agent')):
                _link_claim_to_entity(claim_entity, person, 'has_decision_maker', 0.62)
                _append_claim_signal(claim_entity, 'decision_makers', f"{name} ({title})")

        for key, claim_attr in (
            ('hearing_request_dates', 'hearing_request_dates'),
            ('response_dates', 'response_dates'),
            ('adverse_action_dates', 'adverse_action_dates'),
            ('protected_activity_dates', 'protected_activity_dates'),
            ('decision_dates', 'decision_dates'),
        ):
            for date_token in (contextual_dates.get(key) or [])[:4]:
                _append_claim_signal(claim_entity, claim_attr, date_token)

        if has_causation_signal or has_sequence_signal:
            causation_fact, created = self._add_entity_if_missing(
                knowledge_graph,
                'fact',
                f"Causation sequence: {self._short_description(answer_text, 72)}",
                {
                    'fact_type': 'causation_sequence',
                    'has_causation_signal': bool(has_causation_signal),
                    'has_sequence_signal': bool(has_sequence_signal),
                    'has_adverse_action_signal': bool(has_adverse_action_signal),
                    'captured_dates': list(extracted_dates[:4]),
                    'target_element_id': target_element_id,
                    'description': self._short_description(answer_text, 160),
                },
                0.7,
            )
            if created:
                updates['entities_updated'] += 1
            _link_claim_to_entity(claim_entity, causation_fact, 'has_causation_detail', 0.63)
            if has_causation_signal:
                _append_claim_signal(claim_entity, 'causation_sequences', self._short_description(answer_text, 180))

        should_force_policy = (
            'documentary_artifact_patch_anchor' in patchability_markers
            or 'document_type' in extraction_targets
            or gap_type in {'missing_claim_element', 'missing_proof_leads', 'missing_written_notice'}
            or expected_update_kind in {'proof_lead', 'documentary_support'}
            or 'policy_document' in expected_modalities
            or 'policy_document' in weak_modalities
        )
        should_force_file = (
            should_force_policy
            or 'document_owner' in extraction_targets
            or 'file_evidence' in expected_modalities
            or 'file_evidence' in weak_modalities
        )
        if policy_signal and should_force_policy:
            _upsert_structured_evidence(
                claim_entity,
                claim_id,
                'policy_document',
                0.72,
                {
                    'policy_refs': list(extracted_policy_refs[:4]),
                    'document_mentions': list(document_mentions[:4]),
                    'question_objective': question_objective,
                    'expected_update_kind': expected_update_kind,
                },
            )
        if file_signal and should_force_file:
            _upsert_structured_evidence(
                claim_entity,
                claim_id,
                'file_evidence',
                0.72,
                {
                    'file_refs': list(extracted_file_refs[:4]),
                    'document_mentions': list(document_mentions[:4]),
                    'question_objective': question_objective,
                    'expected_update_kind': expected_update_kind,
                },
            )

        if gap_type in {'missing_hearing_request_date', 'missing_hearing_timing'} and (extracted_dates or response_timing_phrases):
            _append_claim_signal(claim_entity, 'hearing_request_timing', self._short_description(answer_text, 180))
            _append_claim_signal(claim_entity, 'satisfied_requirements', 'hearing_request_timing')
            hearing_fact, created = self._add_entity_if_missing(
                knowledge_graph,
                'fact',
                f"Hearing request timing: {self._short_description(answer_text, 70)}",
                {
                    'fact_type': 'hearing_request_timing',
                    'captured_dates': list(extracted_dates[:3]),
                    'response_timing': list(response_timing_phrases[:3]),
                    'description': self._short_description(answer_text, 180),
                },
                0.73,
            )
            if created:
                updates['entities_updated'] += 1
            _link_claim_to_entity(claim_entity, hearing_fact, 'has_timeline_detail', 0.66)
        if gap_type in {'missing_response_dates', 'missing_decision_timeline'} and (extracted_dates or response_timing_phrases):
            _append_claim_signal(claim_entity, 'response_dates', ", ".join(extracted_dates[:5]) or "; ".join(response_timing_phrases[:4]))
            _append_claim_signal(claim_entity, 'satisfied_requirements', 'response_dates')
            response_fact, created = self._add_entity_if_missing(
                knowledge_graph,
                'fact',
                f"Response dates: {self._short_description(answer_text, 70)}",
                {
                    'fact_type': 'response_dates',
                    'captured_dates': list(extracted_dates[:4]),
                    'response_timing': list(response_timing_phrases[:4]),
                    'description': self._short_description(answer_text, 180),
                },
                0.74,
            )
            if created:
                updates['entities_updated'] += 1
            _link_claim_to_entity(claim_entity, response_fact, 'has_timeline_detail', 0.66)
        if gap_type in {'missing_staff_identity', 'missing_staff_title'} and staff_signal:
            _append_claim_signal(claim_entity, 'staff_names_titles', self._short_description(answer_text, 180))
            _append_claim_signal(claim_entity, 'satisfied_requirements', 'staff_identity')
            for name, role in (named_title_people or named_role_people)[:4]:
                person, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'person',
                    name,
                    {'role': role, 'title': role, 'source': 'denoiser_answer'},
                    0.76,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, person, 'has_decision_maker', 0.68)
        if gap_type in {'retaliation_missing_causation', 'retaliation_missing_causation_link', 'retaliation_missing_sequence', 'retaliation_missing_sequencing_dates'} and (has_causation_signal or has_sequence_signal):
            _append_claim_signal(claim_entity, 'causation_timeline', self._short_description(answer_text, 180))
            _append_claim_signal(claim_entity, 'satisfied_requirements', 'causation_sequence')
            sequence_fact, created = self._add_entity_if_missing(
                knowledge_graph,
                'fact',
                f"Causation sequencing: {self._short_description(answer_text, 70)}",
                {
                    'fact_type': 'causation_sequence',
                    'captured_dates': list(extracted_dates[:4]),
                    'has_causation_signal': bool(has_causation_signal),
                    'has_sequence_signal': bool(has_sequence_signal),
                    'description': self._short_description(answer_text, 180),
                },
                0.74,
            )
            if created:
                updates['entities_updated'] += 1
            _link_claim_to_entity(claim_entity, sequence_fact, 'has_causation_detail', 0.67)

    def _apply_contract_entity_relationship_updates(claim_entity: Optional[Entity]) -> None:
        nonlocal updates
        if not claim_entity or not _answer_is_substantive(answer_text):
            return
        claim_id = claim_entity.id

        if (
            'staff_actor' in deterministic_entity_tokens_updated
            or 'link_staff_to_action' in deterministic_relationship_tokens_updated
        ) and (named_title_people or named_role_people or org_candidates):
            people = list(named_title_people) + list(named_role_people)
            if not people and org_candidates:
                org_entity, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'organization',
                    org_candidates[0],
                    {'role': 'respondent', 'source': 'answer_contract'},
                    0.76,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, org_entity, 'involves', 0.67)
            for name, title in people[:4]:
                person, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'person',
                    name,
                    {'role': title, 'title': title, 'source': 'answer_contract'},
                    0.78,
                )
                if created:
                    updates['entities_updated'] += 1
                _link_claim_to_entity(claim_entity, person, 'involves', 0.67)
                _link_claim_to_entity(claim_entity, person, 'has_decision_maker', 0.66)

        if (
            'document_evidence' in deterministic_entity_tokens_updated
            or 'link_document_to_claim' in deterministic_relationship_tokens_updated
        ):
            if policy_signal or extracted_policy_refs:
                _upsert_structured_evidence(
                    claim_entity,
                    claim_id,
                    'policy_document',
                    0.72,
                    {
                        'policy_refs': list(extracted_policy_refs[:4]),
                        'document_mentions': list(document_mentions[:4]),
                        'source': 'answer_contract',
                    },
                )
            if file_signal or extracted_file_refs:
                _upsert_structured_evidence(
                    claim_entity,
                    claim_id,
                    'file_evidence',
                    0.72,
                    {
                        'file_refs': list(extracted_file_refs[:4]),
                        'document_mentions': list(document_mentions[:4]),
                        'source': 'answer_contract',
                    },
                )

        if (
            'timeline_fact' in deterministic_entity_tokens_updated
            or 'link_event_sequence' in deterministic_relationship_tokens_updated
            or 'validate_temporal_order' in deterministic_relationship_tokens_updated
            or 'link_response_to_hearing_or_action' in deterministic_relationship_tokens_updated
        ) and (extracted_dates or response_timing_phrases or has_sequence_signal):
            timeline_fact, created = self._add_entity_if_missing(
                knowledge_graph,
                'fact',
                f"Timeline contract detail: {self._short_description(answer_text, 72)}",
                {
                    'fact_type': 'timeline_contract_detail',
                    'captured_dates': list(extracted_dates[:4]),
                    'response_timing': list(response_timing_phrases[:4]),
                    'has_sequence_signal': bool(has_sequence_signal),
                    'gap_type': gap_type,
                },
                0.73,
            )
            if created:
                updates['entities_updated'] += 1
            _link_claim_to_entity(claim_entity, timeline_fact, 'has_timeline_detail', 0.66)

        if (
            'claim_fact' in deterministic_entity_tokens_updated
            or 'link_causation_chain' in deterministic_relationship_tokens_updated
        ) and _has_structured_signal():
            fact_entity, created = self._add_entity_if_missing(
                knowledge_graph,
                'fact',
                f"Structured gap fact: {self._short_description(answer_text, 72)}",
                {
                    'fact_type': 'structured_gap_fact',
                    'gap_type': gap_type,
                    'description': self._short_description(answer_text, 180),
                    'source': 'answer_contract',
                },
                0.72,
            )
            if created:
                updates['entities_updated'] += 1
            _link_claim_to_entity(claim_entity, fact_entity, 'has_requirement_fact', 0.65)

    def _actor_critic_gap_confidence() -> float:
        if not _answer_is_substantive(answer_text):
            return 0.0
        claim_type_hint = normalize_claim_type(
            str(context.get('claim_type') or context.get('claim_name') or '').strip()
        )
        weak_claim_focus = claim_type_hint in {'housing_discrimination', 'hacc_research_engine'}
        weak_modality_focus = bool({'policy_document', 'file_evidence'}.intersection(weak_modalities))
        target_checks = {
            'exact_dates': bool(extracted_dates),
            'event_order': bool(has_sequence_signal),
            'response_timing': bool(response_timing_phrases),
            'decision_maker': bool(staff_signal),
            'actor_name': bool(staff_signal),
            'actor_role': bool(staff_signal),
            'adverse_action': bool(has_adverse_action_signal),
            'causation_link': bool(has_causation_signal),
            'document_type': bool(document_mentions),
            'document_date': bool(extracted_dates),
            'document_owner': bool(named_title_people or named_role_people or org_candidates),
            'hearing_request_timing': bool(contextual_dates.get('hearing_request_dates')),
            'response_dates': bool(contextual_dates.get('response_dates') or response_timing_phrases),
            'staff_names_titles': bool(staff_signal),
        }
        requested_targets = set(extraction_targets)
        if not requested_targets and target_element_id:
            if 'timing' in target_element_id or 'date' in target_element_id:
                requested_targets.update({'exact_dates', 'event_order'})
            if any(token in target_element_id for token in ('actor', 'staff', 'identity', 'title', 'party')):
                requested_targets.update({'actor_name', 'actor_role'})
            if any(token in target_element_id for token in ('causation', 'retaliation', 'sequence')):
                requested_targets.update({'causation_link', 'event_order'})
        if requested_targets:
            hits = sum(1 for target in requested_targets if target_checks.get(target, False))
            actor_score = hits / max(len(requested_targets), 1)
        elif contract_required_fields:
            contract_hits = sum(
                1
                for field_name in contract_required_fields
                if field_name in deterministic_fields_updated
            )
            actor_score = contract_hits / max(len(contract_required_fields), 1)
        else:
            actor_score = 1.0 if _has_structured_signal() else 0.35
        contract_capture_ratio = (
            len(deterministic_fields_updated.intersection(contract_missing_required_fields))
            / max(len(contract_missing_required_fields), 1)
            if contract_missing_required_fields
            else 1.0
        )
        critic_components = [
            1.0 if _has_structured_signal() else 0.0,
            1.0 if (policy_signal or file_signal) else 0.0,
            1.0 if (has_sequence_signal or has_causation_signal) else 0.0,
            1.0 if (extracted_dates or response_timing_phrases) else 0.0,
            1.0 if deterministic_fields_updated else 0.0,
            1.0 if deterministic_requirement_tokens_updated else 0.0,
            1.0 if (contextual_dates.get('response_dates') or contextual_dates.get('hearing_request_dates')) else 0.0,
            contract_capture_ratio,
        ]
        critic_score = sum(critic_components) / float(len(critic_components))
        weighted = (
            float(self.actor_weight or 1.0) * float(actor_score)
            + float(self.critic_weight or 1.0) * float(critic_score)
        ) / max(float(self.actor_weight or 1.0) + float(self.critic_weight or 1.0), 1e-6)
        if weak_claim_focus and bool(deterministic_fields_updated):
            weighted = min(1.0, weighted + 0.07)
        if weak_modality_focus and bool(policy_signal or file_signal):
            weighted = min(1.0, weighted + 0.05)
        return max(0.0, min(1.0, weighted))

    def _context_gap_is_closed() -> bool:
        if not _answer_is_substantive(answer_text):
            return False
        closure_confidence = _actor_critic_gap_confidence()
        if bool(self.actor_critic_enabled) and workflow_phase == 'graph_analysis' and closure_confidence < 0.5:
            return False

        claim_entity = _find_claim_entity_from_context()
        claim_attrs = claim_entity.attributes if (claim_entity and isinstance(claim_entity.attributes, dict)) else {}
        field_values = claim_attrs.get('required_field_values')
        field_values = field_values if isinstance(field_values, dict) else {}

        def _field_has_value(field_name: str) -> bool:
            value = field_values.get(field_name)
            if isinstance(value, list):
                return any(str(item).strip() for item in value)
            return bool(str(value or '').strip())

        required_fields = _required_fields_for_gap(gap_type)
        if required_fields:
            matched_fields = 0
            for field_name in required_fields:
                if field_name in deterministic_fields_updated or _field_has_value(field_name):
                    matched_fields += 1
            coverage = matched_fields / max(len(required_fields), 1)
            newly_captured_required = bool(deterministic_fields_updated.intersection(set(required_fields)))
            strict_gaps = {
                'missing_staff_identity',
                'missing_staff_title',
                'missing_written_notice',
                'missing_response_dates',
                'missing_hearing_request_date',
                'missing_decision_timeline',
                'retaliation_missing_causation_link',
                'retaliation_missing_sequencing_dates',
            }
            if gap_type in strict_gaps:
                return coverage >= 1.0 and newly_captured_required
            if workflow_phase == 'graph_analysis' and contract_missing_required_fields:
                captured_missing = deterministic_fields_updated.intersection(contract_missing_required_fields)
                captured_ratio = len(captured_missing) / max(len(contract_missing_required_fields), 1)
                if contract_single_field_closable:
                    return bool(captured_missing)
                if contract_single_turn_closable:
                    return bool(captured_missing) and coverage >= 1.0 and captured_ratio >= 1.0
                if contract_deterministically_closable:
                    return bool(captured_missing) and captured_ratio >= 0.5 and coverage >= 0.67
            # Require a concrete field capture in this turn before considering the gap closed.
            return newly_captured_required and coverage >= 0.5

        if not gap_type:
            return bool(_has_structured_signal() or question_type in {'requirement', 'evidence', 'timeline', 'responsible_party', 'relationship'})
        missing_claim_element_closed = bool(_has_structured_signal() or target_element_id)
        if target_element_id:
            if any(token in target_element_id for token in ('date', 'timeline', 'timing')):
                missing_claim_element_closed = missing_claim_element_closed and bool(extracted_dates or response_timing_phrases)
            if any(token in target_element_id for token in ('staff', 'actor', 'party', 'title', 'identity')):
                missing_claim_element_closed = missing_claim_element_closed and bool(staff_signal)
            if any(token in target_element_id for token in ('causation', 'retaliation', 'sequence')):
                missing_claim_element_closed = missing_claim_element_closed and bool(has_causation_signal or has_sequence_signal)
        checks = {
            'missing_exact_action_dates': bool(extracted_dates),
            'missing_hearing_request_date': bool(extracted_dates),
            'missing_response_dates': bool(extracted_dates or response_timing_phrases),
            'missing_hearing_timing': bool(extracted_dates or response_timing_phrases),
            'missing_decision_timeline': bool(extracted_dates) and bool(has_sequence_signal or response_timing_phrases or has_adverse_action_signal),
            'missing_staff_identity': bool(named_role_people or named_title_people or org_candidates),
            'missing_staff_title': bool(named_role_people or named_title_people or generic_roles),
            'missing_written_notice': bool(file_signal or has_document_precision_signal),
            'retaliation_missing_causation': bool(has_causation_signal) and bool(has_adverse_action_signal or has_sequence_signal or extracted_dates),
            'retaliation_missing_causation_link': bool(has_causation_signal) and bool(has_adverse_action_signal or has_sequence_signal or extracted_dates),
            'retaliation_missing_sequence': bool(has_sequence_signal) and bool(extracted_dates or response_timing_phrases),
            'retaliation_missing_sequencing_dates': bool(has_sequence_signal) and bool(extracted_dates or response_timing_phrases),
            'missing_claim_element': missing_claim_element_closed,
            'missing_proof_leads': bool(policy_signal or file_signal or extracted_file_refs or extracted_policy_refs),
        }
        return bool(checks.get(gap_type, True))

    def _record_gap_resolution(claim_entity: Optional[Entity]) -> None:
        nonlocal updates
        if not claim_entity or not _answer_is_substantive(answer_text):
            return
        if not gap_type:
            return
        fact_name = f"Gap resolved ({gap_type}): {self._short_description(answer_text, 68)}"
        attrs: Dict[str, Any] = {
            'fact_type': 'gap_resolution',
            'gap_type': gap_type,
            'gap_id': str(context.get('gap_id') or ''),
            'description': self._short_description(answer_text, 140),
            'source_question_type': question_type,
        }
        if extracted_dates:
            attrs['captured_dates'] = list(extracted_dates[:4])
        if response_timing_phrases:
            attrs['captured_response_timing'] = list(response_timing_phrases[:3])
        if extracted_policy_refs:
            attrs['captured_policy_refs'] = list(extracted_policy_refs[:3])
        if extracted_file_refs:
            attrs['captured_file_refs'] = list(extracted_file_refs[:3])
        fact_entity, created = self._add_entity_if_missing(
            knowledge_graph,
            'fact',
            fact_name,
            attrs,
            0.68,
        )
        if created:
            updates['entities_updated'] += 1
        _link_claim_to_entity(claim_entity, fact_entity, 'has_gap_resolution', 0.64)

    def _apply_timeline_enrichment() -> None:
        nonlocal updates
        if question_type not in timeline_enrichment_types or not answer_text:
            return
        claim_entity = _find_claim_entity_from_context()
        claim_id = claim_entity.id if claim_entity else _single_claim_id()
        structured_timeline_events = self._extract_structured_timeline_events(answer_text)
        if claim_entity and structured_timeline_events:
            for event in structured_timeline_events[:10]:
                fact_entity, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    f"{event['event_label']}: {self._short_description(event['description'], 72)}",
                    {
                        'fact_type': 'timeline',
                        'predicate_family': event['predicate_family'],
                        'event_label': event['event_label'],
                        'event_id': event['event_id'],
                        'sequence_index': event['sequence_index'],
                        'structured_timeline_group': event['structured_timeline_group'],
                        'description': event['description'],
                        'event_date_or_range': event['event_date_or_range'],
                        'fact_participants': {'actor_label': event['actor_text']},
                        'event_support_refs': [event['artifact_text']] if event['artifact_text'] else [],
                        'source_artifact_ids': [event['artifact_text']] if event['artifact_text'] else [],
                        'source_span_refs': [{'kind': 'structured_answer_line', 'text': event['source_line']}],
                        'source': 'structured_timeline_answer',
                    },
                    0.77,
                )
                if created:
                    updates['entities_updated'] += 1
                if claim_id and fact_entity:
                    _, rel_created = self._add_relationship_if_missing(
                        knowledge_graph,
                        claim_id,
                        fact_entity.id,
                        'has_timeline_detail',
                        0.68,
                    )
                    if rel_created:
                        updates['relationships_added'] += 1
        dates = self._extract_date_strings(answer_text)
        if dates:
            for date_str in dates:
                date_entity, created = self._add_entity_if_missing(
                    knowledge_graph,
                    'date',
                    date_str,
                    {},
                    0.7
                )
                if created:
                    updates['entities_updated'] += 1
                if claim_id and date_entity:
                    _, rel_created = self._add_relationship_if_missing(
                        knowledge_graph,
                        claim_id,
                        date_entity.id,
                        'occurred_on',
                        0.6
                    )
                    if rel_created:
                        updates['relationships_added'] += 1

        response_timing_phrases = self._extract_response_timing_phrases(answer_text)
        has_sequence = self._contains_sequence_signal(answer_text)
        should_add_timeline_fact = (
            question_type in fallback_timeline_fact_types
            and (not dates or has_sequence or bool(response_timing_phrases))
        )
        if should_add_timeline_fact:
            snippet = self._short_description(answer_text, 120)
            fact_name = f"Timeline detail: {self._short_description(answer_text, 60)}"
            fact_attrs: Dict[str, Any] = {'fact_type': 'timeline', 'description': snippet}
            if response_timing_phrases:
                fact_attrs['response_timing'] = list(response_timing_phrases[:3])
            if has_sequence:
                fact_attrs['event_order'] = 'captured'
            fact_entity, created = self._add_entity_if_missing(
                knowledge_graph,
                'fact',
                fact_name,
                fact_attrs,
                0.6
            )
            if created:
                updates['entities_updated'] += 1
            if claim_id and fact_entity:
                _, rel_created = self._add_relationship_if_missing(
                    knowledge_graph,
                    claim_id,
                    fact_entity.id,
                    'has_timeline_detail',
                    0.6
                )
                if rel_created:
                    updates['relationships_added'] += 1

        if question_type in {'evidence', 'timeline', 'responsible_party', 'requirement'}:
            document_mentions = self._extract_document_mentions(answer_text)
            for document_label in document_mentions[:3]:
                artifact_name = f"{document_label}: {self._short_description(answer_text, 64)}"
                artifact_entity, artifact_created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    artifact_name,
                    {
                        'fact_type': 'documentary_artifact',
                        'document_type': document_label,
                        'description': self._short_description(answer_text, 120),
                    },
                    0.58
                )
                if artifact_created:
                    updates['entities_updated'] += 1
                if claim_id and artifact_entity:
                    _, rel_created = self._add_relationship_if_missing(
                        knowledge_graph,
                        claim_id,
                        artifact_entity.id,
                        'has_documentary_artifact',
                        0.58
                    )
                    if rel_created:
                        updates['relationships_added'] += 1

    if question_type == 'clarification':
        entity_id = context.get('entity_id')
        entity = knowledge_graph.get_entity(entity_id)
        if entity:
            entity.confidence = min(1.0, entity.confidence + 0.2)
            entity.attributes['clarification'] = answer
            updates['entities_updated'] += 1

    elif question_type == 'relationship':
        entity_id = context.get('entity_id')
        if entity_id and _answer_is_substantive(answer_text):
            entity = knowledge_graph.get_entity(entity_id)
            if entity:
                entity.attributes['relationship_described'] = True
                entity.attributes['relationship_description'] = self._short_description(answer_text, 180)
                updates['entities_updated'] += 1
                _link_claim_to_entity(_find_claim_entity_from_context(), entity, 'involves', 0.63)

    elif question_type == 'responsible_party':
        pass

    elif question_type == 'evidence':
        claim_entity = _find_claim_entity_from_context()
        if claim_entity:
            claim_entity.attributes['evidence_descriptions'] = self._append_unique_text_item(
                claim_entity.attributes.get('evidence_descriptions'),
                answer,
            )
            updates['entities_updated'] += 1
        claim_id = claim_entity.id if claim_entity else _single_claim_id()
        if claim_id and _answer_is_substantive(answer_text):
            snippet = self._short_description(answer_text, 120)
            evidence_name = f"Evidence: {self._short_description(answer_text, 80)}"
            evidence_entity, created = self._add_entity_if_missing(
                knowledge_graph,
                'evidence',
                evidence_name,
                {'description': snippet},
                0.6
            )
            if created:
                updates['entities_updated'] += 1
            if evidence_entity:
                _, rel_created = self._add_relationship_if_missing(
                    knowledge_graph,
                    claim_id,
                    evidence_entity.id,
                    'supported_by',
                    0.6
                )
                if rel_created:
                    updates['relationships_added'] += 1

        modality_targets = expected_modalities.union(weak_modalities)
        should_capture_policy = bool(policy_signal) and (
            'policy_document' in modality_targets
            or gap_type in {'missing_claim_element', 'missing_proof_leads', 'missing_written_notice'}
        )
        should_capture_file = bool(file_signal) and (
            'file_evidence' in modality_targets
            or gap_type in {'missing_claim_element', 'missing_proof_leads', 'missing_written_notice'}
        )
        if claim_id and _answer_is_substantive(answer_text):
            if should_capture_policy:
                _upsert_structured_evidence(
                    claim_entity,
                    claim_id,
                    'policy_document',
                    0.7,
                    {
                        'policy_refs': list(extracted_policy_refs[:4]),
                        'document_mentions': list(document_mentions[:3]),
                        'document_date_candidates': list(extracted_dates[:3]),
                    },
                )
            if should_capture_file:
                _upsert_structured_evidence(
                    claim_entity,
                    claim_id,
                    'file_evidence',
                    0.7,
                    {
                        'file_refs': list(extracted_file_refs[:4]),
                        'document_mentions': list(document_mentions[:3]),
                        'document_date_candidates': list(extracted_dates[:3]),
                    },
                )

    elif question_type == 'timeline':
        pass

    elif question_type in {'impact', 'remedy'}:
        if answer_text:
            claim_entity = _find_claim_entity_from_context()
            claim_id = claim_entity.id if claim_entity else _single_claim_id()
            snippet = self._short_description(answer_text, 120)
            if question_type == 'remedy':
                fact_type = 'remedy'
                fact_name = f"Requested remedy: {self._short_description(answer_text, 60)}"
                rel_type = 'seeks_remedy'
            else:
                fact_type = 'impact'
                fact_name = f"Impact: {self._short_description(answer_text, 60)}"
                rel_type = 'has_impact'
            fact_entity, created = self._add_entity_if_missing(
                knowledge_graph,
                'fact',
                fact_name,
                {'fact_type': fact_type, 'description': snippet},
                0.6
            )
            if created:
                updates['entities_updated'] += 1
            if claim_id and fact_entity:
                _, rel_created = self._add_relationship_if_missing(
                    knowledge_graph,
                    claim_id,
                    fact_entity.id,
                    rel_type,
                    0.6
                )
                if rel_created:
                    updates['relationships_added'] += 1
            if question_type == 'impact' and self._contains_remedy_cue(answer_text):
                remedy_name = f"Requested remedy: {self._short_description(answer_text, 60)}"
                remedy_entity, remedy_created = self._add_entity_if_missing(
                    knowledge_graph,
                    'fact',
                    remedy_name,
                    {'fact_type': 'remedy', 'description': snippet},
                    0.55
                )
                if remedy_created:
                    updates['entities_updated'] += 1
                if claim_id and remedy_entity:
                    _, rel_created = self._add_relationship_if_missing(
                        knowledge_graph,
                        claim_id,
                        remedy_entity.id,
                        'seeks_remedy',
                        0.55
                    )
                    if rel_created:
                        updates['relationships_added'] += 1

    elif question_type == 'requirement':
        claim_entity = _find_claim_entity_from_context()
        _deterministic_requirement_fact(claim_entity)
        _mark_dependency_requirement_satisfied()
        _append_claim_signal(claim_entity, 'answered_requirement_questions', str(context.get('requirement_id') or context.get('target_element_id') or '').strip().lower())

    if question_type in responsible_party_enrichment_types and answer_text:
        updates = self._update_responsible_parties_from_answer(answer_text, knowledge_graph, updates)

    if question_type in timeline_enrichment_types and answer_text:
        _apply_timeline_enrichment()

    claim_entity_for_gap = _find_claim_entity_from_context()
    _deterministic_gap_field_updates(claim_entity_for_gap)
    _apply_contract_gap_updates(claim_entity_for_gap)
    _add_structured_graph_analysis_updates(claim_entity_for_gap)
    _apply_contract_entity_relationship_updates(claim_entity_for_gap)
    _mark_dependency_requirement_satisfied()

    if _context_gap_is_closed():
        _record_gap_resolution(claim_entity_for_gap)
        _mark_resolved_gap(claim_entity_for_gap)
        _mark_dependency_gap_satisfied()

    logger.info(f"Processed answer: {updates}")
    answered_record = self.record_question_disposition(
        question if isinstance(question, dict) else {},
        answer,
        disposition="answered",
        intake_case_file=(source_context or {}).get("intake_case_file") if isinstance(source_context, dict) else None,
        creates_fact=bool(updates.get("entities_updated") or updates.get("relationships_added")),
        satisfies_requirement=bool(updates.get("requirements_satisfied")),
        contradictory_conclusion=False,
    )
    updates["disposition"] = "answered"
    updates["creates_fact"] = answered_record["creates_fact"]
    updates["satisfies_requirement"] = bool(updates.get("requirements_satisfied"))
    updates["contradictory_conclusion"] = False
    updates["question_disposition"] = answered_record
    self.questions_asked[-1]["disposition"] = "answered"

    try:
        gain = self._compute_gain(updates)
        self._recent_gains.append(gain)
        if len(self._recent_gains) > 50:
            self._recent_gains = self._recent_gains[-50:]
        qtype = question.get('type') if isinstance(question, dict) else 'unknown'
        self._update_momentum(str(qtype or 'unknown'), gain)
    except Exception:
        pass

    if answer_event_id and knowledge_graph is not None:
        knowledge_graph.finish_answer_event(
            answer_event_id,
            event_payload,
            denoiser_updates=dict(updates),
        )
    return updates
