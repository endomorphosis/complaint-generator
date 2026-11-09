"""Legacy draft assembly delegated from FormalComplaintDocumentBuilder."""

from __future__ import annotations

from complaint_phases.document_pipeline import (
    ComplaintPhase,
    DEFAULT_RELIEF,
    STATE_DEFAULT_RELIEF,
    _build_anchored_chronology_summary_from_case_file,
    _coerce_list,
    _collect_temporal_registry_identifiers,
    _collect_unresolved_temporal_issue_identifiers,
    _dedupe_text_values,
    _extract_text_candidates,
    _roman,
    _safe_call,
    _unique_preserving_order,
    _utcnow,
    build_intake_case_review_summary,
    summarize_temporal_issue_registry,
)

def _build_legacy_draft(
    self,
    *,
    user_id: str,
    court_name: str,
    district: str,
    county: Optional[str],
    division: Optional[str],
    court_header_override: Optional[str],
    case_number: Optional[str],
    lead_case_number: Optional[str],
    related_case_number: Optional[str],
    assigned_judge: Optional[str],
    courtroom: Optional[str],
    title_override: Optional[str],
    plaintiff_names: Optional[List[str]],
    defendant_names: Optional[List[str]],
    requested_relief: Optional[List[str]],
    jury_demand: Optional[bool],
    jury_demand_text: Optional[str],
    signer_name: Optional[str],
    signer_title: Optional[str],
    signer_firm: Optional[str],
    signer_bar_number: Optional[str],
    signer_contact: Optional[str],
    additional_signers: Optional[List[Dict[str, str]]],
    declarant_name: Optional[str],
    service_method: Optional[str],
    service_recipients: Optional[List[str]],
    service_recipient_details: Optional[List[Dict[str, str]]],
    signature_date: Optional[str],
    verification_date: Optional[str],
    service_date: Optional[str],
    affidavit_title: Optional[str],
    affidavit_intro: Optional[str],
    affidavit_facts: Optional[List[str]],
    affidavit_supporting_exhibits: Optional[List[Dict[str, str]]],
    affidavit_include_complaint_exhibits: Optional[bool],
    affidavit_venue_lines: Optional[List[str]],
    affidavit_jurat: Optional[str],
    affidavit_notary_block: Optional[List[str]],
) -> Dict[str, Any]:
    state = getattr(self.mediator, "state", None)
    phase_manager = getattr(self.mediator, "phase_manager", None)
    intake_case_file = phase_manager.get_phase_data(ComplaintPhase.INTAKE, "intake_case_file") if phase_manager else None
    generated_complaint = self._get_existing_formal_complaint()
    classification = getattr(state, "legal_classification", {}) or {}
    statutes = _coerce_list(getattr(state, "applicable_statutes", []) or [])
    requirements = getattr(state, "summary_judgment_requirements", {}) or {}
    support_summary = _safe_call(self.mediator, "summarize_claim_support", user_id=user_id) or {}
    support_claims = support_summary.get("claims", {}) if isinstance(support_summary, dict) else {}
    claim_types = self._derive_claim_types(
        generated_complaint,
        classification,
        support_claims,
        requirements,
        user_id=user_id,
    )
    plaintiffs, defendants = self._derive_parties(
        generated_complaint,
        plaintiff_names=plaintiff_names,
        defendant_names=defendant_names,
    )
    title = title_override or generated_complaint.get("title") or self._derive_title(plaintiffs, defendants)
    exhibits = self._collect_exhibits(user_id=user_id, claim_types=claim_types, support_claims=support_claims)
    fact_entries = self._build_summary_fact_entries(
        user_id=user_id,
        generated_complaint=generated_complaint,
        classification=classification,
        state=state,
    )
    fact_entries = self._annotate_entries_with_exhibits(fact_entries, exhibits)
    facts = [str(entry.get("text") or "").strip() for entry in fact_entries if str(entry.get("text") or "").strip()]
    claims_for_relief = self._build_claims_for_relief(
        user_id=user_id,
        claim_types=claim_types,
        requirements=requirements,
        statutes=statutes,
        support_claims=support_claims,
        exhibits=exhibits,
    )
    factual_allegation_entries = self._build_factual_allegation_entries(
        summary_fact_entries=fact_entries,
        claims_for_relief=claims_for_relief,
    )
    factual_allegations = self._build_factual_allegations(
        summary_of_facts=facts,
        claims_for_relief=claims_for_relief,
    )
    relief_items = _unique_preserving_order(
        list(requested_relief or [])
        + list(generated_complaint.get("prayer_for_relief", []) or [])
        + self._extract_requested_relief_from_facts(facts)
        + self._build_claim_specific_relief(claim_types=claim_types, facts=facts)
        + (STATE_DEFAULT_RELIEF if str(classification.get("jurisdiction") or "").strip().lower() == "state" else DEFAULT_RELIEF)
    )
    jury_demand_block = self._build_jury_demand(jury_demand=jury_demand, jury_demand_text=jury_demand_text)
    court_header = self._build_court_header(
        court_name=court_name,
        district=district,
        county=county,
        division=division,
        override=court_header_override,
    )
    jurisdiction_statement = self._build_jurisdiction_statement(
        classification=classification,
        statutes=statutes,
        court_name=court_name,
    )
    venue_statement = self._build_venue_statement(
        district=district,
        county=county,
        division=division,
        classification=classification,
        court_name=court_name,
    )
    nature_of_action = self._build_nature_of_action(
        claim_types=claim_types,
        classification=classification,
        statutes=statutes,
        court_name=court_name,
    )
    legal_standards = self._build_legal_standards_summary(statutes=statutes, requirements=requirements)
    signature_block = self._build_signature_block(
        plaintiffs,
        signer_name=signer_name,
        signer_title=signer_title,
        signer_firm=signer_firm,
        signer_bar_number=signer_bar_number,
        signer_contact=signer_contact,
        additional_signers=additional_signers,
        signature_date=signature_date,
    )
    verification = self._build_verification(
        plaintiffs,
        declarant_name=declarant_name,
        signer_name=signer_name,
        verification_date=verification_date,
        jurisdiction=classification.get("jurisdiction"),
    )
    certificate_of_service = self._build_certificate_of_service(
        plaintiffs,
        defendants,
        signer_name=signer_name,
        service_method=service_method,
        service_recipients=service_recipients,
        service_recipient_details=service_recipient_details,
        service_date=service_date,
        jurisdiction=classification.get("jurisdiction"),
    )

    draft = {
        "court_header": court_header,
        "case_caption": {
            "plaintiffs": plaintiffs,
            "defendants": defendants,
            "case_number": case_number or "________________",
            "county": county.strip().upper() if isinstance(county, str) and county.strip() else None,
            "lead_case_number": lead_case_number.strip() if isinstance(lead_case_number, str) and lead_case_number.strip() else None,
            "related_case_number": related_case_number.strip() if isinstance(related_case_number, str) and related_case_number.strip() else None,
            "assigned_judge": assigned_judge.strip() if isinstance(assigned_judge, str) and assigned_judge.strip() else None,
            "courtroom": courtroom.strip() if isinstance(courtroom, str) and courtroom.strip() else None,
            "jury_demand_notice": "JURY TRIAL DEMANDED" if jury_demand_block else None,
            "document_title": "COMPLAINT",
        },
        "title": title,
        "nature_of_action": nature_of_action,
        "parties": {
            "plaintiffs": plaintiffs,
            "defendants": defendants,
        },
        "jurisdiction_statement": jurisdiction_statement,
        "venue_statement": venue_statement,
        "factual_allegations": factual_allegations,
        "factual_allegation_entries": factual_allegation_entries,
        "summary_of_facts": facts,
        "summary_of_fact_entries": fact_entries,
        "anchored_chronology_summary": _build_anchored_chronology_summary_from_case_file(
            intake_case_file if isinstance(intake_case_file, dict) else {}
        ),
        "claims_for_relief": claims_for_relief,
        "legal_standards": legal_standards,
        "requested_relief": relief_items,
        "jury_demand": jury_demand_block,
        "exhibits": exhibits,
        "signature_block": signature_block,
        "verification": verification,
        "certificate_of_service": certificate_of_service,
        "source_context": {
            "user_id": user_id,
            "claim_types": claim_types,
            "district": district,
            "jurisdiction": classification.get("jurisdiction", "unknown"),
            "generated_at": _utcnow().isoformat(),
        },
        "affidavit_overrides": self._build_affidavit_overrides(
            affidavit_title=affidavit_title,
            affidavit_intro=affidavit_intro,
            affidavit_facts=affidavit_facts,
            affidavit_supporting_exhibits=affidavit_supporting_exhibits,
            affidavit_include_complaint_exhibits=affidavit_include_complaint_exhibits,
            affidavit_venue_lines=affidavit_venue_lines,
            affidavit_jurat=affidavit_jurat,
            affidavit_notary_block=affidavit_notary_block,
        ),
    }
    self._annotate_claim_temporal_gap_hints(draft)
    self._attach_allegation_references(draft)
    self._annotate_case_caption_display(draft)
    draft["affidavit"] = self._build_affidavit(draft)
    draft["draft_text"] = self._render_draft_text(draft)
    return draft


