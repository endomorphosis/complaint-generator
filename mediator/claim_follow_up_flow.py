"""Claim follow-up methods delegated from Mediator."""

from __future__ import annotations

from mediator.mediator import (
    ComplaintPhase,
    _build_confirmed_intake_summary_handoff_metadata,
    match_required_element_id,
    refresh_intake_case_file,
)


def _build_follow_up_task(self, claim_type: str, element: Dict[str, Any], status: str,
		required_support_kinds: List[str]) -> Dict[str, Any]:
	element_text = element.get('element_text') or element.get('claim_element') or 'Unknown element'
	support_by_kind = element.get('support_by_kind', {})
	recommended_action = str(element.get('recommended_action') or '')
	authority_treatment_summary = element.get('authority_treatment_summary', {}) if isinstance(element.get('authority_treatment_summary'), dict) else {}
	authority_rule_candidate_summary = element.get('authority_rule_candidate_summary', {}) if isinstance(element.get('authority_rule_candidate_summary'), dict) else {}
	support_quality_summary = element.get('support_quality_summary', {}) if isinstance(element.get('support_quality_summary'), dict) else {}
	reasoning_diagnostics = element.get('reasoning_diagnostics', {}) if isinstance(element.get('reasoning_diagnostics'), dict) else {}
	ontology_quality_context = self._ontology_quality_follow_up_context(element)
	ontology_quality_gap_targeted = bool(ontology_quality_context.get('gap_count'))
	quality_signal_counts = (
		dict(support_quality_summary.get('quality_signal_counts', {}) or {})
		if isinstance(support_quality_summary.get('quality_signal_counts'), dict)
		else {}
	)
	if ontology_quality_gap_targeted:
		quality_signal_counts['ontology_quality_gap'] = int(ontology_quality_context.get('gap_count', 1) or 1)
	primary_quality_signal = (
		element.get('primary_quality_signal')
		if isinstance(element.get('primary_quality_signal'), dict)
		else {}
	)
	if not primary_quality_signal and support_quality_summary:
		primary_quality_signal_for_summary = getattr(
			getattr(self, 'claim_support', None),
			'_primary_quality_signal_for_summary',
			None,
		)
		if callable(primary_quality_signal_for_summary):
			primary_quality_signal = primary_quality_signal_for_summary(support_quality_summary)
	if ontology_quality_gap_targeted and (
		not primary_quality_signal or str(element.get('validation_status') or '') == 'supported'
	):
		primary_quality_signal = {
			'signal_type': 'ontology_quality_gap',
			'question_lane': 'ontology_quality_gap',
			'follow_up_action': str(ontology_quality_context.get('follow_up_action') or 'improve_ontology_quality'),
			'count': int(ontology_quality_context.get('gap_count', 1) or 1),
		}
	quality_follow_up_action = str(
		element.get('quality_follow_up_action')
		or primary_quality_signal.get('follow_up_action')
		or (ontology_quality_context.get('follow_up_action') if ontology_quality_gap_targeted else '')
		or ''
	).strip()
	rule_candidate_context = self._extract_rule_candidate_context(element)
	missing_support_kinds = [
		kind for kind in required_support_kinds
		if support_by_kind.get(kind, 0) == 0
	]
	priority = 'high' if status == 'missing' else 'medium'
	validation_status = element.get('validation_status', '')
	proof_gaps = element.get('proof_gaps', []) if isinstance(element.get('proof_gaps'), list) else []
	proof_gap_types = self._extract_proof_gap_types(proof_gaps)
	proof_decision_trace = element.get('proof_decision_trace', {}) if isinstance(element.get('proof_decision_trace'), dict) else {}
	temporal_rule_profile = reasoning_diagnostics.get('temporal_rule_profile', {}) if isinstance(reasoning_diagnostics.get('temporal_rule_profile'), dict) else {}
	temporal_proof_bundle = (
		reasoning_diagnostics.get('temporal_proof_bundle')
		if isinstance(reasoning_diagnostics.get('temporal_proof_bundle'), dict)
		else {}
	)
	reasoning_gap_targeted = self._is_reasoning_gap_follow_up(proof_gap_types, proof_decision_trace)
	temporal_gap_targeted = self._is_temporal_rule_gap_follow_up(
		proof_gap_types,
		proof_decision_trace,
		temporal_rule_profile,
	)
	query_recommended_action = (
		str(ontology_quality_context.get('follow_up_action') or 'improve_ontology_quality')
		if ontology_quality_gap_targeted and not recommended_action
		else recommended_action
	)
	queries = self._build_follow_up_queries(
		claim_type,
		element_text,
		missing_support_kinds,
		support_by_kind=support_by_kind,
		recommended_action=query_recommended_action,
		validation_status=validation_status,
		proof_gaps=proof_gaps,
		proof_decision_trace=proof_decision_trace,
		authority_treatment_summary=authority_treatment_summary,
		rule_candidate_context=rule_candidate_context,
		missing_fact_bundle=list(element.get('missing_fact_bundle', []) or []),
		temporal_rule_profile=temporal_rule_profile,
	)
	if validation_status == 'contradicted':
		priority = 'high'
	elif recommended_action == 'review_adverse_authority':
		priority = 'high'
	elif temporal_gap_targeted:
		priority = 'high'
	elif reasoning_gap_targeted:
		priority = 'high'
	elif ontology_quality_gap_targeted and bool(ontology_quality_context.get('has_blocking_gaps', False)):
		priority = 'high'
	elif recommended_action == 'improve_parse_quality':
		priority = 'high'
	execution_mode = 'retrieve_support'
	if validation_status == 'contradicted' and missing_support_kinds:
		execution_mode = 'review_and_retrieve'
	elif validation_status == 'contradicted':
		execution_mode = 'manual_review'
	elif recommended_action == 'review_adverse_authority' and missing_support_kinds:
		execution_mode = 'review_and_retrieve'
	elif recommended_action == 'review_adverse_authority':
		execution_mode = 'manual_review'
	elif temporal_gap_targeted and missing_support_kinds:
		execution_mode = 'review_and_retrieve'
	elif temporal_gap_targeted:
		execution_mode = 'manual_review'
	elif reasoning_gap_targeted and missing_support_kinds:
		execution_mode = 'review_and_retrieve'
	elif reasoning_gap_targeted:
		execution_mode = 'manual_review'
	elif ontology_quality_gap_targeted and missing_support_kinds:
		execution_mode = 'review_and_retrieve'
	elif ontology_quality_gap_targeted:
		execution_mode = 'retrieve_support'
	follow_up_focus = 'support_gap_closure'
	if validation_status == 'contradicted':
		follow_up_focus = 'contradiction_resolution'
	elif recommended_action == 'review_adverse_authority':
		follow_up_focus = 'adverse_authority_review'
	elif recommended_action == 'collect_fact_support':
		follow_up_focus = 'fact_gap_closure'
	elif temporal_gap_targeted:
		follow_up_focus = 'temporal_gap_closure'
	elif reasoning_gap_targeted:
		follow_up_focus = 'reasoning_gap_closure'
	elif ontology_quality_gap_targeted:
		follow_up_focus = 'ontology_quality_gap_closure'
	elif recommended_action == 'improve_parse_quality':
		follow_up_focus = 'parse_quality_improvement'
	else:
		# Detect legally-weak authority support: present but uncertain or limited.
		# Only apply when no higher-priority focus already applies.
		weak_focus = self._is_authority_treatment_weak_follow_up(authority_treatment_summary)
		if weak_focus:
			follow_up_focus = weak_focus
	query_strategy = 'standard_gap_targeted'
	if follow_up_focus == 'contradiction_resolution' and execution_mode == 'review_and_retrieve':
		query_strategy = 'contradiction_targeted'
	elif follow_up_focus == 'adverse_authority_review':
		query_strategy = 'adverse_authority_targeted'
	elif follow_up_focus == 'fact_gap_closure':
		query_strategy = 'rule_fact_targeted'
	elif follow_up_focus == 'temporal_gap_closure':
		query_strategy = 'temporal_gap_targeted'
	elif follow_up_focus == 'reasoning_gap_closure':
		query_strategy = 'reasoning_gap_targeted'
	elif follow_up_focus == 'ontology_quality_gap_closure':
		query_strategy = 'ontology_quality_gap_targeted'
	elif follow_up_focus == 'parse_quality_improvement':
		query_strategy = 'quality_gap_targeted'
	elif follow_up_focus == 'confirm_good_law':
		query_strategy = 'confirm_good_law_targeted'
	elif follow_up_focus == 'find_better_authority':
		query_strategy = 'find_better_authority_targeted'
	preferred_support_kind = str(
		element.get('preferred_support_kind')
		or self._default_preferred_support_kind(missing_support_kinds)
	).strip().lower()
	preferred_support_kind = self._preferred_support_kind_for_temporal_rule_profile(
		temporal_rule_profile,
		preferred_support_kind,
	)
	resolution_status = str(element.get('resolution_status') or '').strip().lower()
	if not resolution_status and temporal_gap_targeted:
		resolution_status = self._temporal_rule_resolution_status(temporal_rule_profile)
	time_window = self._build_follow_up_time_window(
		{
			'temporal_fact_ids': list(temporal_proof_bundle.get('temporal_fact_ids', []) or []),
			'temporal_relation_ids': list(temporal_proof_bundle.get('temporal_relation_ids', []) or []),
			'temporal_issue_ids': list(temporal_proof_bundle.get('temporal_issue_ids', []) or []),
		},
		temporal_rule_profile,
	)
	temporal_next_actions = self._build_temporal_next_actions_for_task(
		claim_type=claim_type,
		claim_element_id=element.get('element_id'),
		claim_element_label=element_text,
		temporal_rule_profile_id=temporal_rule_profile.get('profile_id'),
		temporal_rule_status=temporal_rule_profile.get('status'),
		temporal_rule_follow_ups=temporal_rule_profile.get('recommended_follow_ups', []),
		temporal_rule_blocking_reasons=temporal_rule_profile.get('blocking_reasons', []),
		temporal_issue_records=[],
		temporal_fact_ids=temporal_proof_bundle.get('temporal_fact_ids', []),
		temporal_relation_ids=temporal_proof_bundle.get('temporal_relation_ids', []),
		temporal_issue_ids=temporal_proof_bundle.get('temporal_issue_ids', []),
		missing_temporal_predicates=temporal_proof_bundle.get('missing_temporal_predicates', []),
		required_provenance_kinds=temporal_proof_bundle.get('required_provenance_kinds', []),
		temporal_proof_bundle=temporal_proof_bundle,
		packet_temporal_next_actions=element.get('temporal_next_actions'),
	)
	return {
		'claim_type': claim_type,
		'claim_element_id': element.get('element_id'),
		'claim_element': element_text,
		'status': status,
		'validation_status': validation_status,
		'support_by_kind': dict(support_by_kind or {}),
		'proof_decision_source': str(proof_decision_trace.get('decision_source') or ''),
		'logic_provable_count': int(proof_decision_trace.get('logic_provable_count', 0) or 0),
		'logic_unprovable_count': int(proof_decision_trace.get('logic_unprovable_count', 0) or 0),
		'ontology_validation_signal': str(proof_decision_trace.get('ontology_validation_signal') or ''),
		'proof_gap_count': int(element.get('proof_gap_count', 0) or 0),
		'proof_gaps': proof_gaps,
		'proof_gap_types': proof_gap_types,
		'validation_recommended_action': recommended_action,
		'authority_treatment_summary': authority_treatment_summary,
		'authority_rule_candidate_summary': authority_rule_candidate_summary,
		'support_quality_summary': support_quality_summary,
		'ontology_quality': dict(ontology_quality_context.get('quality') or {}),
		'ontology_gap_types': list(ontology_quality_context.get('gap_types') or []),
		'ontology_quality_gap_count': int(ontology_quality_context.get('gap_count', 0) or 0),
		'ontology_has_blocking_gaps': bool(ontology_quality_context.get('has_blocking_gaps', False)),
		'quality_signal_counts': quality_signal_counts,
		'primary_quality_signal': primary_quality_signal,
		'quality_follow_up_action': quality_follow_up_action,
		'rule_candidate_context': rule_candidate_context,
		'temporal_rule_profile': temporal_rule_profile,
		'temporal_rule_profile_id': str(temporal_rule_profile.get('profile_id') or ''),
		'temporal_rule_status': str(temporal_rule_profile.get('status') or ''),
		'temporal_rule_blocking_reasons': list(temporal_rule_profile.get('blocking_reasons', []) or []),
		'temporal_rule_follow_ups': list(temporal_rule_profile.get('recommended_follow_ups', []) or []),
		'temporal_next_actions': temporal_next_actions,
		'temporal_next_action_count': len(temporal_next_actions),
		'temporal_missingness_kind': 'temporal_gap' if temporal_gap_targeted or temporal_next_actions else '',
		'temporal_proof_bundle_id': str(temporal_proof_bundle.get('proof_bundle_id') or ''),
		'temporal_fact_ids': list(temporal_proof_bundle.get('temporal_fact_ids', []) or []),
		'temporal_relation_ids': list(temporal_proof_bundle.get('temporal_relation_ids', []) or []),
		'temporal_issue_ids': list(temporal_proof_bundle.get('temporal_issue_ids', []) or []),
		'time_window': time_window,
		'execution_mode': execution_mode,
		'requires_manual_review': execution_mode in {'manual_review', 'review_and_retrieve'},
		'reasoning_backed': bool(((element.get('reasoning_diagnostics') or {}).get('backend_available_count', 0) or 0) > 0),
		'follow_up_focus': follow_up_focus,
		'query_strategy': query_strategy,
		'priority': priority,
		'priority_score': 3 if priority == 'high' else 2,
		'recommended_action': recommended_action,
		'missing_support_kinds': missing_support_kinds,
		'preferred_support_kind': preferred_support_kind,
		'preferred_evidence_classes': list(element.get('preferred_evidence_classes', []) or []),
		'fallback_support_kinds': list(element.get('fallback_support_kinds', []) or []),
		'source_preferences': {},
		'authority_intent': '',
		'source_quality_target': str(element.get('source_quality_target') or '').strip(),
		'missing_fact_bundle': list(element.get('missing_fact_bundle', []) or []),
		'satisfied_fact_bundle': list(element.get('satisfied_fact_bundle', []) or []),
		'intake_origin_refs': list(element.get('intake_origin_refs', []) or []),
		'intake_proof_leads': list(element.get('intake_proof_leads', []) or []),
		'resolution_status': resolution_status,
		'success_criteria': list(element.get('success_criteria', []) or []),
		'recommended_queries': list(element.get('recommended_queries', []) or []),
		'queries': queries,
	}
