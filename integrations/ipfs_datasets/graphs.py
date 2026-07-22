from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Mapping, Optional, Protocol, TypedDict, runtime_checkable

from .loader import import_module_optional
from .types import (
    GraphEntity,
    GraphPayload,
    GraphRelationship,
    GraphSnapshotResult,
    GraphSupportMatch,
    GraphSupportResult,
    GraphSupportSummary,
    with_adapter_metadata,
)


_knowledge_graphs_module, _knowledge_graphs_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs"
)
_graph_extraction_module, _graph_extraction_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs.extraction"
)
_graph_query_module, _graph_query_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs.query"
)
_graph_storage_module, _graph_storage_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs.storage"
)
_graph_lineage_module, _graph_lineage_error = import_module_optional(
    "ipfs_datasets_py.knowledge_graphs.lineage"
)

KNOWLEDGE_GRAPHS_AVAILABLE = any(
    value is not None
    for value in (
        _knowledge_graphs_module,
        _graph_extraction_module,
        _graph_query_module,
        _graph_storage_module,
    )
)
GRAPHS_ERROR = (
    _knowledge_graphs_error
    or _graph_extraction_error
    or _graph_query_error
    or _graph_storage_error
    or _graph_lineage_error
)


class GraphProvenance(TypedDict, total=False):
    """Source and transformation lineage carried by graph snapshots and queries.

    All fields are optional so older graph payloads remain valid.  Backends must
    preserve fields they do not understand instead of dropping them.
    """

    source_id: str
    source_type: str
    source_record_id: str | int
    source_ref: str
    source_url: str
    source_system: str
    content_hash: str
    acquired_at: str
    parser_version: str
    extraction_version: str
    transform_lineage: Dict[str, Any]
    metadata: Dict[str, Any]


class GraphPersistenceRequest(TypedDict):
    """Canonical write contract passed to a graph persistence backend."""

    graph_id: str
    graph_version: str
    snapshot_id: str
    content_hash: str
    entities: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    provenance: GraphProvenance
    metadata: Dict[str, Any]


class GraphSupportQuery(TypedDict):
    """Canonical claim-support lookup contract passed to a graph query backend."""

    graph_id: str
    graph_version: str
    claim_element_id: str
    claim_type: str
    claim_element_text: str
    max_results: int
    filters: Dict[str, Any]
    provenance: GraphProvenance


@runtime_checkable
class GraphPersistence(Protocol):
    """Port implemented by durable graph stores.

    ``persist_snapshot`` must be idempotent for a request's ``snapshot_id``.
    ``get_snapshot`` returns that same canonical request shape, or ``None`` when
    the requested graph/version is unknown.
    """

    def persist_snapshot(self, request: GraphPersistenceRequest) -> Mapping[str, Any]:
        """Persist one immutable graph version and return write semantics."""
        ...

    def get_snapshot(
        self,
        graph_id: str,
        *,
        graph_version: Optional[str] = None,
    ) -> Optional[Mapping[str, Any]]:
        """Load the latest or requested immutable graph snapshot."""
        ...


@runtime_checkable
class GraphQuery(Protocol):
    """Port implemented by graph engines capable of support retrieval."""

    def query_support(self, query: GraphSupportQuery) -> Mapping[str, Any]:
        """Return support matches for a canonical claim-element query."""
        ...


@runtime_checkable
class GraphRepository(GraphPersistence, GraphQuery, Protocol):
    """Combined persistence and query plane used by full graph backends."""


