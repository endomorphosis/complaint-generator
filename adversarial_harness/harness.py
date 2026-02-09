"""
Adversarial Harness Module

Orchestrates multiple adversarial sessions with parallel execution.
"""

import logging
from typing import Dict, Any, List, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from datetime import datetime
import os

from .session import AdversarialSession, SessionResult
from .complainant import Complainant, ComplaintContext
from .critic import Critic
from .seed_complaints import SeedComplaintLibrary

logger = logging.getLogger(__name__)


class AdversarialHarness:
    """
    Orchestrates multiple adversarial training sessions.
    
    Features:
    - Parallel execution using LLM router
    - Progress tracking
    - Result aggregation
    - Failure handling
    """
    
    def __init__(self,
                 llm_backend_complainant,
                 llm_backend_critic,
                 mediator_factory: Callable,
                 seed_library: SeedComplaintLibrary = None,
                 max_parallel: int = 4):
        """
        Initialize adversarial harness.
        
        Args:
            llm_backend_complainant: LLM backend for complainant
            llm_backend_critic: LLM backend for critic
            mediator_factory: Factory function to create mediator instances
            seed_library: Optional seed complaint library
            max_parallel: Maximum parallel sessions
        """
        self.llm_backend_complainant = llm_backend_complainant
        self.llm_backend_critic = llm_backend_critic
        self.mediator_factory = mediator_factory
        self.seed_library = seed_library or SeedComplaintLibrary()
        self.max_parallel = max_parallel
        
        self.results = []
    
    def run_batch(self,
                  num_sessions: int = 10,
                  seed_complaints: List[Dict[str, Any]] = None,
                  personalities: List[str] = None,
                  max_turns_per_session: int = 10) -> List[SessionResult]:
        """
        Run a batch of adversarial sessions in parallel.
        
        Args:
            num_sessions: Number of sessions to run
            seed_complaints: Optional list of seed complaints (randomly selected if None)
            personalities: Optional list of personalities for complainants
            max_turns_per_session: Maximum turns per session
            
        Returns:
            List of SessionResults
        """
        logger.info(f"Starting batch of {num_sessions} sessions with {self.max_parallel} parallel")
        
        # Get seed complaints
        if seed_complaints is None:
            seed_complaints = self.seed_library.get_seed_complaints(count=num_sessions)
        elif len(seed_complaints) < num_sessions:
            # Cycle through provided seeds
            seed_complaints = (seed_complaints * ((num_sessions // len(seed_complaints)) + 1))[:num_sessions]
        
        # Get personalities
        if personalities is None:
            personalities = ['cooperative', 'defensive', 'vague', 'detailed', 'emotional']
        
        # Create session specs
        session_specs = []
        for i in range(num_sessions):
            session_id = f"session_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{i:03d}"
            seed = seed_complaints[i % len(seed_complaints)]
            personality = personalities[i % len(personalities)]
            
            session_specs.append({
                'session_id': session_id,
                'seed': seed,
                'personality': personality,
                'max_turns': max_turns_per_session
            })
        
        # Run sessions in parallel
        results = []
        with ThreadPoolExecutor(max_workers=self.max_parallel) as executor:
            # Submit all tasks
            future_to_spec = {
                executor.submit(self._run_single_session, spec): spec
                for spec in session_specs
            }
            
            # Collect results as they complete
            completed = 0
            for future in as_completed(future_to_spec):
                spec = future_to_spec[future]
                try:
                    result = future.result()
                    results.append(result)
                    completed += 1
                    
                    if result.success:
                        logger.info(f"Session {spec['session_id']} completed ({completed}/{num_sessions}). "
                                  f"Score: {result.critic_score.overall_score:.3f}")
                    else:
                        logger.warning(f"Session {spec['session_id']} failed ({completed}/{num_sessions}): "
                                     f"{result.error}")
                except Exception as e:
                    logger.error(f"Error in session {spec['session_id']}: {e}")
                    completed += 1
        
        self.results.extend(results)
        logger.info(f"Batch complete. {len([r for r in results if r.success])}/{num_sessions} successful")
        
        return results
    
    def _run_single_session(self, spec: Dict[str, Any]) -> SessionResult:
        """Run a single session (called in thread pool)."""
        try:
            # Create instances for this session
            complainant = Complainant(
                self.llm_backend_complainant,
                personality=spec['personality']
            )
            
            # Set context
            context = ComplaintContext(
                complaint_type=spec['seed'].get('type', 'unknown'),
                key_facts=spec['seed'].get('key_facts', {}),
                emotional_state='distressed',
                cooperation_level=0.8 if spec['personality'] == 'cooperative' else 0.5
            )
            complainant.set_context(context)
            
            critic = Critic(self.llm_backend_critic)
            
            # Create new mediator instance (thread-safe)
            mediator = self.mediator_factory()
            
            # Create and run session
            session = AdversarialSession(
                session_id=spec['session_id'],
                complainant=complainant,
                mediator=mediator,
                critic=critic,
                max_turns=spec['max_turns']
            )
            
            result = session.run(spec['seed'])
            return result
            
        except Exception as e:
            logger.error(f"Error running session {spec['session_id']}: {e}", exc_info=True)
            return SessionResult(
                session_id=spec['session_id'],
                timestamp=datetime.utcnow().isoformat(),
                seed_complaint=spec['seed'],
                initial_complaint_text="",
                conversation_history=[],
                num_questions=0,
                num_turns=0,
                final_state={},
                success=False,
                error=str(e)
            )
    
    def get_results(self) -> List[SessionResult]:
        """Get all results from this harness."""
        return self.results.copy()
    
    def get_successful_results(self) -> List[SessionResult]:
        """Get only successful results."""
        return [r for r in self.results if r.success]
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics across all results.
        
        Returns:
            Dictionary with aggregate statistics
        """
        if not self.results:
            return {'total_sessions': 0}
        
        successful = self.get_successful_results()
        
        if not successful:
            return {
                'total_sessions': len(self.results),
                'successful_sessions': 0,
                'failed_sessions': len(self.results)
            }
        
        scores = [r.critic_score.overall_score for r in successful]
        question_counts = [r.num_questions for r in successful]
        durations = [r.duration_seconds for r in successful]
        
        return {
            'total_sessions': len(self.results),
            'successful_sessions': len(successful),
            'failed_sessions': len(self.results) - len(successful),
            'average_score': sum(scores) / len(scores) if scores else 0,
            'min_score': min(scores) if scores else 0,
            'max_score': max(scores) if scores else 0,
            'average_questions': sum(question_counts) / len(question_counts) if question_counts else 0,
            'average_duration': sum(durations) / len(durations) if durations else 0,
            'score_distribution': self._score_distribution(scores)
        }
    
    def _score_distribution(self, scores: List[float]) -> Dict[str, int]:
        """Calculate score distribution."""
        if not scores:
            return {}
        
        bins = {
            '0.0-0.2': 0,
            '0.2-0.4': 0,
            '0.4-0.6': 0,
            '0.6-0.8': 0,
            '0.8-1.0': 0
        }
        
        for score in scores:
            if score < 0.2:
                bins['0.0-0.2'] += 1
            elif score < 0.4:
                bins['0.2-0.4'] += 1
            elif score < 0.6:
                bins['0.4-0.6'] += 1
            elif score < 0.8:
                bins['0.6-0.8'] += 1
            else:
                bins['0.8-1.0'] += 1
        
        return bins
    
    def save_results(self, filepath: str):
        """
        Save results to JSON file.
        
        Args:
            filepath: Path to save results
        """
        data = {
            'timestamp': datetime.utcnow().isoformat(),
            'statistics': self.get_statistics(),
            'results': [r.to_dict() for r in self.results]
        }
        
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Results saved to {filepath}")