def execute_claim_follow_up_plan(
	self,
	claim_type: str = None,
	user_id: str = None,
	support_kind: str = None,
	max_tasks_per_claim: int = 3,
	min_relevance: float = 0.6,
	cooldown_seconds: int = 3600,
	force: bool = False,
):
	"""Execute follow-up retrieval tasks for missing or partial claim support."""
	if user_id is None:
		user_id = getattr(self.state, 'username', None) or getattr(self.state, 'hashed_username', 'anonymous')
	plan = self.get_claim_follow_up_plan(claim_type=claim_type, user_id=user_id)
	results = {
		'support_kind': support_kind,
		'claims': {},
	}
	handoff_metadata = _build_confirmed_intake_summary_handoff_metadata(self)

	for current_claim, claim_plan in plan.get('claims', {}).items():
		executed_tasks = []
		skipped_tasks = []
		for task in claim_plan.get('tasks', [])[:max_tasks_per_claim]:
			task_resolution_status = self._resolve_follow_up_execution_handoff(task)
			execution = {
				'claim_element_id': task.get('claim_element_id'),
				'claim_element': task.get('claim_element'),
				'status': task.get('status'),
				'priority': task.get('priority'),
				'preferred_support_kind': task.get('preferred_support_kind'),
				'preferred_evidence_classes': list(task.get('preferred_evidence_classes') or []),
				'missing_fact_bundle': list(task.get('missing_fact_bundle') or []),
				'satisfied_fact_bundle': list(task.get('satisfied_fact_bundle') or []),
				'success_criteria': list(task.get('success_criteria') or []),
				'recommended_action': task.get('recommended_action'),
				'execution_mode': task.get('execution_mode', 'retrieve_support'),
				'requires_manual_review': task.get('requires_manual_review', False),
				'reasoning_backed': task.get('reasoning_backed', False),
				'follow_up_focus': task.get('follow_up_focus', ''),
				'query_strategy': task.get('query_strategy', ''),
				'source_preferences': task.get('source_preferences', {}),
				'time_window': task.get('time_window', {}),
				'authority_intent': task.get('authority_intent', ''),
				'proof_gap_count': int(task.get('proof_gap_count', 0) or 0),
				'proof_gap_types': list(task.get('proof_gap_types') or []),
				'authority_search_program_summary': task.get('authority_search_program_summary', {}),
				'authority_search_programs': list(task.get('authority_search_programs') or []),
				'graph_support': task.get('graph_support', {}),
				'graph_gap_context': task.get('graph_gap_context', {}),
				'graph_gap_query': task.get('graph_gap_query', {}),
				'should_suppress_retrieval': task.get('should_suppress_retrieval', False),
				'suppression_reason': task.get('suppression_reason', ''),
				'resolution_status': task_resolution_status,
				'resolution_applied': '',
				'executed': {},
			}
			if task_resolution_status:
				handoff_query = self._build_follow_up_handoff_query(current_claim, task, task_resolution_status)
				handoff_reason = self._follow_up_handoff_skip_reason(task_resolution_status)
				handoff_support_kind = self._follow_up_handoff_support_kind(task, task_resolution_status)
				self.claim_support.record_follow_up_execution(
					user_id=user_id,
					claim_type=current_claim,
					claim_element_id=task.get('claim_element_id'),
					claim_element_text=task.get('claim_element'),
					support_kind=handoff_support_kind,
					query_text=handoff_query,
					status='skipped_resolution_handoff',
					metadata=self._build_follow_up_record_metadata(
						task,
						skip_reason=handoff_reason,
						audit_query=handoff_query,
						resolution_status=task_resolution_status,
						resolution_applied=task_resolution_status,
					),
				)
				skipped_tasks.append({
					**execution,
					'resolution_applied': task_resolution_status,
					'skipped': {
						'escalation': {
							'reason': handoff_reason,
							'resolution_status': task_resolution_status,
							'audit_query': handoff_query,
						}
					},
				})
				continue
			if task.get('execution_mode') == 'manual_review':
				manual_review_query = self._build_manual_review_audit_query(current_claim, task)
				skip_reason = self._manual_review_skip_reason(task)
				self.claim_support.record_follow_up_execution(
					user_id=user_id,
					claim_type=current_claim,
					claim_element_id=task.get('claim_element_id'),
					claim_element_text=task.get('claim_element'),
					support_kind='manual_review',
					query_text=manual_review_query,
					status='skipped_manual_review',
					metadata=self._build_follow_up_record_metadata(
						task,
						skip_reason=skip_reason,
						audit_query=manual_review_query,
					),
				)
				skipped_tasks.append({
					**execution,
					'skipped': {
						'manual_review': {
							'reason': skip_reason,
							'audit_query': manual_review_query,
						}
					},
				})
				continue
			if not force and task.get('should_suppress_retrieval'):
				skipped_tasks.append({
					**execution,
					'skipped': {
						'suppressed': {
							'reason': task.get('suppression_reason', 'existing_support_sufficient'),
						}
					},
				})
				continue
			preferred_support_kind = str(task.get('preferred_support_kind') or '').strip().lower()
			lane_execution_records: List[Dict[str, Any]] = []
			run_evidence_lane = (
				support_kind in (None, 'evidence')
				and (
					'evidence' in task.get('missing_support_kinds', [])
					or (
						task.get('follow_up_focus') == 'ontology_quality_gap_closure'
						and bool(task.get('queries', {}).get('evidence'))
					)
				)
				and not (
					support_kind is None
					and preferred_support_kind == 'authority'
					and 'authority' in task.get('missing_support_kinds', [])
				)
			)
			run_authority_lane = (
				support_kind in (None, 'authority')
				and 'authority' in task.get('missing_support_kinds', [])
				and not (
					support_kind is None
					and preferred_support_kind == 'evidence'
					and 'evidence' in task.get('missing_support_kinds', [])
				)
			)
			if run_evidence_lane:
				evidence_query = task.get('queries', {}).get('evidence', [])
				query_text = evidence_query[0] if evidence_query else f'{current_claim} {task.get("claim_element", "")} evidence'
				if not force and self.claim_support.was_follow_up_executed(
					user_id,
					current_claim,
					'evidence',
					query_text,
					cooldown_seconds=cooldown_seconds,
				):
					self.claim_support.record_follow_up_execution(
						user_id=user_id,
						claim_type=current_claim,
						claim_element_id=task.get('claim_element_id'),
						claim_element_text=task.get('claim_element'),
						support_kind='evidence',
						query_text=query_text,
						status='skipped_duplicate',
						metadata=self._build_follow_up_record_metadata(
							task,
							cooldown_seconds=cooldown_seconds,
							query_variants=task.get('queries', {}).get('evidence', []),
						),
					)
					skipped_tasks.append({
						**execution,
						'skipped': {'evidence': {'query': query_text, 'reason': 'duplicate_within_cooldown'}},
					})
				else:
					keywords = self._keywords_from_follow_up_query(
						query_text,
						current_claim,
						task.get('claim_element', ''),
					)
					discovery_result = self.discover_web_evidence(
						keywords=keywords,
						user_id=user_id,
						claim_type=current_claim,
						min_relevance=min_relevance,
					)
					discovery_result_count = self._count_evidence_follow_up_results(discovery_result)
					lane_execution_records.append({
						'support_kind': 'evidence',
						'query_text': query_text,
						'status': 'executed',
						'zero_result': discovery_result_count <= 0,
						'metadata': self._build_follow_up_record_metadata(
							task,
							keywords=keywords,
							query_variants=task.get('queries', {}).get('evidence', []),
							result_count=discovery_result_count,
							stored_result_count=int(discovery_result.get('stored', discovery_result.get('total_records', 0)) or 0)
							if isinstance(discovery_result, dict)
							else 0,
							zero_result=discovery_result_count <= 0,
						),
					})
					execution['executed']['evidence'] = {
						'query': query_text,
						'keywords': keywords,
						'result': discovery_result,
					}
			if run_authority_lane:
				authority_query = task.get('queries', {}).get('authority', [])
				task_query_text = authority_query[0] if authority_query else f'{current_claim} {task.get("claim_element", "")} statute'
				primary_program = self._select_primary_authority_search_program(task)
				program_query_text = str(primary_program.get('query_text') or '').strip() if isinstance(primary_program, dict) else ''
				query_text = program_query_text or task_query_text
				program_jurisdiction = str(primary_program.get('jurisdiction') or '').strip() if isinstance(primary_program, dict) else ''
				program_authority_families = list(primary_program.get('authority_families') or []) if isinstance(primary_program, dict) else []
				primary_program_metadata = primary_program.get('metadata') if isinstance(primary_program, dict) else {}
				if not isinstance(primary_program_metadata, dict):
					primary_program_metadata = {}
				selected_authority_context = {
					'selected_search_program_id': str(primary_program.get('program_id') or ''),
					'selected_search_program_type': str(primary_program.get('program_type') or ''),
					'selected_search_program_intent': str(primary_program.get('authority_intent') or ''),
					'selected_search_program_jurisdiction': program_jurisdiction,
					'selected_search_program_forum': str(primary_program.get('forum') or ''),
					'selected_search_program_bias': str(primary_program_metadata.get('authority_signal_bias') or ''),
					'selected_search_program_rule_bias': str(primary_program_metadata.get('rule_signal_bias') or ''),
					'selected_search_program_graph_gap_bias': str(primary_program_metadata.get('graph_gap_authority_bias') or ''),
					'selected_search_program_families': list(program_authority_families),
					'selected_search_program_defense_themes': list(primary_program_metadata.get('defense_themes') or []),
					'selected_search_program_time_window': dict(primary_program_metadata.get('time_window') or {})
					if isinstance(primary_program_metadata.get('time_window'), dict)
					else {},
				}
				execution.update(selected_authority_context)
				if not force and self.claim_support.was_follow_up_executed(
					user_id,
					current_claim,
					'authority',
					query_text,
					cooldown_seconds=cooldown_seconds,
				):
					self.claim_support.record_follow_up_execution(
						user_id=user_id,
						claim_type=current_claim,
						claim_element_id=task.get('claim_element_id'),
						claim_element_text=task.get('claim_element'),
						support_kind='authority',
						query_text=query_text,
						status='skipped_duplicate',
						metadata=self._build_follow_up_record_metadata(
							task,
							cooldown_seconds=cooldown_seconds,
							query_variants=task.get('queries', {}).get('authority', []),
							task_query=task_query_text,
							effective_query=query_text,
							**selected_authority_context,
							search_program_ids=[
								program.get('program_id')
								for program in (task.get('authority_search_programs') or [])
								if isinstance(program, dict) and program.get('program_id')
							],
							search_program_count=int(
								(task.get('authority_search_program_summary') or {}).get('program_count', 0) or 0
							),
						),
					)
					skipped_tasks.append({
						**execution,
						'skipped': {'authority': {'query': query_text, 'reason': 'duplicate_within_cooldown'}},
					})
				else:
					search_results = self.search_legal_authorities(
						query=query_text,
						claim_type=current_claim,
						jurisdiction=program_jurisdiction or None,
						search_all=True,
						authority_families=program_authority_families or None,
					)
					search_result_counts = {
						key: len(value)
						for key, value in search_results.items()
						if isinstance(value, list)
					}
					search_warning_summary = list(search_results.get('search_warning_summary') or [])
					authority_result_count = self._count_authority_follow_up_results(search_results)
					stored_counts = self.store_legal_authorities(
						search_results,
						claim_type=current_claim,
						search_query=query_text,
						user_id=user_id,
						search_programs=task.get('authority_search_programs', []),
					)
					lane_execution_records.append({
						'support_kind': 'authority',
						'query_text': query_text,
						'status': 'executed',
						'zero_result': authority_result_count <= 0,
						'metadata': self._build_follow_up_record_metadata(
							task,
							search_results=search_result_counts,
							search_warning_summary=search_warning_summary,
							query_variants=task.get('queries', {}).get('authority', []),
							task_query=task_query_text,
							effective_query=query_text,
							**selected_authority_context,
							search_program_ids=[
								program.get('program_id')
								for program in (task.get('authority_search_programs') or [])
								if isinstance(program, dict) and program.get('program_id')
							],
							search_program_count=int(
								(task.get('authority_search_program_summary') or {}).get('program_count', 0) or 0
							),
							result_count=authority_result_count,
							stored_result_count=int(stored_counts.get('total_records', 0) or 0),
							zero_result=authority_result_count <= 0,
						),
					})
					execution['executed']['authority'] = {
						'query': query_text,
						'task_query': task_query_text,
						**selected_authority_context,
						'search_program_summary': task.get('authority_search_program_summary', {}),
						'search_programs': list(task.get('authority_search_programs') or []),
						'search_results': search_result_counts,
						'search_diagnostics': dict(search_results.get('search_diagnostics') or {}),
						'search_warning_summary': search_warning_summary,
						'stored_counts': stored_counts,
					}
			if lane_execution_records:
				post_execution_resolution = ''
				if all(bool(record.get('zero_result')) for record in lane_execution_records):
					post_execution_resolution = 'insufficient_support_after_search'
				for record_index, record in enumerate(lane_execution_records):
					metadata = dict(record.get('metadata') or {})
					if post_execution_resolution and record_index == len(lane_execution_records) - 1:
						metadata['resolution_status'] = post_execution_resolution
						metadata['resolution_applied'] = post_execution_resolution
					self.claim_support.record_follow_up_execution(
						user_id=user_id,
						claim_type=current_claim,
						claim_element_id=task.get('claim_element_id'),
						claim_element_text=task.get('claim_element'),
						support_kind=record.get('support_kind'),
						query_text=record.get('query_text'),
						status=record.get('status') or 'executed',
						metadata=metadata,
					)
				if post_execution_resolution:
					execution['resolution_status'] = post_execution_resolution
					execution['resolution_applied'] = post_execution_resolution
			if execution['executed']:
				executed_tasks.append(execution)

		results['claims'][current_claim] = {
			'task_count': len(executed_tasks),
			'skipped_task_count': len(skipped_tasks),
			'tasks': executed_tasks,
			'skipped_tasks': skipped_tasks,
			'updated_claim_overview': self.get_claim_overview(claim_type=current_claim, user_id=user_id).get('claims', {}).get(current_claim, {}),
			'updated_follow_up_plan': self.get_claim_follow_up_plan(claim_type=current_claim, user_id=user_id).get('claims', {}).get(current_claim, {}),
		}
	if handoff_metadata:
		results.update(handoff_metadata)
	return results
