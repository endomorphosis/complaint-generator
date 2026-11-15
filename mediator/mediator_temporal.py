"""Temporal predicate and timeline helpers delegated from Mediator."""

from __future__ import annotations

from typing import Any, Dict, List

import complaint_phases.intake_case_file as intake_case_file_module
from complaint_analysis.temporal_rule_profiles import enrich_follow_up, rank_follow_ups


def _build_temporal_next_actions_for_task(
	self,
	*,
	claim_type: Any,
	claim_element_id: Any,
	claim_element_label: Any,
	temporal_rule_profile_id: Any,
	temporal_rule_status: Any,
	temporal_rule_follow_ups: Any,
	temporal_rule_blocking_reasons: Any,
	temporal_issue_records: Any,
	temporal_fact_ids: Any,
	temporal_relation_ids: Any,
	temporal_issue_ids: Any,
	missing_temporal_predicates: Any,
	required_provenance_kinds: Any,
	temporal_proof_bundle: Any = None,
	packet_temporal_next_actions: Any = None,
) -> List[Dict[str, Any]]:
	source_actions = []
	if isinstance(packet_temporal_next_actions, list) and packet_temporal_next_actions:
		source_actions = packet_temporal_next_actions
	elif isinstance(temporal_proof_bundle, dict) and isinstance(temporal_proof_bundle.get('temporal_next_actions'), list):
		source_actions = temporal_proof_bundle.get('temporal_next_actions') or []
	normalized_actions: List[Dict[str, Any]] = []
	seen = set()
	claim_type_text = str(claim_type or '').strip()
	element_id = str(claim_element_id or '').strip()
	element_label = str(claim_element_label or '').strip()
	profile_id = str(temporal_rule_profile_id or '').strip()
	rule_status = str(temporal_rule_status or '').strip().lower()
	fact_ids = [str(item).strip() for item in (temporal_fact_ids if isinstance(temporal_fact_ids, list) else []) if str(item).strip()]
	relation_ids = [str(item).strip() for item in (temporal_relation_ids if isinstance(temporal_relation_ids, list) else []) if str(item).strip()]
	issue_ids = [str(item).strip() for item in (temporal_issue_ids if isinstance(temporal_issue_ids, list) else []) if str(item).strip()]
	missing_predicates = [str(item).strip() for item in (missing_temporal_predicates if isinstance(missing_temporal_predicates, list) else []) if str(item).strip()]
	required_kinds = [str(item).strip() for item in (required_provenance_kinds if isinstance(required_provenance_kinds, list) else []) if str(item).strip()]

	def _append(raw_action: Dict[str, Any], issue: Dict[str, Any] = None, reason_override: str = '') -> None:
		issue_record = issue if isinstance(issue, dict) else {}
		issue_category = str(issue_record.get('issue_type') or issue_record.get('category') or raw_action.get('issue_category') or '').strip()
		enriched = enrich_follow_up(raw_action, issue_category=issue_category)
		reason = str(
			reason_override
			or enriched.get('reason')
			or issue_record.get('summary')
			or 'Resolve the chronology blocker for this element.'
		).strip()
		affected_issue_ids = [
			str(issue_record.get('issue_id') or issue_record.get('contradiction_id') or issue_record.get('dependency_id') or '').strip()
		] if issue_record else [
			str(item).strip()
			for item in (enriched.get('affected_issue_ids') if isinstance(enriched.get('affected_issue_ids'), list) else [])
			if str(item).strip()
		]
		affected_issue_ids = [item for item in affected_issue_ids if item] or list(issue_ids)
		affected_fact_ids = [
			str(item).strip()
			for item in (issue_record.get('fact_ids') if isinstance(issue_record.get('fact_ids'), list) else enriched.get('affected_fact_ids') if isinstance(enriched.get('affected_fact_ids'), list) else [])
			if str(item).strip()
		] or list(fact_ids)
		lane = str(enriched.get('follow_up_lane') or enriched.get('lane') or '').strip()
		key = (lane, reason, tuple(affected_issue_ids), tuple(affected_fact_ids), profile_id)
		if key in seen:
			return
		seen.add(key)
		normalized_actions.append({
			**dict(enriched),
			'action': str(enriched.get('action') or 'resolve_temporal_blocker'),
			'next_action': str(enriched.get('next_action') or enriched.get('action') or 'resolve_temporal_blocker'),
			'follow_up_lane': lane,
			'lane': str(enriched.get('lane') or lane),
			'reason': reason,
			'prompt': str(enriched.get('prompt') or reason),
			'claim_type': claim_type_text,
			'claim_element_id': element_id,
			'claim_element_label': element_label,
			'temporal_missingness_kind': 'temporal_gap',
			'follow_up_focus': 'temporal_gap_closure',
			'query_strategy': 'temporal_gap_targeted',
			'affected_rule': (
				dict(enriched.get('affected_rule'))
				if isinstance(enriched.get('affected_rule'), dict)
				else {
					'profile_id': profile_id,
					'rule_frame_id': str(enriched.get('affected_rule_frame_id') or ''),
					'status': rule_status,
					'blocking_reason': reason,
				}
			),
			'affected_rule_profile_id': str(enriched.get('affected_rule_profile_id') or profile_id),
			'affected_fact_ids': affected_fact_ids,
			'affected_relation_ids': [
				str(item).strip()
				for item in (enriched.get('affected_relation_ids') if isinstance(enriched.get('affected_relation_ids'), list) else [])
				if str(item).strip()
			] or list(relation_ids),
			'affected_issue_ids': affected_issue_ids,
			'temporal_issue_ids': affected_issue_ids,
			'missing_temporal_predicates': [
				str(item).strip()
				for item in (enriched.get('missing_temporal_predicates') if isinstance(enriched.get('missing_temporal_predicates'), list) else [])
				if str(item).strip()
			] or list(missing_predicates),
			'required_provenance_kinds': [
				str(item).strip()
				for item in (enriched.get('required_provenance_kinds') if isinstance(enriched.get('required_provenance_kinds'), list) else [])
				if str(item).strip()
			] or list(required_kinds),
			'issue_category': issue_category,
		})

	for source_action in source_actions:
		if isinstance(source_action, dict):
			_append(source_action)
	if not normalized_actions:
		for issue in (temporal_issue_records if isinstance(temporal_issue_records, list) else []):
			if not isinstance(issue, dict):
				continue
			_append(
				{
					'lane': str(issue.get('recommended_resolution_lane') or ''),
					'reason': str(issue.get('summary') or issue.get('label') or '').strip(),
				},
				issue=issue,
			)
	if not normalized_actions:
		for follow_up in (temporal_rule_follow_ups if isinstance(temporal_rule_follow_ups, list) else []):
			if isinstance(follow_up, dict):
				_append(follow_up)
	if not normalized_actions:
		for reason in (temporal_rule_blocking_reasons if isinstance(temporal_rule_blocking_reasons, list) else []):
			normalized_reason = str(reason or '').strip()
			if normalized_reason:
				_append({'lane': 'clarify_with_complainant', 'reason': normalized_reason}, reason_override=normalized_reason)

	ranked_actions = rank_follow_ups(normalized_actions)
	for index, action in enumerate(ranked_actions, start=1):
		action['rank'] = int(action.get('rank') or index)
		action.setdefault('action_id', f'temporal_next_action:{claim_type_text}:{element_id or element_label}:{index}')
	return ranked_actions

