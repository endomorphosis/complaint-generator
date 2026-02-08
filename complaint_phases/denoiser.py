"""
Complaint Denoiser

Iteratively asks questions to fill gaps in the knowledge graph and reduce
noise/ambiguity in the complaint information.
"""

import logging
from typing import Dict, List, Any, Optional
from .knowledge_graph import KnowledgeGraph
from .dependency_graph import DependencyGraph

logger = logging.getLogger(__name__)


class ComplaintDenoiser:
    """
    Denoises complaint information through iterative questioning.
    
    Uses knowledge graph gaps and dependency graph requirements to generate
    targeted questions that help clarify and complete the complaint.
    """
    
    def __init__(self, mediator=None):
        self.mediator = mediator
        self.questions_asked = []
        self.questions_pool = []
    
    def generate_questions(self, 
                          knowledge_graph: KnowledgeGraph,
                          dependency_graph: DependencyGraph,
                          max_questions: int = 10) -> List[Dict[str, Any]]:
        """
        Generate questions to denoise the complaint.
        
        Args:
            knowledge_graph: Current knowledge graph
            dependency_graph: Current dependency graph
            max_questions: Maximum number of questions to generate
            
        Returns:
            List of question dictionaries with type, question text, and context
        """
        questions = []
        
        # Get knowledge graph gaps
        kg_gaps = knowledge_graph.find_gaps()
        for gap in kg_gaps[:max_questions]:
            if gap['type'] == 'low_confidence_entity':
                questions.append({
                    'type': 'clarification',
                    'question': gap['suggested_question'],
                    'context': {
                        'entity_id': gap['entity_id'],
                        'entity_name': gap['entity_name'],
                        'confidence': gap['confidence']
                    },
                    'priority': 'medium'
                })
            elif gap['type'] == 'unsupported_claim':
                questions.append({
                    'type': 'evidence',
                    'question': gap['suggested_question'],
                    'context': {
                        'claim_id': gap['entity_id'],
                        'claim_name': gap['claim_name']
                    },
                    'priority': 'high'
                })
            elif gap['type'] == 'isolated_entity':
                questions.append({
                    'type': 'relationship',
                    'question': gap['suggested_question'],
                    'context': {
                        'entity_id': gap['entity_id'],
                        'entity_name': gap['entity_name']
                    },
                    'priority': 'low'
                })
        
        # Get dependency graph unsatisfied requirements
        unsatisfied = dependency_graph.find_unsatisfied_requirements()
        for req in unsatisfied[:max_questions - len(questions)]:
            missing_deps = req.get('missing_dependencies', [])
            for dep in missing_deps[:2]:  # Ask about first 2 missing deps
                questions.append({
                    'type': 'requirement',
                    'question': f"To support the claim '{req['node_name']}', can you provide information about: {dep['source_name']}?",
                    'context': {
                        'claim_id': req['node_id'],
                        'claim_name': req['node_name'],
                        'requirement_id': dep['source_node_id'],
                        'requirement_name': dep['source_name']
                    },
                    'priority': 'high'
                })
        
        # Sort by priority
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        questions.sort(key=lambda q: priority_order.get(q.get('priority', 'low'), 3))
        
        # Track questions in pool
        self.questions_pool.extend(questions[:max_questions])
        
        return questions[:max_questions]
    
    def process_answer(self, question: Dict[str, Any], answer: str,
                      knowledge_graph: KnowledgeGraph,
                      dependency_graph: Optional[DependencyGraph] = None) -> Dict[str, Any]:
        """
        Process an answer to a denoising question.
        
        Args:
            question: The question that was asked
            answer: The user's answer
            knowledge_graph: Knowledge graph to update
            dependency_graph: Optional dependency graph to update
            
        Returns:
            Information about what was updated
        """
        self.questions_asked.append({
            'question': question,
            'answer': answer
        })
        
        updates = {
            'entities_updated': 0,
            'relationships_added': 0,
            'requirements_satisfied': 0
        }
        
        question_type = question.get('type')
        context = question.get('context', {})
        
        if question_type == 'clarification':
            # Update entity with clarified information
            entity_id = context.get('entity_id')
            entity = knowledge_graph.get_entity(entity_id)
            if entity:
                entity.confidence = min(1.0, entity.confidence + 0.2)
                entity.attributes['clarification'] = answer
                updates['entities_updated'] += 1
        
        elif question_type == 'relationship':
            # Extract relationships from answer (simplified)
            # In production, use LLM to extract structured relationships
            entity_id = context.get('entity_id')
            if entity_id and len(answer) > 10:
                # Mark entity as having relationships described
                entity = knowledge_graph.get_entity(entity_id)
                if entity:
                    entity.attributes['relationship_described'] = True
                    updates['entities_updated'] += 1
        
        elif question_type == 'evidence':
            # Track evidence description
            claim_id = context.get('claim_id')
            entity = knowledge_graph.get_entity(claim_id)
            if entity:
                if 'evidence_descriptions' not in entity.attributes:
                    entity.attributes['evidence_descriptions'] = []
                entity.attributes['evidence_descriptions'].append(answer)
                updates['entities_updated'] += 1
        
        elif question_type == 'requirement':
            # Mark requirement as addressed
            if dependency_graph:
                req_id = context.get('requirement_id')
                req_node = dependency_graph.get_node(req_id)
                if req_node and len(answer) > 10:
                    req_node.satisfied = True
                    req_node.confidence = 0.7
                    updates['requirements_satisfied'] += 1
        
        logger.info(f"Processed answer: {updates}")
        return updates
    
    def calculate_noise_level(self, 
                             knowledge_graph: KnowledgeGraph,
                             dependency_graph: DependencyGraph) -> float:
        """
        Calculate current noise/uncertainty level.
        
        Lower values indicate less noise (more complete, confident information).
        
        Args:
            knowledge_graph: Current knowledge graph
            dependency_graph: Current dependency graph
            
        Returns:
            Noise level from 0.0 (no noise) to 1.0 (maximum noise)
        """
        # Calculate knowledge graph confidence
        kg_confidence = 0.0
        if knowledge_graph.entities:
            total_confidence = sum(e.confidence for e in knowledge_graph.entities.values())
            kg_confidence = total_confidence / len(knowledge_graph.entities)
        
        # Calculate dependency satisfaction
        dep_satisfaction = 0.0
        readiness = dependency_graph.get_claim_readiness()
        dep_satisfaction = readiness.get('overall_readiness', 0.0)
        
        # Calculate gap ratio
        kg_gaps = len(knowledge_graph.find_gaps())
        kg_entities = len(knowledge_graph.entities)
        gap_ratio = kg_gaps / max(kg_entities, 1)
        
        # Combine metrics (lower is better)
        noise = (
            (1.0 - kg_confidence) * 0.4 +  # 40% weight on entity confidence
            (1.0 - dep_satisfaction) * 0.4 +  # 40% weight on dependency satisfaction
            min(gap_ratio, 1.0) * 0.2  # 20% weight on gaps
        )
        
        return noise
    
    def is_exhausted(self) -> bool:
        """
        Check if we've exhausted the question pool.
        
        Returns:
            True if no more questions can be asked
        """
        return len(self.questions_pool) == 0 or len(self.questions_asked) > 50
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of denoising progress."""
        return {
            'questions_asked': len(self.questions_asked),
            'questions_remaining': len(self.questions_pool),
            'exhausted': self.is_exhausted()
        }
