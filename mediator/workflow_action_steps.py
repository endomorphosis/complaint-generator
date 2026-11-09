"""Workflow action steps delegated from WorkflowActionService."""

from __future__ import annotations

from mediator.workflow_service import (
    Any,
    ComplaintPhase,
    DependencyGraph,
    Dict,
    KnowledgeGraph,
    List,
    NodeType,
    hashlib,
    json,
)

def refresh_legal_dependency_graph(
	self, *, case_id: str, actor_principal_id: str, correction_kind: str,
	case_revision: int, consent_generation: int, consent_revoked: bool,
	grant_revision: int, granted_actions: Any, legal_source_hashes: Any,
	operation_id: str, expected_case_revision: int, expected_consent_generation: int,
	expected_grant_revision: int, expected_dependency_generation: int,
	links=None, questions=None, proof_obligations=None, successors=None,
	canonical_source_records=None,
) -> Dict[str, Any]:
	"""Re-read canonical scoped sources and refresh an actual isolated workflow.

	The workspace supplies authenticated live bindings and, for private GUI
	cases, only records joined to its current encrypted manifest. It commits
	the exported projection through its late-checked private CAS. Client rows
	are never installed as links, questions, sources or proof obligations.
	"""
	from copy import deepcopy
	from mediator.interface import Mediator
	from integrations.ipfs_datasets.legal import adapt_sourced_legal_requirements

	mediator = self._mediator
	case_file = self._refresh_case_file() if isinstance(mediator, Mediator) else {}
	old_ledger = case_file.get("legal_graph_refresh")
	ledger = deepcopy(old_ledger) if isinstance(old_ledger, dict) else {}
	ledger.setdefault("case_id", case_id)
	ledger.setdefault("dependency_generation", 0)
	ledger.setdefault("operation_version", 0)
	ledger.setdefault("legal_source_hashes", [])
	ledger.setdefault("records", {"links": [], "questions": [], "proof_obligations": []})
	ledger.setdefault("operations", {})
	key = str(operation_id or "")
	kind = str(correction_kind or "")
	def refuse(code):
		return self._refresh_receipt(status="refused", case_id=case_id,
			actor_principal_id=actor_principal_id, operation_id=key,
			correction_kind=kind, ledger=ledger, error_code=code, applied=False)
	if (not isinstance(mediator, Mediator) or not isinstance(ledger["operations"], dict)
		or not isinstance(ledger["records"], dict)
		or any(type(ledger[field]) is not int or ledger[field] < 0
			for field in ("dependency_generation", "operation_version"))
		or any(not isinstance(bucket, list) for bucket in ledger["records"].values())):
		return refuse("actual_workflow_unavailable")
	graph = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
	kg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
	if not isinstance(graph, DependencyGraph) or not isinstance(kg, KnowledgeGraph):
		return refuse("actual_workflow_unavailable")
	if (not key or key != key.strip() or len(key) > 128
		or not case_id or not actor_principal_id or kind not in {"source", "context", "factual"}):
		return refuse("refresh_field")
	if any(value for value in (links, questions, proof_obligations, successors)):
		return refuse("caller_graph_rows_not_accepted")
	if ledger["case_id"] != case_id:
		return refuse("cross_case")
	ints = (case_revision, consent_generation, grant_revision, expected_case_revision,
		expected_consent_generation, expected_grant_revision, expected_dependency_generation)
	if any(type(value) is not int or value < 0 for value in ints):
		return refuse("refresh_field")
	if consent_revoked is True:
		return refuse("consent_revoked")
	if not isinstance(granted_actions, (list, tuple, set, frozenset)) or "case.update" not in granted_actions:
		return refuse("actor_not_permitted")
	for expected, live, code in (
		(expected_case_revision, case_revision, "stale_case_revision"),
		(expected_consent_generation, consent_generation, "stale_consent"),
		(expected_grant_revision, grant_revision, "stale_actor_grant")):
		if expected != live:
			return refuse(code)
	try:
		hashes = self._refresh_hashes(legal_source_hashes)
	except ValueError:
		return refuse("stale_legal_source_hash")
	try:
		manifest_hashes = self._refresh_manifest_hashes(mediator, canonical_source_records)
		manifest_digest = hashlib.sha256(json.dumps(canonical_source_records,
			sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
	except (ValueError, TypeError):
		return refuse("canonical_source_scope_invalid")
	if manifest_hashes is not None and manifest_hashes != hashes:
		return refuse("current_source_scope_mismatch")
	request = {"case_id": case_id, "actor_principal_id": actor_principal_id,
		"correction_kind": kind, "case_revision": case_revision,
		"consent_generation": consent_generation, "grant_revision": grant_revision,
		"legal_source_hashes": list(hashes), "expected_dependency_generation": expected_dependency_generation,
		"manifest_source_scope": canonical_source_records is not None,
		"manifest_source_scope_sha256": manifest_digest}
	fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
	current_basis = self._refresh_snapshot_basis(case_file, graph, kg)
	stored = ledger["operations"].get(key)
	if isinstance(stored, dict):
		if stored.get("request_fingerprint") != fingerprint:
			return refuse("operation_conflict")
		if (stored.get("after_basis_sha256") != current_basis
			or stored.get("dependency_generation") != ledger["dependency_generation"]):
			return refuse("stale_operation_scope")
		receipt = deepcopy(stored["receipt"])
		receipt.update(replayed=True, applied=False, graph_mutated=False)
		return receipt
	if expected_dependency_generation != ledger["dependency_generation"]:
		return refuse("stale_dependency_generation")
	before_case, before_graph = deepcopy(case_file), deepcopy(graph.to_dict())
	old_nodes = [node for node in graph.nodes.values()
		if node.attributes.get("dependency_class") == "legally_sourced_requirement"]
	rule_ids = sorted({str(node.attributes.get("rule_id")) for node in old_nodes if node.attributes.get("rule_id")})
	change = {"rule_ids": rule_ids, "request_id": key,
		"operation": "revalidate_current_legal_dependencies",
		"source_preimage": hashlib.sha256(json.dumps(list(hashes)).encode()).hexdigest(),
		"context_preimage": hashlib.sha256(json.dumps(case_file.get("legal_context") or {},
			sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
	# The real source owner reconciles actual requirements, then its DG owner
	# invalidates/rekeys their support, proof caches and question targets.
	try:
		report = mediator.refresh_verified_legal_dependencies(change, source_records=canonical_source_records)
		selection = mediator.resolve_intake_legal_selection(
			[{"type": node.attributes.get("claim_type")} for node in graph.get_nodes_by_type(NodeType.CLAIM)],
			case_file)
		actual_hashes = set()
		for node in graph.nodes.values():
			attrs = node.attributes
			if attrs.get("dependency_class") != "legally_sourced_requirement" or attrs.get("source_available") is not True:
				continue
			claim = str(attrs.get("claim_type") or "unknown")
			entries = adapt_sourced_legal_requirements({claim: [attrs]}, legal_context=selection["legal_context"])[claim]
			if entries and entries[0].get("intake_requirement_status") == "source_bound":
				actual_hashes.add(str(entries[0]["source_hash"]))
		# Manifest custody and governing admission are different facts. Unknown
		# context may retain owned bytes while admitting no legal requirement.
		if ((manifest_hashes is None and tuple(sorted(actual_hashes)) != hashes)
			or (manifest_hashes is not None and not actual_hashes.issubset(set(hashes)))):
			raise ValueError("current_source_scope_mismatch")
		if report.get("user_facts_modified") is True:
			raise ValueError("factual_state_changed")
		if "legal_context_applicability" in before_case:
			# Source lookup re-derives temporary question/change metadata. It
			# must not rewrite the separate explicit-selection owner's snapshot.
			old_context = before_case.get("legal_context")
			new_context = case_file.get("legal_context")
			transient = {"changed_fields", "questions", "status"}
			if (not isinstance(old_context, dict) or not isinstance(new_context, dict)
				or {k: v for k, v in old_context.items() if k not in transient}
				!= {k: v for k, v in new_context.items() if k not in transient}):
				raise ValueError("current_legal_context_changed")
			for field in list(case_file):
				if field.startswith("legal_context"):
					case_file.pop(field)
			case_file.update({k: deepcopy(v) for k, v in before_case.items() if k.startswith("legal_context")})
	except Exception as exc:
		restored = DependencyGraph.from_dict(deepcopy(before_graph))
		graph.__dict__.clear()
		graph.__dict__.update(restored.__dict__)
		case_file.clear()
		case_file.update(before_case)
		mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "dependency_graph", graph)
		mediator.phase_manager.update_phase_data(ComplaintPhase.INTAKE, "intake_case_file", case_file)
		return refuse(str(exc) if str(exc) in {"current_source_scope_mismatch", "current_legal_context_changed"}
			else "actual_refresh_unavailable")
	generation = ledger["dependency_generation"] + 1
	invalidated = self._invalidate_refresh_records(ledger, key, kind)
	current_records = self._refresh_records_from_actual_graph(graph)
	for name, rows in current_records.items():
		for row in rows:
			row.update(status="current", dependency_generation=generation, installed_by=key,
				legal_source_hashes=list(hashes), proof=False, legal_sufficiency=False)
			ledger["records"].setdefault(name, []).append(row)
	ledger.update(dependency_generation=generation, operation_version=ledger["operation_version"] + 1,
		legal_source_hashes=list(hashes), case_revision=case_revision, consent_generation=consent_generation,
		consent_revoked=False, grant_revision=grant_revision, actor_principal_id=actor_principal_id)
	case_file["legal_graph_refresh"] = ledger
	receipt = self._refresh_receipt(status="applied", case_id=case_id, actor_principal_id=actor_principal_id,
		operation_id=key, correction_kind=kind, ledger=ledger, error_code=None, applied=True, invalidated=invalidated)
	receipt.update(graph_mutated=before_graph != graph.to_dict(), dependency_refresh=deepcopy(report),
		admitted_source_hashes=sorted(actual_hashes), manifest_source_scope_sha256=manifest_digest,
		actual_graph_sha256=self._refresh_snapshot_basis({}, graph, kg),
		limitations=["A real canonical source/DG refresh was performed on this isolated snapshot.",
			"Caller rows are not installed; source membership comes from the current manifest scope.",
			"Request correction_kind describes intent; dependency_refresh reports actual affected nodes.",
			"Neither source admission nor this refresh proves legal sufficiency."])
	ledger["operations"][key] = {"request_fingerprint": fingerprint,
		"after_basis_sha256": self._refresh_snapshot_basis(case_file, graph, kg),
		"dependency_generation": generation, "receipt": deepcopy(receipt)}
	return receipt


def apply_factual_correction(
	self,
	*,
	action: str,
	target_stable_id: str,
	replacement: str,
	source_context: Optional[Dict[str, Any]],
	event_id: str,
	case_id: str,
	expected_graph_revision: Optional[str],
	expected_session_revision: Optional[int],
) -> Dict[str, Any]:
	"""Correct or retract one assertion through process_denoising_answer.

	The same event id and payload replay the stored graph result. A missing,
	cross-case, or stale target is refused before any factual record changes.
	"""
	normalized = str(action or "").strip().lower()
	if normalized not in {"correct", "retract"}:
		return self._correction_receipt(
			status="refused",
			action=normalized or "correct",
			case_id=str(case_id or ""),
			event_id=str(event_id or ""),
			target_stable_id=str(target_stable_id or ""),
			error_code="unknown_action",
		)
	if not self.interview_started:
		return self._correction_receipt(
			status="unavailable",
			action=normalized,
			case_id=str(case_id or ""),
			event_id=str(event_id or ""),
			target_stable_id=str(target_stable_id or ""),
			error_code="session_missing",
		)
	mediator = self._mediator
	kg = mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
	if kg is None or not hasattr(kg, "begin_answer_event"):
		return self._correction_receipt(
			status="unavailable",
			action=normalized,
			case_id=str(case_id or ""),
			event_id=str(event_id or ""),
			target_stable_id=str(target_stable_id or ""),
			error_code="capability_unavailable",
		)
	case_refusal = self._correction_case_refusal(
		kg,
		action=normalized,
		case_id=str(case_id or ""),
		event_id=str(event_id or ""),
		target_stable_id=str(target_stable_id or ""),
	)
	if case_refusal is not None:
		return case_refusal
	stable_event = str(event_id or "").strip()
	if not stable_event:
		return self._correction_receipt(
			status="refused",
			action=normalized,
			case_id=str(case_id or ""),
			event_id="",
			target_stable_id=str(target_stable_id or ""),
			error_code="missing_event",
		)
	statement = str(replacement or "")
	context = dict(source_context) if isinstance(source_context, dict) else None
	question = self._correction_question(stable_event, normalized)
	supersedes = str(target_stable_id or "").strip() if normalized == "correct" else None
	retracts = str(target_stable_id or "").strip() if normalized == "retract" else None
	from complaint_phases.knowledge_graph import AnswerEventConflict, answer_event_payload

	payload = answer_event_payload(
		question=question,
		answer=statement,
		source_context=context,
		factual_action=normalized,
		supersedes_stable_id=supersedes,
		retracts_stable_id=retracts,
	)
	try:
		prior = kg.begin_answer_event(stable_event, payload)
	except AnswerEventConflict:
		return self._correction_receipt(
			status="refused",
			action=normalized,
			case_id=str(case_id or ""),
			event_id=stable_event,
			target_stable_id=str(target_stable_id or ""),
			error_code="event_conflict",
		)
	if prior is None:
		refusal = self._correction_target_refusal(
			kg,
			action=normalized,
			case_id=str(case_id or ""),
			event_id=stable_event,
			target_stable_id=str(target_stable_id or ""),
			statement=statement,
			source_context=context,
			expected_graph_revision=expected_graph_revision,
			expected_session_revision=expected_session_revision,
		)
		if refusal is not None:
			return refusal
	phase_manager = mediator.phase_manager
	saved_questions = list(phase_manager.get_phase_data(ComplaintPhase.INTAKE, "current_questions") or [])
	saved_candidates = list(phase_manager.get_phase_data(ComplaintPhase.INTAKE, "question_candidates") or [])
	try:
		engine = mediator.process_denoising_answer(
			question,
			statement,
			answer_event_id=stable_event,
			source_context=context,
			factual_action=normalized,
			supersedes_stable_id=supersedes,
			retracts_stable_id=retracts,
		)
	except AnswerEventConflict:
		return self._correction_receipt(
			status="refused",
			action=normalized,
			case_id=str(case_id or ""),
			event_id=stable_event,
			target_stable_id=str(target_stable_id or ""),
			error_code="event_conflict",
		)
	except Exception as exc:
		return self._correction_receipt(
			status="unavailable",
			action=normalized,
			case_id=str(case_id or ""),
			event_id=stable_event,
			target_stable_id=str(target_stable_id or ""),
			error_code="capability_unavailable",
			error_type=type(exc).__name__,
		)
	finally:
		phase_manager.update_phase_data(ComplaintPhase.INTAKE, "current_questions", saved_questions)
		phase_manager.update_phase_data(ComplaintPhase.INTAKE, "question_candidates", saved_candidates)
	if prior is None:
		meta = self._interview_meta
		meta["session_revision"] = int(meta.get("session_revision") or 0) + 1
		meta["case_id"] = str(case_id or "")
		metadata = getattr(kg, "metadata", None)
		if isinstance(metadata, dict) and not metadata.get("case_id"):
			metadata["case_id"] = str(case_id or "")
	updates = engine.get("updates") if isinstance(engine, dict) else {}
	if not isinstance(updates, dict):
		updates = {}
	return self._correction_receipt(
		status="applied",
		action=normalized,
		case_id=str(case_id or ""),
		event_id=stable_event,
		target_stable_id=str(target_stable_id or ""),
		idempotent_replay=prior is not None,
		graph_mutated=prior is None,
		updates=updates,
		knowledge_graph=kg,
	)


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


def research_legal_source_gap(
	self,
	*,
	user_id: str,
	case_id: str,
	intake_case_file: Dict[str, Any],
	claims: Optional[List[Dict[str, Any]]] = None,
	query_terms: Optional[List[str]] = None,
	local_rows: Optional[Dict[str, Any]] = None,
	retrieval_mode: str = "cache",
	storage_available: bool = True,
	cancelled: bool = False,
	deadline_seconds: float = 5.0,
	max_bytes: int = 4096,
	max_results: int = 5,
	operation_id: Optional[str] = None,
) -> Dict[str, Any]:
	"""Acquire and admit sources for the current legal-source gap.

	This is the typed bounded acquisition/admission operation. It does not
	record a factual answer and it does not treat a research receipt as proof.
	The same operation id returns the stored receipt and does not acquire again.
	"""
	operation_key = str(operation_id or "").strip()
	seen = getattr(self, "_research_operation_ids", None)
	if not isinstance(seen, dict):
		seen = {}
		self._research_operation_ids = seen
	if operation_key and operation_key in seen:
		prior = dict(seen[operation_key])
		prior["replayed"] = True
		prior["dispatched"] = False
		return prior
	self._legal_research_dispatch_count = int(getattr(self, "_legal_research_dispatch_count", 0) or 0) + 1
	mediator = self._mediator
	case = intake_case_file if isinstance(intake_case_file, dict) else {}
	claim_rows = [item for item in list(claims or []) if isinstance(item, dict)]
	try:
		binding = mediator.build_legal_acquisition_request(
			case,
			claim_rows,
			query_terms=query_terms,
			storage_available=storage_available,
			max_results=max_results,
			timeout_seconds=deadline_seconds,
		)
		acquisition = mediator.legal_authority_search.acquire_bounded_canonical_sources(
			binding,
			owner_id=str(user_id or ""),
			case_id=str(case_id or ""),
			purpose="public_law_citation",
			data_class="public_legal_source_graph",
			provider_kind="local",
			retrieval_mode=retrieval_mode,
			local_rows=local_rows,
			deadline_seconds=deadline_seconds,
			max_bytes=max_bytes,
			max_results=max_results,
			cancelled=bool(cancelled),
		)
	except Exception:
		acquisition = {
			"status": "unavailable",
			"error_code": "acquisition_unavailable",
			"candidates": [],
			"proof": False,
			"resume": {"resumable": True, "next_action": "retry_unavailable", "worker_stalled": False},
		}
	if not isinstance(acquisition, dict):
		acquisition = {
			"status": "unavailable",
			"error_code": "acquisition_unavailable",
			"candidates": [],
			"proof": False,
			"resume": {"resumable": True, "next_action": "retry_unavailable", "worker_stalled": False},
		}
	try:
		admitted = mediator.admit_acquired_authorities(acquisition, claim_rows, case, user_id=user_id)
	except Exception:
		admitted = {
			"acquisition": {"status": acquisition.get("status") or "unavailable", "error_code": "storage_unavailable"},
			"admission": {
				"status": "unavailable",
				"reason": "storage_unavailable",
				"decisions": [{"status": "unavailable", "reason": "storage_error"}],
				"stored_record_ids": [],
				"proof": False,
			},
		}
	admission = admitted.get("admission") if isinstance(admitted, dict) and isinstance(admitted.get("admission"), dict) else {}
	decisions = [item for item in list(admission.get("decisions") or []) if isinstance(item, dict)]
	candidates = acquisition.get("candidates") if isinstance(acquisition.get("candidates"), list) else []
	retrieved = len(candidates)
	admitted_count = sum(1 for item in decisions if item.get("status") == "admitted")
	rejected_count = sum(1 for item in decisions if item.get("status") not in {"admitted", "unavailable", "stored"})
	unavailable_count = sum(1 for item in decisions if item.get("status") == "unavailable")
	acquisition_status = str(acquisition.get("status") or "unavailable")
	admission_status = str(admission.get("status") or "")
	if acquisition_status in {"unavailable", "timeout", "error"} and unavailable_count == 0:
		unavailable_count = 1
	elif admission_status == "unavailable" and unavailable_count == 0:
		unavailable_count = 1
	if admission_status == "rejected" and rejected_count == 0:
		rejected_count = len(decisions) or 1
	resume = acquisition.get("resume") if isinstance(acquisition.get("resume"), dict) else {}
	next_action = str(resume.get("next_action") or "")
	if not next_action or next_action == "none":
		next_action = "continue_pending_inquiry"
	resumable = bool(resume.get("resumable")) or next_action in {
		"continue_pending_inquiry",
		"resolve_legal_context",
		"retry_unavailable",
		"retry_timeout",
		"supply_edition",
		"supply_owned_source_text",
		"awaiting_user",
	}
	receipt = {
		"action": "legal_research",
		"operation": "acquire_bounded_canonical_sources+admit_acquired_authorities",
		"operation_id": operation_key,
		"stored_as_answer": False,
		"proves_complaint": False,
		"legal_sufficiency": False,
		"replayed": False,
		"dispatched": True,
		"status": acquisition_status if acquisition_status != "candidates" else (admission_status or acquisition_status),
		"acquisition_status": acquisition_status,
		"admission_status": admission_status,
		"error_code": str(acquisition.get("error_code") or admission.get("reason") or ""),
		"counts": {
			"retrieved": retrieved,
			"admitted": admitted_count,
			"rejected": rejected_count,
			"unavailable": unavailable_count,
		},
		"next_action": next_action,
		"resumable": resumable,
		"worker_stalled": False,
		"proof": False,
	}
	if operation_key:
		seen[operation_key] = dict(receipt)
	return receipt
