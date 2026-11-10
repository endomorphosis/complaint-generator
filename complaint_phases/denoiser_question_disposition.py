"""Question-disposition methods delegated from ComplaintDenoiser.

The functions keep the original method bodies. Callers on the class forward
here so disposition and phase-1 question metadata stay behavior-compatible.
"""

from typing import Any, Dict, List, Optional

from .dependency_graph import DependencyGraph
from .knowledge_graph import KnowledgeGraph


def record_question_disposition(
    self,
    question: Dict[str, Any],
    answer: Any = "",
    *,
    disposition: Any = None,
    reason: Any = None,
    intake_case_file: Optional[Dict[str, Any]] = None,
    creates_fact: bool = False,
    satisfies_requirement: bool = False,
    contradictory_conclusion: bool = False,
) -> Dict[str, Any]:
    from complaint_phases.intake_case_file import record_question_disposition as persist_disposition
    legal_targets = None
    if isinstance(question, dict) and str(question.get('type') or '').lower() == 'legal_context':
        case = intake_case_file if isinstance(intake_case_file, dict) else self._legal_context_case_file()
        graph = None
        manager = getattr(self.mediator, 'phase_manager', None)
        if manager is not None:
            from complaint_phases.phase_manager import ComplaintPhase
            graph = manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
        legal_targets = self._current_legal_context_question_targets(graph, case)
    bound = self._bind_unresolved_target(question if isinstance(question, dict) else {},
                                         legal_context_targets=legal_targets)
    target_id, revision, kind = self._target_identity(bound if isinstance(bound, dict) else {})
    if not target_id and isinstance(question, dict):
        slot = self._standard_intake_slot(question)
        if slot:
            kind = "proof" if slot == "notice" else "factual"
            target_id = f"{kind}:standard-intake:{slot}"
            revision = revision or self._question_scope_revision
    classified = self.classify_answer_disposition(answer, explicit=disposition)
    non_fact = classified in self._NON_FACT_DISPOSITIONS
    record = {
        "target_id": target_id,
        "target_revision": revision or self._question_scope_revision or "unresolved",
        "target_kind": kind or None,
        "disposition": classified,
        "question": str((bound or question or {}).get("question") or "") or None,
        "answer": None if non_fact else answer,
        "reason": str(reason or "").strip() or None,
        "creates_fact": False if non_fact else bool(creates_fact),
        "satisfies_requirement": False if non_fact else bool(satisfies_requirement),
        "contradictory_conclusion": False if non_fact else bool(contradictory_conclusion),
        "reopened": False,
        "status": "disposed",
    }
    if target_id:
        self.objective_repeat_counts[target_id] = int(self.objective_repeat_counts.get(target_id) or 0) + 1
    if classified in {"unknown", "skipped", "deferred"} or not str(answer or "").strip():
        self.no_information_attempts = int(getattr(self, "no_information_attempts", 0) or 0) + 1
    if target_id:
        self.question_disposition_records = [
            item for item in self.question_disposition_records
            if not (
                isinstance(item, dict)
                and str(item.get("target_id") or "") == target_id
                and str(item.get("target_revision") or "") == record["target_revision"]
                and not item.get("reopened")
            )
        ]
        self.question_disposition_records.append(dict(record))
    case_file = intake_case_file if isinstance(intake_case_file, dict) else None
    if case_file is None and self.mediator is not None:
        phase_manager = getattr(self.mediator, "phase_manager", None)
        getter = getattr(phase_manager, "get_phase_data", None)
        if callable(getter):
            try:
                from complaint_phases.phase_manager import ComplaintPhase
                loaded = getter(ComplaintPhase.INTAKE, "intake_case_file")
            except Exception:
                loaded = None
            if isinstance(loaded, dict):
                case_file = loaded
    if isinstance(case_file, dict) and target_id:
        persist_disposition(
            case_file,
            target_id=target_id,
            target_revision=record["target_revision"],
            disposition=classified,
            target_kind=kind,
            question=record["question"],
            answer=record["answer"],
            reason=record["reason"],
            creates_fact=record["creates_fact"],
            satisfies_requirement=record["satisfies_requirement"],
            contradictory_conclusion=record["contradictory_conclusion"],
        )
    return record


