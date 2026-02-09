"""
Neurosymbolic Matcher

Matches complaint facts (from knowledge/dependency graphs) against legal
requirements (from legal graph) to assess claim viability and identify gaps.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from .knowledge_graph import KnowledgeGraph, Entity
from .dependency_graph import DependencyGraph, DependencyNode, NodeType
from .legal_graph import LegalGraph, LegalElement

logger = logging.getLogger(__name__)


class NeurosymbolicMatcher:
    """
    Performs neurosymbolic matching between complaint facts and legal requirements.
    
    Combines symbolic reasoning (graph matching, logical inference) with
    neural/semantic matching (LLM-based similarity, entity resolution) to
    determine if complaint facts satisfy legal requirements.
    """
    
    def __init__(self, mediator=None):
        self.mediator = mediator
        self.matching_results = []
    
    def match_claims_to_law(self,
                           knowledge_graph: KnowledgeGraph,
                           dependency_graph: DependencyGraph,
                           legal_graph: LegalGraph) -> Dict[str, Any]:
        """
        Match complaint claims against legal requirements.
        
        Args:
            knowledge_graph: Complaint facts and entities
            dependency_graph: Claim dependencies and requirements
            legal_graph: Legal requirements and rules
            
        Returns:
            Matching results with satisfaction analysis
        """
        results = {
            'claims': [],
            'overall_satisfaction': 0.0,
            'satisfied_claims': 0,
            'total_claims': 0,
            'gaps': []
        }
        
        # Get all claims from dependency graph
        claim_nodes = dependency_graph.get_nodes_by_type(NodeType.CLAIM)
        results['total_claims'] = len(claim_nodes)
        
        for claim_node in claim_nodes:
            claim_result = self._match_single_claim(
                claim_node, knowledge_graph, dependency_graph, legal_graph
            )
            results['claims'].append(claim_result)
            
            if claim_result['satisfied']:
                results['satisfied_claims'] += 1
            
            # Collect gaps
            results['gaps'].extend(claim_result.get('missing_requirements', []))
        
        # Calculate overall satisfaction
        if results['total_claims'] > 0:
            results['overall_satisfaction'] = results['satisfied_claims'] / results['total_claims']
        
        logger.info(f"Matching complete: {results['satisfied_claims']}/{results['total_claims']} claims satisfied")
        return results
    
    def _match_single_claim(self,
                           claim_node: DependencyNode,
                           knowledge_graph: KnowledgeGraph,
                           dependency_graph: DependencyGraph,
                           legal_graph: LegalGraph) -> Dict[str, Any]:
        """Match a single claim against legal requirements."""
        claim_type = claim_node.attributes.get('claim_type', 'unknown')
        
        # Get legal requirements for this claim type
        legal_requirements = legal_graph.get_requirements_for_claim_type(claim_type)
        
        result = {
            'claim_id': claim_node.id,
            'claim_name': claim_node.name,
            'claim_type': claim_type,
            'legal_requirements': len(legal_requirements),
            'satisfied_requirements': 0,
            'missing_requirements': [],
            'satisfied': False,
            'confidence': 0.0
        }
        
        # Check each legal requirement
        for legal_req in legal_requirements:
            match = self._check_requirement_satisfied(
                legal_req, claim_node, knowledge_graph, dependency_graph
            )
            
            if match['satisfied']:
                result['satisfied_requirements'] += 1
            else:
                result['missing_requirements'].append({
                    'requirement_name': legal_req.name,
                    'requirement_description': legal_req.description,
                    'citation': legal_req.citation,
                    'suggested_action': match.get('suggested_action', 'Gather more information')
                })
        
        # Calculate satisfaction
        if legal_requirements:
            satisfaction_ratio = result['satisfied_requirements'] / len(legal_requirements)
            result['satisfied'] = satisfaction_ratio >= 1.0
            result['confidence'] = satisfaction_ratio
        else:
            result['satisfied'] = True
            result['confidence'] = 1.0
        
        return result
    
    def _check_requirement_satisfied(self,
                                    legal_req: LegalElement,
                                    claim_node: DependencyNode,
                                    knowledge_graph: KnowledgeGraph,
                                    dependency_graph: DependencyGraph) -> Dict[str, Any]:
        """
        Check if a legal requirement is satisfied by complaint facts.
        
        This combines:
        - Symbolic matching: Check if dependency graph shows requirement as satisfied
        - Semantic matching: Use LLM to check if facts in knowledge graph satisfy requirement
        """
        result = {
            'requirement_name': legal_req.name,
            'satisfied': False,
            'confidence': 0.0,
            'evidence': []
        }
        
        # 1. Symbolic check: Is there a corresponding requirement node?
        dep_requirements = dependency_graph.get_dependencies_for_node(
            claim_node.id, direction='incoming'
        )
        
        for dep in dep_requirements:
            req_node = dependency_graph.get_node(dep.source_id)
            if req_node and self._requirement_matches(legal_req, req_node):
                if req_node.satisfied:
                    result['satisfied'] = True
                    result['confidence'] = req_node.confidence
                    result['evidence'].append(f"Requirement node '{req_node.name}' is satisfied")
                    return result
        
        # 2. Semantic check: Does knowledge graph contain supporting facts?
        semantic_match = self._semantic_requirement_check(
            legal_req, claim_node, knowledge_graph
        )
        
        if semantic_match['satisfied']:
            result['satisfied'] = True
            result['confidence'] = semantic_match['confidence']
            result['evidence'].extend(semantic_match['evidence'])
        else:
            result['suggested_action'] = semantic_match.get('suggested_action', '')
        
        return result
    
    def _requirement_matches(self, legal_req: LegalElement, 
                            req_node: DependencyNode) -> bool:
        """Check if a legal requirement matches a dependency node."""
        # Simple name matching (in production, use semantic similarity)
        legal_name = legal_req.name.lower()
        node_name = req_node.name.lower()
        
        # Check for keyword overlap
        legal_words = set(legal_name.split())
        node_words = set(node_name.split())
        overlap = legal_words & node_words
        
        return len(overlap) >= 2
    
    def _semantic_requirement_check(self,
                                   legal_req: LegalElement,
                                   claim_node: DependencyNode,
                                   knowledge_graph: KnowledgeGraph) -> Dict[str, Any]:
        """
        Use semantic/neural matching to check requirement satisfaction.
        
        This would use LLM in production to assess if facts support the requirement.
        """
        result = {
            'satisfied': False,
            'confidence': 0.0,
            'evidence': [],
            'suggested_action': ''
        }
        
        # Try to find the claim entity by name/type instead of ID
        # since dependency graph and knowledge graph use different ID schemes
        claim_entity = None
        claim_name = claim_node.attributes.get('claim_type', claim_node.name)
        
        # Search for matching entity by name or claim type
        for entity in knowledge_graph.entities.values():
            if (entity.entity_type == 'claim' and 
                (entity.name == claim_name or entity.name == claim_node.name)):
                claim_entity = entity
                break
        
        if not claim_entity:
            result['suggested_action'] = f"Provide more information about {claim_node.name}"
            return result
        
        # Check for supporting relationships using the found entity ID
        relationships = knowledge_graph.get_relationships_for_entity(claim_entity.id)
        supporting_rels = [r for r in relationships if r.relation_type == 'supported_by']
        
        if supporting_rels:
            result['satisfied'] = True
            result['confidence'] = 0.7  # Conservative estimate
            result['evidence'].append(f"Found {len(supporting_rels)} supporting relationships")
        else:
            result['suggested_action'] = f"Gather evidence for: {legal_req.name}"
        
        # If mediator available, use LLM for semantic matching
        if self.mediator:
            llm_result = self._llm_semantic_match(legal_req, claim_entity, knowledge_graph)
            if llm_result['confidence'] > result['confidence']:
                result.update(llm_result)
        
        return result
    
    def _llm_semantic_match(self, legal_req: LegalElement,
                           claim_entity: Entity,
                           knowledge_graph: KnowledgeGraph) -> Dict[str, Any]:
        """Use LLM for semantic matching (placeholder for LLM integration)."""
        # TODO: Implement LLM-based semantic matching
        # This would prompt the LLM to assess if facts satisfy the requirement
        return {
            'satisfied': False,
            'confidence': 0.0,
            'evidence': []
        }
    
    def generate_fact_finding_recommendations(self,
                                             matching_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate recommendations for additional fact-finding based on gaps.
        
        Args:
            matching_results: Results from match_claims_to_law()
            
        Returns:
            List of fact-finding recommendations
        """
        recommendations = []
        
        for gap in matching_results.get('gaps', []):
            rec = {
                'priority': 'high' if 'required' in gap.get('requirement_description', '').lower() else 'medium',
                'requirement': gap['requirement_name'],
                'description': gap['requirement_description'],
                'citation': gap.get('citation', ''),
                'action': gap.get('suggested_action', 'Gather more information'),
                'type': 'fact_finding'
            }
            recommendations.append(rec)
        
        # Sort by priority
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        recommendations.sort(key=lambda r: priority_order.get(r['priority'], 3))
        
        return recommendations
    
    def assess_claim_viability(self,
                              matching_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Assess overall viability of claims based on matching results.
        
        Args:
            matching_results: Results from match_claims_to_law()
            
        Returns:
            Viability assessment with recommendations
        """
        viability = {
            'overall_viability': 'unknown',
            'confidence': 0.0,
            'viable_claims': [],
            'weak_claims': [],
            'unviable_claims': [],
            'recommendations': []
        }
        
        for claim_result in matching_results.get('claims', []):
            confidence = claim_result.get('confidence', 0.0)
            
            if confidence >= 0.8:
                viability['viable_claims'].append(claim_result['claim_name'])
            elif confidence >= 0.5:
                viability['weak_claims'].append(claim_result['claim_name'])
            else:
                viability['unviable_claims'].append(claim_result['claim_name'])
        
        # Overall viability
        total_claims = matching_results.get('total_claims', 0)
        if total_claims > 0:
            viability_ratio = len(viability['viable_claims']) / total_claims
            viability['confidence'] = viability_ratio
            
            if viability_ratio >= 0.7:
                viability['overall_viability'] = 'strong'
            elif viability_ratio >= 0.4:
                viability['overall_viability'] = 'moderate'
            else:
                viability['overall_viability'] = 'weak'
        
        # Generate recommendations
        viability['recommendations'] = self.generate_fact_finding_recommendations(matching_results)
        
        return viability
