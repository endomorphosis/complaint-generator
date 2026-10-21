"""Contract: factual, authority, rule, requirement, and support-link namespaces stay distinct."""

from complaint_phases.dependency_graph import DependencyGraph, DependencyGraphBuilder
from complaint_phases.knowledge_graph import KnowledgeGraphBuilder
from complaint_phases.legal_graph import LegalGraphBuilder
from integrations.ipfs_datasets.graphs import (
    DISTINCT_GRAPH_RECORD_KINDS,
    build_namespaced_support_link,
    extract_graph_from_text,
    mint_graph_record_id,
    record_kind_from_id,
    resolve_duplicate_entities,
)


def test_record_kinds_use_distinct_id_prefixes():
    ids = [
        mint_graph_record_id(kind, "same-label", "same-source")
        for kind in DISTINCT_GRAPH_RECORD_KINDS
    ]
    prefixes = [record_kind_from_id(record_id) for record_id in ids]
    assert prefixes == list(DISTINCT_GRAPH_RECORD_KINDS)
    assert len(set(ids)) == len(ids)
    assert len(set(prefixes)) == len(prefixes)


def test_legal_passage_is_not_a_complainant_fact():
    passage = "The employer shall not discharge an employee for opposing an unlawful practice."
    provenance = {"source_id": "statute-42-usc-2000e", "source_type": "statute", "citation": "42 USC 2000e-3"}
    extracted = extract_graph_from_text(
        passage,
        source_id="statute-42-usc-2000e",
        metadata={"source_kind": "law", "passage_role": "authority_source", "provenance": provenance, "legal_passage": True},
    )
    kinds = {entity["type"] for entity in extracted["entities"]}
    assert "fact" not in kinds
    assert "factual_assertion" not in kinds
    legal_nodes = [entity for entity in extracted["entities"] if entity["type"] == "authority_source"]
    assert legal_nodes
    assert all(entity["attributes"]["about_complainant"] is False for entity in legal_nodes)
    assert all(entity["attributes"]["provenance"]["source_id"] == "statute-42-usc-2000e" for entity in legal_nodes)

    projected = LegalGraphBuilder().project_legal_passage({
        "text": passage,
        "passage_role": "authority_source",
        "provenance": provenance,
    })
    assert projected.element_type == "authority_source"
    assert projected.id.startswith("authority_source:")
    assert projected.attributes["about_complainant"] is False
    assert projected.attributes["provenance"]["citation"] == "42 USC 2000e-3"

    graph = KnowledgeGraphBuilder().build_from_text(
        passage,
        source_context={"source_kind": "law", "source_id": "statute-42-usc-2000e", "legal_passage": True},
        extracted_entities=[{"name": passage, "type": "fact", "attributes": {"description": passage}}],
    )
    assert graph.entities
    for entity in graph.entities.values():
        assert entity.type == "legal_text"
        assert entity.source == "legal"
        assert entity.id.startswith("authority_source:")
        assert entity.attributes["about_complainant"] is False
        envelope = entity.provenance["user_assertion"]
        assert envelope["assertion_status"] != "asserted"
        assert envelope["record_type"] == "legal_text"


def test_entity_dedup_does_not_merge_testimony_with_legal_norm():
    entities = [
        {"entity_id": "e-user", "name": "Equal Protection", "source_kind": "testimony"},
        {"entity_id": "e-law", "name": "equal protection", "source_kind": "law", "record_kind": "legal_requirement"},
        {"entity_id": "e-doc", "name": "Equal Protection", "source_kind": "document"},
    ]
    result = resolve_duplicate_entities(entities)
    assert result["entity_count"] == 2
    assert result["merged_count"] == 1
    by_namespace = {cluster["resolution_namespace"]: cluster for cluster in result["clusters"]}
    assert "e-law" in by_namespace["legal_norm"]["entity_ids"]
    assert "e-user" in by_namespace["user_testimony"]["entity_ids"]
    assert "e-doc" in by_namespace["user_testimony"]["entity_ids"]
    assert "e-law" not in by_namespace["user_testimony"]["entity_ids"]