def reopen_disposed_question(
    self,
    target_id: Any,
    reason: Any,
    *,
    target_revision: Any = None,
    intake_case_file: Optional[Dict[str, Any]] = None,
    evidence_change: Any = None,
    scope_change: Any = None,
) -> Dict[str, Any]:
    from complaint_phases.intake_case_file import reopen_question_disposition
    why = str(reason or "").strip()
    evidence = str(evidence_change or "").strip() or None
    scope = str(scope_change or "").strip() or None
    if not why:
        raise ValueError("reopening a disposed question requires a reason")
    if not evidence and not scope:
        raise ValueError("reopening a disposed question requires new evidence or changed scope")
    wanted = str(target_id or "").strip()
    case_file = intake_case_file if isinstance(intake_case_file, dict) else None
    if case_file is None and self.mediator is not None:
        phase_manager = getattr(self.mediator, "phase_manager", None)
        getter = getattr(phase_manager, "get_phase_data", None)
        if callable(getter):
            try:
                from complaint_phases.phase_manager import ComplaintPhase
                loaded = getter(ComplaintPhase.INTAKE, "intake_case_file")
            except Exception:
                loaded = None
            if isinstance(loaded, dict):
                case_file = loaded
    if isinstance(case_file, dict):
        reopened = reopen_question_disposition(
            case_file,
            wanted,
            reason=why,
            target_revision=target_revision,
            evidence_change=evidence,
            scope_change=scope,
        )
    else:
        if not any(
            isinstance(item, dict) and str(item.get("target_id") or "") == wanted and not item.get("reopened")
            for item in self.question_disposition_records
        ) and wanted not in (self.target_dispositions or {}):
            raise ValueError("no disposed question matches that target")
        reopened = {
            "target_id": wanted,
            "target_revision": str(target_revision or self._question_scope_revision or "unresolved"),
            "disposition": str((self.target_dispositions or {}).get(wanted) or "unknown"),
            "reopened": True,
            "reopen_reason": why,
            "evidence_change": evidence,
            "scope_change": scope,
            "status": "reopened",
            "creates_fact": False,
            "satisfies_requirement": False,
            "contradictory_conclusion": False,
        }
    self.question_disposition_records.append(dict(reopened))
    if wanted in self.target_dispositions:
        self.target_dispositions.pop(wanted, None)
    if scope:
        self._question_scope_revision = scope
    return reopened


