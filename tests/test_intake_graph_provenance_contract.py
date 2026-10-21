"""Contract: factual, authority, rule, requirement, and support-link namespaces stay distinct."""

import pytest

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


def test_colliding_legacy_entity_ids_do_not_drop_a_domain():
    result = resolve_duplicate_entities([
        {"entity_id": "shared", "name": "Equal protection", "source_kind": "testimony"},
        {"entity_id": "shared", "name": "Equal protection", "source_kind": "law", "record_kind": "legal_requirement"},
    ])
    assert result["entity_count"] == 2
    assert len(result["entity_map"]) == 2
    assert {c["resolution_namespace"] for c in result["entity_map"].values()} == {"user_testimony", "legal_norm"}


def test_nested_legal_provenance_cannot_merge_into_testimony():
    result = resolve_duplicate_entities([
        {"entity_id": "user", "name": "Equal protection", "source_kind": "testimony"},
        {"entity_id": "law", "name": "Equal protection", "attributes": {"provenance": {"source_type": "statute"}}},
    ])
    assert result["entity_count"] == 2


def test_nested_legal_passage_provenance_is_not_a_complainant_fact():
    result = extract_graph_from_text("A landlord shall provide reasonable accommodation.",
        source_id="synthetic-statute", metadata={"provenance": {"source_type": "statute", "source_id": "synthetic-statute"}})
    passages = [e for e in result["entities"] if e["type"] != "artifact"]
    assert passages
    assert all(e["type"] == "authority_source" and not e["attributes"]["about_complainant"] for e in passages)


def test_real_verified_graph_fact_can_link_to_real_legal_rule_without_rewriting_proof():
    from integrations.ipfs_datasets.types import source_byte_hash, user_assertion_from_mapping
    text = "I was fired."
    factual = KnowledgeGraphBuilder().build_from_text(text, source_context={
        "source_kind": "user_statement", "source_id": "message-real", "message_id": "message-real",
        "source_hash": source_byte_hash(text), "assertion_status": "asserted", "extractor_version": "audit.v1"})
    fact = next(e for e in factual.entities.values() if e.type == "fact" and user_assertion_from_mapping(e.provenance["user_assertion"]).is_asserted_user_fact)
    original_id, original_proof = fact.id, dict(fact.provenance["user_assertion"])
    rule = LegalGraphBuilder().project_legal_passage({"text": "Retaliation is prohibited.", "passage_role": "rule_candidate", "source_id": "rule-source", "provenance": {"source_id": "rule-source"}})
    graph = DependencyGraph()
    link = DependencyGraphBuilder().add_fact_rule_link(graph,
        factual_assertion_id=fact.id, rule_id=rule.id,
        factual_provenance=fact.provenance, rule_provenance=rule.attributes["provenance"])
    assert record_kind_from_id(link["factual_assertion_id"]) == "factual_assertion"
    assert fact.id == original_id and fact.provenance["user_assertion"] == original_proof
    assert link["provenance_chains"]["factual_assertion"]["user_assertion"] == original_proof


def test_cross_graph_link_rejects_existing_wrong_typed_endpoint():
    import pytest
    from complaint_phases.dependency_graph import DependencyNode, NodeType
    graph = DependencyGraph()
    factual_id = mint_graph_record_id("factual_assertion", "fact")
    rule_id = mint_graph_record_id("rule_candidate", "rule")
    graph.add_node(DependencyNode(id=factual_id, node_type=NodeType.LEGAL_ELEMENT, name="a norm",
        attributes={"record_kind": "authority_source", "provenance": {"source_id": "statute"}}))
    with pytest.raises(ValueError):
        DependencyGraphBuilder().add_fact_rule_link(graph, factual_assertion_id=factual_id, rule_id=rule_id,
            factual_provenance={"source_id": "message"}, rule_provenance={"source_id": "rule"})


def test_support_query_dedup_retains_distinct_factual_and_legal_records():
    from integrations.ipfs_datasets.graphs import query_graph_support
    fact_id = mint_graph_record_id("factual_assertion", "f")
    rule_id = mint_graph_record_id("legal_requirement", "r")
    result = query_graph_support("element", claim_element_text="Equal protection", support_facts=[
        {"fact_id": fact_id, "text": "Equal protection", "record_kind": "factual_assertion", "source_kind": "testimony", "confidence": .6},
        {"fact_id": rule_id, "text": "Equal protection", "record_kind": "legal_requirement", "source_kind": "law", "confidence": .9},
    ])
    assert {r["fact_id"] for r in result["results"]} == {fact_id, rule_id}


def test_namespaced_identity_does_not_alias_delimiter_bearing_parts():
    assert mint_graph_record_id("factual_assertion", "a|b", "c") != mint_graph_record_id("factual_assertion", "a", "b|c")


