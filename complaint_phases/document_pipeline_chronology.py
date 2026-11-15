"""Chronology and fact-entry assembly delegated from FormalComplaintDocumentBuilder."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from complaint_phases.document_pipeline import (
    ComplaintPhase,
    _chronology_fact_label,
    _coerce_list,
    _dedupe_text_values,
    _extract_text_candidates,
    _format_timeline_date,
    _join_chronology_segments,
    _normalize_identifier_list,
    _safe_call,
    _unique_preserving_order,
)

def _build_chronology_blocker_summary(
    self,
    *,
    intake_case_summary: Any,
    claim_support_temporal_handoff: Any,
) -> Dict[str, Any]:
    summary = intake_case_summary if isinstance(intake_case_summary, dict) else {}
    packet_summary = summary.get("claim_support_packet_summary")
    packet_summary = packet_summary if isinstance(packet_summary, dict) else {}
    alignment_task_summary = summary.get("alignment_task_summary")
    alignment_task_summary = alignment_task_summary if isinstance(alignment_task_summary, dict) else {}
    handoff = dict(claim_support_temporal_handoff or {}) if isinstance(claim_support_temporal_handoff, dict) else {}

    unresolved_issue_ids = _dedupe_text_values(
        packet_summary.get("claim_support_unresolved_temporal_issue_ids")
        or handoff.get("unresolved_temporal_issue_ids")
        or []
    )
    unresolved_issue_count = int(
        packet_summary.get("claim_support_unresolved_temporal_issue_count")
        or handoff.get("unresolved_temporal_issue_count")
        or len(unresolved_issue_ids)
        or 0
    )
    temporal_gap_task_count = int(
        packet_summary.get("temporal_gap_task_count")
        or alignment_task_summary.get("temporal_gap_task_count")
        or 0
    )
    proof_readiness_score = float(packet_summary.get("proof_readiness_score", 0.0) or 0.0)

    # T5: Gate drafting readiness on legal temporal rule profile gaps, not
    # only on aggregate proof-readiness score and unresolved issue counts. If any
    # claim element has a failed or partial temporal rule-profile evaluation the
    # chronology is legally insufficient and the summary must surface that clearly.
    claim_reasoning_review = summary.get("claim_reasoning_review")
    if not isinstance(claim_reasoning_review, dict):
        claim_reasoning_review = {}
    temporal_rule_profile_failed_element_count = 0
    temporal_rule_profile_partial_element_count = 0
    failed_rule_frame_ids: List[str] = []
    for _claim_key, claim_review in claim_reasoning_review.items():
        if not isinstance(claim_review, dict):
            continue
        temporal_rule_profile_failed_element_count += int(
            claim_review.get("temporal_rule_profile_failed_element_count") or 0
        )
        temporal_rule_profile_partial_element_count += int(
            claim_review.get("temporal_rule_profile_partial_element_count") or 0
        )
        # Collect rule-frame IDs from failed proof bundles for the summary text.
        proof_bundles = claim_review.get("proof_bundles")
        if isinstance(proof_bundles, dict):
            for bundle in proof_bundles.values():
                if not isinstance(bundle, dict):
                    continue
                bundle_status = str(bundle.get("status") or "").strip()
                if bundle_status in {"failed", "partial"}:
                    rule_frame_id = str(bundle.get("rule_frame_id") or "").strip()
                    if rule_frame_id and rule_frame_id not in failed_rule_frame_ids:
                        failed_rule_frame_ids.append(rule_frame_id)

    chronology_blocked = bool(
        unresolved_issue_count > 0
        or temporal_gap_task_count > 0
        or temporal_rule_profile_failed_element_count > 0
        or temporal_rule_profile_partial_element_count > 0
    )
    if not chronology_blocked and proof_readiness_score <= 0.0 and not unresolved_issue_ids:
        return {}

    summary_parts: List[str] = []
    if temporal_gap_task_count > 0:
        task_label = "task" if temporal_gap_task_count == 1 else "tasks"
        summary_parts.append(f"{temporal_gap_task_count} pending chronology gap {task_label}")
    if unresolved_issue_count > 0:
        issue_label = "issue" if unresolved_issue_count == 1 else "issues"
        summary_parts.append(f"{unresolved_issue_count} unresolved temporal {issue_label}")
    if temporal_rule_profile_failed_element_count > 0:
        element_label = "element" if temporal_rule_profile_failed_element_count == 1 else "elements"
        summary_parts.append(
            f"{temporal_rule_profile_failed_element_count} {element_label} with failed temporal rule profile"
        )
    if temporal_rule_profile_partial_element_count > 0 and not temporal_rule_profile_failed_element_count:
        element_label = "element" if temporal_rule_profile_partial_element_count == 1 else "elements"
        summary_parts.append(
            f"{temporal_rule_profile_partial_element_count} {element_label} with partial temporal rule profile"
        )
    summary_text = (
        f"Chronology blockers remain: {'; '.join(summary_parts)}."
        if summary_parts
        else "No chronology blockers currently reduce proof readiness."
    )

    result: Dict[str, Any] = {
        "chronology_blocked": chronology_blocked,
        "proof_readiness_score": round(proof_readiness_score, 3),
        "temporal_gap_task_count": temporal_gap_task_count,
        "unresolved_temporal_issue_count": unresolved_issue_count,
        "unresolved_temporal_issue_ids": unresolved_issue_ids,
        "temporal_rule_profile_failed_element_count": temporal_rule_profile_failed_element_count,
        "temporal_rule_profile_partial_element_count": temporal_rule_profile_partial_element_count,
        "summary": summary_text,
    }
    if failed_rule_frame_ids:
        result["failed_rule_frame_ids"] = failed_rule_frame_ids
    return result


def _build_document_provenance_summary(self, draft: Dict[str, Any]) -> Dict[str, Any]:
    factual_paragraphs = [
        paragraph
        for paragraph in _coerce_list(draft.get("factual_allegation_paragraphs"))
        if isinstance(paragraph, dict)
    ]
    claims = [
        claim
        for claim in _coerce_list(draft.get("claims_for_relief"))
        if isinstance(claim, dict)
    ]
    claim_rows = []
    total_claim_support_rows = 0
    total_claim_support_fact_backed_rows = 0
    total_claim_support_exhibit_backed_rows = 0
    focused_entry_count = 0
    focus_source_counts: Dict[str, int] = {}
    all_fact_ids: List[str] = []
    all_artifact_ids: List[str] = []
    for claim in claims:
        provenance_rows = [
            row
            for row in _coerce_list(claim.get("supporting_fact_provenance"))
            if isinstance(row, dict)
        ]
        fact_backed_count = sum(1 for row in provenance_rows if _normalize_identifier_list(row.get("fact_ids") or []))
        artifact_backed_count = sum(1 for row in provenance_rows if _normalize_identifier_list(row.get("source_artifact_ids") or []))
        exhibit_backed_count = sum(1 for row in provenance_rows if str(row.get("exhibit_label") or "").strip())
        total_claim_support_rows += len(provenance_rows)
        total_claim_support_fact_backed_rows += fact_backed_count
        total_claim_support_exhibit_backed_rows += exhibit_backed_count
        for row in provenance_rows:
            all_fact_ids.extend(_normalize_identifier_list(row.get("fact_ids") or []))
            all_artifact_ids.extend(_normalize_identifier_list(row.get("source_artifact_ids") or []))
            focus_metadata = row.get("document_focus") if isinstance(row.get("document_focus"), dict) else {}
            focus_source = str(focus_metadata.get("focus_source") or "").strip()
            if focus_source:
                focused_entry_count += 1
                focus_source_counts[focus_source] = focus_source_counts.get(focus_source, 0) + 1
        claim_rows.append(
            {
                "claim_type": str(claim.get("claim_type") or "").strip(),
                "supporting_fact_count": len(provenance_rows),
                "fact_backed_supporting_fact_count": fact_backed_count,
                "artifact_backed_supporting_fact_count": artifact_backed_count,
                "exhibit_backed_supporting_fact_count": exhibit_backed_count,
                "fact_ids": _normalize_identifier_list(
                    [
                        fact_id
                        for row in provenance_rows
                        for fact_id in _coerce_list(row.get("fact_ids"))
                    ]
                ),
                "source_artifact_ids": _normalize_identifier_list(
                    [
                        artifact_id
                        for row in provenance_rows
                        for artifact_id in _coerce_list(row.get("source_artifact_ids"))
                    ]
                ),
            }
        )

    factual_fact_backed_count = sum(
        1 for paragraph in factual_paragraphs if _normalize_identifier_list(paragraph.get("fact_ids") or [])
    )
    factual_exhibit_backed_count = sum(
        1 for paragraph in factual_paragraphs if str(paragraph.get("exhibit_label") or "").strip()
    )
    for paragraph in factual_paragraphs:
        all_fact_ids.extend(_normalize_identifier_list(paragraph.get("fact_ids") or []))
        all_artifact_ids.extend(_normalize_identifier_list(paragraph.get("source_artifact_ids") or []))
        focus_metadata = paragraph.get("document_focus") if isinstance(paragraph.get("document_focus"), dict) else {}
        focus_source = str(focus_metadata.get("focus_source") or "").strip()
        if focus_source:
            focused_entry_count += 1
            focus_source_counts[focus_source] = focus_source_counts.get(focus_source, 0) + 1

    summary_entries = [
        entry for entry in _coerce_list(draft.get("summary_of_fact_entries")) if isinstance(entry, dict)
    ]
    summary_fact_backed_count = sum(1 for entry in summary_entries if _normalize_identifier_list(entry.get("fact_ids") or []))
    summary_exhibit_backed_count = sum(1 for entry in summary_entries if str(entry.get("exhibit_label") or "").strip())
    for entry in summary_entries:
        all_fact_ids.extend(_normalize_identifier_list(entry.get("fact_ids") or []))
        all_artifact_ids.extend(_normalize_identifier_list(entry.get("source_artifact_ids") or []))
        focus_metadata = entry.get("document_focus") if isinstance(entry.get("document_focus"), dict) else {}
        focus_source = str(focus_metadata.get("focus_source") or "").strip()
        if focus_source:
            focused_entry_count += 1
            focus_source_counts[focus_source] = focus_source_counts.get(focus_source, 0) + 1

    summary_fact_ratio = (float(summary_fact_backed_count) / float(len(summary_entries))) if summary_entries else 0.0
    allegation_ratio = (float(factual_fact_backed_count) / float(len(factual_paragraphs))) if factual_paragraphs else 0.0
    claim_ratio = (float(total_claim_support_fact_backed_rows) / float(total_claim_support_rows)) if total_claim_support_rows else 0.0
    fact_backed_ratio = (summary_fact_ratio + allegation_ratio + claim_ratio) / 3.0
    return {
        "summary_fact_count": len(summary_entries),
        "summary_fact_backed_count": summary_fact_backed_count,
        "summary_fact_exhibit_backed_count": summary_exhibit_backed_count,
        "factual_allegation_paragraph_count": len(factual_paragraphs),
        "factual_allegation_fact_backed_count": factual_fact_backed_count,
        "factual_allegation_exhibit_backed_count": factual_exhibit_backed_count,
        "claim_count": len(claims),
        "claim_supporting_fact_count": total_claim_support_rows,
        "claim_supporting_fact_backed_count": total_claim_support_fact_backed_rows,
        "claim_supporting_fact_exhibit_backed_count": total_claim_support_exhibit_backed_rows,
        "fact_id_count": len(_normalize_identifier_list(all_fact_ids)),
        "source_artifact_id_count": len(_normalize_identifier_list(all_artifact_ids)),
        "fact_backed_ratio": round(fact_backed_ratio, 4),
        "low_grounding_flag": bool(fact_backed_ratio < 0.6),
        "focused_entry_count": focused_entry_count,
        "focus_source_counts": focus_source_counts,
        "claims": claim_rows,
    }


def _build_summary_fact_entries(
    self,
    *,
    user_id: str = "",
    generated_complaint: Dict[str, Any],
    classification: Dict[str, Any],
    state: Any,
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    phase_manager = getattr(self.mediator, "phase_manager", None)
    intake_case_file = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file") if phase_manager else None
    canonical_facts = (
        list(intake_case_file.get("canonical_facts") or [])
        if isinstance(intake_case_file, dict)
        else []
    )
    for fact in canonical_facts:
        if not isinstance(fact, dict):
            continue
        text = re.sub(r"\s+", " ", str(fact.get("text") or "").strip())
        if len(text) < 12:
            continue
        entries.append(
            {
                "text": text,
                "fact_ids": _normalize_identifier_list(
                    [fact.get("fact_id")] + list(fact.get("related_fact_ids") or [])
                ),
                "source_artifact_ids": _normalize_identifier_list(
                    list(fact.get("source_artifact_ids") or [])
                    + ([fact.get("source_artifact_id")] if fact.get("source_artifact_id") else [])
                ),
                "claim_types": _normalize_identifier_list(fact.get("claim_types") or []),
                "claim_element_ids": _normalize_identifier_list(
                    fact.get("element_tags")
                    or fact.get("claim_element_ids")
                    or ([] if not fact.get("predicate_family") else [fact.get("predicate_family")])
                ),
                "source_kind": str(fact.get("source_kind") or "canonical_fact").strip() or "canonical_fact",
                "source_ref": str(fact.get("source_ref") or fact.get("fact_id") or "").strip() or None,
            }
        )

    entries.extend(self._collect_uploaded_evidence_fact_entries(user_id=user_id, limit=8))

    for allegation in _coerce_list(generated_complaint.get("factual_allegations")):
        for text in _extract_text_candidates(allegation):
            entries.append({"text": text, "source_kind": "generated_complaint"})
    for text in _extract_text_candidates(classification.get("key_facts")):
        entries.append({"text": text, "source_kind": "classification"})
    for inquiry in _coerce_list(getattr(state, "inquiries", []) if state is not None else []):
        if not isinstance(inquiry, dict):
            continue
        question = str(inquiry.get("question") or "").strip()
        answer = str(inquiry.get("answer") or "").strip()
        if answer:
            entries.append(
                {
                    "text": f"{question}: {answer}" if question else answer,
                    "source_kind": "inquiry",
                    "source_ref": question or None,
                }
            )

    complaint_text = getattr(state, "complaint", None) if state is not None else None
    original_text = getattr(state, "original_complaint", None) if state is not None else None
    if isinstance(complaint_text, dict):
        explicit_facts = _extract_text_candidates(complaint_text.get("facts"))
        if explicit_facts:
            for text in explicit_facts:
                entries.append({"text": text, "source_kind": "complaint"})
        else:
            for text in _extract_text_candidates(complaint_text.get("summary") or complaint_text):
                entries.append({"text": text, "source_kind": "complaint"})
    elif complaint_text:
        for text in _extract_text_candidates(complaint_text):
            entries.append({"text": text, "source_kind": "complaint"})
    elif original_text:
        for text in _extract_text_candidates(original_text):
            entries.append({"text": text, "source_kind": "original_complaint"})

    normalized: List[Dict[str, Any]] = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        text = re.sub(r"\s+", " ", str(entry.get("text") or "").strip())
        if len(text) < 12:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "text": text,
                "fact_ids": _normalize_identifier_list(entry.get("fact_ids") or []),
                "source_artifact_ids": _normalize_identifier_list(entry.get("source_artifact_ids") or []),
                "claim_types": _normalize_identifier_list(entry.get("claim_types") or []),
                "claim_element_ids": _normalize_identifier_list(entry.get("claim_element_ids") or []),
                "source_kind": str(entry.get("source_kind") or "").strip() or None,
                "source_ref": str(entry.get("source_ref") or "").strip() or None,
            }
        )
        if len(normalized) >= 12:
            break
    return normalized or [{"text": "Additional factual development is required before filing.", "source_kind": "fallback"}]


def _collect_uploaded_evidence_fact_entries(
    self,
    *,
    user_id: str,
    claim_type: Optional[str] = None,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    evidence_records = _safe_call(self.mediator, "get_user_evidence", user_id=user_id) or []
    normalized_claim_type = str(claim_type or "").strip().lower()
    entries: List[Dict[str, Any]] = []

    for record in _coerce_list(evidence_records):
        if not isinstance(record, dict):
            continue
        record_claim_type = str(record.get("claim_type") or "").strip().lower()
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        record_claim_types = _normalize_identifier_list(
            ([record.get("claim_type")] if record.get("claim_type") else [])
            + list(metadata.get("claim_types") or [])
        )
        if normalized_claim_type and record_claim_types:
            normalized_record_claim_types = {str(value or "").strip().lower() for value in record_claim_types if str(value or "").strip()}
            if normalized_claim_type not in normalized_record_claim_types:
                continue
        evidence_id = record.get("id")
        source_artifact_ids = _normalize_identifier_list(
            [record.get("cid"), evidence_id]
            + list(record.get("source_artifact_ids") or [])
            + ([record.get("source_artifact_id")] if record.get("source_artifact_id") else [])
        )
        claim_types = record_claim_types
        fact_rows = _safe_call(self.mediator, "get_evidence_facts", evidence_id=evidence_id) or []

        for row in _coerce_list(fact_rows):
            if not isinstance(row, dict):
                continue
            for text in _extract_text_candidates(row):
                for fragment in self._extract_uploaded_evidence_text_candidates(text, limit=3):
                    cleaned = re.sub(r"\s+", " ", str(fragment or "").strip())
                    if len(cleaned) < 12:
                        continue
                    entries.append(
                        {
                            "text": cleaned,
                            "fact_ids": _normalize_identifier_list([row.get("fact_id")] + list(row.get("fact_ids") or [])),
                            "source_artifact_ids": source_artifact_ids,
                            "claim_types": claim_types,
                            "claim_element_ids": _normalize_identifier_list(
                                [row.get("claim_element_id"), row.get("element_id")] + list(row.get("element_tags") or [])
                            ),
                            "support_trace_ids": _normalize_identifier_list(
                                [
                                    trace.get("source_ref")
                                    for trace in _coerce_list(row.get("support_traces"))
                                    if isinstance(trace, dict) and trace.get("source_ref")
                                ]
                            ),
                            "source_kind": "uploaded_evidence_fact",
                            "source_ref": str(row.get("source_ref") or record.get("cid") or evidence_id or "").strip() or None,
                        }
                    )

        preview_texts = _extract_text_candidates(
            {
                "parsed_text_preview": record.get("parsed_text_preview"),
                "description": record.get("description"),
                "summary": metadata.get("summary") if isinstance(metadata, dict) else "",
            }
        )
        for text in preview_texts:
            for fragment in self._extract_uploaded_evidence_text_candidates(text, limit=2):
                cleaned = re.sub(r"\s+", " ", str(fragment or "").strip())
                if len(cleaned) < 12:
                    continue
                entries.append(
                    {
                        "text": cleaned,
                        "fact_ids": [],
                        "source_artifact_ids": source_artifact_ids,
                        "claim_types": claim_types,
                        "claim_element_ids": [],
                        "support_trace_ids": [],
                        "source_kind": "uploaded_evidence_preview",
                        "source_ref": str(record.get("cid") or evidence_id or "").strip() or None,
                    }
                )

    normalized: List[Dict[str, Any]] = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        text = re.sub(r"\s+", " ", str(entry.get("text") or "").strip())
        if len(text) < 12 or self._is_generic_claim_support_text(text):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "text": text,
                "fact_ids": _normalize_identifier_list(entry.get("fact_ids") or []),
                "source_artifact_ids": _normalize_identifier_list(entry.get("source_artifact_ids") or []),
                "claim_types": _normalize_identifier_list(entry.get("claim_types") or []),
                "claim_element_ids": _normalize_identifier_list(entry.get("claim_element_ids") or []),
                "support_trace_ids": _normalize_identifier_list(entry.get("support_trace_ids") or []),
                "source_kind": str(entry.get("source_kind") or "").strip() or "uploaded_evidence_fact",
                "source_ref": str(entry.get("source_ref") or "").strip() or None,
            }
        )
        if len(normalized) >= limit:
            break
    return normalized


def _merge_claim_support_policy_entries(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered_entries = [dict(entry) for entry in entries if isinstance(entry, dict)]
    if not ordered_entries:
        return []

    notice_entry = next(
        (
            entry
            for entry in ordered_entries
            if "notice to the applicant requires" in str(entry.get("text") or "").lower()
        ),
        None,
    )
    review_entry = next(
        (
            entry
            for entry in ordered_entries
            if "scheduling an informal review requires" in str(entry.get("text") or "").lower()
        ),
        None,
    )
    authority_entry = next(
        (
            entry
            for entry in ordered_entries
            if "requires written notice and an opportunity for informal review" in str(entry.get("text") or "").lower()
        ),
        None,
    )
    adverse_action_entry = next(
        (
            entry
            for entry in ordered_entries
            if "denial notice" in str(entry.get("text") or "").lower()
            or "loss of assistance" in str(entry.get("text") or "").lower()
            or "challenged adverse housing action" in str(entry.get("text") or "").lower()
        ),
        None,
    )
    if not (notice_entry and review_entry and authority_entry):
        return self._merge_housing_policy_entries(ordered_entries)

    merged_source_entries = [
        item for item in (adverse_action_entry, notice_entry, review_entry, authority_entry) if isinstance(item, dict)
    ]
    merged_entry = {
        "text": (
            "HACC policy required prompt written notice of a decision denying assistance and a written "
            "opportunity to request informal review before a final adverse housing decision was enforced "
            f"({self._merge_support_exhibit_labels(notice_entry, review_entry, authority_entry)})."
        ),
        "fact_ids": _normalize_identifier_list(
            [
                fact_id
                for source_entry in merged_source_entries
                for fact_id in list(source_entry.get("fact_ids") or [])
            ]
        ),
        "source_artifact_ids": _normalize_identifier_list(
            [
                artifact_id
                for source_entry in merged_source_entries
                for artifact_id in list(source_entry.get("source_artifact_ids") or [])
            ]
        ),
        "claim_types": _normalize_identifier_list(
            [
                claim_type
                for source_entry in merged_source_entries
                for claim_type in list(source_entry.get("claim_types") or [])
            ]
        ),
        "claim_element_ids": _normalize_identifier_list(
            [
                element_id
                for source_entry in merged_source_entries
                for element_id in list(source_entry.get("claim_element_ids") or [])
            ]
        ),
        "support_trace_ids": _normalize_identifier_list(
            [
                trace_id
                for source_entry in merged_source_entries
                for trace_id in list(source_entry.get("support_trace_ids") or [])
            ]
        ),
        "source_kind": "claim_support_merged",
        "exhibit_label": self._merge_support_exhibit_labels(notice_entry, review_entry, authority_entry),
    }

    merged_entries: List[Dict[str, Any]] = []
    merged_inserted = False
    for entry in ordered_entries:
        text = str(entry.get("text") or "").lower()
        if (
            "notice to the applicant requires" in text
            or "scheduling an informal review requires" in text
            or "requires written notice and an opportunity for informal review" in text
        ):
            if not merged_inserted:
                merged_entries.append(merged_entry)
                merged_inserted = True
            continue
        merged_entries.append(entry)
    return merged_entries


def _collect_claim_fact_entries(
    self,
    claim_type: str,
    user_id: str,
    support_claim: Dict[str, Any],
) -> List[Dict[str, Any]]:
    facts: List[str] = []
    entries: List[Dict[str, Any]] = []
    fact_rows = _safe_call(
        self.mediator,
        "get_claim_support_facts",
        claim_type=claim_type,
        user_id=user_id,
    ) or []
    for row in _coerce_list(fact_rows):
        row_texts = _extract_text_candidates(row)
        facts.extend(row_texts)
        if isinstance(row, dict):
            fact_ids = _normalize_identifier_list([row.get("fact_id")] + list(row.get("fact_ids") or []))
            source_artifact_ids = _normalize_identifier_list(
                list(row.get("source_artifact_ids") or [])
                + ([row.get("source_artifact_id")] if row.get("source_artifact_id") else [])
            )
            claim_element_ids = _normalize_identifier_list(
                [row.get("claim_element_id"), row.get("element_id")] + list(row.get("element_tags") or [])
            )
            support_trace_ids = _normalize_identifier_list(
                list(row.get("support_trace_ids") or [])
                + [
                    trace.get("source_ref")
                    for trace in _coerce_list(row.get("support_traces"))
                    if isinstance(trace, dict) and trace.get("source_ref")
                ]
            )
            for text in row_texts:
                entries.append(
                    {
                        "text": text,
                        "fact_ids": fact_ids,
                        "source_artifact_ids": source_artifact_ids,
                        "claim_types": [claim_type] if claim_type else [],
                        "claim_element_ids": claim_element_ids,
                        "support_trace_ids": support_trace_ids,
                        "source_kind": "claim_support_fact",
                        "source_ref": str(row.get("source_ref") or row.get("fact_id") or "").strip() or None,
                        "source_family": str(row.get("source_family") or "").strip(),
                        "source_record_id": row.get("source_record_id"),
                        "record_scope": str(row.get("record_scope") or "").strip(),
                        "artifact_family": str(row.get("artifact_family") or "").strip(),
                        "corpus_family": str(row.get("corpus_family") or "").strip(),
                        "content_origin": str(row.get("content_origin") or "").strip(),
                        "parse_source": str(row.get("parse_source") or "").strip(),
                        "input_format": str(row.get("input_format") or "").strip(),
                        "quality_tier": str(row.get("quality_tier") or "").strip(),
                        "quality_score": row.get("quality_score"),
                        "chunk_id": str(row.get("chunk_id") or "").strip(),
                        "chunk_index": row.get("chunk_index"),
                        "source_passage": dict(row.get("source_passage") or {}) if isinstance(row.get("source_passage"), dict) else {},
                    }
                )

    for element in _coerce_list(support_claim.get("elements") if isinstance(support_claim, dict) else []):
        if not isinstance(element, dict):
            continue
        element_text = str(element.get("element_text") or element.get("claim_element") or "").strip()
        if element_text:
            facts.append(f"Element supported: {element_text}")
        for link in _coerce_list(element.get("links")):
            if isinstance(link, dict):
                link_texts = _extract_text_candidates(link)
                facts.extend(link_texts)
                for text in link_texts:
                    entries.append(
                        {
                            "text": text,
                            "fact_ids": _normalize_identifier_list(
                                [link.get("fact_id")] + list(link.get("fact_ids") or []) + list(element.get("fact_ids") or [])
                            ),
                            "source_artifact_ids": _normalize_identifier_list(
                                list(link.get("source_artifact_ids") or [])
                                + ([link.get("source_artifact_id")] if link.get("source_artifact_id") else [])
                                + list(element.get("supporting_artifact_ids") or [])
                            ),
                            "claim_types": [claim_type] if claim_type else [],
                            "claim_element_ids": _normalize_identifier_list(
                                [element.get("element_id"), link.get("claim_element_id"), link.get("element_id")]
                            ),
                            "support_trace_ids": _normalize_identifier_list(
                                [
                                    trace.get("source_ref")
                                    for trace in _coerce_list(element.get("support_traces"))
                                    if isinstance(trace, dict) and trace.get("source_ref")
                                ]
                            ),
                            "source_kind": "claim_support_link",
                            "source_ref": str(link.get("source_ref") or link.get("fact_id") or "").strip() or None,
                        }
                    )

    evidence_entries = self._collect_uploaded_evidence_fact_entries(
        user_id=user_id,
        claim_type=claim_type,
        limit=6,
    )
    for entry in evidence_entries:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").strip()
        if text:
            facts.append(text)
        entries.append(dict(entry))

    normalized = []
    for item in _unique_preserving_order(facts):
        text = re.sub(r"\s+", " ", item).strip()
        if len(text) < 10 or self._is_generic_claim_support_text(text):
            continue
        normalized.append(text)
        if len(normalized) >= 8:
            break
    chronology_support = self._build_claim_chronology_support(claim_type=claim_type, claim_name=claim_type.title())
    combined = _unique_preserving_order(chronology_support + normalized)
    if not combined:
        combined = [f"The intake record describes facts supporting the {claim_type} claim."]
    entry_index = {
        str(entry.get("text") or "").strip().lower(): entry
        for entry in entries
        if isinstance(entry, dict) and str(entry.get("text") or "").strip()
    }
    result: List[Dict[str, Any]] = []
    for text in combined:
        key = str(text or "").strip().lower()
        entry = dict(entry_index.get(key) or {})
        entry["text"] = text
        entry["fact_ids"] = _normalize_identifier_list(entry.get("fact_ids") or [])
        entry["source_artifact_ids"] = _normalize_identifier_list(entry.get("source_artifact_ids") or [])
        entry["claim_types"] = _normalize_identifier_list(entry.get("claim_types") or [claim_type])
        entry["claim_element_ids"] = _normalize_identifier_list(entry.get("claim_element_ids") or [])
        entry["support_trace_ids"] = _normalize_identifier_list(entry.get("support_trace_ids") or [])
        if not entry.get("source_kind"):
            entry["source_kind"] = "claim_chronology_support" if text in chronology_support else "claim_support_fact"
        result.append(entry)
    return self._enrich_claim_support_entries(result, entries)


def _build_claim_chronology_support(self, *, claim_type: str, claim_name: str, limit: int = 2) -> List[str]:
    phase_manager = getattr(self.mediator, "phase_manager", None)
    intake_case_file = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file") if phase_manager else None
    if not isinstance(intake_case_file, dict):
        return []

    facts = [dict(item) for item in list(intake_case_file.get("canonical_facts") or []) if isinstance(item, dict)]
    relations = [dict(item) for item in list(intake_case_file.get("timeline_relations") or []) if isinstance(item, dict)]
    if not facts or not relations:
        return []

    combined = " ".join([str(claim_type or ""), str(claim_name or "")]).strip().lower()
    if any(token in combined for token in ("retaliat", "reprisal", "protected activity")):
        focus_families = {"protected_activity", "adverse_action", "causation"}
    elif any(token in combined for token in ("due process", "grievance", "hearing", "appeal", "review", "notice")):
        focus_families = {"notice_chain", "hearing_process", "response_timeline", "adverse_action"}
    elif any(token in combined for token in ("accommodation", "disabil", "fair housing", "discrimination", "termination", "denial")):
        focus_families = {"adverse_action", "response_timeline", "notice_chain"}
    else:
        focus_families = set()

    fact_by_id = {
        str(fact.get("fact_id") or "").strip(): fact
        for fact in facts
        if str(fact.get("fact_id") or "").strip()
    }
    relation_records = []
    for relation in relations:
        if str(relation.get("relation_type") or "").strip().lower() != "before":
            continue
        source_id = str(relation.get("source_fact_id") or "").strip()
        target_id = str(relation.get("target_fact_id") or "").strip()
        source_fact = fact_by_id.get(source_id)
        target_fact = fact_by_id.get(target_id)
        if not source_fact or not target_fact:
            continue
        source_date = _format_timeline_date((source_fact.get("temporal_context") or {}).get("start_date") or relation.get("source_start_date"))
        target_date = _format_timeline_date((target_fact.get("temporal_context") or {}).get("start_date") or relation.get("target_start_date"))
        if not source_date or not target_date:
            continue
        relation_records.append(
            {
                "key": (source_id, target_id),
                "source_id": source_id,
                "target_id": target_id,
                "source_fact": source_fact,
                "target_fact": target_fact,
                "source_date": source_date,
                "target_date": target_date,
                "source_family": str(source_fact.get("predicate_family") or "").strip().lower(),
                "target_family": str(target_fact.get("predicate_family") or "").strip().lower(),
            }
        )
    if not relation_records:
        return []

    filtered_records = [
        record for record in relation_records
        if not focus_families or ({record['source_family'], record['target_family']} & focus_families)
    ]
    if not filtered_records:
        filtered_records = relation_records

    outgoing: Dict[str, List[Dict[str, Any]]] = {}
    incoming_count: Dict[str, int] = {}
    for record in filtered_records:
        outgoing.setdefault(record["source_id"], []).append(record)
        incoming_count[record["target_id"]] = incoming_count.get(record["target_id"], 0) + 1
        incoming_count.setdefault(record["source_id"], incoming_count.get(record["source_id"], 0))

    lines: List[str] = []
    fallback_lines: List[str] = []
    seen = set()
    used_keys = set()
    for record in filtered_records:
        if len(lines) >= limit:
            break
        if record["key"] in used_keys:
            continue
        if incoming_count.get(record["source_id"], 0) != 0 or len(outgoing.get(record["source_id"], [])) != 1:
            continue
        chain = [record]
        next_id = record["target_id"]
        temp_used = {record["key"]}
        while len(outgoing.get(next_id, [])) == 1 and incoming_count.get(next_id, 0) == 1:
            next_record = outgoing[next_id][0]
            if next_record["key"] in temp_used:
                break
            chain.append(next_record)
            temp_used.add(next_record["key"])
            next_id = next_record["target_id"]
        if len(chain) < 2:
            continue
        segments = [
            f"{_chronology_fact_label(chain[0]['source_fact']).lower()} on {chain[0]['source_date']}"
        ]
        segments.extend(
            f"{_chronology_fact_label(item['target_fact']).lower()} on {item['target_date']}"
            for item in chain
        )
        line = f"The chronology shows {_join_chronology_segments(segments)} in sequence."
        last_target = chain[-1]["target_fact"]
        target_context = last_target.get("temporal_context") if isinstance(last_target.get("temporal_context"), dict) else {}
        if target_context.get("derived_from_relative_anchor"):
            relative_markers = [str(item) for item in list(target_context.get("relative_markers") or []) if str(item)]
            if relative_markers:
                line = line.rstrip(".") + f". The later date is derived from reported timing ({relative_markers[0]})."
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        used_keys.update(temp_used)
        lines.append(line)

    for record in filtered_records:
        if record["key"] in used_keys:
            continue
        source_label = _chronology_fact_label(record["source_fact"])
        target_label = _chronology_fact_label(record["target_fact"]).lower()
        line = f"The chronology shows {source_label.lower()} on {record['source_date']} before {target_label} on {record['target_date']}."
        target_context = record["target_fact"].get("temporal_context") if isinstance(record["target_fact"].get("temporal_context"), dict) else {}
        if target_context.get("derived_from_relative_anchor"):
            relative_markers = [str(item) for item in list(target_context.get("relative_markers") or []) if str(item)]
            if relative_markers:
                line = line.rstrip(".") + f". The later date is derived from reported timing ({relative_markers[0]})."
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        fallback_lines.append(line)
    if lines:
        return lines
    if fallback_lines:
        return fallback_lines[:1]
    return []
