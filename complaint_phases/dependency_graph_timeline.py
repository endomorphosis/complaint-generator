"""Intake timeline and fact-link updates delegated from the dependency graph builder."""

from complaint_phases.dependency_graph import (
    Any,
    Dependency,
    DependencyGraph,
    DependencyNode,
    DependencyType,
    Dict,
    NodeType,
    Optional,
    deepcopy,
)


def apply_derived_dependency_requirements(self, graph: DependencyGraph, derivation: Dict[str, Any]) -> Dict[str, Any]:
    """Install SDK-derived requirements and visible unresolved research.

    Earlier nodes from this derivation are replaced. Fact support is stored
    on the requirement and does not change its rule text. Other graph
    nodes stay in place.
    """
    if not isinstance(derivation, dict):
        raise ValueError("derivation_invalid")
    task_id = "CIMP-UX-26"
    removed = []
    for node in list(graph.nodes.values()):
        attributes = node.attributes if isinstance(node.attributes, dict) else {}
        if attributes.get("derivation_task") == task_id:
            removed.append(node.id)
            graph.nodes.pop(node.id, None)
    if removed:
        removed_ids = set(removed)
        graph.dependencies = {key: edge for key, edge in graph.dependencies.items()
                              if edge.source_id not in removed_ids and edge.target_id not in removed_ids}
    claims = graph.get_nodes_by_type(NodeType.CLAIM)
    installed = []
    for requirement in derivation.get("requirements") or []:
        if not isinstance(requirement, dict) or requirement.get("rule_text") != requirement.get("description"):
            continue
        node = self._add_legal_requirement_node(graph, claims[0] if claims else DependencyNode(
            id="case", node_type=NodeType.CLAIM, name="case", attributes={"claim_type": "unspecified"}), requirement)
        if not claims:
            graph.dependencies = {key: edge for key, edge in graph.dependencies.items() if edge.target_id != "case"}
            graph.nodes.pop("case", None)
        node.attributes["derivation_task"] = task_id
        node.attributes["derivation_lineage"] = deepcopy(requirement.get("derivation_lineage") or {})
        node.attributes["fact_support"] = list(requirement.get("fact_support") or [])
        node.attributes["support_state"] = requirement.get("support_state") or "unsupported"
        node.attributes["effective_date"] = requirement.get("effective_date") or ""
        node.attributes["authority_version"] = requirement.get("authority_version") or ""
        node.attributes["jurisdiction"] = requirement.get("jurisdiction") or ""
        node.attributes["admitted_law"] = True
        node.attributes["proof"] = False
        node.description = str(requirement.get("rule_text") or "")
        node.satisfied = False
        installed.append(node.id)
        for fact in node.attributes["fact_support"]:
            fact_node = next((item for item in graph.nodes.values()
                              if item.node_type == NodeType.FACT and fact.get("fact_id") in {item.id, item.name}), None)
            if fact_node is None:
                continue
            graph.add_dependency(Dependency(
                id=self._get_dependency_id(), source_id=fact_node.id, target_id=node.id,
                dependency_type=DependencyType.SUPPORTS, required=False,
            ))
    unresolved_ids = []
    for item in derivation.get("unresolved_research") or []:
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason") or "unresolved")
        node = DependencyNode(
            id=self._get_namespaced_node_id("legal_requirement", {"gap": "unresolved_research", "reason": reason,
                "passage_id": str(item.get("passage_id") or ""), "task": task_id}),
            node_type=NodeType.REQUIREMENT,
            name="Unresolved legal research",
            description="Admitted authority did not yield a current requirement. No generic element was substituted.",
            satisfied=False,
            attributes={
                "record_kind": "unresolved_research",
                "dependency_class": "unresolved_research",
                "derivation_task": task_id,
                "unresolved_reason": reason,
                "visible": True,
                "law_derived": False,
                "admitted_law": False,
                "proof": False,
                "review_reasons": list(item.get("review_reasons") or []),
                "passage_id": str(item.get("passage_id") or ""),
                "passage_ids": list(item.get("passage_ids") or []),
            },
        )
        graph.add_node(node)
        unresolved_ids.append(node.id)
        for claim in claims:
            graph.add_dependency(Dependency(
                id=self._get_dependency_id(), source_id=node.id, target_id=claim.id,
                dependency_type=DependencyType.REQUIRES, required=True,
            ))
    graph.metadata["derived_dependency_requirements"] = {
        "task_id": task_id,
        "status": derivation.get("status"),
        "requirement_ids": installed,
        "unresolved_ids": unresolved_ids,
        "hardcoded_elements_used": False,
    }
    return graph.metadata["derived_dependency_requirements"]

