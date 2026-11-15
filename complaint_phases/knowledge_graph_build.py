"""Gap finding, graph merge, and text construction for the knowledge graph."""

from __future__ import annotations

import copy
import re
from dataclasses import replace
from typing import Any, Dict, List, Mapping, Optional, Sequence

from complaint_phases.knowledge_graph import (
    DEFAULT_USER_ASSERTION_EXTRACTOR_VERSION,
    USER_ASSERTION_CONTRACT_VERSION,
    Entity,
    KnowledgeGraph,
    Relationship,
    _CALLER_CONTEXT_FIELDS,
    _SUPPORT_RELATION_TYPES,
    _clean_context_text,
    _merge_provenance,
    _normalized_record_text,
    _resolve_graph_endpoint,
    assertion_from_provenance,
    attach_narrative_source_records,
    envelope_for_extracted_record,
    logger,
    merge_caller_source_context,
)


def find_gaps(self) -> List[Dict[str, Any]]:
    """
    Identify gaps in the knowledge graph that need more information.

    Returns a list of gaps with suggested questions.
    """
    gaps = []
    effective_entities = {key: entity for key, entity in self.entities.items()
                          if self.entity_is_effective(entity)}
    effective_relationships = {
        key: relationship for key, relationship in self.relationships.items()
        if relationship.source_id in effective_entities and relationship.target_id in effective_entities
        and (relationship.attributes or {}).get("effective") is not False
        and (relationship.attributes or {}).get("activity_status") != "invalidated"
    }

    def _relationships_for_entity(entity_id):
        return [relationship for relationship in effective_relationships.values()
                if entity_id in {relationship.source_id, relationship.target_id}]

    def _entity_text(entity: Entity) -> str:
        attributes = entity.attributes if isinstance(entity.attributes, dict) else {}
        parts = [
            str(entity.name or ""),
            str(attributes.get("description") or ""),
            str(attributes.get("event_label") or ""),
            str(attributes.get("event_date_or_range") or ""),
        ]
        return " ".join(part.strip() for part in parts if str(part).strip()).lower()

    def _has_date_signal(text_value: str) -> bool:
        if not text_value:
            return False
        return bool(
            re.search(
                r"\b(?:19|20)\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b",
                text_value,
            )
        )

    def _has_exact_date_signal(text_value: str) -> bool:
        if not text_value:
            return False
        return bool(
            re.search(
                (
                    r"\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|"
                    r"jul|july|aug|august|sep|sept|september|oct|october|nov|november|"
                    r"dec|december)\s+\d{1,2},\s+\d{4}\b"
                    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
                    r"|\b\d{4}-\d{2}-\d{2}\b"
                ),
                text_value,
                flags=re.IGNORECASE,
            )
        )

    # Check for entities with low confidence
    for entity in effective_entities.values():
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
    for entity in effective_entities.values():
        rels = _relationships_for_entity(entity.id)
        if len(rels) == 0 and entity.type in ['person', 'organization']:
            gaps.append({
                'type': 'isolated_entity',
                'entity_id': entity.id,
                'entity_type': entity.type,
                'entity_name': entity.name,
                'suggested_question': f"What is the relationship between {entity.name} and the complaint?"
            })

    # Check for claims without evidence
    claims = [entity for entity in effective_entities.values() if entity.type == 'claim']
    for claim in claims:
        evidence_rels = [
            rel for rel in _relationships_for_entity(claim.id)
            if rel.relation_type == 'supported_by'
        ]
        if len(evidence_rels) == 0:
            gaps.append({
                'type': 'unsupported_claim',
                'entity_id': claim.id,
                'claim_name': claim.name,
                'suggested_question': f"What evidence supports the claim: {claim.name}?"
            })

    # Check for missing timeline details
    has_dates = any(e.type == 'date' for e in effective_entities.values())
    has_timeline_rel = any(
        rel.relation_type in {'occurred_on', 'has_timeline_detail'}
        for rel in effective_relationships.values()
    )
    has_timeline_fact = any(
        e.type == 'fact' and e.attributes.get('fact_type') == 'timeline'
        for e in effective_entities.values()
    )
    if not has_dates and not has_timeline_rel and not has_timeline_fact:
        gaps.append({
            'type': 'missing_timeline',
            'suggested_question': "When did the key events happen? Please share dates or a brief timeline."
        })

    timeline_fact_texts = [
        _entity_text(entity)
        for entity in effective_entities.values()
        if entity.type == "fact" and (entity.attributes or {}).get("fact_type") == "timeline"
    ]
    decision_timeline_terms = (
        "decision",
        "decided",
        "approved",
        "denied",
        "terminated",
        "disciplined",
        "evicted",
        "notice",
        "email",
        "letter",
        "message",
    )
    has_decision_timeline_detail = any(
        any(term in text_value for term in decision_timeline_terms) and _has_date_signal(text_value)
        for text_value in timeline_fact_texts
    )
    if not has_decision_timeline_detail:
        gaps.append({
            'type': 'missing_decision_timeline',
            'suggested_question': (
                "Please walk through an actor-by-actor decision timeline: who took each action, "
                "what they did, and the exact date (or best estimate) for each step."
            ),
        })

    # Check for missing responsible party (no orgs or respondent roles captured)
    has_org = any(e.type == 'organization' for e in effective_entities.values())
    has_respondent_person = any(
        e.type == 'person' and e.attributes.get('role', '').lower() in {'respondent', 'manager', 'supervisor', 'employer', 'owner', 'landlord'}
        for e in effective_entities.values()
    )
    if not has_org and not has_respondent_person:
        gaps.append({
            'type': 'missing_responsible_party',
            'suggested_question': "Who is the person or organization you believe is responsible (e.g., employer, manager, agency)?"
        })

    # Check for missing impact/remedy details
    has_impact = any(
        e.type == 'fact' and e.attributes.get('fact_type') == 'impact'
        for e in effective_entities.values()
    )
    has_remedy = any(
        e.type == 'fact' and e.attributes.get('fact_type') == 'remedy'
        for e in effective_entities.values()
    )
    if not has_impact or not has_remedy:
        gaps.append({
            'type': 'missing_impact_remedy',
            'missing_impact': not has_impact,
            'missing_remedy': not has_remedy,
            'suggested_question': "What harm did you experience, and what outcome or remedy are you seeking?"
        })

    # Blocker checks: written notices, hearing request dates, and identifiable staff actors.
    all_entity_text = " ".join(_entity_text(entity) for entity in effective_entities.values())
    notice_terms = ("notice", "letter", "email", "message", "termination letter", "denial notice")
    has_notice_reference = any(term in all_entity_text for term in notice_terms)
    has_notice_evidence = any(
        entity.type == "evidence" and any(term in _entity_text(entity) for term in notice_terms)
        for entity in effective_entities.values()
    )
    if has_notice_reference and not has_notice_evidence:
        gaps.append({
            'type': 'missing_written_notice',
            'suggested_question': "What written notice, letter, email, or message did you receive, who sent it, and what date is on it?"
        })

    hearing_terms = ("hearing", "grievance", "appeal")
    has_hearing_reference = any(term in all_entity_text for term in hearing_terms)
    hearing_has_date = False
    for entity in effective_entities.values():
        text_value = _entity_text(entity)
        if not any(term in text_value for term in hearing_terms):
            continue
        if entity.type == "date":
            hearing_has_date = True
            break
        if re.search(r"\b(?:19|20)\d{2}\b", text_value):
            hearing_has_date = True
            break
    if has_hearing_reference and not hearing_has_date:
        gaps.append({
            'type': 'missing_hearing_request_date',
            'suggested_question': "When did you request a hearing, grievance, or appeal, and when (if ever) did they respond?"
        })

    response_terms = ("respond", "response", "replied", "reply", "denied", "approved", "ignored", "no response")
    has_response_reference = any(term in all_entity_text for term in response_terms)
    has_response_date = False
    for entity in effective_entities.values():
        text_value = _entity_text(entity)
        if not any(term in text_value for term in response_terms):
            continue
        if _has_date_signal(text_value):
            has_response_date = True
            break
        if entity.type == "date":
            has_response_date = True
            break
    if has_response_reference and not has_response_date:
        gaps.append({
            'type': 'missing_response_dates',
            'suggested_question': "When did each response occur (including any non-response), who gave it, and what exactly did they say?"
        })

    named_staff_entities = [
        entity for entity in effective_entities.values()
        if entity.type == "person" and len((entity.name or "").split()) >= 2
    ]
    has_staff_role = any(
        entity.type == "person" and (entity.attributes or {}).get("role")
        for entity in effective_entities.values()
    )
    if has_staff_role and not named_staff_entities:
        gaps.append({
            'type': 'missing_staff_identity',
            'suggested_question': "Who specifically took the action (full name, role, and team/department if known)?"
        })

    staff_missing_title = [
        entity for entity in named_staff_entities
        if not str((entity.attributes or {}).get("role") or "").strip()
    ]
    if staff_missing_title:
        gaps.append({
            'type': 'missing_staff_title',
            'suggested_question': (
                "For each staff member involved, what was their title/role at the time "
                "(for example manager, HR specialist, hearing officer)?"
            ),
        })

    timeline_action_terms = ("decided", "decision", "denied", "approved", "terminated", "disciplined", "evicted", "notice", "letter", "email")
    has_action_without_exact_date = any(
        entity.type in {"fact", "claim", "evidence"}
        and any(term in _entity_text(entity) for term in timeline_action_terms)
        and not _has_exact_date_signal(_entity_text(entity))
        for entity in effective_entities.values()
    )
    if has_action_without_exact_date:
        gaps.append({
            'type': 'missing_exact_action_dates',
            'suggested_question': (
                "What are the exact dates for each key action (or your best day-level estimate), "
                "including decisions, notices, and responses?"
            ),
        })

    retaliation_claims = [
        entity for entity in claims
        if str((entity.attributes or {}).get("claim_type") or "").strip().lower() == "retaliation"
    ]
    if retaliation_claims:
        has_protected_activity_fact = any(
            entity.type == "fact"
            and any(
                token in _entity_text(entity)
                for token in ("protected activity", "complained", "reported", "grievance", "requested accommodation")
            )
            for entity in effective_entities.values()
        )
        has_adverse_action_fact = any(
            entity.type in {"fact", "claim"}
            and any(
                token in _entity_text(entity)
                for token in ("fired", "terminated", "demoted", "disciplined", "suspended", "reduced")
            )
            for entity in effective_entities.values()
        )
        has_retaliation_timeline = any(
            rel.relation_type in {"occurred_on", "has_timeline_detail"}
            for rel in effective_relationships.values()
        ) or any(entity.type == "date" for entity in effective_entities.values())
        has_protected_activity_date = any(
            entity.type == "fact"
            and "protected" in _entity_text(entity)
            and _has_date_signal(_entity_text(entity))
            for entity in effective_entities.values()
        )
        has_adverse_action_date = any(
            entity.type == "fact"
            and any(token in _entity_text(entity) for token in ("fired", "terminated", "demoted", "disciplined", "suspended", "reduced", "adverse"))
            and _has_date_signal(_entity_text(entity))
            for entity in effective_entities.values()
        )
        has_causation_link_signal = any(
            rel.relation_type in {"caused_by", "causal_link", "follows_protected_activity", "occurred_after"}
            for rel in effective_relationships.values()
        ) or any(
            "because" in _entity_text(entity)
            or "after" in _entity_text(entity)
            or "soon after" in _entity_text(entity)
            for entity in effective_entities.values()
            if entity.type == "fact"
        )
        if not (
            has_protected_activity_fact
            and has_adverse_action_fact
            and has_retaliation_timeline
            and has_causation_link_signal
        ):
            gaps.append({
                'type': 'retaliation_missing_causation',
                'suggested_question': (
                    "What happened immediately after your protected activity, who did it, and on what date "
                    "did each step occur?"
                )
            })
        if not has_causation_link_signal:
            gaps.append({
                'type': 'retaliation_missing_causation_link',
                'suggested_question': (
                    "What protected activity did you engage in, who received it, and what adverse treatment "
                    "followed because of that activity, with dates for each event?"
                ),
            })
        if not (has_protected_activity_date and has_adverse_action_date):
            gaps.append({
                'type': 'retaliation_missing_sequencing_dates',
                'suggested_question': (
                    "Please give the exact date of your protected activity and the exact date of each adverse action, "
                    "plus who took each action."
                ),
            })

    return gaps


