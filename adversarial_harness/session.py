"""
Adversarial Session Module

Manages a single adversarial training session between complainant and mediator.
"""

import logging
import re
from typing import Dict, Any, List, Set
from dataclasses import dataclass
from datetime import datetime
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
            'critic_score': self.critic_score.to_dict() if self.critic_score else None,
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
                 max_turns: int = 10):
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
        
        self.conversation_history = []
        self.start_time = None
        self.end_time = None

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
    def _question_intent_key(question_text: str) -> str:
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
    def _is_timeline_question(question_text: str) -> bool:
        text = question_text.lower()
        timeline_terms = (
            'when',
            'date',
            'timeline',
            'chronolog',
            'sequence',
            'what happened first',
            'before',
            'after',
        )
        return any(term in text for term in timeline_terms)

    @staticmethod
    def _is_harm_or_remedy_question(question_text: str) -> bool:
        text = question_text.lower()
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
        )
        return any(term in text for term in harm_remedy_terms)

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
        return (
            "I understand this can be stressful, and these details help me support you. "
            + text
        )

    def _select_next_question(
        self,
        questions: List[Any],
        asked_question_counts: Dict[str, int],
        asked_intent_counts: Dict[str, int],
        need_timeline: bool,
        need_harm_remedy: bool,
        last_question_key: str | None,
        last_question_intent_key: str | None,
        recent_intent_keys: Set[str],
    ) -> Any:
        if not questions:
            return None

        seen_question_keys = [k for k, count in asked_question_counts.items() if count > 0]
        candidate_keys_in_turn: Set[str] = set()
        novel_similarity_threshold = 0.7
        rephrase_similarity_threshold = 0.65
        candidates = []
        for q in questions:
            text = self._extract_question_text(q)
            key = self._question_dedupe_key(text)
            if not key or key in candidate_keys_in_turn:
                # Skip empty and duplicate prompts emitted in the same mediator step.
                continue
            candidate_keys_in_turn.add(key)
            intent_key = self._question_intent_key(text)
            asked_count = asked_question_counts.get(key, 0)
            intent_count = asked_intent_counts.get(intent_key, 0)
            similarity_to_seen = 0.0
            if seen_question_keys:
                similarity_to_seen = max(
                    self._question_similarity(text, seen_key)
                    for seen_key in seen_question_keys
                )
            candidates.append((
                q,
                text,
                key,
                intent_key,
                asked_count,
                intent_count,
                similarity_to_seen,
            ))

        if not candidates:
            return None

        non_redundant_candidates = [
            c for c in candidates
            if not self._is_redundant_candidate(
                key=c[2],
                intent_key=c[3],
                asked_count=c[4],
                intent_count=c[5],
                similarity_to_seen=c[6],
                last_question_key=last_question_key,
                last_question_intent_key=last_question_intent_key,
                recent_intent_keys=recent_intent_keys,
            )
        ]
        # Prefer broader coverage by choosing less-repeated intents/questions first.
        non_redundant_candidates.sort(key=lambda c: (c[5], c[4], c[6]))

        if need_harm_remedy:
            for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
                if (
                    asked_count == 0
                    and intent_count == 0
                    and similarity_to_seen < novel_similarity_threshold
                    and self._is_harm_or_remedy_question(text)
                ):
                    return q

        if need_timeline:
            for q, text, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
                if (
                    asked_count == 0
                    and intent_count == 0
                    and similarity_to_seen < novel_similarity_threshold
                    and self._is_timeline_question(text)
                ):
                    return q

        for q, _, _, _, asked_count, intent_count, similarity_to_seen in non_redundant_candidates:
            if (
                asked_count == 0
                and intent_count == 0
                and similarity_to_seen < novel_similarity_threshold
            ):
                return q

        # Fall back to any unseen question if all options are close in wording.
        for q, _, _, _, asked_count, intent_count, _ in non_redundant_candidates:
            if asked_count == 0 and intent_count == 0:
                return q

        if need_timeline or need_harm_remedy:
            for q, text, key, _, asked_count, _, _ in candidates:
                if asked_count > 0 or key == last_question_key:
                    continue
                if need_timeline and self._is_timeline_question(text):
                    return q
                if need_harm_remedy and self._is_harm_or_remedy_question(text):
                    return q

        # As a last resort, allow one rephrase on a covered intent only if we still
        # need timeline or harm/remedy coverage and the wording is meaningfully different.
        for q, text, key, _, asked_count, intent_count, similarity_to_seen in candidates:
            if (
                asked_count == 0
                and intent_count == 1
                and key != last_question_key
                and similarity_to_seen < rephrase_similarity_threshold
                and (
                    (need_timeline and self._is_timeline_question(text))
                    or (need_harm_remedy and self._is_harm_or_remedy_question(text))
                )
            ):
                return q

        return None
    
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
            logger.debug(f"Initial complaint generated: {initial_complaint[:100]}...")
            
            # Step 2: Initialize mediator with complaint
            result = self.mediator.start_three_phase_process(initial_complaint)
            
            # Step 3: Iteratively ask and answer questions
            questions_asked = 0
            turns = 0
            asked_question_keys: Set[str] = set()
            asked_question_counts: Dict[str, int] = {}
            asked_intent_counts: Dict[str, int] = {}
            last_question_key: str | None = None
            last_question_intent_key: str | None = None
            recent_intent_keys: List[str] = []
            recent_intent_window = 2
            has_timeline_question = False
            has_harm_remedy_question = False
            
            while turns < self.max_turns:
                # Get questions from mediator
                questions = result.get('initial_questions', []) if turns == 0 else \
                           result.get('next_questions', [])
                
                if not questions:
                    logger.info(f"No more questions, session complete after {turns} turns")
                    break
                
                # Ask a non-repeated question when available and prioritize key coverage gaps.
                question = self._select_next_question(
                    questions=questions,
                    asked_question_counts=asked_question_counts,
                    asked_intent_counts=asked_intent_counts,
                    need_timeline=not has_timeline_question,
                    need_harm_remedy=not has_harm_remedy_question,
                    last_question_key=last_question_key,
                    last_question_intent_key=last_question_intent_key,
                    recent_intent_keys=set(recent_intent_keys),
                )
                if question is None:
                    logger.info(
                        "Only repeated questions remain; ending session early at turn %s",
                        turns,
                    )
                    break
                question_text = self._extract_question_text(question)
                question_key = self._question_dedupe_key(question_text)
                question_intent_key = self._question_intent_key(question_text)
                if question_key in asked_question_keys:
                    logger.debug("Mediator repeated question (no non-repeated alternative available)")
                logger.debug(f"Mediator asks: {question_text}")
                
                # Get response from complainant
                answer = self.complainant.respond_to_question(
                    self._with_empathy_prefix(question_text)
                )
                logger.debug(f"Complainant answers: {answer[:100]}...")
                
                # Process answer with mediator
                result = self.mediator.process_denoising_answer(question, answer)

                asked_question_keys.add(question_key)
                asked_question_counts[question_key] = asked_question_counts.get(question_key, 0) + 1
                asked_intent_counts[question_intent_key] = asked_intent_counts.get(question_intent_key, 0) + 1
                last_question_key = question_key
                last_question_intent_key = question_intent_key
                if question_intent_key:
                    recent_intent_keys.append(question_intent_key)
                    if len(recent_intent_keys) > recent_intent_window:
                        recent_intent_keys = recent_intent_keys[-recent_intent_window:]
                if self._is_timeline_question(question_text):
                    has_timeline_question = True
                if self._is_harm_or_remedy_question(question_text):
                    has_harm_remedy_question = True
                
                questions_asked += 1
                turns += 1
                
                # Check if converged
                converged = result.get('converged', False) or result.get('ready_for_evidence_phase', False)
                if converged and has_harm_remedy_question:
                    logger.info(f"Session converged after {turns} turns")
                    break
            
            # Step 4: Get final state
            final_state = self.mediator.get_three_phase_status()
            
            # Get graph summaries if available
            kg_summary = None
            dg_summary = None
            kg_dict = None
            dg_dict = None
            try:
                from complaint_phases import ComplaintPhase
                kg = self.mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'knowledge_graph')
                dg = self.mediator.phase_manager.get_phase_data(ComplaintPhase.INTAKE, 'dependency_graph')
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
            
            # Step 5: Evaluate with critic
            conversation_history = self.complainant.get_conversation_history()
            critic_score = self.critic.evaluate_session(
                initial_complaint,
                conversation_history,
                final_state,
                context=seed_complaint
            )
            
            self.end_time = time.time()
            duration = self.end_time - self.start_time
            
            # Build result
            result = SessionResult(
                session_id=self.session_id,
                timestamp=datetime.utcnow().isoformat(),
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
            
            return result
            
        except Exception as e:
            logger.error(f"Session {self.session_id} failed: {e}", exc_info=True)
            self.end_time = time.time()
            duration = self.end_time - self.start_time if self.start_time else 0
            
            return SessionResult(
                session_id=self.session_id,
                timestamp=datetime.utcnow().isoformat(),
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
