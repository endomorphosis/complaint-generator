"""Inquiry gap and claim-support packet helpers delegated from Mediator."""

from __future__ import annotations

from mediator.mediator import (
    Any,
    ComplaintPhase,
    Dict,
    List,
)

def build_inquiry_gap_context(self) -> Dict[str, Any]:
	priority_terms: List[str] = []
	priority_term_lookup = set()
	intake_case_file = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {}
	claim_support_packets = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'claim_support_packets') or {}
	chronology_objective_ledger = self._build_chronology_objective_ledger(intake_case_file)
	adversarial_summary = (
		self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'adversarial_intake_priority_summary') or {}
	)
	chronology_priority_hints = self._extract_document_chronology_priority_hints(
		intake_case_file,
		claim_support_packets,
		adversarial_summary,
		self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'workflow_optimization_guidance') or {},
		self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'claim_support_temporal_handoff') or {},
		self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'claim_reasoning_review') or {},
		self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'workflow_optimization_guidance') or {},
		self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'claim_support_temporal_handoff') or {},
		self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'claim_reasoning_review') or {},
	)
	expected_objectives = [
		str(value).strip().lower()
		for value in (
			(adversarial_summary.get('expected_objectives') or [])
			if isinstance(adversarial_summary, dict)
			else []
		)
		if str(value).strip()
	]
	covered_objectives = [
		str(value).strip().lower()
		for value in (
			(adversarial_summary.get('covered_objectives') or [])
			if isinstance(adversarial_summary, dict)
			else []
		)
		if str(value).strip()
	]
	uncovered_objectives = [
		str(value).strip().lower()
		for value in (
			(adversarial_summary.get('uncovered_objectives') or [])
			if isinstance(adversarial_summary, dict)
			else []
		)
		if str(value).strip()
	]
	for default_objective in (
		'anchor_appeal_rights',
		'anchor_grievance_hearing',
		'anchor_selection_criteria',
		'causation_sequence',
		'hearing_request_timing',
	):
		if default_objective in expected_objectives or default_objective in uncovered_objectives:
			continue
		if default_objective not in covered_objectives:
			uncovered_objectives.append(default_objective)
			if default_objective not in expected_objectives:
				expected_objectives.append(default_objective)
	for chronology_objective in chronology_priority_hints.get('objectives') or []:
		objective = str(chronology_objective).strip().lower()
		if not objective:
			continue
		if objective not in expected_objectives:
			expected_objectives.append(objective)
		if objective not in covered_objectives and objective not in uncovered_objectives:
			uncovered_objectives.append(objective)

	def _add_priority_term(value: Any) -> None:
		text = str(value or '').strip()
		if not text:
			return
		lowered = text.lower()
		if lowered in priority_term_lookup:
			return
		priority_term_lookup.add(lowered)
		priority_terms.append(text)

	for claim_packet in claim_support_packets.values() if isinstance(claim_support_packets, dict) else []:
		if not isinstance(claim_packet, dict):
			continue
		for element in claim_packet.get('elements', []) or []:
			if not isinstance(element, dict):
				continue
			if str(element.get('support_status') or '').strip().lower() == 'supported':
				continue
			for value in (element.get('element_label'), element.get('element_id'), claim_packet.get('claim_type')):
				_add_priority_term(value)
	if 'anchor_appeal_rights' in uncovered_objectives:
		for term in (
			'appeal rights notice',
			'right to appeal',
			'appeal deadline',
			'appeal request process',
		):
			_add_priority_term(term)
	if 'anchor_grievance_hearing' in uncovered_objectives:
		for term in (
			'grievance hearing request',
			'hearing process',
			'informal hearing record',
			'hearing officer or panel',
			'fallback grievance hearing details',
		):
			_add_priority_term(term)
	if 'anchor_selection_criteria' in uncovered_objectives:
		for term in (
			'selection criteria',
			'selection process',
			'qualifications used for selection',
			'written policy or rubric',
			'fallback selection criteria details',
		):
			_add_priority_term(term)
	if 'causation_sequence' in uncovered_objectives:
		for term in (
			'protected activity',
			'response timeline',
			'adverse action sequence',
			'step-by-step chronology',
		):
			_add_priority_term(term)
	if 'hearing_request_timing' in uncovered_objectives:
		for term in (
			'hearing request date',
			'hearing request timing',
			'how hearing or review request was submitted',
			'when hacc responded to hearing or review request',
			'request date request method response date',
			'deadline to request hearing',
			'date management received hearing request',
		):
			_add_priority_term(term)
	if bool(chronology_priority_hints.get('needs_chronology_closure')):
		for term in (
			'exact dates',
			'event timeline',
			'chronology sequence',
			'order of events',
			'decision timeline',
		):
			_add_priority_term(term)
	if 'causation_sequence' in uncovered_objectives:
		for term in (
			'causation sequence',
			'protected activity timeline',
			'sequence from complaint to adverse action',
		):
			_add_priority_term(term)
	if 'response_dates' in uncovered_objectives:
		for term in (
			'response date',
			'decision notice date',
			'when the denial or decision was communicated',
		):
			_add_priority_term(term)
	if bool(chronology_priority_hints.get('needs_decision_document_precision')):
		for term in (
			'decision notice',
			'denial letter',
			'written decision',
			'notice email',
		):
			_add_priority_term(term)
	if bool(chronology_priority_hints.get('needs_exhibit_grounding')):
		for term in (
			'exhibit-ready upload',
			'document label or subject line',
			'date sender and fact proved',
		):
			_add_priority_term(term)
	intake_fallback_probes: List[Dict[str, str]] = []
	if bool(chronology_priority_hints.get('needs_chronology_closure')):
		intake_fallback_probes.append({
			'objective': 'timeline',
			'question': 'Ask for the exact sequence of events, including dates for the protected activity, any response, and the adverse decision.',
		})
	if bool(chronology_priority_hints.get('needs_decision_document_precision')):
		intake_fallback_probes.append({
			'objective': 'documents',
			'question': 'Ask for the denial notice, written decision, appeal notice, or related emails that fix the decision date and stated reason.',
		})
	if bool(chronology_priority_hints.get('needs_exhibit_grounding')):
		intake_fallback_probes.append({
			'objective': 'documents',
			'question': 'Ask which uploaded or uploadable documents should be treated as exhibits and, for each one, the date, sender or source, label or subject line, and the fact the document proves.',
		})
	if 'anchor_grievance_hearing' in uncovered_objectives:
		intake_fallback_probes.append({
			'objective': 'anchor_grievance_hearing',
			'question': 'If grievance-hearing details are still missing, ask what grievance or hearing process was available, whether it was requested, and who handled it.',
		})
	if 'anchor_selection_criteria' in uncovered_objectives:
		intake_fallback_probes.append({
			'objective': 'anchor_selection_criteria',
			'question': 'If selection-criteria details are still missing, ask what criteria were used, what qualifications were considered, and what policy or rubric governed the decision.',
		})
	if 'hearing_request_timing' in uncovered_objectives:
		intake_fallback_probes.append({
			'objective': 'hearing_request_timing',
			'question': 'Ask when the hearing or review was requested, how the request was made, and when HACC responded.',
		})
	weak_claim_types = []
	for claim in intake_case_file.get('candidate_claims', []) if isinstance(intake_case_file, dict) else []:
		if not isinstance(claim, dict):
			continue
		claim_type = str(claim.get('claim_type') or '').strip().lower()
		if claim_type in {'housing_discrimination', 'hacc_research_engine'} and claim_type not in weak_claim_types:
			weak_claim_types.append(claim_type)
	weak_modalities = set()
	for claim_packet in claim_support_packets.values() if isinstance(claim_support_packets, dict) else []:
		if not isinstance(claim_packet, dict):
			continue
		for element in claim_packet.get('elements', []) or []:
			if not isinstance(element, dict):
				continue
			for key in ('evidence_classes', 'recommended_evidence', 'recommended_evidence_types', 'missing_evidence_modalities'):
				values = element.get(key)
				for value in values if isinstance(values, list) else [values]:
					normalized = str(value or '').strip().lower()
					if normalized in {'policy_document', 'file_evidence'}:
						weak_modalities.add(normalized)
	if 'policy_document' in weak_modalities:
		for term in ('policy document', 'handbook', 'written procedure', 'official policy notice'):
			_add_priority_term(term)
	if 'file_evidence' in weak_modalities:
		for term in ('file evidence', 'case file', 'email file', 'notice attachment'):
			_add_priority_term(term)
	return {
		'priority_terms': priority_terms,
		'gap_count': len(priority_terms),
		'chronology_objective_ledger': chronology_objective_ledger,
		'chronology_objective_count': len(chronology_objective_ledger),
		'needs_chronology_closure': bool(chronology_priority_hints.get('needs_chronology_closure')),
		'needs_decision_document_precision': bool(chronology_priority_hints.get('needs_decision_document_precision')),
		'needs_exhibit_grounding': bool(chronology_priority_hints.get('needs_exhibit_grounding')),
		'unresolved_temporal_issue_count': int(chronology_priority_hints.get('unresolved_temporal_issue_count') or 0),
		'chronology_task_count': int(chronology_priority_hints.get('chronology_task_count') or 0),
		'missing_proof_artifact_count': int(chronology_priority_hints.get('missing_proof_artifact_count') or 0),
		'intake_expected_objectives': expected_objectives,
		'intake_covered_objectives': covered_objectives,
		'intake_uncovered_objectives': uncovered_objectives,
		'intake_anchor_objectives': [
			objective
			for objective in (
				'anchor_appeal_rights',
				'anchor_grievance_hearing',
				'anchor_selection_criteria',
			)
			if objective in uncovered_objectives or objective in expected_objectives
		],
		'intake_fallback_probes': intake_fallback_probes,
		'weak_claim_types': weak_claim_types,
		'weak_evidence_modalities': sorted(weak_modalities),
	}