def test_support_and_contradiction_links_keep_both_provenance_chains():
    fact_id = mint_graph_record_id("factual_assertion", "user-said-fired")
    rule_id = mint_graph_record_id("rule_candidate", "anti-retaliation")
    fact_provenance = {"source_id": "msg-1", "source_kind": "testimony", "span": "I was fired"}
    rule_provenance = {"source_id": "statute-42-usc-2000e", "source_kind": "law", "citation": "42 USC 2000e-3"}

    support = build_namespaced_support_link(
        factual_assertion_id=fact_id,
        rule_id=rule_id,
        relation="supports",
        factual_provenance=fact_provenance,
        rule_provenance=rule_provenance,
    )
    contradiction = build_namespaced_support_link(
        factual_assertion_id=fact_id,
        rule_id=rule_id,
        relation="contradicts",
        factual_provenance=fact_provenance,
        rule_provenance=rule_provenance,
    )
    assert support["link_type"] == "support_link"
    assert contradiction["link_type"] == "contradiction_link"
    assert support["link_id"] != contradiction["link_id"]
    assert support["factual_assertion_id"] == fact_id
    assert support["rule_id"] == rule_id
    assert record_kind_from_id(support["link_id"]) == "support_link"
    assert support["provenance_chains"]["factual_assertion"] == fact_provenance
    assert support["provenance_chains"]["rule"] == rule_provenance
    assert support["provenance_chains"]["factual_assertion"] is not support["provenance_chains"]["rule"]

    graph = DependencyGraph()
    stored = DependencyGraphBuilder().add_fact_rule_link(
        graph,
        factual_assertion_id=fact_id,
        rule_id=rule_id,
        relation="contradicts",
        factual_provenance=fact_provenance,
        rule_provenance=rule_provenance,
    )
    assert stored["link_id"] in graph.dependencies
    assert graph.dependencies[stored["link_id"]].source_id == fact_id
    assert graph.dependencies[stored["link_id"]].target_id == rule_id
    assert graph.nodes[fact_id].attributes["provenance"]["source_kind"] == "testimony"
    assert graph.nodes[rule_id].attributes["provenance"]["source_kind"] == "law"
    assert graph.metadata["cross_graph_links"][0]["provenance_chains"]["factual_assertion"]["span"] == "I was fired"
    assert graph.metadata["cross_graph_links"][0]["provenance_chains"]["rule"]["citation"] == "42 USC 2000e-3"


def test_legal_builder_namespaces_authority_rule_and_requirement():
    builder = LegalGraphBuilder()
    graph = builder.build_from_authorities(
        [{
            "authority_id": "auth-1",
            "name": "Title VII retaliation",
            "citation": "42 USC 2000e-3",
            "provenance": {"source_id": "auth-1"},
            "rule_candidates": [{
                "rule_text": "An employer may not retaliate against an employee for opposing an unlawful practice.",
                "rule_type": "prohibition",
                "claim_element_id": "element-1",
                "provenance": {"source_id": "rule-span-1"},
            }],
        }],
        claim_elements=[{"element_id": "element-1", "element_text": "retaliation"}],
    )
    kinds = {element.element_type for element in graph.elements.values()}
    assert "authority_source" in kinds
    assert "rule_candidate" in kinds
    authority = next(element for element in graph.elements.values() if element.element_type == "authority_source")
    rule = next(element for element in graph.elements.values() if element.element_type == "rule_candidate")
    assert authority.id.startswith("authority_source:")
    assert rule.id.startswith("rule_candidate:")
    assert authority.id != rule.id
    assert authority.attributes["provenance"]["source_id"] == "auth-1"
    assert rule.attributes["provenance"]["source_id"] == "rule-span-1"

    statute_graph = builder.build_from_statutes(
        [{"name": "Title VII", "citation": "42 USC 2000e", "description": "discrimination"}],
        ["discrimination"],
    )
    requirements = statute_graph.get_elements_by_type("legal_requirement")
    assert requirements
    assert all(element.id.startswith("legal_requirement:") for element in requirements)
    assert all(element.attributes["about_complainant"] is False for element in requirements)

    dependency = DependencyGraphBuilder().build_from_claims(
        [{"name": "Retaliation", "type": "retaliation", "description": "I was fired"}],
        {"retaliation": [{"name": "Protected opposition", "description": "Employee opposed an unlawful practice", "provenance": {"source_id": "req-1"}}]},
    )
    legal_nodes = [node for node in dependency.nodes.values() if node.attributes.get("record_kind") == "legal_requirement"]
    assert legal_nodes
    assert all(node.id.startswith("legal_requirement:") for node in legal_nodes)
    assert legal_nodes[0].attributes["provenance"]["source_id"] == "req-1"