def test_snapshot_content_identity_binds_explicit_namespace():
    from integrations.ipfs_datasets.graphs import build_graph_persistence_request
    payload = {"source_id": "same", "entities": [{"id": "same", "name": "same"}], "relationships": []}
    first = build_graph_persistence_request({**payload, "metadata": {"namespace": "factual_assertion"}})
    second = build_graph_persistence_request({**payload, "metadata": {"namespace": "authority_source"}})
    assert first["content_hash"] != second["content_hash"]
    assert first["snapshot_id"] != second["snapshot_id"]


def test_nested_legal_context_never_creates_an_asserted_user_fact():
    from integrations.ipfs_datasets.types import source_byte_hash, user_assertion_from_mapping
    text = "A landlord must accommodate a disability."
    graph = KnowledgeGraphBuilder().build_from_text(text, source_context={
        "source_kind": "user_statement", "source_id": "synthetic-message", "message_id": "synthetic-message",
        "source_hash": source_byte_hash(text), "assertion_status": "asserted", "extractor_version": "audit.v1",
        "provenance": {"source_type": "statute", "source_id": "synthetic-law"},
    })
    assert graph.entities
    assert all(e.type == "legal_text" and e.attributes["about_complainant"] is False for e in graph.entities.values())
    assert all(not user_assertion_from_mapping(e.provenance["user_assertion"]).is_asserted_user_fact for e in graph.entities.values())


def test_legal_subtypes_do_not_collapse_in_resolution_or_support_query():
    from integrations.ipfs_datasets.graphs import query_graph_support
    records = [
        {"id": mint_graph_record_id(kind, "same"), "fact_id": mint_graph_record_id(kind, "same"),
         "name": "Equal protection", "text": "Equal protection", "record_kind": kind, "source_kind": "law"}
        for kind in ("authority_source", "rule_candidate", "legal_requirement")
    ]
    assert resolve_duplicate_entities(records)["entity_count"] == 3
    queried = query_graph_support("element", claim_element_text="Equal protection", support_facts=records)
    assert {r["fact_id"] for r in queried["results"]} == {r["fact_id"] for r in records}


def test_unclassified_record_cannot_be_merged_into_testimony():
    result = resolve_duplicate_entities([
        {"id": "known", "name": "Equal protection", "source_kind": "testimony"},
        {"id": "unknown", "name": "Equal protection"},
    ])
    assert result["entity_count"] == 2


def test_cross_graph_link_checks_rule_before_creating_any_endpoint():
    import pytest
    from complaint_phases.dependency_graph import DependencyNode, NodeType
    graph = DependencyGraph()
    fact_id, rule_id = mint_graph_record_id("factual_assertion", "f"), mint_graph_record_id("rule_candidate", "r")
    graph.add_node(DependencyNode(id=rule_id, node_type=NodeType.FACT, name="not a rule", attributes={"record_kind": "factual_assertion"}))
    before = graph.to_dict()
    with pytest.raises(ValueError):
        DependencyGraphBuilder().add_fact_rule_link(graph, factual_assertion_id=fact_id, rule_id=rule_id)
    assert graph.to_dict() == before


def test_link_replay_is_idempotent_and_preserves_independent_source_chains():
    import pytest
    graph, builder = DependencyGraph(), DependencyGraphBuilder()
    fact_id, rule_id = mint_graph_record_id("factual_assertion", "f"), mint_graph_record_id("rule_candidate", "r")
    factual = {"source_id": "message", "nested": {"source_revision": 1}}
    legal = {"source_id": "law", "nested": {"source_revision": 2}}
    kwargs = {"factual_assertion_id": fact_id, "rule_id": rule_id, "factual_provenance": factual, "rule_provenance": legal}
    first = builder.add_fact_rule_link(graph, **kwargs)
    assert builder.add_fact_rule_link(graph, **kwargs) == first
    assert len(graph.dependencies) == 1 and len(graph.metadata["cross_graph_links"]) == 1
    assert not graph.nodes[fact_id].satisfied and not graph.nodes[rule_id].satisfied
    factual["nested"]["source_revision"] = 99
    legal["nested"]["source_revision"] = 98
    first["provenance_chains"]["rule"]["nested"]["source_revision"] = 97
    assert graph.nodes[fact_id].attributes["provenance"]["nested"]["source_revision"] == 1
    assert graph.metadata["cross_graph_links"][0]["provenance_chains"]["rule"]["nested"]["source_revision"] == 2
    before = graph.to_dict()
    with pytest.raises(ValueError):
        builder.add_fact_rule_link(graph, **kwargs)
    assert graph.to_dict() == before


