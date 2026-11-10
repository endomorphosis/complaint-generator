"""Follow-up query builders delegated from Mediator."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from claim_support_review import _build_confirmed_intake_summary_handoff_metadata


def _build_follow_up_queries(
	self,
	claim_type: str,
	element_text: str,
	missing_support_kinds: List[str],
	support_by_kind: Dict[str, Any] = None,
	recommended_action: str = '',
	validation_status: str = '',
	proof_gaps: List[Dict[str, Any]] = None,
	proof_decision_trace: Dict[str, Any] = None,
	authority_treatment_summary: Dict[str, Any] = None,
	rule_candidate_context: Dict[str, Any] = None,
	missing_fact_bundle: List[str] = None,
	temporal_rule_profile: Dict[str, Any] = None,
) -> Dict[str, List[str]]:
	queries: Dict[str, List[str]] = {}
	proof_gap_types = self._extract_proof_gap_types(proof_gaps or [])
	decision_trace = proof_decision_trace if isinstance(proof_decision_trace, dict) else {}
	support_kind_counts = support_by_kind if isinstance(support_by_kind, dict) else {}
	treatment_summary = authority_treatment_summary if isinstance(authority_treatment_summary, dict) else {}
	rule_context = rule_candidate_context if isinstance(rule_candidate_context, dict) else {}
	temporal_profile = temporal_rule_profile if isinstance(temporal_rule_profile, dict) else {}
	rule_texts = list(rule_context.get('top_rule_texts') or [])
	rule_types = [str(value).replace('_', ' ') for value in (rule_context.get('top_rule_types') or []) if value]
	primary_rule_text = rule_texts[0] if rule_texts else ''
	exception_rule_text = ''
	for candidate in rule_context.get('rule_candidates', []) or []:
		if not isinstance(candidate, dict):
			continue
		if str(candidate.get('rule_type') or '') == 'exception' and candidate.get('rule_text'):
			exception_rule_text = self._normalize_rule_query_text(candidate.get('rule_text'))
			break
	bundle_terms = self._fact_bundle_query_terms(missing_fact_bundle)
	primary_bundle_term = bundle_terms[0] if bundle_terms else ''
	secondary_bundle_term = bundle_terms[1] if len(bundle_terms) > 1 else ''
	gap_focus = ' '.join(
		gap_type.replace('_', ' ')
		for gap_type in proof_gap_types
		if gap_type != 'contradiction_candidates'
	)[:80].strip()
	temporal_follow_ups = [
		follow_up
		for follow_up in (temporal_profile.get('recommended_follow_ups') or [])
		if isinstance(follow_up, dict)
	]
	temporal_reason_fragments = [
		self._normalize_rule_query_text(reason)
		for reason in list(temporal_profile.get('blocking_reasons') or [])
		if self._normalize_rule_query_text(reason)
	]
	for follow_up in temporal_follow_ups:
		reason = self._normalize_rule_query_text(follow_up.get('reason'))
		if reason:
			temporal_reason_fragments.append(reason)
	primary_temporal_reason = temporal_reason_fragments[0] if temporal_reason_fragments else ''
	secondary_temporal_reason = temporal_reason_fragments[1] if len(temporal_reason_fragments) > 1 else ''

	def _compose_query(*parts: str) -> str:
		return ' '.join(part for part in parts if part).strip()

	contradiction_targeted = validation_status == 'contradicted' and bool(missing_support_kinds)
	reasoning_targeted = self._is_reasoning_gap_follow_up(proof_gap_types, decision_trace)
	temporal_rule_targeted = self._is_temporal_rule_gap_follow_up(
		proof_gap_types,
		decision_trace,
		temporal_profile,
	)
	fact_gap_targeted = recommended_action == 'collect_fact_support'
	adverse_authority_targeted = recommended_action == 'review_adverse_authority'
	ontology_quality_targeted = recommended_action == 'improve_ontology_quality' and not contradiction_targeted and not reasoning_targeted
	quality_targeted = recommended_action == 'improve_parse_quality' and not contradiction_targeted and not reasoning_targeted
	target_support_kinds = list(missing_support_kinds)
	if ontology_quality_targeted and not target_support_kinds:
		target_support_kinds = ['evidence']
	if quality_targeted and not target_support_kinds:
		target_support_kinds = [
			kind for kind, count in support_kind_counts.items()
			if int(count or 0) > 0
		]
		if not target_support_kinds:
			target_support_kinds = ['evidence']
	if 'evidence' in target_support_kinds:
		if contradiction_targeted:
			queries['evidence'] = [
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'contradictory evidence rebuttal', gap_focus),
				_compose_query(f'"{element_text}"', 'corroborating records inconsistency', claim_type),
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'timeline witness statement conflict'),
			]
		elif adverse_authority_targeted:
			queries['evidence'] = [
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'facts distinguish adverse authority', exception_rule_text or primary_rule_text),
				_compose_query(f'"{element_text}"', 'rebuttal evidence questioned authority', claim_type, exception_rule_text),
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'record facts overcome adverse treatment', ' '.join(rule_types[:2])),
			]
		elif temporal_rule_targeted:
			queries['evidence'] = [
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'timeline chronology dated record', primary_temporal_reason),
				_compose_query(f'"{element_text}"', 'protected activity adverse action timeline', secondary_temporal_reason or primary_temporal_reason, claim_type),
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'event sequence date anchor testimony document', primary_temporal_reason),
			]
		elif fact_gap_targeted:
			queries['evidence'] = [
				_compose_query(f'"{claim_type}"', f'"{element_text}"', primary_bundle_term, f'"{primary_rule_text}"' if primary_rule_text else '', 'supporting facts evidence'),
				_compose_query(f'"{element_text}"', secondary_bundle_term or primary_bundle_term, f'"{exception_rule_text}"' if exception_rule_text else '', 'fact pattern records witness timeline', claim_type),
				_compose_query(f'"{claim_type}"', f'"{element_text}"', primary_bundle_term, 'documents showing predicate satisfaction', f'"{primary_rule_text}"' if primary_rule_text else ' '.join(rule_types[:2])),
			]
		elif reasoning_targeted:
			queries['evidence'] = [
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'supporting evidence formal proof', gap_focus),
				_compose_query(f'"{element_text}"', 'corroborating records legal elements', claim_type, gap_focus),
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'evidence burden of proof'),
			]
		elif ontology_quality_targeted:
			queries['evidence'] = [
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'knowledge graph missing entity relationship source detail'),
				_compose_query(f'"{element_text}"', 'support graph complete facts entities relationships', claim_type),
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'document source context graph relation'),
			]
		elif quality_targeted:
			queries['evidence'] = [
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'clearer copy OCR readable evidence'),
				_compose_query(f'"{element_text}"', 'better scan legible document witness record', claim_type),
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'original PDF attachment readable'),
			]
		else:
			queries['evidence'] = [
				_compose_query(f'"{claim_type}"', f'"{element_text}"', primary_bundle_term, 'evidence'),
				_compose_query(f'"{element_text}"', secondary_bundle_term or primary_bundle_term, 'documentation', claim_type),
				_compose_query(f'"{element_text}"', primary_bundle_term, 'facts witness records', claim_type),
			]
	if 'authority' in target_support_kinds:
		if contradiction_targeted:
			queries['authority'] = [
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'contradiction case law', gap_focus),
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'conflicting evidence burden of proof'),
				_compose_query(f'"{element_text}"', 'inconsistent statements legal standard', claim_type),
			]
		elif adverse_authority_targeted:
			adverse_terms = ' '.join(
				str(name).replace('_', ' ')
				for name, count in (treatment_summary.get('treatment_type_counts') or {}).items()
				if int(count or 0) > 0
			)[:80].strip()
			queries['authority'] = [
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'distinguish questioned authority later treatment', adverse_terms),
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'adverse authority exception limitation', f'"{exception_rule_text}"' if exception_rule_text else ''),
				_compose_query(f'"{element_text}"', 'good law treatment distinguishing case', claim_type),
			]
		elif temporal_rule_targeted:
			queries['authority'] = [
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'temporal causation chronology case law', primary_temporal_reason),
				_compose_query(f'"{element_text}"', 'protected activity before adverse action precedent', claim_type, secondary_temporal_reason),
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'temporal proximity ordering legal standard'),
			]
		elif reasoning_targeted:
			queries['authority'] = [
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'formal proof case law', gap_focus),
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'legal standard burden of proof', gap_focus),
				_compose_query(f'"{element_text}"', 'formal elements precedent', claim_type),
			]
		elif ontology_quality_targeted:
			queries['authority'] = [
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'legal element relationship authority ontology'),
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'case law fact pattern relationship elements'),
				_compose_query(f'"{element_text}"', 'authority connects facts legal element', claim_type),
			]
		elif quality_targeted:
			queries['authority'] = [
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'official statute opinion PDF text'),
				_compose_query(f'"{element_text}"', 'authoritative source readable full text', claim_type),
				_compose_query(f'"{claim_type}"', f'"{element_text}"', 'certified opinion clear scan'),
			]
		else:
			queries['authority'] = [
				_compose_query(f'"{claim_type}"', f'"{element_text}"', primary_bundle_term, 'statute'),
				_compose_query(f'"{claim_type}"', f'"{element_text}"', secondary_bundle_term or primary_bundle_term, 'case law'),
				_compose_query(f'"{element_text}"', primary_bundle_term, 'legal elements', claim_type),
			]
	return queries

def _build_follow_up_record_metadata(self, task: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
	graph_summary = ((task.get('graph_support') or {}).get('summary', {})) if isinstance(task.get('graph_support'), dict) else {}
	graph_results = ((task.get('graph_support') or {}).get('results', [])) if isinstance(task.get('graph_support'), dict) else []
	adaptive_retry_state = task.get('adaptive_retry_state', {}) if isinstance(task.get('adaptive_retry_state'), dict) else {}
	rule_candidate_context = task.get('rule_candidate_context', {}) if isinstance(task.get('rule_candidate_context'), dict) else {}

	def _count_result_field(field_name: str) -> Dict[str, int]:
		counts: Dict[str, int] = {}
		for result in graph_results if isinstance(graph_results, list) else []:
			if not isinstance(result, dict):
				continue
			value = str(result.get(field_name) or '').strip()
			if not value:
				continue
			counts[value] = counts.get(value, 0) + 1
		return counts

	def _primary_count_key(counts: Dict[str, int]) -> str:
		if not counts:
			return ''
		return sorted(counts.items(), key=lambda item: (-int(item[1] or 0), str(item[0])))[0][0]

	source_family_counts = _count_result_field('source_family')
	record_scope_counts = _count_result_field('record_scope')
	artifact_family_counts = _count_result_field('artifact_family')
	corpus_family_counts = _count_result_field('corpus_family')
	content_origin_counts = _count_result_field('content_origin')
	metadata = {
		'execution_mode': task.get('execution_mode', 'retrieve_support'),
		'validation_status': task.get('validation_status', ''),
		'recommended_action': task.get('recommended_action', ''),
		'requires_manual_review': task.get('requires_manual_review', False),
		'reasoning_backed': task.get('reasoning_backed', False),
		'resolution_applied': task.get('resolution_applied', ''),
		'proof_decision_source': task.get('proof_decision_source', ''),
		'logic_provable_count': int(task.get('logic_provable_count', 0) or 0),
		'logic_unprovable_count': int(task.get('logic_unprovable_count', 0) or 0),
		'ontology_validation_signal': task.get('ontology_validation_signal', ''),
		'proof_gap_count': int(task.get('proof_gap_count', 0) or 0),
		'proof_gap_types': list(task.get('proof_gap_types') or []),
		'temporal_rule_profile_id': str(task.get('temporal_rule_profile_id') or ''),
		'temporal_rule_status': str(task.get('temporal_rule_status') or ''),
		'temporal_rule_blocking_reasons': list(task.get('temporal_rule_blocking_reasons') or []),
		'temporal_rule_follow_ups': list(task.get('temporal_rule_follow_ups') or []),
		'temporal_next_actions': [dict(action) for action in (task.get('temporal_next_actions') or []) if isinstance(action, dict)],
		'temporal_next_action_count': int(task.get('temporal_next_action_count', 0) or len(task.get('temporal_next_actions') or [])),
		'temporal_missingness_kind': str(task.get('temporal_missingness_kind') or ''),
		'temporal_issue_ids': list(task.get('temporal_issue_ids') or []),
		'missing_temporal_predicates': list(task.get('missing_temporal_predicates') or []),
		'required_temporal_predicates': list(task.get('required_temporal_predicates') or []),
		'required_provenance_kinds': list(task.get('required_provenance_kinds') or []),
		'missing_support_kinds': list(task.get('missing_support_kinds') or []),
		'missing_fact_bundle': list(task.get('missing_fact_bundle') or []),
		'satisfied_fact_bundle': list(task.get('satisfied_fact_bundle') or []),
		'primary_missing_fact': next((str(item).strip() for item in (task.get('missing_fact_bundle') or []) if str(item).strip()), ''),
		'follow_up_focus': task.get('follow_up_focus', ''),
		'query_strategy': task.get('query_strategy', ''),
		'source_preferences': task.get('source_preferences', {}),
		'time_window': task.get('time_window', {}),
		'authority_intent': task.get('authority_intent', ''),
		'adaptive_retry_applied': bool(adaptive_retry_state.get('applied', False)),
		'adaptive_retry_reason': adaptive_retry_state.get('reason', ''),
		'adaptive_query_strategy': adaptive_retry_state.get('adaptive_query_strategy', ''),
		'adaptive_priority_penalty': int(adaptive_retry_state.get('priority_penalty', 0) or 0),
		'adaptive_zero_result_attempt_count': int(adaptive_retry_state.get('zero_result_attempt_count', 0) or 0),
		'adaptive_successful_result_attempt_count': int(adaptive_retry_state.get('successful_result_attempt_count', 0) or 0),
		'graph_gap_context': dict(task.get('graph_gap_context') or {}),
		'graph_gap_query': dict(task.get('graph_gap_query') or {}),
		'graph_support_strength': task.get('graph_support_strength', ''),
		'graph_support_summary': {
			'total_fact_count': int(graph_summary.get('total_fact_count', 0) or 0),
			'unique_fact_count': int(graph_summary.get('unique_fact_count', 0) or 0),
			'duplicate_fact_count': int(graph_summary.get('duplicate_fact_count', 0) or 0),
			'semantic_cluster_count': int(graph_summary.get('semantic_cluster_count', 0) or 0),
			'semantic_duplicate_count': int(graph_summary.get('semantic_duplicate_count', 0) or 0),
			'support_by_kind': dict(graph_summary.get('support_by_kind') or {}),
			'support_by_source': dict(graph_summary.get('support_by_source') or {}),
			'source_family_counts': source_family_counts,
			'record_scope_counts': record_scope_counts,
			'artifact_family_counts': artifact_family_counts,
			'corpus_family_counts': corpus_family_counts,
			'content_origin_counts': content_origin_counts,
		},
		'source_family': _primary_count_key(source_family_counts),
		'record_scope': _primary_count_key(record_scope_counts),
		'artifact_family': _primary_count_key(artifact_family_counts),
		'corpus_family': _primary_count_key(corpus_family_counts),
		'content_origin': _primary_count_key(content_origin_counts),
		'authority_treatment_summary': task.get('authority_treatment_summary', {}),
		'authority_rule_candidate_summary': task.get('authority_rule_candidate_summary', {}),
		'support_quality_summary': task.get('support_quality_summary', {}),
		'quality_signal_counts': dict(task.get('quality_signal_counts') or {}),
		'primary_quality_signal': dict(task.get('primary_quality_signal') or {}),
		'quality_follow_up_action': task.get('quality_follow_up_action', ''),
		'ontology_quality': dict(task.get('ontology_quality') or {}),
		'ontology_gap_types': list(task.get('ontology_gap_types') or []),
		'ontology_quality_gap_count': int(task.get('ontology_quality_gap_count', 0) or 0),
		'ontology_has_blocking_gaps': bool(task.get('ontology_has_blocking_gaps', False)),
		'rule_candidate_focus': {
			'candidate_count': len(rule_candidate_context.get('rule_candidates', []) or []),
			'top_rule_types': list(rule_candidate_context.get('top_rule_types', []) or []),
			'top_rule_texts': list(rule_candidate_context.get('top_rule_texts', []) or []),
			'top_rule_passages': list(rule_candidate_context.get('top_rule_passages', []) or []),
			'parse_lineages': list(rule_candidate_context.get('parse_lineages', []) or []),
		},
	}
	for key, value in extra.items():
		if value is not None:
			metadata[key] = value
	handoff_metadata = _build_confirmed_intake_summary_handoff_metadata(self)
	if handoff_metadata.get('intake_summary_handoff') and 'intake_summary_handoff' not in metadata:
		metadata['intake_summary_handoff'] = handoff_metadata['intake_summary_handoff']
	return metadata

def _build_follow_up_source_preferences(
	self,
	task: Dict[str, Any],
) -> Dict[str, Any]:
	focus = str(task.get('follow_up_focus') or '')
	preferred_support_kind = str(task.get('preferred_support_kind') or '').strip().lower()
	evidence_classes = [
		str(item).strip().lower()
		for item in (task.get('preferred_evidence_classes') or [])
		if str(item).strip()
	]
	source_types: List[str] = []
	artifact_families: List[str] = []
	authority_families: List[str] = []
	archive_first = False
	live_web_ok = True

	if preferred_support_kind == 'authority' or 'authority' in task.get('missing_support_kinds', []):
		authority_families.extend(['statute', 'regulation', 'case_law'])
	if preferred_support_kind in {'evidence', 'testimony'} or 'evidence' in task.get('missing_support_kinds', []):
		source_types.extend(['evidence', 'web'])
		artifact_families.extend(['archived_web_page', 'live_web_page'])
		archive_first = True
	if (
		preferred_support_kind == 'testimony'
		or focus == 'temporal_gap_closure'
		or any('testimony' in item or 'witness' in item for item in evidence_classes)
	):
		source_types.insert(0, 'testimony')
	if focus in {'temporal_gap_closure', 'contradiction_resolution'}:
		source_types.extend(['evidence', 'testimony'])
		artifact_families.insert(0, 'archived_web_page')
		archive_first = True
	if focus == 'ontology_quality_gap_closure':
		source_types.extend(['evidence', 'testimony'])
		artifact_families.extend(['archived_web_page', 'live_web_page'])
		archive_first = True
	if focus in {'adverse_authority_review', 'confirm_good_law', 'find_better_authority'}:
		authority_families = ['case_law', 'statute', 'regulation']
	if focus == 'parse_quality_improvement':
		artifact_families = ['original_pdf', 'official_html', 'archived_web_page']
		archive_first = True

	return {
		'preferred_support_kind': preferred_support_kind,
		'source_types': list(dict.fromkeys([item for item in source_types if item])),
		'artifact_families': list(dict.fromkeys([item for item in artifact_families if item])),
		'authority_families': list(dict.fromkeys([item for item in authority_families if item])),
		'evidence_classes': evidence_classes,
		'archive_first': archive_first,
		'live_web_allowed': live_web_ok,
		'deduplicate_by': ['query_hash', 'url', 'citation', 'semantic_cluster'],
	}

def _refresh_follow_up_task_queries(self, claim_type: str, task: Dict[str, Any]) -> Dict[str, Any]:
	adaptive_retry_state = task.get('adaptive_retry_state') if isinstance(task.get('adaptive_retry_state'), dict) else {}
	adaptive_standard = bool(adaptive_retry_state.get('applied')) and str(adaptive_retry_state.get('adaptive_query_strategy') or '') == 'standard_gap_targeted'
	resolved_standard = bool(task.get('manual_review_resolved')) and str(task.get('query_strategy') or '') == 'standard_gap_targeted'
	use_standard_queries = adaptive_standard or resolved_standard
	recommended_action = str(task.get('validation_recommended_action') or task.get('recommended_action') or '')
	if task.get('follow_up_focus') == 'ontology_quality_gap_closure' and not recommended_action:
		recommended_action = str(task.get('quality_follow_up_action') or 'improve_ontology_quality')
	queries = self._build_follow_up_queries(
		claim_type,
		str(task.get('claim_element') or ''),
		list(task.get('missing_support_kinds') or []),
		support_by_kind=task.get('support_by_kind') if isinstance(task.get('support_by_kind'), dict) else {},
		recommended_action='' if use_standard_queries else recommended_action,
		validation_status='' if use_standard_queries else str(task.get('validation_status') or ''),
		proof_gaps=[] if use_standard_queries else list(task.get('proof_gaps') or []),
		proof_decision_trace={}
		if use_standard_queries else {
			'decision_source': str(task.get('proof_decision_source') or ''),
			'logic_provable_count': int(task.get('logic_provable_count', 0) or 0),
			'logic_unprovable_count': int(task.get('logic_unprovable_count', 0) or 0),
			'ontology_validation_signal': str(task.get('ontology_validation_signal') or ''),
		},
		authority_treatment_summary=task.get('authority_treatment_summary') if isinstance(task.get('authority_treatment_summary'), dict) else {},
		rule_candidate_context=task.get('rule_candidate_context') if isinstance(task.get('rule_candidate_context'), dict) else {},
		missing_fact_bundle=list(task.get('missing_fact_bundle') or []),
		temporal_rule_profile=task.get('temporal_rule_profile') if isinstance(task.get('temporal_rule_profile'), dict) else {},
	)
	recommended_queries = [
		str(item).strip()
		for item in (task.get('recommended_queries') or [])
		if str(item).strip()
	]
	if recommended_queries:
		preferred_support_kind = str(task.get('preferred_support_kind') or '').strip().lower()
		lane = 'authority' if preferred_support_kind == 'authority' else 'evidence'
		existing_queries = [
			str(item).strip()
			for item in (queries.get(lane) or [])
			if str(item).strip()
		]
		queries[lane] = list(dict.fromkeys(recommended_queries + existing_queries))
	task['queries'] = queries
	return task

def _build_follow_up_time_window(
	self,
	task: Dict[str, Any],
	temporal_rule_profile: Dict[str, Any] = None,
) -> Dict[str, Any]:
	profile = temporal_rule_profile if isinstance(temporal_rule_profile, dict) else {}
	temporal_follow_ups = [
		follow_up for follow_up in (profile.get('recommended_follow_ups') or [])
		if isinstance(follow_up, dict)
	]
	blocking_reasons = [
		str(reason).strip()
		for reason in (profile.get('blocking_reasons') or [])
		if str(reason).strip()
	]
	anchor_ids = list(dict.fromkeys([
		*list(task.get('temporal_fact_ids') or []),
		*list(task.get('temporal_relation_ids') or []),
		*list(task.get('temporal_issue_ids') or []),
	]))
	window = {
		'time_window_type': 'temporal_rule_window' if profile else '',
		'profile_id': str(profile.get('profile_id') or task.get('temporal_rule_profile_id') or ''),
		'status': str(profile.get('status') or task.get('temporal_rule_status') or ''),
		'anchor_ids': anchor_ids,
		'blocking_reasons': blocking_reasons,
		'follow_up_count': len(temporal_follow_ups),
		'query_terms': [],
	}
	terms: List[str] = []
	for value in [
		*blocking_reasons,
		*(str(item.get('reason') or '') for item in temporal_follow_ups),
	]:
		for token in re.findall(r'[a-z0-9]+', value.lower()):
			if token in {'temporal', 'ordering', 'before', 'after', 'during', 'within', 'deadline', 'notice', 'date', 'days', 'timeline', 'chronology'} and token not in terms:
				terms.append(token)
	window['query_terms'] = terms[:8]
	if not any(window.values()):
		return {}
	return window

def _should_suppress_follow_up_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
	if task.get('validation_status') == 'contradicted' and not task.get('manual_review_resolved'):
		return {
			'suppress': False,
			'reason': '',
		}
	if task.get('follow_up_focus') in {
		'reasoning_gap_closure',
		'temporal_gap_closure',
		'parse_quality_improvement',
		'ontology_quality_gap_closure',
	}:
		return {
			'suppress': False,
			'reason': '',
		}
	if task.get('follow_up_focus') in {'adverse_authority_review', 'confirm_good_law', 'find_better_authority'}:
		return {
			'suppress': False,
			'reason': '',
		}
	graph_summary = (task.get('graph_support') or {}).get('summary', {})
	semantic_cluster_count = int(
		graph_summary.get('semantic_cluster_count', graph_summary.get('unique_fact_count', graph_summary.get('total_fact_count', 0))) or 0
	)
	semantic_duplicate_count = int(graph_summary.get('semantic_duplicate_count', graph_summary.get('duplicate_fact_count', 0)) or 0)
	strength = task.get('graph_support_strength', 'none')
	if strength == 'strong' and semantic_cluster_count > 0 and semantic_duplicate_count >= semantic_cluster_count:
		return {
			'suppress': True,
			'reason': 'existing_support_high_duplication',
		}
	return {
		'suppress': False,
		'reason': '',
	}