def _apply_intake_answer_to_case_file(
	self,
	question: Dict[str, Any],
	answer: str,
	intake_case_file: Dict[str, Any],
	knowledge_graph,
	*,
	factual_action: Optional[str] = None,
) -> Dict[str, Any]:
	"""Update the structured intake case file from a denoising answer."""
	if not isinstance(intake_case_file, dict):
		intake_case_file = {}
	denoiser = getattr(self, "denoiser", None)
	if not factual_action and denoiser is not None and hasattr(denoiser, "classify_answer_disposition"):
		disposition = denoiser.classify_answer_disposition(answer)
		if disposition in getattr(denoiser, "_NON_FACT_DISPOSITIONS", ()):
			return intake_case_file
	if factual_action:
		refreshed = refresh_intake_case_file(intake_case_file, knowledge_graph, append_snapshot=True)
		return self._sync_factual_activity_to_case_file(refreshed, knowledge_graph)
	normalized_answer = self._normalize_intake_text(answer)
	if not normalized_answer:
		return intake_case_file

	question_type = str(question.get('type') or '').strip().lower()
	context = question.get('context', {}) if isinstance(question.get('context'), dict) else {}
	intake_question_intent = self._build_intake_question_intent_snapshot(question)
	resolved_claim_types = self._resolve_answer_claim_types(intake_case_file, context)
	resolved_element_targets = self._resolve_answer_element_targets(context)
	created_fact: Dict[str, Any] | None = None
	fact_participants = self._extract_fact_participants_from_answer(normalized_answer)
	actor_ref = str(fact_participants.get('actor') or '').strip()
	target_ref = str(fact_participants.get('target') or '').strip()
	location_ref = str(fact_participants.get('location') or '').strip() or self._extract_location_from_text(normalized_answer)

	if question_type == 'timeline':
		existing_timeline_facts = [
			fact for fact in intake_case_file.get('canonical_facts', [])
			if isinstance(fact, dict) and str(fact.get('fact_type') or '').strip().lower() == 'timeline'
		]
		# Try to find an existing stable event record for the same timeline topic so we can
		# update it in place instead of always appending a new record.  Two facts are
		# considered the same event when their normalised text matches exactly (a revision)
		# or when both share the same non-empty `event_id` (a direct ID match).
		target_event_id = str(context.get('event_id') or '').strip()
		normalized_answer_lower = normalized_answer.lower()
		matched_existing: Dict[str, Any] | None = None
		for ef in existing_timeline_facts:
			if not isinstance(ef, dict):
				continue
			ef_event_id = str(ef.get('event_id') or '').strip()
			ef_text = self._normalize_intake_text(ef.get('text') or ef.get('event_label') or '')
			if target_event_id and ef_event_id and ef_event_id == target_event_id:
				matched_existing = ef
				break
			if ef_text and ef_text.lower() == normalized_answer_lower:
				matched_existing = ef
				break
		if matched_existing is not None:
			# Update the stable record in place: refresh the text and any date/participant fields
			# so the event record retains its stable fact_id / event_id.
			new_date = self._extract_date_or_range_from_text(normalized_answer)
			if new_date:
				matched_existing['event_date_or_range'] = new_date
			if actor_ref:
				existing_actors = list(matched_existing.get('actor_ids') or [])
				if actor_ref not in existing_actors:
					existing_actors.append(actor_ref)
				matched_existing['actor_ids'] = existing_actors
			matched_existing['text'] = normalized_answer
			matched_existing['event_label'] = normalized_answer
			matched_existing['intake_question_intent'] = self._merge_intake_question_intent(
				matched_existing.get('intake_question_intent'),
				intake_question_intent,
			)
			for claim_type in resolved_claim_types:
				if claim_type not in (matched_existing.get('claim_types') or []):
					matched_existing.setdefault('claim_types', []).append(claim_type)
			for element_tag in resolved_element_targets:
				if element_tag not in (matched_existing.get('element_tags') or []):
					matched_existing.setdefault('element_tags', []).append(element_tag)
			created_fact = matched_existing
		else:
			created_fact = self._append_canonical_fact(
				intake_case_file,
				text=normalized_answer,
				fact_type='timeline',
				question_type=question_type,
				event_date_or_range=self._extract_date_or_range_from_text(normalized_answer),
				actor_ids=[actor_ref] if actor_ref else None,
				target_ids=[target_ref] if target_ref else None,
				location=location_ref,
				claim_types=resolved_claim_types,
				element_tags=resolved_element_targets,
				materiality='high',
				corroboration_priority='high',
				fact_participants=fact_participants,
				event_support_refs=self._build_authored_event_support_refs(
					fact_id='',
					question_type=question_type,
					intake_question_intent=intake_question_intent,
				),
				intake_question_intent=intake_question_intent,
			)
		created_fact['event_support_refs'] = self._build_authored_event_support_refs(
			fact_id=str(created_fact.get('fact_id') or '').strip(),
			question_type=question_type,
			intake_question_intent=intake_question_intent,
		)
		for existing_fact in existing_timeline_facts:
			if existing_fact is created_fact:
				continue
			existing_text = self._normalize_intake_text(existing_fact.get('text'))
			if existing_text and existing_text.lower() != normalized_answer.lower():
				self._record_case_file_contradiction(
					intake_case_file,
					topic='timeline',
					left_fact=existing_fact,
					right_text=normalized_answer,
				)
				created_fact['status'] = 'contradicted'
				created_fact['contradiction_group_id'] = existing_fact.get('contradiction_group_id')
				break
	elif question_type in {'impact', 'remedy'}:
		created_fact = self._append_canonical_fact(
			intake_case_file,
			text=normalized_answer,
			fact_type='remedy' if question_type == 'remedy' else 'impact',
			question_type=question_type,
			claim_types=resolved_claim_types,
			element_tags=resolved_element_targets,
			materiality='high',
			intake_question_intent=intake_question_intent,
		)
		if question_type == 'impact' and self._normalize_intake_text(answer):
			lower_answer = normalized_answer.lower()
			if any(token in lower_answer for token in ['seek', 'seeking', 'want', 'request', 'asking for', 'compensation', 'refund']):
				self._append_canonical_fact(
					intake_case_file,
					text=normalized_answer,
					fact_type='remedy',
					question_type='remedy',
					intake_question_intent=intake_question_intent,
				)
	elif question_type == 'evidence':
		support_kind = self._infer_support_kind_from_answer(answer, self._extract_proof_lead_type(answer))
		created_fact = self._append_canonical_fact(
			intake_case_file,
			text=normalized_answer,
			fact_type='supporting_evidence',
			question_type=question_type,
			actor_ids=[actor_ref] if actor_ref else None,
			target_ids=[target_ref] if target_ref else None,
			location=location_ref,
			claim_types=resolved_claim_types,
			element_tags=resolved_element_targets,
			materiality='high',
			corroboration_priority='high',
			fact_participants=fact_participants,
			intake_question_intent=intake_question_intent,
		)
		evidence_classes = self._resolve_evidence_classes_for_context(intake_case_file, context)
		lead_type = self._extract_proof_lead_type(answer)
		self._append_proof_lead(
			intake_case_file,
			text=normalized_answer,
			lead_type=lead_type,
			related_fact_ids=[created_fact['fact_id']],
			fact_targets=[created_fact['fact_id']],
			element_targets=resolved_element_targets,
			target_claim_types=resolved_claim_types,
			priority='high' if question.get('priority') == 'high' else 'medium',
			evidence_classes=evidence_classes,
			custodian=self._infer_proof_lead_custodian(answer, lead_type),
			recommended_support_kind=support_kind,
			source_quality_target=self._infer_source_quality_target(support_kind),
			intake_question_intent=intake_question_intent,
		)
	elif question_type == 'responsible_party':
		created_fact = self._append_canonical_fact(
			intake_case_file,
			text=normalized_answer,
			fact_type='responsible_party',
			question_type=question_type,
			actor_ids=[actor_ref or normalized_answer],
			target_ids=[target_ref] if target_ref else None,
			location=location_ref,
			claim_types=resolved_claim_types,
			element_tags=resolved_element_targets,
			fact_participants={
				**fact_participants,
				'actor': actor_ref or normalized_answer,
			},
			materiality='high',
			intake_question_intent=intake_question_intent,
		)
	elif question_type == 'requirement':
		created_fact = self._append_canonical_fact(
			intake_case_file,
			text=normalized_answer,
			fact_type='claim_element',
			question_type=question_type,
			actor_ids=[actor_ref] if actor_ref else None,
			target_ids=[target_ref] if target_ref else None,
			location=location_ref,
			claim_types=resolved_claim_types,
			element_tags=list(resolved_element_targets),
			materiality='high',
			corroboration_priority='high',
			fact_participants=fact_participants,
			intake_question_intent=intake_question_intent,
		)
		target_element_id = self._normalize_intake_text(context.get('requirement_id'))
		requirement_name = self._normalize_intake_text(context.get('requirement_name'))
		candidate_claim_types = [
			str(claim.get('claim_type') or '').strip().lower()
			for claim in intake_case_file.get('candidate_claims', [])
			if isinstance(claim, dict) and claim.get('claim_type')
		]
		matched_element_tags = []
		for claim_type in candidate_claim_types:
			matched = match_required_element_id(claim_type, requirement_name) or match_required_element_id(claim_type, normalized_answer)
			if matched and matched not in matched_element_tags:
				matched_element_tags.append(matched)
		if target_element_id and target_element_id not in matched_element_tags:
			matched_element_tags.append(target_element_id)
		if matched_element_tags:
			created_fact['element_tags'] = matched_element_tags
	elif question_type == 'clarification':
		created_fact = self._append_canonical_fact(
			intake_case_file,
			text=normalized_answer,
			fact_type='clarification',
			question_type=question_type,
			claim_types=resolved_claim_types,
			element_tags=resolved_element_targets,
			intake_question_intent=intake_question_intent,
		)
	elif question_type == 'contradiction':
		contradiction_queue = intake_case_file.setdefault('contradiction_queue', [])
		if isinstance(contradiction_queue, list):
			contradiction_label = self._normalize_intake_text(context.get('contradiction_label'))
			for entry in contradiction_queue:
				if not isinstance(entry, dict):
					continue
				if contradiction_label and self._normalize_intake_text(entry.get('topic')) == contradiction_label:
					entry['status'] = 'resolved'
					entry['current_resolution_status'] = 'resolved'
					entry['resolution'] = normalized_answer
					entry['resolution_notes'] = normalized_answer
					break
		created_fact = self._append_canonical_fact(
			intake_case_file,
			text=normalized_answer,
			fact_type='contradiction_resolution',
			question_type=question_type,
			claim_types=resolved_claim_types,
			element_tags=resolved_element_targets,
			materiality='high',
			corroboration_priority='high',
			intake_question_intent=intake_question_intent,
		)

	temporal_issue_id = self._normalize_intake_text(context.get('temporal_issue_id'))
	if temporal_issue_id:
		temporal_issue_registry = intake_case_file.setdefault('temporal_issue_registry', [])
		if isinstance(temporal_issue_registry, list):
			for entry in temporal_issue_registry:
				if not isinstance(entry, dict):
					continue
				entry_issue_id = self._normalize_intake_text(entry.get('issue_id') or entry.get('source_ref'))
				if entry_issue_id != temporal_issue_id:
					continue
				entry['status'] = 'resolved'
				entry['current_resolution_status'] = 'resolved'
				entry['resolution'] = normalized_answer
				entry['resolution_notes'] = normalized_answer
				entry['answered_by_question_type'] = question_type
				entry['answered_by_candidate_source'] = str(question.get('candidate_source') or '')
				break

	if created_fact and intake_case_file.get('candidate_claims'):
		created_fact['claim_types'] = list(dict.fromkeys(list(created_fact.get('claim_types', []) or []) + resolved_claim_types))

	if created_fact:
		self._author_temporal_case_file_state(
			intake_case_file,
			focus_fact_id=str(created_fact.get('fact_id') or '').strip(),
		)

	self._apply_claim_ambiguity_flags(intake_case_file)

	return self._sync_factual_activity_to_case_file(
		refresh_intake_case_file(intake_case_file, knowledge_graph, append_snapshot=True),
		knowledge_graph,
	)
