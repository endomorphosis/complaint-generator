"""Scraper queue operations delegated from the evidence hooks."""

from __future__ import annotations

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    duckdb = None

from mediator.evidence_hooks import (
    Any,
    DegradedEvidenceResults,
    Dict,
    List,
    Optional,
    UTC,
    _merge_intake_summary_handoff_metadata,
    datetime,
    json,
)


def get_scraper_run_details(self, run_id: int) -> Dict[str, Any]:
    """Return one persisted scraper run with iterations, tactics, and coverage rows."""
    if not DUCKDB_AVAILABLE:
        return {'available': False}

    try:
        conn = duckdb.connect(self.db_path)
        run_row = conn.execute(
            """
            SELECT id, user_id, username, claim_type, keywords, domains,
                   iteration_count, final_result_count, stored_count, new_count,
                   reused_count, unique_url_count, quality, config, metadata, timestamp
            FROM scraper_runs
            WHERE id = ?
            LIMIT 1
            """,
            [int(run_id)],
        ).fetchone()
        if not run_row:
            conn.close()
            return {'available': False, 'run_id': run_id}

        iteration_rows = conn.execute(
            """
            SELECT iteration_index, discovered_count, accepted_count, scraped_count,
                   coverage, quality, critique
            FROM scraper_run_iterations
            WHERE run_id = ?
            ORDER BY iteration_index ASC
            """,
            [int(run_id)],
        ).fetchall()
        tactic_rows = conn.execute(
            """
            SELECT iteration_index, tactic_name, tactic_mode, query_text, weight,
                   discovered_count, scraped_count, accepted_count, novelty_count,
                   quality_score, quality
            FROM scraper_run_tactics
            WHERE run_id = ?
            ORDER BY iteration_index ASC, tactic_name ASC
            """,
            [int(run_id)],
        ).fetchall()
        coverage_rows = conn.execute(
            """
            SELECT url, domain, source_type, last_seen_iteration, metadata
            FROM scraper_run_coverage
            WHERE run_id = ?
            ORDER BY last_seen_iteration ASC, url ASC
            """,
            [int(run_id)],
        ).fetchall()
        conn.close()

        tactics_by_iteration: Dict[int, List[Dict[str, Any]]] = {}
        for row in tactic_rows:
            tactics_by_iteration.setdefault(row[0], []).append({
                'iteration': row[0],
                'name': row[1],
                'mode': row[2],
                'query': row[3],
                'weight': row[4] or 0.0,
                'discovered_count': row[5] or 0,
                'scraped_count': row[6] or 0,
                'accepted_count': row[7] or 0,
                'novelty_count': row[8] or 0,
                'quality_score': row[9] or 0.0,
                'quality': json.loads(row[10]) if row[10] else {},
            })

        iterations = []
        for row in iteration_rows:
            iteration_index = row[0]
            iterations.append({
                'iteration': iteration_index,
                'discovered_count': row[1] or 0,
                'accepted_count': row[2] or 0,
                'scraped_count': row[3] or 0,
                'coverage': json.loads(row[4]) if row[4] else {},
                'quality': json.loads(row[5]) if row[5] else {},
                'critique': json.loads(row[6]) if row[6] else {},
                'tactics': tactics_by_iteration.get(iteration_index, []),
            })

        return {
            'available': True,
            'run': {
                'id': run_row[0],
                'user_id': run_row[1],
                'username': run_row[2],
                'claim_type': run_row[3],
                'keywords': json.loads(run_row[4]) if run_row[4] else [],
                'domains': json.loads(run_row[5]) if run_row[5] else [],
                'iteration_count': run_row[6] or 0,
                'final_result_count': run_row[7] or 0,
                'stored_count': run_row[8] or 0,
                'new_count': run_row[9] or 0,
                'reused_count': run_row[10] or 0,
                'unique_url_count': run_row[11] or 0,
                'quality': json.loads(run_row[12]) if run_row[12] else {},
                'config': json.loads(run_row[13]) if run_row[13] else {},
                'metadata': json.loads(run_row[14]) if run_row[14] else {},
                'timestamp': run_row[15],
            },
            'iterations': iterations,
            'coverage': [
                {
                    'url': row[0],
                    'domain': row[1],
                    'source_type': row[2],
                    'last_seen_iteration': row[3] or 0,
                    'metadata': json.loads(row[4]) if row[4] else {},
                }
                for row in coverage_rows
            ],
        }
    except Exception as e:
        self.mediator.log('scraper_run_detail_error', error=str(e), run_id=run_id)
        return {'available': False, 'run_id': run_id, 'error': str(e)}