def merge_with(self, other_graph: 'KnowledgeGraph'):
    """Merge another knowledge graph without letting confidence erase a different fact.

    Builder-local ids restart on every builder. A colliding id with different
    text is kept as its own record. Verified envelopes stay byte-for-byte on
    their original records. Contradictory asserted facts stay explicit conflicts.
    """
    for entity in other_graph.entities.values():
        if entity.id in self.entities:
            self._assert_compatible_entity_domains(self.entities[entity.id], entity)
    id_remap: Dict[str, str] = {}
    for entity in other_graph.entities.values():
        if entity.id not in self.entities:
            self.add_entity(self._clone_entity(entity, entity.id))
            self._register_merged_assertion(self.entities[entity.id])
            continue
        existing = self.entities[entity.id]
        existing_text = _normalized_record_text(existing)
        incoming_text = _normalized_record_text(entity)
        texts_differ = bool(existing_text and incoming_text and existing_text != incoming_text)
        existing_envelope = assertion_from_provenance(existing.provenance)
        incoming_envelope = assertion_from_provenance(entity.provenance)
        if texts_differ:
            kept_id = self._allocate_record_id(entity.id, self.entities)
            id_remap[entity.id] = kept_id
            kept = self._clone_entity(entity, kept_id)
            self.add_entity(kept)
            self._register_merged_assertion(existing)
            self._register_merged_assertion(kept)
            if (
                existing_envelope is not None
                and incoming_envelope is not None
                and existing_envelope.is_asserted_user_fact
                and incoming_envelope.is_asserted_user_fact
                and existing_envelope.stable_id != incoming_envelope.stable_id
            ):
                self.record_assertion_conflict(
                    existing_envelope.stable_id,
                    incoming_envelope.stable_id,
                    left_entity_id=existing.id,
                    right_entity_id=kept.id,
                )
            continue
        primary_assertion = copy.deepcopy((existing.provenance or {}).get("user_assertion"))
        if (
            entity.confidence > existing.confidence
            and not (
                existing_envelope is not None
                and existing_envelope.is_asserted_user_fact
                and incoming_envelope is not None
                and incoming_envelope.is_asserted_user_fact
                and existing_envelope.stable_id != incoming_envelope.stable_id
            )
        ):
            existing.confidence = entity.confidence
            for key, value in (entity.attributes or {}).items():
                if key not in existing.attributes or existing.attributes.get(key) in (None, "", [], {}):
                    existing.attributes[key] = copy.deepcopy(value)
        existing.provenance = _merge_provenance(existing.provenance, entity.provenance)
        if isinstance(primary_assertion, Mapping):
            existing.provenance["user_assertion"] = primary_assertion
        self._register_merged_assertion(existing)
        if incoming_envelope is not None and incoming_envelope.is_asserted_user_fact:
            self._retain_corroborating_assertion(existing, incoming_envelope)

    for rel in other_graph.relationships.values():
        source_id = id_remap.get(rel.source_id, rel.source_id)
        target_id = id_remap.get(rel.target_id, rel.target_id)
        endpoints_changed = source_id != rel.source_id or target_id != rel.target_id
        if endpoints_changed or (
            rel.id in self.relationships
            and (
                self.relationships[rel.id].source_id != source_id
                or self.relationships[rel.id].target_id != target_id
                or self.relationships[rel.id].relation_type != rel.relation_type
            )
        ):
            # A verified envelope is bound to its original endpoints.
            new_id = self._allocate_record_id(rel.id, self.relationships)
            provenance = copy.deepcopy(rel.provenance or {})
            if endpoints_changed:
                provenance.pop("user_assertion", None)
                provenance.pop("user_assertions", None)
                provenance["endpoint_binding"] = {
                    "dropped_prior_assertion": True,
                    "reason": "endpoint_ids_changed",
                    "prior_relationship_id": rel.id,
                }
            self.add_relationship(Relationship(
                id=new_id,
                source_id=source_id,
                target_id=target_id,
                relation_type=rel.relation_type,
                attributes=copy.deepcopy(rel.attributes or {}),
                confidence=float(rel.confidence),
                source=rel.source,
                provenance=provenance,
            ))
            continue
        if rel.id not in self.relationships:
            self.add_relationship(Relationship(
                id=rel.id,
                source_id=source_id,
                target_id=target_id,
                relation_type=rel.relation_type,
                attributes=copy.deepcopy(rel.attributes or {}),
                confidence=float(rel.confidence),
                source=rel.source,
                provenance=copy.deepcopy(rel.provenance or {}),
            ))
            continue
        existing_rel = self.relationships[rel.id]
        primary_assertion = copy.deepcopy((existing_rel.provenance or {}).get("user_assertion"))
        existing_rel.provenance = _merge_provenance(existing_rel.provenance, rel.provenance)
        if isinstance(primary_assertion, Mapping):
            existing_rel.provenance["user_assertion"] = primary_assertion

    self.metadata['provenance'] = _merge_provenance(
        self.provenance,
        other_graph.provenance,
    )


