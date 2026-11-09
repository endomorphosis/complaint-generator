"""Evidence record storage delegated from the evidence hooks."""

from __future__ import annotations

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    duckdb = None

from mediator.evidence_hooks import (
    Any,
    CaseArtifact,
    CaseFact,
    Dict,
    EvidencePersistenceError,
    EvidenceStorageError,
    IPFS_AVAILABLE,
    List,
    Path,
    _build_fact_chunk_lineage,
    _ensure_evidence_fact_schema,
    _ensure_fact_id_prefix,
    _merge_intake_summary_handoff_metadata,
    add_bytes,
    build_document_parse_contract,
    build_fact_lineage_metadata,
    build_provenance,
    datetime,
    extract_graph_from_text,
    hashlib,
    json,
    merge_metadata_with_provenance,
    parse_document,
    persist_graph_snapshot,
    stable_content_hash,
)

def upsert_evidence_record(self, user_id: str, evidence_info: Dict[str, Any],
                         complaint_id: Optional[str] = None,
                         claim_type: Optional[str] = None,
                         claim_element_id: Optional[str] = None,
                         claim_element: Optional[str] = None,
                         description: Optional[str] = None) -> Dict[str, Any]:
    """
    Add evidence record to DuckDB.

    Args:
        user_id: User identifier
        evidence_info: Evidence information (from EvidenceStorageHook)
        complaint_id: Optional complaint ID this evidence relates to
        claim_type: Optional claim type this evidence supports
        description: Optional description of the evidence

    Returns:
        Dictionary describing whether the record was newly inserted or reused.
    """
    if not DUCKDB_AVAILABLE:
        normalized_evidence_metadata = _merge_intake_summary_handoff_metadata(
            evidence_info.get('metadata', {}),
            self.mediator,
        )
        provenance_payload = (
            dict(normalized_evidence_metadata.get('provenance') or {})
            if isinstance(normalized_evidence_metadata.get('provenance'), dict)
            else {}
        )
        provenance_metadata = _merge_intake_summary_handoff_metadata(
            provenance_payload.get('metadata', {}),
            self.mediator,
        )
        document_parse = evidence_info.get('document_parse') if isinstance(evidence_info.get('document_parse'), dict) else {}
        document_graph = evidence_info.get('document_graph') if isinstance(evidence_info.get('document_graph'), dict) else {}
        parse_contract = build_document_parse_contract(
            document_parse,
            default_source=str(
                document_parse.get('metadata', {}).get('source')
                or normalized_evidence_metadata.get('parse_source')
                or ''
            ),
        )
        parse_metadata = _merge_intake_summary_handoff_metadata(
            parse_contract['storage_metadata'],
            self.mediator,
        )
        parsed_text = parse_contract['text']
        parsed_text_preview = parse_contract['text_preview']
        if not document_graph and parsed_text:
            document_graph = extract_graph_from_text(
                parsed_text,
                source_id=evidence_info.get('artifact_id') or evidence_info.get('cid'),
                metadata={
                    'artifact_id': evidence_info.get('artifact_id', ''),
                    'source_url': evidence_info.get('source_url', ''),
                    'claim_type': claim_type or '',
                    'claim_element_id': claim_element_id or '',
                    'claim_element_text': claim_element or '',
                    'filename': document_parse.get('metadata', {}).get('filename', ''),
                    'mime_type': document_parse.get('metadata', {}).get('mime_type', ''),
                },
            )
        existing_record = next(
            (
                record for record in self._memory_records
                if str(record.get('user_id') or '') == str(user_id)
                and str(record.get('cid') or '') == str(evidence_info.get('cid') or '')
                and str(record.get('claim_type') or '') == str(claim_type or '')
                and str(record.get('claim_element_id') or '') == str(claim_element_id or '')
            ),
            None,
        )
        if existing_record is not None:
            return {'record_id': int(existing_record.get('id') or -1), 'created': False, 'reused': True}

        record_id = len(self._memory_records) + 1
        state = getattr(self.mediator, 'state', None)
        username = getattr(state, 'username', None) if state is not None else None
        if not isinstance(username, str) or not username:
            username = user_id
        record = {
            'id': record_id,
            'user_id': user_id,
            'username': username,
            'cid': evidence_info.get('cid'),
            'type': evidence_info.get('type'),
            'size': evidence_info.get('size'),
            'timestamp': evidence_info.get('timestamp'),
            'metadata': normalized_evidence_metadata,
            'complaint_id': complaint_id,
            'claim_type': claim_type,
            'description': description,
            'content_hash': evidence_info.get('content_hash'),
            'source_url': evidence_info.get('source_url'),
            'acquisition_method': evidence_info.get('acquisition_method'),
            'provenance': evidence_info.get('provenance') or {},
            'claim_element_id': claim_element_id,
            'claim_element': claim_element,
            'parse_status': parse_contract.get('status') or parse_metadata.get('status'),
            'chunk_count': parse_contract.get('chunk_count', 0),
            'parsed_text_preview': parsed_text_preview,
            'parse_metadata': parse_metadata,
            'graph_status': document_graph.get('status', ''),
            'graph_entity_count': len(document_graph.get('entities', []) or []),
            'graph_relationship_count': len(document_graph.get('relationships', []) or []),
            'graph_metadata': document_graph.get('metadata', {}) if isinstance(document_graph.get('metadata'), dict) else {},
            'fact_count': 0,
        }
        memory_facts: List[Dict[str, Any]] = []
        artifact_id = str(evidence_info.get('artifact_id') or evidence_info.get('cid') or '')
        cid = str(evidence_info.get('cid') or '')
        chunks = list(document_parse.get('chunks', []) or [])
        # Iterate over graph entities with type='fact' (same approach as _store_document_facts)
        for entity in list(document_graph.get('entities', []) or []):
            if not isinstance(entity, dict) or entity.get('type') != 'fact':
                continue
            attributes = entity.get('attributes', {}) if isinstance(entity.get('attributes'), dict) else {}
            text = str(attributes.get('text') or entity.get('name') or '').strip()
            if not text:
                continue
            lineage_metadata = build_fact_lineage_metadata(
                attributes,
                parse_contract=parse_contract,
                record_scope='evidence',
                source_ref=artifact_id,
            )
            lineage_metadata.update(
                _build_fact_chunk_lineage(
                    text,
                    int(attributes.get('sentence_index', 0) or 0),
                    chunks,
                )
            )
            fact_metadata = _merge_intake_summary_handoff_metadata(
                lineage_metadata,
                self.mediator,
            )
            fact_provenance = build_provenance(
                source_url=str(provenance_payload.get('source_url', '')),
                acquisition_method=str(provenance_payload.get('acquisition_method', '')),
                source_type=str(provenance_payload.get('source_type', '')),
                acquired_at=str(provenance_payload.get('acquired_at', '')),
                content_hash=str(provenance_payload.get('content_hash', '')),
                source_system=str(provenance_payload.get('source_system', '')),
                jurisdiction=str(provenance_payload.get('jurisdiction', '')),
                metadata=provenance_metadata,
            )
            fact = CaseFact(
                fact_id=_ensure_fact_id_prefix(str(entity.get('id') or ''), artifact_id, text),
                text=text,
                source_artifact_id=artifact_id,
                source_family='evidence',
                source_record_id=record_id,
                source_ref=artifact_id,
                record_scope='evidence',
                confidence=float(entity.get('confidence', 0.0) or 0.0),
                metadata=fact_metadata,
                provenance=fact_provenance,
            )
            memory_facts.append(fact.as_dict())
        if not memory_facts and parsed_text_preview:
            lineage_metadata = build_fact_lineage_metadata(
                {},
                parse_contract=parse_contract,
                record_scope='evidence',
                source_ref=artifact_id,
            )
            lineage_metadata.update(
                _build_fact_chunk_lineage(parsed_text_preview, 0, chunks)
            )
            fact = CaseFact(
                fact_id=f'fact:{hashlib.sha256(parsed_text_preview.encode()).hexdigest()[:16]}',
                text=parsed_text_preview,
                source_artifact_id=artifact_id,
                source_family='evidence',
                source_record_id=record_id,
                source_ref=cid,
                record_scope='evidence',
                confidence=0.5,
                metadata=_merge_intake_summary_handoff_metadata(
                    lineage_metadata,
                    self.mediator,
                ),
                provenance=build_provenance(
                    source_url=str(provenance_payload.get('source_url', '')),
                    acquisition_method=str(provenance_payload.get('acquisition_method', '')),
                    source_type=str(provenance_payload.get('source_type', '')),
                    acquired_at=str(provenance_payload.get('acquired_at', '')),
                    content_hash=str(provenance_payload.get('content_hash', '')),
                    source_system=str(provenance_payload.get('source_system', '')),
                    jurisdiction=str(provenance_payload.get('jurisdiction', '')),
                    metadata=provenance_metadata,
                ),
            )
            memory_facts.append(fact.as_dict())
        record['fact_count'] = len(memory_facts)
        self._memory_records.append(record)
        self._memory_graphs[record_id] = document_graph if isinstance(document_graph, dict) else {'status': 'unavailable', 'entities': [], 'relationships': []}
        self._memory_facts[record_id] = memory_facts
        self.mediator.log('evidence_record_added_memory', record_id=record_id, cid=evidence_info.get('cid'))
        return {'record_id': record_id, 'created': True, 'reused': False}

    try:
        conn = duckdb.connect(self.db_path)
        normalized_evidence_metadata = _merge_intake_summary_handoff_metadata(
            evidence_info.get('metadata', {}),
            self.mediator,
        )
        provenance_payload = (
            dict(normalized_evidence_metadata.get('provenance') or {})
            if isinstance(normalized_evidence_metadata.get('provenance'), dict)
            else {}
        )
        provenance_metadata = _merge_intake_summary_handoff_metadata(
            provenance_payload.get('metadata', {}),
            self.mediator,
        )
        if provenance_metadata:
            provenance_payload['metadata'] = provenance_metadata
        if provenance_payload:
            normalized_evidence_metadata['provenance'] = provenance_payload
        document_parse = evidence_info.get('document_parse') if isinstance(evidence_info.get('document_parse'), dict) else {}
        document_graph = evidence_info.get('document_graph') if isinstance(evidence_info.get('document_graph'), dict) else {}
        document_graph_summary = normalized_evidence_metadata.get('document_graph_summary', {})
        parse_contract = build_document_parse_contract(
            document_parse,
            default_source=str(
                document_parse.get('metadata', {}).get('source')
                or normalized_evidence_metadata.get('parse_source')
                or ''
            ),
        )
        parse_metadata = _merge_intake_summary_handoff_metadata(
            parse_contract['storage_metadata'],
            self.mediator,
        )
        parsed_text = parse_contract['text']
        parsed_text_preview = parse_contract['text_preview']
        if not document_graph and parsed_text:
            document_graph = extract_graph_from_text(
                parsed_text,
                source_id=evidence_info.get('artifact_id') or evidence_info.get('cid'),
                metadata={
                    'artifact_id': evidence_info.get('artifact_id', ''),
                    'source_url': provenance_payload.get('source_url', ''),
                    'claim_type': claim_type or '',
                    'claim_element_id': claim_element_id or '',
                    'claim_element_text': claim_element or '',
                    'filename': document_parse.get('metadata', {}).get('filename', ''),
                    'mime_type': document_parse.get('metadata', {}).get('mime_type', ''),
                },
            )
            document_graph_summary = {
                'status': document_graph.get('status'),
                'entity_count': len(document_graph.get('entities', []) or []),
                'relationship_count': len(document_graph.get('relationships', []) or []),
            }
        graph_snapshot_scope = '|'.join(
            [
                str(Path(self.db_path).resolve()),
                str(user_id or ''),
                str(complaint_id or ''),
                str(evidence_info.get('cid') or ''),
            ]
        )
        graph_snapshot = persist_graph_snapshot(
            document_graph,
            graph_id=f"evidence-record:{hashlib.sha256(graph_snapshot_scope.encode('utf-8')).hexdigest()[:16]}",
            graph_changed=bool(document_graph.get('entities') or document_graph.get('relationships')),
            existing_graph=False,
            persistence_metadata=_merge_intake_summary_handoff_metadata(
                {
                    'record_scope': 'evidence',
                    'record_key': evidence_info.get('cid', ''),
                },
                self.mediator,
            ),
        )
        graph_metadata = {
            **(document_graph.get('metadata', {}) or {}),
            'graph_snapshot': graph_snapshot,
        }

        existing_record_id = self._find_existing_evidence_record(
            conn,
            user_id,
            evidence_info,
            complaint_id,
            claim_type,
            claim_element_id,
        )
        if existing_record_id is not None:
            conn.close()
            self.mediator.log(
                'evidence_record_duplicate',
                record_id=existing_record_id,
                cid=evidence_info.get('cid'),
                claim_type=claim_type,
                claim_element_id=claim_element_id,
            )
            return {'record_id': existing_record_id, 'created': False, 'reused': True}

        # Get username from mediator state if available
        state = getattr(self.mediator, 'state', None)
        username = getattr(state, 'username', None) if state is not None else None
        if not isinstance(username, str) or not username:
            username = user_id

        result = conn.execute("""
            INSERT INTO evidence (
                user_id, username, evidence_cid, evidence_type, 
                evidence_size, metadata, complaint_id, claim_type, description,
                content_hash, source_url, acquisition_method, provenance,
                claim_element_id, claim_element, parse_status, chunk_count,
                parsed_text_preview, parse_metadata, graph_status,
                graph_entity_count, graph_relationship_count, graph_metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
        """, [
            user_id,
            username,
            evidence_info['cid'],
            evidence_info['type'],
            evidence_info['size'],
            self._seal_json(normalized_evidence_metadata),
            complaint_id,
            claim_type,
            self._seal_column(description, 'description'),
            provenance_payload.get('content_hash'),
            provenance_payload.get('source_url'),
            provenance_payload.get('acquisition_method'),
            self._seal_json(provenance_payload),
            claim_element_id,
            self._seal_column(claim_element, 'claim_element'),
            parse_contract.get('status') or parse_metadata.get('status'),
            parse_contract.get('chunk_count', 0),
            self._seal_column(parsed_text_preview, 'parsed_text_preview'),
            self._seal_json(parse_metadata),
            document_graph.get('status') or document_graph_summary.get('status'),
            len(document_graph.get('entities', []) or []),
            len(document_graph.get('relationships', []) or []),
            self._seal_json(graph_metadata),
        ]).fetchone()

        record_id = result[0]
        self._store_document_chunks(conn, record_id, document_parse)
        self._store_document_graph(conn, record_id, document_graph)
        self._store_document_facts(conn, record_id, evidence_info, document_graph, document_parse)
        conn.close()

        self.mediator.log('evidence_record_added', 
            record_id=record_id, cid=evidence_info['cid'])

        return {'record_id': record_id, 'created': True, 'reused': False}

    except Exception as e:
        self.mediator.log(
            'evidence_record_error',
            operation='upsert_evidence_record',
            error=str(e),
            error_type=type(e).__name__,
        )
        raise EvidencePersistenceError(f'Failed to add evidence record: {str(e)}') from e


