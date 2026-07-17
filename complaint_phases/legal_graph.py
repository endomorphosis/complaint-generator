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


    # ------------------------------------------------------------------ #
    # Batch 222: Legal graph analysis and statistics methods             #
    # ------------------------------------------------------------------ #

    def element_jurisdiction_frequency(self) -> dict:
        """Count frequency of elements by jurisdiction.

        Returns:
            Dict mapping jurisdiction to element counts.
        """
        counts: dict = {}
        for element in self.elements.values():
            jurisdiction = element.jurisdiction or ""
            counts[jurisdiction] = counts.get(jurisdiction, 0) + 1
        return counts

    def required_elements_count(self) -> int:
        """Count required elements in the graph.

        Returns:
            Number of elements marked as required.
        """
        return sum(1 for element in self.elements.values() if element.required)

    def optional_elements_count(self) -> int:
        """Count optional (non-required) elements in the graph.

        Returns:
            Number of elements marked as optional.
        """
        return sum(1 for element in self.elements.values() if not element.required)

    def elements_with_attributes_count(self) -> int:
        """Count elements that have non-empty attributes.

        Returns:
            Number of elements with attributes.
        """
        return sum(1 for element in self.elements.values() if element.attributes)

    def elements_missing_citation_count(self) -> int:
        """Count elements missing citation information.

        Returns:
            Number of elements with empty citation fields.
        """
        return sum(1 for element in self.elements.values() if not element.citation)

    def relation_type_set(self) -> List[str]:
        """Return sorted list of unique relation types.

        Returns:
            Sorted list of relation type strings.
        """
        return sorted({rel.relation_type for rel in self.relations.values()})

    def average_elements_per_type(self) -> float:
        """Calculate average number of elements per element type.

        Returns:
            Mean elements per type, or 0.0 if no elements.
        """
        if not self.elements:
            return 0.0
        type_counts = self.element_type_frequency()
        if not type_counts:
            return 0.0
        return len(self.elements) / len(type_counts)

    def elements_by_jurisdiction(self, jurisdiction: str) -> List[LegalElement]:
        """Get elements that match a jurisdiction string.

        Args:
            jurisdiction: Jurisdiction value to match

        Returns:
            List of matching legal elements.
        """
        return [
            element for element in self.elements.values()
            if element.jurisdiction == jurisdiction
        ]

    def relation_count_for_element(self, element_id: str) -> int:
        """Count relations involving a specific element.

        Args:
            element_id: Element identifier

        Returns:
            Number of relations involving the element.
        """
        return len(self.get_relations_for_element(element_id))

    def claim_type_requirement_counts(self) -> dict:
        """Count requirements per claim type.

        Returns:
            Dict mapping claim type to requirement counts.
        """
        counts: dict = {}
        for element in self.elements.values():
            if element.element_type not in ('requirement', 'procedural_requirement'):
                continue
            claim_types = element.attributes.get('applicable_claim_types', [])
            for claim_type in claim_types:
                counts[claim_type] = counts.get(claim_type, 0) + 1
        return counts


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

    # ------------------------------------------------------------------ #
    # W9.4: Authority graph integration                                   #
    # ------------------------------------------------------------------ #

    _MAX_RULE_NAME_LENGTH = 120

    def build_from_authorities(
        self,
        authorities: List[Dict[str, Any]],
        claim_elements: Optional[List[Dict[str, Any]]] = None,
    ) -> 'LegalGraph':
        """Build a LegalGraph from stored authority records with treatment edges.

        Creates three layers of graph structure:
        1. Authority elements (``authority_source``) for each record.
        2. Authority-to-authority treatment edges (``supports``, ``adverse``,
           ``limits``, ``distinguishes``, ``questioned``, ``superseded``,
           ``good_law_unconfirmed``) derived from each authority's
           ``treatment_records`` or ``treatment_summary``.
        3. Rule-to-claim-element edges (``governs``) linking extracted rule
           candidates to the claim elements they cover.

        Args:
            authorities: Authority dicts as returned by legal-authority hooks.
                Each dict should have at minimum ``authority_id`` or ``id``,
                ``name`` or ``title``, and optionally ``treatment_records``,
                ``treatment_summary``, and ``rule_candidates``.
            claim_elements: Optional list of claim-element dicts with
                ``element_id`` / ``claim_element_id`` and ``element_text`` /
                ``claim_element_text``.  When provided, rule candidates whose
                ``claim_element_id`` matches will have a ``governs`` edge added.

        Returns:
            A populated :class:`LegalGraph` instance.
        """
        graph = LegalGraph()

        # Index claim elements by ID for fast lookup
        element_id_to_graph_id: Dict[str, str] = {}
        for elem in claim_elements or []:
            if not isinstance(elem, dict):
                continue
            elem_id = str(elem.get('element_id') or elem.get('claim_element_id') or '').strip()
            elem_text = str(
                elem.get('element_text') or elem.get('claim_element_text') or ''
            ).strip()
            if not elem_id and not elem_text:
                continue
            node = LegalElement(
                id=self._get_element_id(),
                element_type='claim_element',
                name=elem_text or f'Element {elem_id}',
                description=elem_text,
                attributes={'source_element_id': elem_id},
            )
            graph.add_element(node)
            if elem_id:
                element_id_to_graph_id[elem_id] = node.id

        # Build authority nodes and treatment edges
        authority_node_ids: Dict[str, str] = {}
        for authority in authorities or []:
            if not isinstance(authority, dict):
                continue
            raw_id = str(
                authority.get('authority_id')
                or authority.get('id')
                or ''
            ).strip()
            name = str(
                authority.get('name') or authority.get('title') or authority.get('authority_name') or ''
            ).strip() or raw_id or 'unknown_authority'
            citation = str(authority.get('citation') or authority.get('cite') or '').strip()
            jurisdiction = str(authority.get('jurisdiction') or '').strip()
            authority_family = str(
                authority.get('authority_family') or authority.get('source_type') or ''
            ).strip()

            node = LegalElement(
                id=self._get_element_id(),
                element_type='authority_source',
                name=name,
                citation=citation,
                jurisdiction=jurisdiction,
                attributes={
                    'source_authority_id': raw_id,
                    'authority_family': authority_family,
                },
            )
            graph.add_element(node)
            if raw_id:
                authority_node_ids[raw_id] = node.id

        # Second pass: add treatment edges and rule candidate edges now that all
        # authority nodes are registered (so cross-authority treatment targets resolve).
        for authority in authorities or []:
            if not isinstance(authority, dict):
                continue
            raw_id = str(
                authority.get('authority_id') or authority.get('id') or ''
            ).strip()
            source_node_id = authority_node_ids.get(raw_id)
            if not source_node_id:
                continue

            # Treatment edges: authority → authority
            self._add_treatment_edges(graph, source_node_id, authority, authority_node_ids)

            # Rule candidate → claim element edges
            self._add_rule_candidate_edges(
                graph, source_node_id, authority, element_id_to_graph_id
            )

        logger.debug(
            "built authority legal graph: %d elements, %d relations",
            len(graph.elements),
            len(graph.relations),
        )
        return graph

    def _add_treatment_edges(
        self,
        graph: 'LegalGraph',
        source_node_id: str,
        authority: Dict[str, Any],
        authority_node_ids: Dict[str, str],
    ) -> None:
        """Add authority-to-authority treatment relation edges.

        Reads ``treatment_records`` (list of dicts with ``treatment_type``,
        ``treated_authority_id``) or ``treatment_summary`` from *authority* and
        inserts a :class:`LegalRelation` for each valid treatment pair.
        """
        _VALID_TREATMENT_TYPES = {
            'supports', 'adverse', 'limits', 'distinguishes',
            'questioned', 'superseded', 'good_law_unconfirmed',
        }
        treatment_records = authority.get('treatment_records')
        if not isinstance(treatment_records, list):
            summary = authority.get('treatment_summary') if isinstance(authority.get('treatment_summary'), dict) else {}
            treatment_records = summary.get('records', []) if isinstance(summary, dict) else []
        for record in treatment_records or []:
            if not isinstance(record, dict):
                continue
            treatment_type = str(record.get('treatment_type') or record.get('type') or '').strip()
            if treatment_type not in _VALID_TREATMENT_TYPES:
                continue
            treated_id = str(record.get('treated_authority_id') or record.get('target_id') or '').strip()
            target_node_id = authority_node_ids.get(treated_id)
            if not target_node_id:
                continue
            confidence = float(record.get('treatment_confidence', 0.0) or 0.0)
            rel = LegalRelation(
                id=self._get_relation_id(),
                source_id=source_node_id,
                target_id=target_node_id,
                relation_type=treatment_type,
                attributes={
                    'confidence': confidence,
                    'explanation': str(record.get('treatment_explanation') or ''),
                    'treatment_date': str(record.get('treatment_date') or ''),
                    'treatment_source': str(record.get('treatment_source') or ''),
                },
            )
            graph.add_relation(rel)

    def _add_rule_candidate_edges(
        self,
        graph: 'LegalGraph',
        authority_node_id: str,
        authority: Dict[str, Any],
        element_id_to_graph_id: Dict[str, str],
    ) -> None:
        """Add rule-to-claim-element ``governs`` edges from rule candidates.

        Reads ``rule_candidates`` from *authority*.  For each candidate, adds a
        ``rule_candidate`` element and, when the candidate's
        ``claim_element_id`` is in *element_id_to_graph_id*, adds a
        ``governs`` edge from the rule to the matched claim-element node.
        An ``extracted_from`` edge is always added from the rule candidate to the
        authority node (rule *extracted_from* authority).
        """
        for candidate in authority.get('rule_candidates') or []:
            if not isinstance(candidate, dict):
                continue
            rule_text = str(candidate.get('rule_text') or candidate.get('text') or '').strip()
            if not rule_text:
                continue
            rule_type = str(candidate.get('rule_type') or 'rule').strip()
            confidence = float(candidate.get('extraction_confidence', 0.0) or 0.0)
            rule_node = LegalElement(
                id=self._get_element_id(),
                element_type='rule_candidate',
                name=rule_text[:self._MAX_RULE_NAME_LENGTH],
                description=rule_text,
                attributes={
                    'rule_type': rule_type,
                    'extraction_confidence': confidence,
                    'source_authority_node': authority_node_id,
                },
            )
            graph.add_element(rule_node)
            # rule candidate extracted_from authority (rule → authority direction)
            graph.add_relation(
                LegalRelation(
                    id=self._get_relation_id(),
                    source_id=rule_node.id,
                    target_id=authority_node_id,
                    relation_type='extracted_from',
                    attributes={'confidence': confidence},
                )
            )
            # rule candidate → claim element (governs) when linked
            claim_element_id = str(
                candidate.get('claim_element_id') or candidate.get('element_id') or ''
            ).strip()
            target_elem_graph_id = element_id_to_graph_id.get(claim_element_id)
            if target_elem_graph_id:
                graph.add_relation(
                    LegalRelation(
                        id=self._get_relation_id(),
                        source_id=rule_node.id,
                        target_id=target_elem_graph_id,
                        relation_type='governs',
                        attributes={
                            'confidence': confidence,
                            'rule_type': rule_type,
                        },
                    )
                )
