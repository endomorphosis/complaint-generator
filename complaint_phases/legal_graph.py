"""
Legal Graph Builder

Creates graph representations of legal requirements, statutes, and rules
to enable neurosymbolic matching against complaint graphs.
"""

import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class LegalElement:
    """Represents a legal element or requirement."""
    id: str
    element_type: str  # statute, regulation, case_law, element, requirement
    name: str
    description: str = ""
    citation: str = ""
    jurisdiction: str = ""
    required: bool = True
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LegalRelation:
    """Represents a relationship between legal elements."""
    id: str
    source_id: str
    target_id: str
    relation_type: str  # requires, implies, contradicts, supersedes, cites
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)


class LegalGraph:
    """
    Graph representation of legal requirements and their relationships.
    
    Stores legal elements (statutes, regulations, requirements) and their
    relationships to enable matching against complaint facts.
    """
    
    def __init__(self):
        self.elements: Dict[str, LegalElement] = {}
        self.relations: Dict[str, LegalRelation] = {}
        self.metadata = {
            'created_at': datetime.now(timezone.utc).isoformat(),
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'version': '1.0'
        }
    
    def add_element(self, element: LegalElement) -> str:
        """Add a legal element to the graph."""
        self.elements[element.id] = element
        self._update_metadata()
        return element.id
    
    def add_relation(self, relation: LegalRelation) -> str:
        """Add a legal relation to the graph."""
        self.relations[relation.id] = relation
        self._update_metadata()
        return relation.id
    
    def get_element(self, element_id: str) -> Optional[LegalElement]:
        """Get a legal element by ID."""
        return self.elements.get(element_id)
    
    def get_relations_for_element(self, element_id: str) -> List[LegalRelation]:
        """Get all relations involving an element."""
        return [
            rel for rel in self.relations.values()
            if rel.source_id == element_id or rel.target_id == element_id
        ]
    
    def get_elements_by_type(self, element_type: str) -> List[LegalElement]:
        """Get all elements of a specific type."""
        return [e for e in self.elements.values() if e.element_type == element_type]
    
    def get_requirements_for_claim_type(self, claim_type: str) -> List[LegalElement]:
        """
        Get all legal requirements for a specific claim type.
        
        Args:
            claim_type: Type of legal claim (e.g., 'discrimination', 'wrongful_termination')
            
        Returns:
            List of required legal elements (both 'requirement' and 'procedural_requirement')
        """
        requirements = []
        
        # Find elements tagged with this claim type
        # Include both regular requirements and procedural requirements
        for element in self.elements.values():
            if element.element_type in ('requirement', 'procedural_requirement'):
                applicable_claims = element.attributes.get('applicable_claim_types', [])
                if claim_type in applicable_claims:
                    requirements.append(element)
        
        return requirements
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            'metadata': self.metadata,
            'elements': {eid: e.to_dict() for eid, e in self.elements.items()},
            'relations': {rid: r.to_dict() for rid, r in self.relations.items()}
        }
    
    def to_json(self, filepath: str):
        """Save to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Legal graph saved to {filepath}")
    
    @classmethod
    def from_dict(cls, data: dict) -> 'LegalGraph':
        """Deserialize from dictionary."""
        graph = cls()
        graph.metadata = data['metadata']
        
        for eid, edata in data['elements'].items():
            element = LegalElement(**edata)
            graph.elements[eid] = element
        
        for rid, rdata in data['relations'].items():
            rel = LegalRelation(**rdata)
            graph.relations[rid] = rel
        
        return graph
    
    @classmethod
    def from_json(cls, filepath: str) -> 'LegalGraph':
        """Load from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        logger.info(f"Legal graph loaded from {filepath}")
        return cls.from_dict(data)
    
    def _update_metadata(self):
        """Update last_updated timestamp."""
        self.metadata['last_updated'] = datetime.now(timezone.utc).isoformat()
    
    def summary(self) -> Dict[str, Any]:
        """Get a summary of the legal graph."""
        element_counts = {}
        for element in self.elements.values():
            element_counts[element.element_type] = element_counts.get(element.element_type, 0) + 1
        
        rel_counts = {}
        for rel in self.relations.values():
            rel_counts[rel.relation_type] = rel_counts.get(rel.relation_type, 0) + 1
        
        return {
            'total_elements': len(self.elements),
            'total_relations': len(self.relations),
            'element_types': element_counts,
            'relation_types': rel_counts
        }


    # ------------------------------------------------------------------ #
    # Batch 207: Legal graph analysis and statistics methods             #
    # ------------------------------------------------------------------ #

    def total_elements(self) -> int:
        """Return total number of legal elements in the graph.

        Returns:
            Count of elements.
        """
        return len(self.elements)

    def total_relations(self) -> int:
        """Return total number of legal relations in the graph.

        Returns:
            Count of relations.
        """
        return len(self.relations)

    def element_type_frequency(self) -> dict:
        """Count frequency of each element type.

        Returns:
            Dict mapping element types to counts.
        """
        type_counts: dict = {}
        for element in self.elements.values():
            etype = element.element_type
            type_counts[etype] = type_counts.get(etype, 0) + 1
        return type_counts

    def most_common_element_type(self) -> str:
        """Identify the most common element type.

        Returns:
            Most frequent element type, or 'none' if no elements.
        """
        freq = self.element_type_frequency()
        if not freq:
            return 'none'
        return max(freq.items(), key=lambda x: x[1])[0]

    def relation_type_frequency(self) -> dict:
        """Count frequency of each relation type.

        Returns:
            Dict mapping relation types to counts.
        """
        type_counts: dict = {}
        for relation in self.relations.values():
            rtype = relation.relation_type
            type_counts[rtype] = type_counts.get(rtype, 0) + 1
        return type_counts

    def most_connected_element(self) -> str:
        """Find element ID with the most relations.

        Returns:
            Element ID with most relations, or 'none' if no elements.
        """
        if not self.elements:
            return 'none'
        
        connection_counts: dict = {}
        for element_id in self.elements.keys():
            connection_counts[element_id] = len(self.get_relations_for_element(element_id))
        
        if not connection_counts:
            return 'none'
        
        return max(connection_counts.items(), key=lambda x: x[1])[0]

    def average_relations_per_element(self) -> float:
        """Calculate average number of relations per element.

        Returns:
            Mean relation count, or 0.0 if no elements.
        """
        if not self.elements:
            return 0.0
        total_connections = sum(
            len(self.get_relations_for_element(eid))
            for eid in self.elements.keys()
        )
        # Each relation is counted twice (source and target), so divide by 2
        return (total_connections / 2) / len(self.elements)

    def requirements_coverage(self) -> dict:
        """Analyze requirement coverage across claim types.

        Returns:
            Dict with 'total_requirements', 'claim_types_covered', 'avg_requirements_per_claim'.
        """
        requirements = [e for e in self.elements.values() 
                       if e.element_type in ('requirement', 'procedural_requirement')]
        
        claim_types_with_reqs: set = set()
        for req in requirements:
            applicable_claims = req.attributes.get('applicable_claim_types', [])
            claim_types_with_reqs.update(applicable_claims)
        
        avg_per_claim = 0.0
        if claim_types_with_reqs:
            total_req_mappings = sum(
                len(req.attributes.get('applicable_claim_types', []))
                for req in requirements
            )
            avg_per_claim = total_req_mappings / len(claim_types_with_reqs)
        
        return {
            'total_requirements': len(requirements),
            'claim_types_covered': len(claim_types_with_reqs),
            'avg_requirements_per_claim': avg_per_claim
        }

    def elements_with_citations(self) -> int:
        """Count elements that have citation information.

        Returns:
            Number of elements with non-empty citation field.
        """
        return sum(
            1 for element in self.elements.values()
            if element.citation and len(element.citation) > 0
        )

    def graph_density(self) -> float:
        """Calculate graph density (ratio of existing to possible relations).

        Returns:
            Density ratio (0.0-1.0), or 0.0 if fewer than 2 elements.
        """
        n = len(self.elements)
        if n < 2:
            return 0.0
        
        max_possible_relations = n * (n - 1) / 2  # Undirected graph
        actual_relations = len(self.relations)
        
        return actual_relations / max_possible_relations