def test_local_unverified_or_legal_proof_cannot_supply_a_factual_link():
    import pytest
    rule_id = mint_graph_record_id("rule_candidate", "r")
    with pytest.raises(ValueError):
        build_namespaced_support_link(factual_assertion_id="ent_1", rule_id=rule_id,
                                      factual_provenance={"source_id": "unknown"})
    with pytest.raises(ValueError):
        build_namespaced_support_link(factual_assertion_id=mint_graph_record_id("factual_assertion", "f"),
            rule_id=rule_id, factual_provenance={"attributes": {"provenance": {"source_type": "statute"}}})
    with pytest.raises(ValueError):
        build_namespaced_support_link(factual_assertion_id=mint_graph_record_id("factual_assertion", "f"),
            rule_id=rule_id, rule_provenance={"source_kind": "user_statement"})


def test_same_local_id_cannot_overwrite_factual_graph_with_a_legal_record():
    import pytest
    from complaint_phases.knowledge_graph import Entity, KnowledgeGraph
    factual, legal = KnowledgeGraph(), KnowledgeGraph()
    original = Entity(id="ent_1", type="fact", name="I was fired.", provenance={"source_id": "message"})
    factual.add_entity(original)
    legal.add_entity(Entity(id="ent_1", type="legal_text", name="Discharge is prohibited.", source="legal"))
    with pytest.raises(ValueError):
        factual.merge_with(legal)
    assert factual.entities["ent_1"] is original
    assert original.provenance == {"source_id": "message"}


def test_legal_and_requirement_ids_bind_source_content_across_fresh_builders():
    passage = {"text": "Retaliation is prohibited.", "passage_role": "rule_candidate", "provenance": {"source_id": "law-A"}}
    first = LegalGraphBuilder().project_legal_passage(passage)
    builder = LegalGraphBuilder()
    builder.project_legal_passage({**passage, "text": "An unrelated rule."})
    assert builder.project_legal_passage(passage).id == first.id
    assert LegalGraphBuilder().project_legal_passage({**passage, "provenance": {"source_id": "law-B"}}).id != first.id
    def requirement_id(source):
        graph = DependencyGraphBuilder().build_from_claims([{"name": "Retaliation", "type": "retaliation"}],
            {"retaliation": [{"name": "Protected activity", "provenance": {"source_id": source}}]})
        return next(n.id for n in graph.nodes.values() if n.attributes.get("record_kind") == "legal_requirement")
    assert requirement_id("law-A") == requirement_id("law-A")
    assert requirement_id("law-A") != requirement_id("law-B")


def _verified_fact_for_namespace_checks():
    from integrations.ipfs_datasets.types import source_byte_hash, user_assertion_from_mapping
    text = "I was fired."
    graph = KnowledgeGraphBuilder().build_from_text(text, source_context={
        "source_kind": "user_statement", "source_id": "typed-message", "message_id": "typed-message",
        "source_hash": source_byte_hash(text), "assertion_status": "asserted", "extractor_version": "audit.v1"})
    return next(entity for entity in graph.entities.values() if entity.type == "fact"
                and user_assertion_from_mapping(entity.provenance["user_assertion"]).is_asserted_user_fact)


@pytest.mark.parametrize("source", ["law", "statute", "regulation", "case_law"])
def test_deserialized_legal_origin_cannot_replay_a_verified_user_envelope(source):
    from copy import deepcopy
    from complaint_phases.knowledge_graph import Entity
    from integrations.ipfs_datasets.types import user_assertion_from_mapping
    fact = _verified_fact_for_namespace_checks()
    original = deepcopy(fact.provenance)
    replay = Entity(id=fact.id, type=fact.type, name=fact.name, attributes=deepcopy(fact.attributes),
                    source=source, provenance=deepcopy(fact.provenance))
    assert not user_assertion_from_mapping(replay.provenance["user_assertion"]).is_asserted_user_fact
    assert replay.provenance["user_assertion"]["record_type"] == "legal_text"
    assert fact.provenance == original
    assert user_assertion_from_mapping(fact.provenance["user_assertion"]).is_asserted_user_fact


@pytest.mark.parametrize("alias", ["", "authority_source:law", "rule_candidate:rule", "legal_requirement:req", "support_link:s", "contradiction_link:c", "factual_assertion:wrong", "authority_source:", "factual_assertion:"])
def test_verified_user_proof_does_not_authorize_an_empty_or_wrong_namespace_alias(alias):
    fact = _verified_fact_for_namespace_checks()
    with pytest.raises(ValueError):
        build_namespaced_support_link(factual_assertion_id=alias, rule_id=mint_graph_record_id("rule_candidate", "r"),
                                      factual_provenance=fact.provenance)


