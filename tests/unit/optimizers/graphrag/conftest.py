"""Shared fixtures for GraphRAG optimizer unit tests."""

from typing import Any, Dict

import pytest


@pytest.fixture
def create_test_ontology():
    """Factory fixture for lightweight ontology dictionaries used in batch tests."""

    def _build(
        entity_count: int = 5,
        relationship_count: int = 3,
        *,
        entity_prefix: str = "e",
        relationship_prefix: str = "r",
        include_ontology_id: bool = True,
        ontology_id: str = "test_ontology",
        domain: str = "legal",
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        entities = [
            {
                "id": f"{entity_prefix}{i}",
                "text": f"Entity{i}",
                "type": "Person" if i % 2 == 0 else "Organization",
                "confidence": 0.6 + (i * 0.08),
            }
            for i in range(entity_count)
        ]
        relationships = [
            {
                "id": f"{relationship_prefix}{i}",
                "source_id": f"{entity_prefix}{i % entity_count}",
                "target_id": f"{entity_prefix}{(i + 1) % entity_count}",
                "type": "works_for",
                "confidence": 0.75 + (i * 0.05),
            }
            for i in range(relationship_count)
        ]
        ontology = {
            "entities": entities,
            "relationships": relationships,
            "metadata": {"domain": domain, **(metadata or {})},
        }

        if include_ontology_id:
            ontology["id"] = ontology_id

        return ontology

    return _build
