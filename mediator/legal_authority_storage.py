"""Authority storage methods delegated from LegalAuthorityStorageHook."""

from __future__ import annotations

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    duckdb = None

from mediator.legal_authority_hooks import (
    CaseAuthority,
    Path,
    RuleCandidate,
    _clip_source_passage_text,
    _ensure_legal_authority_fact_schema,
    _merge_handoff_into_provenance_record,
    _merge_intake_summary_handoff_metadata,
    build_document_parse_contract,
    build_fact_lineage_metadata,
    build_provenance,
    datetime,
    hashlib,
    json,
    persist_graph_snapshot,
)


def _initialize_schema(self):
    """Initialize DuckDB schema for legal authorities."""
    try:
        conn = duckdb.connect(self.db_path)

        # Create sequence for auto-incrementing IDs
        conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS legal_authorities_id_seq START 1
        """)

        # Create legal_authorities table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS legal_authorities (
                id BIGINT PRIMARY KEY DEFAULT nextval('legal_authorities_id_seq'),
                user_id VARCHAR,
                complaint_id VARCHAR,
                claim_type VARCHAR,
                authority_type VARCHAR NOT NULL,  -- statute, regulation, case_law, web_archive
                source VARCHAR NOT NULL,          -- us_code, federal_register, recap, web
                citation VARCHAR,                 -- Legal citation (e.g., "42 U.S.C. § 1983")
                title TEXT,
                content TEXT,
                url VARCHAR,
                metadata JSON,
                relevance_score FLOAT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                search_query VARCHAR
            )
        """)

        _ensure_legal_authority_fact_schema(conn)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS legal_authority_chunks (
                authority_id BIGINT,
                chunk_id VARCHAR,
                chunk_index INTEGER,
                start_offset INTEGER,
                end_offset INTEGER,
                chunk_text TEXT,
                metadata JSON
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS legal_authority_graph_entities (
                authority_id BIGINT,
                entity_id VARCHAR,
                entity_type VARCHAR,
                entity_name TEXT,
                confidence FLOAT,
                metadata JSON
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS legal_authority_graph_relationships (
                authority_id BIGINT,
                relationship_id VARCHAR,
                source_id VARCHAR,
                target_id VARCHAR,
                relation_type VARCHAR,
                confidence FLOAT,
                metadata JSON
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS legal_authority_treatments (
                authority_id BIGINT,
                treatment_id VARCHAR,
                treatment_type VARCHAR,
                treated_by_authority_id VARCHAR,
                treated_by_citation VARCHAR,
                treatment_source VARCHAR,
                treatment_confidence FLOAT,
                treatment_date VARCHAR,
                treatment_explanation TEXT,
                metadata JSON,
                provenance JSON
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS legal_authority_search_programs (
                authority_id BIGINT,
                program_id VARCHAR,
                program_type VARCHAR,
                claim_type VARCHAR,
                authority_intent VARCHAR,
                query_text TEXT,
                claim_element_id VARCHAR,
                claim_element_text TEXT,
                jurisdiction VARCHAR,
                forum VARCHAR,
                authority_families JSON,
                search_terms JSON,
                metadata JSON,
                provenance JSON
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS legal_authority_rule_candidates (
                authority_id BIGINT,
                rule_id VARCHAR,
                rule_text TEXT,
                rule_type VARCHAR,
                claim_element_id VARCHAR,
                claim_element_text TEXT,
                predicate_template VARCHAR,
                jurisdiction VARCHAR,
                temporal_scope VARCHAR,
                extraction_confidence FLOAT,
                metadata JSON,
                provenance JSON
            )
        """)

        for statement in [
            "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS jurisdiction VARCHAR",
            "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS source_system VARCHAR",
            "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS provenance JSON",
            "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS claim_element_id VARCHAR",
            "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS claim_element TEXT",
            "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS parse_status VARCHAR",
            "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS chunk_count INTEGER",
            "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS parsed_text_preview TEXT",
            "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS parse_metadata JSON",
            "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS graph_status VARCHAR",
            "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS graph_entity_count INTEGER",
            "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS graph_relationship_count INTEGER",
            "ALTER TABLE legal_authorities ADD COLUMN IF NOT EXISTS graph_metadata JSON",
        ]:
            conn.execute(statement)

        # Create indexes
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_authorities_user
            ON legal_authorities(user_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_authorities_claim
            ON legal_authorities(claim_type)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_authorities_citation
            ON legal_authorities(citation)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_authority_treatments_authority
            ON legal_authority_treatments(authority_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_authority_search_programs_authority
            ON legal_authority_search_programs(authority_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_authority_rule_candidates_authority
            ON legal_authority_rule_candidates(authority_id)
        """)

        conn.close()
        self.mediator.log('legal_authority_schema_initialized',
            db_path=self.db_path)

    except Exception as e:
        self.mediator.log('legal_authority_schema_error', error=str(e))
def _extract_rule_candidates(
    self,
    authority_id: int,
    authority: Dict[str, Any],
    claim_type: Optional[str],
    document_parse: Dict[str, Any],
    provenance,
    claim_element: Dict[str, Optional[str]],
) -> List[RuleCandidate]:
    parsed_text = str((document_parse or {}).get('text') or '')
    chunks = (document_parse or {}).get('chunks', []) or []
    parse_contract = build_document_parse_contract(document_parse or {}, default_source='legal_authority')
    base_lineage_metadata = build_fact_lineage_metadata(
        {},
        parse_contract=parse_contract,
        record_scope='legal_authority',
        source_ref=f'authority:{authority_id}',
    )
    candidate_rows: List[Dict[str, Any]] = []

    if chunks:
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            chunk_text = str(chunk.get('text') or '')
            chunk_start = int(chunk.get('start', 0) or 0)
            for sentence in self._split_rule_candidate_sentences(chunk_text):
                local_start = chunk_text.find(sentence)
                absolute_start = chunk_start + local_start if local_start >= 0 else chunk_start
                absolute_end = absolute_start + len(sentence)
                candidate_rows.append(
                    {
                        'text': sentence,
                        'chunk_id': str(chunk.get('chunk_id') or ''),
                        'chunk_index': int(chunk.get('index', 0) or 0),
                        'start': absolute_start,
                        'end': absolute_end,
                        'source_passage': {
                            'chunk_id': str(chunk.get('chunk_id') or ''),
                            'chunk_index': int(chunk.get('index', 0) or 0),
                            'start': absolute_start,
                            'end': absolute_end,
                            'text': _clip_source_passage_text(sentence),
                        },
                    }
                )
    else:
        search_start = 0
        for index, sentence in enumerate(self._split_rule_candidate_sentences(parsed_text)):
            local_start = parsed_text.find(sentence, search_start)
            absolute_start = local_start if local_start >= 0 else 0
            absolute_end = absolute_start + len(sentence)
            search_start = absolute_end
            candidate_rows.append(
                {
                    'text': sentence,
                    'chunk_id': '',
                    'chunk_index': index,
                    'start': absolute_start,
                    'end': absolute_end,
                    'source_passage': {
                        'chunk_id': '',
                        'chunk_index': index,
                        'start': absolute_start,
                        'end': absolute_end,
                        'text': _clip_source_passage_text(sentence),
                    },
                }
            )

    rule_candidates: List[RuleCandidate] = []
    seen_rule_texts = set()
    for row in candidate_rows:
        sentence = str(row.get('text') or '').strip()
        if len(sentence.split()) < 4:
            continue
        normalized_text = sentence.lower()
        if normalized_text in seen_rule_texts:
            continue
        seen_rule_texts.add(normalized_text)

        rule_type = self._classify_rule_candidate_type(sentence)
        claim_element_text = str(claim_element.get('claim_element') or '')
        predicate_template = claim_element_text or str(claim_type or '')
        grounded_rule = self._build_grounded_rule_metadata(
            sentence,
            rule_type,
            authority_id=authority_id,
            authority=authority,
            claim_element=claim_element,
            provenance=provenance,
        )
        rule_candidates.append(
            RuleCandidate(
                authority_id=f'authority:{authority_id}',
                rule_text=sentence,
                rule_type=rule_type,
                claim_element_id=str(claim_element.get('claim_element_id') or ''),
                claim_element_text=claim_element_text,
                predicate_template=predicate_template,
                jurisdiction=str(provenance.jurisdiction or ''),
                temporal_scope=str(authority.get('metadata', {}).get('effective_date') or ''),
                extraction_confidence=self._rule_candidate_confidence(sentence, claim_element_text),
                metadata=_merge_intake_summary_handoff_metadata(
                    {
                        **base_lineage_metadata,
                        'chunk_id': row.get('chunk_id', ''),
                        'chunk_index': row.get('chunk_index', 0),
                        'source_span': {
                            'start': row.get('start', 0),
                            'end': row.get('end', 0),
                        },
                        'source_passage': row.get('source_passage', {}),
                        'claim_type': claim_type or '',
                        'authority_type': authority.get('type', ''),
                        'authority_source': authority.get('source', ''),
                        'grounded_rule': grounded_rule,
                    },
                    self.mediator,
                ),
                provenance=_merge_handoff_into_provenance_record(provenance, self.mediator),
            )
        )

    return rule_candidates[:25]
def upsert_authority(self, authority_data: Dict[str, Any],
                    user_id: str, complaint_id: Optional[str] = None,
                    claim_type: Optional[str] = None,
                    search_query: Optional[str] = None) -> Dict[str, Any]:
    """
    Add a legal authority to the database.

    Args:
        authority_data: Authority information from search
        user_id: User identifier
        complaint_id: Optional complaint ID
        claim_type: Optional claim type
        search_query: Original search query

    Returns:
        Dictionary describing whether the authority was newly inserted or reused.
    """
    if not DUCKDB_AVAILABLE:
        self.mediator.log('legal_authority_storage_unavailable')
        return {'record_id': -1, 'created': False, 'reused': False}

    try:
        conn = duckdb.connect(self.db_path)
        claim_element = self._resolve_claim_element(user_id, claim_type, authority_data)
        document_parse = self._parse_authority_text(authority_data)
        parse_contract = build_document_parse_contract(document_parse, default_source='legal_authority')
        parse_storage_metadata = _merge_intake_summary_handoff_metadata(
            parse_contract.get('storage_metadata', {}),
            self.mediator,
        )
        parsed_text = parse_contract.get('text', '')
        parsed_text_preview = parse_contract.get('text_preview', '')
        authority_record_metadata = _merge_intake_summary_handoff_metadata(
            {
                **(authority_data.get('metadata', {}) if isinstance(authority_data.get('metadata', {}), dict) else {}),
                'claim_element_id': claim_element.get('claim_element_id'),
                'claim_element': claim_element.get('claim_element'),
                'search_programs': self._normalize_search_programs(authority_data),
            },
            self.mediator,
        )
        provenance = build_provenance(
            source_url=str(authority_data.get('url', '')),
            acquisition_method='legal_search',
            source_type=str(authority_data.get('type', 'unknown')),
            acquired_at=datetime.now().isoformat(),
            source_system=str(authority_data.get('source', 'unknown')),
            jurisdiction=str(authority_data.get('jurisdiction', '')),
            metadata=_merge_intake_summary_handoff_metadata(
                self._build_authority_provenance_metadata(authority_data, document_parse),
                self.mediator,
            ),
        )
        authority = CaseAuthority(
            authority_type=authority_data.get('type', 'unknown'),
            source=authority_data.get('source', 'unknown'),
            citation=authority_data.get('citation') or '',
            title=authority_data.get('title') or '',
            content=(
                authority_data.get('content')
                or authority_data.get('text')
                or authority_data.get('html_body')
                or authority_data.get('raw_html')
                or ''
            ),
            url=authority_data.get('url') or '',
            jurisdiction=provenance.jurisdiction,
            source_system=provenance.source_system,
            claim_element_id=claim_element.get('claim_element_id') or '',
            claim_element=claim_element.get('claim_element') or '',
            relevance_score=authority_data.get('relevance_score', 0.5),
            metadata=authority_record_metadata,
            provenance=provenance,
        )
        normalized_authority = authority.as_dict()

        existing_record_id = self._find_existing_authority_record(
            conn,
            user_id,
            complaint_id,
            claim_type,
            normalized_authority,
        )
        if existing_record_id is not None:
            self._store_authority_search_programs(
                conn,
                existing_record_id,
                self._build_search_program_records(existing_record_id, authority_data, provenance, claim_type),
            )
            self._store_authority_treatments(
                conn,
                existing_record_id,
                self._build_treatment_records(existing_record_id, authority_data, provenance),
            )
            self._store_authority_rule_candidates(
                conn,
                existing_record_id,
                self._extract_rule_candidates(
                    existing_record_id,
                    normalized_authority,
                    claim_type,
                    document_parse,
                    provenance,
                    claim_element,
                ),
            )
            conn.close()
            self.mediator.log(
                'legal_authority_duplicate',
                record_id=existing_record_id,
                citation=normalized_authority.get('citation'),
                url=normalized_authority.get('url'),
                claim_type=claim_type,
                claim_element_id=normalized_authority.get('claim_element_id'),
            )
            return {'record_id': existing_record_id, 'created': False, 'reused': True}

        stored_content = normalized_authority.get('content')
        stored_preview = parsed_text_preview
        stored_title = normalized_authority.get('title')
        stored_claim_element = claim_element.get('claim_element')
        authority_meta = authority_data.get('metadata') if isinstance(authority_data.get('metadata'), dict) else {}
        is_public_law = (
            authority_data.get('storage_class') == 'public_legal_corpus'
            or authority_data.get('classification') == 'public_legal_corpus'
            or authority_meta.get('storage_class') == 'public_legal_corpus'
        )
        if is_public_law and self._private_columns_sealed():
            cached = self.cache_public_law_source(
                citation=str(normalized_authority.get('citation') or ''),
                text=str(stored_content or stored_preview or ''),
            )
            authority_record_metadata = dict(authority_record_metadata)
            authority_record_metadata['public_cache_id'] = cached['cache_id']
            authority_record_metadata['storage_class'] = 'public_legal_corpus'
            stored_content = ''
            stored_preview = ''
        if self._private_columns_sealed() and not is_public_law:
            stored_content = self._seal_column(stored_content, 'content')
            stored_preview = self._seal_column(stored_preview, 'parsed_text_preview')
            stored_title = self._seal_column(stored_title, 'title')
        if self._private_columns_sealed():
            stored_claim_element = self._seal_column(stored_claim_element, 'claim_element')
            search_query = self._seal_column(search_query, 'search_query')

        result = conn.execute("""
            INSERT INTO legal_authorities (
                user_id, complaint_id, claim_type, authority_type,
                source, citation, title, content, url, metadata,
                relevance_score, search_query, jurisdiction,
                source_system, provenance, claim_element_id, claim_element,
                parse_status, chunk_count, parsed_text_preview, parse_metadata,
                graph_status, graph_entity_count, graph_relationship_count, graph_metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
        """, [
            user_id,
            complaint_id,
            claim_type,
            normalized_authority.get('type', 'unknown'),
            normalized_authority.get('source', 'unknown'),
            normalized_authority.get('citation'),
            stored_title,
            stored_content,
            normalized_authority.get('url'),
            self._seal_json(authority_record_metadata),
            normalized_authority.get('relevance_score', 0.5),
            search_query,
            provenance.jurisdiction,
            provenance.source_system,
            self._seal_json(provenance.as_dict()),
            claim_element.get('claim_element_id'),
            stored_claim_element,
            parse_contract.get('status'),
            parse_contract.get('chunk_count', 0),
            stored_preview,
            self._seal_json(parse_storage_metadata),
            None,
            0,
            0,
            json.dumps({}),
        ]).fetchone()

        record_id = result[0]
        graph_payload = self._extract_authority_graph(
            record_id,
            normalized_authority,
            claim_type,
            document_parse=document_parse,
        )
        graph_snapshot_scope = '|'.join(
            [
                str(Path(self.db_path).resolve()),
                str(user_id or ''),
                str(complaint_id or ''),
                str(record_id),
            ]
        )
        conn.execute(
            """
            UPDATE legal_authorities
            SET graph_status = ?,
                graph_entity_count = ?,
                graph_relationship_count = ?,
                graph_metadata = ?
            WHERE id = ?
            """,
            [
                graph_payload.get('status'),
                len(graph_payload.get('entities', []) or []),
                len(graph_payload.get('relationships', []) or []),
                json.dumps({
                    **(graph_payload.get('metadata', {}) or {}),
                    'graph_snapshot': persist_graph_snapshot(
                        graph_payload,
                        graph_id=f"legal-authority-record:{hashlib.sha256(graph_snapshot_scope.encode('utf-8')).hexdigest()[:16]}",
                        graph_changed=bool(graph_payload.get('entities') or graph_payload.get('relationships')),
                        existing_graph=False,
                        persistence_metadata=_merge_intake_summary_handoff_metadata(
                            {
                                'record_scope': 'legal_authority',
                                'record_key': str(record_id),
                            },
                            self.mediator,
                        ),
                    ),
                }),
                record_id,
            ],
        )
        self._suppress_authority_plaintext = bool(is_public_law and self._private_columns_sealed())
        self._store_authority_chunks(conn, record_id, document_parse)
        self._store_authority_graph(conn, record_id, graph_payload)
        self._store_authority_facts(
            conn,
            record_id,
            graph_payload,
            provenance,
            document_parse,
        )
        self._suppress_authority_plaintext = False
        self._store_authority_search_programs(
            conn,
            record_id,
            self._build_search_program_records(record_id, authority_data, provenance, claim_type),
        )
        self._store_authority_treatments(
            conn,
            record_id,
            self._build_treatment_records(record_id, authority_data, provenance),
        )
        self._store_authority_rule_candidates(
            conn,
            record_id,
            self._extract_rule_candidates(
                record_id,
                normalized_authority,
                claim_type,
                document_parse,
                provenance,
                claim_element,
            ),
        )
        conn.close()

        self.mediator.log('legal_authority_added',
            record_id=record_id, citation=authority_data.get('citation'))

        return {'record_id': record_id, 'created': True, 'reused': False}

    except Exception as e:
        self.mediator.log('legal_authority_storage_error', error=str(e))
        raise Exception(f'Failed to store legal authority: {str(e)}')
