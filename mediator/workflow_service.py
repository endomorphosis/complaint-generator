from typing import Any, Dict, List

from complaint_phases import ComplaintPhase
from intake_status import (
	_build_document_grounding_improvement_next_action,
	_build_document_grounding_recovery_action,
)


class WorkflowActionService:
	"""Builds mediator workflow action queues and document-grounding handoff actions."""

	def __init__(
		self,
		mediator,
		*,
		recovery_action_builder=_build_document_grounding_recovery_action,
		improvement_next_action_builder=_build_document_grounding_improvement_next_action,
	):
		self._mediator = mediator
		self._recovery_action_builder = recovery_action_builder
		self._improvement_next_action_builder = improvement_next_action_builder

	def __getattr__(self, name):
		return getattr(self._mediator, name)

	def _build_intake_workflow_action_queue(
		self,
		intake_case_file: Dict[str, Any],
		claim_pressure: Dict[str, Dict[str, Any]],
		matching_pressure: Dict[str, Dict[str, Any]],
	) -> List[Dict[str, Any]]:
		queue: List[Dict[str, Any]] = []
		intake_sections = (
			intake_case_file.get('intake_sections')
			if isinstance(intake_case_file, dict) and isinstance(intake_case_file.get('intake_sections'), dict)
			else {}
		)
		intake_focus_areas = [
			str(section_name).strip().lower()
			for section_name, payload in intake_sections.items()
			if isinstance(payload, dict) and str(payload.get('status') or '').strip().lower() != 'complete'
		]
		graph_focus_areas: List[str] = []
		for claim_type, claim_state in (claim_pressure or {}).items():
			if not isinstance(claim_state, dict):
				continue
			if int(claim_state.get('missing_count', 0) or 0) > 0:
				graph_focus_areas.append(str(claim_type).strip().lower())
		for claim_type, matching_state in (matching_pressure or {}).items():
			if not isinstance(matching_state, dict):
				continue
			if int(matching_state.get('missing_requirement_count', 0) or 0) > 0:
				for element_id in matching_state.get('missing_requirement_element_ids') or []:
					element_text = str(element_id).strip().lower()
					if element_text and element_text not in graph_focus_areas:
						graph_focus_areas.append(element_text)
		document_focus_areas = [
			name
			for name in ('proof_leads', 'harm', 'remedy')
			if name in intake_focus_areas
		]
		queue.append(
			{
				'rank': 1,
				'phase_name': 'graph_analysis',
				'status': 'warning' if graph_focus_areas else 'ready',
				'action': 'Close graph and legal-element gaps that still block complaint development.',
				'focus_areas': graph_focus_areas[:4],
			}
		)
		queue.append(
			{
				'rank': 2,
				'phase_name': 'intake_questioning',
				'status': 'warning' if intake_focus_areas else 'ready',
				'action': 'Target remaining intake sections that still prevent a complete complaint narrative.',
				'focus_areas': intake_focus_areas[:4],
			}
		)
		queue.append(
			{
				'rank': 3,
				'phase_name': 'document_generation',
				'status': 'warning' if document_focus_areas else 'ready',
				'action': 'Collect proof, harm, and remedy details needed for drafting-ready allegations.',
				'focus_areas': document_focus_areas[:4],
			}
		)
		return queue

	def _summarize_intake_workflow_action_queue(self, queue: Any) -> Dict[str, Any]:
		summary = {
			'count': 0,
			'phase_counts': {},
			'status_counts': {},
			'focus_area_counts': {},
			'actions': [],
		}
		if not isinstance(queue, list):
			return summary
		summary['count'] = len(queue)
		for item in queue:
			if not isinstance(item, dict):
				continue
			phase_name = str(item.get('phase_name') or '').strip()
			status = str(item.get('status') or '').strip()
			if phase_name:
				summary['phase_counts'][phase_name] = summary['phase_counts'].get(phase_name, 0) + 1
			if status:
				summary['status_counts'][status] = summary['status_counts'].get(status, 0) + 1
			for focus_area in item.get('focus_areas') or []:
				focus_text = str(focus_area).strip()
				if focus_text:
					summary['focus_area_counts'][focus_text] = summary['focus_area_counts'].get(focus_text, 0) + 1
			summary['actions'].append(item)
		return summary

	def _build_evidence_workflow_action_queue(
		self,
		alignment_evidence_tasks: Any,
		evidence_gaps: Any,
	) -> List[Dict[str, Any]]:
		queue: List[Dict[str, Any]] = []
		tasks = alignment_evidence_tasks if isinstance(alignment_evidence_tasks, list) else []
		for index, task in enumerate(tasks, start=1):
			if not isinstance(task, dict):
				continue
			focus_areas = [
				str(item).strip()
				for item in (
					[
						task.get('claim_element_id'),
						task.get('claim_type'),
						*(task.get('missing_fact_bundle') or []),
					]
				)
				if str(item).strip()
			]
			queue.append(
				{
					'rank': index,
					'phase_name': 'graph_analysis' if bool(task.get('blocking')) else 'document_generation',
					'status': 'warning',
					'action': str(task.get('action') or 'fill_evidence_gaps').replace('_', ' '),
					'action_code': str(task.get('action') or 'fill_evidence_gaps').strip().lower(),
					'focus_areas': focus_areas[:4],
					'claim_type': str(task.get('claim_type') or '').strip(),
					'claim_element_id': str(task.get('claim_element_id') or '').strip(),
					'claim_element_label': str(task.get('claim_element_label') or '').strip(),
					'preferred_support_kind': str(task.get('preferred_support_kind') or '').strip(),
					'missing_fact_bundle': list(task.get('missing_fact_bundle') or [])[:4],
				}
			)
		if not queue:
			for gap in (evidence_gaps if isinstance(evidence_gaps, list) else [])[:3]:
				if not isinstance(gap, dict):
					continue
				queue.append(
					{
						'rank': len(queue) + 1,
						'phase_name': 'evidence_collection',
						'status': 'warning',
						'action': str(gap.get('name') or gap.get('description') or 'close evidence gap').strip(),
						'action_code': 'fill_evidence_gaps',
						'focus_areas': [
							str(item).strip()
							for item in [gap.get('related_claim'), gap.get('name')]
							if str(item).strip()
						][:3],
						'claim_type': str(gap.get('related_claim') or '').strip(),
					}
				)
		document_grounding_recovery_action = self._get_document_grounding_recovery_action(
			provisional_evidence_workflow_action_queue=queue,
			alignment_evidence_tasks=alignment_evidence_tasks,
		)
		document_grounding_improvement_next_action = self._get_document_grounding_improvement_next_action(
			provisional_evidence_workflow_action_queue=queue,
			alignment_evidence_tasks=alignment_evidence_tasks,
			document_grounding_recovery_action=document_grounding_recovery_action,
		)
		if document_grounding_improvement_next_action:
			refinement_focus_areas = [
				str(item).strip()
				for item in [
					document_grounding_improvement_next_action.get('claim_element_id'),
					document_grounding_improvement_next_action.get('suggested_claim_element_id'),
					document_grounding_improvement_next_action.get('suggested_support_kind'),
					*(document_grounding_improvement_next_action.get('alternate_support_kinds') or []),
				]
				if str(item).strip()
			]
			refinement_entry = {
				'rank': 1,
				'phase_name': 'document_generation',
				'status': 'warning',
				'action': str(document_grounding_improvement_next_action.get('action') or 'refine_document_grounding_strategy').replace('_', ' '),
				'action_code': str(document_grounding_improvement_next_action.get('action') or 'refine_document_grounding_strategy').strip().lower(),
				'focus_areas': refinement_focus_areas[:4],
				'claim_type': str(document_grounding_improvement_next_action.get('claim_type') or '').strip(),
				'claim_element_id': str(document_grounding_improvement_next_action.get('claim_element_id') or '').strip(),
				'claim_element_label': str(document_grounding_improvement_next_action.get('claim_element_id') or '').strip(),
				'suggested_claim_element_id': str(document_grounding_improvement_next_action.get('suggested_claim_element_id') or '').strip(),
				'alternate_claim_element_ids': list(document_grounding_improvement_next_action.get('alternate_claim_element_ids') or [])[:3],
				'preferred_support_kind': str(document_grounding_improvement_next_action.get('preferred_support_kind') or '').strip(),
				'learned_support_kind': str(document_grounding_improvement_next_action.get('learned_support_kind') or '').strip(),
				'suggested_support_kind': str(document_grounding_improvement_next_action.get('suggested_support_kind') or '').strip(),
				'alternate_support_kinds': list(document_grounding_improvement_next_action.get('alternate_support_kinds') or [])[:3],
				'fact_backed_ratio_delta': float(document_grounding_improvement_next_action.get('fact_backed_ratio_delta') or 0.0),
				'learned_support_lane_priority': bool(document_grounding_improvement_next_action.get('learned_support_kind')),
				'document_grounding_strategy_refinement': True,
			}
			if not any(
				isinstance(item, dict)
				and str(item.get('action_code') or '').strip().lower() in {'refine_document_grounding_strategy', 'retarget_document_grounding'}
				for item in queue
			):
				queue = [refinement_entry, *queue]
		if document_grounding_recovery_action:
			recovery_focus_areas = [
				str(item).strip()
				for item in [
					document_grounding_recovery_action.get('claim_element_id'),
					*(document_grounding_recovery_action.get('missing_fact_bundle') or []),
				]
				if str(item).strip()
			]
			recovery_entry = {
				'rank': 1,
				'phase_name': 'document_generation',
				'status': 'warning',
				'action': 'recover document grounding',
				'action_code': 'recover_document_grounding',
				'focus_areas': recovery_focus_areas[:4],
				'claim_type': str(document_grounding_recovery_action.get('claim_type') or '').strip(),
				'claim_element_id': str(document_grounding_recovery_action.get('claim_element_id') or '').strip(),
				'claim_element_label': str(document_grounding_recovery_action.get('claim_element_id') or '').strip(),
				'preferred_support_kind': str(document_grounding_recovery_action.get('preferred_support_kind') or '').strip(),
				'missing_fact_bundle': list(document_grounding_recovery_action.get('missing_fact_bundle') or [])[:4],
				'fact_backed_ratio': float(document_grounding_recovery_action.get('fact_backed_ratio') or 0.0),
				'recovery_source': str(document_grounding_recovery_action.get('recovery_source') or '').strip(),
				'document_grounding_recovery': True,
			}
			if not any(
				isinstance(item, dict)
				and str(item.get('action_code') or '').strip().lower() == 'recover_document_grounding'
				for item in queue
			):
				if any(
					isinstance(item, dict)
					and str(item.get('action_code') or '').strip().lower() in {
						'refine_document_grounding_strategy',
						'retarget_document_grounding',
					}
					for item in queue
				):
					queue = [queue[0], recovery_entry, *queue[1:]]
				else:
					queue = [recovery_entry, *queue]
		for index, item in enumerate(queue, start=1):
			if isinstance(item, dict):
				item['rank'] = index
		return queue

	def _get_document_provenance_summary(self) -> Dict[str, Any]:
		explicit_summary = self.phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, 'document_provenance_summary')
		if isinstance(explicit_summary, dict) and explicit_summary:
			return dict(explicit_summary)
		formal_complaint = self.phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, 'formal_complaint')
		if isinstance(formal_complaint, dict):
			document_provenance_summary = formal_complaint.get('document_provenance_summary')
			if isinstance(document_provenance_summary, dict) and document_provenance_summary:
				return dict(document_provenance_summary)
		return {}

	def _get_document_grounding_lane_outcome_summary(self) -> Dict[str, Any]:
		explicit_summary = self.phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, 'document_grounding_lane_outcome_summary')
		if isinstance(explicit_summary, dict) and explicit_summary:
			return dict(explicit_summary)
		formal_complaint = self.phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, 'formal_complaint')
		if isinstance(formal_complaint, dict):
			lane_summary = formal_complaint.get('document_grounding_lane_outcome_summary')
			if isinstance(lane_summary, dict) and lane_summary:
				return dict(lane_summary)
		return {}

	def _get_document_grounding_recovery_action(
		self,
		*,
		provisional_evidence_workflow_action_queue: Any = None,
		alignment_evidence_tasks: Any = None,
	) -> Dict[str, Any]:
		explicit_action = self.phase_manager.get_phase_data(
			ComplaintPhase.FORMALIZATION,
			'document_grounding_recovery_action',
		)
		if isinstance(explicit_action, dict) and explicit_action:
			return dict(explicit_action)
		return self._recovery_action_builder(
			self._get_document_provenance_summary(),
			provisional_evidence_workflow_action_queue,
			alignment_evidence_tasks,
		)

	def _get_document_grounding_improvement_next_action(
		self,
		*,
		provisional_evidence_workflow_action_queue: Any = None,
		alignment_evidence_tasks: Any = None,
		document_grounding_recovery_action: Any = None,
	) -> Dict[str, Any]:
		explicit_action = self.phase_manager.get_phase_data(
			ComplaintPhase.FORMALIZATION,
			'document_grounding_improvement_next_action',
		)
		if isinstance(explicit_action, dict) and explicit_action:
			return dict(explicit_action)
		explicit_summary = self.phase_manager.get_phase_data(
			ComplaintPhase.FORMALIZATION,
			'document_grounding_improvement_summary',
		)
		formal_complaint = self.phase_manager.get_phase_data(ComplaintPhase.FORMALIZATION, 'formal_complaint')
		if (not isinstance(explicit_summary, dict) or not explicit_summary) and isinstance(formal_complaint, dict):
			formal_summary = formal_complaint.get('document_grounding_improvement_summary')
			if isinstance(formal_summary, dict) and formal_summary:
				explicit_summary = dict(formal_summary)
		return self._improvement_next_action_builder(
			explicit_summary,
			document_grounding_recovery_action or self._get_document_grounding_recovery_action(
				provisional_evidence_workflow_action_queue=provisional_evidence_workflow_action_queue,
				alignment_evidence_tasks=alignment_evidence_tasks,
			),
			self._get_document_grounding_lane_outcome_summary(),
		)

	def _summarize_evidence_workflow_action_queue(self, queue: Any) -> Dict[str, Any]:
		summary = {
			'count': 0,
			'phase_counts': {},
			'status_counts': {},
			'actions': [],
		}
		if not isinstance(queue, list):
			return summary
		summary['count'] = len(queue)
		for item in queue:
			if not isinstance(item, dict):
				continue
			phase_name = str(item.get('phase_name') or '').strip()
			status = str(item.get('status') or '').strip()
			if phase_name:
				summary['phase_counts'][phase_name] = summary['phase_counts'].get(phase_name, 0) + 1
			if status:
				summary['status_counts'][status] = summary['status_counts'].get(status, 0) + 1
			summary['actions'].append(item)
		return summary

	def _build_question_workflow_action_matches(
		self,
		candidate: Dict[str, Any],
		workflow_action_queue: List[Dict[str, Any]],
	) -> Dict[str, Any]:
		explanation = candidate.get('ranking_explanation', {}) if isinstance(candidate.get('ranking_explanation'), dict) else {}
		question_text = str(candidate.get('question') or '').strip().lower()
		phase1_section = str(explanation.get('phase1_section') or candidate.get('phase1_section') or '').strip().lower()
		target_claim_type = str(explanation.get('target_claim_type') or candidate.get('target_claim_type') or '').strip().lower()
		target_element_id = str(explanation.get('target_element_id') or candidate.get('target_element_id') or '').strip().lower()
		best_rank = 99
		match_count = 0
		matched_phase = ''
		matched_focus_areas: List[str] = []
		for action in workflow_action_queue if isinstance(workflow_action_queue, list) else []:
			if not isinstance(action, dict):
				continue
			phase_name = str(action.get('phase_name') or '').strip().lower()
			rank = int(action.get('rank', 99) or 99)
			focus_areas = [
				str(item).strip().lower()
				for item in (action.get('focus_areas') or [])
				if str(item).strip()
			]
			phase_match = (
				(phase_name == 'graph_analysis' and phase1_section == 'graph_analysis')
				or (phase_name == 'intake_questioning' and phase1_section in {'chronology', 'actors', 'claim_elements', 'harm_remedy', 'proof_leads', 'contradictions'})
				or (phase_name == 'document_generation' and phase1_section in {'proof_leads', 'harm_remedy'})
			)
			focus_matches = [
				focus
				for focus in focus_areas
				if focus in {target_claim_type, target_element_id, phase1_section}
				or (focus and focus in question_text)
			]
			if phase_match or focus_matches:
				match_count += len(focus_matches) or 1
				if rank < best_rank:
					best_rank = rank
					matched_phase = phase_name
					matched_focus_areas = focus_matches or focus_areas[:2]
		return {
			'workflow_action_match_count': match_count,
			'workflow_action_rank': best_rank if best_rank != 99 else None,
			'workflow_action_phase': matched_phase,
			'workflow_action_focus_areas': matched_focus_areas,
		}
