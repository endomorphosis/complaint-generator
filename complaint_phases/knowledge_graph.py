"""
Knowledge Graph Builder

Extracts entities, relationships, and facts from complaint text to build
a knowledge graph representation for denoising and evidence gathering.
"""

import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Entity:
    """Represents an entity in the knowledge graph."""
    id: str
    type: str  # person, organization, location, date, claim, fact, etc.
    name: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = "complaint"  # complaint, evidence, inference
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Relationship:
    """Represents a relationship between entities."""
    id: str
    source_id: str
    target_id: str
    relation_type: str  # caused_by, employed_by, located_at, occurred_on, etc.
    attributes: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = "complaint"
    
    def to_dict(self) -> dict:
        return asdict(self)


class KnowledgeGraph:
    """
    Knowledge graph representation of complaint information.
    
    Stores entities (people, organizations, facts, claims) and their relationships
    to enable reasoning, gap detection, and iterative denoising.
    """
    
    def __init__(self):
        self.entities: Dict[str, Entity] = {}
        self.relationships: Dict[str, Relationship] = {}
        self.metadata = {
            'created_at': datetime.utcnow().isoformat(),
            'last_updated': datetime.utcnow().isoformat(),
            'version': '1.0'
        }
    
    def add_entity(self, entity: Entity) -> str:
        """Add an entity to the graph."""
        self.entities[entity.id] = entity
        self._update_metadata()
        return entity.id
    
    def add_relationship(self, relationship: Relationship) -> str:
        """Add a relationship to the graph."""
        self.relationships[relationship.id] = relationship
        self._update_metadata()
        return relationship.id
    
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get an entity by ID."""
        return self.entities.get(entity_id)
    
    def get_relationships_for_entity(self, entity_id: str) -> List[Relationship]:
        """Get all relationships involving an entity."""
        return [
            rel for rel in self.relationships.values()
            if rel.source_id == entity_id or rel.target_id == entity_id
        ]
    
    def get_entities_by_type(self, entity_type: str) -> List[Entity]:
        """Get all entities of a specific type."""
        return [e for e in self.entities.values() if e.type == entity_type]
    
    def find_gaps(self) -> List[Dict[str, Any]]:
        """
        Identify gaps in the knowledge graph that need more information.
        
        Returns a list of gaps with suggested questions.
        """
        gaps = []
        
        # Check for entities with low confidence
        for entity in self.entities.values():
            if entity.confidence < 0.7:
                gaps.append({
                    'type': 'low_confidence_entity',
                    'entity_id': entity.id,
                    'entity_type': entity.type,
                    'entity_name': entity.name,
                    'confidence': entity.confidence,
                    'suggested_question': f"Can you provide more details about {entity.name}?"
                })
        
        # Check for incomplete relationships
        for entity in self.entities.values():
            rels = self.get_relationships_for_entity(entity.id)
            if len(rels) == 0 and entity.type in ['person', 'organization']:
                gaps.append({
                    'type': 'isolated_entity',
                    'entity_id': entity.id,
                    'entity_type': entity.type,
                    'entity_name': entity.name,
                    'suggested_question': f"What is the relationship between {entity.name} and the complaint?"
                })
        
        # Check for claims without evidence
        claims = self.get_entities_by_type('claim')
        for claim in claims:
            evidence_rels = [
                rel for rel in self.get_relationships_for_entity(claim.id)
                if rel.relation_type == 'supported_by'
            ]
            if len(evidence_rels) == 0:
                gaps.append({
                    'type': 'unsupported_claim',
                    'entity_id': claim.id,
                    'claim_name': claim.name,
                    'suggested_question': f"What evidence supports the claim: {claim.name}?"
                })
        
        return gaps
    
    def merge_with(self, other_graph: 'KnowledgeGraph'):
        """Merge another knowledge graph into this one."""
        for entity in other_graph.entities.values():
            if entity.id not in self.entities:
                self.add_entity(entity)
            else:
                # Update confidence if higher
                existing = self.entities[entity.id]
                if entity.confidence > existing.confidence:
                    existing.confidence = entity.confidence
                    existing.attributes.update(entity.attributes)
        
        for rel in other_graph.relationships.values():
            if rel.id not in self.relationships:
                self.add_relationship(rel)
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            'metadata': self.metadata,
            'entities': {eid: e.to_dict() for eid, e in self.entities.items()},
            'relationships': {rid: r.to_dict() for rid, r in self.relationships.items()}
        }
    
    def to_json(self, filepath: str):
        """Save to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Knowledge graph saved to {filepath}")
    
    @classmethod
    def from_dict(cls, data: dict) -> 'KnowledgeGraph':
        """Deserialize from dictionary."""
        graph = cls()
        graph.metadata = data['metadata']
        
        for eid, edata in data['entities'].items():
            entity = Entity(**edata)
            graph.entities[eid] = entity
        
        for rid, rdata in data['relationships'].items():
            rel = Relationship(**rdata)
            graph.relationships[rid] = rel
        
        return graph
    
    @classmethod
    def from_json(cls, filepath: str) -> 'KnowledgeGraph':
        """Load from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        logger.info(f"Knowledge graph loaded from {filepath}")
        return cls.from_dict(data)
    
    def _update_metadata(self):
        """Update last_updated timestamp."""
        self.metadata['last_updated'] = datetime.utcnow().isoformat()
    
    def summary(self) -> Dict[str, Any]:
        """Get a summary of the knowledge graph."""
        entity_counts = {}
        for entity in self.entities.values():
            entity_counts[entity.type] = entity_counts.get(entity.type, 0) + 1
        
        rel_counts = {}
        for rel in self.relationships.values():
            rel_counts[rel.relation_type] = rel_counts.get(rel.relation_type, 0) + 1
        
        return {
            'total_entities': len(self.entities),
            'total_relationships': len(self.relationships),
            'entity_types': entity_counts,
            'relationship_types': rel_counts,
            'gaps': len(self.find_gaps())
        }


class KnowledgeGraphBuilder:
    """
    Builds knowledge graphs from complaint text using LLM extraction.
    
    This builder uses the mediator's LLM backend to extract entities and
    relationships from text, progressively building a knowledge graph.
    """
    
    def __init__(self, mediator=None):
        self.mediator = mediator
        self.entity_counter = 0
        self.relationship_counter = 0
    
    def build_from_text(self, text: str) -> KnowledgeGraph:
        """
        Build a knowledge graph from complaint text.
        
        Args:
            text: The complaint text to analyze
            
        Returns:
            A KnowledgeGraph instance
        """
        graph = KnowledgeGraph()
        
        # Extract entities
        entities = self._extract_entities(text)
        for entity_data in entities:
            entity = Entity(
                id=self._get_entity_id(),
                type=entity_data['type'],
                name=entity_data['name'],
                attributes=entity_data.get('attributes', {}),
                confidence=entity_data.get('confidence', 0.8),
                source='complaint'
            )
            graph.add_entity(entity)
        
        # Extract relationships
        relationships = self._extract_relationships(text, graph)
        for rel_data in relationships:
            rel = Relationship(
                id=self._get_relationship_id(),
                source_id=rel_data['source_id'],
                target_id=rel_data['target_id'],
                relation_type=rel_data['type'],
                attributes=rel_data.get('attributes', {}),
                confidence=rel_data.get('confidence', 0.8),
                source='complaint'
            )
            graph.add_relationship(rel)
        
        logger.info(f"Built knowledge graph: {graph.summary()}")
        return graph
    
    def _extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract entities from text using LLM or rule-based extraction.
        
        This is a simplified implementation. In production, this would use
        the mediator's LLM backend to do sophisticated entity extraction.
        """
        entities = []
        
        # For now, use simple keyword-based extraction
        # In production, this would use LLM prompts like:
        # "Extract all people, organizations, dates, locations, and claims from: {text}"
        
        # Extract simple entities (this is a placeholder)
        if 'discrimination' in text.lower():
            entities.append({
                'type': 'claim',
                'name': 'Discrimination Claim',
                'attributes': {'claim_type': 'discrimination'},
                'confidence': 0.9
            })
        
        if 'employer' in text.lower():
            entities.append({
                'type': 'organization',
                'name': 'Employer',
                'attributes': {},
                'confidence': 0.7
            })
        
        if 'employee' in text.lower() or 'complainant' in text.lower():
            entities.append({
                'type': 'person',
                'name': 'Complainant',
                'attributes': {'role': 'complainant'},
                'confidence': 0.9
            })
        
        # Use LLM if available
        if self.mediator:
            llm_entities = self._llm_extract_entities(text)
            entities.extend(llm_entities)

        # Fallback: ensure we have at least one claim to drive downstream graphs.
        # Many parts of the pipeline (dependency graph, denoiser questions) assume
        # there's at least one claim-like entity.
        has_claim = any(e.get("type") == "claim" for e in entities if isinstance(e, dict))
        if not has_claim:
            snippet = (text or "").strip().splitlines()[0:1]
            description = snippet[0].strip() if snippet else ""
            if len(description) > 240:
                description = description[:237] + "..."
            entities.append(
                {
                    "type": "claim",
                    "name": "Complaint Claim",
                    "attributes": {
                        "claim_type": "unknown",
                        "description": description,
                    },
                    "confidence": 0.5,
                }
            )
        
        return entities
    
    def _extract_relationships(self, text: str, graph: KnowledgeGraph) -> List[Dict[str, Any]]:
        """
        Extract relationships between entities.
        
        This is a simplified implementation. In production, this would use
        the mediator's LLM backend.
        """
        relationships = []
        
        # Find entities to relate
        persons = graph.get_entities_by_type('person')
        orgs = graph.get_entities_by_type('organization')
        claims = graph.get_entities_by_type('claim')
        
        # Create employment relationships
        for person in persons:
            for org in orgs:
                if (
                    'employer' in org.name.lower()
                    or org.attributes.get('role') == 'respondent'
                ):
                    relationships.append({
                        'source_id': person.id,
                        'target_id': org.id,
                        'type': 'employed_by',
                        'confidence': 0.7
                    })
        
        # Link claims to complainants
        for claim in claims:
            for person in persons:
                if 'complainant' in person.attributes.get('role', '').lower():
                    relationships.append({
                        'source_id': person.id,
                        'target_id': claim.id,
                        'type': 'makes_claim',
                        'confidence': 0.9
                    })
        
        # Use LLM if available
        if self.mediator:
            llm_rels = self._llm_extract_relationships(text, graph)
            for rel in llm_rels:
                if not isinstance(rel, dict):
                    continue
                if rel.get('source_id') and rel.get('target_id') and rel.get('type'):
                    relationships.append(rel)
        
        unique_relationships = {}
        for rel in relationships:
            key = (rel.get('source_id'), rel.get('target_id'), rel.get('type'))
            if not all(key):
                continue
            current = unique_relationships.get(key)
            if current is None or rel.get('confidence', 0.0) > current.get('confidence', 0.0):
                unique_relationships[key] = rel

        return list(unique_relationships.values())
    
    def _llm_extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """Use LLM to extract entities (placeholder for LLM integration)."""
        # TODO: Implement LLM-based extraction
        return []
    
    def _llm_extract_relationships(self, text: str, graph: KnowledgeGraph) -> List[Dict[str, Any]]:
        """Use LLM to extract relationships (placeholder for LLM integration)."""
        # TODO: Implement LLM-based extraction
        return []
    
    def _get_entity_id(self) -> str:
        """Generate unique entity ID."""
        self.entity_counter += 1
        return f"entity_{self.entity_counter}"
    
    def _get_relationship_id(self) -> str:
        """Generate unique relationship ID."""
        self.relationship_counter += 1
        return f"rel_{self.relationship_counter}"
