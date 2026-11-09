"""Graph query and snapshot helpers delegated from the datasets graph adapter."""

from __future__ import annotations

from integrations.ipfs_datasets.graphs import (
    GRAPHS_ERROR,
    GraphEntity,
    GraphPayload,
    GraphRelationship,
    GraphSnapshotResult,
    GraphSupportMatch,
    GraphSupportResult,
    GraphSupportSummary,
    KNOWLEDGE_GRAPHS_AVAILABLE,
    Mapping,
    _GRAPH_SNAPSHOT_REGISTRY,
    _PRIVATE_EXTRACTION_TEXT_LIMIT,
    _PRIVATE_EXTRACTION_TIMEOUT_SECONDS,
    _PRIVATE_EXTRACTOR_OPTIONS,
    _caller_source_context,
    _cluster_semantically_similar_results,
    _extract_fact_registry_summary,
    _fact_dedup_key,
    _fact_matches_filters,
    _graph_query_contract,
    _graph_storage_error,
    _graph_storage_module,
    _persist_nodes_through_client,
    _run_private_extraction,
    _score_fact_match,
    _split_sentences,
    _stable_identifier,
    _write_private_graph_ciphertext,
    build_graph_persistence_request,
    build_graph_support_query,
    json,
    legal_namespace_kind,
    mint_graph_record_id,
    persist_private_graph_snapshot,
    resume_graph_revisions,
    source_is_legal_norm,
    with_adapter_metadata,
)