def _derive_missing_temporal_predicates(
	self,
	*,
	temporal_gap_targeted: bool,
	temporal_relation_formulas: Any,
	temporal_theorem_formulas: Any,
	temporal_proof_objectives: Any,
	temporal_issue_records: Any = None,
	temporal_fact_ids: Any = None,
) -> List[str]:
	if not temporal_gap_targeted:
		return []
	relation_formulas = [
		str(formula).strip()
		for formula in (temporal_relation_formulas if isinstance(temporal_relation_formulas, list) else [])
		if str(formula).strip()
	]
	if relation_formulas:
		return list(dict.fromkeys(relation_formulas))[:6]
	issue_records = [
		issue
		for issue in (temporal_issue_records if isinstance(temporal_issue_records, list) else [])
		if isinstance(issue, dict)
	]
	explicit_issue_predicates = [
		str(predicate).strip()
		for issue in issue_records
		for predicate in (issue.get('missing_temporal_predicates') if isinstance(issue.get('missing_temporal_predicates'), list) else [])
		if str(predicate).strip()
	]
	if explicit_issue_predicates:
		return list(dict.fromkeys(explicit_issue_predicates))[:6]
	issue_predicates: List[str] = []
	for issue in issue_records:
		issue_type = str(issue.get('issue_type') or issue.get('category') or '').strip().lower()
		issue_fact_ids = [
			str(fact_id).strip()
			for fact_id in (issue.get('fact_ids') if isinstance(issue.get('fact_ids'), list) else [])
			if str(fact_id).strip()
		]
		if issue_type == 'relative_only_ordering':
			if len(issue_fact_ids) >= 2:
				issue_predicates.append(f'Before({issue_fact_ids[0]},{issue_fact_ids[-1]})')
			continue
		if issue_type == 'missing_anchor':
			anchor_targets = issue_fact_ids or [
				str(fact_id).strip()
				for fact_id in (temporal_fact_ids if isinstance(temporal_fact_ids, list) else [])
				if str(fact_id).strip()
			]
			if anchor_targets:
				issue_predicates.append(f'Anchored({anchor_targets[0]})')
			continue
		if issue_type.startswith('temporal') and len(issue_fact_ids) >= 2:
			issue_predicates.append(f'Before({issue_fact_ids[0]},{issue_fact_ids[-1]})')
	if issue_predicates:
		return list(dict.fromkeys(issue_predicates))[:6]
	theorem_formulas = [
		str(formula).strip()
		for formula in (temporal_theorem_formulas if isinstance(temporal_theorem_formulas, list) else [])
		if str(formula).strip()
	]
	if theorem_formulas:
		prioritized = [
			formula for formula in theorem_formulas
			if formula.startswith(('Before(', 'After(', 'SameTime(', 'Overlaps(', 'During(', 'Meets('))
		]
		return list(dict.fromkeys(prioritized or theorem_formulas))[:6]
	objectives = [
		str(objective).strip()
		for objective in (temporal_proof_objectives if isinstance(temporal_proof_objectives, list) else [])
		if str(objective).strip()
	]
	if objectives:
		return list(dict.fromkeys(objectives))[:4]
	fact_ids = [
		str(fact_id).strip()
		for fact_id in (temporal_fact_ids if isinstance(temporal_fact_ids, list) else [])
		if str(fact_id).strip()
	]
	if len(fact_ids) >= 2:
		return [f'Before({fact_ids[0]},{fact_ids[-1]})']
	return []