def sync_intake_timeline_to_graph(
    self,
    graph: DependencyGraph,
    intake_case_file: Optional[Dict[str, Any]],
) -> DependencyGraph:
    """Synchronize structured intake timeline facts and temporal edges into a dependency graph."""
    if not isinstance(graph, DependencyGraph):
        return graph

    case_file = intake_case_file if isinstance(intake_case_file, dict) else {}
    canonical_facts = case_file.get('canonical_facts') if isinstance(case_file.get('canonical_facts'), list) else []
    timeline_relations = case_file.get('timeline_relations') if isinstance(case_file.get('timeline_relations'), list) else []

    temporal_node_ids = [
        node_id
        for node_id, node in graph.nodes.items()
        if isinstance(node.attributes, dict) and node.attributes.get('timeline_fact_node')
    ]
    if temporal_node_ids:
        temporal_node_id_set = set(temporal_node_ids)
        graph.dependencies = {
            dep_id: dep
            for dep_id, dep in graph.dependencies.items()
            if dep.source_id not in temporal_node_id_set and dep.target_id not in temporal_node_id_set
        }
        for node_id in temporal_node_ids:
            graph.nodes.pop(node_id, None)

    claim_nodes = graph.get_nodes_by_type(NodeType.CLAIM)
    claim_nodes_by_type = {
        str(node.attributes.get('claim_type') or '').strip(): node
        for node in claim_nodes
        if isinstance(node.attributes, dict)
    }
    timeline_node_ids_by_fact_id: Dict[str, str] = {}

    for fact in canonical_facts:
        if not isinstance(fact, dict):
            continue
        temporal_context = fact.get('temporal_context') if isinstance(fact.get('temporal_context'), dict) else {}
        if (
            str(fact.get('fact_type') or '').strip().lower() != 'timeline'
            and not temporal_context.get('start_date')
            and not temporal_context.get('relative_markers')
        ):
            continue

        fact_id = str(fact.get('fact_id') or '').strip()
        if not fact_id:
            continue
        node_id = self._get_node_id()
        timeline_node = DependencyNode(
            id=node_id,
            node_type=NodeType.FACT,
            name=str(fact.get('text') or fact_id),
            description=str(fact.get('event_date_or_range') or fact.get('text') or ''),
            satisfied=bool(
                temporal_context.get('start_date')
                or temporal_context.get('relative_markers')
                or fact.get('event_date_or_range')
            ),
            confidence=float(fact.get('confidence', 0.0) or 0.0),
            attributes={
                'timeline_fact_node': True,
                'source_fact_id': fact_id,
                'fact_type': fact.get('fact_type'),
                'event_date_or_range': fact.get('event_date_or_range'),
                'temporal_context': temporal_context,
                'claim_types': list(fact.get('claim_types') or []),
                'element_tags': list(fact.get('element_tags') or []),
            },
        )
        graph.add_node(timeline_node)
        timeline_node_ids_by_fact_id[fact_id] = node_id

        target_claim_nodes = []
        claim_types = [str(item).strip() for item in (fact.get('claim_types') or []) if str(item).strip()]
        for claim_type in claim_types:
            claim_node = claim_nodes_by_type.get(claim_type)
            if claim_node is not None:
                target_claim_nodes.append(claim_node)
        if not target_claim_nodes:
            target_claim_nodes = claim_nodes

        for claim_node in target_claim_nodes:
            graph.add_dependency(
                Dependency(
                    id=self._get_dependency_id(),
                    source_id=timeline_node.id,
                    target_id=claim_node.id,
                    dependency_type=DependencyType.SUPPORTS,
                    required=False,
                    strength=max(0.1, min(1.0, float(fact.get('confidence', 0.0) or 0.0))),
                )
            )

    relation_type_map = {
        'before': DependencyType.BEFORE,
        'same_time': DependencyType.SAME_TIME,
        'overlaps': DependencyType.OVERLAPS,
    }
    for relation in timeline_relations:
        if not isinstance(relation, dict):
            continue
        source_fact_id = str(relation.get('source_fact_id') or '').strip()
        target_fact_id = str(relation.get('target_fact_id') or '').strip()
        dependency_type = relation_type_map.get(str(relation.get('relation_type') or '').strip())
        source_node_id = timeline_node_ids_by_fact_id.get(source_fact_id)
        target_node_id = timeline_node_ids_by_fact_id.get(target_fact_id)
        if not dependency_type or not source_node_id or not target_node_id:
            continue
        confidence = str(relation.get('confidence') or '').strip().lower()
        strength = 0.7 if confidence == 'high' else 0.55 if confidence == 'medium' else 0.4
        graph.add_dependency(
            Dependency(
                id=self._get_dependency_id(),
                source_id=source_node_id,
                target_id=target_node_id,
                dependency_type=dependency_type,
                required=False,
                strength=strength,
            )
        )

    graph._update_metadata()
    return graph

