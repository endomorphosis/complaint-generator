from pathlib import Path
import base64
import copy
import fcntl
import json
import os
import stat
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from complaint_phases.document_surface import (
    DEFAULT_OUTPUT_DIR,
    _build_claim_checklist_chip_labels as _pipeline_claim_chip_labels,
    build_intake_case_review_summary,
    build_intake_status_summary,
    build_intake_warning_entries,
    humanize_workflow_priority_label,
    normalize_workflow_phase_recommended_actions,
    resolve_prioritized_workflow_phase,
)
from .fastapi_compat import attach_router_routes
from integrations.ipfs_datasets.storage import retrieve_bytes


FORMAL_COMPLAINT_DOCUMENT_REQUEST_EXAMPLE = {
    "district": "Northern District of California",
    "county": "San Francisco County",
    "plaintiff_names": ["Jane Doe"],
    "defendant_names": ["Acme Corporation"],
    "enable_agentic_optimization": True,
    "optimization_max_iterations": 1,
    "optimization_target_score": 0.95,
    "optimization_provider": "huggingface_router",
    "optimization_model_name": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
    "optimization_llm_config": {
        "base_url": "https://router.huggingface.co/v1",
        "headers": {
            "X-Title": "Complaint Generator"
        },
        "arch_router": {
            "enabled": True,
            "model": "katanemo/Arch-Router-1.5B",
            "context": "Complaint drafting, legal issue spotting, and filing packet generation.",
            "routes": {
                "legal_reasoning": "meta-llama/Llama-3.3-70B-Instruct",
                "drafting": "Qwen/Qwen3-Coder-480B-A35B-Instruct"
            }
        },
        "timeout": 45
    },
    "output_formats": ["txt", "packet"]
}


class ServiceRecipientDetail(BaseModel):
    recipient: Optional[str] = None
    method: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None


class AdditionalSignerDetail(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    firm: Optional[str] = None
    bar_number: Optional[str] = None
    contact: Optional[str] = None


class AffidavitExhibitDetail(BaseModel):
    label: Optional[str] = None
    title: Optional[str] = None
    link: Optional[str] = None
    summary: Optional[str] = None


class FormalComplaintDocumentRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": FORMAL_COMPLAINT_DOCUMENT_REQUEST_EXAMPLE})

    user_id: Optional[str] = None
    court_name: str = "United States District Court"
    district: str = ""
    county: Optional[str] = None
    division: Optional[str] = None
    court_header_override: Optional[str] = None
    case_number: Optional[str] = None
    lead_case_number: Optional[str] = None
    related_case_number: Optional[str] = None
    assigned_judge: Optional[str] = None
    courtroom: Optional[str] = None
    title_override: Optional[str] = None
    plaintiff_names: List[str] = Field(default_factory=list)
    defendant_names: List[str] = Field(default_factory=list)
    requested_relief: List[str] = Field(default_factory=list)
    jury_demand: bool = False
    jury_demand_text: Optional[str] = None
    signer_name: Optional[str] = None
    signer_title: Optional[str] = None
    signer_firm: Optional[str] = None
    signer_bar_number: Optional[str] = None
    signer_contact: Optional[str] = None
    additional_signers: List[AdditionalSignerDetail] = Field(default_factory=list)
    declarant_name: Optional[str] = None
    service_method: Optional[str] = None
    service_recipients: List[str] = Field(default_factory=list)
    service_recipient_details: List[ServiceRecipientDetail] = Field(default_factory=list)
    signature_date: Optional[str] = None
    verification_date: Optional[str] = None
    service_date: Optional[str] = None
    affidavit_title: Optional[str] = None
    affidavit_intro: Optional[str] = None
    affidavit_facts: List[str] = Field(default_factory=list)
    affidavit_supporting_exhibits: List[AffidavitExhibitDetail] = Field(default_factory=list)
    affidavit_include_complaint_exhibits: Optional[bool] = None
    affidavit_venue_lines: List[str] = Field(default_factory=list)
    affidavit_jurat: Optional[str] = None
    affidavit_notary_block: List[str] = Field(default_factory=list)
    enable_agentic_optimization: bool = False
    optimization_max_iterations: int = 2
    optimization_target_score: float = 0.9
    optimization_provider: Optional[str] = None
    optimization_model_name: Optional[str] = None
    optimization_llm_config: Dict[str, Any] = Field(default_factory=dict)
    optimization_persist_artifacts: bool = False
    email_timeline_handoff_path: Optional[str] = None
    email_authority_enrichment_path: Optional[str] = None
    output_dir: Optional[str] = None
    output_formats: List[str] = Field(default_factory=lambda: ["docx", "pdf"])


def _default_generated_documents_root() -> Path:
    return DEFAULT_OUTPUT_DIR.resolve()


def _is_allowed_download_path(path: Path) -> bool:
    try:
        path.resolve().relative_to(_default_generated_documents_root())
        return True
    except ValueError:
        return False


def _build_download_url(path: str) -> Optional[str]:
    resolved = Path(path).resolve()
    if not _is_allowed_download_path(resolved):
        return None
    return f"/api/documents/download?path={resolved}"


def _build_optimization_trace_url(cid: str) -> str:
    return f"/api/documents/optimization-trace?cid={cid}"


def _build_optimization_trace_view_url(cid: str) -> str:
    return f"/document/optimization-trace?cid={cid}"


def _dedupe_text_values(values: Any) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for value in values if isinstance(values, list) else []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _build_review_url(
    *,
    user_id: Optional[str] = None,
    claim_type: Optional[str] = None,
    section: Optional[str] = None,
) -> str:
    params = {}
    if user_id:
        params["user_id"] = user_id
    if claim_type:
        params["claim_type"] = claim_type
    if section:
        params["section"] = section
    query = urlencode(params)
    return f"/claim-support-review?{query}" if query else "/claim-support-review"


def _default_support_kind_for_section(section_key: Optional[str]) -> Optional[str]:
    mapping = {
        "summary_of_facts": "evidence",
        "exhibits": "evidence",
        "jurisdiction_and_venue": "authority",
        "claims_for_relief": "authority",
    }
    normalized = str(section_key or "").strip().lower()
    return mapping.get(normalized)


def _build_review_intent(
    *,
    user_id: Optional[str] = None,
    claim_type: Optional[str] = None,
    section: Optional[str] = None,
    follow_up_support_kind: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "claim_type": claim_type,
        "section": section,
        "follow_up_support_kind": follow_up_support_kind,
        "review_url": _build_review_url(user_id=user_id, claim_type=claim_type, section=section),
    }


def _append_review_query_params(review_url: str, **params: Optional[str]) -> str:
    normalized_url = str(review_url or "").strip() or "/claim-support-review"
    split = urlsplit(normalized_url)
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    for key, value in params.items():
        text = str(value or "").strip()
        if text:
            query[key] = text
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))