def _initialize_schema(self):
    """Initialize DuckDB schema for evidence tracking."""
    try:
        conn = duckdb.connect(self.db_path)

        # Create sequence for auto-incrementing IDs
        conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS evidence_id_seq START 1
        """)

        # Create evidence table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS evidence (
                id BIGINT PRIMARY KEY DEFAULT nextval('evidence_id_seq'),
                user_id VARCHAR,
                username VARCHAR,
                evidence_cid VARCHAR NOT NULL,
                evidence_type VARCHAR NOT NULL,
                evidence_size INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata JSON,
                complaint_id VARCHAR,
                claim_type VARCHAR,
                description TEXT
            )
        """)

        for statement in [
            "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS content_hash VARCHAR",
            "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS source_url VARCHAR",
            "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS acquisition_method VARCHAR",
            "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS provenance JSON",
            "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS claim_element_id VARCHAR",
            "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS claim_element TEXT",
            "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS parse_status VARCHAR",
            "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS chunk_count INTEGER",
            "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS parsed_text_preview TEXT",
            "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS parse_metadata JSON",
            "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS graph_status VARCHAR",
            "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS graph_entity_count INTEGER",
            "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS graph_relationship_count INTEGER",
            "ALTER TABLE evidence ADD COLUMN IF NOT EXISTS graph_metadata JSON",
        ]:
            conn.execute(statement)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS evidence_chunks (
                evidence_id BIGINT,
                chunk_id VARCHAR,
                chunk_index INTEGER,
                start_offset INTEGER,
                end_offset INTEGER,
                chunk_text TEXT,
                metadata JSON
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS evidence_graph_entities (
                evidence_id BIGINT,
                entity_id VARCHAR,
                entity_type VARCHAR,
                entity_name TEXT,
                confidence FLOAT,
                metadata JSON
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS evidence_graph_relationships (
                evidence_id BIGINT,
                relationship_id VARCHAR,
                source_id VARCHAR,
                target_id VARCHAR,
                relation_type VARCHAR,
                confidence FLOAT,
                metadata JSON
            )
        """)

        _ensure_evidence_fact_schema(conn)

        conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS scraper_run_id_seq START 1
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS scraper_runs (
                id BIGINT PRIMARY KEY DEFAULT nextval('scraper_run_id_seq'),
                user_id VARCHAR,
                username VARCHAR,
                claim_type VARCHAR,
                keywords JSON,
                domains JSON,
                iteration_count INTEGER,
                final_result_count INTEGER,
                stored_count INTEGER,
                new_count INTEGER,
                reused_count INTEGER,
                unique_url_count INTEGER,
                quality JSON,
                config JSON,
                metadata JSON,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS scraper_run_iterations (
                run_id BIGINT,
                iteration_index INTEGER,
                discovered_count INTEGER,
                accepted_count INTEGER,
                scraped_count INTEGER,
                coverage JSON,
                quality JSON,
                critique JSON
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS scraper_run_tactics (
                run_id BIGINT,
                iteration_index INTEGER,
                tactic_name VARCHAR,
                tactic_mode VARCHAR,
                query_text TEXT,
                weight FLOAT,
                discovered_count INTEGER,
                scraped_count INTEGER,
                accepted_count INTEGER,
                novelty_count INTEGER,
                quality_score FLOAT,
                quality JSON
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS scraper_run_coverage (
                run_id BIGINT,
                url TEXT,
                domain VARCHAR,
                source_type VARCHAR,
                last_seen_iteration INTEGER,
                metadata JSON
            )
        """)

        conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS scraper_queue_id_seq START 1
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS scraper_queue (
                id BIGINT PRIMARY KEY DEFAULT nextval('scraper_queue_id_seq'),
                user_id VARCHAR,
                username VARCHAR,
                claim_type VARCHAR,
                keywords JSON,
                domains JSON,
                iterations INTEGER,
                sleep_seconds DOUBLE,
                quality_domain VARCHAR,
                min_relevance DOUBLE,
                store_results BOOLEAN,
                priority INTEGER DEFAULT 100,
                status VARCHAR DEFAULT 'queued',
                available_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                claimed_at TIMESTAMP,
                completed_at TIMESTAMP,
                worker_id VARCHAR,
                run_id BIGINT,
                error TEXT,
                metadata JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create index on CID for fast lookups
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_evidence_cid 
            ON evidence(evidence_cid)
        """)

        # Create index on user_id for user-specific queries
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_evidence_user 
            ON evidence(user_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_scraper_queue_status_available
            ON scraper_queue(status, available_at)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_scraper_queue_user_status
            ON scraper_queue(user_id, status)
        """)

        conn.close()
        self.mediator.log('evidence_schema_initialized', db_path=self.db_path)

    except Exception as e:
        self.mediator.log(
            'evidence_schema_error',
            operation='initialize_evidence_schema',
            error=str(e),
            error_type=type(e).__name__,
        )


def persist_scraper_run(self,
                        user_id: str,
                        run_result: Dict[str, Any],
                        *,
                        keywords: Optional[List[str]] = None,
                        domains: Optional[List[str]] = None,
                        claim_type: Optional[str] = None,
                        stored_summary: Optional[Dict[str, Any]] = None,
                        config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Persist an agentic scraper run, its iterations, and coverage ledger."""
    if not DUCKDB_AVAILABLE:
        return {'persisted': False, 'run_id': -1}

    try:
        conn = duckdb.connect(self.db_path)
        state = getattr(self.mediator, 'state', None)
        username = getattr(state, 'username', None) if state is not None else None
        if not isinstance(username, str) or not username:
            username = user_id

        iterations = list(run_result.get('iterations', []) or [])
        final_results = list(run_result.get('final_results', []) or [])
        coverage_ledger = run_result.get('coverage_ledger', {}) if isinstance(run_result.get('coverage_ledger'), dict) else {}
        quality_payload = run_result.get('final_quality', {}) if isinstance(run_result.get('final_quality'), dict) else {}
        stored_summary = stored_summary or {}
        run_metadata = _merge_intake_summary_handoff_metadata(
            {'tactic_history': run_result.get('tactic_history', {})},
            self.mediator,
        )

        row = conn.execute(
            """
            INSERT INTO scraper_runs (
                user_id, username, claim_type, keywords, domains,
                iteration_count, final_result_count, stored_count, new_count, reused_count,
                unique_url_count, quality, config, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            [
                user_id,
                username,
                claim_type,
                json.dumps(keywords or []),
                json.dumps(domains or []),
                len(iterations),
                len(final_results),
                int(stored_summary.get('stored', 0) or 0),
                int(stored_summary.get('total_new', 0) or 0),
                int(stored_summary.get('total_reused', 0) or 0),
                len(coverage_ledger),
                json.dumps(quality_payload),
                json.dumps(config or {}),
                json.dumps(run_metadata),
            ],
        ).fetchone()
        run_id = int(row[0])

        for iteration in iterations:
            iteration_index = int(iteration.get('iteration', 0) or 0)
            iteration_coverage = _merge_intake_summary_handoff_metadata(
                iteration.get('coverage', {}),
                self.mediator,
            )
            iteration_quality = _merge_intake_summary_handoff_metadata(
                iteration.get('quality', {}),
                self.mediator,
            )
            iteration_critique = _merge_intake_summary_handoff_metadata(
                iteration.get('critique', {}),
                self.mediator,
            )
            conn.execute(
                """
                INSERT INTO scraper_run_iterations (
                    run_id, iteration_index, discovered_count, accepted_count, scraped_count,
                    coverage, quality, critique
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    run_id,
                    iteration_index,
                    int(iteration.get('discovered_count', 0) or 0),
                    int(iteration.get('accepted_count', 0) or 0),
                    int(iteration.get('scraped_count', 0) or 0),
                    json.dumps(iteration_coverage),
                    json.dumps(iteration_quality),
                    json.dumps(iteration_critique),
                ],
            )

            for tactic in iteration.get('tactics', []) or []:
                tactic_quality = _merge_intake_summary_handoff_metadata(
                    tactic.get('quality', {}),
                    self.mediator,
                )
                conn.execute(
                    """
                    INSERT INTO scraper_run_tactics (
                        run_id, iteration_index, tactic_name, tactic_mode, query_text,
                        weight, discovered_count, scraped_count, accepted_count,
                        novelty_count, quality_score, quality
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        run_id,
                        iteration_index,
                        tactic.get('name'),
                        tactic.get('mode'),
                        tactic.get('query'),
                        float(tactic.get('weight', 0.0) or 0.0),
                        int(tactic.get('discovered_count', 0) or 0),
                        int(tactic.get('scraped_count', 0) or 0),
                        int(tactic.get('accepted_count', 0) or 0),
                        int(tactic.get('novelty_count', 0) or 0),
                        float(tactic.get('quality_score', 0.0) or 0.0),
                        json.dumps(tactic_quality),
                    ],
                )

        for url, coverage in coverage_ledger.items():
            coverage_metadata = _merge_intake_summary_handoff_metadata(
                coverage if isinstance(coverage, dict) else {},
                self.mediator,
            )
            conn.execute(
                """
                INSERT INTO scraper_run_coverage (
                    run_id, url, domain, source_type, last_seen_iteration, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    run_id,
                    url,
                    coverage_metadata.get('domain', ''),
                    coverage_metadata.get('source_type', ''),
                    int(coverage_metadata.get('last_seen_iteration', 0) or 0),
                    json.dumps(coverage_metadata),
                ],
            )

        conn.close()
        self.mediator.log('scraper_run_persisted', run_id=run_id, user_id=user_id)
        return {'persisted': True, 'run_id': run_id}
    except Exception as e:
        self.mediator.log('scraper_run_persist_error', error=str(e), user_id=user_id)
        return {'persisted': False, 'run_id': -1, 'error': str(e)}


def store_evidence(self, data: bytes, evidence_type: str, 
                  metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Store evidence data in IPFS.

    Args:
        data: Evidence data as bytes
        evidence_type: Type of evidence (e.g., 'document', 'image', 'video', 'text')
        metadata: Optional metadata about the evidence

    Returns:
        Dictionary with:
        - cid: Content ID in IPFS
        - size: Size of data in bytes
        - type: Evidence type
        - timestamp: When stored
        - metadata: Any additional metadata
    """
    try:
        if self._is_public_legal_corpus(metadata):
            return self._store_public_legal_evidence(data, evidence_type, metadata)
        if self._private_route_bound:
            return self._store_private_evidence(data, evidence_type, metadata)
        storage_status = 'stored'
        storage_degraded_reason = ''
        storage_error_type = ''
        content_hash = stable_content_hash(data)
        provenance = build_provenance(
            source_url=str((metadata or {}).get('source_url', '')),
            acquisition_method=str((metadata or {}).get('acquisition_method', 'submitted')),
            source_type=str((metadata or {}).get('source_type', evidence_type)),
            acquired_at=datetime.now().isoformat(),
            content_hash=content_hash,
            source_system=str((metadata or {}).get('source_system', 'complaint_generator')),
            jurisdiction=str((metadata or {}).get('jurisdiction', '')),
        )
        provenance = build_provenance(
            source_url=str(provenance.source_url or ''),
            acquisition_method=str(provenance.acquisition_method or ''),
            source_type=str(provenance.source_type or ''),
            acquired_at=str(provenance.acquired_at or ''),
            content_hash=str(provenance.content_hash or ''),
            source_system=str(provenance.source_system or ''),
            jurisdiction=str(provenance.jurisdiction or ''),
            metadata=_merge_intake_summary_handoff_metadata(
                dict(getattr(provenance, 'metadata', {}) or {}),
                self.mediator,
            ),
        )
        normalized_metadata = _merge_intake_summary_handoff_metadata(
            merge_metadata_with_provenance(metadata, provenance),
            self.mediator,
        )
        if IPFS_AVAILABLE:
            try:
                # Store in IPFS
                cid = add_bytes(data, pin=True)
                self.mediator.log('evidence_stored', 
                    cid=cid, size=len(data), type=evidence_type)
            except Exception as ipfs_error:
                cid = f"Qm{hashlib.sha256(data).hexdigest()[:44]}"
                storage_status = 'degraded'
                storage_degraded_reason = str(ipfs_error) or type(ipfs_error).__name__
                storage_error_type = type(ipfs_error).__name__
                self.mediator.log(
                    'evidence_ipfs_runtime_unavailable',
                    error=str(ipfs_error),
                    error_type=type(ipfs_error).__name__,
                    operation='ipfs_add_bytes',
                    cid=cid,
                    size=len(data),
                    type=evidence_type,
                )
        else:
            # Fallback: Create a simulated CID using hash
            cid = f"Qm{hashlib.sha256(data).hexdigest()[:44]}"
            storage_status = 'degraded'
            storage_degraded_reason = 'IPFS backend unavailable; using deterministic local identifier'
            storage_error_type = 'BackendUnavailable'
            self.mediator.log('evidence_simulated', 
                cid=cid, size=len(data), type=evidence_type)

        artifact = CaseArtifact(
            cid=cid,
            artifact_type=evidence_type,
            size=len(data),
            timestamp=datetime.now().isoformat(),
            mime_type=str((metadata or {}).get('mime_type', '')),
            source_type=provenance.source_type,
            content_hash=content_hash,
            acquisition_method=provenance.acquisition_method,
            source_url=provenance.source_url,
            metadata=normalized_metadata,
            provenance=provenance,
        )
        result = artifact.as_dict()
        if self._should_parse_evidence(evidence_type, metadata):
            document_parse = parse_document(
                data=data,
                filename=str((metadata or {}).get('filename', '')),
                mime_type=str((metadata or {}).get('mime_type', '')),
                source=str((metadata or {}).get('parse_source', 'bytes')),
            )
            parse_contract = build_document_parse_contract(
                document_parse,
                default_source=str((metadata or {}).get('parse_source', 'bytes')),
            )
            result['document_parse'] = document_parse
            result['metadata']['document_parse_summary'] = parse_contract['summary']
            result['metadata']['document_parse_contract'] = parse_contract
            graph_payload = extract_graph_from_text(
                parse_contract.get('text', ''),
                source_id=result.get('artifact_id') or result.get('cid'),
                metadata={
                    'artifact_id': result.get('artifact_id', ''),
                    'filename': str((metadata or {}).get('filename', '')),
                    'mime_type': str((metadata or {}).get('mime_type', '')),
                    'source_url': provenance.source_url,
                    'claim_type': str((metadata or {}).get('claim_type', '')),
                    'claim_element_id': str((metadata or {}).get('claim_element_id', '')),
                    'claim_element_text': str((metadata or {}).get('claim_element', '')),
                    'title': str((metadata or {}).get('title', '')),
                },
            )
            result['document_graph'] = graph_payload
            result['metadata']['document_graph_summary'] = {
                'status': graph_payload.get('status'),
                'entity_count': len(graph_payload.get('entities', []) or []),
                'relationship_count': len(graph_payload.get('relationships', []) or []),
            }
        result['ipfs_available'] = IPFS_AVAILABLE
        result['ipfs_persisted'] = storage_status == 'stored'
        result['storage_status'] = storage_status
        if storage_degraded_reason:
            result['degraded_reason'] = storage_degraded_reason
            result['error_type'] = storage_error_type
        return result

    except EvidenceStorageError:
        raise
    except Exception as e:
        self.mediator.log(
            'evidence_storage_error',
            error=str(e),
            error_type=type(e).__name__,
            operation='store_evidence',
        )
        raise EvidenceStorageError(f'Failed to store evidence: {str(e)}') from e