def invalidate_factual_dependents(
    self,
    graph: DependencyGraph,
    fact_id: str,
    *,
    reason: str,
    event_id: str = "",
) -> Dict[str, Any]:
    """Drop proof caches and satisfaction only where this fact is a support input.

    Legal requirement text, source identity, and unrelated node ids stay.
    Contradiction edges remain. Affected inquiry targets are reopened.
    """
    if not isinstance(graph, DependencyGraph) or not fact_id:
        return {"invalidated_node_ids": [], "reopened_inquiry_ids": [], "preserved_node_ids": []}
    invalidated = []
    reopened = []
    for node in graph.nodes.values():
        attributes = node.attributes if isinstance(node.attributes, dict) else {}
        if not self._node_depends_on_fact(node, fact_id):
            continue
        if node.id == fact_id:
            continue
        preserved_text = {
            "name": node.name,
            "description": node.description,
            "rule_id": attributes.get("rule_id"),
            "authority_id": attributes.get("authority_id"),
            "source_hash": attributes.get("source_hash"),
            "source_span": deepcopy(attributes.get("source_span")) if isinstance(attributes.get("source_span"), dict) else attributes.get("source_span"),
            "provenance": deepcopy(attributes.get("provenance")) if isinstance(attributes.get("provenance"), dict) else attributes.get("provenance"),
        }
        if node.satisfied or attributes.get("satisfaction_state") == "satisfied" or attributes.get("proof_cache_identity") or isinstance(attributes.get("proof_cache"), dict):
            attributes["invalidated_satisfaction"] = {
                "satisfied": bool(node.satisfied),
                "confidence": node.confidence,
                "satisfaction_state": attributes.get("satisfaction_state"),
                "proof_cache_identity": attributes.get("proof_cache_identity"),
            }
            node.satisfied = False
            attributes["satisfaction_state"] = "invalidated"
            attributes["stale_satisfaction"] = True
        if attributes.get("proof_cache_identity"):
            attributes["rejected_proof_cache_identity"] = attributes.get("proof_cache_identity")
        attributes["proof_cache_reusable"] = False
        if isinstance(attributes.get("proof_cache"), dict):
            attributes["proof_cache"] = dict(attributes["proof_cache"])
            attributes["proof_cache"]["reusable"] = False
            attributes["proof_cache"]["satisfied"] = False
            attributes["proof_cache"]["invalidation_reason"] = reason
            attributes["proof_cache"]["invalidated_entity_id"] = fact_id
        attributes["invalidation_reason"] = reason
        attributes["invalidated_entity_id"] = fact_id
        for inquiry in attributes.get("inquiry_targets") or []:
            if not isinstance(inquiry, dict):
                continue
            target = str(inquiry.get("entity_id") or inquiry.get("fact_id") or "")
            if target != fact_id:
                continue
            inquiry["status"] = "reopened"
            inquiry["invalidation_reason"] = reason
            inquiry["event_id"] = event_id
            reopened.append(inquiry.get("inquiry_id"))
        node.name = preserved_text["name"]
        node.description = preserved_text["description"]
        attributes["rule_id"] = preserved_text["rule_id"]
        attributes["authority_id"] = preserved_text["authority_id"]
        attributes["source_hash"] = preserved_text["source_hash"]
        attributes["source_span"] = preserved_text["source_span"]
        attributes["provenance"] = preserved_text["provenance"]
        node.attributes = attributes
        invalidated.append(node.id)
    for dependency in graph.dependencies.values():
        if dependency.dependency_type == DependencyType.CONTRADICTS:
            continue
        if dependency.dependency_type != DependencyType.SUPPORTS:
            continue
        if fact_id not in {dependency.source_id, dependency.target_id}:
            continue
        graph.metadata.setdefault("invalidated_support_refs", [])
        ref = {
            "dependency_id": dependency.id,
            "source_id": dependency.source_id,
            "target_id": dependency.target_id,
            "fact_id": fact_id,
            "reason": reason,
            "event_id": event_id,
        }
        if ref not in graph.metadata["invalidated_support_refs"]:
            graph.metadata["invalidated_support_refs"].append(ref)
    graph._update_metadata()
    preserved = [node_id for node_id in graph.nodes if node_id not in set(invalidated)]
    return {
        "invalidated_node_ids": invalidated,
        "reopened_inquiry_ids": reopened,
        "preserved_node_ids": preserved,
    }