def _resolve_document_review_url(
    *,
    user_id: Optional[str],
    dashboard_url: str,
    claim_review_map: Dict[str, Dict[str, Any]],
    section_review_map: Dict[str, Dict[str, Any]],
    claim_type: Optional[str] = None,
    section_key: Optional[str] = None,
) -> str:
    normalized_claim_type = str(claim_type or "").strip()
    normalized_section_key = str(section_key or "").strip()

    if normalized_section_key:
        section_target = section_review_map.get(normalized_section_key) or {}
        section_context = section_target.get("review_context") if isinstance(section_target.get("review_context"), dict) else {}
        return str(
            section_target.get("review_url")
            or _build_review_url(
                user_id=user_id,
                claim_type=normalized_claim_type or section_context.get("claim_type"),
                section=normalized_section_key,
            )
        )

    if normalized_claim_type:
        claim_target = claim_review_map.get(normalized_claim_type) or {}
        return str(
            claim_target.get("review_url")
            or _build_review_url(user_id=user_id, claim_type=normalized_claim_type)
        )

    return dashboard_url


def _claim_type_in_case_summary_queue(
    intake_case_summary: Dict[str, Any],
    *,
    claim_type: Optional[str],
    summary_key: str,
) -> bool:
    normalized_claim_type = str(claim_type or "").strip()
    if not normalized_claim_type:
        return False
    summary = intake_case_summary.get(summary_key) if isinstance(intake_case_summary.get(summary_key), dict) else {}
    for item in summary.get("claims") or []:
        if str((item or {}).get("claim_type") or "").strip() == normalized_claim_type:
            return True
    return False




def _build_checklist_intake_status(intake_status: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intake_status, dict) or not intake_status:
        return {}
    blockers = intake_status.get("blockers")
    blocker_list = [str(item).strip() for item in blockers] if isinstance(blockers, list) else []
    contradictions = intake_status.get("contradictions")
    contradiction_list = contradictions if isinstance(contradictions, list) else []
    next_action = intake_status.get("next_action") if isinstance(intake_status.get("next_action"), dict) else {}
    primary_validation_target = (
        intake_status.get("primary_validation_target")
        if isinstance(intake_status.get("primary_validation_target"), dict)
        else {}
    )
    document_drafting_next_action = (
        intake_status.get("document_drafting_next_action")
        if isinstance(intake_status.get("document_drafting_next_action"), dict)
        else {}
    )
    return {
        "score": float(intake_status.get("score") or 0.0),
        "ready_to_advance": bool(intake_status.get("ready_to_advance", False)),
        "remaining_gap_count": int(intake_status.get("remaining_gap_count") or 0),
        "contradiction_count": int(intake_status.get("contradiction_count") or len(contradiction_list)),
        "blockers": blocker_list,
        "contradictions": contradiction_list[:2],
        "next_action": next_action,
        "primary_validation_target": primary_validation_target,
        "document_drafting_next_action": document_drafting_next_action,
    }