def _build_alignment_evidence_tasks(
	self,
	alignment_summary: Any,
	intake_case_file: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
	tasks: List[Dict[str, Any]] = []
	if not isinstance(alignment_summary, dict):
		return tasks
	claims = alignment_summary.get('claims', {})
	if not isinstance(claims, dict):
		return tasks

	for claim_type, claim_data in claims.items():
		if not isinstance(claim_data, dict):
			continue
		for element in claim_data.get('shared_elements', []) or []:
			if not isinstance(element, dict):
				continue
			support_status = str(element.get('support_status') or '').strip().lower()
			if support_status not in {'unsupported', 'partially_supported', 'contradicted'}:
				continue
			temporal_rule_status = str(element.get('temporal_rule_status') or '').strip().lower()
			temporal_follow_ups = [
				dict(follow_up)
				for follow_up in (element.get('temporal_rule_follow_ups', []) or [])
				if isinstance(follow_up, dict)
			]
			temporal_gap_targeted = temporal_rule_status in {'partial', 'failed'}
			action = 'resolve_support_conflicts' if support_status == 'contradicted' else (
				'fill_temporal_chronology_gap' if temporal_gap_targeted else 'fill_evidence_gaps'
			)
			claim_element_id = str(element.get('element_id') or '').strip()
			claim_element_label = str(element.get('label') or element.get('element_id') or '').strip()
			preferred_evidence_classes = list(element.get('preferred_evidence_classes', []) or [])
			missing_fact_bundle = list(element.get('missing_fact_bundle', []) or [])
			satisfied_fact_bundle = list(element.get('satisfied_fact_bundle', []) or [])
			missing_support_kinds = list(element.get('missing_support_kinds', []) or [])
			intake_proof_leads = [
				dict(lead)
				for lead in (element.get('intake_proof_leads', []) or [])
				if isinstance(lead, dict)
			]
			preferred_support_kind = self._resolve_task_preferred_support_kind(missing_support_kinds, preferred_evidence_classes)
			preferred_support_kind = self._preferred_support_kind_for_temporal_rule_profile(
				{'recommended_follow_ups': temporal_follow_ups},
				preferred_support_kind,
			)
			fallback_support_kinds = self._resolve_task_fallback_support_kinds(preferred_support_kind, preferred_evidence_classes)
			source_quality_target = 'credible_testimony' if preferred_support_kind == 'testimony' else 'high_quality_document'
			temporal_proof_objectives = list(element.get('temporal_proof_objectives', []) or [])
			missing_temporal_predicates = self._derive_missing_temporal_predicates(
				temporal_gap_targeted=temporal_gap_targeted,
				temporal_relation_formulas=element.get('temporal_relation_formulas', []),
				temporal_theorem_formulas=element.get('temporal_theorem_formulas', []),
				temporal_proof_objectives=temporal_proof_objectives,
				temporal_issue_records=element.get('temporal_issue_records', []),
				temporal_fact_ids=element.get('temporal_fact_ids', []),
			)
			required_provenance_kinds = self._derive_required_provenance_kinds(
				preferred_support_kind=preferred_support_kind,
				fallback_support_kinds=fallback_support_kinds,
				temporal_follow_ups=temporal_follow_ups,
				temporal_issue_records=element.get('temporal_issue_records', []),
			)
			temporal_next_actions = self._build_temporal_next_actions_for_task(
				claim_type=claim_type,
				claim_element_id=claim_element_id,
				claim_element_label=claim_element_label,
				temporal_rule_profile_id=element.get('temporal_rule_profile_id'),
				temporal_rule_status=temporal_rule_status,
				temporal_rule_follow_ups=temporal_follow_ups,
				temporal_rule_blocking_reasons=element.get('temporal_rule_blocking_reasons', []),
				temporal_issue_records=element.get('temporal_issue_records', []),
				temporal_fact_ids=element.get('temporal_fact_ids', []),
				temporal_relation_ids=element.get('temporal_relation_ids', []),
				temporal_issue_ids=element.get('temporal_issue_ids', []),
				missing_temporal_predicates=missing_temporal_predicates,
				required_provenance_kinds=required_provenance_kinds,
				packet_temporal_next_actions=element.get('temporal_next_actions'),
			)
			authored_temporal_issue_ids = [
				str(issue_id).strip()
				for issue_id in (element.get('authored_temporal_issue_ids', []) or [])
				if str(issue_id).strip()
			]
			proof_temporal_issue_ids = [
				str(issue_id).strip()
				for issue_id in (element.get('proof_temporal_issue_ids', []) or [])
				if str(issue_id).strip()
			]
			closure_issue_ids = authored_temporal_issue_ids or [
				str(issue_id).strip()
				for issue_id in (element.get('temporal_issue_ids', []) or [])
				if str(issue_id).strip()
			]
			required_anchor_ids = [
				str(anchor_id).strip()
				for anchor_id in (element.get('timeline_anchor_ids', []) or [])
				if str(anchor_id).strip()
			]
			chronology_source = str(element.get('chronology_source') or '').strip()
			intake_chronology_readiness = (
				dict(element.get('intake_chronology_readiness'))
				if isinstance(element.get('intake_chronology_readiness'), dict)
				else {}
			)
			closure_ready_when: List[str] = []
			if closure_issue_ids:
				closure_ready_when.append('Closure issue ids are resolved in authored chronology readiness')
			if required_anchor_ids:
				closure_ready_when.append('Required anchor ids remain attached to the chronology facts')
			if missing_temporal_predicates:
				closure_ready_when.append('Required temporal predicates are no longer missing')
			if required_provenance_kinds:
				closure_ready_when.append('Required provenance kinds are attached to the supporting record')
			if chronology_source.startswith('authored_intake_registry'):
				closure_ready_when.append('Authored intake chronology readiness clears the remaining open chronology blockers for this element')
			task_priority = 'high' if support_status == 'contradicted' or bool(element.get('blocking', False)) else 'medium'
			if temporal_gap_targeted:
				task_priority = 'high'
			success_criteria = [
				f'Element {claim_element_label} reaches supported status',
			]
			if missing_fact_bundle:
				success_criteria.append(f'Collect support addressing: {missing_fact_bundle[0]}')
			if temporal_gap_targeted and element.get('temporal_rule_blocking_reasons'):
				success_criteria.append(
					f'Establish chronology: {str((element.get("temporal_rule_blocking_reasons") or [""])[0] or "").strip()}'
				)
			recommended_witness_prompts = [
				f'Who can give first-hand testimony about {bundle_item} for {claim_element_label}?'
				for bundle_item in missing_fact_bundle[:2]
			]
			if temporal_gap_targeted:
				recommended_witness_prompts.extend(
					str(follow_up.get('reason') or '').strip()
					for follow_up in temporal_follow_ups
					if str(follow_up.get('reason') or '').strip()
				)
			resolution_status = self._derive_alignment_task_resolution_status(
				support_status,
				missing_fact_bundle,
				preferred_support_kind=preferred_support_kind,
				intake_proof_leads=intake_proof_leads,
			)
			tasks.append(
				{
					'task_id': f'{claim_type}:{claim_element_id}:{action}',
					'action': action,
					'claim_type': str(claim_type),
					'claim_element_id': claim_element_id,
					'claim_element_label': claim_element_label,
					'support_status': support_status,
					'blocking': bool(element.get('blocking', False)),
					'preferred_support_kind': preferred_support_kind,
					'preferred_evidence_classes': preferred_evidence_classes,
					'fallback_support_kinds': fallback_support_kinds,
					'fallback_lanes': list(fallback_support_kinds),
					'source_quality_target': source_quality_target,
					'task_priority': task_priority,
					'missing_fact_bundle': missing_fact_bundle,
					'satisfied_fact_bundle': satisfied_fact_bundle,
					'temporal_proof_objective': (
						temporal_proof_objectives[0]
						if temporal_proof_objectives
						else ('resolve_temporal_rule_profile' if temporal_gap_targeted else '')
					),
					'event_ids': list(element.get('temporal_fact_ids', []) or []),
					'temporal_fact_ids': list(element.get('temporal_fact_ids', []) or []),
					'anchor_ids': list(element.get('timeline_anchor_ids', []) or []),
					'required_anchor_ids': required_anchor_ids,
					'temporal_relation_ids': list(element.get('temporal_relation_ids', []) or []),
					'timeline_issue_ids': list(element.get('temporal_issue_ids', []) or []),
					'temporal_issue_ids': list(element.get('temporal_issue_ids', []) or []),
					'authored_temporal_issue_ids': authored_temporal_issue_ids,
					'proof_temporal_issue_ids': proof_temporal_issue_ids,
					'closure_issue_ids': closure_issue_ids,
					'chronology_source': chronology_source,
					'missing_temporal_predicates': missing_temporal_predicates,
					'required_temporal_predicates': list(missing_temporal_predicates),
					'required_provenance_kinds': required_provenance_kinds,
					'closure_ready_when': closure_ready_when,
					'intake_chronology_readiness': intake_chronology_readiness,
					'temporal_proof_bundle_id': str(element.get('temporal_proof_bundle_id') or '').strip(),
					'temporal_rule_profile_id': str(element.get('temporal_rule_profile_id') or ''),
					'temporal_rule_status': temporal_rule_status,
					'temporal_rule_blocking_reasons': list(element.get('temporal_rule_blocking_reasons', []) or []),
					'temporal_rule_follow_ups': temporal_follow_ups,
					'temporal_next_actions': temporal_next_actions,
					'temporal_next_action_count': len(temporal_next_actions),
					'temporal_missingness_kind': 'temporal_gap' if temporal_gap_targeted or temporal_next_actions else '',
					'intake_origin_refs': [
						f'open_item:{item_id}'
						for item_id in (element.get('intake_open_item_ids', []) or [])
					] + [
						f'proof_lead:{lead_id}'
						for lead_id in (element.get('intake_proof_lead_ids', []) or [])
					],
					'intake_proof_leads': intake_proof_leads,
					'recommended_queries': self._recommended_task_queries(
						str(claim_type),
						claim_element_label,
						missing_fact_bundle,
					),
					'recommended_witness_prompts': recommended_witness_prompts,
					'success_criteria': success_criteria,
					'resolution_status': resolution_status,
					'resolution_notes': '',
				}
			)

	# Merge in contradiction tasks from intake queue (Batch 3)
	if isinstance(intake_case_file, dict):
		contradiction_tasks = self._build_contradiction_tasks_from_queue(intake_case_file)
		existing_task_ids = {str(t.get('task_id') or '') for t in tasks}
		for ctask in contradiction_tasks:
			ctask_id = str(ctask.get('task_id') or '')
			if ctask_id not in existing_task_ids:
				tasks.append(ctask)
				existing_task_ids.add(ctask_id)

	tasks.sort(
		key=lambda task: (
			0 if task.get('support_status') == 'contradicted' else 1,
			0 if task.get('blocking') else 1,
			str(task.get('claim_type') or ''),
			str(task.get('claim_element_id') or ''),
		)
	)
	return tasks


def _build_authority_search_programs_for_task(
	self,
	claim_type: str,
	task: Dict[str, Any],
) -> List[Dict[str, Any]]:
	authority_queries = task.get('queries', {}).get('authority', []) if isinstance(task.get('queries'), dict) else []
	if not authority_queries:
		return []
	legal_authority_search = getattr(self, 'legal_authority_search', None)
	if legal_authority_search is None or not hasattr(legal_authority_search, 'build_search_programs'):
		return []
	primary_query = str(authority_queries[0] or '').strip()
	if not primary_query:
		return []
	claim_element_id = str(task.get('claim_element_id') or '').strip()
	claim_element_text = str(task.get('claim_element') or '').strip()
	source_preferences = task.get('source_preferences') if isinstance(task.get('source_preferences'), dict) else {}
	time_window = task.get('time_window') if isinstance(task.get('time_window'), dict) else {}
	graph_gap_query = task.get('graph_gap_query') if isinstance(task.get('graph_gap_query'), dict) else {}
	graph_gap_missing_support_values = graph_gap_query.get('missing_support_kinds') or []
	if not isinstance(graph_gap_missing_support_values, list):
		graph_gap_missing_support_values = [graph_gap_missing_support_values]
	graph_gap_missing_support_kinds = [
		str(kind or '').strip()
		for kind in graph_gap_missing_support_values
		if str(kind or '').strip()
	]
	graph_gap_has_support = bool(graph_gap_query.get('has_graph_support', False))
	graph_gap_authority_bias = ''
	if graph_gap_has_support and 'authority' in graph_gap_missing_support_kinds:
		graph_gap_authority_bias = 'graph_backed_authority_gap'
	defense_themes = self._authority_defense_themes_for_follow_up_task(task)
	if graph_gap_authority_bias:
		defense_themes = list(dict.fromkeys([*defense_themes, graph_gap_authority_bias]))
	try:
		programs = legal_authority_search.build_search_programs(
			query=primary_query,
			claim_type=claim_type,
			claim_elements=[
				{
					'claim_element_id': claim_element_id,
					'claim_element_text': claim_element_text,
				}
			],
			jurisdiction=str(task.get('jurisdiction') or ''),
			forum=str(task.get('forum') or ''),
			time_window=time_window,
			defense_themes=defense_themes,
			authority_families=list(source_preferences.get('authority_families') or []),
		)
	except Exception as exc:
		self.log(
			'follow_up_authority_search_program_error',
			claim_type=claim_type,
			claim_element_id=claim_element_id,
			error=str(exc),
		)
		return []
	if not isinstance(programs, list):
		return []

	focus = str(task.get('follow_up_focus') or '')
	priority_by_type: Dict[str, int] = {
		'element_definition_search': 2,
		'fact_pattern_search': 1,
		'procedural_search': 4,
		'adverse_authority_search': 3,
		'treatment_check_search': 5,
	}
	if focus == 'contradiction_resolution':
		priority_by_type.update({
			'adverse_authority_search': 1,
			'treatment_check_search': 2,
			'fact_pattern_search': 3,
		})
	elif focus == 'adverse_authority_review':
		priority_by_type.update({
			'adverse_authority_search': 1,
			'treatment_check_search': 2,
			'fact_pattern_search': 3,
		})
	elif focus == 'fact_gap_closure':
		priority_by_type.update({
			'fact_pattern_search': 1,
			'procedural_search': 2,
			'element_definition_search': 3,
		})
	elif focus == 'reasoning_gap_closure':
		priority_by_type.update({
			'fact_pattern_search': 1,
			'element_definition_search': 2,
			'treatment_check_search': 3,
		})
	elif focus == 'ontology_quality_gap_closure':
		priority_by_type.update({
			'element_definition_search': 1,
			'fact_pattern_search': 2,
			'treatment_check_search': 3,
		})
	elif focus == 'parse_quality_improvement':
		priority_by_type.update({
			'element_definition_search': 1,
			'fact_pattern_search': 2,
			'treatment_check_search': 3,
		})
	if graph_gap_authority_bias:
		priority_by_type.update({
			'element_definition_search': 1,
			'fact_pattern_search': 2,
			'treatment_check_search': 3,
			'adverse_authority_search': 4,
			'procedural_search': 5,
		})

	rule_candidate_context = task.get('rule_candidate_context', {}) if isinstance(task.get('rule_candidate_context'), dict) else {}
	top_rule_types = [
		str(rule_type or '').strip()
		for rule_type in (rule_candidate_context.get('top_rule_types') or [])
		if str(rule_type or '').strip()
	]
	has_exception_rules = bool(rule_candidate_context.get('has_exception_rules'))
	has_procedural_rules = bool(rule_candidate_context.get('has_procedural_rules'))
	has_element_rules = any(rule_type in {'element', 'definition'} for rule_type in top_rule_types)
	rule_signal_bias = ''
	if has_exception_rules:
		priority_by_type.update({
			'adverse_authority_search': 1,
			'treatment_check_search': 2,
			'fact_pattern_search': 3,
			'element_definition_search': 4,
			'procedural_search': 5,
		})
		rule_signal_bias = 'exception'
	elif has_procedural_rules:
		priority_by_type.update({
			'procedural_search': 1,
			'element_definition_search': 2,
			'fact_pattern_search': 3,
			'treatment_check_search': 4,
			'adverse_authority_search': 5,
		})
		rule_signal_bias = 'procedural_prerequisite'
	elif has_element_rules and focus in {'fact_gap_closure', 'reasoning_gap_closure', 'temporal_gap_closure'}:
		priority_by_type.update({
			'element_definition_search': 1,
			'fact_pattern_search': 2,
			'procedural_search': 3,
			'adverse_authority_search': 4,
			'treatment_check_search': 5,
		})
		rule_signal_bias = 'element'

	treatment_summary = task.get('authority_treatment_summary', {}) if isinstance(task.get('authority_treatment_summary'), dict) else {}
	treatment_type_counts = treatment_summary.get('treatment_type_counts', {}) if isinstance(treatment_summary.get('treatment_type_counts'), dict) else {}
	adverse_authority_count = int(treatment_summary.get('adverse_authority_link_count', 0) or 0)
	uncertain_authority_count = int(treatment_summary.get('uncertain_authority_link_count', 0) or 0)
	concerning_treatment_count = sum(
		int(count or 0)
		for name, count in treatment_type_counts.items()
		if str(name or '') in {'questioned', 'limits', 'superseded', 'good_law_unconfirmed'}
	)
	authority_signal_bias = ''
	if adverse_authority_count > 0:
		priority_by_type.update({
			'adverse_authority_search': 1,
			'treatment_check_search': 2,
			'fact_pattern_search': 3,
			'element_definition_search': 4,
			'procedural_search': 5,
		})
		authority_signal_bias = 'adverse'
	elif uncertain_authority_count > 0 or concerning_treatment_count > 0:
		priority_by_type.update({
			'treatment_check_search': 1,
			'adverse_authority_search': 2,
			'fact_pattern_search': 3,
			'element_definition_search': 4,
			'procedural_search': 5,
		})
		authority_signal_bias = 'uncertain'

	normalized_programs: List[Dict[str, Any]] = []
	for program in programs:
		if not isinstance(program, dict):
			continue
		program_type = str(program.get('program_type') or '')
		metadata = dict(program.get('metadata') or {}) if isinstance(program.get('metadata'), dict) else {}
		existing_authority_signal_bias = str(metadata.get('authority_signal_bias') or '')
		existing_rule_signal_bias = str(metadata.get('rule_signal_bias') or '')
		metadata.update({
			'follow_up_focus': focus,
			'query_strategy': str(task.get('query_strategy') or ''),
			'recommended_action': str(task.get('recommended_action') or ''),
			'validation_status': str(task.get('validation_status') or ''),
			'primary_authority_query': primary_query,
			'query_variants': list(authority_queries),
			'source_preferences': dict(source_preferences),
			'time_window': dict(time_window),
			'defense_themes': list(defense_themes),
			'graph_gap_query': dict(graph_gap_query),
			'graph_gap_authority_bias': graph_gap_authority_bias,
			'graph_gap_missing_support_kinds': list(graph_gap_missing_support_kinds),
			'rule_signal_bias': rule_signal_bias or existing_rule_signal_bias,
			'rule_candidate_focus_types': list(top_rule_types[:3]),
			'rule_candidate_focus_texts': list((rule_candidate_context.get('top_rule_texts') or [])[:2]),
			'priority_rank': priority_by_type.get(program_type, 99),
			'authority_signal_bias': authority_signal_bias or existing_authority_signal_bias,
		})
		normalized_programs.append({
			**program,
			'claim_type': str(program.get('claim_type') or claim_type),
			'claim_element_id': str(program.get('claim_element_id') or claim_element_id),
			'claim_element_text': str(program.get('claim_element_text') or claim_element_text),
			'jurisdiction': str(program.get('jurisdiction') or task.get('jurisdiction') or ''),
			'forum': str(program.get('forum') or task.get('forum') or ''),
			'metadata': metadata,
		})

	normalized_programs.sort(
		key=lambda program: (
			int(((program.get('metadata') or {}).get('priority_rank', 99)) or 99),
			str(program.get('program_type') or ''),
			str(program.get('program_id') or ''),
		)
	)
	return normalized_programs


def _build_claim_support_packets(
	self,
	user_id: str = None,
	required_support_kinds: List[str] | None = None,
) -> Dict[str, Any]:
	"""Build normalized evidence support packets from claim-support diagnostics."""
	resolved_user_id = user_id or self._current_user_id()
	intake_case_file = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {}
	candidate_claims = intake_case_file.get('candidate_claims', []) if isinstance(intake_case_file, dict) else []

	try:
		validation = self.get_claim_support_validation(
			user_id=resolved_user_id,
			required_support_kinds=required_support_kinds,
		)
	except Exception as exc:
		self.log(
			'claim_support_packet_degraded',
			operation='get_claim_support_validation',
			error=str(exc),
			error_type=type(exc).__name__,
		)
		validation = {'claims': {}}
	try:
		gaps = self.get_claim_support_gaps(
			user_id=resolved_user_id,
			required_support_kinds=required_support_kinds,
		)
	except Exception as exc:
		self.log(
			'claim_support_packet_degraded',
			operation='get_claim_support_gaps',
			error=str(exc),
			error_type=type(exc).__name__,
		)
		gaps = {'claims': {}}

	validation_claims = validation.get('claims', {}) if isinstance(validation, dict) else {}
	gap_claims = gaps.get('claims', {}) if isinstance(gaps, dict) else {}
	claim_names = set(validation_claims.keys()) | set(gap_claims.keys())
	for candidate in candidate_claims:
		if isinstance(candidate, dict) and candidate.get('claim_type'):
			claim_names.add(str(candidate.get('claim_type')))

	packets: Dict[str, Any] = {}
	for claim_type in sorted(claim_names):
		validation_claim = validation_claims.get(claim_type, {}) if isinstance(validation_claims, dict) else {}
		gap_claim = gap_claims.get(claim_type, {}) if isinstance(gap_claims, dict) else {}
		elements = []
		validation_elements = validation_claim.get('elements', []) if isinstance(validation_claim, dict) else []
		if isinstance(validation_elements, list) and validation_elements:
			for element in validation_elements:
				if not isinstance(element, dict):
					continue
				gap_context = element.get('gap_context', {}) if isinstance(element.get('gap_context'), dict) else {}
				support_facts = gap_context.get('support_facts', []) if isinstance(gap_context, dict) else []
				support_traces = gap_context.get('support_traces', []) if isinstance(gap_context, dict) else []
				reasoning_diagnostics = element.get('reasoning_diagnostics', {}) if isinstance(element.get('reasoning_diagnostics'), dict) else {}
				hybrid_reasoning = reasoning_diagnostics.get('hybrid_reasoning', {}) if isinstance(reasoning_diagnostics.get('hybrid_reasoning'), dict) else {}
				hybrid_result = hybrid_reasoning.get('result', {}) if isinstance(hybrid_reasoning.get('result'), dict) else {}
				element_id = element.get('element_id')
				element_text = element.get('element_text')
				registry_entry = self._claim_element_registry_entry(intake_case_file, claim_type, element_id)
				evidence_classes = list(registry_entry.get('evidence_classes', []) or [])
				required_fact_bundle = self._required_fact_bundle_for_element(claim_type, element_id, element_text)
				support_status = self._normalize_support_status(element.get('validation_status'))
				satisfied_fact_bundle, missing_fact_bundle = self._evaluate_fact_bundle_coverage(
					required_fact_bundle,
					support_facts,
					support_traces,
					support_status,
				)
				packet_element = {
					'element_id': element_id,
					'element_text': element_text,
					'support_status': support_status,
					'canonical_fact_ids': [
						fact.get('fact_id') for fact in support_facts
						if isinstance(fact, dict) and fact.get('fact_id')
					],
					'supporting_artifact_ids': [
						trace.get('source_ref') for trace in support_traces
						if isinstance(trace, dict) and trace.get('source_ref')
					],
					'supporting_testimony_ids': [
						trace.get('support_ref') for trace in support_traces
						if isinstance(trace, dict) and str(trace.get('source_family') or '').lower() == 'testimony'
						and trace.get('support_ref')
					],
					'supporting_authority_ids': [
						trace.get('support_ref') for trace in support_traces
						if isinstance(trace, dict) and str(trace.get('source_family') or '').lower() == 'authority'
						and trace.get('support_ref')
					],
					'contrary_fact_ids': [
						fact_id
						for item in (element.get('contradiction_candidates', []) or [])
						if isinstance(item, dict)
						for fact_id in (item.get('fact_ids', []) or [])
						if fact_id
					],
					'missing_support_kinds': list(element.get('missing_support_kinds', []) or []),
					'preferred_evidence_classes': evidence_classes,
					'required_fact_bundle': required_fact_bundle,
					'satisfied_fact_bundle': satisfied_fact_bundle,
					'missing_fact_bundle': missing_fact_bundle,
					'hybrid_bridge_used': bool(hybrid_reasoning),
					'hybrid_bridge_available': bool(hybrid_result.get('compiler_bridge_available', False)),
					'hybrid_tdfol_formula_count': len(hybrid_result.get('tdfol_formulas', []) or []),
					'hybrid_dcec_formula_count': len(hybrid_result.get('dcec_formulas', []) or []),
					'temporal_fact_count': int(((reasoning_diagnostics.get('temporal_summary') or {}).get('fact_count', 0)) or 0),
					'temporal_relation_count': int(((reasoning_diagnostics.get('temporal_summary') or {}).get('relation_count', 0)) or 0),
					'temporal_issue_count': int(((reasoning_diagnostics.get('temporal_summary') or {}).get('issue_count', 0)) or 0),
					'temporal_partial_order_ready': bool(((reasoning_diagnostics.get('temporal_summary') or {}).get('partial_order_ready', False))),
					'temporal_warning_count': int(((reasoning_diagnostics.get('temporal_summary') or {}).get('warning_count', 0)) or 0),
					'temporal_rule_profile_id': str(((reasoning_diagnostics.get('temporal_rule_profile') or {}).get('profile_id', '')) or ''),
					'temporal_rule_status': str(((reasoning_diagnostics.get('temporal_rule_profile') or {}).get('status', '')) or ''),
					'temporal_rule_blocking_reasons': list(((reasoning_diagnostics.get('temporal_rule_profile') or {}).get('blocking_reasons', [])) or []),
					'temporal_rule_follow_ups': list(((reasoning_diagnostics.get('temporal_rule_profile') or {}).get('recommended_follow_ups', [])) or []),
					'parse_quality_flags': self._extract_parse_quality_flags(element),
					'recommended_next_step': str(element.get('recommended_action') or ''),
					'contradiction_count': int(element.get('contradiction_candidate_count', 0) or 0),
				}
				packet_element['bundle_manifest'] = self._build_support_packet_bundle_manifest(
					support_facts,
					support_traces,
				)
				packet_element['archive_history'] = self._build_support_packet_archive_history(support_traces)
				packet_element['graph_trace_drilldown'] = self._build_support_packet_graph_trace_drilldown(
					element,
					support_traces,
				)
				packet_element['timeline_drilldown'] = self._build_support_packet_timeline_drilldown(
					reasoning_diagnostics,
					support_facts,
				)
				packet_element['contradiction_report'] = self._build_support_packet_contradiction_report(element)
				packet_element['missing_support_report'] = self._build_support_packet_missing_support_report(
					packet_element,
				)
				packet_element['support_quality'] = self._derive_packet_support_quality(packet_element)
				packet_element['support_lane_label'] = self._derive_support_lane_label(packet_element)
				elements.append(packet_element)
		else:
			for gap_element in gap_claim.get('unresolved_elements', []) if isinstance(gap_claim, dict) else []:
				if not isinstance(gap_element, dict):
					continue
				element_id = gap_element.get('element_id')
				element_text = gap_element.get('element_text')
				registry_entry = self._claim_element_registry_entry(intake_case_file, claim_type, element_id)
				evidence_classes = list(registry_entry.get('evidence_classes', []) or [])
				required_fact_bundle = self._required_fact_bundle_for_element(claim_type, element_id, element_text)
				packet_element = {
					'element_id': element_id,
					'element_text': element_text,
					'support_status': 'unsupported',
					'canonical_fact_ids': [
						fact.get('fact_id') for fact in (gap_element.get('support_facts', []) or [])
						if isinstance(fact, dict) and fact.get('fact_id')
					],
					'supporting_artifact_ids': [],
					'supporting_testimony_ids': [],
					'supporting_authority_ids': [],
					'contrary_fact_ids': [],
					'missing_support_kinds': list(gap_element.get('missing_support_kinds', []) or []),
					'preferred_evidence_classes': evidence_classes,
					'required_fact_bundle': required_fact_bundle,
					'satisfied_fact_bundle': [],
					'missing_fact_bundle': list(required_fact_bundle),
					'parse_quality_flags': [],
					'recommended_next_step': str(gap_element.get('recommended_action') or ''),
					'contradiction_count': 0,
				}
				packet_element['bundle_manifest'] = self._build_support_packet_bundle_manifest(
					gap_element.get('support_facts', []) or [],
					gap_element.get('support_traces', []) or [],
				)
				packet_element['archive_history'] = self._build_support_packet_archive_history(
					gap_element.get('support_traces', []) or [],
				)
				packet_element['graph_trace_drilldown'] = self._build_support_packet_graph_trace_drilldown(
					gap_element,
					gap_element.get('support_traces', []) or [],
				)
				packet_element['timeline_drilldown'] = {}
				packet_element['contradiction_report'] = self._build_support_packet_contradiction_report(gap_element)
				packet_element['missing_support_report'] = self._build_support_packet_missing_support_report(
					packet_element,
				)
				packet_element['support_quality'] = self._derive_packet_support_quality(packet_element)
				packet_element['support_lane_label'] = self._derive_support_lane_label(packet_element)
				elements.append(packet_element)
		packets[claim_type] = {
			'claim_type': claim_type,
			'overall_status': str(validation_claim.get('validation_status') or 'missing'),
			'elements': elements,
			'support_packet_reports': self._build_claim_support_packet_reports(elements),
		}

	return packets
