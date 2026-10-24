import hashlib
import json
from typing import Any, Dict, List, Optional
from uuid import uuid4

from complaint_phases import ComplaintPhase, DependencyGraph, KnowledgeGraph
from intake_status import (
	_build_document_grounding_improvement_next_action,
	_build_document_grounding_recovery_action,
)


__all__ = ['WorkflowActionService', 'WorkflowService']


class WorkflowActionService:
	"""Build mediator workflow queues and document-grounding handoff actions.

	The service is intentionally composed into :class:`mediator.Mediator` rather
	than inherited by it.  The public methods below are the service boundary for
	new callers.  Underscore-prefixed methods remain in place because older code
	may have reached them through ``Mediator`` or the previously exported service
	class.
	"""

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

	def build_intake_action_queue(
		self,
		intake_case_file: Dict[str, Any],
		claim_pressure: Dict[str, Dict[str, Any]],
		matching_pressure: Dict[str, Dict[str, Any]],
	) -> List[Dict[str, Any]]:
		"""Build the ordered action queue for the intake workflow."""
		return self._build_intake_workflow_action_queue(
			intake_case_file,
			claim_pressure,
			matching_pressure,
		)

	def summarize_intake_action_queue(self, queue: Any) -> Dict[str, Any]:
		"""Summarize an intake action queue without changing its payload."""
		return self._summarize_intake_workflow_action_queue(queue)

	def build_evidence_action_queue(
		self,
		alignment_evidence_tasks: Any,
		evidence_gaps: Any,
	) -> List[Dict[str, Any]]:
		"""Build the ordered action queue for evidence and grounding work."""
		return self._build_evidence_workflow_action_queue(
			alignment_evidence_tasks,
			evidence_gaps,
		)

	def summarize_evidence_action_queue(self, queue: Any) -> Dict[str, Any]:
		"""Summarize an evidence action queue without changing its payload."""
		return self._summarize_evidence_workflow_action_queue(queue)

	def build_question_action_matches(
		self,
		candidate: Dict[str, Any],
		workflow_action_queue: List[Dict[str, Any]],
	) -> Dict[str, Any]:
		"""Return workflow-priority signals for an intake question candidate."""
		return self._build_question_workflow_action_matches(
			candidate,
			workflow_action_queue,
		)

	def get_document_provenance_summary(self) -> Dict[str, Any]:
		"""Return the current formal document provenance summary."""
		return self._get_document_provenance_summary()

	def get_document_grounding_lane_outcome_summary(self) -> Dict[str, Any]:
		"""Return outcomes from the current document-grounding lanes."""
		return self._get_document_grounding_lane_outcome_summary()

	def get_document_grounding_recovery_action(
		self,
		*,
		provisional_evidence_workflow_action_queue: Any = None,
		alignment_evidence_tasks: Any = None,
	) -> Dict[str, Any]:
		"""Resolve the next recovery action for weak document grounding."""
		return self._get_document_grounding_recovery_action(
			provisional_evidence_workflow_action_queue=provisional_evidence_workflow_action_queue,
			alignment_evidence_tasks=alignment_evidence_tasks,
		)

	def get_document_grounding_improvement_next_action(
		self,
		*,
		provisional_evidence_workflow_action_queue: Any = None,
		alignment_evidence_tasks: Any = None,
		document_grounding_recovery_action: Any = None,
	) -> Dict[str, Any]:
		"""Resolve the next learned improvement action for document grounding."""
		return self._get_document_grounding_improvement_next_action(
			provisional_evidence_workflow_action_queue=provisional_evidence_workflow_action_queue,
			alignment_evidence_tasks=alignment_evidence_tasks,
			document_grounding_recovery_action=document_grounding_recovery_action,
		)

	# One versioned interview transition. Session identity lives here; graph
	# updates stay on Mediator.start_three_phase_process and
	# process_denoising_answer.
	INTERVIEW_CONTRACT_VERSION = "interview-transition-v1"
	SESSION_PROJECTION_VERSION = "shared-interview-session-v1"

	def bind_interview_privacy(self, policy: Any, *, user_id: str, case_id: str, data_class: str = "raw_intake") -> Dict[str, Any]:
		"""Attach the per-case privacy context used before any interview inference."""
		from integrations.ipfs_datasets.llm import build_complaint_privacy_context, privacy_policy_for_mode

		resolved = policy
		if not isinstance(resolved, dict):
			resolved = privacy_policy_for_mode(user_id, case_id, "local")
		context = build_complaint_privacy_context(
			resolved,
			user_id=str(user_id or ""),
			case_id=str(case_id or user_id or ""),
			data_class=data_class,
		)
		self._mediator._interview_privacy_context = context
		self._interview_privacy_policy = context.get("policy")
		self._bound_case_id = str(context.get("case_id") or case_id or "")
		meta = getattr(self, "_interview_meta", None)
		if isinstance(meta, dict):
			meta["case_id"] = self._bound_case_id
		return context

	@property
	def interview_started(self) -> bool:
		meta = getattr(self, "_interview_meta", None)
		return bool(isinstance(meta, dict) and meta.get("started"))

	def transition_interview(
		self,
		*,
		action: str,
		narrative: Optional[str] = None,
		answer: Optional[str] = None,
		inquiry_id: Optional[str] = None,
		expected_question_revision: Optional[int] = None,
		session_projection: Optional[Dict[str, Any]] = None,
		privacy_policy: Any = None,
		user_id: Optional[str] = None,
		case_id: Optional[str] = None,
	) -> Dict[str, Any]:
		"""Start, answer, resume, or report one shared interview step.

		The pending question is the canonical graph question already stored on
		the phase manager. A caller-supplied question body is not accepted.
		"""
		normalized = str(action or "status").strip().lower()
		identity = str(user_id or getattr(self._mediator.state, "username", None) or "anonymous")
		bound_case = str(case_id or identity)
		if privacy_policy is not None or normalized in {"start", "answer"}:
			self.bind_interview_privacy(privacy_policy, user_id=identity, case_id=bound_case)
		if normalized == "resume":
			if isinstance(session_projection, dict):
				restored = self.restore_session_projection(session_projection)
				if restored.get("error"):
					return restored
			elif not self.interview_started:
				return self._interview_receipt(
					action="resume",
					status="unavailable",
					error=self._interview_error("session_missing", resumable=True),
				)
			return self._interview_receipt(action="resume", status=self._interview_runtime_status())
		if normalized == "prompt":
			return self._interview_receipt(
				action="prompt",
				status="awaiting_user",
				inquiry=self._narrative_prompt_inquiry(),
			)
		if normalized == "start":
			text = str(narrative or "").strip()
			if not text:
				return self._interview_receipt(
					action="start",
					status="awaiting_user",
					inquiry=self._narrative_prompt_inquiry(),
					error=self._interview_error("narrative_required", resumable=True),
				)
			if self.interview_started:
				return self._interview_receipt(action="start", status=self._interview_runtime_status())
			try:
				engine = self._mediator.start_three_phase_process(text)
			except Exception as exc:
				return self._failure_receipt("start", exc)
			self._remember_start(engine)
			return self._interview_receipt(action="start", status=self._interview_runtime_status(), engine=engine)
		if normalized == "answer":
			if not self.interview_started:
				return self._interview_receipt(
					action="answer",
					status="unavailable",
					error=self._interview_error("session_missing", resumable=True),
				)
			pending = self._canonical_pending_question()
			if pending is None:
				return self._interview_receipt(action="answer", status="complete")
			refusal = self._stale_refusal(pending, inquiry_id, expected_question_revision)
			if refusal is not None:
				return refusal
			answer_text = str(answer or "").strip()
			if not answer_text:
				return self._interview_receipt(
					action="answer",
					status="awaiting_user",
					error=self._interview_error("answer_required", resumable=True),
				)
			self._note_answer_quality(answer_text)
			try:
				engine = self._mediator.process_denoising_answer(pending["question"], answer_text)
			except Exception as exc:
				return self._failure_receipt("answer", exc)
			self._remember_answer(engine)
			return self._interview_receipt(action="answer", status=self._interview_runtime_status(), engine=engine)
		if normalized == "status":
			return self._interview_receipt(action="status", status=self._interview_runtime_status())
		return self._interview_receipt(
			action=normalized,
			status="refused",
			error=self._interview_error("unknown_action", resumable=True),
		)

	FACTUAL_CORRECTION_CONTRACT_VERSION = "factual-correction-v1"

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

	def export_session_projection(self) -> Optional[Dict[str, Any]]:
		"""Versioned snapshot that can rebuild KG/DG without a new extraction."""
		if not self.interview_started:
			return None
		mediator = self._mediator
		phase_manager = mediator.phase_manager
		kg = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
		dg = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "dependency_graph")
		if kg is None or dg is None or not hasattr(kg, "to_dict") or not hasattr(dg, "to_dict"):
			return None
		meta = dict(self._interview_meta)
		denoiser = getattr(mediator, "denoiser", None)
		history = list(getattr(denoiser, "questions_asked", []) or [])
		projection = {
			"schema_version": self.SESSION_PROJECTION_VERSION,
			"contract_version": self.INTERVIEW_CONTRACT_VERSION,
			"session_id": meta.get("session_id"),
			"session_revision": meta.get("session_revision", 0),
			"phase": phase_manager.current_phase.value,
			"narrative_extraction_count": meta.get("narrative_extraction_count", 0),
			"question_revision": meta.get("question_revision", 0),
			"pending_inquiry": meta.get("pending_inquiry"),
			"answered_inquiries": list(meta.get("answered_inquiries") or []),
			"unknown_reasons": list(meta.get("unknown_reasons") or []),
			"unavailable_reasons": list(meta.get("unavailable_reasons") or []),
			"capped_reasons": list(meta.get("capped_reasons") or []),
			"legal_sufficiency": False,
			"knowledge_graph": kg.to_dict(),
			"dependency_graph": dg.to_dict(),
			"denoiser_history": history,
			"iteration_count": phase_manager.iteration_count,
			"loss_history": list(getattr(phase_manager, "loss_history", []) or []),
			"phase_history": list(getattr(phase_manager, "phase_history", []) or []),
			"intake_case_file": phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file") or {},
			"current_questions": phase_manager.get_phase_data(ComplaintPhase.INTAKE, "current_questions") or [],
			"question_candidates": phase_manager.get_phase_data(ComplaintPhase.INTAKE, "question_candidates") or [],
		}
		return _json_ready(projection)

	def restore_session_projection(self, projection: Dict[str, Any]) -> Dict[str, Any]:
		"""Restore graphs and denoiser history. Does not extract the narrative again."""
		if not isinstance(projection, dict):
			return self._interview_receipt(
				action="resume",
				status="unavailable",
				error=self._interview_error("projection_invalid", resumable=True),
			)
		if projection.get("schema_version") != self.SESSION_PROJECTION_VERSION:
			return self._interview_receipt(
				action="resume",
				status="unavailable",
				error=self._interview_error("projection_version", resumable=True),
			)
		try:
			kg = KnowledgeGraph.from_dict(projection.get("knowledge_graph") or {})
			dg = DependencyGraph.from_dict(projection.get("dependency_graph") or {})
		except Exception as exc:
			return self._failure_receipt("resume", exc)
		phase_manager = self._mediator.phase_manager
		phase_name = str(projection.get("phase") or ComplaintPhase.INTAKE.value)
		try:
			phase_manager.current_phase = ComplaintPhase(phase_name)
		except ValueError:
			phase_manager.current_phase = ComplaintPhase.INTAKE
		phase_manager.update_phase_data(ComplaintPhase.INTAKE, "knowledge_graph", kg)
		phase_manager.update_phase_data(ComplaintPhase.INTAKE, "dependency_graph", dg)
		phase_manager.update_phase_data(ComplaintPhase.INTAKE, "intake_case_file", projection.get("intake_case_file") or {})
		phase_manager.update_phase_data(ComplaintPhase.INTAKE, "current_questions", list(projection.get("current_questions") or []))
		phase_manager.update_phase_data(ComplaintPhase.INTAKE, "question_candidates", list(projection.get("question_candidates") or []))
		phase_manager.iteration_count = int(projection.get("iteration_count") or 0)
		phase_manager.loss_history = list(projection.get("loss_history") or [])
		phase_manager.phase_history = list(projection.get("phase_history") or [])
		denoiser = getattr(self._mediator, "denoiser", None)
		if denoiser is not None:
			denoiser.questions_asked = list(projection.get("denoiser_history") or [])
		self._interview_meta = {
			"started": True,
			"session_id": projection.get("session_id") or f"interview-{uuid4().hex[:12]}",
			"session_revision": int(projection.get("session_revision") or 0),
			"narrative_extraction_count": int(projection.get("narrative_extraction_count") or 0),
			"question_revision": int(projection.get("question_revision") or 0),
			"pending_inquiry": projection.get("pending_inquiry"),
			"answered_inquiries": list(projection.get("answered_inquiries") or []),
			"unknown_reasons": list(projection.get("unknown_reasons") or []),
			"unavailable_reasons": list(projection.get("unavailable_reasons") or []),
			"capped_reasons": list(projection.get("capped_reasons") or []),
		}
		return self._interview_receipt(action="resume", status=self._interview_runtime_status())

	def _remember_start(self, engine: Dict[str, Any]) -> None:
		questions = list((engine or {}).get("initial_questions") or [])
		candidates = list((engine or {}).get("question_candidates") or [])
		self._interview_meta = {
			"started": True,
			"session_id": f"interview-{uuid4().hex[:12]}",
			"session_revision": 1,
			"case_id": str(getattr(self, "_bound_case_id", "") or ""),
			"narrative_extraction_count": 1,
			"question_revision": 1 if questions else 0,
			"pending_inquiry": self._inquiry_from_question(questions[0], revision=1) if questions else None,
			"answered_inquiries": [],
			"unknown_reasons": [],
			"unavailable_reasons": [],
			"capped_reasons": ["question_cap"] if len(candidates) > len(questions) else [],
		}

	def _remember_answer(self, engine: Dict[str, Any]) -> None:
		meta = self._interview_meta
		previous = meta.get("pending_inquiry") or {}
		meta["answered_inquiries"] = list(meta.get("answered_inquiries") or []) + [
			{"inquiry_id": previous.get("inquiry_id"), "revision": previous.get("revision")}
		]
		meta["session_revision"] = int(meta.get("session_revision") or 0) + 1
		questions = list((engine or {}).get("next_questions") or [])
		candidates = list((engine or {}).get("question_candidates") or [])
		if len(candidates) > len(questions) and "question_cap" not in meta["capped_reasons"]:
			meta["capped_reasons"] = list(meta.get("capped_reasons") or []) + ["question_cap"]
		if questions:
			revision = int(meta.get("question_revision") or 0) + 1
			meta["question_revision"] = revision
			meta["pending_inquiry"] = self._inquiry_from_question(questions[0], revision=revision)
		else:
			meta["pending_inquiry"] = None

	def _note_answer_quality(self, answer_text: str) -> None:
		lowered = answer_text.lower()
		unknown_tokens = {"unknown", "not sure", "unsure", "i don't know", "i do not know", "n/a", "na", "none"}
		meta = self._interview_meta
		if lowered in unknown_tokens and "user_answer_unknown" not in meta.get("unknown_reasons", []):
			meta["unknown_reasons"] = list(meta.get("unknown_reasons") or []) + ["user_answer_unknown"]

	def _canonical_pending_question(self) -> Optional[Dict[str, Any]]:
		questions = self._mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "current_questions") or []
		if not questions or not isinstance(questions[0], dict):
			return None
		meta = self._interview_meta
		inquiry = meta.get("pending_inquiry") or self._inquiry_from_question(
			questions[0], revision=int(meta.get("question_revision") or 1)
		)
		meta["pending_inquiry"] = inquiry
		return {"inquiry": inquiry, "question": questions[0]}

	def _stale_refusal(self, pending: Dict[str, Any], inquiry_id: Optional[str], expected_revision: Optional[int]) -> Optional[Dict[str, Any]]:
		inquiry = pending["inquiry"]
		supplied_id = str(inquiry_id or "").strip()
		if supplied_id and supplied_id != inquiry.get("inquiry_id"):
			return self._interview_receipt(
				action="answer",
				status="refused",
				error=self._interview_error("stale_question", resumable=True),
			)
		if expected_revision is not None and int(expected_revision) != int(inquiry.get("revision") or 0):
			return self._interview_receipt(
				action="answer",
				status="refused",
				error=self._interview_error("stale_question", resumable=True),
			)
		return None

	def _inquiry_from_question(self, question: Dict[str, Any], *, revision: int) -> Dict[str, Any]:
		qtype = str(question.get("type") or "clarification")
		text = str(question.get("question") or "").strip()
		digest = hashlib.sha256(f"{qtype}|{text}".encode("utf-8")).hexdigest()[:16]
		reasons = []
		if not text:
			reasons.append("question_text_unavailable")
		return {
			"inquiry_id": f"inq-{digest}",
			"revision": int(revision),
			"question": text,
			"question_type": qtype,
			"kind": "graph",
			"unknown_reasons": reasons,
			"legal_sufficiency": False,
		}

	def _narrative_prompt_inquiry(self) -> Dict[str, Any]:
		return {
			"inquiry_id": "inq-narrative",
			"revision": 0,
			"question": "Describe your complaint in plain language.",
			"question_type": "narrative",
			"kind": "narrative",
			"legal_sufficiency": False,
		}

	def _interview_runtime_status(self) -> str:
		if not self.interview_started:
			return "awaiting_user"
		pending = (self._interview_meta or {}).get("pending_inquiry")
		return "awaiting_user" if pending else "complete"

	def _failure_receipt(self, action: str, exc: BaseException) -> Dict[str, Any]:
		privacy = getattr(exc, "description", "") if exc.__class__.__name__ == "UserPresentableException" else ""
		if isinstance(privacy, str) and privacy.startswith("privacy_denied"):
			meta = getattr(self, "_interview_meta", None)
			if isinstance(meta, dict) and "privacy_refused" not in meta.get("unavailable_reasons", []):
				meta["unavailable_reasons"] = list(meta.get("unavailable_reasons") or []) + ["privacy_refused"]
			return self._interview_receipt(
				action=action,
				status="refused",
				error=self._interview_error("privacy_refused", resumable=True, detail=privacy),
			)
		return self._interview_receipt(
			action=action,
			status="unavailable",
			error=self._interview_error(
				"capability_unavailable",
				resumable=True,
				detail=type(exc).__name__,
			),
		)

	def _interview_error(self, code: str, *, resumable: bool, detail: Optional[str] = None) -> Dict[str, Any]:
		error = {"code": code, "resumable": bool(resumable), "legal_sufficiency": False}
		if detail and detail.startswith("privacy_denied"):
			error["reason"] = detail
		elif detail:
			error["error_type"] = detail
		return error

	def _interview_receipt(
		self,
		*,
		action: str,
		status: str,
		inquiry: Optional[Dict[str, Any]] = None,
		error: Optional[Dict[str, Any]] = None,
		engine: Optional[Dict[str, Any]] = None,
	) -> Dict[str, Any]:
		meta = getattr(self, "_interview_meta", None) or {}
		pending = inquiry if inquiry is not None else meta.get("pending_inquiry")
		kg = None
		try:
			kg = self._mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, "knowledge_graph")
		except Exception:
			kg = None
		graph = {
			"entity_count": len(getattr(kg, "entities", {}) or {}),
			"relationship_count": len(getattr(kg, "relationships", {}) or {}),
			"graph_id": getattr(kg, "graph_id", "") if kg is not None else "",
			"graph_version": getattr(kg, "graph_version", "") if kg is not None else "",
			"provenance": {},
			"legal_sufficiency": False,
		}
		if kg is not None:
			provenance = getattr(kg, "provenance", None)
			if not isinstance(provenance, dict):
				provenance = (getattr(kg, "metadata", {}) or {}).get("provenance")
			if isinstance(provenance, dict):
				graph["provenance"] = {"keys": sorted(str(key) for key in provenance.keys())}
		readiness = {}
		if isinstance(engine, dict) and isinstance(engine.get("intake_readiness"), dict):
			readiness = {
				"ready_to_advance": bool(engine["intake_readiness"].get("ready_to_advance", False)),
				"legal_sufficiency": False,
			}
		receipt = {
			"contract_version": self.INTERVIEW_CONTRACT_VERSION,
			"action": action,
			"status": status,
			"awaiting_user": status == "awaiting_user",
			"session_id": meta.get("session_id"),
			"session_revision": int(meta.get("session_revision") or 0),
			"narrative_extraction_count": int(meta.get("narrative_extraction_count") or 0),
			"inquiry": pending,
			"expected_question_revision": None if not isinstance(pending, dict) else pending.get("revision"),
			"answered_count": len(meta.get("answered_inquiries") or []),
			"graph": graph,
			"readiness": readiness,
			"unknown_reasons": list(meta.get("unknown_reasons") or []),
			"unavailable_reasons": list(meta.get("unavailable_reasons") or []),
			"capped_reasons": list(meta.get("capped_reasons") or []),
			"legal_sufficiency": False,
			"error": error,
		}
		if isinstance(pending, dict) and pending.get("unknown_reasons"):
			for reason in pending["unknown_reasons"]:
				if reason not in receipt["unknown_reasons"]:
					receipt["unknown_reasons"].append(reason)
		return receipt

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

	def declare_legal_evidence_hook_operations(self) -> Dict[str, Any]:
		"""Record the disabled legal/evidence registry. Does not write case state."""
		from mediator.hook_runtime import register_legal_evidence_operations

		receipt = register_legal_evidence_operations()
		self._legal_evidence_operation_registry = receipt
		self._legal_evidence_handlers_enabled = False
		return receipt

	def dispatch_legal_evidence_hook_operation(self, request: Any, **kwargs: Any) -> Dict[str, Any]:
		"""Refuse acquire, ingest, and refresh until later consent and storage tasks."""
		from mediator.hook_runtime import dispatch_registered_hook_operation

		if self.__dict__.get("_legal_evidence_operation_registry") is None:
			from mediator.hook_runtime import HOOK_OPERATION_RESULT_SCHEMA

			return {
				"schema": HOOK_OPERATION_RESULT_SCHEMA,
				"operation": str(request.get("operation") or "") if isinstance(request, dict) else "",
				"status": "refused",
				"code": "operation_unregistered",
				"candidate_status": "refused",
				"source_status": "refused",
				"support_status": "refused",
				"proof_status": "not_proof",
				"source_refs": [],
				"source_refs_admitted": False,
				"handler_enabled": False,
				"handler_invoked": False,
				"effect_dispatched": False,
				"provider_invoked": False,
				"backend_invoked": False,
				"storage_invoked": False,
				"writes": 0,
				"dispatch_enabled": False,
			}
		kwargs.pop("probes", None)
		kwargs.pop("effect", None)
		kwargs.pop("handler", None)
		return dispatch_registered_hook_operation(request, **kwargs)

	def accept_bound_hook_effect(self, **kwargs: Any) -> Dict[str, Any]:
		"""Admit one hook effect through the case graph's revision ledger.

		Candidate acquisitions stay on this service. They are not written into
		the graph, the pending inquiry, or the saved case, and a receipt is not
		treated as durability or proof. No second session database is opened.
		"""
		from mediator.hook_runtime import accept_bound_hook_effect

		graph = kwargs.pop("graph", None)
		if graph is None:
			phase_manager = getattr(self._mediator, "phase_manager", None)
			getter = getattr(phase_manager, "get_phase_data", None)
			graph = getter(ComplaintPhase.INTAKE, "knowledge_graph") if getter is not None else None
		meta = self.__dict__.get("_interview_meta")
		if "pending_inquiry" not in kwargs:
			kwargs["pending_inquiry"] = meta.get("pending_inquiry") if isinstance(meta, dict) else None
		if "saved_case" not in kwargs:
			phase_manager = getattr(self._mediator, "phase_manager", None)
			getter = getattr(phase_manager, "get_phase_data", None)
			loaded = getter(ComplaintPhase.INTAKE, "intake_case_file") if getter is not None else None
			kwargs["saved_case"] = loaded if isinstance(loaded, dict) else {}
		log = self.__dict__.setdefault("_hook_candidate_acquisitions", [])
		kwargs.setdefault("acquisition_log", log)
		pending_before = kwargs.get("pending_inquiry")
		saved_before = kwargs.get("saved_case")
		result = accept_bound_hook_effect(graph=graph, **kwargs)
		if isinstance(meta, dict) and meta.get("pending_inquiry") is not pending_before and "pending_inquiry" not in kwargs:
			result["mutated_pending_inquiry"] = True
		if saved_before is not kwargs.get("saved_case"):
			result["mutated_saved_case"] = True
		result["candidate_log_count"] = len(log)
		result["receipt_is_durable"] = False
		result["receipt_is_proof"] = False
		return result


	def _bound_case_ids(self, knowledge_graph) -> Dict[str, str]:
		meta = getattr(self, "_interview_meta", None) or {}
		privacy = getattr(self._mediator, "_interview_privacy_context", None)
		graph_case = ""
		metadata = getattr(knowledge_graph, "metadata", None)
		if isinstance(metadata, dict):
			graph_case = str(metadata.get("case_id") or "")
		privacy_case = str(privacy.get("case_id") or "") if isinstance(privacy, dict) else ""
		return {
			"session": str(meta.get("case_id") or getattr(self, "_bound_case_id", "") or ""),
			"privacy": privacy_case,
			"graph": graph_case,
		}

	def _correction_case_refusal(self, knowledge_graph, *, action, case_id, event_id, target_stable_id):
		bound = self._bound_case_ids(knowledge_graph)
		requested = str(case_id or "")
		present = [value for value in bound.values() if value]
		if not requested or not present or any(value != requested for value in present):
			return self._correction_receipt(
				status="refused",
				action=action,
				case_id=requested,
				event_id=event_id,
				target_stable_id=target_stable_id,
				error_code="cross_case",
				knowledge_graph=knowledge_graph,
			)
		return None

	def _correction_target_refusal(
		self,
		knowledge_graph,
		*,
		action,
		case_id,
		event_id,
		target_stable_id,
		statement,
		source_context,
		expected_graph_revision,
		expected_session_revision,
	):
		from mediator.hook_runtime import graph_revision_token

		current_session = int((self._interview_meta or {}).get("session_revision") or 0)
		current_graph = graph_revision_token(knowledge_graph)
		stale = (
			expected_session_revision is None
			or int(expected_session_revision) != current_session
			or str(expected_graph_revision or "") != current_graph
		)
		if stale:
			return self._correction_receipt(
				status="refused",
				action=action,
				case_id=case_id,
				event_id=event_id,
				target_stable_id=target_stable_id,
				error_code="stale_target",
				knowledge_graph=knowledge_graph,
			)
		denoiser = getattr(self._mediator, "denoiser", None)
		if denoiser is not None and hasattr(denoiser, "classify_answer_disposition"):
			disposition = denoiser.classify_answer_disposition(statement)
			if disposition in getattr(denoiser, "_NON_FACT_DISPOSITIONS", ()):
				return self._correction_receipt(
					status="refused",
					action=action,
					case_id=case_id,
					event_id=event_id,
					target_stable_id=target_stable_id,
					error_code="correction_required",
					knowledge_graph=knowledge_graph,
				)
		if not isinstance(source_context, dict) or not str(source_context.get("source_text") or ""):
			return self._correction_receipt(
				status="refused",
				action=action,
				case_id=case_id,
				event_id=event_id,
				target_stable_id=target_stable_id,
				error_code="correction_required",
				knowledge_graph=knowledge_graph,
			)
		target = str(target_stable_id or "").strip()
		entity = knowledge_graph.entity_for_stable_id(target) if target else None
		if entity is None:
			return self._correction_receipt(
				status="refused",
				action=action,
				case_id=case_id,
				event_id=event_id,
				target_stable_id=target,
				error_code="missing_target",
				knowledge_graph=knowledge_graph,
			)
		if knowledge_graph.entity_activity(entity.id) in {"superseded", "retracted", "conflict"}:
			return self._correction_receipt(
				status="refused",
				action=action,
				case_id=case_id,
				event_id=event_id,
				target_stable_id=target,
				error_code="stale_target",
				knowledge_graph=knowledge_graph,
			)
		return None

	def _correction_question(self, event_id: str, action: str) -> Dict[str, Any]:
		return {
			"type": "clarification",
			"question": "What is the corrected fact?",
			"context": {
				"fact_type": "clarification",
				"factual_action": action,
				"correction_event_id": event_id,
			},
			"candidate_source": "factual_correction",
		}

	def _affected_support_targets(self, knowledge_graph, updates: Dict[str, Any], target_stable_id: str) -> List[Dict[str, Any]]:
		previous = None
		if knowledge_graph is not None and target_stable_id and hasattr(knowledge_graph, "entity_for_stable_id"):
			previous = knowledge_graph.entity_for_stable_id(target_stable_id)
		previous_id = getattr(previous, "id", "")
		found: List[Dict[str, Any]] = []
		seen = set()
		relationships = getattr(knowledge_graph, "relationships", {}) or {}
		for relationship in relationships.values():
			attributes = getattr(relationship, "attributes", {}) or {}
			if attributes.get("activity_status") != "invalidated":
				continue
			if previous_id and str(attributes.get("invalidated_entity_id") or "") not in {"", previous_id}:
				continue
			if previous_id and previous_id not in {getattr(relationship, "source_id", ""), getattr(relationship, "target_id", "")}:
				continue
			source_id = str(getattr(relationship, "source_id", "") or "")
			target_id = str(getattr(relationship, "target_id", "") or "")
			other = target_id if source_id == previous_id else source_id
			item = {
				"relationship_id": str(getattr(relationship, "id", "") or ""),
				"target_id": other,
				"relation_type": str(getattr(relationship, "relation_type", "") or ""),
			}
			key = (item["relationship_id"], item["target_id"])
			if key in seen:
				continue
			seen.add(key)
			found.append(item)
		for node_id in updates.get("dependency_nodes_invalidated") or []:
			item = {"relationship_id": "", "target_id": str(node_id), "relation_type": "dependency"}
			key = ("", item["target_id"])
			if key in seen:
				continue
			seen.add(key)
			found.append(item)
		return found

	def _correction_receipt(
		self,
		*,
		status: str,
		action: str,
		case_id: str,
		event_id: str,
		target_stable_id: str,
		error_code: Optional[str] = None,
		error_type: Optional[str] = None,
		idempotent_replay: bool = False,
		graph_mutated: bool = False,
		updates: Optional[Dict[str, Any]] = None,
		knowledge_graph=None,
	) -> Dict[str, Any]:
		from mediator.hook_runtime import graph_revision_token

		meta = getattr(self, "_interview_meta", None) or {}
		updates = updates or {}
		graph_revision = ""
		revision_index = 0
		lineage = {
			"action": "supersede" if action == "correct" else "retract",
			"previous_stable_id": target_stable_id,
			"new_stable_id": str(updates.get("stable_id") or ""),
			"previous_envelope_retained": False,
			"replacement_envelope_retained": False,
		}
		if knowledge_graph is not None and hasattr(knowledge_graph, "factual_ledger"):
			graph_revision = graph_revision_token(knowledge_graph)
			revision_index = len(knowledge_graph.factual_ledger().get("revisions") or [])
			previous_state = knowledge_graph.assertion_state(target_stable_id) if target_stable_id else {}
			replacement_state = knowledge_graph.assertion_state(lineage["new_stable_id"]) if lineage["new_stable_id"] else {}
			lineage["previous_envelope_retained"] = isinstance(previous_state.get("envelope"), dict)
			lineage["replacement_envelope_retained"] = isinstance(replacement_state.get("envelope"), dict)
			lineage["previous_status"] = str(previous_state.get("status") or "")
			lineage["replacement_status"] = str(replacement_state.get("status") or "")
		error = None
		if error_code:
			error = {"code": error_code, "resumable": error_code != "event_conflict", "legal_sufficiency": False}
			if error_type:
				error["error_type"] = error_type
		return {
			"contract_version": self.FACTUAL_CORRECTION_CONTRACT_VERSION,
			"status": status,
			"action": action,
			"case_id": case_id,
			"event_id": event_id,
			"target_stable_id": target_stable_id,
			"replacement_stable_id": lineage["new_stable_id"],
			"idempotent_replay": bool(idempotent_replay),
			"graph_mutated": bool(graph_mutated),
			"display_only": False,
			"graph_revision": graph_revision,
			"graph_revision_index": revision_index,
			"session_revision": int(meta.get("session_revision") or 0),
			"affected_support_targets": self._affected_support_targets(knowledge_graph, updates, target_stable_id) if status == "applied" else [],
			"lineage": lineage,
			"awaiting_user": False,
			"worker_stalled": False,
			"legal_sufficiency": False,
			"error": error,
		}


def _json_ready(value: Any) -> Any:
	"""Drop values that cannot be stored in the versioned session projection."""
	try:
		return json.loads(json.dumps(value, default=_json_default))
	except (TypeError, ValueError):
		return None


def _json_default(value: Any) -> Any:
	if isinstance(value, set):
		return sorted(value)
	name = getattr(value, "value", None)
	if isinstance(name, str):
		return name
	raise TypeError(type(value).__name__)


# A concise name for new integrations.  Keep WorkflowActionService as the
# defining class so its identity and name remain stable for existing callers.
WorkflowService = WorkflowActionService