def build_from_text(
    self,
    text: str,
    *,
    source_context: Optional[Mapping[str, Any]] = None,
    provenance: Optional[Mapping[str, Any]] = None,
    extractor_provenance: Optional[Mapping[str, Any]] = None,
    extracted_entities: Optional[Sequence[Mapping[str, Any]]] = None,
    extracted_relationships: Optional[Sequence[Mapping[str, Any]]] = None,
    include_local_heuristics: bool = True,
) -> KnowledgeGraph:
    """
    Build a knowledge graph from complaint text.

    Caller source context and extractor provenance are carried onto each
    entity and edge as a versioned assertion envelope. Relationship
    source_id and target_id stay graph node ids. A missing or conflicting
    user source does not become an asserted fact.

    Args:
        text: The complaint text to analyze

    Returns:
        A KnowledgeGraph instance
    """
    source_text = text or ""
    caller_context, context_deficiencies = merge_caller_source_context(
        source_context,
        provenance,
        extractor_provenance,
    )
    graph = KnowledgeGraph()
    stored_context = {
        key: value
        for key, value in caller_context.items()
        if key in set(_CALLER_CONTEXT_FIELDS)
    }
    preserved_extractor = _merge_provenance(provenance, extractor_provenance)
    graph.metadata["provenance"] = _merge_provenance(
        graph.provenance,
        {
            "user_assertion_contract": {
                "contract_version": USER_ASSERTION_CONTRACT_VERSION,
                "extractor_version": (
                    _clean_context_text(caller_context.get("extractor_version"))
                    or DEFAULT_USER_ASSERTION_EXTRACTOR_VERSION
                ),
                "source_context": stored_context,
            },
            "extractor": preserved_extractor,
        },
    )

    from integrations.ipfs_datasets.graphs import (
        legal_candidate_role_handoff,
        legal_namespace_kind,
        mint_graph_record_id,
        prepare_private_extraction,
        source_is_legal_norm,
    )

    legal_source = {"metadata": source_context or {}, "provenance": provenance or {}, "attributes": extractor_provenance or {}}
    legal_passage = source_is_legal_norm(legal_source) or source_is_legal_norm(caller_context)
    private_entities: List[Mapping[str, Any]] = []
    private_relationships: List[Mapping[str, Any]] = []
    # Explicit record projection is also used by the standalone adapter.
    # It must not recurse or repeat the owned extractor invocation.
    if legal_passage:
        graph.metadata["factual_candidate_roles"] = legal_candidate_role_handoff()
    elif include_local_heuristics and extracted_entities is None and extracted_relationships is None:
        extraction = prepare_private_extraction(source_text, caller_context)
        graph.metadata["private_extraction"] = {
            key: extraction[key]
            for key in ("status", "diagnostic", "diagnostics", "provenance", "bounded", "factual_candidate_roles")
            if key in extraction
        }
        graph.metadata["factual_candidate_roles"] = extraction.get("factual_candidate_roles") or {}
        if extraction["status"] != "available":
            graph.metadata["private_extraction"]["local_fallback"] = True
        if extraction["status"] == "available":
            private_entities = extraction["entities"]
            private_relationships = extraction["relationships"]

    entities: List[Dict[str, Any]] = []
    if include_local_heuristics:
        for entity_data in self._extract_entities(source_text):
            if isinstance(entity_data, Mapping):
                entities.append(dict(entity_data))
    local_entity_count = len(entities)
    for raw_entity in [*(extracted_entities or []), *private_entities]:
        if not isinstance(raw_entity, Mapping):
            continue
        prepared = dict(raw_entity)
        entity_name = _clean_context_text(prepared.get("name"))
        entity_type = _clean_context_text(prepared.get("type"))
        if not entity_name or not entity_type:
            continue
        prepared["name"] = entity_name
        prepared["type"] = entity_type
        prepared.setdefault("origin", "user")
        entities.append(prepared)

    entity_key_to_id: Dict[str, str] = {}
    local_entity_ids: Set[str] = set()
    for entity_index, entity_data in enumerate(entities):
        entity_is_legal = legal_passage or source_is_legal_norm(entity_data)
        if entity_is_legal:
            entity_data = dict(entity_data)
            entity_data["type"] = "legal_text"
            entity_data["origin"] = "legal"
            entity_data["source"] = "legal"
            entity_data["record_type"] = "legal_text"
            entity_data["legal_hit"] = True
        envelope = envelope_for_extracted_record(
            entity_data,
            source_text=source_text,
            caller_context=caller_context,
            context_deficiencies=context_deficiencies,
            role=_clean_context_text(entity_data.get("type")) or "entity",
        )
        raw_extractor = entity_data.get("provenance") if isinstance(entity_data.get("provenance"), Mapping) else {}
        provenance_payload: Dict[str, Any] = {"user_assertion": envelope.as_dict()}
        carried_extractor = _merge_provenance(preserved_extractor, raw_extractor)
        if carried_extractor:
            provenance_payload["extractor"] = carried_extractor
        attributes = dict(entity_data.get("attributes") if isinstance(entity_data.get("attributes"), Mapping) else {})
        if envelope.factual_record_class:
            attributes["factual_record_class"] = envelope.factual_record_class
        upstream_unverified = attributes.get("upstream_extraction") is True and not entity_is_legal and not envelope.is_asserted_user_fact
        if upstream_unverified:
            # Legacy support consumers inspect entity.type. Keeping a model
            # or source-mismatched record as type=fact would promote it there.
            attributes = dict(attributes)
            attributes["upstream_entity_type"] = str(entity_data.get("type") or "")
            attributes["origin"] = "model"
            attributes["record_type"] = "model_suggestion"
        raw_confidence = entity_data.get("confidence", 0.8)
        if entity_is_legal:
            passage_kind = legal_namespace_kind({"metadata": legal_source, "attributes": entity_data, **dict(caller_context)})
            attributes = dict(attributes)
            attributes["record_kind"] = passage_kind
            attributes["about_complainant"] = False
            entity_id = mint_graph_record_id(
                passage_kind,
                str(len(graph.entities)),
                str(entity_data.get("name") or ""),
                str(caller_context.get("source_id") or ""),
            )
            entity_source = "legal"
        else:
            entity_id = self._get_entity_id()
            entity_source = str(entity_data.get("source") or "complaint")
        entity = Entity(
            id=entity_id,
            type="model_suggestion" if upstream_unverified else str(entity_data.get("type") or ""),
            name=str(entity_data.get("name") or ""),
            attributes=dict(attributes),
            confidence=float(0.8 if raw_confidence is None else raw_confidence),
            source="model" if upstream_unverified else entity_source,
            provenance=provenance_payload,
        )
        graph.add_entity(entity)
        if entity_index < local_entity_count:
            local_entity_ids.add(entity.id)
        extractor_key = _clean_context_text(entity_data.get("extractor_key"))
        if extractor_key:
            entity_key_to_id[extractor_key] = entity.id

    relationships: List[Dict[str, Any]] = []
    if include_local_heuristics:
        # Keep existing heuristic/LLM relationships confined to their original
        # local records; upstream model mentions cannot acquire support here.
        local_graph = graph
        if private_entities:
            local_graph = copy.copy(graph)
            local_graph.entities = {key: value for key, value in graph.entities.items() if key in local_entity_ids}
        for rel_data in self._extract_relationships(source_text, local_graph):
            if isinstance(rel_data, Mapping):
                relationships.append(dict(rel_data))
    for raw_relationship in [*(extracted_relationships or []), *private_relationships]:
        if not isinstance(raw_relationship, Mapping):
            continue
        prepared_relationship = dict(raw_relationship)
        prepared_relationship.setdefault("origin", "user")
        source_endpoint = _resolve_graph_endpoint(
            prepared_relationship,
            graph,
            entity_key_to_id,
            "source_id",
            "source_key",
        )
        target_endpoint = _resolve_graph_endpoint(
            prepared_relationship,
            graph,
            entity_key_to_id,
            "target_id",
            "target_key",
        )
        if not source_endpoint or not target_endpoint:
            continue
        prepared_relationship["source_id"] = source_endpoint
        prepared_relationship["target_id"] = target_endpoint
        if prepared_relationship.get("type") and not prepared_relationship.get("relation_type"):
            prepared_relationship["relation_type"] = prepared_relationship.get("type")
        relationships.append(prepared_relationship)

    for rel_data in relationships:
        source_endpoint = _clean_context_text(rel_data.get("source_id"))
        target_endpoint = _clean_context_text(rel_data.get("target_id"))
        if source_endpoint not in graph.entities or target_endpoint not in graph.entities:
            continue
        relation_type = _clean_context_text(rel_data.get("type") or rel_data.get("relation_type"))
        if not relation_type:
            continue
        relationship_record = dict(rel_data)
        relationship_record["relation_type"] = relation_type
        relationship_record["type"] = relation_type
        if legal_passage:
            relationship_record["record_type"] = "legal_text"
            relationship_record["origin"] = "legal"
            relationship_record["legal_hit"] = True
        envelope = envelope_for_extracted_record(
            relationship_record,
            source_text=source_text,
            caller_context=caller_context,
            context_deficiencies=context_deficiencies,
            role=relation_type,
        )
        if envelope.is_asserted_user_fact and any(
            not (assertion_from_provenance(graph.entities[endpoint].provenance)
                 and assertion_from_provenance(graph.entities[endpoint].provenance).is_asserted_user_fact)
            for endpoint in (source_endpoint, target_endpoint)
        ):
            envelope = replace(envelope, record_type="unverified_candidate", source_kind="unverified",
                assertion_status="unverified", deficiencies=("unverified_relationship_endpoint",))
        raw_extractor = rel_data.get("provenance") if isinstance(rel_data.get("provenance"), Mapping) else {}
        provenance_payload = {"user_assertion": envelope.as_dict()}
        carried_extractor = _merge_provenance(preserved_extractor, raw_extractor)
        if carried_extractor:
            provenance_payload["extractor"] = carried_extractor
        attributes = dict(rel_data.get("attributes") if isinstance(rel_data.get("attributes"), Mapping) else {})
        if envelope.factual_record_class:
            attributes["factual_record_class"] = envelope.factual_record_class
        upstream_support_suggestion = (attributes.get("upstream_extraction") is True
            and not envelope.is_asserted_user_fact
            and relation_type in (_SUPPORT_RELATION_TYPES | {"has_fact"}))
        if upstream_support_suggestion:
            attributes = dict(attributes)
            attributes["upstream_relationship_type"] = relation_type
            attributes["origin"] = "model"
            attributes["record_type"] = "model_suggestion"
            relation_type = "model_suggestion"
        raw_confidence = rel_data.get("confidence", 0.8)
        graph.add_relationship(
            Relationship(
                id=self._get_relationship_id(),
                source_id=source_endpoint,
                target_id=target_endpoint,
                relation_type=relation_type,
                attributes=dict(attributes),
                confidence=float(0.8 if raw_confidence is None else raw_confidence),
                source="model" if upstream_support_suggestion else ("legal" if legal_passage else str(rel_data.get("source") or "complaint")),
                provenance=provenance_payload,
            )
        )

    if self.actor_critic_enabled:
        entity_scores = [
            float((entity.attributes or {}).get("actor_critic_score", 0.0) or 0.0)
            for entity in graph.entities.values()
        ]
        relationship_scores = [
            float((rel.attributes or {}).get("actor_critic_score", 0.0) or 0.0)
            for rel in graph.relationships.values()
        ]
        graph.metadata["actor_critic"] = {
            "enabled": True,
            "entity_count": len(entity_scores),
            "relationship_count": len(relationship_scores),
            "avg_entity_score": (
                round(sum(entity_scores) / len(entity_scores), 4) if entity_scores else 0.0
            ),
            "avg_relationship_score": (
                round(sum(relationship_scores) / len(relationship_scores), 4) if relationship_scores else 0.0
            ),
            "entity_score_floor": float(self.min_entity_actor_critic_score),
            "relationship_score_floor": float(self.min_relationship_actor_critic_score),
        }

    link_narrative = bool(isinstance(source_context, Mapping) and source_context.get("link_narrative") is True)
    if include_local_heuristics and not legal_passage and link_narrative:
        attach_narrative_source_records(graph, source_text, self)

    logger.info(f"Built knowledge graph: {graph.summary()}")

    # Batch 220: Track graph building
    self._built_graphs.append(graph)
    self._text_processed_count += 1

    return graph
