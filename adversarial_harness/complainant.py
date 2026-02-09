"""
Complainant Module

LLM-based complainant that generates complaints and responds to mediator questions.
"""

import logging
from typing import Dict, Any, List
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


@dataclass
class ComplaintContext:
    """Context information for a complaint."""
    complaint_type: str
    key_facts: Dict[str, Any]
    emotional_state: str = "distressed"
    cooperation_level: float = 0.8  # 0.0 to 1.0, how willing to provide info
    context_depth: int = 1  # How much detail complainant has


class Complainant:
    """
    LLM-based complainant that generates and responds to questions.
    
    This class simulates a real complainant by:
    - Generating initial complaints from seed data
    - Responding to mediator questions based on context
    - Simulating various emotional states and cooperation levels
    """
    
    def __init__(self, llm_backend, personality: str = "cooperative"):
        """
        Initialize complainant with LLM backend.
        
        Args:
            llm_backend: LLM backend for generating responses
            personality: Type of complainant (cooperative, defensive, vague, etc.)
        """
        self.llm_backend = llm_backend
        self.personality = personality
        self.context = None
        self.conversation_history = []
    
    def set_context(self, context: ComplaintContext):
        """Set the complaint context for this session."""
        self.context = context
        self.conversation_history = []
    
    def generate_initial_complaint(self, seed_data: Dict[str, Any]) -> str:
        """
        Generate an initial complaint from seed data.
        
        Args:
            seed_data: Seed information for complaint generation
            
        Returns:
            Generated complaint text
        """
        prompt = self._build_complaint_prompt(seed_data)
        
        try:
            response = self.llm_backend(prompt)
            self.conversation_history.append({
                'role': 'complainant',
                'type': 'initial_complaint',
                'content': response
            })
            return response
        except Exception as e:
            logger.error(f"Error generating complaint: {e}")
            return self._fallback_complaint(seed_data)
    
    def respond_to_question(self, question: str) -> str:
        """
        Respond to a mediator's question based on context and personality.
        
        Args:
            question: Question from mediator
            
        Returns:
            Complainant's response
        """
        if not self.context:
            raise ValueError("Context must be set before responding to questions")
        
        prompt = self._build_response_prompt(question)
        
        try:
            response = self.llm_backend(prompt)
            self.conversation_history.append({
                'role': 'mediator',
                'type': 'question',
                'content': question
            })
            self.conversation_history.append({
                'role': 'complainant',
                'type': 'response',
                'content': response
            })
            return response
        except Exception as e:
            logger.error(f"Error responding to question: {e}")
            return self._fallback_response(question)
    
    def _build_complaint_prompt(self, seed_data: Dict[str, Any]) -> str:
        """Build prompt for generating initial complaint."""
        prompt = f"""You are a person filing a complaint. Based on the following situation, write a detailed but natural complaint as if you were experiencing this issue.

Situation:
{json.dumps(seed_data, indent=2)}

Personality: {self.personality}

Generate a complaint that:
1. Describes what happened in your own words
2. Expresses how this affected you
3. Mentions key facts but doesn't over-explain
4. Sounds like a real person telling their story

Complaint:"""
        return prompt
    
    def _build_response_prompt(self, question: str) -> str:
        """Build prompt for responding to mediator question."""
        # Include conversation history for context
        history_text = "\n".join([
            f"{msg['role']}: {msg['content']}"
            for msg in self.conversation_history[-5:]  # Last 5 messages
        ])
        
        cooperation_desc = "very cooperative" if self.context.cooperation_level > 0.7 else \
                          "somewhat cooperative" if self.context.cooperation_level > 0.4 else \
                          "defensive"
        
        prompt = f"""You are a complainant in a legal matter. You are {cooperation_desc} and your personality is {self.personality}.

Your situation involves:
{json.dumps(self.context.key_facts, indent=2)}

Recent conversation:
{history_text}

The mediator asks: "{question}"

Respond naturally as this person would. Your response should:
1. Answer the question based on your knowledge
2. Match your personality ({self.personality}) and cooperation level ({cooperation_desc})
3. Be honest but not overly detailed unless asked
4. Sound like a real person, not a legal document

Response:"""
        return prompt
    
    def _fallback_complaint(self, seed_data: Dict[str, Any]) -> str:
        """Fallback complaint if LLM fails."""
        return f"I need to file a complaint about {seed_data.get('type', 'an issue')}. {seed_data.get('summary', 'Something happened that I need help with.')}"
    
    def _fallback_response(self, question: str) -> str:
        """Fallback response if LLM fails."""
        return "I'm not sure how to answer that right now. Can you rephrase the question?"
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get the full conversation history."""
        return self.conversation_history.copy()


class ComplaintGenerator:
    """
    Generates varied complaints from seed templates.
    
    This class creates diverse complaint scenarios by:
    - Using seed templates
    - Varying details and circumstances
    - Generating different personality types
    """
    
    def __init__(self, llm_backend):
        """
        Initialize complaint generator.
        
        Args:
            llm_backend: LLM backend for generating variations
        """
        self.llm_backend = llm_backend
    
    def generate_variations(self, seed: Dict[str, Any], count: int = 5) -> List[Dict[str, Any]]:
        """
        Generate variations of a seed complaint.
        
        Args:
            seed: Seed complaint template
            count: Number of variations to generate
            
        Returns:
            List of complaint variations
        """
        variations = []
        
        for i in range(count):
            prompt = f"""Based on this seed complaint scenario, generate a variation with different specific details but the same type of issue.

Seed scenario:
{json.dumps(seed, indent=2)}

Generate variation #{i+1} with:
- Different names/locations
- Different specific circumstances
- Same type of legal issue
- Realistic details

Return as JSON with fields: type, key_facts, summary

Variation:"""
            
            try:
                response = self.llm_backend(prompt)
                # Try to parse as JSON
                variation = self._parse_variation(response)
                variations.append(variation)
            except Exception as e:
                logger.warning(f"Error generating variation {i}: {e}")
                # Use seed with small modifications
                variations.append(self._simple_variation(seed, i))
        
        return variations
    
    def _parse_variation(self, response: str) -> Dict[str, Any]:
        """Parse LLM response as JSON variation."""
        try:
            # Try to extract JSON from response
            if '{' in response:
                json_start = response.index('{')
                json_end = response.rindex('}') + 1
                json_str = response[json_start:json_end]
                return json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")
        except Exception as e:
            logger.error(f"Error parsing variation: {e}")
            return {
                'type': 'unknown',
                'key_facts': {},
                'summary': response[:200]
            }
    
    def _simple_variation(self, seed: Dict[str, Any], index: int) -> Dict[str, Any]:
        """Create simple variation of seed."""
        variation = seed.copy()
        variation['variation_id'] = index
        return variation