def apply_retrieval_nomination(
    self,
    graph: DependencyGraph,
    payload: Dict[str, Any],
    *,
    claim_id: str = "",
    requirement_id: str = "",
    source_span: Optional[Dict[str, Any]] = None,
    allegation_id: str = "",
) -> Dict[str, Any]:
    """Admit retrieval output as a nomination until exact binding is rechecked.

    A bound nomination may support a factual allegation. It does not rewrite
    or satisfy the governing legal requirement.
    """
    from mediator.integrations.graph_tools import GraphRetrievalAugmentor

    if not isinstance(graph, DependencyGraph):
        return {"admitted": False, "reason": "dependency_graph_unavailable", "bound_support": False}
    augmentor = GraphRetrievalAugmentor()
    if claim_id or requirement_id or source_span is not None:
        checked = augmentor.recheck_support_binding(
            payload,
            claim_id=claim_id,
            requirement_id=requirement_id,
            source_span=source_span,
        )
    else:
        checked = dict(payload)
        checked["bound_support"] = False
        checked["support_status"] = checked.get("support_status") or "candidate_nomination"
        checked["satisfied_legal_requirement"] = False
    legal = graph.nodes.get(requirement_id) if requirement_id else None
    legal_before = None
    if legal is not None:
        legal_before = {
            "id": legal.id,
            "name": legal.name,
            "description": legal.description,
            "satisfied": legal.satisfied,
            "rule_id": (legal.attributes or {}).get("rule_id"),
            "authority_id": (legal.attributes or {}).get("authority_id"),
            "source_hash": (legal.attributes or {}).get("source_hash"),
            "source_span": deepcopy((legal.attributes or {}).get("source_span")),
            "provenance": deepcopy((legal.attributes or {}).get("provenance")),
        }
    record_id = str(checked.get("id") or "").strip()
    if record_id and graph.get_node(record_id) is None:
        graph.add_node(DependencyNode(
            id=record_id,
            node_type=NodeType.EVIDENCE,
            name=str(checked.get("name") or "Evidence"),
            description=str(checked.get("description") or ""),
            satisfied=False,
            confidence=float(checked.get("retrieval_confidence", checked.get("confidence", 0.0)) or 0.0),
            attributes={
                "support_status": checked.get("support_status"),
                "binding_status": checked.get("binding_status"),
                "bound_support": bool(checked.get("bound_support")),
                "retrieval_confidence": checked.get("retrieval_confidence", checked.get("confidence")),
                "confidence_role": "retrieval_candidate",
                "satisfied_legal_requirement": False,
                "supports_claims": list(checked.get("supports_claims") or []),
                "source_type": checked.get("source_type"),
            },
        ))
    if checked.get("bound_support") and allegation_id and allegation_id in graph.nodes and record_id in graph.nodes:
        dependency_id = f"supports:{record_id}:{allegation_id}"
        if dependency_id not in graph.dependencies:
            graph.add_dependency(Dependency(
                id=dependency_id,
                source_id=record_id,
                target_id=allegation_id,
                dependency_type=DependencyType.SUPPORTS,
                required=False,
                strength=0.0,
            ))
        allegation = graph.nodes[allegation_id]
        allegation_attributes = dict(allegation.attributes or {})
        refs = list(allegation_attributes.get("evidence_support_refs") or [])
        if record_id not in refs:
            refs.append(record_id)
        allegation_attributes["evidence_support_refs"] = refs
        allegation.attributes = allegation_attributes
    if legal is not None and legal_before is not None:
        legal.id = legal_before["id"]
        legal.name = legal_before["name"]
        legal.description = legal_before["description"]
        legal.satisfied = False if not legal_before["satisfied"] else legal_before["satisfied"]
        attributes = dict(legal.attributes or {})
        attributes["rule_id"] = legal_before["rule_id"]
        attributes["authority_id"] = legal_before["authority_id"]
        attributes["source_hash"] = legal_before["source_hash"]
        attributes["source_span"] = legal_before["source_span"]
        attributes["provenance"] = legal_before["provenance"]
        attributes["satisfied_by_retrieval"] = False
        legal.attributes = attributes
    graph._update_metadata()
    return {
        "admitted": bool(checked.get("bound_support")),
        "bound_support": bool(checked.get("bound_support")),
        "support_status": checked.get("support_status"),
        "binding_status": checked.get("binding_status"),
        "binding_reason": checked.get("binding_reason"),
        "satisfied_legal_requirement": False,
        "retrieval_confidence": checked.get("retrieval_confidence", checked.get("confidence")),
        "legal_requirement": legal_before,
    }

