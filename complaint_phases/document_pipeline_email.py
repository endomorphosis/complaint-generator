"""Email-timeline builders delegated from FormalComplaintDocumentBuilder."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Dict, Iterable, List, Optional

from complaint_phases.document_pipeline import (
    _coerce_list,
    _format_timeline_date,
    _join_chronology_segments,
    _normalize_identifier_list,
    _unique_preserving_order,
    normalize_claim_type,
)


def _resolve_email_timeline_handoff(
    self,
    *,
    draft: Dict[str, Any],
    document_optimization: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    optimization_report = document_optimization if isinstance(document_optimization, dict) else {}
    for candidate in (
        optimization_report.get("email_timeline_handoff"),
        (draft.get("source_context") or {}).get("email_timeline_handoff")
        if isinstance(draft.get("source_context"), dict)
        else None,
    ):
        if isinstance(candidate, dict) and candidate:
            return deepcopy(candidate)
    return {}


def _build_email_timeline_fact_entries(
    self,
    email_timeline_handoff: Dict[str, Any],
    *,
    limit: int = 6,
    exclude_predicate_families: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    canonical_facts = (
        list(email_timeline_handoff.get("canonical_facts") or [])
        if isinstance(email_timeline_handoff, dict)
        else []
    )
    default_claim_type = str(email_timeline_handoff.get("claim_type") or "").strip()
    default_claim_element_id = str(email_timeline_handoff.get("claim_element_id") or "").strip()
    excluded_predicates = {
        str(value or "").strip().lower()
        for value in (exclude_predicate_families or [])
        if str(value or "").strip()
    }
    entries: List[Dict[str, Any]] = []
    seen = set()
    for fact in canonical_facts:
        if not isinstance(fact, dict):
            continue
        predicate_family = str(fact.get("predicate_family") or "").strip().lower()
        if predicate_family and predicate_family in excluded_predicates:
            continue
        text = re.sub(r"\s+", " ", str(fact.get("text") or "").strip())
        if len(text) < 12:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            {
                "text": text,
                "fact_ids": _normalize_identifier_list(
                    [fact.get("fact_id")] + list(fact.get("related_fact_ids") or [])
                ),
                "source_artifact_ids": _normalize_identifier_list(
                    list(fact.get("source_artifact_ids") or [])
                ),
                "claim_types": _normalize_identifier_list(
                    list(fact.get("claim_types") or [])
                    + ([default_claim_type] if default_claim_type else [])
                ),
                "claim_element_ids": _normalize_identifier_list(
                    list(fact.get("element_tags") or [])
                    + ([default_claim_element_id] if default_claim_element_id else [])
                    + ([fact.get("predicate_family")] if fact.get("predicate_family") else [])
                ),
                "source_kind": str(fact.get("source_kind") or "email_timeline_candidate").strip()
                or "email_timeline_candidate",
                "source_ref": str(fact.get("source_ref") or fact.get("fact_id") or "").strip() or None,
            }
        )
        if len(entries) >= limit:
            break
    return entries


def _build_email_timeline_narrative_text(
    self,
    predicate_family: str,
    facts: List[Dict[str, Any]],
) -> str:
    ordered_facts = sorted(
        [fact for fact in facts if isinstance(fact, dict)],
        key=lambda fact: str(
            (fact.get("temporal_context") or {}).get("sortable_date")
            or fact.get("event_date_or_range")
            or ""
        ),
    )
    if not ordered_facts:
        return ""

    def _date_text(fact: Dict[str, Any]) -> str:
        return _format_timeline_date(
            (fact.get("temporal_context") or {}).get("start_date")
            or fact.get("event_date_or_range")
        )

    first_date = _date_text(ordered_facts[0])
    last_date = _date_text(ordered_facts[-1])
    clackamas_participants = _unique_preserving_order(
        [
            str(email).strip().lower()
            for fact in ordered_facts
            for email in list(fact.get("participants") or [])
            if str(email).strip().lower().endswith("@clackamas.us")
        ]
    )
    participant_phrase = _join_chronology_segments(clackamas_participants[:4]) if clackamas_participants else ""

    if predicate_family == "fraud_household" and first_date and last_date:
        return (
            f"Beginning on {first_date} and continuing through {last_date}, Plaintiff emailed "
            "Clackamas County Housing Authority staff in the "
            "'Allegations of Fraud - JC Household' chain, "
            f"including {participant_phrase or 'multiple Clackamas housing staff members'}."
        )
    if predicate_family == "additional_information" and first_date and last_date:
        return (
            f"From {first_date} through {last_date}, Clackamas housing staff sent "
            "'Additional Information Needed' emails requesting additional housing-program information from Plaintiff."
        )
    if predicate_family == "cortez_case" and first_date:
        return (
            f"On {first_date}, Plaintiff emailed Clackamas personnel regarding the "
            "'Jane Kay Cortez vs Solomon Samuel Barber' matter."
        )
    if predicate_family == "hcv_orientation" and first_date:
        attachment_names = _unique_preserving_order(
            [
                str(attachment.get("filename") or "").strip()
                for fact in ordered_facts
                for attachment in list(
                    self._load_email_timeline_message_metadata(fact.get("source_ref")).get("attachments") or []
                )
                if isinstance(attachment, dict) and str(attachment.get("filename") or "").strip()
            ]
        )
        denial_attachment = next(
            (name for name in attachment_names if "denial" in name.lower() or "ra-" in name.lower()),
            "",
        )
        attachment_clause = (
            f" One of those Clackamas emails included the attachment '{denial_attachment}'."
            if denial_attachment
            else ""
        )
        return (
            f"On {first_date}, Clackamas housing staff emailed Plaintiff in the 'HCV Orientation' thread "
            f"involving {participant_phrase or 'Clackamas voucher staff'}."
            f"{attachment_clause}"
        )
    return ""


def _build_email_timeline_narrative_fact_entries(
    self,
    email_timeline_handoff: Dict[str, Any],
    *,
    limit: int = 4,
) -> List[Dict[str, Any]]:
    canonical_facts = (
        list(email_timeline_handoff.get("canonical_facts") or [])
        if isinstance(email_timeline_handoff, dict)
        else []
    )
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for fact in canonical_facts:
        if not isinstance(fact, dict):
            continue
        predicate_family = str(fact.get("predicate_family") or "").strip().lower()
        if not predicate_family:
            continue
        grouped.setdefault(predicate_family, []).append(fact)

    entries: List[Dict[str, Any]] = []
    for predicate_family in ("hcv_orientation", "additional_information", "cortez_case", "fraud_household"):
        facts = grouped.get(predicate_family) or []
        text = self._build_email_timeline_narrative_text(predicate_family, facts)
        if not text:
            continue
        entries.append(
            {
                "text": text,
                "fact_ids": _normalize_identifier_list([fact.get("fact_id") for fact in facts]),
                "source_artifact_ids": _normalize_identifier_list(
                    [fact.get("source_ref") for fact in facts if fact.get("source_ref")]
                ),
                "claim_types": _normalize_identifier_list(
                    [claim_type for fact in facts for claim_type in list(fact.get("claim_types") or [])]
                ),
                "claim_element_ids": _normalize_identifier_list(
                    [predicate_family]
                    + [element_id for fact in facts for element_id in list(fact.get("element_tags") or [])]
                ),
                "source_kind": "email_timeline_narrative",
                "source_ref": str(facts[0].get("source_ref") or "").strip() or None,
            }
        )
        if len(entries) >= limit:
            break
    return entries


def _build_email_timeline_chronology_lines(
    self,
    email_timeline_handoff: Dict[str, Any],
    *,
    limit: int = 6,
) -> List[str]:
    canonical_facts = (
        list(email_timeline_handoff.get("canonical_facts") or [])
        if isinstance(email_timeline_handoff, dict)
        else []
    )
    lines: List[str] = []
    seen = set()
    for fact in canonical_facts:
        if not isinstance(fact, dict):
            continue
        temporal_context = fact.get("temporal_context") if isinstance(fact.get("temporal_context"), dict) else {}
        event_date = _format_timeline_date(
            temporal_context.get("start_date")
            or fact.get("event_date_or_range")
        )
        text = re.sub(r"\s+", " ", str(fact.get("text") or "").strip())
        if len(text) < 12 or not event_date:
            continue
        line = f"On {event_date}, {text}"
        if not line.endswith((".", "?", "!")):
            line = f"{line}."
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def _enrich_draft_with_email_timeline_handoff(
    self,
    draft: Dict[str, Any],
    *,
    email_timeline_handoff: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(draft, dict) or not isinstance(email_timeline_handoff, dict) or not email_timeline_handoff:
        return draft

    narrative_entries = self._build_email_timeline_narrative_fact_entries(email_timeline_handoff)
    narrative_predicates = _normalize_identifier_list(
        [
            element_id
            for entry in narrative_entries
            for element_id in _coerce_list(entry.get("claim_element_ids"))
            if str(element_id or "").strip().lower()
            in {"hcv_orientation", "additional_information", "cortez_case", "fraud_household"}
        ]
    )
    raw_limit = 0 if narrative_entries else 6
    email_fact_entries = narrative_entries + self._build_email_timeline_fact_entries(
        email_timeline_handoff,
        limit=raw_limit,
        exclude_predicate_families=narrative_predicates,
    )
    email_chronology_lines = self._build_email_timeline_chronology_lines(email_timeline_handoff)
    if not email_fact_entries and not email_chronology_lines:
        return draft

    updated = dict(draft)
    existing_fact_entries = [
        dict(entry)
        for entry in _coerce_list(updated.get("summary_of_fact_entries"))
        if isinstance(entry, dict)
    ]
    merged_fact_entries: List[Dict[str, Any]] = []
    seen_fact_texts = set()
    for entry in email_fact_entries + existing_fact_entries:
        text = re.sub(r"\s+", " ", str(entry.get("text") or "").strip())
        if len(text) < 12:
            continue
        key = text.lower()
        if key in seen_fact_texts:
            continue
        seen_fact_texts.add(key)
        normalized_entry = dict(entry)
        normalized_entry["text"] = text
        normalized_entry["fact_ids"] = _normalize_identifier_list(normalized_entry.get("fact_ids") or [])
        normalized_entry["source_artifact_ids"] = _normalize_identifier_list(
            normalized_entry.get("source_artifact_ids") or []
        )
        normalized_entry["claim_types"] = _normalize_identifier_list(normalized_entry.get("claim_types") or [])
        normalized_entry["claim_element_ids"] = _normalize_identifier_list(
            normalized_entry.get("claim_element_ids") or []
        )
        if normalized_entry.get("source_ref") is not None:
            source_ref = str(normalized_entry.get("source_ref") or "").strip()
            normalized_entry["source_ref"] = source_ref or None
        merged_fact_entries.append(normalized_entry)
        if len(merged_fact_entries) >= 14:
            break

    if narrative_entries:
        filtered_fact_entries = [
            entry for entry in merged_fact_entries if not self._is_low_signal_email_summary_entry(entry)
        ]
        if filtered_fact_entries:
            merged_fact_entries = filtered_fact_entries

    if merged_fact_entries:
        updated["summary_of_fact_entries"] = merged_fact_entries
        updated["summary_of_facts"] = [
            str(entry.get("text") or "").strip()
            for entry in merged_fact_entries
            if str(entry.get("text") or "").strip()
        ]

    chronology_lines = _unique_preserving_order(
        list(self._normalize_text_lines(updated.get("anchored_chronology_summary", [])))
        + email_chronology_lines
    )
    if chronology_lines:
        updated["anchored_chronology_summary"] = chronology_lines[:8]

    claims_for_relief = (
        list(updated.get("claims_for_relief") or [])
        if isinstance(updated.get("claims_for_relief"), list)
        else []
    )
    if merged_fact_entries:
        updated["factual_allegation_entries"] = self._build_factual_allegation_entries(
            summary_fact_entries=merged_fact_entries,
            claims_for_relief=claims_for_relief,
        )
        updated["factual_allegations"] = self._build_factual_allegations(
            summary_of_facts=updated.get("summary_of_facts", []),
            claims_for_relief=claims_for_relief,
        )
    return updated


def _specialize_generic_claims_from_email_support(
    self,
    draft: Dict[str, Any],
    *,
    email_timeline_handoff: Dict[str, Any],
    email_authority_enrichment: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(draft, dict):
        return draft
    claims = [dict(item) for item in list(draft.get("claims_for_relief") or []) if isinstance(item, dict)]
    if len(claims) != 1:
        return draft
    base_claim = claims[0]
    if normalize_claim_type(base_claim.get("claim_type") or "") != "general_civil_action":
        return draft

    inferred_claim_types = self._infer_claim_types_from_email_support(
        email_timeline_handoff=email_timeline_handoff,
        email_authority_enrichment=email_authority_enrichment,
    )
    if not inferred_claim_types:
        return draft

    specialized_claims: List[Dict[str, Any]] = []
    base_facts = [
        str(item or "").strip()
        for item in list(base_claim.get("supporting_facts") or [])
        if str(item or "").strip() and not self._is_generic_claim_support_text(item)
    ]
    summary_facts = [
        line
        for line in self._normalize_text_lines(draft.get("summary_of_facts", []))
        if not self._is_generic_claim_support_text(line)
    ]
    merged_claim_facts = _unique_preserving_order(base_facts + summary_facts)[:8]
    for claim_type in inferred_claim_types[:3]:
        specialized = deepcopy(base_claim)
        specialized["claim_type"] = claim_type
        specialized["count_title"] = self._humanize_claim_title(claim_type, merged_claim_facts or base_facts)
        if merged_claim_facts:
            specialized["supporting_facts"] = merged_claim_facts
        specialized["legal_standards"] = (
            self._build_claim_legal_standard_fallbacks(claim_type)
            + self._build_claim_authority_lines_from_email_enrichment(
                claim_type,
                email_authority_enrichment=email_authority_enrichment,
            )
        )
        specialized_claims.append(specialized)

    updated = dict(draft)
    updated["claims_for_relief"] = sorted(specialized_claims, key=self._claim_order_score)
    return updated


def _build_email_timeline_issue_allegations(
    self,
    allegations: List[str],
    source_allegations: Optional[List[str]] = None,
) -> List[str]:
    source_pool = [str(item or "").strip() for item in (source_allegations or allegations) if str(item or "").strip()]
    if not source_pool:
        return []
    priority_lines = [line for line in source_pool if self._is_priority_email_timeline_allegation(line)]
    if not priority_lines:
        return []

    combined = " ".join(priority_lines).lower()
    has_hcv_orientation = "hcv orientation" in combined
    has_additional_information = "additional information needed" in combined
    has_cortez_case = "jane kay cortez" in combined
    has_ra_denial = "cortez-j-ra-denial" in combined or "ra-denial" in combined or "ra denial" in combined
    has_fraud_chain = "jc household" in combined or "allegations of fraud" in combined

    allegations_out: List[str] = []
    if has_hcv_orientation and has_ra_denial:
        allegations_out.append(
            "Plaintiff alleges that, by March 26, 2026, Clackamas housing staff were circulating an HCV orientation email chain that included the RA-denial attachment, reflecting maintenance of the challenged denial of housing assistance."
        )
    elif has_hcv_orientation:
        allegations_out.append(
            "Plaintiff alleges that, by March 26, 2026, Clackamas housing staff were still handling Plaintiff's housing matter through the HCV Orientation email chain while maintaining the challenged adverse housing action."
        )

    if has_additional_information:
        allegations_out.append(
            "Plaintiff further alleges that Clackamas housing staff used the 'Additional Information Needed' thread between February 9 and March 10, 2026 to demand additional housing-program information while the challenged denial or loss of assistance remained in place."
        )

    if has_cortez_case and (has_hcv_orientation or has_additional_information):
        allegations_out.append(
            "Plaintiff alleges that the March 10, 2026 Cortez case emails and the March 26, 2026 HCV Orientation emails show Clackamas personnel were actively handling Plaintiff's housing matter without first providing the notice and review protections required before enforcing an adverse housing decision."
        )

    if has_ra_denial:
        allegations_out.append(
            "Plaintiff further alleges that the RA-denial attachment and related HCV communications support Plaintiff's claim that Defendant denied housing-related benefits or accommodations on discriminatory grounds."
        )
    elif has_fraud_chain and has_hcv_orientation:
        allegations_out.append(
            "Plaintiff alleges that the December 2025 through March 2026 Clackamas email sequence shows a continuing course of adverse housing treatment rather than an isolated communication."
        )

    return _unique_preserving_order(allegations_out)