def query_graph_support(
    claim_element_id: str,
    *,
    graph_id: Optional[str] = None,
    graph_version: Optional[str] = None,
    support_facts: Optional[List[Dict[str, Any]]] = None,
    claim_type: Optional[str] = None,
    claim_element_text: Optional[str] = None,
    max_results: int = 10,
    filters: Optional[Mapping[str, Any]] = None,
    provenance: Optional[Mapping[str, Any]] = None,
    query_backend: Optional[GraphQuery] = None,
) -> Dict[str, Any]:
    query = build_graph_support_query(
        claim_element_id,
        graph_id=graph_id,
        graph_version=graph_version,
        claim_type=claim_type,
        claim_element_text=claim_element_text,
        max_results=max_results,
        filters=filters,
        provenance=provenance,
    )
    backend_error: Optional[Exception] = None
    if query_backend is not None:
        try:
            backend_response = query_backend.query_support(query)
            if not isinstance(backend_response, Mapping):
                raise TypeError("graph query backend must return a mapping")
            normalized_response = dict(backend_response)
            normalized_response.setdefault("status", "available")
            normalized_response.setdefault("graph_id", query["graph_id"])
            normalized_response.setdefault("graph_version", query["graph_version"])
            normalized_response.setdefault("claim_element_id", query["claim_element_id"])
            normalized_response.setdefault("claim_type", query["claim_type"])
            normalized_response.setdefault("claim_element_text", query["claim_element_text"])
            normalized_response.setdefault("results", [])
            normalized_response.setdefault("summary", {"result_count": len(normalized_response["results"])})
            normalized_response.setdefault("provenance", query["provenance"])
            normalized_response["query"] = query
            return with_adapter_metadata(
                normalized_response,
                operation="query_graph_support",
                backend_available=True,
                implementation_status="backend",
                extra_metadata={
                    "graph_id": query["graph_id"],
                    "graph_version": query["graph_version"],
                },
            )
        except Exception as exc:  # A backend failure must not remove local support review.
            backend_error = exc

    facts = [
        fact
        for fact in support_facts or []
        if isinstance(fact, Mapping) and _fact_matches_filters(fact, query["filters"])
    ]
    ranked_results = []
    support_by_kind: Dict[str, int] = {}
    support_by_source: Dict[str, int] = {}
    source_family_counts: Dict[str, int] = {}
    record_scope_counts: Dict[str, int] = {}
    artifact_family_counts: Dict[str, int] = {}
    corpus_family_counts: Dict[str, int] = {}
    content_origin_counts: Dict[str, int] = {}
    parse_source_counts: Dict[str, int] = {}
    input_format_counts: Dict[str, int] = {}
    quality_tier_counts: Dict[str, int] = {}
    unique_source_refs = set()
    unique_source_records = set()
    passage_anchored_count = 0
    deduped_results: Dict[str, Dict[str, Any]] = {}

    def _count(target: Dict[str, int], value: Any) -> None:
        text = str(value or "").strip()
        if text:
            target[text] = target.get(text, 0) + 1

    for fact in facts:
        score = _score_fact_match(fact, claim_element_id, claim_element_text or "")
        result = {
            **fact,
            "score": score,
            "matched_claim_element": bool(
                (claim_element_id and str(fact.get("claim_element_id") or "") == claim_element_id)
                or (claim_element_text and str(fact.get("claim_element_text") or "") == claim_element_text)
            ),
            "duplicate_count": 1,
        }
        support_kind = str(fact.get("support_kind") or "unknown")
        source_table = str(fact.get("source_table") or "unknown")
        support_by_kind[support_kind] = support_by_kind.get(support_kind, 0) + 1
        support_by_source[source_table] = support_by_source.get(source_table, 0) + 1
        source_family = str(fact.get("source_family") or "").strip()
        source_record_id = fact.get("source_record_id")
        source_ref = str(fact.get("source_ref") or "").strip()
        source_passage = fact.get("source_passage") if isinstance(fact.get("source_passage"), dict) else {}
        if source_ref:
            unique_source_refs.add(source_ref)
        if source_family and source_record_id not in (None, ""):
            unique_source_records.add((source_family, str(source_record_id)))
        if source_passage.get("chunk_id") or fact.get("chunk_id"):
            passage_anchored_count += 1
        _count(source_family_counts, source_family)
        _count(record_scope_counts, fact.get("record_scope"))
        _count(artifact_family_counts, fact.get("artifact_family"))
        _count(corpus_family_counts, fact.get("corpus_family"))
        _count(content_origin_counts, fact.get("content_origin"))
        _count(parse_source_counts, fact.get("parse_source"))
        _count(input_format_counts, fact.get("input_format"))
        _count(quality_tier_counts, fact.get("quality_tier"))

        dedup_key = _fact_dedup_key(result)
        existing = deduped_results.get(dedup_key)
        if existing is None:
            deduped_results[dedup_key] = {
                **result,
                "support_kind_set": [support_kind],
                "source_table_set": [source_table],
            }
            continue

        existing["duplicate_count"] += 1
        existing["score"] = max(existing.get("score", 0.0), result["score"])
        existing["confidence"] = max(existing.get("confidence", 0.0), result.get("confidence", 0.0))
        if support_kind not in existing["support_kind_set"]:
            existing["support_kind_set"].append(support_kind)
        if source_table not in existing["source_table_set"]:
            existing["source_table_set"].append(source_table)

    ranked_results = _cluster_semantically_similar_results(list(deduped_results.values()))

    ranked_results.sort(
        key=lambda item: (
            item.get("score", 0.0),
            item.get("matched_claim_element", False),
            item.get("confidence", 0.0),
            item.get("duplicate_count", 0),
        ),
        reverse=True,
    )

    limited_results = ranked_results[:max_results]
    unique_fact_count = len(deduped_results)
    duplicate_fact_count = max(len(facts) - unique_fact_count, 0)
    semantic_cluster_count = len(ranked_results)
    semantic_duplicate_count = max(unique_fact_count - semantic_cluster_count, 0)

    typed_results = [
        GraphSupportMatch(
            fact_id=str(item.get("fact_id") or ""),
            text=str(item.get("text") or ""),
            score=float(item.get("score", 0.0) or 0.0),
            confidence=float(item.get("confidence", 0.0) or 0.0),
            matched_claim_element=bool(item.get("matched_claim_element", False)),
            duplicate_count=int(item.get("duplicate_count", 1) or 1),
            cluster_size=int(item.get("cluster_size", item.get("duplicate_count", 1)) or 1),
            cluster_texts=[str(text) for text in item.get("cluster_texts", []) or []],
            support_kind=str(item.get("support_kind") or ""),
            source_table=str(item.get("source_table") or ""),
            support_kind_set=[str(kind) for kind in item.get("support_kind_set", []) or []],
            source_table_set=[str(source) for source in item.get("source_table_set", []) or []],
            claim_element_id=str(item.get("claim_element_id") or ""),
            claim_element_text=str(item.get("claim_element_text") or ""),
            support_ref=str(item.get("support_ref") or ""),
            support_label=str(item.get("support_label") or ""),
            source_family=str(item.get("source_family") or ""),
            source_record_id=item.get("source_record_id"),
            source_ref=str(item.get("source_ref") or ""),
            record_scope=str(item.get("record_scope") or ""),
            artifact_family=str(item.get("artifact_family") or ""),
            corpus_family=str(item.get("corpus_family") or ""),
            content_origin=str(item.get("content_origin") or ""),
            parse_source=str(item.get("parse_source") or ""),
            input_format=str(item.get("input_format") or ""),
            quality_tier=str(item.get("quality_tier") or ""),
            quality_score=float(item.get("quality_score", 0.0) or 0.0),
            evidence_record_id=item.get("evidence_record_id"),
            authority_record_id=item.get("authority_record_id"),
            metadata={
                key: value
                for key, value in item.items()
                if key not in {
                    "fact_id",
                    "text",
                    "score",
                    "confidence",
                    "matched_claim_element",
                    "duplicate_count",
                    "cluster_size",
                    "cluster_texts",
                    "support_kind",
                    "source_table",
                    "support_kind_set",
                    "source_table_set",
                    "claim_element_id",
                    "claim_element_text",
                    "support_ref",
                    "support_label",
                    "source_family",
                    "source_record_id",
                    "source_ref",
                    "record_scope",
                    "artifact_family",
                    "corpus_family",
                    "content_origin",
                    "parse_source",
                    "input_format",
                    "quality_tier",
                    "quality_score",
                    "evidence_record_id",
                    "authority_record_id",
                }
            },
        )
        for item in limited_results
    ]

    graph_contract = _graph_query_contract(graph_id)
    payload = with_adapter_metadata(
        GraphSupportResult(
            status="available-fallback" if KNOWLEDGE_GRAPHS_AVAILABLE else "unavailable",
            claim_element_id=claim_element_id,
            claim_type=claim_type or "",
            claim_element_text=claim_element_text or "",
            graph_id=graph_id or "",
            results=typed_results,
            summary=GraphSupportSummary(
                result_count=len(limited_results),
                total_fact_count=len(facts),
                unique_fact_count=unique_fact_count,
                duplicate_fact_count=duplicate_fact_count,
                semantic_cluster_count=semantic_cluster_count,
                semantic_duplicate_count=semantic_duplicate_count,
                unique_source_ref_count=len(unique_source_refs),
                unique_source_record_count=len(unique_source_records),
                passage_anchored_count=passage_anchored_count,
                support_by_kind=support_by_kind,
                support_by_source=support_by_source,
                source_family_counts=source_family_counts,
                record_scope_counts=record_scope_counts,
                artifact_family_counts=artifact_family_counts,
                corpus_family_counts=corpus_family_counts,
                content_origin_counts=content_origin_counts,
                parse_source_counts=parse_source_counts,
                input_format_counts=input_format_counts,
                quality_tier_counts=quality_tier_counts,
                max_score=ranked_results[0]["score"] if ranked_results else 0.0,
            ),
            metadata={},
        ).as_dict(),
        operation="query_graph_support",
        backend_available=KNOWLEDGE_GRAPHS_AVAILABLE,
        degraded_reason=(
            backend_error
            or (GRAPHS_ERROR if not KNOWLEDGE_GRAPHS_AVAILABLE else None)
        ),
        implementation_status="fallback" if facts or KNOWLEDGE_GRAPHS_AVAILABLE else "unavailable",
        extra_metadata={
            **graph_contract,
            "graph_id": query["graph_id"],
            "graph_version": query["graph_version"],
            "query_filters": query["filters"],
        },
    )
    payload["graph_version"] = query["graph_version"]
    payload["provenance"] = query["provenance"]
    payload["query"] = query
    for result in payload.get("results", []):
        result_metadata = result.get("metadata") if isinstance(result, dict) else None
        if isinstance(result_metadata, dict) and isinstance(result_metadata.get("provenance"), dict):
            result["provenance"] = dict(result_metadata["provenance"])
    return payload