def _canonical_graph_content(graph_payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the immutable graph content used for version identifiers."""
    entities = [
        dict(item)
        for item in graph_payload.get("entities", []) or []
        if isinstance(item, Mapping)
    ]
    relationships = [
        dict(item)
        for item in graph_payload.get("relationships", []) or []
        if isinstance(item, Mapping)
    ]
    entities.sort(key=lambda item: str(item.get("id") or item.get("entity_id") or ""))
    relationships.sort(
        key=lambda item: str(item.get("id") or item.get("relationship_id") or "")
    )
    return {
        "entities": entities,
        "relationships": relationships,
    }


def _graph_content_hash(graph_payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _canonical_graph_content(graph_payload),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_graph_provenance(
    graph_payload: Mapping[str, Any],
    explicit: Optional[Mapping[str, Any]] = None,
) -> GraphProvenance:
    metadata = graph_payload.get("metadata")
    graph_metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
    embedded = graph_metadata.get("provenance")
    provenance: Dict[str, Any] = dict(embedded) if isinstance(embedded, Mapping) else {}

    source_id = str(graph_payload.get("source_id") or provenance.get("source_id") or "")
    if source_id:
        provenance["source_id"] = source_id
    lineage = graph_metadata.get("transform_lineage") or graph_metadata.get("lineage")
    if isinstance(lineage, Mapping) and "transform_lineage" not in provenance:
        provenance["transform_lineage"] = dict(lineage)
    if explicit:
        for key, value in explicit.items():
            if value not in (None, "", [], (), {}):
                provenance[str(key)] = value
    return GraphProvenance(**provenance)


def build_graph_persistence_request(
    graph_payload: Mapping[str, Any],
    *,
    graph_id: Optional[str] = None,
    graph_version: Optional[str] = None,
    provenance: Optional[Mapping[str, Any]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> GraphPersistenceRequest:
    """Normalize a graph payload into the backend-independent write contract."""
    payload_metadata = graph_payload.get("metadata")
    normalized_metadata = dict(payload_metadata) if isinstance(payload_metadata, Mapping) else {}
    if metadata:
        normalized_metadata.update(metadata)

    content_hash = _graph_content_hash(graph_payload)
    source_id = str(graph_payload.get("source_id") or "")
    stable_graph_id = str(
        graph_id
        or normalized_metadata.get("graph_id")
        or _stable_identifier("graph", source_id or content_hash)
    )
    stable_graph_version = str(
        graph_version
        or normalized_metadata.get("graph_version")
        or f"sha256:{content_hash[:16]}"
    )
    snapshot_id = _stable_identifier("graph-snapshot", stable_graph_id, stable_graph_version, content_hash)
    return GraphPersistenceRequest(
        graph_id=stable_graph_id,
        graph_version=stable_graph_version,
        snapshot_id=snapshot_id,
        content_hash=content_hash,
        entities=[dict(item) for item in graph_payload.get("entities", []) or [] if isinstance(item, Mapping)],
        relationships=[
            dict(item)
            for item in graph_payload.get("relationships", []) or []
            if isinstance(item, Mapping)
        ],
        provenance=_normalize_graph_provenance(graph_payload, provenance),
        metadata=normalized_metadata,
    )


def build_graph_support_query(
    claim_element_id: str,
    *,
    graph_id: Optional[str] = None,
    graph_version: Optional[str] = None,
    claim_type: Optional[str] = None,
    claim_element_text: Optional[str] = None,
    max_results: int = 10,
    filters: Optional[Mapping[str, Any]] = None,
    provenance: Optional[Mapping[str, Any]] = None,
) -> GraphSupportQuery:
    """Normalize user input into the backend-independent query contract."""
    if max_results < 0:
        raise ValueError("max_results must be greater than or equal to zero")
    return GraphSupportQuery(
        graph_id=str(graph_id or ""),
        graph_version=str(graph_version or ""),
        claim_element_id=str(claim_element_id or ""),
        claim_type=str(claim_type or ""),
        claim_element_text=str(claim_element_text or ""),
        max_results=int(max_results),
        filters=dict(filters or {}),
        provenance=GraphProvenance(**dict(provenance or {})),
    )


def _stable_identifier(prefix: str, *parts: str) -> str:
    normalized = "|".join(part.strip() for part in parts if part and part.strip())
    if not normalized:
        return ""
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _split_sentences(text: str) -> List[str]:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+", cleaned)
    return [part.strip() for part in parts if part and part.strip()]


def _tokenize(value: str) -> List[str]:
    return [token for token in re.findall(r"[a-z0-9]+", (value or "").lower()) if token]


def _normalize_semantic_token(token: str) -> str:
    normalized = (token or "").lower().strip()
    if not normalized:
        return ""

    canonical_map = {
        "complained": "complain",
        "complaint": "complain",
        "complaints": "complain",
        "filing": "file",
        "filed": "file",
        "files": "file",
        "engaged": "engage",
        "engaging": "engage",
    }
    if normalized in canonical_map:
        return canonical_map[normalized]

    for suffix in ("ing", "ed", "es", "s"):
        if normalized.endswith(suffix) and len(normalized) > len(suffix) + 2:
            return normalized[: -len(suffix)]
    return normalized


def _semantic_token_set(value: str) -> set[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "about",
        "by",
        "in",
        "of",
        "the",
        "to",
    }
    return {
        normalized
        for normalized in (_normalize_semantic_token(token) for token in _tokenize(value))
        if normalized and normalized not in stopwords
    }


def _score_fact_match(fact: Dict[str, Any], claim_element_id: str, claim_element_text: str) -> float:
    score = float(fact.get("confidence", 0.0) or 0.0)
    fact_tokens = set(_tokenize(str(fact.get("text") or "")))
    target_tokens = set(_tokenize(claim_element_text))

    if claim_element_id and str(fact.get("claim_element_id") or "") == claim_element_id:
        score += 1.0
    if claim_element_text and str(fact.get("claim_element_text") or "") == claim_element_text:
        score += 1.0
    if fact_tokens and target_tokens:
        overlap = len(fact_tokens & target_tokens)
        score += overlap / max(len(target_tokens), 1)
    return round(score, 4)


def _fact_dedup_key(fact: Dict[str, Any]) -> str:
    text = " ".join(str(fact.get("text") or "").lower().split())
    claim_element_id = str(fact.get("claim_element_id") or "")
    claim_element_text = " ".join(str(fact.get("claim_element_text") or "").lower().split())
    return "|".join([claim_element_id, claim_element_text, text])


def _fact_matches_filters(fact: Mapping[str, Any], filters: Mapping[str, Any]) -> bool:
    for key, expected in filters.items():
        actual: Any = fact.get(key)
        if actual is None and isinstance(fact.get("provenance"), Mapping):
            actual = fact["provenance"].get(key)
        if isinstance(expected, (list, tuple, set, frozenset)):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _texts_semantically_similar(left: str, right: str) -> bool:
    left_normalized = " ".join((left or "").lower().split())
    right_normalized = " ".join((right or "").lower().split())
    if not left_normalized or not right_normalized:
        return False
    if left_normalized == right_normalized:
        return True
    if left_normalized in right_normalized or right_normalized in left_normalized:
        return True

    left_tokens = _semantic_token_set(left_normalized)
    right_tokens = _semantic_token_set(right_normalized)
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    containment = overlap / max(min(len(left_tokens), len(right_tokens)), 1)
    jaccard = overlap / max(union, 1)
    return containment >= 0.6 or jaccard >= 0.45


def _cluster_semantically_similar_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    clusters: List[Dict[str, Any]] = []
    for result in results:
        matched_cluster: Optional[Dict[str, Any]] = None
        for cluster in clusters:
            same_element = (
                str(cluster.get("claim_element_id") or "") == str(result.get("claim_element_id") or "")
                and str(cluster.get("claim_element_text") or "") == str(result.get("claim_element_text") or "")
            )
            if not same_element:
                continue
            if _texts_semantically_similar(str(cluster.get("text") or ""), str(result.get("text") or "")):
                matched_cluster = cluster
                break

        if matched_cluster is None:
            clusters.append(
                {
                    **result,
                    "cluster_size": int(result.get("duplicate_count", 1) or 1),
                    "cluster_texts": [str(result.get("text") or "")],
                }
            )
            continue

        matched_cluster["duplicate_count"] = int(matched_cluster.get("duplicate_count", 1) or 1) + int(result.get("duplicate_count", 1) or 1)
        matched_cluster["cluster_size"] = int(matched_cluster.get("cluster_size", 1) or 1) + int(result.get("duplicate_count", 1) or 1)
        matched_cluster["score"] = max(float(matched_cluster.get("score", 0.0) or 0.0), float(result.get("score", 0.0) or 0.0))
        matched_cluster["confidence"] = max(float(matched_cluster.get("confidence", 0.0) or 0.0), float(result.get("confidence", 0.0) or 0.0))
        if result.get("matched_claim_element"):
            matched_cluster["matched_claim_element"] = True
        if str(result.get("text") or "") not in matched_cluster["cluster_texts"]:
            matched_cluster["cluster_texts"].append(str(result.get("text") or ""))
        for support_kind in result.get("support_kind_set", []) or []:
            if support_kind not in matched_cluster.get("support_kind_set", []):
                matched_cluster.setdefault("support_kind_set", []).append(support_kind)
        for source_table in result.get("source_table_set", []) or []:
            if source_table not in matched_cluster.get("source_table_set", []):
                matched_cluster.setdefault("source_table_set", []).append(source_table)
    return clusters


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

    sentences = _split_sentences(text)
    if not sentences and text.strip():
        sentences = [text.strip()]

    for index, sentence in enumerate(sentences[:25]):
        fact_id = _stable_identifier("fact", artifact_id or source_id or "text", str(index), sentence)
        entities.append(
            GraphEntity(
                entity_id=fact_id,
                entity_type="fact",
                name=sentence[:120],
                confidence=0.6,
                attributes={
                    "text": sentence,
                    "sentence_index": index,
                    "source_id": artifact_id,
                    "provenance": graph_provenance,
                },
            )
        )
        if artifact_id:
            relationships.append(
                GraphRelationship(
                    relationship_id=_stable_identifier("rel", artifact_id, fact_id, "has_fact"),
                    source_id=artifact_id,
                    target_id=fact_id,
                    relation_type="has_fact",
                    confidence=1.0,
                    attributes={"sentence_index": index, "provenance": graph_provenance},
                )
            )
        if claim_node_id:
            relationships.append(
                GraphRelationship(
                    relationship_id=_stable_identifier("rel", fact_id, claim_node_id, "supports"),
                    source_id=fact_id,
                    target_id=claim_node_id,
                    relation_type="supports",
                    confidence=0.6,
                    attributes={"sentence_index": index, "provenance": graph_provenance},
                )
            )

    implementation_status = "fallback" if KNOWLEDGE_GRAPHS_AVAILABLE else "unavailable"
    return with_adapter_metadata(
        GraphPayload(
            status="available-fallback" if KNOWLEDGE_GRAPHS_AVAILABLE else "unavailable",
            source_id=source_id or "",
            entities=entities,
            relationships=relationships,
            metadata={
                **metadata,
                "text_length": len(text),
                "sentence_count": len(sentences),
                "provenance": graph_provenance,
            },
        ).as_dict(),
        operation="extract_graph_from_text",
        backend_available=KNOWLEDGE_GRAPHS_AVAILABLE,
        degraded_reason=GRAPHS_ERROR if not KNOWLEDGE_GRAPHS_AVAILABLE else None,
        implementation_status=implementation_status,
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
    deduped_results: Dict[str, Dict[str, Any]] = {}

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
                support_by_kind=support_by_kind,
                support_by_source=support_by_source,
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
) -> Dict[str, Any]:
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
    base_payload = GraphSnapshotResult(
        status=(
            str(backend_result.get("status") or "persisted")
            if backend_used
            else ("degraded" if persistence_error else ("pending" if _graph_storage_module is not None else "noop"))
        ),
        graph_id=stable_graph_id,
        persisted=bool(backend_result.get("persisted", True)) if backend_used else False,
        created=bool(backend_result.get("created", created)) if backend_used else created,
        reused=bool(backend_result.get("reused", reused)) if backend_used else reused,
        node_count=int(backend_result.get("node_count", entity_count) or 0) if backend_used else entity_count,
        edge_count=int(backend_result.get("edge_count", relationship_count) or 0) if backend_used else relationship_count,
        metadata={
            "source_id": source_id,
            **(persistence_metadata or {}),
            "lineage": {
                "status": str(graph_payload.get("status") or ""),
                "text_length": metadata.get("text_length", 0),
                "sentence_count": metadata.get("sentence_count", 0),
            },
        },
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
        backend_available=backend_used or _graph_storage_module is not None,
        degraded_reason=persistence_error or (_graph_storage_error if persistence is None else None),
        implementation_status=(
            "backend"
            if backend_used
            else ("degraded" if persistence_error else ("pending" if _graph_storage_module is not None else "noop"))
        ),
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


__all__ = [
    "KNOWLEDGE_GRAPHS_AVAILABLE",
    "GRAPHS_ERROR",
    "GraphProvenance",
    "GraphPersistenceRequest",
    "GraphSupportQuery",
    "GraphPersistence",
    "GraphQuery",
    "GraphRepository",
    "build_graph_persistence_request",
    "build_graph_support_query",
    "extract_graph_from_text",
    "query_graph_support",
    "persist_graph_snapshot",
]