def get_three_phase_status(self) -> Dict[str, Any]:
	"""Get current status of three-phase process."""
	intake_readiness = self.phase_manager.get_intake_readiness()
	intake_case_file = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {}
	candidate_claims = intake_case_file.get('candidate_claims', []) if isinstance(intake_case_file, dict) else []
	canonical_facts = intake_case_file.get('canonical_facts', []) if isinstance(intake_case_file, dict) else []
	proof_leads = intake_case_file.get('proof_leads', []) if isinstance(intake_case_file, dict) else []
	blocker_follow_up_summary = intake_case_file.get('blocker_follow_up_summary', {}) if isinstance(intake_case_file, dict) else {}
	open_items = intake_case_file.get('open_items', []) if isinstance(intake_case_file, dict) else []
	event_ledger = intake_case_file.get('event_ledger', []) if isinstance(intake_case_file, dict) else []
	temporal_fact_registry = intake_case_file.get('temporal_fact_registry', []) if isinstance(intake_case_file, dict) else []
	temporal_relation_registry = intake_case_file.get('temporal_relation_registry', []) if isinstance(intake_case_file, dict) else []
	temporal_issue_registry = intake_case_file.get('temporal_issue_registry', []) if isinstance(intake_case_file, dict) else []
	claim_temporal_graphs = intake_case_file.get('claim_temporal_graphs', {}) if isinstance(intake_case_file, dict) else {}
	# `timeline_issues` is a stable canonical alias for `temporal_issue_registry`
	timeline_issues = (
		intake_case_file.get('timeline_issues', temporal_issue_registry)
		if isinstance(intake_case_file, dict)
		else temporal_issue_registry
	)
	if not isinstance(timeline_issues, list):
		timeline_issues = temporal_issue_registry
	if not temporal_issue_registry and isinstance(intake_case_file, dict) and isinstance(intake_case_file.get('timeline_issues'), list):
		temporal_issue_registry = intake_case_file.get('timeline_issues')
		timeline_issues = temporal_issue_registry
	if not isinstance(timeline_issues, list):
		timeline_issues = []
	question_candidates = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'question_candidates') or []
	adversarial_intake_priority_summary = (
		self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'adversarial_intake_priority_summary') or {}
	)
	intake_matching_pressure = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_matching_pressure') or {}
	intake_workflow_action_queue = self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_workflow_action_queue') or []
	claim_support_packets = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'claim_support_packets') or {}
	uploaded_evidence_summary = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'uploaded_evidence_summary') or {}
	alignment_evidence_tasks = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_evidence_tasks') or []
	evidence_workflow_action_queue = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'evidence_workflow_action_queue') or []
	alignment_task_updates = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_updates') or []
	alignment_task_update_history = self.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'alignment_task_update_history') or []
	timeline_anchors = intake_case_file.get('timeline_anchors', []) if isinstance(intake_case_file, dict) else []
	timeline_relations = intake_case_file.get('timeline_relations', []) if isinstance(intake_case_file, dict) else []
	timeline_consistency_summary = intake_case_file.get('timeline_consistency_summary', {}) if isinstance(intake_case_file, dict) else {}
	harm_profile = intake_case_file.get('harm_profile', {}) if isinstance(intake_case_file, dict) else {}
	remedy_profile = intake_case_file.get('remedy_profile', {}) if isinstance(intake_case_file, dict) else {}
	complainant_summary_confirmation = intake_case_file.get('complainant_summary_confirmation', {}) if isinstance(intake_case_file, dict) else {}
	claim_support_packet_summary = self._summarize_claim_support_packets(claim_support_packets)
	alignment_task_summary = self._summarize_alignment_evidence_tasks(alignment_evidence_tasks)
	temporal_issue_status_counts: Dict[str, int] = {}
	temporal_issue_severity_counts: Dict[str, int] = {}
	temporal_issue_lane_counts: Dict[str, int] = {}
	temporal_issue_type_counts: Dict[str, int] = {}
	temporal_issue_claim_type_counts: Dict[str, int] = {}
	temporal_issue_element_tag_counts: Dict[str, int] = {}
	temporal_issue_ids: List[str] = []
	temporal_issue_missing_predicates: List[str] = []
	temporal_issue_required_provenance_kinds: List[str] = []
	for issue in temporal_issue_registry if isinstance(temporal_issue_registry, list) else []:
		if not isinstance(issue, dict):
			continue
		issue_id = str(issue.get('issue_id') or '').strip()
		if issue_id and issue_id not in temporal_issue_ids:
			temporal_issue_ids.append(issue_id)
		status_value = str(issue.get('current_resolution_status') or issue.get('status') or '').strip().lower()
		if status_value:
			temporal_issue_status_counts[status_value] = temporal_issue_status_counts.get(status_value, 0) + 1
		severity_value = str(issue.get('severity') or '').strip().lower()
		if severity_value:
			temporal_issue_severity_counts[severity_value] = temporal_issue_severity_counts.get(severity_value, 0) + 1
		lane_value = str(issue.get('recommended_resolution_lane') or '').strip().lower()
		if lane_value:
			temporal_issue_lane_counts[lane_value] = temporal_issue_lane_counts.get(lane_value, 0) + 1
		issue_type_value = str(issue.get('issue_type') or issue.get('category') or '').strip().lower()
		if issue_type_value:
			temporal_issue_type_counts[issue_type_value] = temporal_issue_type_counts.get(issue_type_value, 0) + 1
		for claim_type_value in (issue.get('claim_types') or []):
			normalized_claim_type = str(claim_type_value or '').strip()
			if not normalized_claim_type:
				continue
			temporal_issue_claim_type_counts[normalized_claim_type] = (
				temporal_issue_claim_type_counts.get(normalized_claim_type, 0) + 1
			)
		for element_tag_value in (issue.get('element_tags') or []):
			normalized_element_tag = str(element_tag_value or '').strip()
			if not normalized_element_tag:
				continue
			temporal_issue_element_tag_counts[normalized_element_tag] = (
				temporal_issue_element_tag_counts.get(normalized_element_tag, 0) + 1
			)
		for predicate in issue.get('missing_temporal_predicates') or []:
			normalized_predicate = str(predicate or '').strip()
			if normalized_predicate and normalized_predicate not in temporal_issue_missing_predicates:
				temporal_issue_missing_predicates.append(normalized_predicate)
		for provenance_kind in issue.get('required_provenance_kinds') or []:
			normalized_provenance_kind = str(provenance_kind or '').strip()
			if normalized_provenance_kind and normalized_provenance_kind not in temporal_issue_required_provenance_kinds:
				temporal_issue_required_provenance_kinds.append(normalized_provenance_kind)
	resolved_temporal_issue_count = int(temporal_issue_status_counts.get('resolved', 0) or 0)
	unresolved_temporal_issue_count = max(
		0,
		(len(temporal_issue_registry) if isinstance(temporal_issue_registry, list) else 0) - resolved_temporal_issue_count,
	)
	claim_support_packet_summary = {
		**claim_support_packet_summary,
		'temporal_gap_task_count': int(alignment_task_summary.get('temporal_gap_task_count', 0) or 0),
		'temporal_gap_targeted_task_count': int(alignment_task_summary.get('temporal_gap_targeted_task_count', 0) or 0),
		'temporal_next_action_count': int(alignment_task_summary.get('temporal_next_action_count', 0) or 0),
		'temporal_rule_status_counts': dict(alignment_task_summary.get('temporal_rule_status_counts', {}) or {}),
		'temporal_rule_blocking_reason_counts': dict(alignment_task_summary.get('temporal_rule_blocking_reason_counts', {}) or {}),
		'temporal_resolution_status_counts': dict(alignment_task_summary.get('temporal_resolution_status_counts', {}) or {}),
		'temporal_follow_up_target_counts': dict(alignment_task_summary.get('temporal_follow_up_target_counts', {}) or {}),
		'temporal_question_objective_counts': dict(alignment_task_summary.get('temporal_question_objective_counts', {}) or {}),
		'temporal_proof_criticality_counts': dict(alignment_task_summary.get('temporal_proof_criticality_counts', {}) or {}),
	}
	alignment_task_update_summary = self._summarize_alignment_task_update_status(
		alignment_task_updates,
		alignment_task_update_history,
		alignment_evidence_tasks,
	)
	alignment_validation_focus_summary = self._summarize_alignment_validation_focus(
		alignment_task_updates,
		alignment_task_update_history,
	)
	intake_chronology_readiness = self._build_intake_chronology_readiness(intake_case_file)
	recent_validation_outcome = self._summarize_recent_validation_outcome(
		alignment_task_updates,
		alignment_task_update_history,
	)
	status = {
		'current_phase': self.phase_manager.get_current_phase().value,
		'iteration_count': self.phase_manager.iteration_count,
		'convergence_history': self.phase_manager.loss_history[-10:] if self.phase_manager.loss_history else [],
		'loss_history': self.phase_manager.loss_history if self.phase_manager.loss_history else [],
		'intake_readiness': intake_readiness,
		'candidate_claims': candidate_claims,
		'intake_sections': intake_readiness.get('intake_sections', {}),
		'canonical_fact_summary': {
			'count': len(canonical_facts),
			'facts': canonical_facts,
		},
		'canonical_fact_intent_summary': self._summarize_intake_record_intents(canonical_facts),
		'proof_lead_summary': {
			'count': len(proof_leads),
			'proof_leads': proof_leads,
		},
		'proof_lead_collection_summary': self._summarize_proof_lead_collection(proof_leads),
		'blocker_follow_up_summary': blocker_follow_up_summary if isinstance(blocker_follow_up_summary, dict) else {},
		'open_items': open_items if isinstance(open_items, list) else [],
		'open_item_summary': self._summarize_open_intake_work(open_items),
		'event_ledger': event_ledger if isinstance(event_ledger, list) else [],
		'event_ledger_summary': {
			'count': len(event_ledger) if isinstance(event_ledger, list) else 0,
			'events': event_ledger if isinstance(event_ledger, list) else [],
		},
		'proof_lead_intent_summary': self._summarize_intake_record_intents(proof_leads),
		'temporal_fact_registry': temporal_fact_registry if isinstance(temporal_fact_registry, list) else [],
		'temporal_fact_registry_summary': {
			'count': len(temporal_fact_registry) if isinstance(temporal_fact_registry, list) else 0,
			'facts': temporal_fact_registry if isinstance(temporal_fact_registry, list) else [],
		},
		'timeline_anchors': timeline_anchors if isinstance(timeline_anchors, list) else [],
		'timeline_anchor_summary': {
			'count': len(timeline_anchors) if isinstance(timeline_anchors, list) else 0,
			'anchors': timeline_anchors if isinstance(timeline_anchors, list) else [],
		},
		'temporal_relation_registry': (
			temporal_relation_registry if isinstance(temporal_relation_registry, list) else []
		),
		'temporal_relation_registry_summary': {
			'count': len(temporal_relation_registry) if isinstance(temporal_relation_registry, list) else 0,
			'relations': temporal_relation_registry if isinstance(temporal_relation_registry, list) else [],
		},
		'timeline_relations': timeline_relations if isinstance(timeline_relations, list) else [],
		'timeline_relation_summary': {
			'count': len(timeline_relations) if isinstance(timeline_relations, list) else 0,
			'relations': timeline_relations if isinstance(timeline_relations, list) else [],
		},
		'temporal_issue_registry': temporal_issue_registry if isinstance(temporal_issue_registry, list) else [],
		'timeline_issues': timeline_issues if isinstance(timeline_issues, list) else [],
		'timeline_issues_summary': {
			'count': len(timeline_issues) if isinstance(timeline_issues, list) else 0,
			'issues': timeline_issues if isinstance(timeline_issues, list) else [],
			'issue_ids': temporal_issue_ids,
			'status_counts': temporal_issue_status_counts,
			'severity_counts': temporal_issue_severity_counts,
			'lane_counts': temporal_issue_lane_counts,
			'issue_type_counts': temporal_issue_type_counts,
			'claim_type_counts': temporal_issue_claim_type_counts,
			'element_tag_counts': temporal_issue_element_tag_counts,
			'missing_temporal_predicates': temporal_issue_missing_predicates,
			'required_provenance_kinds': temporal_issue_required_provenance_kinds,
			'resolved_count': resolved_temporal_issue_count,
			'unresolved_count': unresolved_temporal_issue_count,
		},
		'timeline_issue_summary': {
			'count': len(timeline_issues),
			'issues': timeline_issues,
			'issue_ids': temporal_issue_ids,
			'status_counts': temporal_issue_status_counts,
			'severity_counts': temporal_issue_severity_counts,
			'lane_counts': temporal_issue_lane_counts,
			'issue_type_counts': temporal_issue_type_counts,
			'claim_type_counts': temporal_issue_claim_type_counts,
			'element_tag_counts': temporal_issue_element_tag_counts,
			'missing_temporal_predicates': temporal_issue_missing_predicates,
			'required_provenance_kinds': temporal_issue_required_provenance_kinds,
			'resolved_count': resolved_temporal_issue_count,
			'unresolved_count': unresolved_temporal_issue_count,
		},
		'temporal_issue_registry_summary': {
			'count': len(temporal_issue_registry) if isinstance(temporal_issue_registry, list) else 0,
			'issues': temporal_issue_registry if isinstance(temporal_issue_registry, list) else [],
			'issue_ids': temporal_issue_ids,
			'status_counts': temporal_issue_status_counts,
			'severity_counts': temporal_issue_severity_counts,
			'lane_counts': temporal_issue_lane_counts,
			'issue_type_counts': temporal_issue_type_counts,
			'claim_type_counts': temporal_issue_claim_type_counts,
			'element_tag_counts': temporal_issue_element_tag_counts,
			'missing_temporal_predicates': temporal_issue_missing_predicates,
			'required_provenance_kinds': temporal_issue_required_provenance_kinds,
			'resolved_count': resolved_temporal_issue_count,
			'unresolved_count': unresolved_temporal_issue_count,
		},
		'claim_temporal_graphs': claim_temporal_graphs if isinstance(claim_temporal_graphs, dict) else {},
		'claim_temporal_graph_summary': {
			'contract_version': (
				str(claim_temporal_graphs.get('contract_version') or '')
				if isinstance(claim_temporal_graphs, dict)
				else ''
			),
			'claim_count': (
				int(claim_temporal_graphs.get('claim_count', 0) or 0)
				if isinstance(claim_temporal_graphs, dict)
				else 0
			),
			'claim_keys': (
				list(claim_temporal_graphs.get('claim_keys', []) or [])
				if isinstance(claim_temporal_graphs, dict)
				else []
			),
			'fact_ids': (
				list(claim_temporal_graphs.get('fact_ids', []) or [])
				if isinstance(claim_temporal_graphs, dict)
				else []
			),
			'relation_ids': (
				list(claim_temporal_graphs.get('relation_ids', []) or [])
				if isinstance(claim_temporal_graphs, dict)
				else []
			),
			'issue_ids': (
				list(claim_temporal_graphs.get('issue_ids', []) or [])
				if isinstance(claim_temporal_graphs, dict)
				else []
			),
		},
		'intake_chronology_readiness': intake_chronology_readiness,
		'timeline_consistency_summary': (
			timeline_consistency_summary if isinstance(timeline_consistency_summary, dict) else {}
		),
		'harm_profile': harm_profile if isinstance(harm_profile, dict) else {},
		'remedy_profile': remedy_profile if isinstance(remedy_profile, dict) else {},
		'complainant_summary_confirmation': complainant_summary_confirmation if isinstance(complainant_summary_confirmation, dict) else {},
		'intake_matching_summary': self._summarize_intake_matching_pressure(intake_matching_pressure),
		'intake_workflow_action_queue': intake_workflow_action_queue if isinstance(intake_workflow_action_queue, list) else [],
		'intake_workflow_action_summary': self._summarize_intake_workflow_action_queue(intake_workflow_action_queue),
		'intake_legal_targeting_summary': self._summarize_intake_legal_targeting(
			intake_matching_pressure,
			question_candidates,
		),
		'question_candidate_summary': self._summarize_question_candidates(question_candidates),
		'adversarial_intake_priority_summary': (
			adversarial_intake_priority_summary
			if isinstance(adversarial_intake_priority_summary, dict)
			else {}
		),
		'claim_support_packet_summary': claim_support_packet_summary,
		'uploaded_evidence_summary': uploaded_evidence_summary if isinstance(uploaded_evidence_summary, dict) else {},
		'intake_evidence_alignment_summary': self._summarize_intake_evidence_alignment(
			intake_case_file,
			claim_support_packets,
		),
		'alignment_evidence_tasks': alignment_evidence_tasks if isinstance(alignment_evidence_tasks, list) else [],
		'evidence_workflow_action_queue': evidence_workflow_action_queue if isinstance(evidence_workflow_action_queue, list) else [],
		'evidence_workflow_action_summary': self._summarize_evidence_workflow_action_queue(evidence_workflow_action_queue),
		'document_provenance_summary': self._get_document_provenance_summary(),
		'document_grounding_lane_outcome_summary': self._get_document_grounding_lane_outcome_summary(),
		'document_grounding_improvement_next_action': self._get_document_grounding_improvement_next_action(
			provisional_evidence_workflow_action_queue=evidence_workflow_action_queue,
			alignment_evidence_tasks=alignment_evidence_tasks,
		),
		'document_grounding_recovery_action': self._get_document_grounding_recovery_action(
			provisional_evidence_workflow_action_queue=evidence_workflow_action_queue,
			alignment_evidence_tasks=alignment_evidence_tasks,
		),
		'alignment_task_summary': alignment_task_summary,
		'alignment_task_updates': alignment_task_updates if isinstance(alignment_task_updates, list) else [],
		'alignment_task_update_history': alignment_task_update_history if isinstance(alignment_task_update_history, list) else [],
		'alignment_task_update_summary': alignment_task_update_summary,
		'alignment_validation_focus_summary': alignment_validation_focus_summary,
		'recent_validation_outcome': recent_validation_outcome,
		'alignment_promotion_drift_summary': self._summarize_alignment_promotion_drift(
			alignment_task_update_summary,
			claim_support_packet_summary,
		),
		'intake_contradictions': {
			'candidate_count': intake_readiness.get('contradiction_count', 0),
			'candidates': intake_readiness.get('contradictions', []),
		},
		'interview_stop': (
			dict(self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'interview_stop') or {})
			if isinstance(self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'interview_stop'), dict)
			else {}
		),
		'stopping_policy': self._current_stopping_policy(),
		'intentional_user_wait': (
			dict(self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intentional_user_wait') or {})
			if isinstance(self.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intentional_user_wait'), dict)
			else {}
		),
		'phase_completion': {
			'intake': self.phase_manager.is_phase_complete(ComplaintPhase.INTAKE),
			'evidence': self.phase_manager.is_phase_complete(ComplaintPhase.EVIDENCE),
			'formalization': self.phase_manager.is_phase_complete(ComplaintPhase.FORMALIZATION)
		},
		'evidence_readiness': self.phase_manager.get_evidence_readiness(),
		'reranking_metrics': self.get_reranker_metrics(),
		'next_action': self.phase_manager.get_next_action()
	}
	status.update(self._get_confirmed_intake_summary_handoff())
	return status