def persist_graph_snapshot(
    graph_payload: Dict[str, Any],
    *,
    graph_id: Optional[str] = None,
    graph_version: Optional[str] = None,
    graph_changed: Optional[bool] = None,
    existing_graph: bool = False,
    persistence_metadata: Optional[Dict[str, Any]] = None,
    provenance: Optional[Mapping[str, Any]] = None,
    persistence: Optional[GraphPersistence] = None,
    private_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if private_context is not None:
        return persist_private_graph_snapshot(graph_payload, private_context, graph_id=graph_id)
    if not isinstance(graph_payload, Mapping):
        raise TypeError("graph_payload must be a mapping")

    request = build_graph_persistence_request(
        graph_payload,
        graph_id=graph_id,
        graph_version=graph_version,
        provenance=provenance,
        metadata=persistence_metadata,
    )
    entity_count = len(request["entities"])
    relationship_count = len(request["relationships"])
    source_id = str(graph_payload.get("source_id") or "")
    metadata = graph_payload.get("metadata", {}) if isinstance(graph_payload.get("metadata"), dict) else {}
    derived_graph_changed = bool(graph_changed) if graph_changed is not None else bool(entity_count or relationship_count) and not existing_graph
    created = bool(derived_graph_changed and not existing_graph)
    reused = bool(existing_graph and not created)
    stable_graph_id = request["graph_id"]
    fact_registry_summary = _extract_fact_registry_summary(
        dict(graph_payload),
        metadata,
        persistence_metadata,
    )
    backend_result: Dict[str, Any] = {}
    persistence_error: Optional[Exception] = None
    if persistence is not None:
        try:
            raw_result = persistence.persist_snapshot(request)
            if not isinstance(raw_result, Mapping):
                raise TypeError("graph persistence backend must return a mapping")
            backend_result = dict(raw_result)
        except Exception as exc:  # Keep snapshot metadata available in degraded mode.
            persistence_error = exc

    backend_used = persistence is not None and persistence_error is None
    snapshot_metadata = {
        "source_id": source_id,
        **(persistence_metadata or {}),
        "fact_registry_summary": fact_registry_summary,
        "lineage": {
            "status": str(graph_payload.get("status") or ""),
            "text_length": metadata.get("text_length", 0),
            "sentence_count": metadata.get("sentence_count", 0),
        },
    }

    if persistence is None:
        client_contract = _persist_nodes_through_client(stable_graph_id, request)
        existing_snapshot = _GRAPH_SNAPSHOT_REGISTRY.get(stable_graph_id)
        local_created = existing_snapshot is None and not existing_graph
        local_reused = existing_snapshot is not None or existing_graph
        snapshot_metadata.update(
            {
                "persistence_scope": "adapter_memory",
                "backend_storage_available": _graph_storage_module is not None,
                **client_contract,
            }
        )
        snapshot_record = {
            "graph_id": stable_graph_id,
            "source_id": source_id,
            "status": "stored-fallback",
            "node_count": entity_count,
            "edge_count": relationship_count,
            "entities": list(request["entities"]),
            "relationships": list(request["relationships"]),
            "fact_registry_summary": fact_registry_summary,
            "metadata": snapshot_metadata,
            "graph_version": request["graph_version"],
            "snapshot_id": request["snapshot_id"],
            "content_hash": request["content_hash"],
            "provenance": dict(request["provenance"]),
        }
        if client_contract.get("client_write_ok"):
            try:
                resumed = resume_graph_revisions(stable_graph_id)
            except Exception:
                resumed = {}
            if resumed:
                snapshot_record["revisions"] = list(resumed.get("revisions") or [])
                snapshot_record["superseded_facts"] = list(resumed.get("superseded_facts") or [])
                snapshot_record["cross_graph_links"] = list(resumed.get("cross_graph_links") or [])
                snapshot_record["provenance_chain"] = list(resumed.get("provenance") or [])
        snapshot_record["plaintext_publication"] = False
        _GRAPH_SNAPSHOT_REGISTRY[stable_graph_id] = snapshot_record
        payload = with_adapter_metadata(
            GraphSnapshotResult(
                status="stored-fallback",
                graph_id=stable_graph_id,
                persisted=True,
                created=(
                    local_created
                    if graph_changed is None
                    else bool(created and not existing_snapshot)
                ),
                reused=(
                    local_reused
                    if graph_changed is None
                    else bool(reused or existing_snapshot)
                ),
                node_count=entity_count,
                edge_count=relationship_count,
                metadata=snapshot_metadata,
            ).as_dict(),
            operation="persist_graph_snapshot",
            backend_available=_graph_storage_module is not None,
            degraded_reason=_graph_storage_error,
            implementation_status="fallback",
            extra_metadata={
                "graph_version": request["graph_version"],
                "snapshot_id": request["snapshot_id"],
                "content_hash": request["content_hash"],
                **client_contract,
                "persistence_scope": "adapter_memory",
            },
        )
    else:
        base_payload = GraphSnapshotResult(
            status=(
                str(backend_result.get("status") or "persisted")
                if backend_used
                else "degraded"
            ),
            graph_id=stable_graph_id,
            persisted=(
                bool(backend_result.get("persisted", True))
                if backend_used
                else False
            ),
            created=(
                bool(backend_result.get("created", created))
                if backend_used
                else created
            ),
            reused=(
                bool(backend_result.get("reused", reused))
                if backend_used
                else reused
            ),
            node_count=(
                int(backend_result.get("node_count", entity_count) or 0)
                if backend_used
                else entity_count
            ),
            edge_count=(
                int(backend_result.get("edge_count", relationship_count) or 0)
                if backend_used
                else relationship_count
            ),
            metadata=snapshot_metadata,
        ).as_dict()
        if backend_result:
            for key, value in backend_result.items():
                if key != "metadata":
                    base_payload[key] = value
            if isinstance(backend_result.get("metadata"), Mapping):
                base_payload["metadata"].update(backend_result["metadata"])
        payload = with_adapter_metadata(
            base_payload,
            operation="persist_graph_snapshot",
            backend_available=backend_used,
            degraded_reason=persistence_error,
            implementation_status="backend" if backend_used else "degraded",
            extra_metadata={
                "graph_version": request["graph_version"],
                "snapshot_id": request["snapshot_id"],
                "content_hash": request["content_hash"],
            },
        )
    payload["graph_version"] = request["graph_version"]
    payload["snapshot_id"] = request["snapshot_id"]
    payload["content_hash"] = request["content_hash"]
    backend_provenance = backend_result.get("provenance")
    merged_provenance = dict(request["provenance"])
    if isinstance(backend_provenance, Mapping):
        merged_provenance.update(
            {
                str(key): value
                for key, value in backend_provenance.items()
                if value not in (None, "", [], (), {})
            }
        )
    payload["graph_id"] = request["graph_id"]
    payload["provenance"] = merged_provenance
    return payload


def extract_graph_from_text(
    text: str,
    *,
    source_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata = metadata or {}
    entities: List[GraphEntity] = []
    relationships: List[GraphRelationship] = []
    artifact_id = source_id or metadata.get("artifact_id") or ""
    claim_element_id = str(metadata.get("claim_element_id") or "").strip()
    claim_element_text = str(metadata.get("claim_element_text") or metadata.get("claim_element") or "").strip()
    legal_passage = source_is_legal_norm(metadata)
    embedded_provenance = metadata.get("provenance")
    graph_provenance: Dict[str, Any] = (
        dict(embedded_provenance) if isinstance(embedded_provenance, Mapping) else {}
    )
    if artifact_id:
        graph_provenance.setdefault("source_id", str(artifact_id))
    for provenance_key in (
        "source_type",
        "source_record_id",
        "source_ref",
        "source_url",
        "source_system",
        "content_hash",
        "acquired_at",
        "parser_version",
        "extraction_version",
    ):
        if metadata.get(provenance_key) not in (None, ""):
            graph_provenance.setdefault(provenance_key, metadata[provenance_key])

    if artifact_id:
        entities.append(
            GraphEntity(
                entity_id=artifact_id,
                entity_type="artifact",
                name=str(metadata.get("title") or metadata.get("filename") or artifact_id),
                confidence=1.0,
                attributes={
                    "source_id": artifact_id,
                    "source_url": metadata.get("source_url", ""),
                    "mime_type": metadata.get("mime_type", ""),
                    "provenance": graph_provenance,
                },
            )
        )

    claim_node_id = ""
    if claim_element_id or claim_element_text:
        claim_node_id = claim_element_id or _stable_identifier("claim_element", claim_element_text)
        entities.append(
            GraphEntity(
                entity_id=claim_node_id,
                entity_type="claim_element",
                name=claim_element_text or claim_element_id,
                confidence=1.0,
                attributes={
                    "claim_element_id": claim_element_id,
                    "claim_element_text": claim_element_text,
                    "claim_type": metadata.get("claim_type", ""),
                    "provenance": graph_provenance,
                },
            )
        )

    submitted = text if isinstance(text, str) else ""
    timeout_raw = metadata.get("extraction_timeout_seconds", _PRIVATE_EXTRACTION_TIMEOUT_SECONDS)
    try:
        timeout_seconds = float(timeout_raw)
    except (TypeError, ValueError):
        timeout_seconds = _PRIVATE_EXTRACTION_TIMEOUT_SECONDS
    timeout_seconds = min(max(timeout_seconds, 0.01), _PRIVATE_EXTRACTION_TIMEOUT_SECONDS)
    private_extraction: Dict[str, Any] = {
        "method": "extract_knowledge_graph",
        "options": dict(_PRIVATE_EXTRACTOR_OPTIONS),
        "diagnostics": [],
    }
    sentences: List[str] = []
    payload_status = "unavailable"
    backend_available = False
    degraded_reason: Optional[str] = None
    implementation_status = "unavailable"

    if not submitted.strip():
        private_extraction["status"] = "degraded"
        private_extraction["diagnostic"] = "input_empty"
        private_extraction["diagnostics"] = ["input_empty"]
        payload_status = "degraded"
        degraded_reason = "input_empty"
        implementation_status = "degraded"
    elif len(submitted) > _PRIVATE_EXTRACTION_TEXT_LIMIT:
        private_extraction["status"] = "degraded"
        private_extraction["diagnostic"] = "input_bound_exceeded"
        private_extraction["diagnostics"] = ["input_bound_exceeded"]
        payload_status = "degraded"
        degraded_reason = "input_bound_exceeded"
        implementation_status = "degraded"
    elif legal_passage:
        sentences = _split_sentences(submitted)
        if not sentences and submitted.strip():
            sentences = [submitted.strip()]
        passage_kind = legal_namespace_kind(metadata)
        for index, sentence in enumerate(sentences[:25]):
            fact_id = mint_graph_record_id(
                passage_kind, artifact_id or source_id or "legal", str(index), sentence,
            )
            entities.append(
                GraphEntity(
                    entity_id=fact_id,
                    entity_type=passage_kind,
                    name=sentence[:120],
                    confidence=0.6,
                    attributes={
                        "text": sentence,
                        "sentence_index": index,
                        "source_id": artifact_id,
                        "record_kind": passage_kind,
                        "about_complainant": False,
                        "extraction_mode": "legal_heuristic",
                        "provenance": graph_provenance,
                    },
                )
            )
            if artifact_id:
                relationships.append(
                    GraphRelationship(
                        relationship_id=_stable_identifier("rel", artifact_id, fact_id, "cites_authority"),
                        source_id=artifact_id,
                        target_id=fact_id,
                        relation_type="cites_authority",
                        confidence=1.0,
                        attributes={"sentence_index": index, "provenance": graph_provenance, "extraction_mode": "legal_heuristic"},
                    )
                )
        private_extraction["status"] = "legal_heuristic"
        private_extraction["diagnostic"] = "legal_passage_not_private_extraction"
        private_extraction["diagnostics"] = ["legal_passage_not_private_extraction"]
        payload_status = "available-fallback"
        implementation_status = "legal_heuristic"
        backend_available = False
    else:
        caller_context = _caller_source_context(str(artifact_id or source_id or ""), metadata)
        extraction = _run_private_extraction(submitted, caller_context, timeout_seconds)
        private_extraction.update({
            "status": extraction["status"],
            "diagnostic": extraction["diagnostic"],
            "diagnostics": list(extraction["diagnostics"]),
            "provenance": extraction["provenance"],
            "bounded": extraction.get("bounded", True),
            "factual_candidate_roles": extraction.get("factual_candidate_roles"),
        })
        if extraction["status"] == "available":
            entities.extend(extraction["entities"])
            relationships.extend(extraction["relationships"])
            sentences = _split_sentences(submitted)
            if not sentences and submitted.strip():
                sentences = [submitted.strip()]
            payload_status = "available"
            backend_available = True
            implementation_status = "upstream"
        else:
            degraded_reason = str(extraction["diagnostic"] or extraction["status"])
            payload_status = extraction["status"]
            backend_available = False
            implementation_status = extraction["status"]

    return with_adapter_metadata(
        GraphPayload(
            status=payload_status,
            source_id=source_id or "",
            entities=entities,
            relationships=relationships,
            metadata={
                **metadata,
                "text_length": len(submitted),
                "sentence_count": len(sentences),
                "provenance": graph_provenance,
                "private_extraction": private_extraction,
            },
        ).as_dict(),
        operation="extract_graph_from_text",
        backend_available=backend_available,
        degraded_reason=degraded_reason,
        implementation_status=implementation_status,
        extra_metadata={"private_extraction": private_extraction},
    )


def publish_private_graph_case_manifest(
    graph_payload: Dict[str, Any],
    private_context: Mapping[str, Any],
) -> Dict[str, Any]:
    """Bind a private graph into the case manifest. Public names stay opaque hashes.

    The filename, node labels, and provenance travel only inside the encrypted
    manifest and the sealed fact-graph envelope. The destination filename is the
    manifest generation.
    """
    from integrations.private_storage import (
        CaseManifestConflict,
        PrivateRevisionError,
        PrivateStorageError,
        publish_case_manifest,
        read_case_manifest,
    )

    if not isinstance(graph_payload, Mapping):
        raise TypeError("graph_payload must be a mapping")
    repository = private_context.get("case_manifest_repository")
    if not repository:
        raise PrivateRevisionError("case manifest repository is missing", code="role_missing", state="recoverable")
    supplied = private_context.get("case_artifacts")
    if not isinstance(supplied, Mapping):
        raise PrivateRevisionError("case artifacts are missing", code="role_missing", state="recoverable")
    graph_body = json.dumps(dict(graph_payload), sort_keys=True, default=str).encode("utf-8")
    artifacts: Dict[str, Any] = {}
    for role in ("answer", "fact_graph", "legal_rule_source", "evaluation", "proof"):
        item = supplied.get(role)
        if role == "fact_graph":
            revision = role
            if isinstance(item, Mapping) and item.get("revision"):
                revision = str(item["revision"])
            artifacts[role] = {"body": graph_body, "revision": revision}
            continue
        if isinstance(item, (bytes, bytearray)):
            artifacts[role] = {"body": bytes(item), "revision": role}
        elif isinstance(item, Mapping) and isinstance(item.get("body"), (bytes, bytearray)):
            artifacts[role] = {
                "body": bytes(item["body"]),
                "revision": str(item.get("revision") or role),
            }
        else:
            raise PrivateRevisionError("case role is missing", code="role_missing", state="recoverable")
    labels = private_context.get("labels")
    if labels is None:
        labels = []
        for entity in graph_payload.get("entities") or []:
            if isinstance(entity, Mapping):
                labels.append(str(entity.get("label") or entity.get("text") or ""))
    provenance = private_context.get("provenance")
    if not isinstance(provenance, Mapping):
        raw_provenance = graph_payload.get("provenance")
        provenance = dict(raw_provenance) if isinstance(raw_provenance, Mapping) else {}
    filename = str(private_context.get("filename") or "")
    try:
        publication = publish_case_manifest(
            repository,
            tenant_id=str(private_context["tenant_id"]),
            case_id=str(private_context["case_id"]),
            principal_id=str(private_context.get("principal_id") or private_context["tenant_id"]),
            key=private_context.get("key"),
            key_id=private_context.get("key_id"),
            expected_head=str(private_context.get("expected_head") or ""),
            expected_hash=str(private_context.get("expected_hash") or ""),
            artifacts=artifacts,
            private_names={"filename": filename, "labels": list(labels), "provenance": dict(provenance)},
            backend=str(private_context.get("case_backend") or "local"),
            iroh_store=private_context.get("iroh_store"),
        )
    except CaseManifestConflict:
        return {
            "status": "conflict",
            "persisted": False,
            "committed": False,
            "verified": False,
            "private_artifact": True,
            "private_indexing": "unsupported",
            "plaintext_catalog": False,
            "plaintext_index": False,
            "code": "manifest_conflict",
            "overwrites_existing": False,
            "minted_completion": False,
        }
    except PrivateStorageError as exc:
        return {
            "status": "unlock_needed" if getattr(exc, "code", "") == "key_unavailable" else "recoverable",
            "persisted": False,
            "committed": False,
            "verified": False,
            "private_artifact": True,
            "private_indexing": "unsupported",
            "plaintext_catalog": False,
            "code": str(getattr(exc, "code", "") or "private_graph_failed"),
            "overwrites_existing": False,
            "minted_completion": False,
        }
    destination = private_context.get("destination_dir")
    if destination is not None:
        opened = read_case_manifest(
            repository,
            tenant_id=str(private_context["tenant_id"]),
            case_id=str(private_context["case_id"]),
            principal_id=str(private_context.get("principal_id") or private_context["tenant_id"]),
            key=private_context.get("key"),
            key_id=private_context.get("key_id"),
        )
        envelope = (opened or {}).get("envelopes", {}).get("fact_graph")
        if not isinstance(envelope, (bytes, bytearray)) or not publication.generation:
            return {
                "status": "recoverable",
                "persisted": False,
                "verified": False,
                "private_artifact": True,
                "plaintext_catalog": False,
                "code": "readback_mismatch",
                "overwrites_existing": False,
                "minted_completion": False,
            }
        _write_private_graph_ciphertext(destination, publication.generation + ".bin", bytes(envelope))
    public = publication.as_dict()
    public.update({
        "status": "stored-private",
        "persisted": True,
        "verified": True,
        "private_artifact": True,
        "private_indexing": "unsupported",
        "plaintext_catalog": False,
        "plaintext_index": False,
        "opaque_ref": publication.generation,
        "overwrites_existing": False,
    })
    return public