def load_question_dispositions(self, intake_case_file: Optional[Dict[str, Any]]) -> None:
    if isinstance(intake_case_file, dict):
        scope = intake_case_file.get("question_scope_revision") or intake_case_file.get("scope_revision")
        legal = intake_case_file.get("legal_context") if isinstance(intake_case_file.get("legal_context"), dict) else {}
        scope = scope or legal.get("scope_revision")
        if str(scope or "").strip():
            self._question_scope_revision = str(scope).strip()
    from complaint_phases.intake_case_file import question_disposition_records
    incoming = question_disposition_records(intake_case_file)
    seen = {
        (
            str(item.get("target_id") or ""),
            str(item.get("target_revision") or ""),
            str(item.get("disposition") or ""),
            bool(item.get("reopened")),
            str(item.get("reopen_reason") or ""),
        )
        for item in self.question_disposition_records
        if isinstance(item, dict)
    }
    for record in incoming:
        key = (
            record["target_id"],
            record["target_revision"],
            record["disposition"],
            bool(record["reopened"]),
            str(record.get("reopen_reason") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        self.question_disposition_records.append(dict(record))


def is_question_target_closed(self, target_id: Any, target_revision: Any = None) -> bool:
    wanted = str(target_id or "").strip()
    if not wanted:
        return False
    revision = str(target_revision or "").strip()
    blanket = str((self.target_dispositions or {}).get(wanted) or "").strip().lower()
    if blanket in self._CLOSED_TARGET_DISPOSITIONS:
        reopened = False
        for record in self.question_disposition_records:
            if not isinstance(record, dict) or str(record.get("target_id") or "") != wanted:
                continue
            if record.get("reopened"):
                reopen_revision = str(record.get("target_revision") or "")
                if not revision or not reopen_revision or reopen_revision == revision:
                    reopened = True
        if not reopened:
            return True
    closed = False
    for record in self.question_disposition_records:
        if not isinstance(record, dict) or str(record.get("target_id") or "") != wanted:
            continue
        if record.get("reopened"):
            reopen_revision = str(record.get("target_revision") or "")
            if not revision or not reopen_revision or reopen_revision == revision:
                closed = False
            continue
        disposition = str(record.get("disposition") or "").strip().lower()
        if disposition in self._CLOSED_TARGET_DISPOSITIONS or disposition in self._NON_FACT_DISPOSITIONS:
            closed = True
    return closed


def _phase1_question_targeting(
    self,
    question_type: str,
    context: Optional[Dict[str, Any]] = None,
    source: str = '',
) -> Dict[str, Any]:
    """Attach section-aware routing metadata to phase-1 intake questions."""
    context = context or {}
    qtype = (question_type or '').strip().lower()

    defaults = {
        'phase1_section': 'general',
        'target_claim_type': str(context.get('claim_type') or ''),
        'target_element_id': str(context.get('requirement_id') or context.get('target_element_id') or ''),
        'target_fact_type': '',
        'blocking_level': 'important',
        'expected_update_kind': 'clarify_record',
    }

    if qtype == 'contradiction':
        defaults.update({
            'phase1_section': 'contradictions',
            'target_fact_type': 'contradicted_fact',
            'blocking_level': 'blocking',
            'expected_update_kind': 'resolve_contradiction',
        })
    elif qtype == 'timeline':
        defaults.update({
            'phase1_section': 'chronology',
            'target_fact_type': 'timeline',
            'blocking_level': 'blocking',
            'expected_update_kind': 'add_timeline_fact',
        })
    elif qtype == 'responsible_party':
        defaults.update({
            'phase1_section': 'actors',
            'target_fact_type': 'responsible_party',
            'blocking_level': 'blocking',
            'expected_update_kind': 'identify_actor',
        })
    elif qtype == 'impact':
        defaults.update({
            'phase1_section': 'harm_remedy',
            'target_fact_type': 'impact_or_remedy',
            'blocking_level': 'important',
            'expected_update_kind': 'capture_harm_or_remedy',
        })
    elif qtype == 'requirement':
        defaults.update({
            'phase1_section': 'claim_elements',
            'target_fact_type': 'claim_element',
            'blocking_level': 'blocking',
            'expected_update_kind': 'satisfy_claim_element',
        })
    elif qtype == 'evidence':
        defaults.update({
            'phase1_section': 'proof_leads',
            'target_fact_type': 'proof_lead',
            'blocking_level': 'important',
            'expected_update_kind': 'capture_proof_lead',
        })
    elif qtype == 'relationship':
        defaults.update({
            'phase1_section': 'actors',
            'target_fact_type': 'relationship',
            'blocking_level': 'important',
            'expected_update_kind': 'link_parties',
        })
    elif qtype == 'clarification':
        defaults.update({
            'phase1_section': 'general',
            'target_fact_type': 'uncertain_fact',
            'blocking_level': 'informational',
            'expected_update_kind': 'clarify_fact',
        })

    if not defaults['target_claim_type']:
        defaults['target_claim_type'] = str(context.get('claim_name') or '')
    workflow_phase = str(context.get('workflow_phase') or '').strip().lower() or self._workflow_phase_for_question(qtype, context=context, source=source)
    defaults['workflow_phase'] = workflow_phase
    defaults['workflow_phase_rank'] = int(context.get('workflow_phase_rank', self._phase_focus_rank(workflow_phase)) or self._phase_focus_rank(workflow_phase))
    context_targets = [str(target).strip() for target in (context.get('extraction_targets') or []) if str(target).strip()]
    context_markers = [str(marker).strip() for marker in (context.get('patchability_markers') or []) if str(marker).strip()]
    defaults['extraction_targets'] = context_targets or self._derive_extraction_targets(qtype, context=context)
    defaults['patchability_markers'] = context_markers or self._derive_patchability_markers(qtype, context=context)
    if context.get('recommended_resolution_lane'):
        defaults['recommended_resolution_lane'] = str(context.get('recommended_resolution_lane') or '')

    return defaults


def _phase1_question_metadata(
    self,
    question_type: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    context = context or {}
    qtype = (question_type or '').strip().lower()

    if qtype == 'timeline':
        return {
            'question_objective': 'establish_chronology',
            'question_reason': 'Chronology is necessary to determine sequence, notice, and causation.',
            'expected_proof_gain': 'high',
            'proof_priority': self._phase1_proof_priority(qtype),
        }
    if qtype == 'contradiction':
        contradiction_label = str(context.get('contradiction_label') or 'the conflicting facts')
        return {
            'question_objective': 'resolve_factual_contradiction',
            'question_reason': f"The intake record contains conflicting information about {contradiction_label} that should be reconciled before relying on it.",
            'expected_proof_gain': 'high',
            'proof_priority': self._phase1_proof_priority(qtype),
        }
    if qtype == 'responsible_party':
        return {
            'question_objective': 'identify_responsible_party',
            'question_reason': 'The complaint needs a concrete actor or organization tied to the alleged conduct.',
            'expected_proof_gain': 'high',
            'proof_priority': self._phase1_proof_priority(qtype),
        }
    if qtype == 'impact':
        return {
            'question_objective': 'capture_harm_and_requested_remedy',
            'question_reason': 'The intake record should state both the harm suffered and the outcome being sought.',
            'expected_proof_gain': 'high',
            'proof_priority': self._phase1_proof_priority(qtype),
        }
    if qtype == 'requirement':
        requirement_name = str(context.get('requirement_name') or 'this claim element')
        claim_name = str(context.get('claim_name') or 'the claim')
        return {
            'question_objective': 'satisfy_claim_requirement',
            'question_reason': f"{requirement_name} is still missing for {claim_name}.",
            'expected_proof_gain': 'high',
            'proof_priority': self._phase1_proof_priority(qtype),
        }
    if qtype == 'evidence':
        claim_name = str(context.get('claim_name') or 'the claim')
        return {
            'question_objective': 'identify_supporting_evidence',
            'question_reason': f"{claim_name} still needs supporting proof leads or corroborating evidence.",
            'expected_proof_gain': 'high',
            'proof_priority': self._phase1_proof_priority(qtype),
        }
    if qtype == 'clarification':
        entity_name = str(context.get('entity_name') or 'this fact')
        return {
            'question_objective': 'clarify_low_confidence_fact',
            'question_reason': f"The current record about {entity_name} is too uncertain to rely on safely.",
            'expected_proof_gain': 'medium',
            'proof_priority': self._phase1_proof_priority(qtype),
        }
    if qtype == 'relationship':
        entity_name = str(context.get('entity_name') or 'this entity')
        return {
            'question_objective': 'connect_parties_and_facts',
            'question_reason': f"{entity_name} needs clearer linkage to the complaint narrative.",
            'expected_proof_gain': 'medium',
            'proof_priority': self._phase1_proof_priority(qtype),
        }

    return {
        'question_objective': 'general_intake_clarification',
        'question_reason': 'This question helps fill a remaining intake gap.',
        'expected_proof_gain': 'medium',
        'proof_priority': self._phase1_proof_priority(qtype),
    }


def generate_questions(self, 
                      knowledge_graph: KnowledgeGraph,
                      dependency_graph: DependencyGraph,
                      max_questions: int = 10,
                      intake_case_file: Optional[Dict[str, Any]] = None,
                      additional_candidates: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """
    Generate questions to denoise the complaint.
    
    Args:
        knowledge_graph: Current knowledge graph
        dependency_graph: Current dependency graph
        max_questions: Maximum number of questions to generate
        
    Returns:
        List of question dictionaries with type, question text, and context
    """
    self.load_question_dispositions(intake_case_file)
    legal_context_targets = self._current_legal_context_question_targets(knowledge_graph, intake_case_file)
    # Subsequent public answer turns do not pass additional_candidates.
    # Rederive their open context prompts instead of losing them after turn one.
    if additional_candidates is None:
        additional_candidates = [
            {'type': 'legal_context', 'question_id': item['question_id'],
             'field': item['field'], 'question': item['prompt'], 'priority': 'critical'}
            for item in legal_context_targets.values()
        ]
    questions = self.collect_question_candidates(
        knowledge_graph,
        dependency_graph,
        max_questions=max_questions,
        intake_case_file=intake_case_file,
    )
    # Context questions join the same selection pass as graph questions.
    questions = [candidate for candidate in (additional_candidates or [])
                 if isinstance(candidate, dict)] + questions
    prepared = []
    for candidate in questions:
        if str(candidate.get('type') or candidate.get('question_type') or '').strip().lower() == 'legal_context':
            candidate = self._bind_unresolved_target(candidate, legal_context_targets=legal_context_targets)
            if not candidate.get('unresolved_target'):
                continue
        prepared.append(candidate)
    questions = prepared
    selector = getattr(self.mediator, 'select_intake_question_candidates', None) if self.mediator else None
    questions = self.select_question_candidates(
        questions,
        max_questions=max_questions,
        selector=selector,
        legal_context_targets=legal_context_targets,
    )

    # Ensure we cover basic intake dimensions beyond evidence-only prompts.
    questions = self._ensure_standard_intake_questions(questions, max_questions)

    # Optional exploration/momentum policy (reorders questions only).
    questions = self._apply_exploration_and_momentum(questions)

    # Light empathy / framing tweaks (text-only; doesn't change structure).
    for q in questions:
        qtype = q.get('type', '')
        qtext = q.get('question', '')
        q['question'] = self._with_empathy(qtext, qtype)

    self._record_source_capability_diagnostic(intake_case_file)
    self._record_operator_candidates(list(additional_candidates or []) + list(questions))
    questions = self._finalize_neutral_targeted_questions(questions, legal_context_targets=legal_context_targets)

    # Track questions in pool
    self.questions_pool.extend(questions[:max_questions])

    return questions[:max_questions]