def complete_scraper_job(self,
                         job_id: int,
                         *,
                         run_id: Optional[int] = None,
                         error: Optional[str] = None,
                         metadata: Optional[Dict[str, Any]] = None,
                         worker_id: Optional[str] = None) -> Dict[str, Any]:
    """Mark a claimed scraper job as completed or failed."""
    if not DUCKDB_AVAILABLE:
        return {'updated': False, 'job_id': job_id}

    try:
        conn = duckdb.connect(self.db_path)
        current = conn.execute(
            """
            SELECT status, worker_id, metadata
            FROM scraper_queue
            WHERE id = ?
            LIMIT 1
            """,
            [int(job_id)],
        ).fetchone()
        if not current:
            conn.close()
            return {'updated': False, 'job_id': job_id, 'error': 'job_not_found'}
        current_status = str(current[0] or '')
        current_worker_id = str(current[1] or '')
        if current_status != 'running':
            conn.close()
            return {
                'updated': False,
                'job_id': job_id,
                'error': 'job_not_running',
                'current_status': current_status,
            }
        if worker_id and current_worker_id and str(worker_id) != current_worker_id:
            conn.close()
            return {
                'updated': False,
                'job_id': job_id,
                'error': 'worker_mismatch',
                'worker_id': worker_id,
                'claimed_worker_id': current_worker_id,
            }

        merged_metadata = json.loads(current[2]) if current and current[2] else {}
        if metadata:
            merged_metadata.update(metadata)
        merged_metadata = _merge_intake_summary_handoff_metadata(
            merged_metadata,
            self.mediator,
        )

        status = 'failed' if error else 'completed'
        row = conn.execute(
            """
            UPDATE scraper_queue
            SET status = ?,
                completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                run_id = ?,
                error = ?,
                metadata = ?
            WHERE id = ? AND status = 'running'
            RETURNING id, user_id, username, claim_type, keywords, domains,
                      iterations, sleep_seconds, quality_domain, min_relevance,
                      store_results, priority, status, available_at, claimed_at,
                      completed_at, worker_id, run_id, error, metadata,
                      created_at, updated_at
            """,
            [status, run_id, error, json.dumps(merged_metadata), int(job_id)],
        ).fetchone()
        conn.close()
        if not row:
            return {'updated': False, 'job_id': job_id}

        job = self._serialize_scraper_queue_row(row)
        self.mediator.log('scraper_job_completed', job_id=job_id, status=status, run_id=run_id)
        return {'updated': True, 'job': job}
    except Exception as e:
        self.mediator.log('scraper_job_complete_error', error=str(e), job_id=job_id)
        return {'updated': False, 'job_id': job_id, 'error': str(e)}


