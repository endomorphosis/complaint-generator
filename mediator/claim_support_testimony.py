"""Testimony persistence delegated from ClaimSupportHook."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from claim_support_review import _merge_intake_summary_handoff_metadata

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    duckdb = None


def save_testimony_record(
    self,
    user_id: str,
    claim_type: str,
    *,
    claim_element_id: Optional[str] = None,
    claim_element_text: Optional[str] = None,
    raw_narrative: Optional[str] = None,
    event_date: Optional[str] = None,
    actor: Optional[str] = None,
    act: Optional[str] = None,
    target: Optional[str] = None,
    harm: Optional[str] = None,
    firsthand_status: Optional[str] = None,
    source_confidence: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not DUCKDB_AVAILABLE:
        return {
            'available': False,
            'recorded': False,
            'claim_type': claim_type,
            'error': 'duckdb_unavailable',
        }

    resolved_element = self.resolve_claim_element(
        user_id,
        claim_type,
        claim_element_id=claim_element_id,
        claim_element_text=claim_element_text,
        support_label=raw_narrative,
        metadata=metadata,
    )

    normalized_payload = {
        'claim_element_id': str(
            resolved_element.get('claim_element_id') or claim_element_id or ''
        ),
        'claim_element_text': str(
            resolved_element.get('claim_element_text') or claim_element_text or ''
        ),
        'raw_narrative': str(raw_narrative or '').strip(),
        'event_date': str(event_date or '').strip(),
        'actor': str(actor or '').strip(),
        'act': str(act or '').strip(),
        'target': str(target or '').strip(),
        'harm': str(harm or '').strip(),
        'firsthand_status': str(firsthand_status or 'unknown').strip() or 'unknown',
        'source_confidence': source_confidence,
        'metadata': _merge_intake_summary_handoff_metadata(
            dict(metadata or {}),
            self.mediator,
        ),
    }
    has_content = any(
        normalized_payload[field]
        for field in ('raw_narrative', 'event_date', 'actor', 'act', 'target', 'harm')
    )
    if not has_content:
        return {
            'available': True,
            'recorded': False,
            'claim_type': claim_type,
            'error': 'empty_testimony',
        }

    created_at = datetime.now(timezone.utc).isoformat()
    testimony_id = self._make_testimony_id(
        user_id=user_id,
        claim_type=claim_type,
        claim_element_id=normalized_payload['claim_element_id'],
        raw_narrative=normalized_payload['raw_narrative'],
        created_at=created_at,
    )

    try:
        conn = duckdb.connect(self.db_path)
        row = conn.execute(
            """
            INSERT INTO claim_testimony (
                testimony_id,
                user_id,
                claim_type,
                claim_element_id,
                claim_element_text,
                raw_narrative,
                event_date,
                actor_name,
                act_text,
                target_text,
                harm_text,
                firsthand_status,
                source_confidence,
                metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id, timestamp
            """,
            [
                testimony_id,
                user_id,
                claim_type,
                normalized_payload['claim_element_id'] or None,
                normalized_payload['claim_element_text'] or None,
                normalized_payload['raw_narrative'] or None,
                normalized_payload['event_date'] or None,
                normalized_payload['actor'] or None,
                normalized_payload['act'] or None,
                normalized_payload['target'] or None,
                normalized_payload['harm'] or None,
                normalized_payload['firsthand_status'] or None,
                normalized_payload['source_confidence'],
                json.dumps(normalized_payload['metadata'], default=str),
            ],
        ).fetchone()
        conn.close()
    except Exception as exc:
        self.mediator.log('claim_testimony_save_error', error=str(exc), claim_type=claim_type)
        return {
            'available': False,
            'recorded': False,
            'claim_type': claim_type,
            'error': str(exc),
        }

    return {
        'available': True,
        'recorded': True,
        'record_id': row[0],
        'timestamp': row[1].isoformat() if hasattr(row[1], 'isoformat') else row[1],
        'testimony_id': testimony_id,
        'user_id': user_id,
        'claim_type': claim_type,
        **normalized_payload,
    }
def backfill_claim_testimony_links(
    self,
    user_id: Optional[str] = None,
    claim_type: Optional[str] = None,
    *,
    limit: int = 0,
    dry_run: bool = False,
) -> Dict[str, Any]:
    normalized_limit = max(0, int(limit or 0))
    if not DUCKDB_AVAILABLE:
        return {
            'available': False,
            'user_id': user_id,
            'claim_type': claim_type,
            'limit': normalized_limit,
            'dry_run': bool(dry_run),
            'scanned_count': 0,
            'candidate_count': 0,
            'updated_count': 0,
            'records': [],
        }

    where_clauses = ["(claim_element_id IS NULL OR TRIM(claim_element_id) = '')"]
    parameters: List[Any] = []
    if user_id:
        where_clauses.append('user_id = ?')
        parameters.append(user_id)
    if claim_type:
        where_clauses.append('claim_type = ?')
        parameters.append(claim_type)

    limit_clause = ''
    if normalized_limit:
        limit_clause = 'LIMIT ?'
        parameters.append(normalized_limit)

    try:
        conn = duckdb.connect(self.db_path)
        rows = conn.execute(
            f"""
            SELECT
                id,
                user_id,
                testimony_id,
                claim_type,
                claim_element_id,
                claim_element_text,
                raw_narrative,
                metadata,
                timestamp
            FROM claim_testimony
            WHERE {' AND '.join(where_clauses)}
            ORDER BY timestamp DESC, id DESC
            {limit_clause}
            """,
            parameters,
        ).fetchall()
    except Exception as exc:
        self.mediator.log('claim_testimony_backfill_error', error=str(exc), claim_type=claim_type)
        return {
            'available': False,
            'user_id': user_id,
            'claim_type': claim_type,
            'limit': normalized_limit,
            'dry_run': bool(dry_run),
            'scanned_count': 0,
            'candidate_count': 0,
            'updated_count': 0,
            'records': [],
            'error': str(exc),
        }

    updated_records: List[Dict[str, Any]] = []
    for row in rows:
        entry_metadata = json.loads(row[7]) if row[7] else {}
        resolved = self._resolve_testimony_claim_element(
            record_id=row[0],
            row_user_id=row[1],
            claim_type=row[3],
            claim_element_id=row[4],
            claim_element_text=row[5],
            raw_narrative=row[6],
            entry_metadata=entry_metadata,
            conn=conn,
            persist_updates=not dry_run,
        )
        if not resolved['backfilled']:
            continue
        updated_records.append({
            'record_id': row[0],
            'user_id': row[1],
            'testimony_id': row[2],
            'claim_type': row[3],
            'claim_element_id': resolved['claim_element_id'],
            'claim_element_text': resolved['claim_element_text'],
            'timestamp': row[8].isoformat() if hasattr(row[8], 'isoformat') else row[8],
        })

    conn.close()

    return {
        'available': True,
        'user_id': user_id,
        'claim_type': claim_type,
        'limit': normalized_limit,
        'dry_run': bool(dry_run),
        'scanned_count': len(rows),
        'candidate_count': len(updated_records),
        'updated_count': 0 if dry_run else len(updated_records),
        'records': updated_records,
    }
def get_claim_testimony_records(
    self,
    user_id: str,
    claim_type: Optional[str] = None,
    claim_element_id: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    normalized_limit = max(0, int(limit or 0))
    if not DUCKDB_AVAILABLE:
        return self._with_intake_summary_handoff({
            'available': False,
            'user_id': user_id,
            'claim_type': claim_type,
            'limit': normalized_limit,
            'claims': {},
            'summary': {},
        })

    where_clauses = ['user_id = ?']
    parameters: List[Any] = [user_id]
    if claim_type:
        where_clauses.append('claim_type = ?')
        parameters.append(claim_type)
    if claim_element_id:
        where_clauses.append('claim_element_id = ?')
        parameters.append(claim_element_id)
    parameters.append(normalized_limit)

    try:
        conn = duckdb.connect(self.db_path)
        rows = conn.execute(
            f"""
            SELECT
                id,
                testimony_id,
                claim_type,
                claim_element_id,
                claim_element_text,
                raw_narrative,
                event_date,
                actor_name,
                act_text,
                target_text,
                harm_text,
                firsthand_status,
                source_confidence,
                metadata,
                timestamp
            FROM claim_testimony
            WHERE {' AND '.join(where_clauses)}
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
    except Exception as exc:
        self.mediator.log('claim_testimony_query_error', error=str(exc), claim_type=claim_type)
        return self._with_intake_summary_handoff({
            'available': False,
            'user_id': user_id,
            'claim_type': claim_type,
            'limit': normalized_limit,
            'claims': {},
            'summary': {},
            'error': str(exc),
        })

    claim_entries: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        entry_metadata = json.loads(row[13]) if row[13] else {}
        resolved = self._resolve_testimony_claim_element(
            record_id=row[0],
            row_user_id=user_id,
            claim_type=row[2],
            claim_element_id=row[3],
            claim_element_text=row[4],
            raw_narrative=row[5],
            entry_metadata=entry_metadata,
            conn=conn,
            persist_updates=True,
        )

        entry = {
            'record_id': row[0],
            'testimony_id': row[1],
            'claim_type': row[2],
            'claim_element_id': resolved['claim_element_id'],
            'claim_element_text': resolved['claim_element_text'],
            'raw_narrative': row[5] or '',
            'event_date': row[6] or '',
            'actor': row[7] or '',
            'act': row[8] or '',
            'target': row[9] or '',
            'harm': row[10] or '',
            'firsthand_status': row[11] or '',
            'source_confidence': row[12],
            'metadata': entry_metadata,
            'timestamp': row[14].isoformat() if hasattr(row[14], 'isoformat') else row[14],
        }
        current_claim = str(row[2] or '')
        claim_entries.setdefault(current_claim, []).append(entry)

    conn.close()

    return self._with_intake_summary_handoff({
        'available': True,
        'user_id': user_id,
        'claim_type': claim_type,
        'limit': normalized_limit,
        'claims': claim_entries,
        'summary': {
            current_claim: self._summarize_testimony_records(entries)
            for current_claim, entries in claim_entries.items()
        },
    })
def _build_testimony_support_link(self, record: Dict[str, Any]) -> Dict[str, Any]:
    quality_summary = self._testimony_quality_summary(record.get('source_confidence'))
    testimony_id = str(record.get('testimony_id') or '')
    testimony_record_id = record.get('record_id')
    testimony_fact_text = self._build_testimony_fact_text(record)
    parse_lineage = {
        'record_scope': 'claim_testimony',
        'source_ref': testimony_id,
        'source': 'claim_testimony',
        'input_format': 'structured_testimony',
        'quality_tier': quality_summary['quality_tier'],
        'quality_score': quality_summary['quality_score'],
        'transform_lineage': {
            'content_origin': 'operator_testimony_intake',
            'artifact_family': 'testimony_statement',
            'corpus_family': 'claim_testimony',
        },
    }
    if str(record.get('event_date') or '').strip():
        parse_lineage['observed_at'] = str(record.get('event_date') or '').strip()

    record_summary = {
        'id': testimony_record_id,
        'testimony_id': testimony_id,
        'event_date': str(record.get('event_date') or ''),
        'actor': str(record.get('actor') or ''),
        'act': str(record.get('act') or ''),
        'target': str(record.get('target') or ''),
        'harm': str(record.get('harm') or ''),
        'firsthand_status': str(record.get('firsthand_status') or 'unknown'),
        'timestamp': str(record.get('timestamp') or ''),
        'parse_summary': {
            'source': 'claim_testimony',
            'input_format': 'structured_testimony',
            'quality_tier': quality_summary['quality_tier'],
            'quality_score': quality_summary['quality_score'],
            'artifact_family': 'testimony_statement',
            'corpus_family': 'claim_testimony',
            'content_origin': 'operator_testimony_intake',
            'observed_at': str(record.get('event_date') or ''),
        },
    }
    graph_summary = self._normalize_graph_summary(default_status='not_available')
    graph_trace = self._build_graph_trace(
        source_table='claim_testimony',
        support_ref=testimony_id,
        record_id=testimony_record_id,
        graph_summary=graph_summary,
    )
    fact = {
        'fact_id': f'{testimony_id}:fact',
        'text': testimony_fact_text,
        'confidence': quality_summary['support_strength'],
        'source_record_id': testimony_record_id,
        'source_ref': testimony_id,
        'source_family': 'claim_testimony',
        'record_scope': 'claim_testimony',
        'artifact_family': 'testimony_statement',
        'corpus_family': 'claim_testimony',
        'content_origin': 'operator_testimony_intake',
        'parse_source': 'claim_testimony',
        'input_format': 'structured_testimony',
        'quality_tier': quality_summary['quality_tier'],
        'quality_score': quality_summary['quality_score'],
        'metadata': {
            'parse_lineage': parse_lineage,
        },
    }
    return {
        'claim_type': str(record.get('claim_type') or ''),
        'claim_element_id': str(record.get('claim_element_id') or ''),
        'claim_element_text': str(record.get('claim_element_text') or ''),
        'support_kind': 'testimony',
        'support_ref': testimony_id,
        'support_label': self._build_testimony_support_label(record),
        'source_table': 'claim_testimony',
        'support_strength': quality_summary['support_strength'],
        'metadata': dict(record.get('metadata') or {}),
        'timestamp': record.get('timestamp'),
        'testimony_record_id': testimony_record_id,
        'fact_count': 1,
        'facts': [fact],
        'record_summary': record_summary,
        'graph_summary': graph_summary,
        'graph_trace': graph_trace,
    }
def _resolve_testimony_claim_element(
    self,
    *,
    record_id: Optional[int],
    row_user_id: Optional[str],
    claim_type: Optional[str],
    claim_element_id: Optional[str],
    claim_element_text: Optional[str],
    raw_narrative: Optional[str],
    entry_metadata: Optional[Dict[str, Any]],
    conn=None,
    persist_updates: bool = False,
) -> Dict[str, Any]:
    resolved_claim_element_id = claim_element_id
    resolved_claim_element_text = claim_element_text
    backfilled = False

    if not str(resolved_claim_element_id or '').strip() and str(claim_type or '').strip():
        resolved_element = self.resolve_claim_element(
            str(row_user_id or ''),
            str(claim_type or ''),
            claim_element_text=str(claim_element_text or '').strip() or None,
            support_label=str(raw_narrative or '').strip() or None,
            metadata=entry_metadata,
        )
        candidate_element_id = str(resolved_element.get('claim_element_id') or '').strip()
        if candidate_element_id:
            resolved_claim_element_id = candidate_element_id
            resolved_claim_element_text = (
                resolved_element.get('claim_element_text')
                or resolved_claim_element_text
            )
            backfilled = True
            if persist_updates and conn is not None and record_id is not None:
                conn.execute(
                    """
                    UPDATE claim_testimony
                    SET claim_element_id = ?, claim_element_text = ?
                    WHERE id = ?
                    """,
                    [
                        resolved_claim_element_id,
                        resolved_claim_element_text or None,
                        record_id,
                    ],
                )

    return {
        'claim_element_id': resolved_claim_element_id,
        'claim_element_text': resolved_claim_element_text,
        'backfilled': backfilled,
    }
def _summarize_testimony_records(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
    normalized_records = [record for record in (records or []) if isinstance(record, dict)]
    firsthand_status_counts: Dict[str, int] = {}
    confidence_bucket_counts: Dict[str, int] = {}
    linked_element_ids = set()
    actor_names = set()
    dated_records = 0

    for record in normalized_records:
        firsthand_status = str(record.get('firsthand_status') or 'unknown')
        firsthand_status_counts[firsthand_status] = firsthand_status_counts.get(firsthand_status, 0) + 1

        confidence_value = record.get('source_confidence')
        if confidence_value is None:
            bucket = 'unknown'
        else:
            try:
                numeric_confidence = float(confidence_value)
            except (TypeError, ValueError):
                bucket = 'unknown'
            else:
                if numeric_confidence >= 0.75:
                    bucket = 'high'
                elif numeric_confidence >= 0.4:
                    bucket = 'medium'
                else:
                    bucket = 'low'
        confidence_bucket_counts[bucket] = confidence_bucket_counts.get(bucket, 0) + 1

        claim_element_id = str(record.get('claim_element_id') or '')
        if claim_element_id:
            linked_element_ids.add(claim_element_id)
        actor_name = str(record.get('actor') or '').strip()
        if actor_name:
            actor_names.add(actor_name)
        if str(record.get('event_date') or '').strip():
            dated_records += 1

    latest_timestamp = ''
    if normalized_records:
        latest_timestamp = str(normalized_records[0].get('timestamp') or '')

    return {
        'record_count': len(normalized_records),
        'linked_element_count': len(linked_element_ids),
        'firsthand_status_counts': firsthand_status_counts,
        'confidence_bucket_counts': confidence_bucket_counts,
        'actor_count': len(actor_names),
        'dated_record_count': dated_records,
        'latest_timestamp': latest_timestamp,
    }
def _build_testimony_fact_text(self, record: Dict[str, Any]) -> str:
    raw_narrative = str(record.get('raw_narrative') or '').strip()
    if raw_narrative:
        return raw_narrative

    actor = str(record.get('actor') or '').strip()
    act = str(record.get('act') or '').strip()
    target = str(record.get('target') or '').strip()
    harm = str(record.get('harm') or '').strip()
    event_date = str(record.get('event_date') or '').strip()
    claim_element_text = str(record.get('claim_element_text') or '').strip()

    clauses: List[str] = []
    actor_and_act = ' '.join(part for part in [actor, act] if part).strip()
    if actor_and_act:
        clauses.append(actor_and_act)
    if target:
        clauses.append(f'targeting {target}')
    if harm:
        clauses.append(f'causing {harm}')
    if event_date:
        clauses.append(f'on {event_date}')

    text = '; '.join(clauses).strip()
    if not text:
        text = claim_element_text or 'Testimony provided.'
    if text and not text.endswith('.'):
        text = f'{text}.'
    return text