def add_fact_rule_link(
    self,
    graph: DependencyGraph,
    *,
    factual_assertion_id: str,
    rule_id: str,
    relation: str = "supports",
    factual_provenance: Optional[Dict[str, Any]] = None,
    rule_provenance: Optional[Dict[str, Any]] = None,
    factual_name: str = "",
    rule_name: str = "",
) -> Dict[str, Any]:
    """Record a support or contradiction edge across factual and rule namespaces.

    Each side keeps its own provenance chain. The link id is neither a fact
    id nor a rule id.
    """
    from integrations.ipfs_datasets.graphs import (
        FACTUAL_ASSERTION_KIND,
        build_namespaced_support_link,
        record_kind_from_id,
    )

    link = build_namespaced_support_link(
        factual_assertion_id=factual_assertion_id,
        rule_id=rule_id,
        relation=relation,
        factual_provenance=factual_provenance,
        rule_provenance=rule_provenance,
    )
    fact_chain = dict(link["provenance_chains"][FACTUAL_ASSERTION_KIND])
    rule_chain = dict(link["provenance_chains"]["rule"])
    fact_text = factual_name or factual_assertion_id
    if link["assertion_verified"]:
        # The flag verifies only the immutable assertion's content. A local
        # alias or caller display label cannot introduce another assertion.
        from integrations.ipfs_datasets.types import user_assertion_from_mapping
        asserted_text = user_assertion_from_mapping(fact_chain["user_assertion"]).source_span_text
        if factual_name and " ".join(factual_name.split()) != " ".join(asserted_text.split()):
            raise ValueError("factual label differs from the verified assertion span")
        fact_text = asserted_text
    fact_ref = link["factual_assertion_id"]
    rule_kind = record_kind_from_id(rule_id)
    # Validate both endpoints and any replay BEFORE mutating the graph.
    for endpoint, expected_type, expected_kind, chain in (
        (fact_ref, NodeType.FACT, FACTUAL_ASSERTION_KIND, fact_chain),
        (rule_id, NodeType.LEGAL_ELEMENT, rule_kind, rule_chain),
    ):
        node = graph.nodes.get(endpoint)
        if node is None:
            continue
        if node.id != endpoint or node.node_type != expected_type or node.attributes.get("record_kind") != expected_kind:
            raise ValueError("cross-graph endpoint has a conflicting type or namespace")
        if node.attributes.get("provenance", {}) != chain:
            raise ValueError("cross-graph endpoint has conflicting source provenance")
        if expected_type == NodeType.FACT and link["assertion_verified"] and (
            not isinstance(node.name, str) or " ".join(node.name.split()) != " ".join(fact_text.split())
        ):
            raise ValueError("stored factual text differs from its verified assertion span")
    if fact_ref != factual_assertion_id and factual_assertion_id in graph.nodes:
        node = graph.nodes[factual_assertion_id]
        if node.id != factual_assertion_id or node.node_type != NodeType.FACT or node.attributes.get("provenance", {}) != fact_chain:
            raise ValueError("local factual endpoint is ambiguous or has conflicting provenance")
        if link["assertion_verified"] and (
            not isinstance(node.name, str) or " ".join(node.name.split()) != " ".join(fact_text.split())
        ):
            raise ValueError("local factual text differs from its verified assertion span")
    dependency_type = (
        DependencyType.CONTRADICTS if link["link_type"] == "contradiction_link" else DependencyType.SUPPORTS
    )
    existing_dependency = graph.dependencies.get(link["link_id"])
    if existing_dependency is not None and (
        existing_dependency.id != link["link_id"]
        or existing_dependency.source_id != fact_ref or existing_dependency.target_id != rule_id
        or existing_dependency.dependency_type != dependency_type
        or existing_dependency.required or existing_dependency.strength != 1.0
    ):
        raise ValueError("cross-graph link identity conflicts with an existing dependency")
    existing_links = graph.metadata.get("cross_graph_links", [])
    if not isinstance(existing_links, list):
        raise ValueError("invalid cross-graph link registry")
    previous = [item for item in existing_links if isinstance(item, dict) and item.get("link_id") == link["link_id"]]
    if any(item != link for item in previous):
        raise ValueError("cross-graph link replay changed provenance")
    if fact_ref not in graph.nodes:
        graph.add_node(DependencyNode(
            id=fact_ref,
            node_type=NodeType.FACT,
            name=fact_text,
            attributes={
                "record_kind": FACTUAL_ASSERTION_KIND,
                "source_entity_id": factual_assertion_id,
                "assertion_verified": link["assertion_verified"],
                "provenance": deepcopy(fact_chain),
            },
        ))
    if rule_id not in graph.nodes:
        graph.add_node(DependencyNode(
            id=rule_id,
            node_type=NodeType.LEGAL_ELEMENT,
            name=rule_name or rule_id,
            attributes={
                "record_kind": rule_kind,
                "about_complainant": False,
                "provenance": deepcopy(rule_chain),
            },
        ))
    graph.add_dependency(Dependency(
        id=link["link_id"],
        source_id=fact_ref,
        target_id=rule_id,
        dependency_type=dependency_type,
        required=False,
        strength=1.0,
    ))
    if not previous:
        graph.metadata.setdefault("cross_graph_links", []).append(deepcopy(link))
    return deepcopy(link)