def enqueue_scraper_job(self,
                        user_id: str,
                        keywords: List[str],
                        *,
                        domains: Optional[List[str]] = None,
                        claim_type: Optional[str] = None,
                        iterations: int = 3,
                        sleep_seconds: float = 0.0,
                        quality_domain: str = 'caselaw',
                        min_relevance: float = 0.5,
                        store_results: bool = True,
                        priority: int = 100,
                        available_at: Optional[datetime] = None,
                        metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Queue a scraper job for later worker consumption."""
    if not DUCKDB_AVAILABLE:
        return {'queued': False, 'job_id': -1}

    try:
        conn = duckdb.connect(self.db_path)
        state = getattr(self.mediator, 'state', None)
        username = getattr(state, 'username', None) if state is not None else None
        if not isinstance(username, str) or not username:
            username = user_id
        queued_metadata = _merge_intake_summary_handoff_metadata(
            metadata,
            self.mediator,
        )

        row = conn.execute(
            """
            INSERT INTO scraper_queue (
                user_id, username, claim_type, keywords, domains,
                iterations, sleep_seconds, quality_domain, min_relevance,
                store_results, priority, available_at, metadata, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            [
                user_id,
                username,
                claim_type,
                json.dumps(keywords or []),
                json.dumps(domains or []),
                int(iterations),
                float(sleep_seconds),
                quality_domain,
                float(min_relevance),
                bool(store_results),
                int(priority),
                available_at or datetime.now(UTC),
                json.dumps(queued_metadata or {}),
            ],
        ).fetchone()
        conn.close()
        job_id = int(row[0])
        self.mediator.log('scraper_job_enqueued', job_id=job_id, user_id=user_id)
        return {'queued': True, 'job_id': job_id}
    except Exception as e:
        self.mediator.log('scraper_job_enqueue_error', error=str(e), user_id=user_id)
        return {'queued': False, 'job_id': -1, 'error': str(e)}


def claim_next_scraper_job(self,
                           worker_id: str,
                           *,
                           user_id: Optional[str] = None) -> Dict[str, Any]:
    """Claim the next available scraper job so only queued work is processed."""
    if not DUCKDB_AVAILABLE:
        return {'claimed': False, 'job': None}

    try:
        conn = duckdb.connect(self.db_path)
        for _ in range(3):
            clauses = ["status = 'queued'", 'available_at <= CURRENT_TIMESTAMP']
            params: List[Any] = []
            if user_id:
                clauses.append('user_id = ?')
                params.append(user_id)

            row = conn.execute(
                f"""
                SELECT id
                FROM scraper_queue
                WHERE {' AND '.join(clauses)}
                ORDER BY priority ASC, available_at ASC, created_at ASC
                LIMIT 1
                """,
                params,
            ).fetchone()
            if not row:
                conn.close()
                return {'claimed': False, 'job': None}

            claimed_row = conn.execute(
                """
                UPDATE scraper_queue
                SET status = 'running',
                    claimed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP,
                    worker_id = ?
                WHERE id = ? AND status = 'queued'
                RETURNING id, user_id, username, claim_type, keywords, domains,
                          iterations, sleep_seconds, quality_domain, min_relevance,
                          store_results, priority, status, available_at, claimed_at,
                          completed_at, worker_id, run_id, error, metadata,
                          created_at, updated_at
                """,
                [worker_id, int(row[0])],
            ).fetchone()
            if claimed_row:
                conn.close()
                job = self._serialize_scraper_queue_row(claimed_row)
                self.mediator.log('scraper_job_claimed', job_id=job['id'], worker_id=worker_id)
                return {'claimed': True, 'job': job}

        conn.close()
        return {'claimed': False, 'job': None}
    except Exception as e:
        self.mediator.log('scraper_job_claim_error', error=str(e), worker_id=worker_id, user_id=user_id)
        return {'claimed': False, 'job': None, 'error': str(e)}


def get_scraper_runs(self, user_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """Return persisted scraper runs with summary metadata."""
    if not DUCKDB_AVAILABLE:
        return []

    try:
        conn = duckdb.connect(self.db_path)
        if user_id:
            rows = conn.execute(
                """
                SELECT id, user_id, username, claim_type, keywords, domains,
                       iteration_count, final_result_count, stored_count, new_count,
                       reused_count, unique_url_count, quality, config, metadata, timestamp
                FROM scraper_runs
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                [user_id, int(limit)],
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, user_id, username, claim_type, keywords, domains,
                       iteration_count, final_result_count, stored_count, new_count,
                       reused_count, unique_url_count, quality, config, metadata, timestamp
                FROM scraper_runs
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                [int(limit)],
            ).fetchall()
        conn.close()
        return [
            {
                'id': row[0],
                'user_id': row[1],
                'username': row[2],
                'claim_type': row[3],
                'keywords': json.loads(row[4]) if row[4] else [],
                'domains': json.loads(row[5]) if row[5] else [],
                'iteration_count': row[6] or 0,
                'final_result_count': row[7] or 0,
                'stored_count': row[8] or 0,
                'new_count': row[9] or 0,
                'reused_count': row[10] or 0,
                'unique_url_count': row[11] or 0,
                'quality': json.loads(row[12]) if row[12] else {},
                'config': json.loads(row[13]) if row[13] else {},
                'metadata': json.loads(row[14]) if row[14] else {},
                'timestamp': row[15],
            }
            for row in rows
        ]
    except Exception as e:
        self.mediator.log('scraper_run_query_error', error=str(e), user_id=user_id)
        return DegradedEvidenceResults(operation='get_scraper_runs', error=e)


def get_scraper_queue(self,
                      user_id: Optional[str] = None,
                      status: Optional[str] = None,
                      limit: int = 20) -> List[Dict[str, Any]]:
    """Return queued/running/completed scraper jobs."""
    if not DUCKDB_AVAILABLE:
        return []

    try:
        conn = duckdb.connect(self.db_path)
        clauses: List[str] = []
        params: List[Any] = []
        if user_id:
            clauses.append('user_id = ?')
            params.append(user_id)
        if status:
            clauses.append('status = ?')
            params.append(status)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ''
        rows = conn.execute(
            f"""
            SELECT id, user_id, username, claim_type, keywords, domains,
                   iterations, sleep_seconds, quality_domain, min_relevance,
                   store_results, priority, status, available_at, claimed_at,
                   completed_at, worker_id, run_id, error, metadata,
                   created_at, updated_at
            FROM scraper_queue
            {where_sql}
            ORDER BY
                CASE status WHEN 'running' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END,
                priority ASC,
                available_at ASC,
                created_at ASC
            LIMIT ?
            """,
            [*params, int(limit)],
        ).fetchall()
        conn.close()
        return [self._serialize_scraper_queue_row(row) for row in rows]
    except Exception as e:
        self.mediator.log('scraper_queue_query_error', error=str(e), user_id=user_id, status=status)
        return DegradedEvidenceResults(operation='get_scraper_queue', error=e)
