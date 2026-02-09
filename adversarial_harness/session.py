"""
Adversarial Session Module

Manages a single adversarial training session between complainant and mediator.
"""

import logging
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
            return str(question.get('question', ''))
        return str(question)

    @staticmethod
    def _normalize_question(question_text: str) -> str:
        return " ".join(question_text.lower().strip().split())

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

    def _select_next_question(
        self,
        questions: List[Any],
        asked_question_keys: Set[str],
        need_timeline: bool,
        need_harm_remedy: bool,
    ) -> Any:
        if not questions:
            return None

        candidates = []
        for q in questions:
            text = self._extract_question_text(q)
            key = self._normalize_question(text)
            candidates.append((q, text, key, key in asked_question_keys))

        if need_timeline:
            for q, text, _, is_repeat in candidates:
                if not is_repeat and self._is_timeline_question(text):
                    return q

        if need_harm_remedy:
            for q, text, _, is_repeat in candidates:
                if not is_repeat and self._is_harm_or_remedy_question(text):
                    return q

        for q, _, _, is_repeat in candidates:
            if not is_repeat:
                return q

        return questions[0]
    
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
                    asked_question_keys=asked_question_keys,
                    need_timeline=not has_timeline_question,
                    need_harm_remedy=not has_harm_remedy_question,
                )
                question_text = self._extract_question_text(question)
                question_key = self._normalize_question(question_text)
                if question_key in asked_question_keys:
                    logger.debug("Mediator repeated question (no non-repeated alternative available)")
                logger.debug(f"Mediator asks: {question_text}")
                
                # Get response from complainant
                answer = self.complainant.respond_to_question(question_text)
                logger.debug(f"Complainant answers: {answer[:100]}...")
                
                # Process answer with mediator
                result = self.mediator.process_denoising_answer(question, answer)

                asked_question_keys.add(question_key)
                if self._is_timeline_question(question_text):
                    has_timeline_question = True
                if self._is_harm_or_remedy_question(question_text):
                    has_harm_remedy_question = True
                
                questions_asked += 1
                turns += 1
                
                # Check if converged
                if result.get('converged', False) or result.get('ready_for_evidence_phase', False):
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