def _merge_claim_temporal_gap_summary(
    intake_case_summary: Dict[str, Any],
    document_optimization: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    merged = dict(intake_case_summary or {}) if isinstance(intake_case_summary, dict) else {}
    optimization_payload = document_optimization if isinstance(document_optimization, dict) else {}
    intake_priorities = (
        optimization_payload.get("intake_priorities")
        if isinstance(optimization_payload.get("intake_priorities"), dict)
        else {}
    )
    claim_temporal_gap_summary = intake_priorities.get("claim_temporal_gap_summary")
    if not isinstance(claim_temporal_gap_summary, list) or not claim_temporal_gap_summary:
        return merged
    merged["claim_temporal_gap_count"] = int(intake_priorities.get("claim_temporal_gap_count") or 0)
    merged["claim_temporal_gap_summary"] = [
        dict(item)
        for item in claim_temporal_gap_summary
        if isinstance(item, dict)
    ]
    return merged


def _annotate_workflow_priority_with_temporal_gap_summary(
    workflow_priority: Dict[str, Any],
    intake_case_summary: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(workflow_priority, dict) or not workflow_priority:
        return workflow_priority
    claim_temporal_gap_count = int(intake_case_summary.get("claim_temporal_gap_count") or 0)
    claim_temporal_gap_summary = (
        intake_case_summary.get("claim_temporal_gap_summary")
        if isinstance(intake_case_summary.get("claim_temporal_gap_summary"), list)
        else []
    )
    if claim_temporal_gap_count <= 0 or not claim_temporal_gap_summary:
        return workflow_priority
    chip_labels = list(workflow_priority.get("chip_labels") or [])
    chip_labels.append(f"claim chronology gaps: {claim_temporal_gap_count}")
    first_claim_type = str((claim_temporal_gap_summary[0] or {}).get("claim_type") or "").strip()
    if first_claim_type:
        chip_labels.append(f"chronology focus: {humanize_workflow_priority_label(first_claim_type)}")
    workflow_priority["chip_labels"] = chip_labels
    return workflow_priority


def _merge_warning_entries(existing: Any, additions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    base = existing if isinstance(existing, list) else []
    merged: List[Dict[str, Any]] = [item for item in base if isinstance(item, dict)]
    seen = {
        (
            str(item.get("code") or "").strip(),
            str(item.get("message") or "").strip(),
            str(item.get("severity") or "").strip(),
        )
        for item in merged
    }
    for item in additions:
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("code") or "").strip(),
            str(item.get("message") or "").strip(),
            str(item.get("severity") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _merge_chip_labels(existing: Any, additions: Any) -> List[str]:
    merged: List[str] = []
    seen = set()
    for source in (existing, additions):
        if not isinstance(source, list):
            continue
        for item in source:
            label = str(item or "").strip()
            if not label or label in seen:
                continue
            seen.add(label)
            merged.append(label)
    return merged


def _annotate_artifacts_with_download_urls(payload: Dict[str, Any]) -> Dict[str, Any]:
    artifacts = payload.get("artifacts") if isinstance(payload, dict) else None
    if not isinstance(artifacts, dict):
        return payload
    for artifact in artifacts.values():
        if not isinstance(artifact, dict):
            continue
        artifact_path = artifact.get("path")
        if artifact_path:
            download_url = _build_download_url(str(artifact_path))
            if download_url:
                artifact["download_url"] = download_url
    return payload



def _section_claim_types(section_key: str, claim_types: List[str]) -> List[str]:
    claim_oriented_sections = {
        "summary_of_facts",
        "claims_for_relief",
        "exhibits",
        "requested_relief",
    }
    return claim_types if section_key in claim_oriented_sections else []


def _build_claim_review_chip_labels(claim: Dict[str, Any]) -> List[str]:
    """Build chip labels for claim review using the canonical pipeline implementation.

    Delegates to ``_pipeline_claim_chip_labels`` so that the application layer
    stays in sync with the richer set of chip signals maintained by
    ``document_pipeline`` (temporal predicates, provenance kinds, authority
    treatment, etc.) rather than duplicating a simplified version here.
    """
    return _pipeline_claim_chip_labels(claim)


def _annotate_checklist_review_links(
    payload: Dict[str, Any],
    *,
    dashboard_url: str,
    claim_review_map: Dict[str, Dict[str, Any]],
    section_review_map: Dict[str, Dict[str, Any]],
    default_review_intent: Dict[str, Any],
    intake_status: Dict[str, Any],
) -> Dict[str, Any]:
    checklist_targets = []
    top_level = payload.get("filing_checklist") if isinstance(payload.get("filing_checklist"), list) else []
    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else {}
    draft_level = draft.get("filing_checklist") if isinstance(draft.get("filing_checklist"), list) else []
    if top_level:
        checklist_targets.append(top_level)
    if draft_level and draft_level is not top_level:
        checklist_targets.append(draft_level)

    for checklist in checklist_targets:
        for item in checklist:
            if not isinstance(item, dict):
                continue
            scope = str(item.get("scope") or "").strip().lower()
            key = str(item.get("key") or "").strip()
            target = None
            if scope == "claim":
                target = claim_review_map.get(key)
            elif scope == "section":
                target = section_review_map.get(key)
            if target:
                item["review_url"] = target.get("review_url")
                item["review_context"] = target.get("review_context")
                item["review_intent"] = target.get("review_intent")
                merged_chip_labels = _merge_chip_labels(item.get("chip_labels"), target.get("chip_labels"))
                if merged_chip_labels:
                    item["chip_labels"] = merged_chip_labels
                else:
                    item.pop("chip_labels", None)
            else:
                item["review_url"] = dashboard_url
                item["review_context"] = {"user_id": default_review_intent.get("user_id")}
                item["review_intent"] = dict(default_review_intent)
            if str(item.get("status") or "").strip().lower() in {"warning", "blocked"}:
                checklist_intake_status = _build_checklist_intake_status(intake_status)
                if checklist_intake_status:
                    item["intake_status"] = checklist_intake_status
    return payload


def _build_document_focus_preview(draft: Dict[str, Any]) -> List[Dict[str, Any]]:
    preview_rows: List[Dict[str, Any]] = []

    def _append_rows(section: str, entries: Any) -> None:
        for entry in list(entries or []):
            if not isinstance(entry, dict):
                continue
            focus = entry.get("document_focus")
            if not isinstance(focus, dict) or not focus:
                continue
            preview_rows.append(
                {
                    "section": section,
                    "text": str(entry.get("text") or "").strip(),
                    "focus_source": str(focus.get("focus_source") or "").strip(),
                    "action": str(focus.get("action") or "").strip(),
                    "target_claim_element_id": str(focus.get("target_claim_element_id") or "").strip(),
                    "original_claim_element_id": str(focus.get("original_claim_element_id") or "").strip(),
                    "preferred_support_kind": str(focus.get("preferred_support_kind") or "").strip(),
                    "priority_rank": int(entry.get("document_focus_priority_rank") or 0),
                }
            )

    _append_rows("summary_of_facts", draft.get("summary_of_fact_entries"))
    _append_rows("factual_allegations", draft.get("factual_allegation_paragraphs"))
    claims = draft.get("claims_for_relief") if isinstance(draft.get("claims_for_relief"), list) else []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        _append_rows(
            f"claims_for_relief:{str(claim.get('claim_type') or '').strip() or 'claim'}",
            claim.get("supporting_fact_provenance"),
        )

    preview_rows.sort(
        key=lambda row: (
            int(row.get("priority_rank") or 0) or 9999,
            str(row.get("section") or ""),
            str(row.get("text") or ""),
        )
    )
    return preview_rows[:8]

from .document_review import _build_document_review_workflow_phase_priority, _build_document_review_workflow_priority, _build_document_builder_summary, _annotate_review_links




OUTLINE_TASK_ID = "CIMP-UX-30"
_LABEL_KEYS = ("evidence_label", "label", "exhibit_label", "support_label")
_PROSE_KEYS = ("model_prose", "model_text", "generated_prose", "ai_suggestion")


def _outline_text(value: Any, limit: int = 500) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _outline_span(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    start = value.get("start", value.get("span_start"))
    end = value.get("end", value.get("span_end"))
    if type(start) is not int or type(end) is not int or start < 0 or end <= start:
        return None
    return {
        "start": start,
        "end": end,
        "text": _outline_text(value.get("text"), 400),
        "unit": _outline_text(value.get("unit"), 40) or "utf-8-bytes",
    }


def _current_draft(case_file: Dict[str, Any]) -> Dict[str, Any]:
    store = case_file.get("draft_workflow") if isinstance(case_file.get("draft_workflow"), dict) else {}
    versions = [item for item in store.get("versions") or [] if isinstance(item, dict)]
    if not versions:
        return {"present": False, "draft_id": "", "revision": 0, "text": "", "text_digest": ""}
    current = max(versions, key=lambda item: (int(item.get("revision") or 0), str(item.get("draft_id") or "")))
    return {
        "present": True,
        "draft_id": _outline_text(current.get("draft_id"), 80),
        "revision": int(current.get("revision") or 0),
        "text": _outline_text(current.get("text"), 4000),
        "text_digest": _outline_text(current.get("text_digest"), 80),
    }


def _facts(case_file: Dict[str, Any]) -> List[Dict[str, Any]]:
    domains = case_file.get("workflow_domains") if isinstance(case_file.get("workflow_domains"), dict) else {}
    factual = domains.get("factual") if isinstance(domains.get("factual"), dict) else {}
    rows = []
    for item in factual.get("assertions") or []:
        if not isinstance(item, dict):
            continue
        fact_id = _outline_text(item.get("id") or item.get("fact_id"), 80)
        if not fact_id:
            continue
        rows.append({
            "fact_id": fact_id,
            "text": _outline_text(item.get("text"), 500),
            "bound": item.get("bound") is True,
            "revision": int(item.get("revision") or 0) if type(item.get("revision")) is int else 0,
        })
    return rows


def _exhibits(case_file: Dict[str, Any]) -> List[Dict[str, Any]]:
    domains = case_file.get("workflow_domains") if isinstance(case_file.get("workflow_domains"), dict) else {}
    evidence = domains.get("evidence") if isinstance(domains.get("evidence"), dict) else {}
    rows = []
    for item in evidence.get("exhibits") or []:
        if not isinstance(item, dict):
            continue
        span = _outline_span(item.get("span") if isinstance(item.get("span"), dict) else item)
        label = ""
        for key in _LABEL_KEYS:
            label = label or _outline_text(item.get(key), 160)
        rows.append({
            "exhibit_id": _outline_text(item.get("id") or item.get("exhibit_id"), 80),
            "artifact_id": _outline_text(item.get("artifact_id"), 120),
            "fact_id": _outline_text(item.get("fact_id"), 80),
            "requirement_id": _outline_text(item.get("requirement_id") or item.get("passage_id"), 120),
            "span": span,
            "label_only": bool(label) and span is None,
            "label": label,
        })
    return rows


def _gap(reason: str, **extra: Any) -> Dict[str, Any]:
    payload = {"reason": reason, "visible": True}
    payload.update(extra)
    return payload


def project_complaint_outline(case_file: Any) -> Dict[str, Any]:
    """Project the current draft beside facts, spans, and admitted authority.

    A model paragraph or an evidence label never completes a requirement.
    Legal sufficiency and proof stay false on this surface.
    """

    source = case_file if isinstance(case_file, dict) else {}
    draft = _current_draft(source)
    facts = _facts(source)
    exhibits = _exhibits(source)
    stored = source.get("derived_dependency_requirements") if isinstance(source.get("derived_dependency_requirements"), dict) else {}
    requirements_in = [item for item in stored.get("requirements") or [] if isinstance(item, dict)]
    unresolved = [item for item in stored.get("unresolved_research") or [] if isinstance(item, dict)]
    fact_ids = {item["fact_id"] for item in facts}
    sections = []
    gaps = []
    if not draft["present"] or not draft["text"]:
        gaps.append(_gap("missing_draft_text"))
    for item in unresolved:
        gaps.append(_gap(str(item.get("reason") or "unresolved_research"), passage_id=_outline_text(item.get("passage_id"), 120)))
    if not requirements_in and not unresolved:
        gaps.append(_gap("no_requirements"))
    for index, item in enumerate(requirements_in):
        passage_id = _outline_text(item.get("passage_id"), 120)
        span = _outline_span(item.get("source_span"))
        admitted = item.get("admitted_law") is True and bool(passage_id) and span is not None
        prose = ""
        for key in _PROSE_KEYS:
            prose = prose or _outline_text(item.get(key), 500)
        label = ""
        for key in _LABEL_KEYS:
            label = label or _outline_text(item.get(key), 160)
        linked_fact_ids = []
        for support in item.get("fact_support") or []:
            if isinstance(support, dict):
                fact_id = _outline_text(support.get("fact_id"), 80)
                if fact_id and fact_id in fact_ids and fact_id not in linked_fact_ids:
                    linked_fact_ids.append(fact_id)
        requirement_id = _outline_text(item.get("requirement_id"), 80) or passage_id or f"requirement-{index + 1}"
        linked_exhibits = []
        for exhibit in exhibits:
            matches = exhibit["requirement_id"] in {requirement_id, passage_id} or exhibit["fact_id"] in linked_fact_ids
            if matches and exhibit["artifact_id"] and exhibit["span"] is not None:
                linked_exhibits.append(exhibit)
        section_gaps = []
        if prose:
            section_gaps.append(_gap("model_prose_is_not_support"))
        if label:
            section_gaps.append(_gap("evidence_label_is_not_support"))
        if not admitted:
            section_gaps.append(_gap("missing_admitted_authority"))
        if not linked_fact_ids:
            section_gaps.append(_gap("missing_fact"))
        elif any(not next(fact["text"] for fact in facts if fact["fact_id"] == fact_id) for fact_id in linked_fact_ids):
            section_gaps.append(_gap("missing_fact_text"))
        if not linked_exhibits:
            section_gaps.append(_gap("missing_evidence_span"))
        cited = admitted and bool(linked_fact_ids) and bool(linked_exhibits) and not any(
            gap["reason"] == "missing_fact_text" for gap in section_gaps
        )
        citation = _outline_text(item.get("citation") or item.get("name"), 160)
        authority = None
        if admitted:
            authority = {
                "passage_id": passage_id,
                "citation": citation,
                "authority_id": _outline_text(item.get("authority_id"), 120),
                "source_span": span,
                "admitted_law": True,
                "href": "#admitted-authority-" + passage_id,
            }
        section = {
            "section_id": requirement_id,
            "heading": citation or "Untitled requirement",
            "draft_text": draft["text"],
            "support_cited": cited,
            "legal_sufficiency": False,
            "proof": False,
            "model_prose": prose,
            "evidence_label": label,
            "caller_satisfied_ignored": item.get("satisfied") is True or item.get("complete") is True,
            "authority": authority,
            "facts": [fact for fact in facts if fact["fact_id"] in linked_fact_ids],
            "evidence": [{
                "artifact_id": exhibit["artifact_id"],
                "exhibit_id": exhibit["exhibit_id"],
                "span": exhibit["span"],
                "fact_id": exhibit["fact_id"],
            } for exhibit in linked_exhibits],
            "gaps": section_gaps,
            "requirement_completed": False,
        }
        sections.append(section)
        gaps.extend(dict(gap, section_id=requirement_id) for gap in section_gaps)
    for exhibit in exhibits:
        if exhibit["label_only"]:
            gaps.append(_gap("evidence_label_is_not_support", exhibit_id=exhibit["exhibit_id"]))
    status = "empty" if not sections and not draft["present"] else "gaps" if gaps else "cited"
    return {
        "task_id": OUTLINE_TASK_ID,
        "status": status,
        "legal_sufficiency": False,
        "proof": False,
        "governing_law": False,
        "draft": draft,
        "facts": facts,
        "sections": sections,
        "gaps": gaps,
        "unresolved_research": [{
            "reason": str(item.get("reason") or "unresolved_research"),
            "visible": True,
            "passage_id": _outline_text(item.get("passage_id"), 120),
        } for item in unresolved],
    }


EDITOR_TASK_ID = "CIMP-UX-31"
_DRAFT_EDITOR_SCHEMA = "complaint-draft-editor@1"
_DRAFT_EDITOR_KIND = "complaint-draft-editor"
_DRAFT_EDITOR_FILE = "draft-editor.json"


def _editor_error(exc: Exception) -> HTTPException:
    from .case_review import CaseReviewError
    from integrations.private_storage import PrivateKeyLockedError, PrivateKeyMaterialError, PrivateStorageError

    if isinstance(exc, CaseReviewError):
        code = "draft_field" if exc.code in {"lawyer_review_field", "lawyer_review_bounds"} else exc.code
        status = 409 if code in {"stale_revision", "stale_domain", "replay_mismatch"} else 422 if code in {
            "draft_field", "draft_bounds", "stage_not_ready", "draft_revision_required",
        } else 403 if code in {"actor_not_permitted", "key_revoked"} else 503
        return HTTPException(status_code=status, detail=code)
    if isinstance(exc, PrivateKeyLockedError):
        return HTTPException(status_code=409, detail="key_locked")
    if isinstance(exc, PrivateKeyMaterialError):
        code = "key_revoked" if exc.reason in {"case_key_destroyed", "key_unavailable"} and exc.reason == "case_key_destroyed" else "key_unavailable"
        if exc.reason == "case_key_destroyed":
            code = "key_revoked"
        return HTTPException(status_code=403 if code == "key_revoked" else 409, detail=code)
    if isinstance(exc, PrivateStorageError):
        return HTTPException(status_code=409, detail="key_unavailable")
    return HTTPException(status_code=503, detail="workflow_record_unavailable")


def _require_draft_owner(scope: Dict[str, Any], request: Request) -> Any:
    decision = getattr(request.state, "case_authorization", None)
    if decision is None or decision.membership != "owner" or decision.action not in {"case.read", "case.update", "case.download"}:
        raise HTTPException(status_code=403, detail="actor_not_permitted")
    if scope.get("membership") != "owner":
        raise HTTPException(status_code=403, detail="actor_not_permitted")
    return decision


def _draft_directory(decision: Any, request: Request):
    from .case_directory import CaseDirectory, CaseDirectoryError

    directory = getattr(request.app.state, "case_directory", None)
    if not isinstance(directory, CaseDirectory):
        authorizer = getattr(request.app.state, "case_authorizer", None)
        directory = getattr(authorizer, "_cases", None)
    if not isinstance(directory, CaseDirectory):
        raise HTTPException(status_code=503, detail="workflow_record_unavailable")
    try:
        return directory.owned_revision_directory(
            actor_principal_id=decision.actor_principal_id,
            case_id=decision.case_id,
        )
    except CaseDirectoryError as exc:
        raise HTTPException(status_code=403, detail=exc.code) from None


def _owner_key_session(decision: Any, request: Request):
    from integrations.private_storage import UserOwnedKeySession

    mediator = getattr(request.app.state, "case_handlers", None)
    session = None
    bound = getattr(request.state, "case_handler_mediator", None)
    if bound is None:
        resolver_mediator = None
        try:
            from .case_routes import _BOUND_HANDLERS
            resolver = _BOUND_HANDLERS.get()
            if resolver is not None:
                resolver_mediator = resolver()[0]
        except Exception:
            resolver_mediator = None
        session = getattr(resolver_mediator, "owner_key_session", None)
    if session is None:
        sessions = getattr(request.app.state, "owner_key_sessions", None)
        if isinstance(sessions, dict):
            session = sessions.get(decision.actor_principal_id)
    if not isinstance(session, UserOwnedKeySession):
        raise HTTPException(status_code=409, detail="key_unavailable")
    if session.unlocked is not True:
        raise HTTPException(status_code=409, detail="key_locked")
    return session


def _draft_data_key(session: Any, decision: Any) -> tuple[str, bytes]:
    key_id = session.ensure_data_key(decision.tenant_id, decision.case_id)
    key = session.lookup_data_key(decision.tenant_id, decision.case_id, key_id)
    if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
        raise HTTPException(status_code=409, detail="key_unavailable")
    return key_id, bytes(key)


def _draft_binding(decision: Any, head_revision: int):
    from integrations.private_storage import PrivateArtifactBinding

    return PrivateArtifactBinding(
        tenant_id=decision.tenant_id,
        case_id=decision.case_id,
        artifact_kind=_DRAFT_EDITOR_KIND,
        revision=str(head_revision),
        principal_id=decision.tenant_id,
    )


def _seal_draft(document: Dict[str, Any], decision: Any, key_id: str, key: bytes) -> bytes:
    from integrations.private_storage import assert_access_matches_binding, seal_private_artifact

    binding = _draft_binding(decision, int(document["head_revision"]))
    access = SimpleNamespace(trust="authenticated", principal_id=decision.tenant_id, case_id=decision.case_id)
    assert_access_matches_binding(access, binding)
    return seal_private_artifact(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        binding=binding,
        key=key,
        key_id=key_id,
    )


def _open_draft(envelope: bytes, decision: Any, head_revision: int, key_id: str, key: bytes) -> Dict[str, Any]:
    from integrations.private_storage import assert_access_matches_binding, open_private_artifact

    binding = _draft_binding(decision, head_revision)
    access = SimpleNamespace(trust="authenticated", principal_id=decision.tenant_id, case_id=decision.case_id)
    assert_access_matches_binding(access, binding)
    plaintext = open_private_artifact(envelope, binding=binding, key=key, expected_key_id=key_id)
    document = json.loads(plaintext.decode("utf-8"))
    if not isinstance(document, dict) or document.get("head_revision") != head_revision:
        raise HTTPException(status_code=409, detail="stale_revision")
    workflow = document.get("draft_workflow")
    if not isinstance(workflow, dict):
        raise HTTPException(status_code=409, detail="stale_revision")
    return document


def _read_editor_file(directory_fd: int) -> Optional[Dict[str, Any]]:
    try:
        descriptor = os.open(_DRAFT_EDITOR_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or not stat.S_ISREG(info.st_mode):
            raise HTTPException(status_code=503, detail="case_revision_unavailable")
        chunks = []
        while True:
            block = os.read(descriptor, 65536)
            if not block:
                break
            chunks.append(block)
    finally:
        os.close(descriptor)
    payload = json.loads(b"".join(chunks).decode("utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != _DRAFT_EDITOR_SCHEMA:
        raise HTTPException(status_code=409, detail="stale_revision")
    if type(payload.get("revision")) is not int or not isinstance(payload.get("envelope"), str):
        raise HTTPException(status_code=409, detail="stale_revision")
    return payload


def _write_editor_file(directory_fd: int, head_revision: int, envelope: bytes) -> None:
    raw = json.dumps({
        "schema": _DRAFT_EDITOR_SCHEMA,
        "revision": head_revision,
        "envelope": base64.b64encode(envelope).decode("ascii"),
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    temporary = ".draft-editor-" + os.urandom(8).hex() + ".tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory_fd)
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise HTTPException(status_code=503, detail="case_revision_unavailable")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(temporary, _DRAFT_EDITOR_FILE, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def _editor_lock(path: Path):
    from contextlib import contextmanager

    @contextmanager
    def locked():
        directory_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        lock_fd = None
        try:
            info = os.fstat(directory_fd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise HTTPException(status_code=503, detail="case_revision_unavailable")
            lock_fd = os.open(".draft-editor.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory_fd)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            yield directory_fd
        finally:
            if lock_fd is not None:
                os.close(lock_fd)
            os.close(directory_fd)

    return locked()


def _workflow_versions(document: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not document:
        return []
    store = document.get("draft_workflow") if isinstance(document.get("draft_workflow"), dict) else {}
    return [item for item in store.get("versions") or [] if isinstance(item, dict)]


def draft_revision_difference(base_text: str, compare_text: str) -> List[Dict[str, str]]:
    """Line difference an owner can inspect. Equal lines stay visible."""

    import difflib

    changes: List[Dict[str, str]] = []
    base_lines = base_text.splitlines()
    compare_lines = compare_text.splitlines()
    matcher = difflib.SequenceMatcher(a=base_lines, b=compare_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in {"equal", "delete", "replace"}:
            for line in base_lines[i1:i2]:
                changes.append({"op": "equal" if tag == "equal" else "delete", "text": line})
        if tag in {"insert", "replace"}:
            for line in compare_lines[j1:j2]:
                changes.append({"op": "insert", "text": line})
    return changes


def project_draft_editor(document: Optional[Dict[str, Any]], *, base_revision: Optional[int] = None,
                         compare_revision: Optional[int] = None, save_state: str = "idle") -> Dict[str, Any]:
    versions = sorted(_workflow_versions(document), key=lambda item: int(item.get("revision") or 0))
    public = []
    for item in versions:
        public.append({
            "draft_id": str(item.get("draft_id") or ""),
            "revision": int(item.get("revision") or 0),
            "text": str(item.get("text") or ""),
            "text_digest": str(item.get("text_digest") or ""),
            "actor_principal_id": str(item.get("actor_principal_id") or ""),
        })
    current = public[-1] if public else {"draft_id": "", "revision": 0, "text": "", "text_digest": "", "actor_principal_id": ""}
    left = base_revision
    right = compare_revision
    if left is None and right is None and len(public) >= 2:
        left = public[-2]["revision"]
        right = public[-1]["revision"]
    elif left is None and right is not None and len(public) >= 2:
        left = public[-2]["revision"]
    base = next((item for item in public if item["revision"] == left), None)
    compare = next((item for item in public if item["revision"] == right), None)
    difference = {
        "base_revision": left or 0,
        "compare_revision": right or 0,
        "base_text": base["text"] if base else "",
        "compare_text": compare["text"] if compare else "",
        "changes": draft_revision_difference(base["text"] if base else "", compare["text"] if compare else "") if base or compare else [],
    }
    head = int(document.get("head_revision") or 0) if isinstance(document, dict) else 0
    return {
        "task_id": EDITOR_TASK_ID,
        "save_state": save_state,
        "durable": head > 0,
        "head_revision": head,
        "draft_id": current["draft_id"],
        "current_revision": current["revision"],
        "current_text": current["text"],
        "text_digest": current["text_digest"],
        "revisions": public,
        "difference": difference,
        "browser_storage": False,
    }


def _loaded_document(directory_fd: int, decision: Any, session: Any) -> Optional[Dict[str, Any]]:
    stored = _read_editor_file(directory_fd)
    if stored is None:
        return {"head_revision": 0, "draft_workflow": {"versions": [], "reviews": [], "exports": []}}
    key_id, key = _draft_data_key(session, decision)
    envelope = base64.b64decode(stored["envelope"].encode("ascii"), validate=True)
    return _open_draft(envelope, decision, int(stored["revision"]), key_id, key)


def _publish_memory(case_file: Dict[str, Any], document: Dict[str, Any]) -> None:
    workflow = document.get("draft_workflow")
    if isinstance(workflow, dict):
        case_file["draft_workflow"] = copy.deepcopy(workflow)


def _project_locked_editor(case_id: str, request: Request, *, base_revision: Optional[int], compare_revision: Optional[int]) -> Dict[str, Any]:
    decision = _require_draft_owner({"membership": "owner"}, request)
    if decision.case_id != case_id:
        raise HTTPException(status_code=403, detail="cross_case_id")
    session = _owner_key_session(decision, request)
    path = _draft_directory(decision, request)
    with _editor_lock(path) as directory_fd:
        document = _loaded_document(directory_fd, decision, session)
    case_file = getattr(_request_mediator(), "intake_case_file", None)
    if isinstance(case_file, dict) and isinstance(document, dict) and int(document.get("head_revision") or 0) > 0:
        _publish_memory(case_file, document)
    return project_draft_editor(document, base_revision=base_revision, compare_revision=compare_revision, save_state="idle")


def _request_mediator() -> Any:
    from .case_routes import _BOUND_HANDLERS

    resolver = _BOUND_HANDLERS.get()
    if resolver is None:
        raise HTTPException(status_code=503, detail="workflow_record_unavailable")
    return resolver()[0]


def _save_locked_editor(case_id: str, request: Request, body: Dict[str, Any], scope: Dict[str, Any]) -> Dict[str, Any]:
    from fastapi.responses import JSONResponse
    from .case_review import version_draft

    decision = _require_draft_owner(scope, request)
    if decision.action != "case.update":
        raise HTTPException(status_code=403, detail="actor_not_permitted")
    if decision.case_id != case_id:
        raise HTTPException(status_code=403, detail="cross_case_id")
    expected = body.get("expected_head_revision")
    if type(expected) is not int:
        raise HTTPException(status_code=422, detail="draft_field")
    session = _owner_key_session(decision, request)
    key_id, key = _draft_data_key(session, decision)
    mediator = _request_mediator()
    case_file = getattr(mediator, "intake_case_file", None)
    if not isinstance(case_file, dict):
        raise HTTPException(status_code=503, detail="workflow_record_unavailable")
    path = _draft_directory(decision, request)
    with _editor_lock(path) as directory_fd:
        document = _loaded_document(directory_fd, decision, session)
        head = int(document.get("head_revision") or 0) if document else 0
        if head != expected:
            conflict = project_draft_editor(document, save_state="conflict")
            conflict["code"] = "stale_revision"
            conflict["overwrote_head"] = False
            return JSONResponse(status_code=409, content=conflict)
        before = _read_editor_file(directory_fd)
        before_bytes = json.dumps(before, sort_keys=True).encode("utf-8") if before else b""
        working = copy.deepcopy(case_file)
        stored_workflow = document.get("draft_workflow") if isinstance(document, dict) else {}
        if not isinstance(stored_workflow, dict):
            stored_workflow = {}
        working["draft_workflow"] = copy.deepcopy(stored_workflow)
        draft_body = {
            "operation": "version_draft",
            "request_id": body.get("request_id"),
            "draft_id": body.get("draft_id"),
            "text": body.get("text"),
        }
        for name in ("expected_factual_revision", "expected_legal_revision", "expected_evidence_revision", "expected_proof_revision"):
            if name in body:
                draft_body[name] = body[name]
        try:
            written = version_draft(working, draft_body, actor_principal_id=scope["actor_principal_id"],
                                    membership=scope["membership"], action="case.update")
        except Exception:
            current = _read_editor_file(directory_fd)
            current_bytes = json.dumps(current, sort_keys=True).encode("utf-8") if current else b""
            if current_bytes != before_bytes:
                raise HTTPException(status_code=409, detail="stale_revision") from None
            raise
        again = _read_editor_file(directory_fd)
        again_bytes = json.dumps(again, sort_keys=True).encode("utf-8") if again else b""
        if again_bytes != before_bytes:
            conflict = project_draft_editor(document, save_state="conflict")
            conflict["code"] = "stale_revision"
            conflict["overwrote_head"] = False
            return JSONResponse(status_code=409, content=conflict)
        next_head = head if written.get("replayed") is True else head + 1
        sealed_document = {"head_revision": next_head, "draft_workflow": working.get("draft_workflow") or {}}
        envelope = _seal_draft(sealed_document, decision, key_id, key)
        _write_editor_file(directory_fd, next_head, envelope)
        reread = _loaded_document(directory_fd, decision, session)
        if reread is None or int(reread.get("head_revision") or 0) != next_head:
            raise HTTPException(status_code=503, detail="case_revision_unavailable")
        _publish_memory(case_file, reread)
        projected = project_draft_editor(reread, save_state="saved")
        projected["replayed"] = written.get("replayed") is True
        projected["overwrote_head"] = True
        return projected


async def require_composed_document_authorizer(request: Request) -> None:
    """When production composition is active, document and download handlers require its decision."""

    from .case_routes import COMPOSITION_NAME

    if getattr(request.app.state, "case_route_composition", None) != COMPOSITION_NAME:
        raise HTTPException(status_code=401, detail="authorizer_required")
    decision = getattr(request.state, "case_authorization", None)
    if decision is None or not getattr(decision, "permits_case_content", False):
        raise HTTPException(status_code=401, detail="authorizer_required")


def create_document_router(mediator: Any) -> APIRouter:
    router = APIRouter(dependencies=[Depends(require_composed_document_authorizer)])

    @router.post("/api/documents/formal-complaint")
    async def build_formal_complaint_document(
        request: FormalComplaintDocumentRequest,
    ) -> Dict[str, Any]:
        if not request.output_formats:
            raise HTTPException(status_code=400, detail="At least one output format is required")
        from .case_routes import case_download_root, CaseAccessError
        try:
            output_root = case_download_root()
        except CaseAccessError:
            raise HTTPException(status_code=503, detail="case_handler_unavailable") from None
        if request.output_dir is not None or request.email_timeline_handoff_path or request.email_authority_enrichment_path:
            raise HTTPException(status_code=403, detail="host_path_not_permitted")
        if request.enable_agentic_optimization or request.optimization_llm_config:
            raise HTTPException(status_code=403, detail="case_processing_not_configured")
        build_kwargs = dict(
            user_id=request.user_id,
            court_name=request.court_name,
            district=request.district,
            county=request.county,
            division=request.division,
            court_header_override=request.court_header_override,
            case_number=request.case_number,
            lead_case_number=request.lead_case_number,
            related_case_number=request.related_case_number,
            assigned_judge=request.assigned_judge,
            courtroom=request.courtroom,
            title_override=request.title_override,
            plaintiff_names=request.plaintiff_names,
            defendant_names=request.defendant_names,
            requested_relief=request.requested_relief,
            jury_demand=request.jury_demand,
            jury_demand_text=request.jury_demand_text,
            signer_name=request.signer_name,
            signer_title=request.signer_title,
            signer_firm=request.signer_firm,
            signer_bar_number=request.signer_bar_number,
            signer_contact=request.signer_contact,
            additional_signers=[detail.model_dump(exclude_none=True) for detail in request.additional_signers],
            declarant_name=request.declarant_name,
            service_method=request.service_method,
            service_recipients=request.service_recipients,
            service_recipient_details=[detail.model_dump(exclude_none=True) for detail in request.service_recipient_details],
            signature_date=request.signature_date,
            verification_date=request.verification_date,
            service_date=request.service_date,
            affidavit_title=request.affidavit_title,
            affidavit_intro=request.affidavit_intro,
            affidavit_facts=request.affidavit_facts,
            affidavit_supporting_exhibits=[detail.model_dump(exclude_none=True) for detail in request.affidavit_supporting_exhibits],
            affidavit_include_complaint_exhibits=request.affidavit_include_complaint_exhibits,
            affidavit_venue_lines=request.affidavit_venue_lines,
            affidavit_jurat=request.affidavit_jurat,
            affidavit_notary_block=request.affidavit_notary_block,
            enable_agentic_optimization=request.enable_agentic_optimization,
            optimization_max_iterations=request.optimization_max_iterations,
            optimization_target_score=request.optimization_target_score,
            optimization_provider=request.optimization_provider,
            optimization_model_name=request.optimization_model_name,
            optimization_persist_artifacts=request.optimization_persist_artifacts,
            email_timeline_handoff_path=request.email_timeline_handoff_path,
            email_authority_enrichment_path=request.email_authority_enrichment_path,
            output_dir=str(output_root),
            output_formats=request.output_formats,
        )
        if request.optimization_llm_config:
            build_kwargs["optimization_llm_config"] = request.optimization_llm_config
        payload = mediator.build_formal_complaint_document_package(**build_kwargs)
        payload = _annotate_artifacts_with_download_urls(payload)
        return _annotate_review_links(payload, mediator=mediator, user_id=request.user_id)

    @router.get("/api/documents/download")
    async def download_generated_document(path: str = Query(...)) -> FileResponse:
        from .case_routes import case_download_root, CaseAccessError
        try:
            root = case_download_root()
        except CaseAccessError:
            raise HTTPException(status_code=503, detail="case_handler_unavailable") from None
        file_path = Path(path).resolve()
        if not file_path.is_relative_to(root):
            raise HTTPException(status_code=403, detail="case_download_denied")
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Generated document not found")
        return FileResponse(path=str(file_path), filename=file_path.name)

    def _workflow_case_file() -> Dict[str, Any]:
        case_file = getattr(mediator, "intake_case_file", None)
        if not isinstance(case_file, dict):
            raise HTTPException(status_code=503, detail="workflow_record_unavailable")
        return case_file

    def _workflow_scope(case_id: str, request: Request) -> Dict[str, Any]:
        decision = getattr(request.state, "case_authorization", None)
        if decision is None or decision.case_id != case_id:
            raise HTTPException(status_code=403, detail="cross_case_id")
        return {
            "actor_principal_id": decision.actor_principal_id,
            "membership": decision.membership,
            "action": decision.action,
        }

    def _workflow_error(exc: Exception) -> HTTPException:
        from .case_review import CaseReviewError
        code = exc.code if isinstance(exc, CaseReviewError) else "workflow_unavailable"
        status = 409 if code in {"stale_domain", "stale_revision", "replay_mismatch"} else 403 if code in {
            "actor_not_permitted", "export_authorization_required", "automatic_filing_refused", "legal_sufficiency_refused", "cross_case_id",
        } else 422 if code in {
            "draft_field", "draft_bounds", "stage_not_ready", "review_required", "draft_revision_required", "review_field", "review_bounds",
        } else 503
        return HTTPException(status_code=status, detail=code)

    @router.get("/api/documents/{case_id}/complaint-outline")
    async def read_complaint_outline(case_id: str, request: Request) -> Dict[str, Any]:
        _workflow_scope(case_id, request)
        return project_complaint_outline(_workflow_case_file())

    @router.get("/api/documents/{case_id}/draft-editor")
    async def read_draft_editor(
        case_id: str,
        request: Request,
        base_revision: Optional[int] = Query(default=None),
        compare_revision: Optional[int] = Query(default=None),
    ) -> Dict[str, Any]:
        scope = _workflow_scope(case_id, request)
        _require_draft_owner(scope, request)
        try:
            return _project_locked_editor(case_id, request, base_revision=base_revision, compare_revision=compare_revision)
        except HTTPException:
            raise
        except Exception as exc:
            raise _editor_error(exc) from None

    @router.post("/api/documents/{case_id}/draft-editor")
    async def save_draft_editor(case_id: str, request: Request) -> Dict[str, Any]:
        scope = _workflow_scope(case_id, request)
        _require_draft_owner(scope, request)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=422, detail="draft_field") from None
        if not isinstance(body, dict):
            raise HTTPException(status_code=422, detail="draft_field")
        try:
            return _save_locked_editor(case_id, request, body, scope)
        except HTTPException:
            raise
        except Exception as exc:
            raise _editor_error(exc) from None

    @router.get("/api/documents/{case_id}/workflow-stage")
    async def read_workflow_stage(case_id: str, request: Request) -> Dict[str, Any]:
        from .case_review import CaseReviewError, project_workflow_stage
        _workflow_scope(case_id, request)
        try:
            return project_workflow_stage(_workflow_case_file())
        except CaseReviewError as exc:
            raise _workflow_error(exc) from None

    @router.post("/api/documents/{case_id}/draft-versions")
    async def write_draft_version(case_id: str, request: Request) -> Dict[str, Any]:
        from .case_review import CaseReviewError, version_draft
        scope = _workflow_scope(case_id, request)
        try:
            return version_draft(_workflow_case_file(), await request.json(), **scope)
        except CaseReviewError as exc:
            raise _workflow_error(exc) from None

    @router.post("/api/documents/{case_id}/draft-reviews")
    async def write_draft_review(case_id: str, request: Request) -> Dict[str, Any]:
        from .case_review import CaseReviewError, review_draft_version
        scope = _workflow_scope(case_id, request)
        try:
            return review_draft_version(_workflow_case_file(), await request.json(), **scope)
        except CaseReviewError as exc:
            raise _workflow_error(exc) from None

    @router.post("/api/documents/{case_id}/draft-exports")
    async def write_draft_export(case_id: str, request: Request) -> Dict[str, Any]:
        from .case_review import CaseReviewError, export_draft_version
        scope = _workflow_scope(case_id, request)
        try:
            return export_draft_version(_workflow_case_file(), await request.json(), **scope)
        except CaseReviewError as exc:
            raise _workflow_error(exc) from None

    @router.get("/api/documents/optimization-trace")
    async def retrieve_optimization_trace(cid: str = Query(...)) -> Dict[str, Any]:
        # A caller-selected CID has no per-case provenance. Later private
        # artifact routes may admit a scoped reference; this legacy path may not.
        raise HTTPException(status_code=403, detail="trace_reference_not_bound")

    return router


def attach_document_routes(app: FastAPI, mediator: Any) -> FastAPI:
    return attach_router_routes(app, create_document_router(mediator))