def test_verified_fact_node_text_is_the_proven_span_not_a_caller_claim():
    fact = _verified_fact_for_namespace_checks()
    graph, builder = DependencyGraph(), DependencyGraphBuilder()
    kwargs = {"factual_assertion_id": fact.id, "rule_id": mint_graph_record_id("rule_candidate", "r"),
              "factual_provenance": fact.provenance, "rule_provenance": {"source_id": "law"}}
    before = graph.to_dict()
    with pytest.raises(ValueError):
        builder.add_fact_rule_link(graph, **kwargs, factual_name="A different and unsupported allegation.")
    assert graph.to_dict() == before
    link = builder.add_fact_rule_link(graph, **kwargs)
    node = graph.nodes[link["factual_assertion_id"]]
    assert node.name == fact.provenance["user_assertion"]["source_span_text"]
    assert node.attributes["source_entity_id"] == fact.id
    assert node.attributes["assertion_verified"] is True
    assert node.attributes["provenance"]["user_assertion"] == fact.provenance["user_assertion"]


def test_current_legal_kind_precedes_inherited_rule_provenance():
    records = [
        {"id": "requirement", "name": "Same text", "record_kind": "legal_requirement", "provenance": {"passage_role": "rule_candidate"}},
        {"id": "authority", "name": "Same text", "record_kind": "authority_source", "provenance": {"passage_role": "rule_candidate"}},
        {"id": "rule", "name": "Same text", "record_kind": "rule_candidate"},
    ]
    result = resolve_duplicate_entities(records)
    assert result["entity_count"] == 3
    assert {record["resolution_kind"] for record in result["clusters"]} == {"legal_requirement", "authority_source", "rule_candidate"}


def test_nested_span_serialization_remains_valid_without_rewriting_its_proof():
    from copy import deepcopy
    from integrations.ipfs_datasets.types import user_assertion_from_mapping
    fact = _verified_fact_for_namespace_checks()
    proof = deepcopy(fact.provenance)
    for key in ("source_span_start", "source_span_end", "source_span_text"):
        proof["user_assertion"].pop(key)
    original = deepcopy(proof)
    envelope = user_assertion_from_mapping(proof["user_assertion"])
    assert envelope.is_asserted_user_fact
    graph = DependencyGraph()
    link = DependencyGraphBuilder().add_fact_rule_link(graph,
        factual_assertion_id=fact.id, rule_id=mint_graph_record_id("rule_candidate", "r"),
        factual_provenance=proof)
    assert graph.nodes[link["factual_assertion_id"]].name == envelope.source_span_text
    assert link["provenance_chains"]["factual_assertion"] == original == proof


@pytest.mark.parametrize("tamper", ["fact_id", "rule_id", "dependency_id", "fact_name"])
def test_deserialized_link_replay_checks_stored_identity_and_verified_content(tamper):
    from copy import deepcopy
    fact = _verified_fact_for_namespace_checks()
    graph, builder = DependencyGraph(), DependencyGraphBuilder()
    rule = LegalGraphBuilder().project_legal_passage({"text": "Retaliation is prohibited.",
        "passage_role": "rule_candidate", "provenance": {"source_id": "synthetic-law"}})
    kwargs = {"factual_assertion_id": fact.id, "rule_id": rule.id,
              "factual_provenance": deepcopy(fact.provenance), "rule_provenance": deepcopy(rule.attributes["provenance"])}
    link = builder.add_fact_rule_link(graph, **kwargs)
    payload = deepcopy(graph.to_dict())
    if tamper == "fact_id":
        payload["nodes"][link["factual_assertion_id"]]["id"] = "authority_source:foreign"
    elif tamper == "rule_id":
        payload["nodes"][rule.id]["id"] = "factual_assertion:foreign"
    elif tamper == "dependency_id":
        payload["dependencies"][link["link_id"]]["id"] = "contradiction_link:foreign"
    else:
        payload["nodes"][link["factual_assertion_id"]]["name"] = "An unrelated unsupported allegation."
    replay = DependencyGraph.from_dict(payload)
    before = deepcopy(replay.to_dict())
    with pytest.raises(ValueError):
        builder.add_fact_rule_link(replay, **kwargs)
    assert replay.to_dict() == before
    assert fact.provenance == kwargs["factual_provenance"]


def test_unchanged_deserialized_real_link_replays_without_rewriting_proof():
    from copy import deepcopy
    fact = _verified_fact_for_namespace_checks()
    graph, builder = DependencyGraph(), DependencyGraphBuilder()
    kwargs = {"factual_assertion_id": fact.id, "rule_id": mint_graph_record_id("rule_candidate", "synthetic-law"),
              "factual_provenance": deepcopy(fact.provenance), "rule_provenance": {"source_id": "synthetic-law"}}
    link = builder.add_fact_rule_link(graph, **kwargs)
    replay = DependencyGraph.from_dict(deepcopy(graph.to_dict()))
    assert builder.add_fact_rule_link(replay, **kwargs) == link
    assert len(replay.dependencies) == len(replay.metadata["cross_graph_links"]) == 1
    assert fact.provenance == kwargs["factual_provenance"]