class LegalGraphBuilder:
    """
    Builds legal requirement graphs from statutes, regulations, and case law.
    
    Creates structured graph representations of legal requirements that can
    be matched against complaint facts.
    """
    
    def __init__(self, mediator=None):
        self.mediator = mediator
        self.element_counter = 0
        self.relation_counter = 0
    
    def build_from_statutes(self, statutes: List[Dict[str, Any]],
                           claim_types: List[str]) -> LegalGraph:
        """
        Build a legal graph from statutes and claim types.
        
        Args:
            statutes: List of statute dictionaries
            claim_types: List of claim types these statutes apply to
            
        Returns:
            A LegalGraph instance
        """
        graph = LegalGraph()
        
        # Add statutes as elements
        statute_elements = []
        for statute in statutes:
            element = LegalElement(
                id=self._get_element_id(),
                element_type='statute',
                name=statute.get('name', 'Unnamed Statute'),
                description=statute.get('description', ''),
                citation=statute.get('citation', ''),
                jurisdiction=statute.get('jurisdiction', 'US'),
                attributes={'text': statute.get('text', '')}
            )
            graph.add_element(element)
            statute_elements.append(element)
        
        # Extract requirements from statutes
        for statute_elem in statute_elements:
            requirements = self._extract_requirements_from_statute(statute_elem, claim_types)
            
            for req_data in requirements:
                req_element = LegalElement(
                    id=self._get_element_id(),
                    element_type='requirement',
                    name=req_data['name'],
                    description=req_data.get('description', ''),
                    citation=statute_elem.citation,
                    required=req_data.get('required', True),
                    attributes={
                        'applicable_claim_types': claim_types,
                        'source_statute': statute_elem.id
                    }
                )
                graph.add_element(req_element)
                
                # Create relation: statute provides requirement
                rel = LegalRelation(
                    id=self._get_relation_id(),
                    source_id=statute_elem.id,
                    target_id=req_element.id,
                    relation_type='provides'
                )
                graph.add_relation(rel)
        
        logger.info(f"Built legal graph: {graph.summary()}")
        return graph
    
    def build_rules_of_procedure(self, jurisdiction: str = 'federal') -> LegalGraph:
        """
        Build a legal graph for rules of civil procedure.
        
        Args:
            jurisdiction: 'federal' or specific state
            
        Returns:
            A LegalGraph with procedural requirements
        """
        graph = LegalGraph()
        
        # Common procedural requirements (simplified)
        procedural_reqs = [
            {
                'name': 'Statement of Jurisdiction',
                'description': 'Must state the basis for the court\'s jurisdiction',
                'rule': 'FRCP 8(a)(1)'
            },
            {
                'name': 'Statement of Claim',
                'description': 'Must contain a short and plain statement of the claim showing entitlement to relief',
                'rule': 'FRCP 8(a)(2)'
            },
            {
                'name': 'Demand for Relief',
                'description': 'Must state the relief sought',
                'rule': 'FRCP 8(a)(3)'
            },
            {
                'name': 'Plausible Claim',
                'description': 'Facts must plausibly suggest entitlement to relief',
                'rule': 'Twombly/Iqbal Standard'
            }
        ]
        
        for req_data in procedural_reqs:
            element = LegalElement(
                id=self._get_element_id(),
                element_type='procedural_requirement',
                name=req_data['name'],
                description=req_data['description'],
                citation=req_data['rule'],
                jurisdiction=jurisdiction,
                required=True,
                attributes={'category': 'civil_procedure'}
            )
            graph.add_element(element)
        
        logger.info(f"Built procedural rules graph: {graph.summary()}")
        return graph
    
    def _extract_requirements_from_statute(self, statute: LegalElement,
                                          claim_types: List[str]) -> List[Dict[str, Any]]:
        """
        Extract legal requirements from a statute.
        
        This is a simplified implementation. In production, this would use
        LLM to parse statute text and extract elements.
        """
        requirements = []
        
        # Basic element extraction (placeholder)
        # In production, use LLM to analyze statute text
        
        # Example: discrimination statutes typically require these elements
        if 'discrimination' in str(claim_types).lower():
            requirements.extend([
                {
                    'name': 'Protected Class Membership',
                    'description': 'Plaintiff must be member of protected class',
                    'required': True
                },
                {
                    'name': 'Adverse Action',
                    'description': 'Plaintiff suffered adverse employment/housing action',
                    'required': True
                },
                {
                    'name': 'Causal Connection',
                    'description': 'Protected class status was motivating factor',
                    'required': True
                }
            ])
        
        return requirements
    
    def _get_element_id(self) -> str:
        """Generate unique element ID."""
        self.element_counter += 1
        return f"legal_elem_{self.element_counter}"
    
    def _get_relation_id(self) -> str:
        """Generate unique relation ID."""
        self.relation_counter += 1
        return f"legal_rel_{self.relation_counter}"