def _build_claim_support_temporal_handoff(self, document_optimization: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    optimization_report = document_optimization if isinstance(document_optimization, dict) else {}
    optimization_handoff = optimization_report.get("claim_support_temporal_handoff")
    if isinstance(optimization_handoff, dict) and optimization_handoff:
        return dict(optimization_handoff)

    intake_case_summary = optimization_report.get("intake_case_summary")
    if not isinstance(intake_case_summary, dict) or not intake_case_summary:
        intake_case_summary = build_intake_case_review_summary(self.mediator)
    if not isinstance(intake_case_summary, dict) or not intake_case_summary:
        return {}

    packet_summary = intake_case_summary.get("claim_support_packet_summary")
    packet_summary = packet_summary if isinstance(packet_summary, dict) else {}
    alignment_tasks = intake_case_summary.get("alignment_evidence_tasks")
    alignment_tasks = alignment_tasks if isinstance(alignment_tasks, list) else []
    temporal_issue_registry_summary = summarize_temporal_issue_registry(
        intake_case_summary.get("temporal_issue_registry_summary")
    )

    unresolved_temporal_issue_ids = _dedupe_text_values(
        packet_summary.get("claim_support_unresolved_temporal_issue_ids") or []
    )
    event_ids: List[str] = []
    temporal_fact_ids: List[str] = []
    temporal_relation_ids: List[str] = []
    timeline_anchor_ids: List[str] = []
    timeline_issue_ids: List[str] = []
    temporal_issue_ids: List[str] = []
    missing_temporal_predicates: List[str] = []
    required_provenance_kinds: List[str] = []
    temporal_proof_bundle_ids: List[str] = []
    temporal_proof_objectives: List[str] = []

    for task in alignment_tasks:
        if not isinstance(task, dict):
            continue
        event_ids.extend(_dedupe_text_values(task.get("event_ids") or []))
        temporal_fact_ids.extend(_dedupe_text_values(task.get("temporal_fact_ids") or []))
        temporal_relation_ids.extend(_dedupe_text_values(task.get("temporal_relation_ids") or []))
        timeline_anchor_ids.extend(_dedupe_text_values(task.get("anchor_ids") or task.get("timeline_anchor_ids") or []))
        timeline_issue_ids.extend(_dedupe_text_values(task.get("timeline_issue_ids") or []))
        temporal_issue_ids.extend(_dedupe_text_values(task.get("temporal_issue_ids") or []))
        missing_temporal_predicates.extend(_dedupe_text_values(task.get("missing_temporal_predicates") or []))
        required_provenance_kinds.extend(_dedupe_text_values(task.get("required_provenance_kinds") or []))
        proof_bundle_id = str(task.get("temporal_proof_bundle_id") or "").strip()
        if proof_bundle_id:
            temporal_proof_bundle_ids.append(proof_bundle_id)
        proof_objective = str(task.get("temporal_proof_objective") or "").strip()
        if proof_objective:
            temporal_proof_objectives.append(proof_objective)

    raw_event_ids = _collect_temporal_registry_identifiers(
        intake_case_summary.get("event_ledger"),
        "event_id",
    )
    raw_temporal_fact_ids = _collect_temporal_registry_identifiers(
        intake_case_summary.get("temporal_fact_registry"),
        "temporal_fact_id",
        "fact_id",
        "event_id",
    )
    if not raw_temporal_fact_ids:
        raw_temporal_fact_ids = _collect_temporal_registry_identifiers(
            intake_case_summary.get("event_ledger"),
            "temporal_fact_id",
            "event_id",
            "fact_id",
        )
    raw_temporal_relation_ids = _collect_temporal_registry_identifiers(
        intake_case_summary.get("temporal_relation_registry"),
        "temporal_relation_id",
        "relation_id",
    )
    if not raw_temporal_relation_ids:
        raw_temporal_relation_ids = _collect_temporal_registry_identifiers(
            intake_case_summary.get("timeline_relations"),
            "temporal_relation_id",
            "relation_id",
        )
    raw_temporal_issue_ids = _collect_temporal_registry_identifiers(
        intake_case_summary.get("temporal_issue_registry"),
        "temporal_issue_id",
        "issue_id",
        "timeline_issue_id",
    )
    raw_timeline_anchor_ids = _collect_temporal_registry_identifiers(
        intake_case_summary.get("timeline_anchors"),
        "anchor_id",
        "timeline_anchor_id",
    )
    raw_unresolved_temporal_issue_ids = _collect_unresolved_temporal_issue_identifiers(
        intake_case_summary.get("temporal_issue_registry")
    )
    summary_issue_ids = _dedupe_text_values(temporal_issue_registry_summary.get("issue_ids") or [])
    summary_missing_temporal_predicates = _dedupe_text_values(
        temporal_issue_registry_summary.get("missing_temporal_predicates") or []
    )
    summary_required_provenance_kinds = _dedupe_text_values(
        temporal_issue_registry_summary.get("required_provenance_kinds") or []
    )

    unresolved_temporal_issue_count = int(
        packet_summary.get("claim_support_unresolved_temporal_issue_count", 0) or 0
    )
    if not unresolved_temporal_issue_count and raw_unresolved_temporal_issue_ids:
        unresolved_temporal_issue_count = len(raw_unresolved_temporal_issue_ids)
    if not unresolved_temporal_issue_count:
        unresolved_temporal_issue_count = int(temporal_issue_registry_summary.get("unresolved_count") or 0)
    if not unresolved_temporal_issue_ids:
        unresolved_temporal_issue_ids = raw_unresolved_temporal_issue_ids

    temporal_handoff = {
        "unresolved_temporal_issue_count": unresolved_temporal_issue_count,
        "unresolved_temporal_issue_ids": unresolved_temporal_issue_ids,
        "chronology_task_count": int(packet_summary.get("temporal_gap_task_count", 0) or 0),
        "event_ids": _dedupe_text_values(event_ids) or raw_event_ids,
        "temporal_fact_ids": _dedupe_text_values(temporal_fact_ids) or raw_temporal_fact_ids,
        "temporal_relation_ids": _dedupe_text_values(temporal_relation_ids) or raw_temporal_relation_ids,
        "timeline_issue_ids": _dedupe_text_values(timeline_issue_ids) or raw_temporal_issue_ids or summary_issue_ids,
        "temporal_issue_ids": _dedupe_text_values(temporal_issue_ids) or raw_temporal_issue_ids or summary_issue_ids,
        "temporal_proof_bundle_ids": _dedupe_text_values(temporal_proof_bundle_ids),
        "temporal_proof_objectives": _dedupe_text_values(temporal_proof_objectives),
    }
    normalized_timeline_anchor_ids = _dedupe_text_values(timeline_anchor_ids) or raw_timeline_anchor_ids
    if normalized_timeline_anchor_ids:
        temporal_handoff["timeline_anchor_ids"] = normalized_timeline_anchor_ids
    normalized_missing_temporal_predicates = _dedupe_text_values(missing_temporal_predicates) or summary_missing_temporal_predicates
    if normalized_missing_temporal_predicates:
        temporal_handoff["missing_temporal_predicates"] = normalized_missing_temporal_predicates
    normalized_required_provenance_kinds = _dedupe_text_values(required_provenance_kinds) or summary_required_provenance_kinds
    if normalized_required_provenance_kinds:
        temporal_handoff["required_provenance_kinds"] = normalized_required_provenance_kinds
    if not temporal_handoff["unresolved_temporal_issue_count"] and not any(
        temporal_handoff.get(key)
        for key in (
            "unresolved_temporal_issue_ids",
            "event_ids",
            "temporal_fact_ids",
            "temporal_relation_ids",
            "timeline_anchor_ids",
            "timeline_issue_ids",
            "temporal_issue_ids",
            "missing_temporal_predicates",
            "required_provenance_kinds",
            "temporal_proof_bundle_ids",
            "temporal_proof_objectives",
        )
    ):
        return {}
    return temporal_handoff


def _adapt_formal_complaint_to_package_draft(self, formal_complaint: Dict[str, Any]) -> Dict[str, Any]:
    caption = formal_complaint.get("caption", {}) if isinstance(formal_complaint.get("caption"), dict) else {}
    claims_for_relief = []
    for claim in _coerce_list(formal_complaint.get("legal_claims")):
        if not isinstance(claim, dict):
            continue
        normalized_missing_elements = _unique_preserving_order(
            _extract_text_candidates(claim.get("missing_requirements"))
        )
        claims_for_relief.append(
            {
                "claim_type": claim.get("claim_type") or claim.get("claim_name") or claim.get("title") or "Claim",
                "count_title": claim.get("claim_name") or claim.get("title") or "Claim",
                "legal_standards": _unique_preserving_order(
                    [claim.get("legal_standard", "")]
                    + [
                        f"{item.get('citation')} - {item.get('element')}"
                        if item.get("citation")
                        else str(item.get("element") or "")
                        for item in _coerce_list(claim.get("legal_standard_elements"))
                        if isinstance(item, dict) and (item.get("element") or item.get("citation"))
                    ]
                ),
                "supporting_facts": _unique_preserving_order(_extract_text_candidates(claim.get("supporting_facts"))),
                "missing_elements": normalized_missing_elements,
                "partially_supported_elements": [],
                "support_summary": {
                    "elements_satisfied": claim.get("elements_satisfied", ""),
                    "authority_count": len(_coerce_list(claim.get("supporting_authorities"))),
                    "temporal_gap_hint_count": sum(
                        1
                        for item in normalized_missing_elements
                        if str(item or "").strip().lower().startswith("chronology gap")
                    ),
                },
                "supporting_exhibits": [
                    {
                        "label": exhibit.get("label"),
                        "title": exhibit.get("title"),
                        "link": exhibit.get("reference") or exhibit.get("source_url") or exhibit.get("link"),
                    }
                    for exhibit in _coerce_list(claim.get("supporting_exhibits"))
                    if isinstance(exhibit, dict)
                ],
            }
        )

    legal_standards = []
    for standard in _coerce_list(formal_complaint.get("legal_standards")):
        if isinstance(standard, dict):
            claim_name = str(standard.get("claim_name") or standard.get("claim_type") or "").strip()
            body = str(standard.get("standard") or "").strip()
            citations = ", ".join(_unique_preserving_order(_extract_text_candidates(standard.get("citations"))))
            if claim_name and body and citations:
                legal_standards.append(f"{claim_name}: {body} ({citations})")
            elif claim_name and body:
                legal_standards.append(f"{claim_name}: {body}")
            elif body:
                legal_standards.append(body)
        else:
            text = str(standard or "").strip()
            if text:
                legal_standards.append(text)

    exhibits = []
    for exhibit in _coerce_list(formal_complaint.get("exhibits")):
        if not isinstance(exhibit, dict):
            continue
        exhibits.append(
            {
                "label": exhibit.get("label"),
                "title": exhibit.get("title") or exhibit.get("description") or "Supporting exhibit",
                "claim_type": exhibit.get("claim_type"),
                "kind": exhibit.get("kind") or "evidence",
                "link": exhibit.get("reference") or exhibit.get("source_url") or exhibit.get("link") or "",
                "source_ref": exhibit.get("cid") or exhibit.get("reference") or "",
                "summary": exhibit.get("summary") or exhibit.get("description") or "",
            }
        )

    nature_of_action = formal_complaint.get("nature_of_action")
    if isinstance(nature_of_action, str):
        nature_of_action = [nature_of_action]

    factual_allegations = _unique_preserving_order(
        _extract_text_candidates(formal_complaint.get("factual_allegations") or formal_complaint.get("summary_of_facts"))
    )
    if not factual_allegations:
        factual_allegations = self._build_factual_allegations(
            summary_of_facts=_extract_text_candidates(formal_complaint.get("summary_of_facts")),
            claims_for_relief=claims_for_relief,
        )

    draft = {
        "court_header": formal_complaint.get("court_header", ""),
        "case_caption": {
            "plaintiffs": _coerce_list(formal_complaint.get("parties", {}).get("plaintiffs", [])) if isinstance(formal_complaint.get("parties"), dict) else [],
            "defendants": _coerce_list(formal_complaint.get("parties", {}).get("defendants", [])) if isinstance(formal_complaint.get("parties"), dict) else [],
            "case_number": caption.get("case_number") or formal_complaint.get("case_number") or "________________",
            "county": caption.get("county_line") or ((formal_complaint.get("caption") or {}).get("county_line") if isinstance(formal_complaint.get("caption"), dict) else ""),
            "lead_case_number": caption.get("lead_case_number") or ((formal_complaint.get("caption") or {}).get("lead_case_number") if isinstance(formal_complaint.get("caption"), dict) else ""),
            "related_case_number": caption.get("related_case_number") or ((formal_complaint.get("caption") or {}).get("related_case_number") if isinstance(formal_complaint.get("caption"), dict) else ""),
            "assigned_judge": caption.get("assigned_judge") or ((formal_complaint.get("caption") or {}).get("assigned_judge") if isinstance(formal_complaint.get("caption"), dict) else ""),
            "courtroom": caption.get("courtroom") or ((formal_complaint.get("caption") or {}).get("courtroom") if isinstance(formal_complaint.get("caption"), dict) else ""),
            "jury_demand_notice": caption.get("jury_demand_notice") or ((formal_complaint.get("caption") or {}).get("jury_demand_notice") if isinstance(formal_complaint.get("caption"), dict) else ""),
            "document_title": "COMPLAINT",
        },
        "title": formal_complaint.get("title") or caption.get("case_title") or "Complaint",
        "nature_of_action": _unique_preserving_order(_extract_text_candidates(nature_of_action)),
        "parties": formal_complaint.get("parties", {}),
        "jurisdiction_statement": formal_complaint.get("jurisdiction_statement", ""),
        "venue_statement": formal_complaint.get("venue_statement", ""),
        "factual_allegations": factual_allegations,
        "summary_of_facts": _unique_preserving_order(_extract_text_candidates(formal_complaint.get("summary_of_facts") or formal_complaint.get("factual_allegations"))),
        "anchored_chronology_summary": _unique_preserving_order(
            _extract_text_candidates(formal_complaint.get("anchored_chronology_summary"))
        ),
        "claims_for_relief": claims_for_relief,
        "legal_standards": _unique_preserving_order(legal_standards),
        "requested_relief": _unique_preserving_order(_extract_text_candidates(formal_complaint.get("requested_relief") or formal_complaint.get("prayer_for_relief"))),
        "jury_demand": formal_complaint.get("jury_demand", {}),
        "exhibits": exhibits,
        "signature_block": formal_complaint.get("signature_block", {}),
        "verification": formal_complaint.get("verification", {}),
        "certificate_of_service": formal_complaint.get("certificate_of_service", {}),
        "source_context": {
            "generated_at": formal_complaint.get("generated_at") or _utcnow().isoformat(),
            "district": formal_complaint.get("district") or caption.get("district") or "",
            "jurisdiction": formal_complaint.get("jurisdiction", "unknown"),
        },
    }
    self._annotate_claim_temporal_gap_hints(draft)
    self._attach_allegation_references(draft)
    self._annotate_case_caption_display(draft)
    built_affidavit = self._build_affidavit(draft)
    existing_affidavit = formal_complaint.get("affidavit", {}) if isinstance(formal_complaint.get("affidavit"), dict) else {}
    draft["affidavit"] = {**built_affidavit, **existing_affidavit}
    rendered_draft_text = self._render_draft_text(draft)
    supplied_draft_text = str(formal_complaint.get("draft_text") or "").strip()
    expected_case_line = (
        f"{draft['case_caption'].get('case_number_label', 'Civil Action No.')} "
        f"{draft['case_caption'].get('case_number', '________________')}"
    )
    draft["draft_text"] = (
        supplied_draft_text
        if supplied_draft_text and expected_case_line in supplied_draft_text
        else rendered_draft_text
    )
    return draft


def _render_draft_text(self, draft: Dict[str, Any]) -> str:
    caption = draft.get("case_caption", {}) if isinstance(draft.get("case_caption"), dict) else {}
    parties = draft.get("parties", {}) if isinstance(draft.get("parties"), dict) else {}
    signature_block = draft.get("signature_block", {}) if isinstance(draft.get("signature_block"), dict) else {}
    plaintiff_list = parties.get("plaintiffs", []) or caption.get("plaintiffs", []) or ["Plaintiff"]
    defendant_list = parties.get("defendants", []) or caption.get("defendants", []) or ["Defendant"]
    plaintiffs = ", ".join(plaintiff_list)
    defendants = ", ".join(defendant_list)
    forum_type = self._resolve_draft_forum_type(draft)
    caption_party_lines = caption.get("caption_party_lines") if isinstance(caption.get("caption_party_lines"), list) else self._build_caption_party_lines(caption)
    party_section_lines = self._build_party_section_lines(
        plaintiffs=plaintiff_list,
        defendants=defendant_list,
        forum_type=forum_type,
    )
    case_number_label = str(caption.get("case_number_label") or "Civil Action No.")
    lead_case_number_label = str(caption.get("lead_case_number_label") or "Lead Case No.")
    related_case_number_label = str(caption.get("related_case_number_label") or "Related Case No.")
    assigned_judge_label = str(caption.get("assigned_judge_label") or "Assigned Judge")
    courtroom_label = str(caption.get("courtroom_label") or "Courtroom")
    lines = [
        str(draft.get("court_header") or "IN THE COURT OF COMPETENT JURISDICTION"),
        *([str(caption.get("county"))] if caption.get("county") else []),
        "",
        *caption_party_lines,
        f"{case_number_label} {caption.get('case_number', '________________')}",
        *([f"{lead_case_number_label} {caption.get('lead_case_number')}"] if caption.get('lead_case_number') else []),
        *([f"{related_case_number_label} {caption.get('related_case_number')}"] if caption.get('related_case_number') else []),
        *([f"{assigned_judge_label}: {caption.get('assigned_judge')}"] if caption.get('assigned_judge') else []),
        *([f"{courtroom_label}: {caption.get('courtroom')}"] if caption.get('courtroom') else []),
        "",
        str(caption.get("document_title") or "COMPLAINT"),
        *([str(caption.get("jury_demand_notice"))] if caption.get("jury_demand_notice") else []),
        "",
        "NATURE OF THE ACTION",
    ]
    lines.extend(self._normalize_text_lines(draft.get("nature_of_action", [])))
    lines.extend([
        "",
        "PARTIES",
        *party_section_lines,
        "",
        "JURISDICTION AND VENUE",
    ])
    if draft.get("jurisdiction_statement"):
        lines.append(str(draft["jurisdiction_statement"]))
    if draft.get("venue_statement"):
        lines.append(str(draft["venue_statement"]))
    lines.extend(["", "FACTUAL ALLEGATIONS"])
    lines.extend(self._grouped_allegation_text_lines(draft))
    chronology_lines = self._normalize_text_lines(draft.get("anchored_chronology_summary", []))
    if chronology_lines:
        lines.extend(["", "ANCHORED CHRONOLOGY"])
        lines.extend(self._numbered_lines(chronology_lines))
    authority_summary_lines = self._normalize_text_lines(draft.get("email_authority_summary_lines", []))
    if authority_summary_lines:
        lines.extend(["", "EMAIL-ALIGNED AUTHORITY SUPPORT"])
        lines.extend(self._bulletize_lines(authority_summary_lines))
    claims = draft.get("claims_for_relief", []) if isinstance(draft.get("claims_for_relief"), list) else []
    if claims:
        lines.extend(["", "CLAIMS FOR RELIEF"])
    for index, claim in enumerate(claims, start=1):
        lines.extend([
            "",
            f"COUNT {_roman(index)} - {claim.get('count_title', claim.get('claim_type', 'Claim'))}",
        ])
        lines.extend(self._build_claim_render_lines(claim))
        missing = self._normalize_text_lines(claim.get("missing_elements", []))
        if missing:
            lines.append("Open Support Gaps:")
            lines.extend([f"- {line}" for line in missing])
    lines.extend(["", "REQUESTED RELIEF"])
    if forum_type == "state":
        lines.append("Wherefore, Plaintiff prays for judgment against Defendant as follows:")
    lines.extend(self._numbered_lines(draft.get("requested_relief", [])))
    jury_demand = draft.get("jury_demand", {}) if isinstance(draft.get("jury_demand"), dict) else {}
    if jury_demand:
        lines.extend(["", str(jury_demand.get("title") or "JURY DEMAND").upper()])
        if jury_demand.get("text"):
            lines.append(str(jury_demand.get("text")))
    exhibits = draft.get("exhibits", []) if isinstance(draft.get("exhibits"), list) else []
    if exhibits:
        lines.extend(["", "EXHIBITS"])
        for exhibit in exhibits:
            if not isinstance(exhibit, dict):
                continue
            text = f"{exhibit.get('label', 'Exhibit')} - {exhibit.get('title', 'Supporting exhibit')}"
            if exhibit.get("link"):
                text = f"{text} ({exhibit['link']})"
            lines.append(text)
            if exhibit.get("summary"):
                lines.append(f"  {exhibit['summary']}")
    verification = draft.get("verification", {}) if isinstance(draft.get("verification"), dict) else {}
    if verification:
        lines.extend([
            "",
            str(verification.get("title") or "Verification").upper(),
            str(verification.get("text") or ""),
            str(verification.get("dated") or ""),
            str(verification.get("signature_line") or ""),
        ])
    certificate_of_service = draft.get("certificate_of_service", {}) if isinstance(draft.get("certificate_of_service"), dict) else {}
    if certificate_of_service:
        lines.extend([
            "",
            str(certificate_of_service.get("title") or "Certificate of Service").upper(),
            str(certificate_of_service.get("text") or ""),
            str(certificate_of_service.get("dated") or ""),
            str(certificate_of_service.get("signature_line") or ""),
        ])
    affidavit = draft.get("affidavit", {}) if isinstance(draft.get("affidavit"), dict) else {}
    if affidavit:
        lines.extend([
            "",
            str(affidavit.get("title") or "AFFIDAVIT IN SUPPORT OF COMPLAINT"),
        ])
        lines.extend(str(line) for line in _coerce_list(affidavit.get("venue_lines")) if str(line or "").strip())
        lines.extend([
            "",
            str(affidavit.get("intro") or ""),
            str(affidavit.get("knowledge_graph_note") or ""),
            "",
            "Affiant states as follows:",
        ])
        lines.extend(self._numbered_lines(affidavit.get("facts", [])))
        supporting_exhibits = affidavit.get("supporting_exhibits") if isinstance(affidavit.get("supporting_exhibits"), list) else []
        if supporting_exhibits:
            lines.extend(["", "AFFIDAVIT SUPPORTING EXHIBITS"])
            for exhibit in supporting_exhibits:
                if not isinstance(exhibit, dict):
                    continue
                exhibit_text = f"{exhibit.get('label', 'Exhibit')} - {exhibit.get('title', 'Supporting exhibit')}"
                if exhibit.get("link"):
                    exhibit_text = f"{exhibit_text} ({exhibit['link']})"
                lines.append(exhibit_text)
        lines.extend([
            "",
            str(affidavit.get("dated") or ""),
            str(affidavit.get("signature_line") or ""),
            str(affidavit.get("jurat") or ""),
        ])
        lines.extend(str(line) for line in _coerce_list(affidavit.get("notary_block")) if str(line or "").strip())
    lines.extend(["", *self._build_signature_section_lines(signature_block, forum_type)])
    return "\n".join(line for line in lines if line is not None)