def _author_temporal_case_file_state(
	self,
	intake_case_file: Dict[str, Any],
	*,
	focus_fact_id: str = '',
) -> None:
	canonical_facts = intake_case_file.get('canonical_facts')
	if not isinstance(canonical_facts, list):
		return
	for fact in canonical_facts:
		if not isinstance(fact, dict):
			continue
		fact_type = str(fact.get('fact_type') or '').strip().lower()
		event_date_or_range = str(fact.get('event_date_or_range') or '').strip()
		if fact_type != 'timeline' and not event_date_or_range:
			continue
		fact['temporal_context'] = intake_case_file_module._build_temporal_context(
			event_date_or_range,
			fallback_text=str(fact.get('text') or ''),
		)
		if focus_fact_id and str(fact.get('fact_id') or '').strip() == focus_fact_id:
			fact.setdefault('event_label', str(fact.get('text') or '').strip())

	timeline_anchors = intake_case_file_module.build_timeline_anchors(canonical_facts)
	anchor_ids_by_fact_id: Dict[str, List[str]] = {}
	for anchor in timeline_anchors:
		if not isinstance(anchor, dict):
			continue
		fact_id = str(anchor.get('fact_id') or '').strip()
		anchor_id = str(anchor.get('anchor_id') or '').strip()
		if not fact_id or not anchor_id:
			continue
		anchor_ids_by_fact_id.setdefault(fact_id, [])
		if anchor_id not in anchor_ids_by_fact_id[fact_id]:
			anchor_ids_by_fact_id[fact_id].append(anchor_id)
	for fact in canonical_facts:
		if not isinstance(fact, dict):
			continue
		fact_id = str(fact.get('fact_id') or '').strip()
		if not fact_id:
			continue
		fact['event_id'] = str(fact.get('event_id') or fact_id).strip() or fact_id
		anchor_ids = list(anchor_ids_by_fact_id.get(fact_id, []))
		if anchor_ids:
			fact['timeline_anchor_ids'] = anchor_ids
		event_support_refs = [
			str(item).strip()
			for item in list(fact.get('event_support_refs') or [])
			if str(item or '').strip()
		]
		for derived_ref in [f'fact:{fact_id}', *[f'anchor:{anchor_id}' for anchor_id in anchor_ids]]:
			if derived_ref not in event_support_refs:
				event_support_refs.append(derived_ref)
		if event_support_refs:
			fact['event_support_refs'] = event_support_refs
	timeline_relations = intake_case_file_module.build_timeline_relations(canonical_facts)
	temporal_fact_registry = intake_case_file_module.build_temporal_fact_registry(canonical_facts, timeline_anchors)
	previous_temporal_issue_registry = (
		intake_case_file.get('temporal_issue_registry')
		if isinstance(intake_case_file.get('temporal_issue_registry'), list)
		else []
	)
	temporal_issue_registry = intake_case_file_module.merge_preserved_temporal_issue_registry(
		intake_case_file_module.build_temporal_issue_registry(
			canonical_facts,
			intake_case_file.get('contradiction_queue') if isinstance(intake_case_file.get('contradiction_queue'), list) else [],
		),
		previous_temporal_issue_registry,
	)
	intake_case_file['timeline_anchors'] = timeline_anchors
	intake_case_file['timeline_relations'] = timeline_relations
	intake_case_file['temporal_fact_registry'] = temporal_fact_registry
	intake_case_file['event_ledger'] = intake_case_file_module.build_event_ledger(temporal_fact_registry)
	intake_case_file['temporal_relation_registry'] = intake_case_file_module.build_temporal_relation_registry(
		canonical_facts,
		timeline_relations,
	)
	intake_case_file['temporal_issue_registry'] = temporal_issue_registry
	# Canonical alias so callers can reference timeline issues under the stable key `timeline_issues`
	intake_case_file['timeline_issues'] = temporal_issue_registry

