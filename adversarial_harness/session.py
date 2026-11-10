"""
Adversarial Session Module

Manages a single adversarial training session between complainant and mediator.
"""

import logging
import re
from contextlib import contextmanager
from typing import Dict, Any, List, Set, Sequence, Callable, Optional
from dataclasses import dataclass
from datetime import UTC, datetime
import time

logger = logging.getLogger(__name__)


@dataclass
class SessionResult:
    """Result of an adversarial session."""
    session_id: str
    timestamp: str
    
    # Input
    seed_complaint: Dict[str, Any]
    initial_complaint_text: str
    
    # Conversation
    conversation_history: List[Dict[str, Any]]
    num_questions: int
    num_turns: int
    
    # Outputs
    final_state: Dict[str, Any]
    knowledge_graph_summary: Dict[str, Any] = None
    dependency_graph_summary: Dict[str, Any] = None

    # Optional full graph snapshots (may be large); persisted as separate JSON files.
    knowledge_graph: Dict[str, Any] | None = None
    dependency_graph: Dict[str, Any] | None = None
    
    # Evaluation
    critic_score: Any = None  # CriticScore object
    
    # Timing
    duration_seconds: float = 0.0
    
    # Status
    success: bool = True
    error: str = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        critic_payload = self.critic_score.to_dict() if self.critic_score else None
        result = {
            'session_id': self.session_id,
            'timestamp': self.timestamp,
            'seed_complaint': self.seed_complaint,
            'initial_complaint_text': self.initial_complaint_text,
            'conversation_history': self.conversation_history,
            'num_questions': self.num_questions,
            'num_turns': self.num_turns,
            'final_state': self.final_state,
            'knowledge_graph_summary': self.knowledge_graph_summary,
            'dependency_graph_summary': self.dependency_graph_summary,
            'knowledge_graph': self.knowledge_graph,
            'dependency_graph': self.dependency_graph,
            'critic_score': critic_payload,
            'anchor_section_summary': {
                'expected': list((critic_payload or {}).get('anchor_sections_expected', []) or []),
                'covered': list((critic_payload or {}).get('anchor_sections_covered', []) or []),
                'missing': list((critic_payload or {}).get('anchor_sections_missing', []) or []),
            },
            'duration_seconds': self.duration_seconds,
            'success': self.success,
            'error': self.error
        }
        return result


