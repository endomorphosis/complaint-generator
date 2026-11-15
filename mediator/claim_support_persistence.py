"""Persistence methods delegated from ClaimSupportHook."""

from __future__ import annotations

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    duckdb = None

from mediator.claim_support_hooks import (
    hashlib,
    json,
    persist_graph_snapshot,
    _merge_intake_summary_handoff_metadata,
)


def persist_fact_record(
    self,
    user_id: str,
    claim_type: str,
    *,
    claim_element_id: Optional[str] = None,
    claim_element_text: Optional[str] = None,
    proposition_text: str,
    source_artifact_id: str = '',
    source_authority_id: str = '',
    source_testimony_id: str = '',
    chunk_ref: str = '',
    span_ref: str = '',
    confidence: float = 0.0,
    validation_state: str = 'unvalidated',
    uncertainty_flag: bool = False,
    contradiction_flag: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist a durable fact record linked to a claim element.

    Returns ``{fact_id, record_id, created}`` whether or not DuckDB is
    available.  When DuckDB is unavailable the record is held in memory so
    that callers can still obtain a stable ``fact_id`` for the session.
    """
    if not proposition_text or not proposition_text.strip():
        return {
            'available': DUCKDB_AVAILABLE,
            'recorded': False,
            'claim_type': claim_type,
            'error': 'empty_proposition_text',
        }

    resolved_element = self.resolve_claim_element(
        user_id,
        claim_type,
        claim_element_id=claim_element_id,
        claim_element_text=claim_element_text,
    )
    resolved_element_id = claim_element_id or resolved_element.get('claim_element_id', '')
    resolved_element_text = claim_element_text or resolved_element.get('claim_element_text', '')

    normalized_validation_state = str(validation_state or 'unvalidated') or 'unvalidated'
    if normalized_validation_state not in (
        'unvalidated', 'confirmed', 'contradicted', 'uncertain', 'exception_barred'
    ):
        normalized_validation_state = 'unvalidated'

    fact_id = self._make_fact_id(
        user_id=user_id,
        claim_type=claim_type,
        claim_element_id=resolved_element_id,
        proposition_text=proposition_text.strip(),
        source_artifact_id=source_artifact_id,
        source_authority_id=source_authority_id,
        source_testimony_id=source_testimony_id,
        chunk_ref=chunk_ref,
    )

    normalized_metadata = _merge_intake_summary_handoff_metadata(
        dict(metadata or {}),
        self.mediator,
    )

    if not DUCKDB_AVAILABLE:
        return {
            'available': False,
            'recorded': False,
            'fact_id': fact_id,
            'claim_type': claim_type,
            'error': 'duckdb_unavailable',
        }

    try:
        conn = duckdb.connect(self.db_path)
        existing = conn.execute(
            'SELECT id FROM claim_facts WHERE fact_id = ? LIMIT 1',
            [fact_id],
        ).fetchone()
        if existing:
            conn.close()
            return {
                'available': True,
                'recorded': False,
                'fact_id': fact_id,
                'record_id': existing[0],
                'claim_type': claim_type,
                'created': False,
                'reused': True,
            }
        row = conn.execute(
            """
            INSERT INTO claim_facts (
                fact_id, user_id, claim_type,
                claim_element_id, claim_element_text,
                proposition_text,
                source_artifact_id, source_authority_id, source_testimony_id,
                chunk_ref, span_ref,
                confidence, validation_state,
                uncertainty_flag, contradiction_flag,
                metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id, timestamp
            """,
            [
                fact_id,
                user_id,
                claim_type,
                resolved_element_id or None,
                resolved_element_text or None,
                proposition_text.strip(),
                source_artifact_id or None,
                source_authority_id or None,
                source_testimony_id or None,
                chunk_ref or None,
                span_ref or None,
                float(confidence or 0.0),
                normalized_validation_state,
                bool(uncertainty_flag),
                bool(contradiction_flag),
                json.dumps(normalized_metadata, default=str),
            ],
        ).fetchone()
        conn.close()
        self.mediator.log(
            'claim_fact_persisted',
            fact_id=fact_id,
            claim_type=claim_type,
            claim_element_id=resolved_element_id,
            validation_state=normalized_validation_state,
        )
        return {
            'available': True,
            'recorded': True,
            'fact_id': fact_id,
            'record_id': row[0],
            'timestamp': row[1].isoformat() if hasattr(row[1], 'isoformat') else row[1],
            'claim_type': claim_type,
            'claim_element_id': resolved_element_id,
            'claim_element_text': resolved_element_text,
            'proposition_text': proposition_text.strip(),
            'validation_state': normalized_validation_state,
            'uncertainty_flag': bool(uncertainty_flag),
            'contradiction_flag': bool(contradiction_flag),
            'confidence': float(confidence or 0.0),
            'created': True,
            'reused': False,
        }
    except Exception as exc:
        self.mediator.log('claim_fact_persist_error', error=str(exc), claim_type=claim_type)
        return {
            'available': False,
            'recorded': False,
            'fact_id': fact_id,
            'claim_type': claim_type,
            'error': str(exc),
        }


def persist_support_path(
    self,
    user_id: str,
    claim_type: str,
    claim_element_id: str,
    support_traces: List[Dict[str, Any]],
    *,
    path_kind: str = 'support',
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist a stable proof-path record for a set of support traces.

    Collects all fact IDs from the traces, generates a stable
    ``proof_path_id``, and upserts a record in ``claim_support_paths``.
    Returns ``{proof_path_id, record_id, created}``.
    """
    fact_ids: List[str] = []
    for trace in support_traces or []:
        fid = str(trace.get('fact_id') or '')
        if fid and fid not in fact_ids:
            fact_ids.append(fid)
    path_drilldown_metadata = self._build_support_path_drilldown_metadata(support_traces or [])
    support_refs = path_drilldown_metadata.get('support_refs', [])

    proof_path_id = self._make_trace_path_id(
        user_id=user_id,
        claim_type=claim_type,
        claim_element_id=claim_element_id,
        fact_ids=fact_ids,
        support_refs=support_refs if isinstance(support_refs, list) else [],
        path_kind=path_kind,
    )

    if not DUCKDB_AVAILABLE:
        return {
            'available': False,
            'recorded': False,
            'proof_path_id': proof_path_id,
            'claim_type': claim_type,
            'error': 'duckdb_unavailable',
        }

    normalized_metadata = _merge_intake_summary_handoff_metadata(
        dict(metadata or {}),
        self.mediator,
    )
    support_fact_registry_summary = self._summarize_fact_registry(support_traces or [])
    normalized_metadata.setdefault('support_fact_registry_summary', support_fact_registry_summary)
    normalized_metadata.setdefault('support_trace_summary', self._summarize_support_traces(support_traces or []))
    normalized_metadata.setdefault('graph_trace_summary', path_drilldown_metadata.get('graph_trace_summary', {}))
    normalized_metadata.setdefault('path_drilldown', path_drilldown_metadata)
    for key in (
        'support_refs',
        'support_ref_count',
        'support_kinds',
        'source_families',
        'graph_ids',
        'graph_id_count',
        'graph_trace_count',
    ):
        normalized_metadata.setdefault(key, path_drilldown_metadata.get(key))

    try:
        conn = duckdb.connect(self.db_path)
        existing = conn.execute(
            'SELECT id FROM claim_support_paths WHERE proof_path_id = ? LIMIT 1',
            [proof_path_id],
        ).fetchone()
        if existing:
            conn.close()
            return {
                'available': True,
                'recorded': False,
                'proof_path_id': proof_path_id,
                'record_id': existing[0],
                'claim_type': claim_type,
                'claim_element_id': claim_element_id,
                'fact_ids': fact_ids,
                'support_refs': support_refs if isinstance(support_refs, list) else [],
                'support_ref_count': int(path_drilldown_metadata.get('support_ref_count', 0) or 0),
                'support_kinds': path_drilldown_metadata.get('support_kinds', []),
                'source_families': path_drilldown_metadata.get('source_families', []),
                'graph_ids': path_drilldown_metadata.get('graph_ids', []),
                'graph_id_count': int(path_drilldown_metadata.get('graph_id_count', 0) or 0),
                'graph_trace_count': int(path_drilldown_metadata.get('graph_trace_count', 0) or 0),
                'created': False,
                'reused': True,
            }
        row = conn.execute(
            """
            INSERT INTO claim_support_paths (
                proof_path_id, user_id, claim_type, claim_element_id,
                fact_ids, path_kind, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING id, timestamp
            """,
            [
                proof_path_id,
                user_id,
                claim_type,
                claim_element_id or None,
                json.dumps(fact_ids),
                path_kind or 'support',
                json.dumps(normalized_metadata, default=str),
            ],
        ).fetchone()
        conn.close()
        self.mediator.log(
            'claim_support_path_persisted',
            proof_path_id=proof_path_id,
            claim_type=claim_type,
            claim_element_id=claim_element_id,
            fact_count=len(fact_ids),
        )
        return {
            'available': True,
            'recorded': True,
            'proof_path_id': proof_path_id,
            'record_id': row[0],
            'timestamp': row[1].isoformat() if hasattr(row[1], 'isoformat') else row[1],
            'claim_type': claim_type,
            'claim_element_id': claim_element_id,
            'fact_ids': fact_ids,
            'support_refs': support_refs if isinstance(support_refs, list) else [],
            'support_ref_count': int(path_drilldown_metadata.get('support_ref_count', 0) or 0),
            'support_kinds': path_drilldown_metadata.get('support_kinds', []),
            'source_families': path_drilldown_metadata.get('source_families', []),
            'graph_ids': path_drilldown_metadata.get('graph_ids', []),
            'graph_id_count': int(path_drilldown_metadata.get('graph_id_count', 0) or 0),
            'graph_trace_count': int(path_drilldown_metadata.get('graph_trace_count', 0) or 0),
            'support_fact_registry_summary': support_fact_registry_summary,
            'path_kind': path_kind,
            'created': True,
            'reused': False,
        }
    except Exception as exc:
        self.mediator.log('claim_support_path_error', error=str(exc), claim_type=claim_type)
        return {
            'available': False,
            'recorded': False,
            'proof_path_id': proof_path_id,
            'claim_type': claim_type,
            'error': str(exc),
        }


def persist_typed_graph_snapshot(
    self,
    user_id: str,
    claim_type: str,
    source_kind: str,
    graph_payload: Dict[str, Any],
    *,
    graph_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist a graph snapshot for a typed source (testimony, evidence, law).

    Stores the snapshot in ``claim_support_snapshot`` with a stable
    ``snapshot_kind`` derived from *source_kind* and returns the snapshot ID.
    Falls back gracefully when DuckDB is unavailable.
    """
    source_kind_clean = str(source_kind or 'unknown').strip().lower()
    snapshot_kind = f'graph:{source_kind_clean}'

    entity_count = len(graph_payload.get('entities', []) or []) if isinstance(graph_payload, dict) else 0
    relationship_count = len(graph_payload.get('relationships', []) or []) if isinstance(graph_payload, dict) else 0
    source_id = str(graph_payload.get('source_id') or '') if isinstance(graph_payload, dict) else ''
    graph_metadata = graph_payload.get('metadata') if isinstance(graph_payload, dict) and isinstance(graph_payload.get('metadata'), dict) else {}
    support_facts = graph_payload.get('support_facts') if isinstance(graph_payload, dict) and isinstance(graph_payload.get('support_facts'), list) else []
    input_metadata = metadata if isinstance(metadata, dict) else {}
    fact_registry_summary = (
        dict(input_metadata.get('fact_registry_summary'))
        if isinstance(input_metadata.get('fact_registry_summary'), dict)
        else dict(graph_payload.get('fact_registry_summary'))
        if isinstance(graph_payload, dict) and isinstance(graph_payload.get('fact_registry_summary'), dict)
        else dict(graph_metadata.get('fact_registry_summary'))
        if isinstance(graph_metadata.get('fact_registry_summary'), dict)
        else self._summarize_fact_registry(support_facts)
    )

    stable_graph_id = graph_id or (
        'graph:' + hashlib.sha256(
            '|'.join([user_id, claim_type, source_kind_clean, source_id, str(entity_count), str(relationship_count)]).encode('utf-8')
        ).hexdigest()[:16]
    )
    snapshot_metadata = dict(metadata or {})
    snapshot_metadata['graph_id'] = stable_graph_id
    snapshot_metadata.setdefault('fact_registry_summary', fact_registry_summary)
    adapter_graph_snapshot = persist_graph_snapshot(
        graph_payload if isinstance(graph_payload, dict) else {},
        graph_id=stable_graph_id,
        graph_changed=True,
        existing_graph=False,
        persistence_metadata={
            **snapshot_metadata,
            'user_id': user_id,
            'claim_type': claim_type,
            'source_kind': source_kind_clean,
            'record_scope': snapshot_metadata.get('record_scope') or source_kind_clean,
            'fact_registry_summary': fact_registry_summary,
        },
    )

    if not DUCKDB_AVAILABLE:
        return {
            'available': False,
            'recorded': False,
            'graph_id': stable_graph_id,
            'snapshot_kind': snapshot_kind,
            'source_kind': source_kind_clean,
            'claim_type': claim_type,
            'error': 'duckdb_unavailable',
            'graph_snapshot': adapter_graph_snapshot,
        }

    snapshot_payload = {
        'graph_id': stable_graph_id,
        'source_kind': source_kind_clean,
        'entity_count': entity_count,
        'relationship_count': relationship_count,
        'source_id': source_id,
        'entities': graph_payload.get('entities', []) if isinstance(graph_payload, dict) else [],
        'relationships': graph_payload.get('relationships', []) if isinstance(graph_payload, dict) else [],
        'fact_registry_summary': fact_registry_summary,
        'graph_snapshot': adapter_graph_snapshot,
    }
    snapshot_metadata['graph_snapshot'] = adapter_graph_snapshot

    try:
        conn = duckdb.connect(self.db_path)
        row = conn.execute(
            """
            INSERT INTO claim_support_snapshot (
                user_id, claim_type, snapshot_kind,
                required_support_kinds, payload, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?)
            RETURNING id, timestamp
            """,
            [
                user_id,
                claim_type,
                snapshot_kind,
                json.dumps([], default=str),
                json.dumps(snapshot_payload, default=str),
                json.dumps(snapshot_metadata, default=str),
            ],
        ).fetchone()
        conn.close()
        self.mediator.log(
            'typed_graph_snapshot_persisted',
            graph_id=stable_graph_id,
            snapshot_kind=snapshot_kind,
            claim_type=claim_type,
            entity_count=entity_count,
        )
        return {
            'available': True,
            'recorded': True,
            'graph_id': stable_graph_id,
            'snapshot_kind': snapshot_kind,
            'source_kind': source_kind_clean,
            'snapshot_id': row[0] if row else None,
            'claim_type': claim_type,
            'entity_count': entity_count,
            'relationship_count': relationship_count,
            'fact_registry_summary': fact_registry_summary,
            'graph_snapshot': adapter_graph_snapshot,
            'created': True,
            'reused': False,
        }
    except Exception as exc:
        self.mediator.log('typed_graph_snapshot_error', error=str(exc), claim_type=claim_type)
        return {
            'available': False,
            'recorded': False,
            'graph_id': stable_graph_id,
            'snapshot_kind': snapshot_kind,
            'source_kind': source_kind_clean,
            'claim_type': claim_type,
            'error': str(exc),
            'graph_snapshot': adapter_graph_snapshot,
        }


def persist_claim_support_diagnostics(
    self,
    user_id: str,
    claim_type: Optional[str] = None,
    *,
    required_support_kinds: Optional[List[str]] = None,
    gaps: Optional[Dict[str, Any]] = None,
    contradictions: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    retention_limit: Optional[int] = 3,
) -> Dict[str, Any]:
    normalized_retention_limit = self._normalize_snapshot_retention_limit(retention_limit)
    if not DUCKDB_AVAILABLE:
        return {
            'available': False,
            'required_support_kinds': self._normalize_required_support_kinds(required_support_kinds),
            'retention_limit': normalized_retention_limit,
            'pruned_snapshot_count': 0,
            'claims': {},
        }

    normalized_kinds = self._normalize_required_support_kinds(required_support_kinds)
    normalized_metadata = _merge_intake_summary_handoff_metadata(
        metadata,
        self.mediator,
    )
    gap_payload = gaps if isinstance(gaps, dict) else self.get_claim_support_gaps(
        user_id,
        claim_type=claim_type,
        required_support_kinds=normalized_kinds or None,
    )
    contradiction_payload = (
        contradictions if isinstance(contradictions, dict)
        else self.get_claim_contradiction_candidates(user_id, claim_type=claim_type)
    )

    gap_claims = gap_payload.get('claims', {}) if isinstance(gap_payload, dict) else {}
    contradiction_claims = (
        contradiction_payload.get('claims', {})
        if isinstance(contradiction_payload, dict)
        else {}
    )
    claim_names = sorted(set(gap_claims.keys()) | set(contradiction_claims.keys()))
    persisted: Dict[str, Any] = {
        'available': True,
        'required_support_kinds': normalized_kinds,
        'retention_limit': normalized_retention_limit,
        'pruned_snapshot_count': 0,
        'claims': {},
    }

    for current_claim in claim_names:
        support_state_token = self._build_claim_support_state_token(
            user_id,
            current_claim,
            normalized_kinds,
        )
        claim_metadata = {
            **(normalized_metadata or {}),
            'support_state_token': support_state_token,
        }
        claim_result = {
            'gaps': gap_claims.get(current_claim, {}),
            'contradictions': contradiction_claims.get(current_claim, {}),
            'snapshots': {},
        }
        for snapshot_kind, payload in (
            ('gaps', claim_result['gaps']),
            ('contradictions', claim_result['contradictions']),
        ):
            if not isinstance(payload, dict) or not payload:
                continue
            try:
                conn = duckdb.connect(self.db_path)
                result = conn.execute(
                    """
                    INSERT INTO claim_support_snapshot (
                        user_id, claim_type, snapshot_kind,
                        required_support_kinds, payload, metadata
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    RETURNING id, timestamp
                    """,
                    [
                        user_id,
                        current_claim,
                        snapshot_kind,
                        json.dumps(normalized_kinds, default=str),
                        json.dumps(payload, default=str),
                        json.dumps(claim_metadata, default=str),
                    ],
                ).fetchone()
                conn.close()
                prune_result = self._prune_snapshot_history(
                    user_id=user_id,
                    claim_type=current_claim,
                    snapshot_kind=snapshot_kind,
                    required_support_kinds=normalized_kinds,
                    keep_latest=normalized_retention_limit,
                )
                persisted['pruned_snapshot_count'] += int(
                    prune_result.get('pruned_snapshot_count', 0) or 0
                )
                claim_result['snapshots'][snapshot_kind] = {
                    'snapshot_id': result[0],
                    'timestamp': result[1].isoformat() if hasattr(result[1], 'isoformat') else result[1],
                    'required_support_kinds': normalized_kinds,
                    'metadata': claim_metadata,
                    'is_stale': False,
                    'retention_limit': normalized_retention_limit,
                    'pruned_snapshot_count': int(prune_result.get('pruned_snapshot_count', 0) or 0),
                }
            except Exception as exc:
                self.mediator.log(
                    'claim_support_snapshot_persist_error',
                    error=str(exc),
                    claim_type=current_claim,
                    snapshot_kind=snapshot_kind,
                )
                claim_result['snapshots'][snapshot_kind] = {
                    'snapshot_id': -1,
                    'required_support_kinds': normalized_kinds,
                    'metadata': claim_metadata,
                    'is_stale': True,
                    'retention_limit': normalized_retention_limit,
                    'pruned_snapshot_count': 0,
                    'error': str(exc),
                }
        persisted['claims'][current_claim] = claim_result

    return persisted


def persist_claim_coverage_matrix_snapshot(
    self,
    user_id: str,
    claim_type: Optional[str] = None,
    *,
    required_support_kinds: Optional[List[str]] = None,
    coverage_matrix: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    retention_limit: Optional[int] = 3,
) -> Dict[str, Any]:
    """Persist the current claim coverage matrix as an authoritative snapshot."""
    normalized_kinds = self._normalize_required_support_kinds(required_support_kinds)
    normalized_retention_limit = self._normalize_snapshot_retention_limit(retention_limit)
    if not DUCKDB_AVAILABLE:
        return {
            'available': False,
            'required_support_kinds': normalized_kinds,
            'retention_limit': normalized_retention_limit,
            'claims': {},
            'error': 'duckdb_unavailable',
        }

    matrix = coverage_matrix if isinstance(coverage_matrix, dict) else self.get_claim_coverage_matrix(
        user_id,
        claim_type=claim_type,
        required_support_kinds=normalized_kinds or None,
    )
    claim_matrices = matrix.get('claims', {}) if isinstance(matrix.get('claims'), dict) else {}
    normalized_metadata = _merge_intake_summary_handoff_metadata(
        metadata,
        self.mediator,
    )
    persisted: Dict[str, Any] = {
        'available': True,
        'required_support_kinds': normalized_kinds,
        'retention_limit': normalized_retention_limit,
        'pruned_snapshot_count': 0,
        'claims': {},
    }

    for current_claim, claim_matrix in sorted(claim_matrices.items()):
        if claim_type and current_claim != claim_type:
            continue
        if not isinstance(claim_matrix, dict) or not claim_matrix:
            continue
        support_state_token = self._build_claim_support_state_token(
            user_id,
            current_claim,
            normalized_kinds,
        )
        claim_metadata = {
            **(normalized_metadata or {}),
            'support_state_token': support_state_token,
            'snapshot_source': 'claim_coverage_matrix',
            'element_count': len(claim_matrix.get('elements', []) or []),
            'total_links': int(claim_matrix.get('total_links', 0) or 0),
            'total_facts': int(claim_matrix.get('total_facts', 0) or 0),
            'coverage_matrix_summary': self._summarize_coverage_matrix_for_snapshot(claim_matrix),
        }
        try:
            conn = duckdb.connect(self.db_path)
            result = conn.execute(
                """
                INSERT INTO claim_support_snapshot (
                    user_id, claim_type, snapshot_kind,
                    required_support_kinds, payload, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?)
                RETURNING id, timestamp
                """,
                [
                    user_id,
                    current_claim,
                    'coverage_matrix',
                    json.dumps(normalized_kinds, default=str),
                    json.dumps(claim_matrix, default=str),
                    json.dumps(claim_metadata, default=str),
                ],
            ).fetchone()
            conn.close()
            prune_result = self._prune_snapshot_history(
                user_id=user_id,
                claim_type=current_claim,
                snapshot_kind='coverage_matrix',
                required_support_kinds=normalized_kinds,
                keep_latest=normalized_retention_limit,
            )
            persisted['pruned_snapshot_count'] += int(
                prune_result.get('pruned_snapshot_count', 0) or 0
            )
            persisted['claims'][current_claim] = {
                'coverage_matrix': claim_matrix,
                'snapshot': {
                    'snapshot_id': result[0],
                    'timestamp': result[1].isoformat() if hasattr(result[1], 'isoformat') else result[1],
                    'required_support_kinds': normalized_kinds,
                    'metadata': claim_metadata,
                    'stored_support_state_token': support_state_token,
                    'current_support_state_token': support_state_token,
                    'is_stale': False,
                    'retention_limit': normalized_retention_limit,
                    'pruned_snapshot_count': int(prune_result.get('pruned_snapshot_count', 0) or 0),
                },
            }
        except Exception as exc:
            self.mediator.log(
                'claim_coverage_matrix_snapshot_persist_error',
                error=str(exc),
                claim_type=current_claim,
            )
            persisted['claims'][current_claim] = {
                'coverage_matrix': claim_matrix,
                'snapshot': {
                    'snapshot_id': -1,
                    'required_support_kinds': normalized_kinds,
                    'metadata': claim_metadata,
                    'stored_support_state_token': support_state_token,
                    'current_support_state_token': support_state_token,
                    'is_stale': True,
                    'retention_limit': normalized_retention_limit,
                    'pruned_snapshot_count': 0,
                    'error': str(exc),
                },
            }

    return persisted


def persist_private_factual_graph(
    self,
    graph_payload: Dict[str, Any],
    private_context: Dict[str, Any],
    *,
    graph_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Seal graph payload, source text, embeddings, and indexes before replication.

    Plaintext publication stays disabled. The knowledge-graph client catalog
    is not used for these private bytes.
    """
    from integrations.ipfs_datasets.graphs import persist_graph_snapshot

    sealed = dict(private_context or {})
    sealed.pop('publish_plaintext', None)
    result = persist_graph_snapshot(
        graph_payload if isinstance(graph_payload, dict) else {},
        graph_id=graph_id,
        private_context=sealed,
    )
    result['plaintext_publication'] = False
    self.mediator.log(
        'private_factual_graph_sealed',
        graph_id=str(graph_id or ''),
        persisted=bool(result.get('persisted')),
        plaintext_publication=False,
    )
    return result