def _build_temporal_relation_formulas_by_id(self, intake_case_file: Dict[str, Any]) -> Dict[str, str]:
	relation_formula_map = {
		'before': 'Before',
		'after': 'After',
		'same_time': 'SameTime',
		'overlaps': 'Overlaps',
		'during': 'During',
		'meets': 'Meets',
	}
	formulas_by_id: Dict[str, str] = {}
	relation_sources = []
	if isinstance(intake_case_file.get('temporal_relation_registry'), list):
		relation_sources.extend(intake_case_file.get('temporal_relation_registry', []))
	if isinstance(intake_case_file.get('timeline_relations'), list):
		relation_sources.extend(intake_case_file.get('timeline_relations', []))
	for relation in relation_sources:
		if not isinstance(relation, dict):
			continue
		relation_id = str(relation.get('relation_id') or '').strip()
		relation_type = str(relation.get('relation_type') or '').strip().lower()
		source_fact_id = str(relation.get('source_fact_id') or relation.get('source_temporal_fact_id') or '').strip()
		target_fact_id = str(relation.get('target_fact_id') or relation.get('target_temporal_fact_id') or '').strip()
		relation_predicate = relation_formula_map.get(relation_type)
		if not relation_id or not relation_predicate or not source_fact_id or not target_fact_id:
			continue
		formulas_by_id[relation_id] = f'{relation_predicate}({source_fact_id},{target_fact_id})'
	return formulas_by_id