class AdversarialSession:
    """
    Manages a single adversarial training session.
    
    A session consists of:
    1. Complainant generates initial complaint from seed
    2. Mediator processes complaint and asks questions
    3. Complainant responds to questions
    4. Repeat until completion (convergence or max turns)
    5. Critic evaluates the session
    """
    
    def __init__(self,
                  session_id: str,
                  complainant: Any,  # Complainant instance
                  mediator: Any,  # Mediator instance
                  critic: Any,  # Critic instance
                max_turns: int = 12,
                progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        Initialize adversarial session.
        
        Args:
            session_id: Unique session identifier
            complainant: Complainant instance
            mediator: Mediator instance
            critic: Critic instance
            max_turns: Maximum number of question-answer turns
        """
        self.session_id = session_id
        self.complainant = complainant
        self.mediator = mediator
        self.critic = critic
        self.max_turns = max_turns
        self.progress_callback = progress_callback
        
        self.conversation_history = []
        self.start_time = None
        self.end_time = None

    def _emit_progress(self, stage: str, *, metadata: Optional[Dict[str, Any]] = None) -> None:
        if not callable(self.progress_callback):
            return
        self.progress_callback(
            {
                'session_id': self.session_id,
                'stage': str(stage or ''),
                'timestamp': datetime.now(UTC).isoformat(),
                'metadata': metadata or {},
            }
        )

    @staticmethod
    def _extract_question_text(question: Any) -> str:
        if isinstance(question, dict):
            for key in ('question', 'text', 'prompt', 'content'):
                value = question.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            nested_question = question.get('question')
            if isinstance(nested_question, dict):
                for key in ('text', 'content'):
                    value = nested_question.get(key)
                    if isinstance(value, str) and value.strip():
                        return value
            return ''
        return str(question)

    @staticmethod
    def _extract_question_objective(question: Any) -> str:
        if not isinstance(question, dict):
            return ''
        objective = question.get('question_objective')
        if isinstance(objective, str) and objective.strip():
            return objective.strip().lower()
        nested_question = question.get('question')
        if isinstance(nested_question, dict):
            nested_objective = nested_question.get('question_objective')
            if isinstance(nested_objective, str) and nested_objective.strip():
                return nested_objective.strip().lower()
        return ''

    @staticmethod
    def _extract_question_type(question: Any) -> str:
        if not isinstance(question, dict):
            return ''
        question_type = question.get('type')
        if isinstance(question_type, str) and question_type.strip():
            return question_type.strip().lower()
        nested_question = question.get('question')
        if isinstance(nested_question, dict):
            nested_type = nested_question.get('type')
            if isinstance(nested_type, str) and nested_type.strip():
                return nested_type.strip().lower()
        return ''

    def _refresh_final_intake_case_file_snapshot(self) -> Dict[str, Any] | None:
        """Refresh the stored intake case file from the current knowledge graph when possible."""
        phase_manager = getattr(self.mediator, 'phase_manager', None)
        if phase_manager is None or not hasattr(phase_manager, 'get_phase_data'):
            return None
        try:
            from complaint_phases import ComplaintPhase, build_intake_case_file, refresh_intake_case_file

            knowledge_graph = phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
            intake_case_file = phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file') or {}
            if knowledge_graph is None or not isinstance(intake_case_file, dict):
                return intake_case_file if isinstance(intake_case_file, dict) else None
            refreshed_intake_case_file = refresh_intake_case_file(
                intake_case_file,
                knowledge_graph,
                append_snapshot=False,
            )
            graph_has_structured_timeline = any(
                bool(getattr(entity, 'attributes', {}).get('structured_timeline_group'))
                for entity in getattr(knowledge_graph, 'entities', {}).values()
            )
            case_file_has_structured_timeline = any(
                bool((fact or {}).get('structured_timeline_group'))
                for fact in list(refreshed_intake_case_file.get('canonical_facts') or [])
                if isinstance(fact, dict)
            )
            source_complaint_text = str(intake_case_file.get('source_complaint_text') or '').strip()
            if graph_has_structured_timeline and not case_file_has_structured_timeline:
                rebuilt_intake_case_file = build_intake_case_file(
                    knowledge_graph,
                    complaint_text=source_complaint_text,
                )
                confirmation_record = intake_case_file.get('complainant_summary_confirmation')
                if isinstance(confirmation_record, dict) and confirmation_record:
                    rebuilt_intake_case_file['complainant_summary_confirmation'] = dict(confirmation_record)
                contradiction_queue = intake_case_file.get('contradiction_queue')
                if isinstance(contradiction_queue, list) and contradiction_queue:
                    rebuilt_intake_case_file['contradiction_queue'] = list(contradiction_queue)
                if source_complaint_text and not rebuilt_intake_case_file.get('source_complaint_text'):
                    rebuilt_intake_case_file['source_complaint_text'] = source_complaint_text
                refreshed_intake_case_file = rebuilt_intake_case_file
            if hasattr(phase_manager, 'update_phase_data'):
                phase_manager.update_phase_data(
                    ComplaintPhase.INTAKE,
                    'intake_case_file',
                    refreshed_intake_case_file,
                )
            return refreshed_intake_case_file
        except Exception:
            # Refreshing the final snapshot is best-effort: callers can still use
            # the mediator's existing case file.  Keep that fallback observable,
            # though, because otherwise a stale final result is indistinguishable
            # from a successful refresh.
            logger.warning(
                "Could not refresh the final intake case file for session %s; "
                "using the mediator's existing snapshot",
                self.session_id,
                exc_info=True,
            )

    @staticmethod
    def _normalize_question(question_text: str) -> str:
        return " ".join(question_text.lower().strip().split())

    @staticmethod
    def _strip_leading_wrapper_clauses(question_text: str) -> str:
        """Remove conversational lead-ins that often vary across rephrases."""
        cleaned = question_text.strip()
        wrapper_patterns = (
            r"i (?:understand|am sorry|know|appreciate)[^,]*,\s*",
            r"(?:thanks|thank you)[^,]*,\s*",
            r"(?:before we continue|to clarify|just to clarify|to better understand|so i can help)[^,]*,\s*",
        )
        changed = True
        while cleaned and changed:
            changed = False
            for pattern in wrapper_patterns:
                updated = re.sub(rf"^\s*{pattern}", "", cleaned)
                if updated != cleaned:
                    cleaned = updated.strip()
                    changed = True
        return cleaned

    @staticmethod
    def _question_dedupe_key(question_text: str) -> str:
        normalized = AdversarialSession._normalize_question(question_text)
        normalized = AdversarialSession._strip_leading_wrapper_clauses(normalized)
        # Strip common numbering/list prefixes.
        normalized = re.sub(r"^(?:q(?:uestion)?\s*\d+[:.)-]\s*|\d+[:.)-]\s*)", "", normalized)
        # Strip conversational wrappers so semantically identical prompts
        # map to a stable key when politeness/empathy phrasing varies.
        normalized = re.sub(
            r"^(i (?:understand|am sorry|know|appreciate)[^,]*,\s*)",
            "",
            normalized,
        )
        normalized = re.sub(
            r"^(can you|could you|would you|please|just|let me ask|help me understand)\s+",
            "",
            normalized,
        )
        normalized = re.sub(
            r"^(?:can|could|would)\s+you\s+(?:tell me|share|describe|explain|clarify|walk me through)\s+",
            "",
            normalized,
        )
        normalized = re.sub(
            r"^(?:tell me|share|describe|explain|clarify|walk me through)\s+",
            "",
            normalized,
        )
        normalized = re.sub(r"\s+(please|thanks?)$", "", normalized)
        normalized = re.sub(r"\s+(?:if you can|if possible|when you can)$", "", normalized)
        # Remove punctuation differences so "when did X happen?" and "when did X happen"
        # map to the same dedupe key.
        return " ".join(re.sub(r"[^a-z0-9\s]", " ", normalized).split())

    @staticmethod
    def _question_tokens(question_text: str) -> Set[str]:
        key = AdversarialSession._question_dedupe_key(question_text)
        tokens = set(key.split())
        # Ignore low-information tokens so overlap focuses on intent/content.
        stopwords = {
            "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "at",
            "is", "are", "was", "were", "be", "been", "it", "this", "that", "your",
            "you", "can", "could", "would", "did", "do", "does", "please", "about",
            "what", "when", "where", "who", "how", "why", "any",
        }
        return {t for t in tokens if t and t not in stopwords}

    @staticmethod
    def _question_similarity(question_a: str, question_b: str) -> float:
        tokens_a = AdversarialSession._question_tokens(question_a)
        tokens_b = AdversarialSession._question_tokens(question_b)
        if not tokens_a and not tokens_b:
            return 1.0
        if not tokens_a or not tokens_b:
            return 0.0
        overlap = tokens_a & tokens_b
        union = tokens_a | tokens_b
        return len(overlap) / len(union)

    @staticmethod
    def _question_intent_key(question_text: str, question: Any = None) -> str:
        objective = AdversarialSession._extract_question_objective(question)
        if objective:
            context = question.get('context', {}) if isinstance(question, dict) and isinstance(question.get('context'), dict) else {}
            context_segments = []
            for key in ('requirement_id', 'claim_id', 'entity_id'):
                value = context.get(key)
                if value:
                    context_segments.append(str(value))
            question_type = AdversarialSession._extract_question_type(question)
            base = objective if not question_type else f"{objective}:{question_type}"
            if context_segments:
                return base + ':' + ':'.join(context_segments)
            return base
        normalized = AdversarialSession._question_dedupe_key(question_text)
        stop_words = {
            'a', 'an', 'and', 'are', 'can', 'could', 'did', 'do', 'for', 'from',
            'have', 'how', 'i', 'if', 'in', 'is', 'it', 'me', 'of', 'on', 'or',
            'please', 'share', 'tell', 'that', 'the', 'to', 'was', 'what', 'when',
            'where', 'which', 'who', 'why', 'with', 'would', 'you', 'your',
        }
        tokens = []
        for token in normalized.split():
            if token in stop_words:
                continue
            if token.endswith('ing') and len(token) > 5:
                token = token[:-3]
            elif token.endswith('ed') and len(token) > 4:
                token = token[:-2]
            elif token.endswith('s') and len(token) > 3:
                token = token[:-1]
            tokens.append(token)
        if not tokens:
            return normalized
        return " ".join(tokens)

    @staticmethod
    def _is_redundant_candidate(
        key: str,
        intent_key: str,
        asked_count: int,
        intent_count: int,
        similarity_to_seen: float,
        last_question_key: str | None,
        last_question_intent_key: str | None,
        recent_intent_keys: Set[str] | None = None,
    ) -> bool:
        # Never ask the exact same question back-to-back.
        if key == last_question_key:
            return True
        # Avoid asking the same normalized question more than once.
        if asked_count > 0:
            return True
        # Treat near-identical rephrasings as redundant even when intent bucketing differs.
        if similarity_to_seen >= 0.9:
            return True
        # Avoid immediate intent repetition when it's already substantially similar.
        if (
            last_question_intent_key
            and intent_key == last_question_intent_key
            and similarity_to_seen >= 0.5
        ):
            return True
        # Avoid repeatedly circling the same intent across nearby turns.
        if recent_intent_keys and intent_key in recent_intent_keys and similarity_to_seen >= 0.5:
            return True
        # De-prioritize high-overlap variants once an intent has been asked.
        if intent_count > 0 and similarity_to_seen >= 0.68:
            return True
        return False

    @staticmethod
    def _is_timeline_question(question: Any) -> bool:
        objective = AdversarialSession._extract_question_objective(question)
        question_type = AdversarialSession._extract_question_type(question)
        if objective == 'establish_chronology' or question_type == 'timeline':
            return True
        text = AdversarialSession._extract_question_text(question).lower()
        timeline_terms = (
            'when',
            'date',
            'timeline',
            'chronolog',
            'sequence',
            'what happened first',
            'before',
            'after',
            'when did',
            'date range',
            'how long',
            'start date',
            'end date',
            'first happened',
            'step by step',
            'walk me through',
            'date anchor',
            'decision timeline',
            'actor by actor',
            'actor-by-actor',
        )
        return any(term in text for term in timeline_terms)

    @staticmethod
    def _is_harm_or_remedy_question(question: Any) -> bool:
        objective = AdversarialSession._extract_question_objective(question)
        question_type = AdversarialSession._extract_question_type(question)
        if objective == 'capture_harm_and_requested_remedy' or question_type in {'impact', 'remedy'}:
            return True
        text = AdversarialSession._extract_question_text(question).lower()
        harm_remedy_terms = (
            'harm',
            'impact',
            'affected',
            'damag',
            'loss',
            'distress',
            'remedy',
            'resolve',
            'outcome',
            'seeking',
            'requesting',
            'want',
            'relief',
            'fix',
            'refund',
            'reimburse',
            'compensation',
            'cost',
            'out of pocket',
            'financial',
            'lost wages',
            'make you whole',
            'repair',
            'replace',
            'accommodation',
        )
        return any(term in text for term in harm_remedy_terms)

    @staticmethod
    def _is_actor_or_decisionmaker_question(question: Any) -> bool:
        objective = AdversarialSession._extract_question_objective(question)
        question_type = AdversarialSession._extract_question_type(question)
        if objective == 'identify_responsible_party' or question_type == 'responsible_party':
            return True
        text = AdversarialSession._extract_question_text(question).lower()
        actor_terms = (
            'who',
            'manager',
            'supervisor',
            'decision',
            'hr',
            'human resources',
            'person',
            'individual',
            'name',
            'landlord',
            'owner',
            'employer',
            'staff',
            'employee',
            'representative',
            'agent',
            'contractor',
            'provider',
            'point of contact',
            'contact person',
        )
        return any(term in text for term in actor_terms)

    @staticmethod
    def _is_protected_activity_causation_question(question: Any) -> bool:
        objective = AdversarialSession._extract_question_objective(question)
        question_type = AdversarialSession._extract_question_type(question)
        if objective in {'establish_causation', 'link_protected_activity_to_adverse_action'}:
            return True
        if question_type in {'causation', 'retaliation'}:
            return True
        text = AdversarialSession._extract_question_text(question).lower()
        protected_activity_terms = (
            'protected activity',
            'complaint',
            'reported',
            'accommodation request',
            'grievance',
            'appeal',
        )
        adverse_terms = (
            'adverse action',
            'retaliat',
            'termination',
            'denial',
            'disciplin',
        )
        causation_terms = (
            'because',
            'after',
            'linked',
            'caus',
            'reason',
            'connection',
        )
        return (
            any(term in text for term in protected_activity_terms)
            and any(term in text for term in adverse_terms)
            and any(term in text for term in causation_terms)
        )

    @staticmethod
    def _is_documentary_evidence_question(question: Any) -> bool:
        objective = AdversarialSession._extract_question_objective(question)
        question_type = AdversarialSession._extract_question_type(question)
        text = AdversarialSession._extract_question_text(question).lower()
        if objective == 'identify_supporting_evidence' and question_type == 'evidence':
            return True
        document_terms = (
            'document',
            'email',
            'text message',
            'notice',
            'letter',
            'written',
            'record',
            'records',
            'screenshot',
            'attachment',
            'paperwork',
            'file',
            'contract',
            'agreement',
            'estimate',
            'invoice',
            'receipt',
            'lease',
            'application',
            'screening criteria',
            'policy',
            'warranty',
            'change order',
            'work order',
            'photo',
            'photos',
            'picture',
            'video',
            'payment',
            'check',
            'bank statement',
            'message',
            'messages',
            'chat',
            'communication',
            'communications',
            'call',
            'call log',
            'voicemail',
            'report',
        )
        return any(term in text for term in document_terms)

    @staticmethod
    def _is_exhibit_ready_question(question: Any) -> bool:
        text = AdversarialSession._extract_question_text(question).lower()
        return bool(
            ('exhibit' in text or 'treated as exhibits' in text or 'exhibit-ready' in text)
            and any(
                token in text
                for token in (
                    'date',
                    'sender or source',
                    'label or subject line',
                    'fact the document proves',
                    'fact it proves',
                )
            )
        )

    @staticmethod
    def _build_intake_question_structure_summary(
        conversation_history: Sequence[Dict[str, Any]],
        final_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        mediator_questions = [
            item for item in list(conversation_history or [])
            if isinstance(item, dict) and str(item.get('role') or '').strip().lower() == 'mediator'
        ]
        documentary_questions = [
            item for item in mediator_questions
            if AdversarialSession._is_documentary_evidence_question(item)
        ]
        temporal_document_questions = [
            item for item in mediator_questions
            if (
                AdversarialSession._is_exhibit_ready_question(item)
                and (
                    AdversarialSession._is_hearing_request_timing_question(item)
                    or AdversarialSession._is_response_dates_question(item)
                    or AdversarialSession._is_exact_dates_question(item)
                )
            )
        ]
        exhibit_ready_questions = [
            item for item in mediator_questions
            if AdversarialSession._is_exhibit_ready_question(item)
        ]
        workflow_guidance = (
            final_state.get('workflow_optimization_guidance')
            if isinstance(final_state, dict) and isinstance(final_state.get('workflow_optimization_guidance'), dict)
            else {}
        )
        document_provenance_summary = (
            final_state.get('document_provenance_summary')
            if isinstance(final_state, dict) and isinstance(final_state.get('document_provenance_summary'), dict)
            else {}
        )
        chronology_hints = (
            workflow_guidance.get('document_chronology_priority_hints')
            if isinstance(workflow_guidance.get('document_chronology_priority_hints'), dict)
            else {}
        )
        needs_exhibit_grounding = bool(
            chronology_hints.get('needs_exhibit_grounding')
            or bool(document_provenance_summary.get('low_grounding_flag'))
        )
        documentary_count = len(documentary_questions)
        exhibit_ready_count = len(exhibit_ready_questions)
        return {
            'question_count': len(mediator_questions),
            'documentary_question_count': documentary_count,
            'exhibit_ready_question_count': exhibit_ready_count,
            'temporal_exhibit_ready_question_count': len(temporal_document_questions),
            'documentary_exhibit_ready_question_count': len(
                [item for item in documentary_questions if AdversarialSession._is_exhibit_ready_question(item)]
            ),
            'needs_exhibit_grounding': needs_exhibit_grounding,
            'documentary_exhibit_ready_ratio': round(
                float(exhibit_ready_count) / float(documentary_count),
                4,
            ) if documentary_count > 0 else 0.0,
        }

    @staticmethod
    def _is_witness_question(question: Any) -> bool:
        text = AdversarialSession._extract_question_text(question).lower()
        witness_terms = (
            'witness',
            'anyone else',
            'who else',
            'present',
            'saw',
            'heard',
            'observer',
            'coworker',
            'anyone with you',
            'anyone there',
            'others there',
            'bystander',
        )
        return any(term in text for term in witness_terms)

    @staticmethod
    def _build_runtime_workflow_guidance(final_state: Dict[str, Any]) -> Dict[str, Any]:
        state = final_state if isinstance(final_state, dict) else {}
        intake_sections = state.get('intake_sections') if isinstance(state.get('intake_sections'), dict) else {}
        question_summary = state.get('question_candidate_summary') if isinstance(state.get('question_candidate_summary'), dict) else {}
        packet_summary = state.get('claim_support_packet_summary') if isinstance(state.get('claim_support_packet_summary'), dict) else {}
        alignment_summary = state.get('alignment_task_summary') if isinstance(state.get('alignment_task_summary'), dict) else {}

        intake_focus_areas = [
            str(section_name)
            for section_name, payload in intake_sections.items()
            if isinstance(payload, dict) and str(payload.get('status') or '').strip().lower() != 'complete'
        ]
        graph_focus_areas = []
        if int(packet_summary.get('unsupported_element_count') or 0) > 0:
            graph_focus_areas.append('unsupported_claim_elements')
        if int(alignment_summary.get('temporal_gap_task_count') or 0) > 0:
            graph_focus_areas.append('temporal_support_gaps')
        if int(alignment_summary.get('count') or 0) > 0:
            graph_focus_areas.append('alignment_evidence_tasks')

        current_phase = str(state.get('current_phase') or '').strip().lower()
        document_status = 'ready'
        if current_phase in {'intake', 'evidence'}:
            document_status = 'warning'

        cross_phase_findings: List[str] = []
        if intake_focus_areas and graph_focus_areas:
            cross_phase_findings.append(
                'Unresolved intake gaps are still limiting graph-supported claim development in this session.'
            )
        if current_phase == 'evidence' and graph_focus_areas:
            cross_phase_findings.append(
                'Evidence alignment gaps remain open, so the complaint is not yet ready for final drafting.'
            )

        if not any((intake_focus_areas, graph_focus_areas, cross_phase_findings, question_summary)):
            return {}

        return {
            'phase_scorecards': {
                'intake_questioning': {
                    'status': 'warning' if intake_focus_areas else 'ready',
                    'focus_areas': intake_focus_areas,
                    'question_candidate_count': int(question_summary.get('count') or 0),
                },
                'graph_analysis': {
                    'status': 'warning' if graph_focus_areas else 'ready',
                    'focus_areas': graph_focus_areas,
                    'unsupported_element_count': int(packet_summary.get('unsupported_element_count') or 0),
                    'alignment_task_count': int(alignment_summary.get('count') or 0),
                },
                'document_generation': {
                    'status': document_status,
                    'focus_areas': ['await_phase_completion'] if document_status != 'ready' else [],
                    'current_phase': current_phase,
                },
            },
            'cross_phase_findings': cross_phase_findings,
        }

    @staticmethod
    def _is_contradiction_resolution_question(question: Any) -> bool:
        objective = AdversarialSession._extract_question_objective(question)
        question_type = AdversarialSession._extract_question_type(question)
        if objective == 'resolve_factual_contradiction' or question_type == 'contradiction':
            return True
        text = AdversarialSession._extract_question_text(question).lower()
        contradiction_terms = (
            'conflicting information',
            'which version is correct',
            'contradiction',
            'inconsistent',
            'conflict',
        )
        return any(term in text for term in contradiction_terms)

    @staticmethod
    def _extract_phase1_section(question: Any) -> str:
        if not isinstance(question, dict):
            return ''
        phase1_section = question.get('phase1_section')
        if isinstance(phase1_section, str) and phase1_section.strip():
            return phase1_section.strip().lower()
        explanation = question.get('ranking_explanation')
        if isinstance(explanation, dict):
            nested = explanation.get('phase1_section')
            if isinstance(nested, str) and nested.strip():
                return nested.strip().lower()
        return ''

    @staticmethod
    def _extract_workflow_phase(question: Any) -> str:
        if not isinstance(question, dict):
            return ''
        workflow_phase = question.get('workflow_phase')
        if isinstance(workflow_phase, str) and workflow_phase.strip():
            return workflow_phase.strip().lower()
        explanation = question.get('ranking_explanation')
        if isinstance(explanation, dict):
            nested = explanation.get('workflow_phase')
            if isinstance(nested, str) and nested.strip():
                return nested.strip().lower()
            nested_phase1 = explanation.get('phase1_section')
            if isinstance(nested_phase1, str) and nested_phase1.strip():
                return nested_phase1.strip().lower()
        return ''

    @staticmethod
    def _phase_focus_rank_for_candidate(question: Any) -> int:
        workflow_phase = AdversarialSession._extract_workflow_phase(question)
        if workflow_phase:
            return {
                'graph_analysis': 0,
                'document_generation': 1,
                'intake_questioning': 2,
            }.get(workflow_phase, 3)
        phase1_section = AdversarialSession._extract_phase1_section(question)
        return {
            'graph_analysis': 0,
            'document_generation': 1,
            'intake_questioning': 2,
            # Compatibility with denoiser section labels.
            'contradictions': 0,
            'chronology': 0,
            'actors': 0,
            'claim_elements': 0,
            'proof_leads': 0,
            'harm_remedy': 1,
            'general': 2,
        }.get(phase1_section, 3)

    @staticmethod
    def _is_exact_dates_question(question: Any) -> bool:
        text = AdversarialSession._extract_question_text(question).lower()
        if AdversarialSession._is_timeline_question(question):
            return True
        date_tokens = (
            'exact date',
            'specific date',
            'what date',
            'on what date',
            'date did',
            'date was',
            'month and year',
            'mm/dd',
            'date anchor',
        )
        return any(token in text for token in date_tokens)

    @staticmethod
    def _is_staff_names_titles_question(question: Any) -> bool:
        if AdversarialSession._extract_question_objective(question) == 'staff_names_titles':
            return True
        signals = AdversarialSession._extract_selector_signals(question)
        matches = signals.get('intake_priority_match')
        if isinstance(matches, list) and 'staff_names_titles' in matches:
            return True
        text = AdversarialSession._extract_question_text(question).lower()
        if not any(
            token in text
            for token in (
                'who',
                'name',
                'names',
                'staff',
                'person',
                'manager',
                'supervisor',
                'decision',
                'decision-maker',
                'decision maker',
                'sender',
                'signer',
                'author',
            )
        ):
            return False
        title_tokens = (
            'title',
            'titles',
            'job title',
            'job titles',
            'role',
            'roles',
            'position',
            'positions',
            'decision-maker information',
            'decision maker information',
        )
        return any(token in text for token in title_tokens)

    @staticmethod
    def _seed_supports_reasonable_accommodation(seed_complaint: Dict[str, Any]) -> bool:
        key_facts = seed_complaint.get('key_facts') if isinstance(seed_complaint.get('key_facts'), dict) else {}
        anchor_sections = {
            str(value or '').strip().lower()
            for value in list(key_facts.get('anchor_sections') or [])
            if str(value or '').strip()
        }
        theory_labels = {
            str(value or '').strip().lower()
            for value in list(key_facts.get('theory_labels') or [])
            if str(value or '').strip()
        }
        protected_bases = {
            str(value or '').strip().lower()
            for value in list(key_facts.get('protected_bases') or [])
            if str(value or '').strip()
        }
        if 'reasonable_accommodation' in anchor_sections or 'reasonable_accommodation' in theory_labels:
            return True
        if 'disability_discrimination' in theory_labels or 'disability' in protected_bases:
            return True
        return False

    @staticmethod
    def _seed_supports_selection_criteria(seed_complaint: Dict[str, Any]) -> bool:
        key_facts = seed_complaint.get('key_facts') if isinstance(seed_complaint.get('key_facts'), dict) else {}
        anchor_sections = {
            str(value or '').strip().lower()
            for value in list(key_facts.get('anchor_sections') or [])
            if str(value or '').strip()
        }
        theory_labels = {
            str(value or '').strip().lower()
            for value in list(key_facts.get('theory_labels') or [])
            if str(value or '').strip()
        }
        anchor_terms = {
            str(value or '').strip().lower()
            for value in list(key_facts.get('anchor_terms') or [])
            if str(value or '').strip()
        }
        if 'selection_criteria' in anchor_sections or 'selection_criteria' in theory_labels:
            return True
        return any(
            token in term
            for term in anchor_terms
            for token in ('selection', 'screening', 'criteria', 'evaluation', 'priority', 'threshold')
        )

    @staticmethod
    def _is_hearing_request_timing_question(question: Any) -> bool:
        text = AdversarialSession._extract_question_text(question).lower()
        hearing_tokens = ('hearing', 'grievance', 'appeal', 'review')
        timing_tokens = ('when', 'date', 'timing', 'timeline', 'after', 'before', 'deadline', 'requested')
        return any(token in text for token in hearing_tokens) and any(token in text for token in timing_tokens)

    @staticmethod
    def _is_response_dates_question(question: Any) -> bool:
        text = AdversarialSession._extract_question_text(question).lower()
        response_tokens = ('respond', 'response', 'notice', 'decision', 'outcome', 'reply', 'letter')
        date_tokens = ('when', 'date', 'dated', 'timeline', 'how long', 'days later')
        return any(token in text for token in response_tokens) and any(token in text for token in date_tokens)

    @staticmethod
    def _is_adverse_action_detail_question(question: Any) -> bool:
        text = AdversarialSession._extract_question_text(question).lower()
        adverse_tokens = (
            'adverse action',
            'denial',
            'terminate',
            'termination',
            'evict',
            'suspend',
            'nonrenew',
            'notice',
            'decision',
            'outcome',
        )
        detail_tokens = (
            'exactly',
            'specific',
            'what happened',
            'what was said',
            'what was done',
            'reason given',
            'stated reason',
            'basis',
            'details',
            'content',
        )
        return any(token in text for token in adverse_tokens) and any(token in text for token in detail_tokens)

    @staticmethod
    def _is_causation_sequence_question(question: Any) -> bool:
        text = AdversarialSession._extract_question_text(question).lower()
        if AdversarialSession._is_protected_activity_causation_question(question):
            return True
        protected_activity_tokens = ('protected activity', 'complaint', 'reported', 'accommodation', 'grievance', 'appeal')
        adverse_tokens = ('adverse', 'retaliat', 'denial', 'termination', 'disciplin')
        sequencing_tokens = ('before', 'after', 'sequence', 'timeline', 'what happened first', 'step by step')
        return (
            any(token in text for token in protected_activity_tokens)
            and any(token in text for token in adverse_tokens)
            and any(token in text for token in sequencing_tokens)
        )

    @staticmethod
    def _coverage_gap_rank(
        question: Any,
        need_timeline: bool,
        need_harm_remedy: bool,
        need_actor_decisionmaker: bool,
        need_adverse_action_details: bool,
        need_causation: bool,
        need_documentary_evidence: bool,
        need_witness: bool,
        need_exact_dates: bool = False,
        need_staff_names_titles: bool = False,
        need_hearing_request_timing: bool = False,
        need_response_dates: bool = False,
        need_causation_sequence: bool = False,
        missing_anchor_sections: Set[str] | None = None,
    ) -> int:
        question_text = AdversarialSession._extract_question_text(question)
        if AdversarialSession._is_contradiction_resolution_question(question):
            return -2
        if need_exact_dates and AdversarialSession._is_exact_dates_question(question):
            return 0
        if need_adverse_action_details and AdversarialSession._is_adverse_action_detail_question(question):
            return 1
        if need_staff_names_titles and AdversarialSession._is_staff_names_titles_question(question):
            return 2
        if need_hearing_request_timing and AdversarialSession._is_hearing_request_timing_question(question):
            return 3
        if need_response_dates and AdversarialSession._is_response_dates_question(question):
            return 4
        if need_causation_sequence and AdversarialSession._is_causation_sequence_question(question):
            return 5
        if missing_anchor_sections and AdversarialSession._question_targets_missing_anchor_section(
            question_text,
            missing_anchor_sections,
        ):
            return 6
        if need_harm_remedy and AdversarialSession._is_harm_or_remedy_question(question):
            return 7
        if need_timeline and AdversarialSession._is_timeline_question(question):
            return 8
        if need_actor_decisionmaker and AdversarialSession._is_actor_or_decisionmaker_question(question):
            return 9
        if need_causation and AdversarialSession._is_protected_activity_causation_question(question):
            return 10
        if need_documentary_evidence and AdversarialSession._is_documentary_evidence_question(question):
            return 11
        if need_witness and AdversarialSession._is_witness_question(question):
            return 12
        return 13

    @staticmethod
    def _extract_actor_critic_score(question: Any) -> float:
        if not isinstance(question, dict):
            return 0.0
        direct = question.get('actor_critic_score')
        if isinstance(direct, (int, float)):
            return float(direct)
        explanation = question.get('ranking_explanation')
        if isinstance(explanation, dict):
            nested = explanation.get('actor_critic_score')
            if isinstance(nested, (int, float)):
                return float(nested)
        return 0.0

    @staticmethod
    def _extract_selector_score(question: Any) -> float:
        if not isinstance(question, dict):
            return 0.0
        direct = question.get('selector_score')
        if isinstance(direct, (int, float)):
            return float(direct)
        explanation = question.get('ranking_explanation')
        if isinstance(explanation, dict):
            nested = explanation.get('selector_score')
            if isinstance(nested, (int, float)):
                return float(nested)
        return 0.0

    @staticmethod
    def _extract_selector_signals(question: Any) -> Dict[str, Any]:
        if not isinstance(question, dict):
            return {}
        direct = question.get('selector_signals')
        if isinstance(direct, dict):
            return dict(direct)
        explanation = question.get('ranking_explanation')
        if isinstance(explanation, dict):
            nested = explanation.get('selector_signals')
            if isinstance(nested, dict):
                return dict(nested)
        return {}

    @classmethod
    def _extract_blocker_closure_match_count(cls, question: Any) -> int:
        signals = cls._extract_selector_signals(question)
        direct = signals.get('blocker_closure_match_count')
        if isinstance(direct, (int, float)):
            return int(direct)
        fallback = signals.get('blocker_match_count')
        if isinstance(fallback, (int, float)):
            return int(fallback)
        return 0

    @staticmethod
    def _normalized_actor_critic_score(question: Any) -> float:
        raw = AdversarialSession._extract_actor_critic_score(question)
        # Candidate actor/critic scores can be unbounded depending on router internals.
        # Clamp to a stable window before normalizing so ranking remains predictable.
        bounded = max(-3.0, min(6.0, float(raw)))
        return (bounded + 3.0) / 9.0

    @staticmethod
    def _normalized_selector_score(question: Any) -> float:
        raw = AdversarialSession._extract_selector_score(question)
        # Selector scores are usually positive, but may drift by router/model version.
        return max(0.0, min(1.0, float(raw) / 100.0))

    @staticmethod
    def _phase_focus_weight(phase_focus_rank: int) -> float:
        # Preserve phase ordering while keeping lower-priority phases selectable.
        if phase_focus_rank <= 0:
            return 1.0
        if phase_focus_rank == 1:
            return 0.9
        if phase_focus_rank == 2:
            return 0.72
        return 0.4

    @staticmethod
    def _question_specificity_score(question_text: str) -> float:
        normalized = AdversarialSession._question_dedupe_key(question_text)
        if not normalized:
            return 0.0
        tokens = normalized.split()
        token_count = len(tokens)
        has_interrogative = bool(
            tokens
            and tokens[0]
            in {
                'who',
                'what',
                'when',
                'where',
                'why',
                'how',
                'which',
                'did',
                'does',
                'do',
                'is',
                'are',
                'can',
                'could',
                'would',
            }
        )
        legal_context_tokens = {
            'date',
            'timeline',
            'notice',
            'decision',
            'hearing',
            'appeal',
            'grievance',
            'adverse',
            'accommodation',
            'protected',
            'document',
            'email',
            'message',
            'witness',
            'harm',
            'remedy',
            'staff',
            'title',
        }
        legal_context_hits = sum(1 for token in tokens if token in legal_context_tokens)
        score = 0.0
        if has_interrogative:
            score += 0.35
        score += min(0.45, token_count / 20.0)
        score += min(0.20, legal_context_hits * 0.05)
        return max(0.0, min(1.0, score))

    @staticmethod
    def _question_precision_score(question_text: str) -> float:
        lowered = " ".join(question_text.lower().split())
        if not lowered:
            return 0.0

        chronology_hits = sum(
            1
            for token in (
                'exact date',
                'specific date',
                'month and year',
                'days later',
                'before',
                'after',
                'sequence',
                'timeline',
                'what happened first',
            )
            if token in lowered
        )
        decision_hits = sum(
            1
            for token in (
                'name',
                'title',
                'role',
                'decision-maker',
                'decision maker',
                'who made',
                'who decided',
                'who communicated',
            )
            if token in lowered
        )
        adverse_hits = sum(
            1
            for token in (
                'adverse action',
                'denial',
                'termination',
                'eviction',
                'suspension',
                'notice',
                'reason given',
                'what exactly',
            )
            if token in lowered
        )
        document_hits = sum(
            1
            for token in (
                'document',
                'email',
                'text message',
                'notice',
                'letter',
                'record',
                'screenshot',
                'attachment',
                'receipt',
                'invoice',
                'policy',
            )
            if token in lowered
        )
        extraction_hits = sum(
            1
            for token in (
                'for each',
                'identify',
                'list',
                'exact',
                'specific',
                'date and time',
                'name and title',
                'which document',
            )
            if token in lowered
        )
        score = 0.0
        score += min(0.30, chronology_hits * 0.08)
        score += min(0.22, decision_hits * 0.07)
        score += min(0.20, adverse_hits * 0.06)
        score += min(0.16, document_hits * 0.04)
        score += min(0.12, extraction_hits * 0.05)
        return max(0.0, min(1.0, score))

    @classmethod
    def _router_backed_quality_signal(cls, question: Any) -> float:
        if not isinstance(question, dict):
            return 0.0
        signals = cls._extract_selector_signals(question)
        candidate_source = str(signals.get('candidate_source') or '').strip().lower()
        source_bonus = 0.0
        if candidate_source:
            source_bonus = 0.4
            if any(token in candidate_source for token in ('dependency_graph', 'router', 'matcher', 'knowledge_graph')):
                source_bonus = 0.6
        blocker_matches = min(1.0, float(cls._extract_blocker_closure_match_count(question)) / 2.0)
        selector_score = cls._normalized_selector_score(question)
        actor_critic = cls._normalized_actor_critic_score(question)
        return max(0.0, min(1.0, source_bonus * 0.35 + blocker_matches * 0.30 + selector_score * 0.20 + actor_critic * 0.15))

    @classmethod
    def _question_quality_score(cls, question: Any, question_text: str) -> float:
        specificity = cls._question_specificity_score(question_text)
        precision = cls._question_precision_score(question_text)
        actor_critic = cls._normalized_actor_critic_score(question)
        selector_score = cls._normalized_selector_score(question)
        blocker_matches = min(1.0, float(cls._extract_blocker_closure_match_count(question)) / 2.0)
        phase_weight = cls._phase_focus_weight(cls._phase_focus_rank_for_candidate(question))
        router_backed = cls._router_backed_quality_signal(question)
        # Weighted blend that favors concrete, extraction-ready prompts while still
        # respecting actor/critic feedback and router phase focus.
        score = (
            specificity * 0.30
            + precision * 0.24
            + actor_critic * 0.18
            + selector_score * 0.09
            + blocker_matches * 0.10
            + phase_weight * 0.05
            + router_backed * 0.04
        )
        return max(0.0, min(1.0, score))

    @staticmethod
    def _question_targets_anchor_section(question_text: str, section: str) -> bool:
        text = question_text.lower()
        section_terms = {
            'grievance_hearing': ('grievance', 'hearing', 'impartial', 'informal hearing'),
            'appeal_rights': ('appeal', 'review', 'due process', 'rights'),
            'reasonable_accommodation': ('reasonable accommodation', 'accommodation', 'disability'),
            'adverse_action': ('termination', 'denial', 'adverse', 'admission', 'occupancy'),
            'selection_criteria': ('selection', 'screening', 'criteria', 'evaluation', 'priority'),
        }
        return any(term in text for term in section_terms.get(section, (section.replace('_', ' '),)))

    @classmethod
    def _question_targets_missing_anchor_section(
        cls,
        question_text: str,
        missing_anchor_sections: Set[str],
    ) -> bool:
        return any(cls._question_targets_anchor_section(question_text, section) for section in missing_anchor_sections)

    @staticmethod
    def _anchor_probe_map() -> Dict[str, tuple[str, str]]:
        return {
            'grievance_hearing': (
                "What grievance or informal hearing process were you told was available, whether you requested it, and who was supposed to handle it?",
                "anchor_grievance_hearing",
            ),
            'appeal_rights': (
                "Were you told you could request a grievance hearing, appeal, review, or other due-process rights, and did you try to use them?",
                "anchor_appeal_rights",
            ),
            'reasonable_accommodation': (
                "Did you request a reasonable accommodation or raise a disability-related need, and how did HACC respond?",
                "anchor_reasonable_accommodation",
            ),
            'adverse_action': (
                "What adverse action happened to you exactly, such as a denial, termination, or other loss of housing benefits?",
                "anchor_adverse_action",
            ),
            'selection_criteria': (
                "What screening, selection, or evaluation criteria were you told were being used in your case?",
                "anchor_selection_criteria",
            ),
        }

    @classmethod
    def _question_objectives_from_prompt(cls, question_text: str) -> List[str]:
        lowered = question_text.lower()
        objectives: List[str] = []
        if any(token in lowered for token in ('exact date', 'specific date', 'what date', 'date anchor', 'month and year')):
            objectives.append('exact_dates')
        if (
            any(token in lowered for token in ('staff', 'name', 'who', 'person', 'manager', 'supervisor', 'decision-maker', 'decision maker'))
            and any(token in lowered for token in ('title', 'titles', 'role', 'roles', 'position', 'positions', 'job title', 'job titles'))
        ):
            objectives.append('staff_names_titles')
        if (
            any(token in lowered for token in ('hearing', 'grievance', 'appeal', 'review'))
            and any(token in lowered for token in ('when', 'date', 'timing', 'requested', 'deadline'))
        ):
            objectives.append('hearing_request_timing')
        if (
            any(token in lowered for token in ('response', 'respond', 'notice', 'decision', 'outcome'))
            and any(token in lowered for token in ('when', 'date', 'dated', 'days later', 'timeline'))
        ):
            objectives.append('response_dates')
        if any(token in lowered for token in ('when', 'date', 'timeline', 'chronology', 'sequence', 'decision timeline')):
            objectives.append('timeline')
        if cls._is_adverse_action_detail_question({'question': question_text}):
            objectives.append('adverse_action_details')
        if any(token in lowered for token in ('harm', 'remedy', 'loss', 'relief')):
            objectives.append('harm_remedy')
        if any(token in lowered for token in ('who', 'which person', 'made', 'communicated', 'carried out', 'decision-maker', 'decision maker')):
            objectives.append('actors')
        if (
            any(token in lowered for token in ('protected activity', 'complaint', 'reported', 'accommodation', 'grievance', 'appeal'))
            and any(token in lowered for token in ('adverse', 'retaliat', 'denial', 'termination'))
            and any(token in lowered for token in ('because', 'after', 'caus', 'reason', 'link'))
        ):
            objectives.append('causation')
        if (
            any(token in lowered for token in ('protected activity', 'complaint', 'reported', 'accommodation', 'grievance', 'appeal'))
            and any(token in lowered for token in ('adverse', 'retaliat', 'denial', 'termination'))
            and any(token in lowered for token in ('before', 'after', 'sequence', 'timeline', 'what happened first'))
        ):
            objectives.append('causation_sequence')
        if any(token in lowered for token in ('email', 'emails', 'document', 'documents', 'notice', 'records', 'messages', 'written')):
            objectives.append('documents')
        if any(token in lowered for token in ('witness', 'witnesses', 'saw or heard')):
            objectives.append('witnesses')

        for section, (_, objective) in cls._anchor_probe_map().items():
            if cls._question_targets_anchor_section(question_text, section):
                objectives.append(objective)

        if not objectives:
            objectives.append('intake_follow_up')

        deduped: List[str] = []
        seen = set()
        for objective in objectives:
            if objective not in seen:
                seen.add(objective)
                deduped.append(objective)
        return deduped

    @staticmethod
    def _extract_anchor_sections(seed_complaint: Dict[str, Any]) -> Set[str]:
        key_facts = seed_complaint.get('key_facts') if isinstance(seed_complaint.get('key_facts'), dict) else {}
        return {
            str(value) for value in list(key_facts.get('anchor_sections') or []) if str(value)
        }

    @classmethod
    def _extract_required_blocker_objectives(cls, seed_complaint: Dict[str, Any]) -> Set[str]:
        key_facts = seed_complaint.get('key_facts') if isinstance(seed_complaint.get('key_facts'), dict) else {}
        synthetic_prompts = key_facts.get('synthetic_prompts') if isinstance(key_facts, dict) else {}
        blocker_objectives = {
            'exact_dates',
            'staff_names_titles',
            'hearing_request_timing',
            'response_dates',
            'causation_sequence',
            'adverse_action_details',
        }
        extraction_target_objectives = {
            'timeline_anchors': 'exact_dates',
            'actor_role_mapping': 'staff_names_titles',
            'hearing_process': 'hearing_request_timing',
            'response_timeline': 'response_dates',
            'retaliation_sequence': 'causation_sequence',
            'adverse_action_details': 'adverse_action_details',
        }
        required: Set[str] = set()
        for payload in (key_facts, synthetic_prompts if isinstance(synthetic_prompts, dict) else {}):
            if not isinstance(payload, dict):
                continue
            for value in list(payload.get('blocker_objectives') or []):
                objective = str(value or '').strip().lower()
                if objective in blocker_objectives:
                    required.add(objective)
            for value in list(payload.get('extraction_targets') or []):
                mapped_objective = extraction_target_objectives.get(str(value or '').strip().lower())
                if mapped_objective:
                    required.add(mapped_objective)
        for _, objective in cls._extract_intake_prompt_candidates(seed_complaint):
            if objective in blocker_objectives:
                required.add(objective)
        return required

    @classmethod
    def _covered_anchor_sections_from_questions(
        cls,
        question_keys: Sequence[str],
        expected_anchor_sections: Set[str],
    ) -> Set[str]:
        covered: Set[str] = set()
        for key in question_keys:
            for section in expected_anchor_sections:
                if cls._question_targets_anchor_section(key, section):
                    covered.add(section)
        return covered

    @staticmethod
    def _extract_intake_prompt_candidates(seed_complaint: Dict[str, Any]) -> List[tuple[str, str]]:
        key_facts = seed_complaint.get('key_facts') if isinstance(seed_complaint.get('key_facts'), dict) else {}
        synthetic_prompts = key_facts.get('synthetic_prompts') if isinstance(key_facts, dict) else {}
        candidates: List[tuple[str, str]] = []
        if isinstance(synthetic_prompts, dict):
            explicit_question_lists = (
                synthetic_prompts.get('intake_questions') or [],
                synthetic_prompts.get('evidence_upload_questions') or [],
                synthetic_prompts.get('mediator_questions') or [],
                synthetic_prompts.get('document_generation_questions') or [],
            )
            for raw_question in [item for values in explicit_question_lists for item in list(values or [])]:
                question_text = str(raw_question or '').strip()
                if not question_text:
                    continue
                for objective in AdversarialSession._question_objectives_from_prompt(question_text):
                    candidates.append((question_text, objective))

            for raw_prompt in (
                synthetic_prompts.get('intake_questionnaire_prompt'),
                synthetic_prompts.get('complaint_chatbot_prompt'),
                synthetic_prompts.get('evidence_upload_prompt'),
                synthetic_prompts.get('mediator_evidence_review_prompt'),
                synthetic_prompts.get('mediator_evaluation_prompt'),
                synthetic_prompts.get('document_generation_prompt'),
            ):
                prompt_text = " ".join(str(raw_prompt or '').split()).strip()
                if not prompt_text or "?" not in prompt_text:
                    continue
                for fragment in re.split(r"(?<=[?])\s+", prompt_text):
                    question_text = fragment.strip()
                    if not question_text.endswith("?"):
                        continue
                    for objective in AdversarialSession._question_objectives_from_prompt(question_text):
                        candidates.append((question_text, objective))

        candidates.extend(AdversarialSession._claim_temporal_gap_prompts(seed_complaint))
        if AdversarialSession._extract_latest_batch_priority_flags(seed_complaint).get('needs_exhibit_grounding'):
            exhibit_ready_prompt = AdversarialSession._synthesize_exhibit_ready_intake_prompt(seed_complaint)
            if exhibit_ready_prompt:
                candidates.append((exhibit_ready_prompt, 'documents'))

        expected_anchor_sections = [
            str(value) for value in list(key_facts.get('anchor_sections') or []) if str(value)
        ]
        supports_reasonable_accommodation = AdversarialSession._seed_supports_reasonable_accommodation(seed_complaint)
        if not supports_reasonable_accommodation:
            candidates = [
                item for item in candidates
                if item[1] != 'anchor_reasonable_accommodation'
            ]
        covered_anchor_objectives = {objective for _, objective in candidates if objective.startswith('anchor_')}
        for section in expected_anchor_sections:
            probe = AdversarialSession._anchor_probe_map().get(section)
            if not probe:
                continue
            probe_text, probe_type = probe
            if probe_type not in covered_anchor_objectives:
                candidates.append((probe_text, probe_type))

        if not candidates:
            return []

        priority = {
            'exact_dates': 0,
            'staff_names_titles': 1,
            'hearing_request_timing': 2,
            'response_dates': 3,
            'adverse_action_details': 4,
            'anchor_adverse_action': 0,
            'anchor_grievance_hearing': 1,
            'anchor_appeal_rights': 2,
            'anchor_reasonable_accommodation': 3,
            'anchor_selection_criteria': 4,
            'timeline': 6,
            'actors': 7,
            'causation': 8,
            'causation_sequence': 9,
            'documents': 10,
            'witnesses': 11,
            'harm_remedy': 12,
            'intake_follow_up': 13,
        }
        candidates.sort(key=lambda item: (priority.get(item[1], 99), item[0].lower(), item[1]))
        deduped: List[tuple[str, str]] = []
        seen = set()
        for item in candidates:
            key = (item[0].strip().lower(), item[1])
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        return deduped

    @staticmethod
    def _synthesize_exhibit_ready_intake_prompt(seed_complaint: Dict[str, Any]) -> str:
        chronology_hints = AdversarialSession._extract_document_chronology_priority_hints(seed_complaint)
        key_facts = seed_complaint.get('key_facts') if isinstance(seed_complaint.get('key_facts'), dict) else {}
        anchor_sections = {
            str(value or '').strip().lower()
            for value in list(key_facts.get('anchor_sections') or [])
            if str(value or '').strip()
        }
        if bool(chronology_hints.get('needs_decision_document_precision')) or 'adverse_action' in anchor_sections:
            return (
                "Which uploaded or uploadable documents should be treated as exhibits for each notice, denial, "
                "hearing request, or review decision, and for each one what are the date, sender or source, "
                "label or subject line, and the fact the document proves?"
            )
        if bool(chronology_hints.get('needs_chronology_closure')):
            return (
                "Which uploaded or uploadable documents should be treated as exhibits for each key event in the timeline, "
                "and for each one what are the date, sender or source, label or subject line, and the fact the document proves?"
            )
        return (
            "Which uploaded or uploadable documents should be treated as exhibits, and for each one what are the date, "
            "sender or source, label or subject line, and the fact the document proves?"
        )

    @staticmethod
    def _seed_requires_causation_probe(seed_complaint: Dict[str, Any]) -> bool:
        key_facts = seed_complaint.get('key_facts') if isinstance(seed_complaint.get('key_facts'), dict) else {}
        seed_text = " ".join(
            [
                str(seed_complaint.get('summary') or ''),
                str(key_facts.get('incident_summary') or ''),
                " ".join(str(item or '') for item in list(key_facts.get('complainant_story_facts') or [])),
                " ".join(str(item or '') for item in list(key_facts.get('anchor_sections') or [])),
            ]
        ).lower()
        protected_activity_terms = (
            'protected activity',
            'complaint',
            'reported',
            'accommodation',
            'grievance',
            'appeal',
            'retaliat',
        )
        adverse_terms = (
            'adverse',
            'termination',
            'denial',
            'disciplin',
            'evict',
            'nonrenew',
            'suspension',
        )
        return any(term in seed_text for term in protected_activity_terms) and any(
            term in seed_text for term in adverse_terms
        )

    @staticmethod
    def _extract_latest_batch_priorities(seed_complaint: Dict[str, Any]) -> List[str]:
        candidate_containers = [
            seed_complaint,
            seed_complaint.get('document_optimization') if isinstance(seed_complaint, dict) else None,
            seed_complaint.get('optimization_guidance') if isinstance(seed_complaint, dict) else None,
            seed_complaint.get('actor_critic_optimizer') if isinstance(seed_complaint, dict) else None,
        ]
        latest: List[str] = []
        for payload in candidate_containers:
            if not isinstance(payload, dict):
                continue
            for value in list(payload.get('latest_batch_priorities') or []):
                text = str(value or '').strip()
                if text:
                    latest.append(text)
        deduped: List[str] = []
        seen = set()
        for item in latest:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    @classmethod
    def _extract_latest_batch_priority_flags(cls, seed_complaint: Dict[str, Any]) -> Dict[str, bool]:
        priorities = [item.lower() for item in cls._extract_latest_batch_priorities(seed_complaint)]
        chronology_markers = (
            'chronology',
            'exact date',
            'response timing',
            'sequence',
            'timeline',
        )
        decision_document_markers = (
            'decision-maker',
            'decision maker',
            'adverse action',
            'documentary artifacts',
            'document',
            'artifact',
            'precision',
        )
        chronology_priority_hints = cls._extract_document_chronology_priority_hints(seed_complaint)
        needs_chronology_closure = any(
            any(marker in item for marker in chronology_markers)
            for item in priorities
        ) or bool(chronology_priority_hints.get('needs_chronology_closure'))
        needs_decision_document_precision = any(
            any(marker in item for marker in decision_document_markers)
            for item in priorities
        ) or bool(chronology_priority_hints.get('needs_decision_document_precision'))
        needs_exhibit_grounding = any(
            'exhibit' in item or 'uploaded evidence' in item or 'uploaded document' in item
            for item in priorities
        ) or bool(chronology_priority_hints.get('needs_exhibit_grounding'))
        return {
            'needs_chronology_closure': needs_chronology_closure,
            'needs_decision_document_precision': needs_decision_document_precision,
            'needs_exhibit_grounding': needs_exhibit_grounding,
        }

    @staticmethod
    def _extract_document_chronology_priority_hints(seed_complaint: Dict[str, Any]) -> Dict[str, Any]:
        candidate_containers = [
            seed_complaint,
            seed_complaint.get('workflow_optimization_guidance') if isinstance(seed_complaint, dict) else None,
            seed_complaint.get('document_optimization') if isinstance(seed_complaint, dict) else None,
            seed_complaint.get('optimization_guidance') if isinstance(seed_complaint, dict) else None,
            seed_complaint.get('actor_critic_optimizer') if isinstance(seed_complaint, dict) else None,
        ]
        unresolved_temporal_issue_count = 0
        chronology_task_count = 0
        missing_proof_artifact_count = 0
        low_exhibit_grounding = False
        objectives: Set[str] = set()

        for payload in candidate_containers:
            if not isinstance(payload, dict):
                continue
            nested_payloads = [
                payload,
                payload.get('workflow_optimization_guidance') if isinstance(payload.get('workflow_optimization_guidance'), dict) else None,
            ]
            for nested in nested_payloads:
                if not isinstance(nested, dict):
                    continue
                temporal_handoff = nested.get('claim_support_temporal_handoff')
                if isinstance(temporal_handoff, dict):
                    unresolved_temporal_issue_count += int(temporal_handoff.get('unresolved_temporal_issue_count') or 0)
                    chronology_task_count += int(temporal_handoff.get('chronology_task_count') or 0)
                    if int(temporal_handoff.get('unresolved_temporal_issue_count') or 0) > 0 or int(temporal_handoff.get('chronology_task_count') or 0) > 0:
                        objectives.update({'timeline', 'exact_dates'})
                    claim_element_id = str(temporal_handoff.get('claim_element_id') or '').strip().lower()
                    temporal_objective_text = ' '.join(
                        str(item or '').strip().lower()
                        for item in list(temporal_handoff.get('temporal_proof_objectives') or [])
                        if str(item or '').strip()
                    )
                    if claim_element_id == 'causation' or any(
                        token in temporal_objective_text
                        for token in ('causation', 'protected activity', 'adverse action', 'retaliation', 'sequence')
                    ):
                        objectives.add('causation_sequence')
                    if any(
                        token in temporal_objective_text
                        for token in ('hearing', 'appeal', 'review', 'grievance')
                    ):
                        objectives.add('hearing_request_timing')
                    if any(
                        token in temporal_objective_text
                        for token in ('response', 'notice', 'decision')
                    ):
                        objectives.add('response_dates')

                claim_reasoning_review = nested.get('claim_reasoning_review')
                if isinstance(claim_reasoning_review, dict):
                    for review in claim_reasoning_review.values():
                        if not isinstance(review, dict):
                            continue
                        status_counts = dict(review.get('proof_artifact_status_counts') or {})
                        missing_count = int(status_counts.get('missing') or 0)
                        if missing_count <= 0:
                            total_count = int(review.get('proof_artifact_element_count') or 0)
                            available_count = int(review.get('proof_artifact_available_element_count') or 0)
                            missing_count = max(0, total_count - available_count)
                        if missing_count > 0:
                            missing_proof_artifact_count += missing_count
                            objectives.add('documents')

                document_provenance_summary = nested.get('document_provenance_summary')
                if isinstance(document_provenance_summary, dict):
                    exhibit_backed_ratio = float(document_provenance_summary.get('avg_exhibit_backed_ratio') or 0.0)
                    if exhibit_backed_ratio < 0.6:
                        low_exhibit_grounding = True
                        objectives.add('documents')

        return {
            'needs_chronology_closure': bool(unresolved_temporal_issue_count or chronology_task_count),
            'needs_decision_document_precision': bool(missing_proof_artifact_count),
            'needs_exhibit_grounding': bool(low_exhibit_grounding),
            'objectives': sorted(objectives),
            'unresolved_temporal_issue_count': unresolved_temporal_issue_count,
            'chronology_task_count': chronology_task_count,
            'missing_proof_artifact_count': missing_proof_artifact_count,
        }

    @staticmethod
    def _extract_claim_temporal_gap_summary(seed_complaint: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidate_containers = [
            seed_complaint,
            seed_complaint.get('document_optimization') if isinstance(seed_complaint, dict) else None,
            seed_complaint.get('optimization_guidance') if isinstance(seed_complaint, dict) else None,
            seed_complaint.get('actor_critic_optimizer') if isinstance(seed_complaint, dict) else None,
        ]
        rows: List[Dict[str, Any]] = []
        seen = set()
        for payload in candidate_containers:
            if not isinstance(payload, dict):
                continue
            intake_priorities = payload.get('intake_priorities') if isinstance(payload.get('intake_priorities'), dict) else {}
            claim_gap_summary = intake_priorities.get('claim_temporal_gap_summary')
            if not isinstance(claim_gap_summary, list):
                continue
            for item in claim_gap_summary:
                if not isinstance(item, dict):
                    continue
                claim_type = str(item.get('claim_type') or '').strip().lower()
                gaps = [str(gap).strip() for gap in list(item.get('gaps') or []) if str(gap).strip()]
                key = (claim_type, tuple(gaps))
                if key in seen:
                    continue
                seen.add(key)
                rows.append({'claim_type': claim_type, 'gaps': gaps})
        return rows

    @classmethod
    def _claim_temporal_gap_prompts(cls, seed_complaint: Dict[str, Any]) -> List[tuple[str, str]]:
        prompts: List[tuple[str, str]] = []
        for row in cls._extract_claim_temporal_gap_summary(seed_complaint):
            claim_type = str(row.get('claim_type') or '').strip().replace('_', ' ')
            claim_label = claim_type or 'claim'
            for gap in list(row.get('gaps') or []):
                gap_text = str(gap or '').strip()
                lowered = gap_text.lower()
                if any(token in lowered for token in ('relative ordering', 'anchor', 'anchoring', 'exact date', 'date anchor')):
                    prompts.append((
                        f"For your {claim_label} claim, what exact dates or best available date anchors do you have for each key event in sequence?",
                        'exact_dates',
                    ))
                if any(token in lowered for token in ('response', 'non-response', 'reply', 'response dates')):
                    prompts.append((
                        f"For your {claim_label} claim, when did HACC respond, fail to respond, or issue each notice or decision?",
                        'response_dates',
                    ))
                if any(token in lowered for token in ('hearing', 'appeal', 'review request', 'grievance request')):
                    prompts.append((
                        f"For your {claim_label} claim, when did you request a hearing, grievance review, or appeal, and when was that request acknowledged or denied?",
                        'hearing_request_timing',
                    ))
                if any(token in lowered for token in ('causation', 'protected activity', 'adverse action', 'sequence')):
                    prompts.append((
                        f"For your {claim_label} claim, please walk through the sequence from protected activity to adverse action, including who knew what and when.",
                        'causation_sequence',
                    ))
                if any(token in lowered for token in ('name', 'title', 'staff', 'role')):
                    prompts.append((
                        f"For your {claim_label} claim, which HACC staff handled each step, and what were their names and titles or roles?",
                        'staff_names_titles',
                    ))
        deduped: List[tuple[str, str]] = []
        seen = set()
        for item in prompts:
            key = (item[0].strip().lower(), item[1])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    @staticmethod
    def _extract_actor_critic_intake_context(seed_complaint: Dict[str, Any]) -> Dict[str, Any]:
        containers = [
            seed_complaint,
            seed_complaint.get('_meta') if isinstance(seed_complaint, dict) else None,
            seed_complaint.get('actor_critic_optimizer') if isinstance(seed_complaint, dict) else None,
            seed_complaint.get('optimization_guidance') if isinstance(seed_complaint, dict) else None,
            seed_complaint.get('document_optimization') if isinstance(seed_complaint, dict) else None,
        ]
        weak_complaint_types: Set[str] = set()
        weak_evidence_modalities: Set[str] = set()
        question_quality_signal = None
        empathy_signal = None
        efficiency_signal = None

        for payload in containers:
            if not isinstance(payload, dict):
                continue
            for key in ('weak_complaint_types', 'complaint_type_targets', 'generalization_targets'):
                for value in list(payload.get(key) or []):
                    item = str(value or '').strip().lower()
                    if item:
                        weak_complaint_types.add(item)
            for key in ('weak_evidence_modalities', 'evidence_modality_targets'):
                for value in list(payload.get(key) or []):
                    item = str(value or '').strip().lower()
                    if item:
                        weak_evidence_modalities.add(item)

            for key in ('question_quality_avg', 'question_quality'):
                value = payload.get(key)
                if isinstance(value, (int, float)):
                    question_quality_signal = float(value)
            for key in ('empathy_avg', 'empathy'):
                value = payload.get(key)
                if isinstance(value, (int, float)):
                    empathy_signal = float(value)
            for key in ('efficiency_avg', 'efficiency'):
                value = payload.get(key)
                if isinstance(value, (int, float)):
                    efficiency_signal = float(value)

            phase_signals = payload.get('phase_signal_context')
            if isinstance(phase_signals, dict):
                for key in ('question_quality_avg', 'question_quality'):
                    value = phase_signals.get(key)
                    if isinstance(value, (int, float)):
                        question_quality_signal = float(value)
                for key in ('empathy_avg', 'empathy'):
                    value = phase_signals.get(key)
                    if isinstance(value, (int, float)):
                        empathy_signal = float(value)
                for key in ('efficiency_avg', 'efficiency'):
                    value = phase_signals.get(key)
                    if isinstance(value, (int, float)):
                        efficiency_signal = float(value)

        complaint_type = str(seed_complaint.get('type') or '').strip().lower()
        source = str(
            seed_complaint.get('source')
            or (seed_complaint.get('_meta') or {}).get('seed_source')
            or ''
        ).strip().lower()
        if complaint_type:
            weak_complaint_types.add(complaint_type)
        if source:
            weak_complaint_types.add(source)

        if source == 'hacc_research_engine':
            weak_evidence_modalities.add('policy_document')
            weak_evidence_modalities.add('file_evidence')

        return {
            'weak_complaint_types': weak_complaint_types,
            'weak_evidence_modalities': weak_evidence_modalities,
            'question_quality': question_quality_signal,
            'empathy': empathy_signal,
            'efficiency': efficiency_signal,
            'is_housing_discrimination': 'housing_discrimination' in weak_complaint_types,
            'is_hacc_research_seed': 'hacc_research_engine' in weak_complaint_types,
        }

    @staticmethod
    def _intake_objective_group(objective: str) -> str:
        if objective.startswith('anchor_'):
            return 'anchor'
        if objective in {'documents', 'witnesses'}:
            return 'evidentiary'
        if objective in {
            'exact_dates',
            'staff_names_titles',
            'hearing_request_timing',
            'response_dates',
            'adverse_action_details',
            'timeline',
            'actors',
            'causation',
            'causation_sequence',
            'harm_remedy',
        }:
            return 'factual'
        return 'other'

    @classmethod
    def _intake_objective_weight(
        cls,
        objective: str,
        context: Dict[str, Any],
    ) -> float:
        weight = 1.0
        group = cls._intake_objective_group(objective)
        if group == 'anchor':
            weight += 0.35
        elif group == 'factual':
            weight += 0.25
        elif group == 'evidentiary':
            weight += 0.30

        weak_complaint_types = set(context.get('weak_complaint_types') or set())
        weak_evidence_modalities = set(context.get('weak_evidence_modalities') or set())
        if objective in {'documents', 'anchor_selection_criteria'} and weak_evidence_modalities.intersection({'policy_document', 'file_evidence'}):
            weight += 0.55
        if objective in {'adverse_action_details', 'causation_sequence', 'timeline', 'actors'} and (
            'housing_discrimination' in weak_complaint_types
            or 'hacc_research_engine' in weak_complaint_types
        ):
            weight += 0.30
        if objective.startswith('anchor_') and (
            'housing_discrimination' in weak_complaint_types
            or 'hacc_research_engine' in weak_complaint_types
        ):
            weight += 0.20
        return weight

    @staticmethod
    def _intake_objective_gap_label(objective: str) -> str:
        labels = {
            'anchor_grievance_hearing': 'the unresolved grievance hearing process',
            'anchor_selection_criteria': 'the unresolved selection criteria basis',
            'hearing_request_timing': 'the unresolved hearing-request timing',
            'adverse_action_details': 'the unresolved adverse-action fact pattern',
            'exact_dates': 'the unresolved chronology detail',
            'response_dates': 'the unresolved response-date detail',
            'staff_names_titles': 'the unresolved decision-maker identification',
            'causation_sequence': 'the unresolved causation sequence',
            'documents': 'the unresolved documentary evidence gap',
        }
        return labels.get(objective, f"the unresolved {objective.replace('_', ' ')}")

    @staticmethod
    def _strongest_evidence_anchor_for_objective(
        objective: str,
        weak_evidence_modalities: Set[str],
    ) -> str:
        weak_policy = 'policy_document' in weak_evidence_modalities
        weak_file = 'file_evidence' in weak_evidence_modalities
        if objective == 'anchor_selection_criteria':
            if weak_policy and weak_file:
                return "the written screening policy section and the exact case file or notice showing how that criterion was applied"
            if weak_policy:
                return "the written screening policy section that governed your selection outcome"
            if weak_file:
                return "the exact notice, email, or file record showing which criterion was applied to your case"
            return "the written screening criteria source and the specific case record applying that criterion"
        if objective in {'anchor_grievance_hearing', 'hearing_request_timing'}:
            return "the hearing-request record (portal/email/form/phone log) plus the response notice date"
        if objective in {'exact_dates', 'response_dates', 'causation_sequence'}:
            return "dated records such as notices, emails, texts, and uploads tied to each event"
        if objective in {'adverse_action_details', 'staff_names_titles'}:
            return "the decision notice or communication that names the actor, role, and stated reason"
        if objective == 'documents':
            if weak_policy and weak_file:
                return "a policy citation and a supporting case file with date, sender/source, and the fact proved"
            if weak_policy:
                return "a policy citation with the exact section used in your case"
            if weak_file:
                return "a supporting case file with date, sender/source, and the fact it proves"
        if weak_policy and weak_file:
            return "the strongest available policy citation and supporting case file"
        if weak_policy:
            return "the strongest available policy citation"
        if weak_file:
            return "the strongest available supporting case file"
        return "the strongest available documentary record"

    @staticmethod
    def _question_mentions_evidence_anchor(question_text: str, objective: str) -> bool:
        text = " ".join((question_text or '').lower().split())
        if not text:
            return False
        objective_terms = {
            'anchor_grievance_hearing': ('hearing', 'grievance', 'request', 'response', 'notice', 'portal', 'email', 'form'),
            'anchor_selection_criteria': ('selection', 'screening', 'criteria', 'threshold', 'policy', 'section', 'file', 'document', 'notice'),
            'hearing_request_timing': ('hearing', 'request', 'date', 'respond', 'notice', 'portal', 'email', 'form'),
            'exact_dates': ('date', 'dated', 'timeline', 'before', 'after', 'sequence'),
            'response_dates': ('response', 'date', 'notice', 'email', 'letter'),
            'staff_names_titles': ('name', 'title', 'role', 'who'),
            'causation_sequence': ('before', 'after', 'sequence', 'because', 'caus'),
            'adverse_action_details': ('adverse action', 'reason', 'decision', 'notice', 'communicated'),
            'documents': ('document', 'file', 'policy', 'email', 'text', 'letter', 'screenshot', 'upload', 'record'),
        }
        terms = objective_terms.get(objective, ())
        if any(term in text for term in terms):
            return True
        generic_terms = ('document', 'file', 'policy', 'notice', 'email', 'text', 'record', 'upload', 'screenshot')
        return any(term in text for term in generic_terms)

    @classmethod
    def _tighten_intake_question_text(
        cls,
        question_text: str,
        objective: str,
        evidence_anchor: str,
    ) -> str:
        text = str(question_text or '').strip()
        if not text:
            return text
        tightened = text
        normalized = " ".join(text.lower().split())
        gap_hint = cls._intake_objective_gap_label(objective)
        if objective and objective.replace('_', ' ') not in normalized:
            tightened = f"For {gap_hint}, {tightened}"
        if tightened and tightened[-1] not in {'?', '.', '!'}:
            tightened += "?"
        if evidence_anchor and not cls._question_mentions_evidence_anchor(tightened, objective):
            tightened += f" Please anchor your answer to {evidence_anchor}."
        return tightened

    @classmethod
    def _tighten_intake_candidate_for_objective(
        cls,
        candidate: Any,
        objective: str,
        evidence_anchor: str,
    ) -> Any:
        question_text = cls._extract_question_text(candidate)
        tightened_text = cls._tighten_intake_question_text(question_text, objective, evidence_anchor)
        if tightened_text == question_text:
            return candidate
        if isinstance(candidate, dict):
            updated = dict(candidate)
            if isinstance(updated.get('question'), str):
                updated['question'] = tightened_text
            elif isinstance(updated.get('text'), str):
                updated['text'] = tightened_text
            elif isinstance(updated.get('prompt'), str):
                updated['prompt'] = tightened_text
            elif isinstance(updated.get('content'), str):
                updated['content'] = tightened_text
            else:
                updated['question'] = tightened_text
            selector_signals = dict(updated.get('selector_signals', {}) if isinstance(updated.get('selector_signals'), dict) else {})
            selector_signals['tightened_intake_objective'] = objective
            selector_signals['tightened_evidence_anchor'] = evidence_anchor
            updated['selector_signals'] = selector_signals
            explanation = dict(updated.get('ranking_explanation', {}) if isinstance(updated.get('ranking_explanation'), dict) else {})
            explanation['tightened_intake_objective'] = objective
            explanation['tightened_evidence_anchor'] = evidence_anchor
            updated['ranking_explanation'] = explanation
            return updated
        return tightened_text

    @classmethod
    def _questions_substantially_overlap(cls, question_a: Any, question_b: Any) -> bool:
        text_a = cls._extract_question_text(question_a)
        text_b = cls._extract_question_text(question_b)
        if not text_a or not text_b:
            return False
        key_a = cls._question_dedupe_key(text_a)
        key_b = cls._question_dedupe_key(text_b)
        if key_a and key_a == key_b:
            return True
        intent_a = cls._question_intent_key(text_a, question_a)
        intent_b = cls._question_intent_key(text_b, question_b)
        similarity = cls._question_similarity(text_a, text_b)
        if intent_a and intent_b and intent_a == intent_b and similarity >= 0.35:
            return True
        if cls._is_timeline_question(question_a) and cls._is_timeline_question(question_b) and similarity >= 0.35:
            return True
        return similarity >= 0.72

    @classmethod
    def _inject_intake_prompt_questions(
        cls,
        seed_complaint: Dict[str, Any],
        questions: Sequence[Any],
    ) -> List[Any]:
        return session_intake._inject_intake_prompt_questions(
            cls,
            seed_complaint,
            questions,
        )

    @classmethod
    def _candidate_matches_intake_objective(cls, candidate: Any, objective: str) -> bool:
        question_text = cls._extract_question_text(candidate)
        if not question_text:
            return False
        if objective == 'exact_dates':
            return cls._is_exact_dates_question(candidate)
        if objective == 'staff_names_titles':
            return cls._is_staff_names_titles_question(candidate)
        if objective == 'hearing_request_timing':
            return cls._is_hearing_request_timing_question(candidate)
        if objective == 'response_dates':
            return cls._is_response_dates_question(candidate)
        if objective == 'adverse_action_details':
            return cls._is_adverse_action_detail_question(candidate)
        if objective == 'timeline':
            return cls._is_timeline_question(candidate)
        if objective == 'actors':
            return cls._is_actor_or_decisionmaker_question(candidate)
        if objective == 'causation':
            return cls._is_protected_activity_causation_question(candidate)
        if objective == 'causation_sequence':
            return cls._is_causation_sequence_question(candidate)
        if objective == 'harm_remedy':
            return cls._is_harm_or_remedy_question(candidate)
        if objective == 'documents':
            return cls._is_documentary_evidence_question(candidate)
        if objective == 'witnesses':
            return cls._is_witness_question(candidate)
        if objective.startswith('anchor_'):
            return cls._question_targets_anchor_section(question_text, objective.replace('anchor_', '', 1))
        return False

    @classmethod
    def _reprioritize_candidates_for_intake_objectives(
        cls,
        candidates: Sequence[Any],
        seed_complaint: Dict[str, Any],
        *,
        max_questions: int,
    ) -> List[Any]:
        return session_intake._reprioritize_candidates_for_intake_objectives(
            cls,
            candidates,
            seed_complaint,
            max_questions=max_questions,
        )

    @classmethod
    def _summarize_intake_priority_coverage(
        cls,
        questions: Sequence[Any],
        seed_complaint: Dict[str, Any],
    ) -> Dict[str, Any]:
        return session_intake._summarize_intake_priority_coverage(
            cls,
            questions,
            seed_complaint,
        )

    def _persist_intake_priority_summary(
        self,
        seed_complaint: Dict[str, Any],
        initial_questions: Sequence[Any],
    ) -> None:
        phase_manager = getattr(self.mediator, "phase_manager", None)
        update_phase_data = getattr(phase_manager, "update_phase_data", None)
        if not callable(update_phase_data):
            return
        try:
            from complaint_phases import ComplaintPhase
        except Exception:
            return

        summary = self._summarize_intake_priority_coverage(initial_questions, seed_complaint)
        try:
            update_phase_data(ComplaintPhase.INTAKE, "current_questions", list(initial_questions or []))
            update_phase_data(ComplaintPhase.INTAKE, "adversarial_intake_priority_summary", summary)
        except Exception:
            logger.debug("Could not persist intake-priority summary into mediator phase state", exc_info=True)

    @contextmanager
    def _temporarily_prioritize_mediator_intake_objectives(self, seed_complaint: Dict[str, Any]):
        original_selector = getattr(self.mediator, 'select_intake_question_candidates', None)
        if not callable(original_selector):
            yield
            return

        def selector_with_intake_priority(candidates: List[Dict[str, Any]], *, max_questions: int = 10):
            try:
                selected = original_selector(candidates, max_questions=len(candidates or []))
            except TypeError:
                selected = original_selector(candidates)
            if not isinstance(selected, list):
                selected = list(candidates or [])
            return self._reprioritize_candidates_for_intake_objectives(
                selected,
                seed_complaint,
                max_questions=max_questions,
            )

        setattr(self.mediator, 'select_intake_question_candidates', selector_with_intake_priority)
        try:
            yield
        finally:
            setattr(self.mediator, 'select_intake_question_candidates', original_selector)

    def _build_fallback_probe(
        self,
        seed_complaint: Dict[str, Any] | None = None,
        asked_question_counts: Dict[str, int] | None = None,
        asked_intent_counts: Dict[str, int] | None = None,
        need_timeline: bool = False,
        need_harm_remedy: bool = False,
        need_actor_decisionmaker: bool = False,
        need_causation: bool = False,
        need_documentary_evidence: bool = False,
        need_witness: bool = False,
        need_exact_dates: bool = False,
        need_staff_names_titles: bool = False,
        need_hearing_request_timing: bool = False,
        need_response_dates: bool = False,
        need_causation_sequence: bool = False,
        last_question_key: str | None = None,
        last_question_intent_key: str | None = None,
        recent_intent_keys: Set[str] | None = None,
        missing_anchor_sections: Set[str] | None = None,
    ) -> Dict[str, Any] | None:
        return session_document_fallback._build_fallback_probe(
            self,
            seed_complaint,
            asked_question_counts,
            asked_intent_counts,
            need_timeline,
            need_harm_remedy,
            need_actor_decisionmaker,
            need_causation,
            need_documentary_evidence,
            need_witness,
            need_exact_dates,
            need_staff_names_titles,
            need_hearing_request_timing,
            need_response_dates,
            need_causation_sequence,
            last_question_key,
            last_question_intent_key,
            recent_intent_keys,
            missing_anchor_sections,
        )

    @staticmethod
    def _has_empathy_prefix(question_text: str) -> bool:
        text = question_text.lower()
        empathy_markers = (
            "i understand",
            "i'm sorry",
            "i am sorry",
            "i know this is",
            "that sounds",
            "i appreciate",
            "thank you for sharing",
        )
        return any(marker in text for marker in empathy_markers)

    @staticmethod
    def _with_empathy_prefix(question_text: str) -> str:
        text = question_text.strip()
        if not text:
            return text
        if AdversarialSession._has_empathy_prefix(text):
            return text
        return "Thank you for walking me through this; I know it can be difficult. " + text

    @classmethod
    def _empathy_prefix_for_question(cls, turn_index: int, question: Any) -> str:
        if cls._is_harm_or_remedy_question(question):
            return "I am sorry you are dealing with this, and I appreciate you sharing these details."
        if cls._is_protected_activity_causation_question(question) or cls._is_contradiction_resolution_question(question):
            return "Thank you for staying with me through this; these details are important and I know this can be hard to revisit."
        if cls._is_documentary_evidence_question(question) or cls._is_witness_question(question):
            return "Thank you for sharing this; even partial records can still help."
        if cls._is_timeline_question(question):
            return "Thank you for your patience; timeline details help us protect your claim."
        if turn_index <= 1:
            return "Thank you for sharing this; I know it may be stressful."
        return "Thank you for walking me through this."

    @classmethod
    def _should_apply_empathy_prefix(cls, turn_index: int, question: Any) -> bool:
        if turn_index <= 2:
            return True
        return (
            cls._is_harm_or_remedy_question(question)
            or cls._is_protected_activity_causation_question(question)
            or cls._is_contradiction_resolution_question(question)
            or cls._is_documentary_evidence_question(question)
            or cls._is_witness_question(question)
        )

    def _select_next_question(
        self,
        questions: List[Any],
        asked_question_counts: Dict[str, int] | None = None,
        asked_intent_counts: Dict[str, int] | None = None,
        need_timeline: bool = False,
        need_harm_remedy: bool = False,
        need_actor_decisionmaker: bool = False,
        need_causation: bool = False,
        need_documentary_evidence: bool = False,
        need_witness: bool = False,
        need_exact_dates: bool = False,
        need_staff_names_titles: bool = False,
        need_hearing_request_timing: bool = False,
        need_response_dates: bool = False,
        need_causation_sequence: bool = False,
        last_question_key: str | None = None,
        last_question_intent_key: str | None = None,
        recent_intent_keys: Set[str] | None = None,
        missing_anchor_sections: Set[str] | None = None,
    ) -> Any:
        return session_intake._select_next_question(
            self,
            questions,
            asked_question_counts,
            asked_intent_counts,
            need_timeline,
            need_harm_remedy,
            need_actor_decisionmaker,
            need_causation,
            need_documentary_evidence,
            need_witness,
            need_exact_dates,
            need_staff_names_titles,
            need_hearing_request_timing,
            need_response_dates,
            need_causation_sequence,
            last_question_key,
            last_question_intent_key,
            recent_intent_keys,
            missing_anchor_sections,
        )

    @staticmethod
    def _compact_document_generation_result(result: Any) -> Dict[str, Any]:
        return session_document_fallback._compact_document_generation_result(
            result,
        )

    @staticmethod
    def _build_grounding_summary(seed_complaint: Dict[str, Any], final_state: Dict[str, Any]) -> Dict[str, Any]:
        key_facts = seed_complaint.get('key_facts') if isinstance(seed_complaint.get('key_facts'), dict) else {}
        synthetic_prompts = key_facts.get('synthetic_prompts') if isinstance(key_facts.get('synthetic_prompts'), dict) else {}
        uploaded_evidence_summary = final_state.get('uploaded_evidence_summary') if isinstance(final_state, dict) and isinstance(final_state.get('uploaded_evidence_summary'), dict) else {}
        return {
            'grounding_note': str(key_facts.get('grounding_note') or ''),
            'search_summary': dict(key_facts.get('search_summary') or {}),
            'anchor_sections': list(key_facts.get('anchor_sections') or []),
            'repository_evidence_candidate_count': len(list(key_facts.get('repository_evidence_candidates') or [])),
            'preloaded_mediator_evidence_count': len(list(((seed_complaint.get('_meta') or {}).get('preloaded_mediator_evidence') or []))),
            'uploaded_evidence_count': int(uploaded_evidence_summary.get('count') or 0),
            'synthetic_intake_question_count': len(list(synthetic_prompts.get('intake_questions') or [])),
            'has_evidence_upload_prompt': bool(
                str(synthetic_prompts.get('evidence_upload_prompt') or '').strip()
                or str(synthetic_prompts.get('production_upload_prompt') or '').strip()
                or next(
                    (
                        str((prompt or {}).get('text') or '').strip()
                        for prompt in list(synthetic_prompts.get('evidence_upload_prompts') or [])
                        if isinstance(prompt, dict) and str((prompt or {}).get('text') or '').strip()
                    ),
                    '',
                )
            ),
        }

    @staticmethod
    def _default_relief_for_seed(seed_complaint: Dict[str, Any]) -> List[str]:
        complaint_type = str(seed_complaint.get('type') or '').strip().lower()
        if complaint_type == 'housing_discrimination':
            return [
                'Declaratory relief that the challenged housing action was unlawful.',
                'Injunctive relief requiring a fair hearing and restoration of housing benefits if warranted.',
                'Compensatory damages for housing instability, delay, and emotional distress.',
                'Costs and any other relief authorized by law.',
            ]
        return [
            'Compensatory damages according to proof.',
            'Costs and any other relief authorized by law.',
        ]

    def _build_document_generation_fallback(
        self,
        seed_complaint: Dict[str, Any],
        *,
        builder_error: str = '',
    ) -> Dict[str, Any]:
        return session_document_fallback._build_document_generation_fallback(
            self,
            seed_complaint,
            builder_error=builder_error,
        )

    def _run_document_generation(self, seed_complaint: Dict[str, Any]) -> Dict[str, Any]:
        return session_document_fallback._run_document_generation(
            self,
            seed_complaint,
        )
    
    def run(self, seed_complaint: Dict[str, Any]) -> SessionResult:
        """
        Run a complete session.
        
        Args:
            seed_complaint: Seed data for complaint generation
            
        Returns:
            SessionResult with complete session data
        """
        logger.info(f"Starting session {self.session_id}")
        self.start_time = time.time()
        
        try:
            # Step 1: Generate initial complaint
            initial_complaint = self.complainant.generate_initial_complaint(seed_complaint)
            self._emit_progress(
                'initial_complaint_generated',
                metadata={'complaint_length': len(initial_complaint or '')},
            )
            logger.debug(f"Initial complaint generated: {initial_complaint[:100]}...")
            
            # Step 2: Initialize mediator with complaint
            with self._temporarily_prioritize_mediator_intake_objectives(seed_complaint):
                result = self.mediator.start_three_phase_process(initial_complaint)
            self._emit_progress(
                'mediator_initialized',
                metadata={'initial_question_count': len(list((result or {}).get('initial_questions', []) or [])) if isinstance(result, dict) else 0},
            )
            if isinstance(result, dict):
                result['initial_questions'] = self._inject_intake_prompt_questions(
                    seed_complaint,
                    result.get('initial_questions', []),
                )
                self._persist_intake_priority_summary(
                    seed_complaint,
                    result.get('initial_questions', []),
                )
            
            # Step 3: Iteratively ask and answer questions
            questions_asked = 0
            turns = 0
            asked_question_keys: Set[str] = set()
            asked_question_counts: Dict[str, int] = {}
            asked_intent_counts: Dict[str, int] = {}
            last_question_key: str | None = None
            last_question_intent_key: str | None = None
            recent_intent_keys: List[str] = []
            recent_intent_window = 3
            has_timeline_question = False
            has_harm_remedy_question = False
            has_actor_or_decisionmaker_question = False
            has_causation_question = False
            has_documentary_evidence_question = False
            has_witness_question = False
            has_exact_dates_question = False
            has_staff_names_titles_question = False
            has_hearing_request_timing_question = False
            has_response_dates_question = False
            has_causation_sequence_question = False
            expected_anchor_sections = self._extract_anchor_sections(seed_complaint)
            required_blocker_objectives = self._extract_required_blocker_objectives(seed_complaint)
            latest_batch_flags = self._extract_latest_batch_priority_flags(seed_complaint)
            require_causation_probe = self._seed_requires_causation_probe(seed_complaint)
            require_exact_dates_probe = (
                'exact_dates' in required_blocker_objectives
                or bool(latest_batch_flags.get('needs_chronology_closure'))
            )
            require_staff_names_titles_probe = (
                'staff_names_titles' in required_blocker_objectives
                or bool(latest_batch_flags.get('needs_decision_document_precision'))
            )
            require_hearing_timing_probe = (
                'hearing_request_timing' in required_blocker_objectives
                or bool(latest_batch_flags.get('needs_chronology_closure'))
                or bool(expected_anchor_sections & {'grievance_hearing', 'appeal_rights'})
            )
            require_response_dates_probe = (
                'response_dates' in required_blocker_objectives
                or bool(latest_batch_flags.get('needs_chronology_closure'))
                or bool(expected_anchor_sections & {'grievance_hearing', 'appeal_rights', 'adverse_action'})
            )
            require_causation_sequence_probe = (
                'causation_sequence' in required_blocker_objectives
                or require_causation_probe
                or bool(latest_batch_flags.get('needs_chronology_closure'))
            )
            
            while turns < self.max_turns:
                # Get questions from mediator
                questions = result.get('initial_questions', []) if turns == 0 else \
                           result.get('next_questions', [])
                covered_anchor_sections = self._covered_anchor_sections_from_questions(
                    asked_question_keys,
                    expected_anchor_sections,
                )
                missing_anchor_sections = expected_anchor_sections - covered_anchor_sections

                need_timeline = not has_timeline_question
                need_harm_remedy = not has_harm_remedy_question
                need_actor_decisionmaker = not has_actor_or_decisionmaker_question
                need_causation = require_causation_probe and not has_causation_question
                need_documentary_evidence = not has_documentary_evidence_question
                need_witness = not has_witness_question
                need_exact_dates = require_exact_dates_probe and not has_exact_dates_question
                need_staff_names_titles = require_staff_names_titles_probe and not has_staff_names_titles_question
                need_hearing_request_timing = require_hearing_timing_probe and not has_hearing_request_timing_question
                need_response_dates = require_response_dates_probe and not has_response_dates_question
                need_causation_sequence = require_causation_sequence_probe and not has_causation_sequence_question

                coverage_rank_kwargs = dict(
                    need_timeline=need_timeline,
                    need_harm_remedy=need_harm_remedy,
                    need_actor_decisionmaker=need_actor_decisionmaker,
                    need_adverse_action_details=need_actor_decisionmaker,
                    need_causation=need_causation,
                    need_documentary_evidence=need_documentary_evidence,
                    need_witness=need_witness,
                    need_exact_dates=need_exact_dates,
                    need_staff_names_titles=need_staff_names_titles,
                    need_hearing_request_timing=need_hearing_request_timing,
                    need_response_dates=need_response_dates,
                    need_causation_sequence=need_causation_sequence,
                    missing_anchor_sections=missing_anchor_sections,
                )
                question = None
                if questions:
                    # Ask a non-repeated question when available and prioritize key coverage gaps.
                    question = self._select_next_question(
                        questions=questions,
                        asked_question_counts=asked_question_counts,
                        asked_intent_counts=asked_intent_counts,
                        need_timeline=need_timeline,
                        need_harm_remedy=need_harm_remedy,
                        need_actor_decisionmaker=need_actor_decisionmaker,
                        need_causation=need_causation,
                        need_documentary_evidence=need_documentary_evidence,
                        need_witness=need_witness,
                        need_exact_dates=need_exact_dates,
                        need_staff_names_titles=need_staff_names_titles,
                        need_hearing_request_timing=need_hearing_request_timing,
                        need_response_dates=need_response_dates,
                        need_causation_sequence=need_causation_sequence,
                        last_question_key=last_question_key,
                        last_question_intent_key=last_question_intent_key,
                        recent_intent_keys=set(recent_intent_keys),
                        missing_anchor_sections=missing_anchor_sections,
                    )

                fallback_question = self._build_fallback_probe(
                    seed_complaint,
                    asked_question_counts=asked_question_counts,
                    asked_intent_counts=asked_intent_counts,
                    need_timeline=need_timeline,
                    need_harm_remedy=need_harm_remedy,
                    need_actor_decisionmaker=need_actor_decisionmaker,
                    need_causation=need_causation,
                    need_documentary_evidence=need_documentary_evidence,
                    need_witness=need_witness,
                    need_exact_dates=need_exact_dates,
                    need_staff_names_titles=need_staff_names_titles,
                    need_hearing_request_timing=need_hearing_request_timing,
                    need_response_dates=need_response_dates,
                    need_causation_sequence=need_causation_sequence,
                    last_question_key=last_question_key,
                    last_question_intent_key=last_question_intent_key,
                    recent_intent_keys=set(recent_intent_keys),
                    missing_anchor_sections=missing_anchor_sections,
                )
                if fallback_question is not None:
                    use_fallback = question is None
                    if question is not None:
                        fallback_rank = self._coverage_gap_rank(fallback_question, **coverage_rank_kwargs)
                        selected_rank = self._coverage_gap_rank(question, **coverage_rank_kwargs)
                        if fallback_rank < selected_rank and not self._questions_substantially_overlap(
                            fallback_question,
                            question,
                        ):
                            use_fallback = True
                    if use_fallback:
                        question = fallback_question
                        logger.debug("Using harness fallback probe for missing coverage")

                if question is None:
                    if not questions:
                        logger.info(f"No more questions, session complete after {turns} turns")
                    else:
                        logger.info(
                            "Only repeated questions remain and no useful fallback probe was available; ending session at turn %s",
                            turns,
                        )
                    break
                question_text = self._extract_question_text(question)
                question_objective = self._extract_question_objective(question)
                question_reason = ''
                if isinstance(question, dict):
                    question_reason = str(question.get('question_reason') or '').strip()
                expected_proof_gain = ''
                if isinstance(question, dict):
                    expected_proof_gain = str(question.get('expected_proof_gain') or '').strip()
                question_key = self._question_dedupe_key(question_text)
                question_intent_key = self._question_intent_key(question_text, question)
                if question_key in asked_question_keys:
                    logger.debug("Mediator repeated question (no non-repeated alternative available)")
                logger.debug(f"Mediator asks: {question_text}")

                # Get response from complainant
                complainant_prompt = question_text
                if self._should_apply_empathy_prefix(turns, question):
                    empathic_prefix = self._empathy_prefix_for_question(turns, question)
                    complainant_prompt = (
                        question_text
                        if self._has_empathy_prefix(question_text)
                        else f"{empathic_prefix} {question_text}".strip()
                    )
                self._emit_progress(
                    'awaiting_complainant_answer',
                    metadata={
                        'turn_index': turns + 1,
                        'question_objective': question_objective,
                        'question_preview': question_text[:160],
                    },
                )
                answer = self.complainant.respond_to_question(
                    complainant_prompt
                )
                self._emit_progress(
                    'complainant_answer_received',
                    metadata={
                        'turn_index': turns + 1,
                        'answer_length': len(answer or ''),
                    },
                )
                logger.debug(f"Complainant answers: {answer[:100]}...")

                mediator_turn = {
                    'role': 'mediator',
                    'type': 'question',
                    'content': question_text,
                }
                if question_objective:
                    mediator_turn['question_objective'] = question_objective
                if question_reason:
                    mediator_turn['question_reason'] = question_reason
                if expected_proof_gain:
                    mediator_turn['expected_proof_gain'] = expected_proof_gain
                selector_score = self._extract_selector_score(question)
                if selector_score:
                    mediator_turn['selector_score'] = selector_score
                actor_critic_score = self._extract_actor_critic_score(question)
                if actor_critic_score:
                    mediator_turn['actor_critic_score'] = actor_critic_score
                phase1_section = self._extract_phase1_section(question)
                if phase1_section:
                    mediator_turn['phase1_section'] = phase1_section
                selector_signals = self._extract_selector_signals(question)
                if selector_signals:
                    candidate_source = str(selector_signals.get('candidate_source') or '').strip()
                    if candidate_source:
                        mediator_turn['candidate_source'] = candidate_source
                    intake_matches = selector_signals.get('intake_priority_match')
                    if isinstance(intake_matches, list) and intake_matches:
                        mediator_turn['intake_priority_match'] = list(intake_matches)
                self.conversation_history.append(mediator_turn)

                self.conversation_history.append(
                    {
                        'role': 'complainant',
                        'type': 'answer',
                        'content': answer,
                    }
                )
                
                # Process answer with mediator
                result = self.mediator.process_denoising_answer(question, answer)
                self._emit_progress(
                    'turn_processed',
                    metadata={
                        'turn_index': turns + 1,
                        'questions_asked': questions_asked + 1,
                        'converged': bool(result.get('converged', False) or result.get('ready_for_evidence_phase', False)),
                    },
                )

                asked_question_keys.add(question_key)
                asked_question_counts[question_key] = asked_question_counts.get(question_key, 0) + 1
                asked_intent_counts[question_intent_key] = asked_intent_counts.get(question_intent_key, 0) + 1
                last_question_key = question_key
                last_question_intent_key = question_intent_key
                if question_intent_key:
                    recent_intent_keys.append(question_intent_key)
                    if len(recent_intent_keys) > recent_intent_window:
                        recent_intent_keys = recent_intent_keys[-recent_intent_window:]
                if self._is_timeline_question(question):
                    has_timeline_question = True
                if self._is_harm_or_remedy_question(question):
                    has_harm_remedy_question = True
                if self._is_actor_or_decisionmaker_question(question):
                    has_actor_or_decisionmaker_question = True
                if self._is_protected_activity_causation_question(question):
                    has_causation_question = True
                if self._is_documentary_evidence_question(question):
                    has_documentary_evidence_question = True
                if self._is_witness_question(question):
                    has_witness_question = True
                if self._is_exact_dates_question(question):
                    has_exact_dates_question = True
                if self._is_staff_names_titles_question(question):
                    has_staff_names_titles_question = True
                if self._is_hearing_request_timing_question(question):
                    has_hearing_request_timing_question = True
                if self._is_response_dates_question(question):
                    has_response_dates_question = True
                if self._is_causation_sequence_question(question):
                    has_causation_sequence_question = True
                
                questions_asked += 1
                turns += 1
                
                # Check if converged
                converged = result.get('converged', False) or result.get('ready_for_evidence_phase', False)
                has_core_coverage = has_timeline_question and has_harm_remedy_question
                has_evidence_coverage = (
                    has_actor_or_decisionmaker_question
                    or has_causation_question
                    or has_documentary_evidence_question
                    or has_witness_question
                )
                has_causation_coverage = (not require_causation_probe) or has_causation_question
                has_blocker_coverage = (
                    ((not require_exact_dates_probe) or has_exact_dates_question)
                    and ((not require_staff_names_titles_probe) or has_staff_names_titles_question)
                    and ((not require_hearing_timing_probe) or has_hearing_request_timing_question)
                    and ((not require_response_dates_probe) or has_response_dates_question)
                    and ((not require_causation_sequence_probe) or has_causation_sequence_question)
                )
                if converged and has_core_coverage and has_evidence_coverage and has_causation_coverage and has_blocker_coverage:
                    logger.info(f"Session converged after {turns} turns")
                    break
            
            refreshed_intake_case_file_snapshot = self._refresh_final_intake_case_file_snapshot()

            # Step 4: Get final state
            final_state = self.mediator.get_three_phase_status()
            if isinstance(final_state, dict):
                runtime_workflow_guidance = self._build_runtime_workflow_guidance(final_state)
                if runtime_workflow_guidance:
                    final_state = {
                        **final_state,
                        'workflow_optimization_guidance': runtime_workflow_guidance,
                    }
                document_generation_result = self._run_document_generation(seed_complaint)
                if document_generation_result:
                    final_state = {
                        **final_state,
                        'document_generation': self._compact_document_generation_result(document_generation_result),
                    }
                final_state['grounding_summary'] = self._build_grounding_summary(seed_complaint, final_state)
                final_state['intake_question_structure_summary'] = self._build_intake_question_structure_summary(
                    self.conversation_history,
                    final_state,
                )
            self._emit_progress(
                'final_state_built',
                metadata={
                    'has_final_state': isinstance(final_state, dict),
                    'final_state_keys': sorted(list(final_state.keys()))[:20] if isinstance(final_state, dict) else [],
                },
            )

            refreshed_intake_case_file_snapshot = (
                self._refresh_final_intake_case_file_snapshot()
                or refreshed_intake_case_file_snapshot
            )
            
            # Get graph summaries if available
            kg_summary = None
            dg_summary = None
            kg_dict = None
            dg_dict = None
            intake_case_file_snapshot = None
            uploaded_evidence_summary = None
            claim_support_packet_summary = None
            try:
                from complaint_phases import ComplaintPhase
                kg = self.mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
                dg = self.mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
                intake_case_file_snapshot = (
                    refreshed_intake_case_file_snapshot
                    or self.mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'intake_case_file')
                )
                uploaded_evidence_summary = self.mediator.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'uploaded_evidence_summary')
                claim_support_packet_summary = self.mediator.phase_manager.get_phase_data(ComplaintPhase.EVIDENCE, 'claim_support_packet_summary')
                if kg:
                    kg_summary = kg.summary()
                    try:
                        kg_dict = kg.to_dict()
                    except Exception:
                        kg_dict = None
                if dg:
                    dg_summary = dg.summary()
                    try:
                        dg_dict = dg.to_dict()
                    except Exception:
                        dg_dict = None
            except Exception as e:
                logger.warning(f"Could not get graph summaries: {e}")

            if isinstance(final_state, dict):
                if isinstance(intake_case_file_snapshot, dict) and intake_case_file_snapshot:
                    final_state['intake_case_file'] = intake_case_file_snapshot
                if isinstance(uploaded_evidence_summary, dict) and uploaded_evidence_summary:
                    final_state['uploaded_evidence_summary'] = uploaded_evidence_summary
                if isinstance(claim_support_packet_summary, dict) and claim_support_packet_summary:
                    final_state['claim_support_packet_summary'] = claim_support_packet_summary
            
            # Step 5: Evaluate with critic
            conversation_history = self.complainant.get_conversation_history()
            critic_score = self.critic.evaluate_session(
                initial_complaint,
                conversation_history,
                final_state,
                context=seed_complaint
            )
            self._emit_progress(
                'critic_evaluated',
                metadata={'overall_score': float(getattr(critic_score, 'overall_score', 0.0) or 0.0)},
            )
            
            self.end_time = time.time()
            duration = self.end_time - self.start_time
            
            # Build result
            result = SessionResult(
                session_id=self.session_id,
                timestamp=datetime.now(UTC).isoformat(),
                seed_complaint=seed_complaint,
                initial_complaint_text=initial_complaint,
                conversation_history=conversation_history,
                num_questions=questions_asked,
                num_turns=turns,
                final_state=final_state,
                knowledge_graph_summary=kg_summary,
                dependency_graph_summary=dg_summary,
                knowledge_graph=kg_dict,
                dependency_graph=dg_dict,
                critic_score=critic_score,
                duration_seconds=duration,
                success=True
            )
            
            logger.info(f"Session {self.session_id} completed successfully. "
                       f"Score: {critic_score.overall_score:.3f}")
            self._emit_progress(
                'session_completed',
                metadata={'success': True, 'overall_score': float(getattr(critic_score, 'overall_score', 0.0) or 0.0)},
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Session {self.session_id} failed: {e}", exc_info=True)
            self.end_time = time.time()
            duration = self.end_time - self.start_time if self.start_time else 0
            self._emit_progress(
                'session_failed',
                metadata={'success': False, 'error': str(e)},
            )
            
            return SessionResult(
                session_id=self.session_id,
                timestamp=datetime.now(UTC).isoformat(),
                seed_complaint=seed_complaint,
                initial_complaint_text="",
                conversation_history=[],
                num_questions=0,
                num_turns=0,
                final_state={},
                duration_seconds=duration,
                success=False,
                error=str(e)
            )

from . import session_intake
from . import session_document_fallback