def _build_timeline_anchor_ids_by_fact_id(self, intake_case_file: Dict[str, Any]) -> Dict[str, List[str]]:
	anchor_ids_by_fact_id: Dict[str, List[str]] = {}
	for anchor in intake_case_file.get('timeline_anchors', []) if isinstance(intake_case_file.get('timeline_anchors'), list) else []:
		if not isinstance(anchor, dict):
			continue
		fact_id = str(anchor.get('fact_id') or '').strip()
		anchor_id = str(anchor.get('anchor_id') or '').strip()
		if not fact_id or not anchor_id:
			continue
		anchor_ids_by_fact_id.setdefault(fact_id, [])
		if anchor_id not in anchor_ids_by_fact_id[fact_id]:
			anchor_ids_by_fact_id[fact_id].append(anchor_id)
	for event in intake_case_file.get('event_ledger', []) if isinstance(intake_case_file.get('event_ledger'), list) else []:
		if not isinstance(event, dict):
			continue
		fact_id = str(event.get('event_id') or event.get('temporal_fact_id') or event.get('fact_id') or '').strip()
		if not fact_id:
			continue
		anchor_ids_by_fact_id.setdefault(fact_id, [])
		for anchor_id in (event.get('timeline_anchor_ids') or []):
			normalized_anchor_id = str(anchor_id or '').strip()
			if normalized_anchor_id and normalized_anchor_id not in anchor_ids_by_fact_id[fact_id]:
				anchor_ids_by_fact_id[fact_id].append(normalized_anchor_id)
	return anchor_ids_by_fact_id

def _is_temporal_rule_gap_follow_up(
	self,
	proof_gap_types: List[str],
	proof_decision_trace: Dict[str, Any] = None,
	temporal_rule_profile: Dict[str, Any] = None,
) -> bool:
	decision_trace = proof_decision_trace if isinstance(proof_decision_trace, dict) else {}
	profile = temporal_rule_profile if isinstance(temporal_rule_profile, dict) else {}
	decision_source = str(decision_trace.get('decision_source') or '')
	temporal_rule_status = str(
		profile.get('status')
		or decision_trace.get('temporal_rule_status')
		or ''
	)
	return (
		'temporal_rule_partial' in (proof_gap_types or [])
		or 'temporal_rule_failed' in (proof_gap_types or [])
		or decision_source in {'temporal_rule_partial', 'temporal_rule_failed'}
		or temporal_rule_status in {'partial', 'failed'}
	)

def _accumulate_temporal_rule_profile_counts(
	element: Dict[str, Any],
	summary: Dict[str, Any],
	status_counter_map: Dict[str, str],
) -> None:
	"""Increment rule-profile availability and status counters for one packet element.

	Only elements with a non-empty ``temporal_rule_profile_id`` are counted as
	having an available rule profile. Elements with a profile ID but an
	unrecognized or empty status (e.g. profiles registered but not yet
	evaluated) contribute to the available count only.
	"""
	rule_profile_id = str(element.get('temporal_rule_profile_id') or '').strip()
	if not rule_profile_id:
		return
	summary['temporal_rule_profile_available_element_count'] += 1
	rule_status = str(element.get('temporal_rule_status') or '').strip().lower()
	status_counter_key = status_counter_map.get(rule_status)
	if status_counter_key:
		summary[status_counter_key] += 1

def _build_support_packet_timeline_drilldown(
	self,
	reasoning_diagnostics: Dict[str, Any],
	support_facts: List[Dict[str, Any]],
) -> Dict[str, Any]:
	if not isinstance(reasoning_diagnostics, dict):
		reasoning_diagnostics = {}
	temporal_summary = reasoning_diagnostics.get('temporal_summary') if isinstance(reasoning_diagnostics.get('temporal_summary'), dict) else {}
	temporal_profile = reasoning_diagnostics.get('temporal_rule_profile') if isinstance(reasoning_diagnostics.get('temporal_rule_profile'), dict) else {}
	timeline_fact_ids = [
		str(fact.get('fact_id') or '')
		for fact in support_facts or []
		if isinstance(fact, dict) and str(fact.get('fact_type') or fact.get('predicate_family') or '').lower() in {'timeline', 'temporal'}
	]
	return {
		'temporal_summary': temporal_summary,
		'temporal_rule_profile': temporal_profile,
		'timeline_fact_ids': [fact_id for fact_id in timeline_fact_ids if fact_id],
	}

def _preferred_support_kind_for_temporal_rule_profile(
	self,
	temporal_rule_profile: Dict[str, Any],
	fallback: str,
) -> str:
	profile = temporal_rule_profile if isinstance(temporal_rule_profile, dict) else {}
	lanes = {
		str(follow_up.get('lane') or '').strip().lower()
		for follow_up in (profile.get('recommended_follow_ups') or [])
		if isinstance(follow_up, dict)
	}
	if lanes & {'clarify_with_complainant', 'capture_testimony'}:
		return 'testimony'
	if 'request_document' in lanes:
		return 'evidence'
	return fallback
